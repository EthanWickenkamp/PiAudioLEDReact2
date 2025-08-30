# wled_audio_v2_sender.py
# Audio → WLED Audio Sync V2 (44-byte variant with padding + frameCounter) over UDP.
# Target: WLED 0.14+ / MoonModules builds that decode the 44B struct on UDP port (default 11988).
#
# Packet fields (per frame):
#   header[6]       = b"00002\x00"
#   float sampleRaw = pre-AGC loudness (RMS)
#   float sampleSmth= post-AGC loudness (smoothed/normalized)
#   uint8 samplePeak= beat flag (0/1)
#   uint8 frameCtr  = rolling counter (helps ignore duplicates)
#   uint8 fft[16]   = 16-band spectrum, 0..255
#   float FFT_Mag   = magnitude of strongest FFT bin
#   float FFT_Peak  = freq (Hz) of strongest FFT bin (WLED clamps to 1..11025 Hz)

import os, socket, struct, time, math
import numpy as np
import sounddevice as sd

# ── Network / device ────────────────────────────────────────────────────────────
HOST = os.getenv("WLED_HOST", "192.168.50.165")  # WLED IP (unicast). Valid: any reachable IP.
PORT = int(os.getenv("WLED_PORT", "11988"))      # Must match WLED Sync→Receive. Typical: 11988.
IN_PCM = os.getenv("IN_PCM", None)               # ALSA device, e.g. "hw:Loopback,1,1" or numeric index.

# ── Audio capture ───────────────────────────────────────────────────────────────
SR = int(os.getenv("SAMPLE_RATE", "44100"))      # 8000..48000 typical. 44100 is safe.
BS = int(os.getenv("BLOCKSIZE", "512"))          # 256..2048. Smaller = snappier peaks, more CPU.
CH = int(os.getenv("CHANNELS", "2"))             # 1 or 2. Stereo will be averaged to mono.

# ── Spectrum bands (GEQ) ───────────────────────────────────────────────────────
# 16 log-spaced bands between F_MIN..F_MAX (Hz). Effects expect 16 bins.
F_MIN = float(os.getenv("F_MIN", "40"))          # 20..80 typical. Lowers emphasize bass.
F_MAX = float(os.getenv("F_MAX", "10000"))       # 6k..16k typical. Higher adds more treble detail.
BAND_EDGES = np.geomspace(F_MIN, F_MAX, 17)

# Compression/scale from linear energy → 0..255 bins:
BAND_COMP_EXP = float(os.getenv("BAND_COMP_EXP", "0.5"))  # 0.35..0.8; lower = stronger compression (more vivid).
BAND_SCALE    = float(os.getenv("BAND_SCALE", "128"))     # 64..192; overall intensity of bins.
BAND_FLOOR    = float(os.getenv("BAND_FLOOR", "0.01"))    # 0.0..0.05; subtract small floor to kill hiss/idle.

# ── AGC (auto gain control) for sampleSmth ──────────────────────────────────────
AGC_TARGET   = float(os.getenv("AGC_TARGET", "0.6"))      # 0.3..0.8; higher = louder normalized level (more movement).
AGC_STRENGTH = float(os.getenv("AGC_STRENGTH", "0.02"))   # 0.01..0.08; responsiveness of gain.

# ── Beat detector (drives many peak-based effects) ──────────────────────────────
PEAK_ATTACK  = float(os.getenv("PEAK_ATTACK",  "0.3"))    # 0.1..0.5; how fast envelope rises.
PEAK_RELEASE = float(os.getenv("PEAK_RELEASE", "0.05"))   # 0.02..0.2; how fast it falls.
PEAK_THRESH  = float(os.getenv("PEAK_THRESH",  "1.3"))    # 1.1..2.5; ratio above envelope to register a peak.
PEAK_HOLD_MS = int(os.getenv("PEAK_HOLD_MS",   "120"))    # 40..200 ms; hold flag so effects see the beat.

# ── Wire format (44 bytes) ─────────────────────────────────────────────────────
HEADER = b"00002\x00"                      # 6 bytes including NUL
PACK_FMT_44 = "<6s 2x f f B B 16B 2x f f"  # little-endian; explicit pads to reach 44 bytes
assert struct.calcsize(PACK_FMT_44) == 44

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_frame = 0  # 0..255 rolling frame counter

# Internal state
_rms_smooth = 0.0
_env = 0.0
_last_peak_time = 0.0

def send_packet(sampleRaw, sampleSmth, peak, bands, mag, hz):
    """Pack and send one 44B V2 telemetry frame."""
    global _frame
    _frame = (_frame + 1) & 0xFF
    # clip bands to uint8
    b = [int(max(0, min(255, int(v)))) for v in bands]
    # clamp freq like firmware does (won't hurt if WLED clamps again)
    hz = float(min(11025.0, max(1.0, hz)))
    payload = struct.pack(PACK_FMT_44, HEADER, float(sampleRaw), float(sampleSmth),
                          int(peak) & 0xFF, _frame, *b, float(mag), hz)
    sock.sendto(payload, (HOST, PORT))

def compute_features(block):
    """Return (sampleRaw, sampleSmth, peak_flag, bands16, FFT_Magnitude, FFT_MajorPeak)."""
    global _rms_smooth, _env, _last_peak_time

    # mono mix
    x = block.mean(axis=1).astype(np.float32)

    # windowed FFT
    win = np.hanning(len(x)).astype(np.float32)
    X = np.fft.rfft(x * win)
    mag = np.abs(X).astype(np.float32)
    freqs = np.fft.rfftfreq(len(x), 1.0 / SR).astype(np.float32)

    # Loudness (RMS)
    rms = float(np.sqrt(np.mean(x * x) + 1e-12))
    _rms_smooth = 0.95 * _rms_smooth + 0.05 * rms

    # Envelope follower on |x| for beat detection
    absx = float(np.abs(x).mean())
    if absx > _env:
        _env = PEAK_ATTACK * absx + (1.0 - PEAK_ATTACK) * _env
    else:
        _env = PEAK_RELEASE * absx + (1.0 - PEAK_RELEASE) * _env

    # Adaptive peak: instantaneous level vs envelope
    now = time.time()
    peak_flag = 0
    if _env > 1e-6 and (absx / max(_env, 1e-6)) > PEAK_THRESH:
        peak_flag = 1
        _last_peak_time = now
    # hold so effects catch it
    if (now - _last_peak_time) * 1000.0 < PEAK_HOLD_MS:
        peak_flag = 1

    # AGC toward target
    gain = (AGC_TARGET / _rms_smooth) if _rms_smooth > 1e-9 else 1.0
    gain = 0.98 + AGC_STRENGTH * (gain - 1.0)

    sampleRaw  = rms
    sampleSmth = min(rms * gain, 2.0)  # arbitrary safety ceiling

    # 16 GEQ bands
    bands = []
    for i in range(16):
        lo, hi = BAND_EDGES[i], BAND_EDGES[i + 1]
        m = (freqs >= lo) & (freqs < hi)
        v = float(mag[m].mean()) if m.any() else 0.0
        v = max(0.0, v - BAND_FLOOR)   # noise floor
        v *= gain                      # AGC scaling
        v = (v ** BAND_COMP_EXP) * BAND_SCALE
        bands.append(v)

    # Dominant frequency (for hue-reactive modes)
    idx = int(np.argmax(mag))
    FFT_Magnitude = float(mag[idx])
    FFT_MajorPeak = float(freqs[idx])

    return sampleRaw, sampleSmth, peak_flag, bands, FFT_Magnitude, FFT_MajorPeak

def main():
    print(f"[AUDIO] {IN_PCM or 'default'} @ {SR} Hz  BS={BS}  CH={CH}  -> {HOST}:{PORT}")
    print(f"[GEQ]  F_MIN={F_MIN}Hz  F_MAX={F_MAX}Hz  SCALE={BAND_SCALE}  COMP_EXP={BAND_COMP_EXP}  FLOOR={BAND_FLOOR}")
    print(f"[AGC]  TARGET={AGC_TARGET}  STRENGTH={AGC_STRENGTH}   [PEAK] ATTACK={PEAK_ATTACK}  RELEASE={PEAK_RELEASE}  THRESH={PEAK_THRESH}  HOLD={PEAK_HOLD_MS}ms")
    last_log = 0.0

    def cb(indata, frames, timeinfo, status):
        nonlocal last_log
        if status:
            print("Audio status:", status, flush=True)
        sR, sS, peak, bands, mag, hz = compute_features(indata.copy())
        send_packet(sR, sS, peak, bands, mag, hz)
        now = time.time()
        if now - last_log > 1.0:
            # Log min/max AFTER scaling (pre-clip); helps tune SCALE/EXP/FLOOR.
            print(f"rms={sR:.3f} smth={sS:.3f} peak={peak} bands={int(min(bands))}..{int(max(bands))} mag={mag:.2f} hz={hz:.0f}")
            last_log = now

    with sd.InputStream(device=IN_PCM, samplerate=SR, channels=CH,
                        blocksize=BS, dtype="float32", callback=cb):
        print("[AUDIO] Streaming… Ctrl+C to stop")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
