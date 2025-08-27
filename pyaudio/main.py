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


def main():
    print(sd.query_devices())
    print(f"[analyzer] input={DEVICE} rate={RATE} frame={FRAME} → {HOST}:{PORT}")
    with sd.InputStream(blocksize=FRAME, callback=process):
        import time
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
