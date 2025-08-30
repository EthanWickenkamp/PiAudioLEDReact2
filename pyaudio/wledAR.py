# wled_audio_v2_sender.py
import os, socket, struct, time, math
import numpy as np
import sounddevice as sd

# ---- Env / config ----
HOST = os.getenv("WLED_HOST", "192.168.50.165")
PORT = int(os.getenv("WLED_PORT", "11988"))  # match WLED Sync->Receive
INPUT_DEVICE = os.getenv("IN_PCM", None)  # e.g. "hw:Loopback,1,1"
SR   = int(os.getenv("SAMPLE_RATE", "44100"))
BS   = int(os.getenv("BLOCKSIZE", "1024"))
CH   = int(os.getenv("CHANNELS", "2"))

# Choose packet variant: 44 (C++ lib with gaps+frameCounter) or 40 (pure V2)
V2_VARIANT = int(os.getenv("V2_VARIANT", "44"))
HEADER = b"00002\x00"  # 6 bytes including NUL
PACK_FMT_44 = "<6s 2x f f B B 16B 2x f f"  # 44 bytes
PACK_FMT_40 = "<6s f f B B 16B f f"        # 40 bytes
assert struct.calcsize(PACK_FMT_44) == 44 and struct.calcsize(PACK_FMT_40) == 40
SEND_FMT = PACK_FMT_44 if V2_VARIANT == 44 else PACK_FMT_40

# FFT band edges (log) and scaling knobs
F_MIN = float(os.getenv("F_MIN", "40"))     # Hz
F_MAX = float(os.getenv("F_MAX", "10000"))  # Hz
BAND_EDGES = np.geomspace(F_MIN, F_MAX, 17)

BAND_COMP_EXP = float(os.getenv("BAND_COMP_EXP", "0.5"))  # sqrt by default
BAND_SCALE    = float(os.getenv("BAND_SCALE", "64"))      # increase if bands feel low
BAND_FLOOR    = float(os.getenv("BAND_FLOOR", "0.0"))     # subtract a small floor to kill noise

# AGC knobs
AGC_TARGET   = float(os.getenv("AGC_TARGET", "0.4"))
AGC_STRENGTH = float(os.getenv("AGC_STRENGTH", "0.02"))

# Peak detector knobs
PEAK_ATTACK   = float(os.getenv("PEAK_ATTACK", "0.2"))   # faster rise
PEAK_RELEASE  = float(os.getenv("PEAK_RELEASE", "0.05")) # slower fall
PEAK_THRESH   = float(os.getenv("PEAK_THRESH", "1.8"))   # ratio over envelope to call a peak
PEAK_HOLD_MS  = int(os.getenv("PEAK_HOLD_MS", "80"))     # hold flag briefly to ensure visibility

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_frame = 0

def send_packet(sampleRaw, sampleSmth, peak, bands, mag, hz):
    global _frame
    bands = [int(max(0, min(255, int(b)))) for b in bands]

    if V2_VARIANT == 44:
        _frame = (_frame + 1) & 0xFF
        payload = struct.pack(PACK_FMT_44, HEADER, float(sampleRaw), float(sampleSmth),
                              int(peak) & 0xFF, _frame, *bands, float(mag), float(hz))
    else:
        payload = struct.pack(PACK_FMT_40, HEADER, float(sampleRaw), float(sampleSmth),
                              int(peak) & 0xFF, 0, *bands, float(mag), float(hz))
    sock.sendto(payload, (HOST, PORT))

# ---- state ----
_rms_smooth = 0.0
_env = 0.0
_last_peak_time = 0.0

def compute_features(block):
    global _rms_smooth, _env, _last_peak_time

    # mono
    x = block.mean(axis=1).astype(np.float32)

    # window & FFT
    win = np.hanning(len(x)).astype(np.float32)
    X = np.fft.rfft(x * win)
    mag = np.abs(X).astype(np.float32)
    freqs = np.fft.rfftfreq(len(x), 1.0/SR).astype(np.float32)

    # RMS (pre-AGC) and smoothed
    rms = float(np.sqrt(np.mean(x*x) + 1e-12))
    _rms_smooth = 0.95*_rms_smooth + 0.05*rms

    # Envelope follower for peak detection (on abs waveform)
    absx = np.abs(x).mean()  # quick-and-dirty level
    if absx > _env:
        _env = PEAK_ATTACK * absx + (1.0 - PEAK_ATTACK)*_env
    else:
        _env = PEAK_RELEASE * absx + (1.0 - PEAK_RELEASE)*_env

    # Adaptive peak: if instantaneous amplitude exceeds envelope * threshold → peak
    now = time.time()
    peak_flag = 0
    if _env > 1e-6 and (absx / _env) > PEAK_THRESH:
        peak_flag = 1
        _last_peak_time = now
    # hold the flag briefly so effects see it
    if (now - _last_peak_time) * 1000.0 < PEAK_HOLD_MS:
        peak_flag = 1

    # AGC gain toward target
    gain = (AGC_TARGET / _rms_smooth) if _rms_smooth > 1e-9 else 1.0
    gain = 0.98 + AGC_STRENGTH * (gain - 1.0)

    sampleRaw  = rms
    sampleSmth = min(rms * gain, 2.0)

    # 16 bands
    bands = []
    for i in range(16):
        lo, hi = BAND_EDGES[i], BAND_EDGES[i+1]
        m = (freqs >= lo) & (freqs < hi)
        v = float(mag[m].mean()) if m.any() else 0.0
        v = max(0.0, v - BAND_FLOOR)   # noise floor
        v *= gain
        v = (v ** BAND_COMP_EXP) * BAND_SCALE
        bands.append(v)

    # Peak bin & magnitude
    idx = int(np.argmax(mag))
    FFT_Magnitude = float(mag[idx])
    FFT_MajorPeak = float(freqs[idx])

    return sampleRaw, sampleSmth, peak_flag, bands, FFT_Magnitude, FFT_MajorPeak

def main():
    print(f"[AUDIO] {INPUT_DEVICE or 'default'} @ {SR} Hz, BS={BS}, CH={CH} -> {HOST}:{PORT}  V2={V2_VARIANT}")
    print(f"[KNOBS] BAND_SCALE={BAND_SCALE}  COMP_EXP={BAND_COMP_EXP}  AGC_TARGET={AGC_TARGET}  PEAK_THRESH={PEAK_THRESH}")
    last_log = 0.0

    def cb(indata, frames, timeinfo, status):
        nonlocal last_log
        if status:
            print("Audio status:", status, flush=True)
        sR, sS, peak, bands, mag, hz = compute_features(indata.copy())
        send_packet(sR, sS, peak, bands, mag, hz)
        now = time.time()
        if now - last_log > 1.0:
            print(f"rms={sR:.3f} smth={sS:.3f} peak={peak} bands={int(min(bands))}..{int(max(bands))} mag={mag:.2f} hz={hz:.0f}")
            last_log = now

    with sd.InputStream(device=INPUT_DEVICE, samplerate=SR, channels=CH,
                        blocksize=BS, dtype="float32", callback=cb):
        print("[AUDIO] Streaming… Ctrl+C to stop")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
