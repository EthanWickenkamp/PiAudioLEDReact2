# Sends WLED Audio UDP V2 packets ("00002\0", 40 bytes).
# Default TEST_MODE=1: synthetic band sweep (proves packet/port/WLED mode).
# Set TEST_MODE=0 to capture audio from ALSA (Loopback).

import os, socket, struct, time, math
import numpy as np

HOST = os.getenv("WLED_HOST", "192.168.50.165")
PORT = int(os.getenv("WLED_AUDIO_PORT", "11988"))
TEST_MODE = os.getenv("TEST_MODE", "1") == "1"

INPUT_DEVICE = os.getenv("INPUT_DEVICE", None)  # e.g. "hw:Loopback,1,1"
SR   = int(os.getenv("SAMPLE_RATE", "44100"))
BS   = int(os.getenv("BLOCKSIZE", "1024"))
CH   = int(os.getenv("CHANNELS", "2"))

HEADER = b"00002\x00"                 # 6 bytes (with NUL)
PACK_FMT = "<6s f f B B 16B f f"      # little-endian, total 40 bytes
assert struct.calcsize(PACK_FMT) == 40

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def send_packet(sampleRaw, sampleSmth, peak_flag, bands16, mag, peak_hz):
    bands16 = [int(max(0, min(255, int(b)))) for b in bands16]
    payload = struct.pack(PACK_FMT, HEADER, float(sampleRaw), float(sampleSmth),
                          int(peak_flag) & 0xFF, 0, *bands16, float(mag), float(peak_hz))
    sock.sendto(payload, (HOST, PORT))

def test_sweep(fps=20):
    print(f"[TEST] Sweep -> {HOST}:{PORT} (Ctrl+C to stop)")
    k = 0
    interval = 1.0/max(1,fps)
    while True:
        bands = [0]*16
        pos = k % 16
        for i in range(16):
            d = (i - pos) % 16
            bands[i] = max(0, 255 - d*60)
        send_packet(0.3, 0.6, (k % 8 == 0), bands, 1.0, 440.0 + 200.0*math.sin(k*0.15))
        k += 1
        time.sleep(interval)

def run_audio():
    import sounddevice as sd
    print(f"[AUDIO] Input={INPUT_DEVICE or 'default'} SR={SR} BS={BS} CH={CH} -> {HOST}:{PORT}")

    agc_target, agc_strength, rms_smooth, last_log = 0.4, 0.02, 0.0, 0.0
    F_MIN, F_MAX = 20.0, 8000.0
    edges = np.geomspace(F_MIN, F_MAX, 17)

    def compute_features(block):
        nonlocal rms_smooth
        x = block.mean(axis=1).astype(np.float32)
        win = np.hanning(len(x)).astype(np.float32)
        X = np.fft.rfft(x * win)
        mag = np.abs(X).astype(np.float32)
        freqs = np.fft.rfftfreq(len(x), 1.0/SR).astype(np.float32)

        rms = float(np.sqrt(np.mean(x*x) + 1e-12))
        rms_smooth = 0.95*rms_smooth + 0.05*rms
        peak_flag = 1 if (np.max(np.abs(x)) > 0.8) else 0

        gain = (agc_target / rms_smooth) if rms_smooth > 1e-6 else 1.0
        gain = 0.98 + agc_strength * (gain - 1.0)

        sampleRaw  = rms
        sampleSmth = min(rms * gain, 1.5)

        bands = []
        for i in range(16):
            lo, hi = edges[i], edges[i+1]
            m = (freqs >= lo) & (freqs < hi)
            v = float(mag[m].mean()) if m.any() else 0.0
            v *= gain
            bands.append(int(max(0, min(255, (v**0.5)*48))))

        idx = int(np.argmax(mag))
        return sampleRaw, sampleSmth, peak_flag, bands, float(mag[idx]), float(freqs[idx])

    def cb(indata, frames, timeinfo, status):
        nonlocal last_log
        if status:
            print("Audio status:", status, flush=True)
        sR, sS, peak, bands, mag, hz = compute_features(indata.copy())
        send_packet(sR, sS, peak, bands, mag, hz)
        now = time.time()
        if now - last_log > 1.0:
            print(f"rms={sR:.3f} smth={sS:.3f} peak={peak} bands={min(bands)}..{max(bands)} mag={mag:.2f} hz={hz:.0f}")
            last_log = now

    with sd.InputStream(device=INPUT_DEVICE, samplerate=SR, channels=CH,
                        blocksize=BS, dtype="float32", callback=cb):
        print("[AUDIO] Streaming… Ctrl+C to stop")
        while True:
            time.sleep(1)

if __name__ == "__main__":
    print(f"WLED V2 -> {HOST}:{PORT} | TEST_MODE={'1' if TEST_MODE else '0'} (packet=40 bytes)")
    try:
        if TEST_MODE: test_sweep()
        else: run_audio()
    except KeyboardInterrupt:
        print("\nStopped.")
