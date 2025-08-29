# wled_audio_v2_test.py
# Sends WLED Audio UDP V2 packets ("00002\0", 40 bytes).
# Default: TEST_MODE=1 -> synthetic band sweep (no audio device required).
# Set TEST_MODE=0 to use ALSA input (requires sounddevice).

import os, socket, struct, time, math
import numpy as np

# -------------------------
# Environment / config
# -------------------------
HOST = os.getenv("WLED_HOST", "192.168.50.165")
PORT = int(os.getenv("WLED_AUDIO_PORT", "11988"))   # match WLED Sync->Receive port
TEST_MODE = os.getenv("TEST_MODE", "1") == "1"      # 1 = run synthetic test
INPUT_DEVICE = os.getenv("INPUT_DEVICE", None)      # e.g. "hw:Loopback,1,1"
SR   = int(os.getenv("SAMPLE_RATE", "44100"))
BS   = int(os.getenv("BLOCKSIZE", "1024"))
CH   = int(os.getenv("CHANNELS", "2"))

# -------------------------
# Packet format (V2, 40 bytes)
# -------------------------
HEADER = b"00002\x00"                  # 6 bytes including NUL
PACK_FMT = "<6s f f B B 16B f f"       # little-endian
PACK_SIZE = struct.calcsize(PACK_FMT)  # should be 40
assert PACK_SIZE == 40, f"PACK_SIZE={PACK_SIZE} (!=40)"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def send_packet(sampleRaw, sampleSmth, peak_flag, bands16, mag, peak_hz):
    """Send one V2 packet to WLED."""
    if len(bands16) != 16:
        raise ValueError("bands16 must have 16 uint8 values")
    # Clip/convert bands to uint8
    bands16 = [int(max(0, min(255, int(b)))) for b in bands16]
    payload = struct.pack(
        PACK_FMT,
        HEADER,
        float(sampleRaw),
        float(sampleSmth),
        int(peak_flag) & 0xFF,
        0,                # reserved1
        *bands16,
        float(mag),
        float(peak_hz)
    )
    # sanity: 40 bytes
    if len(payload) != 40:
        raise RuntimeError(f"Packed payload is {len(payload)} bytes (expected 40)")
    sock.sendto(payload, (HOST, PORT))

# -------------------------
# TEST MODE (no audio needed)
# -------------------------
def test_sweep(fps=30, duration_sec=0):  # duration_sec=0 -> loop forever
    print(f"[TEST] Sending synthetic band sweep to {HOST}:{PORT} (Ctrl+C to stop)")
    print("Make sure WLED: Effect is an AudioReactive effect, Sync->Receive ON, port matches.")
    interval = 1.0 / max(1, fps)
    k = 0
    start = time.time()
    while True:
        bands = [0]*16
        # bright "cursor" + a little tail
        pos = k % 16
        for i in range(16):
            d = (i - pos) % 16
            bands[i] = max(0, 255 - d*60)  # simple trailing falloff

        sampleRaw  = 0.3
        sampleSmth = 0.6
        peak       = 1 if (k % 8 == 0) else 0
        mag        = 1.0 + 0.2*math.sin(k*0.2)
        hz         = 440.0 + 200.0*math.sin(k*0.15)

        send_packet(sampleRaw, sampleSmth, peak, bands, mag, hz)

        k += 1
        if duration_sec and (time.time() - start) > duration_sec:
            break
        time.sleep(interval)

# -------------------------
# AUDIO MODE (requires sounddevice)
# -------------------------
def run_audio():
    try:
        import sounddevice as sd
    except Exception as e:
        raise SystemExit(f"sounddevice import failed. Set TEST_MODE=1 or install it. Error: {e}")

    print(f"[AUDIO] Input={INPUT_DEVICE or 'default'} SR={SR} BS={BS} CH={CH} -> {HOST}:{PORT}")

    # simple AGC state
    agc_target = 0.4
    agc_strength = 0.02
    rms_smooth = 0.0
    last_log = 0.0

    # 16 log-spaced bands ~20..8000 Hz
    F_MIN, F_MAX = 20.0, 8000.0
    band_edges = np.geomspace(F_MIN, F_MAX, 17)  # 17 edges, 16 bands

    def compute_features(block):
        nonlocal rms_smooth
        # mono
        x = block.mean(axis=1).astype(np.float32)
        # window & FFT
        win = np.hanning(len(x)).astype(np.float32)
        X = np.fft.rfft(x * win)
        mag = np.abs(X).astype(np.float32)
        freqs = np.fft.rfftfreq(len(x), 1.0/SR).astype(np.float32)

        # RMS & peak flag
        rms = float(np.sqrt(np.mean(x*x) + 1e-12))
        rms_smooth = 0.95*rms_smooth + 0.05*rms
        peak_flag = 1 if (np.max(np.abs(x)) > 0.8) else 0

        # gain toward target
        gain = (agc_target / rms_smooth) if rms_smooth > 1e-6 else 1.0
        gain = 0.98 + agc_strength * (gain - 1.0)

        sampleRaw  = float(rms)
        sampleSmth = float(min(rms * gain, 1.5))

        # band energies -> uint8
        bands = []
        for i in range(16):
            lo, hi = band_edges[i], band_edges[i+1]
            mask = (freqs >= lo) & (freqs < hi)
            val = float(mag[mask].mean()) if mask.any() else 0.0
            val *= gain
            # gentle compression + scale
            bands.append(int(max(0, min(255, (val**0.5)*48))))

        idx = int(np.argmax(mag))
        FFT_Magnitude = float(mag[idx])
        FFT_MajorPeak = float(freqs[idx])
        return sampleRaw, sampleSmth, peak_flag, bands, FFT_Magnitude, FFT_MajorPeak

    def cb(indata, frames, timeinfo, status):
        nonlocal last_log
        if status:
            print("Audio status:", status, flush=True)
        sR, sS, peak, bands, mag, hz = compute_features(indata.copy())
        send_packet(sR, sS, peak, bands, mag, hz)
        now = time.time()
        if now - last_log > 1.0:
            print(f"rms={sR:.3f} smth={sS:.3f} peak={peak} bands[min..max]={min(bands)}..{max(bands)} mag={mag:.2f} hz={hz:.0f}")
            last_log = now

    with sd.InputStream(
        device=INPUT_DEVICE,
        samplerate=SR,
        channels=CH,
        blocksize=BS,
        dtype="float32",
        callback=cb
    ):
        print("[AUDIO] Streaming… Ctrl+C to stop")
        while True:
            time.sleep(1)

# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    print(f"WLED V2 test -> {HOST}:{PORT} | TEST_MODE={'1' if TEST_MODE else '0'}")
    print("Packet size check:", PACK_SIZE, "bytes (expected 40)")
    try:
        if TEST_MODE:
            test_sweep(fps=20, duration_sec=0)  # run until Ctrl+C
        else:
            run_audio()
    except KeyboardInterrupt:
        print("\nStopped.")
