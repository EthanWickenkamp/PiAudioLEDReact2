import os, socket, numpy as np, sounddevice as sd

DEVICE = os.getenv("INPUT_DEVICE", "hw:Loopback,1,0")
RATE   = int(os.getenv("SAMPLE_RATE", "44100"))
FRAME  = int(os.getenv("FRAME_SIZE", "1024"))
HOST   = os.getenv("WLED_HOST", "192.168.50.123")
PORT   = int(os.getenv("WLED_PORT", "21324"))

sd.default.device = (DEVICE, None)   # (input, output)
sd.default.channels = 2
sd.default.samplerate = RATE
sd.default.dtype = "float32"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def pack_simple(low, mid, high):
    # 3-band value packed into 3 bytes (expand to MoonModules V2 later)
    vals = np.clip(np.array([low, mid, high]) * 255, 0, 255).astype(np.uint8)
    return b"AW\x02" + bytes(vals)  # tiny header + 3 bands

def process(indata, frames, time, status):
    if status:  # xruns etc.
        return
    mono = indata.mean(axis=1)
    # FFT magnitudes
    spec = np.fft.rfft(mono * np.hanning(len(mono)))
    mag = np.abs(spec)
    freqs = np.fft.rfftfreq(len(mono), 1.0 / RATE)
    # crude 3-band split
    low  = np.log1p(mag[(freqs >=  40) & (freqs <  200)]).mean() if mag.size else 0
    mid  = np.log1p(mag[(freqs >= 200) & (freqs < 2000)]).mean() if mag.size else 0
    high = np.log1p(mag[(freqs >=2000) & (freqs < 8000)]).mean() if mag.size else 0
    try:
        sock.sendto(pack_simple(low, mid, high), (HOST, PORT))
    except Exception:
        pass

def main():
    print(f"[analyzer] input={DEVICE} rate={RATE} frame={FRAME} → {HOST}:{PORT}")
    with sd.InputStream(blocksize=FRAME, callback=process):
        import time
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
