import os, socket, struct, time, math
import numpy as np
import sounddevice as sd

# --- Env / config (your keys) ---
HOST = os.getenv("WLED_HOST", "192.168.50.165")
PORT = int(os.getenv("WLED_PORT", "11988"))
INPUT_DEVICE = os.getenv("IN_PCM", None)          # e.g. "hw:Loopback,1,1"
SR   = int(os.getenv("SAMPLE_RATE", "44100"))
BS   = int(os.getenv("BLOCKSIZE", "1024"))
CH   = int(os.getenv("CHANNELS", "2"))

# Mode toggles
TEST_MODE  = os.getenv("TEST_MODE", "0") == "1"         # 1 = synthetic sweep (no audio needed)
V2_VARIANT = int(os.getenv("V2_VARIANT", "44"))         # 44 = C++ lib layout, 40 = "pure" V2

# Packet layouts
HEADER = b"00002\x00"                  # 6 bytes inc. NUL
PACK_FMT_44 = "<6s 2x f f B B 16B 2x f f"  # 44 bytes (pads + frameCounter)
PACK_FMT_40 = "<6s f f B B 16B f f"        # 40 bytes (no pads, no counter)
PACK_SIZE_44 = struct.calcsize(PACK_FMT_44)
PACK_SIZE_40 = struct.calcsize(PACK_FMT_40)
assert PACK_SIZE_44 == 44 and PACK_SIZE_40 == 40

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_frame = 0

def send_packet_44(sampleRaw, sampleSmth, peak, bands, mag, hz):
    global _frame
    _frame = (_frame + 1) & 0xFF
    bands = [int(max(0, min(255, int(b)))) for b in bands]
    payload = struct.pack(PACK_FMT_44, HEADER, float(sampleRaw), float(sampleSmth),
                          int(peak) & 0xFF, _frame, *bands, float(mag), float(hz))
    sock.sendto(payload, (HOST, PORT))

def send_packet_40(sampleRaw, sampleSmth, peak, bands, mag, hz):
    bands = [int(max(0, min(255, int(b)))) for b in bands]
    payload = struct.pack(PACK_FMT_40, HEADER, float(sampleRaw), float(sampleSmth),
                          int(peak) & 0xFF, 0, *bands, float(mag), float(hz))
    sock.sendto(payload, (HOST, PORT))

SEND = send_packet_44 if V2_VARIANT == 44 else send_packet_40

# --- Audio feature extraction ---
# 16 log bands ~40..10kHz to mirror common SR tools; tweak if desired
BAND_EDGES = np.geomspace(40.0, 10000.0, 17)

# simple AGC
_agc_target = 0.4
_agc_strength = 0.02
_rms_smooth = 0.0
_last_log = 0.0

def compute_features(block):
    global _rms_smooth
    x = block.mean(axis=1).astype(np.float32)
    win = np.hanning(len(x)).astype(np.float32)
    X = np.fft.rfft(x * win)
    mag = np.abs(X).astype(np.float32)
    freqs = np.fft.rfftfreq(len(x), 1.0 / SR).astype(np.float32)

    rms = float(np.sqrt(np.mean(x * x) + 1e-12))
    _rms_smooth = 0.95 * _rms_smooth + 0.05 * rms
    peak_flag = 1 if (np.max(np.abs(x)) > 0.8) else 0

    gain = (_agc_target / _rms_smooth) if _rms_smooth > 1e-6 else 1.0
    gain = 0.98 + _agc_strength * (gain - 1.0)

    sampleRaw = rms
    sampleSmth = min(rms * gain, 1.5)

    bands = []
    for i in range(16):
        lo, hi = BAND_EDGES[i], BAND_EDGES[i + 1]
        m = (freqs >= lo) & (freqs < hi)
        v = float(mag[m].mean()) if m.any() else 0.0
        v *= gain
        # gentle compression + scale to uint8
        bands.append(int(max(0, min(255, (v ** 0.5) * 48))))

    idx = int(np.argmax(mag))
    FFT_Magnitude = float(mag[idx])
    FFT_MajorPeak = float(freqs[idx])
    return sampleRaw, sampleSmth, peak_flag, bands, FFT_Magnitude, FFT_MajorPeak

# --- Modes ---
def test_sweep(fps=20):
    print(f"[TEST] Variant={V2_VARIANT} -> {HOST}:{PORT} (Ctrl+C to stop)")
    k = 0; dt = 1.0 / max(1, fps)
    while True:
        bands = [0] * 16
        pos = k % 16
        for i in range(16):
            d = (i - pos) % 16
            bands[i] = max(0, 255 - d * 60)
        SEND(0.3, 0.6, (k % 8 == 0), bands, 1.0, 440.0 + 200.0 * math.sin(k * 0.15))
        k += 1
        time.sleep(dt)

def run_audio():
    global _last_log
    print(f"[AUDIO] {INPUT_DEVICE or 'default'} @ {SR} Hz, BS={BS}, CH={CH} -> {HOST}:{PORT} (V2={V2_VARIANT})")
    def cb(indata, frames, timeinfo, status):
        global _last_log
        if status: print("Audio status:", status, flush=True)
        sR, sS, peak, bands, mag, hz = compute_features(indata.copy())
        SEND(sR, sS, peak, bands, mag, hz)
        now = time.time()
        if now - _last_log > 1.0:
            print(f"rms={sR:.3f} smth={sS:.3f} peak={peak} bands={min(bands)}..{max(bands)} mag={mag:.2f} hz={hz:.0f}")
            _last_log = now
    with sd.InputStream(device=INPUT_DEVICE, samplerate=SR, channels=CH,
                        blocksize=BS, dtype="float32", callback=cb):
        print("[AUDIO] Streaming… Ctrl+C to stop")
        while True: time.sleep(1)

if __name__ == "__main__":
    try:
        if TEST_MODE:
            test_sweep()
        else:
            run_audio()
    except KeyboardInterrupt:
        print("\nStopped.")
