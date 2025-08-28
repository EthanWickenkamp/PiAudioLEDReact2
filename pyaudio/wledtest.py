import os, sys, socket, struct, time
import numpy as np
import sounddevice as sd

# ---------- ENV ----------
MATCH_DEVICE = os.getenv('IN_PCM', 'hw:9,1')        # match substring from sd.query_devices() like "Loopback: PCM (hw:9,1)"
SAMPLE_RATE  = int(os.getenv('SAMPLE_RATE', '44100'))
FRAME_SIZE   = int(os.getenv('FRAME_SIZE',  '1024'))
CHANNELS     = 2

WLED_HOST    = os.getenv('WLED_HOST',    '192.168.50.165')  # or '239.0.0.1' for multicast
WLED_SR_PORT = int(os.getenv('WLED_SR_PORT', '11988'))      # Audio Sync default

# ---------- Resolve PortAudio input device by name substring ----------
def resolve_input_device(match_substring: str) -> int:
    devices = sd.query_devices()
    # prefer ALSA-hostapi matches first
    hostapis = sd.query_hostapis()
    def hostapi_name(i): return hostapis[devices[i]['hostapi']]['name']
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and match_substring in d['name'] and hostapi_name(i) == 'ALSA':
            return i
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and match_substring in d['name']:
            return i
    print("No PortAudio input device matched:", match_substring)
    for i, d in enumerate(devices):
        print(f"[{i}] {d['name']}  in:{d['max_input_channels']} out:{d['max_output_channels']}")
    sys.exit(2)

DEV_INDEX = resolve_input_device(MATCH_DEVICE)

# ---------- UDP socket ----------
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ---------- Audio Sync v2 packet builder ----------
# Layout: "<6sffBB16Bff"
#   header="00002\0", sampleRaw(float), sampleSmth(float), samplePeak(u8), reserved(u8),
#   16 FFT bins (u8), FFT_Magnitude(float), FFT_MajorPeakHz(float)
PKT_FMT = "<6sffBB16Bff"
HEADER  = b"00002\x00"
_prev_smth = [0.0]

def to_audio_sync_packet(frame: np.ndarray, sr: int) -> bytes:
    # frame: float32, shape (N, 2) in [-1,1]
    if frame.ndim == 2 and frame.shape[1] >= 2:
        x = (frame[:, 0] + frame[:, 1]) * 0.5
    else:
        x = frame.astype(np.float32).ravel()

    # RMS & peak
    rms  = float(np.sqrt(np.mean(x**2)) + 1e-12)
    peak = float(np.max(np.abs(x)) + 1e-12)

    # simple smoothing
    alpha = 0.2
    _prev_smth[0] = (1 - alpha) * _prev_smth[0] + alpha * rms
    smth = _prev_smth[0]

    # FFT → 16 log bands (40..10k Hz)
    N = len(x)
    win = np.hanning(N).astype(np.float32)
    X = np.fft.rfft(x * win)
    mag = np.abs(X)
    freqs = np.fft.rfftfreq(N, 1.0 / sr)

    f_lo, f_hi = 40.0, 10000.0
    edges = np.logspace(np.log10(f_lo), np.log10(f_hi), 17)
    bins = []
    for i in range(16):
        m = (freqs >= edges[i]) & (freqs < edges[i+1])
        bins.append(float(np.mean(mag[m])) if np.any(m) else 0.0)

    mx = max(bins) or 1.0
    fft_u8 = [int(max(0, min(255, (b / mx) * 255))) for b in bins]

    idx = int(np.argmax(mag))
    fft_mag = float(mag[idx])
    fft_peak_hz = float(freqs[idx])

    sample_peak_flag = 1 if peak > 0.4 else 0
    return struct.pack(PKT_FMT, HEADER, rms, smth, sample_peak_flag, 0, *fft_u8, fft_mag, fft_peak_hz)

# ---------- Run ----------
print("\n=== WLED Audio Sync Sender ===")
print(f"Capture Device idx: {DEV_INDEX}  name: {sd.query_devices(DEV_INDEX)['name']}")
print(f"Sample Rate:        {SAMPLE_RATE} Hz")
print(f"Frame Size:         {FRAME_SIZE}")
print(f"Sending to:         {WLED_HOST}:{WLED_SR_PORT}\n")

try:
    with sd.InputStream(device=DEV_INDEX,
                        channels=CHANNELS,
                        samplerate=SAMPLE_RATE,
                        blocksize=FRAME_SIZE,
                        dtype='float32') as stream:
        print("✅ Input stream opened, streaming to WLED… (Ctrl+C to stop)")
        last = 0.0
        while True:
            data, overflowed = stream.read(FRAME_SIZE)
            if overflowed:
                print("⚠️  Overflow", flush=True)
            pkt = to_audio_sync_packet(data, SAMPLE_RATE)
            sock.sendto(pkt, (WLED_HOST, WLED_SR_PORT))

            # lightweight logging every ~0.5s
            now = time.time()
            if now - last > 0.5:
                last = now
                # show simple level
                lvl = float(np.sqrt(np.mean(data**2)))
                print(f"L:{lvl:.4f}", flush=True)

except KeyboardInterrupt:
    print("\nStopped.")
