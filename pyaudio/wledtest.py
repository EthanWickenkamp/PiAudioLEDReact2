# wledtest.py  (runs until stopped)
import socket, struct, time, math, os, signal, sys

HOST = os.getenv("WLED_HOST", "192.168.50.165")
PORT = int(os.getenv("WLED_PORT", "21324"))

fmt = "<6s 2B f f B B 16B H f f"
stop = False
def handle_sigterm(*_):
    global stop
    stop = True
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

def pack_v2(fft_bins, frame, sample_raw=0.5, sample_smth=0.5, peak=1,
            pressure_db=65.0, zc=22, mag=1500.0, major_hz=440.0):
    header = b"00002\x00"
    p = max(0.0, min(255.0, pressure_db))
    p_int = int(p)
    p_frac = int((p - p_int) * 256.0) & 0xFF
    bins = [(b & 0xFF) for b in (fft_bins + [0]*16)[:16]]
    return struct.pack(fmt, header, p_int, p_frac,
                       float(sample_raw), float(sample_smth),
                       peak & 0xFF, frame & 0xFF,
                       *bins, int(zc) & 0xFFFF,
                       float(mag), float(major_hz))

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

frame = 0
print(f"[wledtest] sending to {HOST}:{PORT}", flush=True)
while not stop:
    idx = (frame // 2) % 16
    fft = [0]*16
    fft[idx] = 220

    mag = 1000.0 + 800.0*math.sin(frame/10.0)
    major = 400.0 + 80.0*math.sin(frame/7.0)

    pkt = pack_v2(fft, frame, sample_raw=0.7, sample_smth=0.6,
                  peak=1, pressure_db=65.0, zc=22, mag=mag, major_hz=major)
    sock.sendto(pkt, (HOST, PORT))
    if frame % 100 == 0:
        print(f"[wledtest] frame={frame}", flush=True)
    frame = (frame + 1) & 0xFF
    time.sleep(0.023)

print("[wledtest] stopping", flush=True)
