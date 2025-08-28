import os, socket, struct, numpy as np

WLED_HOST = os.getenv("WLED_HOST", "239.0.0.1")  # multicast works everywhere WLED expects it
WLED_SR_PORT = int(os.getenv("WLED_PORT", "11988"))

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# If you want to force multicast TTL etc., you can setsockopt here; not required on a LAN.

# Packet layout (V2): header "00002\0", sampleRaw (f), sampleSmth (f),
# samplePeak (u8), reserved (u8), fft[16] (u8), FFT_Magnitude (f), FFT_MajorPeak (f)
PKT_FMT = "<6sffBB16Bff"
HEADER = b"00002\x00"

def to_audio_sync_packet(samples: np.ndarray, sr: int, prev_smth=[0.0]):
    # mono mix
    if samples.ndim == 2 and samples.shape[1] >= 2:
        x = (samples[:,0] + samples[:,1]) * 0.5
    else:
        x = samples.astype(np.float32).ravel()

    # RMS, peak
    rms = float(np.sqrt(np.mean(x**2)) + 1e-12)
    peak = float(np.max(np.abs(x)) + 1e-12)

    # simple smoothing (AGC-friendly)
    alpha = 0.2
    prev_smth[0] = (1-alpha)*prev_smth[0] + alpha*rms
    smth = prev_smth[0]

    # FFT → 16 log-spaced bands (40..10000 Hz)
    N = len(x)
    win = np.hanning(N).astype(np.float32)
    X = np.fft.rfft(x * win)
    mag = np.abs(X)
    freqs = np.fft.rfftfreq(N, 1.0/sr)

    f_lo, f_hi = 40.0, 10000.0
    edges = np.logspace(np.log10(f_lo), np.log10(f_hi), 17)
    bins = []
    for i in range(16):
        m = (freqs >= edges[i]) & (freqs < edges[i+1])
        val = float(np.mean(mag[m])) if np.any(m) else 0.0
        bins.append(val)

    # normalize bins to 0..255 (naive AGC)
    mx = max(bins) or 1.0
    fft_u8 = [int(max(0, min(255, (b / mx) * 255))) for b in bins]

    # strongest peak
    idx = int(np.argmax(mag))
    fft_mag = float(mag[idx])
    fft_peak_hz = float(freqs[idx])

    # "peak" boolean: crude gate on short-term level
    sample_peak_flag = 1 if peak > 0.4 else 0

    pkt = struct.pack(PKT_FMT, HEADER, rms, smth, sample_peak_flag, 0,
                      *fft_u8, fft_mag, fft_peak_hz)
    return pkt

# In your audio loop, after you read `data` (numpy float32, shape [FRAME_SIZE, 2]):
# pkt = to_audio_sync_packet(data, SAMPLE_RATE)
# sock.sendto(pkt, (WLED_HOST, WLED_SR_PORT))
