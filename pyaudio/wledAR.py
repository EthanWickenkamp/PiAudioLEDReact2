# /app/wled_audio_v2_sender.py
import os, socket, struct, math, numpy as np
import sounddevice as sd

HOST = os.getenv("WLED_HOST", "192.168.50.165")
PORT = int(os.getenv("WLED_AUDIO_PORT", "21324"))
INPUT_DEVICE = os.getenv("INPUT_DEVICE", None)         # e.g. "hw:Loopback,1,1"
SR   = int(os.getenv("SAMPLE_RATE", "44100"))
BS   = int(os.getenv("BLOCKSIZE", "1024"))
CH   = int(os.getenv("CHANNELS", "2"))

HEADER = b"00002\x00"  # 6 bytes with NUL
PACK_FMT = "<6s f f B B 16B f f"
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# 16 log-spaced bands ~20 Hz..~8 kHz (tune as desired)
F_MIN, F_MAX = 20.0, 8000.0
BANDS = np.geomspace(F_MIN, F_MAX, 17)  # 17 edges -> 16 bands

# simple AGC state
agc_target = 0.4   # target RMS after AGC
agc_strength = 0.02
rms_smooth = 0.0

def compute_features(block):
    global rms_smooth, agc_target
    # mono
    x = block.mean(axis=1).astype(np.float32)
    # window & FFT
    win = np.hanning(len(x)).astype(np.float32)
    X = np.fft.rfft(x * win)
    mag = np.abs(X).astype(np.float32)
    freqs = np.fft.rfftfreq(len(x), 1.0/SR).astype(np.float32)

    # RMS & simple peak
    rms = float(np.sqrt(np.mean(x*x) + 1e-12))
    rms_smooth = 0.95*rms_smooth + 0.05*rms
    peak_flag = 1 if (np.max(np.abs(x)) > 0.8) else 0

    # AGC gain toward target
    if rms_smooth > 1e-6:
        gain = (agc_target / rms_smooth)
    else:
        gain = 1.0
    # ease the gain to avoid pumping
    gain = 0.98 + agc_strength * (gain - 1.0)

    # samples for packet
    sampleRaw  = float(rms)                      # pre-AGC rms (or peak)
    sampleSmth = float(min(rms * gain, 1.5))     # post-AGC-ish “smoothed”

    # 16 band energies
    bands = []
    for i in range(16):
        lo, hi = BANDS[i], BANDS[i+1]
        m = (freqs >= lo) & (freqs < hi)
        val = float(mag[m].mean()) if m.any() else 0.0
        # apply same gain to roughly normalize
        val *= gain
        # compress and scale to 0..255
        val = int(max(0, min(255, math.pow(val, 0.5)*32)))
        bands.append(val)

    # major peak (freq of max bin) and its magnitude
    idx = int(np.argmax(mag))
    FFT_Magnitude = float(mag[idx])
    FFT_MajorPeak = float(freqs[idx])

    return sampleRaw, sampleSmth, peak_flag, bands, FFT_Magnitude, FFT_MajorPeak

def send_packet(sampleRaw, sampleSmth, peak_flag, bands, mag, peak_hz):
    payload = struct.pack(
        PACK_FMT,
        HEADER,
        sampleRaw, sampleSmth,
        peak_flag, 0,                 # reserved1 = 0
        *bands,
        mag, peak_hz
    )
    sock.sendto(payload, (HOST, PORT))

def audio_cb(indata, frames, time, status):
    if status:
        print("Audio status:", status, flush=True)
    sR, sS, peak, bands, mag, hz = compute_features(indata.copy())
    send_packet(sR, sS, peak, bands, mag, hz)

def main():
    print(f"Input={INPUT_DEVICE or 'default'} SR={SR} BS={BS} CH={CH} -> {HOST}:{PORT}")
    with sd.InputStream(
        device=INPUT_DEVICE, samplerate=SR, channels=CH,
        blocksize=BS, dtype="float32", callback=audio_cb
    ):
        print("Streaming V2 audio telemetry… Ctrl+C to quit")
        import time
        while True: time.sleep(1)

if __name__ == "__main__":
    main()
