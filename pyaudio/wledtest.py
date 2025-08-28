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
# FIXED Layout based on WLED 0.14.0+ v2 format:
# struct audioSyncPacket_v2 {
#   char header[6] = "00002\0";     // 6 bytes
#   float sampleRaw;                // 4 bytes - raw sample or AGC'd sample
#   float sampleSmth;               // 4 bytes - smoothed sample (sampleAvg or sampleAgc)
#   uint8_t samplePeak;             // 1 byte  - 0=no peak, >=1 peak detected
#   uint8_t reserved1;              // 1 byte  - reserved
#   uint8_t fftResult[16];          // 16 bytes - FFT results per GEQ channel
#   float FFT_Magnitude;            // 4 bytes - magnitude of strongest peak
#   float FFT_MajorPeak;            // 4 bytes - frequency of strongest peak
# };
PKT_FMT = "<6sffBB16Bff"  # Little-endian format
HEADER  = b"00002\x00"    # Correct header for v2 format
_prev_smth = [0.0]

def to_audio_sync_packet(frame: np.ndarray, sr: int) -> bytes:
    # frame: float32, shape (N, 2) in [-1,1]
    if frame.ndim == 2 and frame.shape[1] >= 2:
        x = (frame[:, 0] + frame[:, 1]) * 0.5
    else:
        x = frame.astype(np.float32).ravel()

    # Calculate RMS for sampleRaw (this should be the "current" sample level)
    rms = float(np.sqrt(np.mean(x**2)))
    
    # Apply basic AGC scaling to make it more responsive
    # Scale RMS to a more reasonable range (WLED expects values roughly 0-512 range)
    sample_raw = rms * 512.0
    
    # Simple smoothing for sampleSmth (this represents smoothed/averaged sample)
    alpha = 0.1  # Slower smoothing for sampleSmth
    _prev_smth[0] = (1 - alpha) * _prev_smth[0] + alpha * sample_raw
    sample_smth = _prev_smth[0]

    # Peak detection - WLED uses this as a boolean flag
    peak_level = float(np.max(np.abs(x)))
    sample_peak = 1 if peak_level > 0.3 else 0  # Threshold for peak detection

    # FFT → 16 frequency bins for GEQ
    N = len(x)
    if N < 64:  # Ensure we have enough samples for meaningful FFT
        N = 64
        x = np.pad(x, (0, 64 - len(x)), 'constant')
    
    # Apply window function
    win = np.hanning(N).astype(np.float32)
    X = np.fft.rfft(x * win)
    mag = np.abs(X)
    freqs = np.fft.rfftfreq(N, 1.0 / sr)

    # Create 16 logarithmic frequency bands (similar to GEQ)
    # WLED typically uses bands from ~40Hz to ~10kHz
    f_lo, f_hi = 40.0, min(10000.0, sr/2)
    
    if f_hi <= f_lo:
        f_hi = sr/4  # Fallback
    
    # Create 17 edges for 16 bands
    edges = np.logspace(np.log10(f_lo), np.log10(f_hi), 17)
    fft_bands = []
    
    for i in range(16):
        # Find frequency indices for this band
        idx_start = np.searchsorted(freqs, edges[i])
        idx_end = np.searchsorted(freqs, edges[i+1])
        
        if idx_end > idx_start:
            # Average magnitude in this band
            band_mag = np.mean(mag[idx_start:idx_end])
        else:
            band_mag = 0.0
        
        fft_bands.append(band_mag)
    
    # Normalize FFT bands to 0-255 range
    max_band = max(fft_bands) if fft_bands else 1.0
    if max_band > 0:
        fft_u8 = [min(255, int((band / max_band) * 255)) for band in fft_bands]
    else:
        fft_u8 = [0] * 16

    # Find dominant frequency and its magnitude
    if len(mag) > 1:
        dominant_idx = int(np.argmax(mag[1:]) + 1)  # Skip DC component
        fft_magnitude = float(mag[dominant_idx])
        fft_major_peak = float(freqs[dominant_idx])
    else:
        fft_magnitude = 0.0
        fft_major_peak = 0.0

    # Pack the packet according to WLED v2 format
    return struct.pack(PKT_FMT, 
                      HEADER,           # 6 bytes: "00002\0"
                      sample_raw,       # 4 bytes: float sampleRaw
                      sample_smth,      # 4 bytes: float sampleSmth  
                      sample_peak,      # 1 byte:  uint8_t samplePeak
                      0,                # 1 byte:  uint8_t reserved1
                      *fft_u8,          # 16 bytes: uint8_t fftResult[16]
                      fft_magnitude,    # 4 bytes: float FFT_Magnitude
                      fft_major_peak)   # 4 bytes: float FFT_MajorPeak

# ---------- Run ----------
print("\n=== WLED Audio Sync Sender (v2 Format) ===")
print(f"Capture Device idx: {DEV_INDEX}  name: {sd.query_devices(DEV_INDEX)['name']}")
print(f"Sample Rate:        {SAMPLE_RATE} Hz")
print(f"Frame Size:         {FRAME_SIZE}")
print(f"Sending to:         {WLED_HOST}:{WLED_SR_PORT}")
print(f"Packet size:        {struct.calcsize(PKT_FMT)} bytes\n")

try:
    with sd.InputStream(device=DEV_INDEX,
                        channels=CHANNELS,
                        samplerate=SAMPLE_RATE,
                        blocksize=FRAME_SIZE,
                        dtype='float32') as stream:
        print("✅ Input stream opened, streaming to WLED… (Ctrl+C to stop)")
        last_log = 0.0
        packet_count = 0
        
        while True:
            data, overflowed = stream.read(FRAME_SIZE)
            if overflowed:
                print("⚠️  Audio buffer overflow!", flush=True)
            
            # Create and send packet
            pkt = to_audio_sync_packet(data, SAMPLE_RATE)
            sock.sendto(pkt, (WLED_HOST, WLED_SR_PORT))
            packet_count += 1

            # Enhanced logging every ~1 second
            now = time.time()
            if now - last_log > 1.0:
                last_log = now
                
                # Calculate current levels for display
                if data.ndim == 2:
                    mono = (data[:, 0] + data[:, 1]) * 0.5
                else:
                    mono = data.flatten()
                
                rms = float(np.sqrt(np.mean(mono**2)))
                peak = float(np.max(np.abs(mono)))
                scaled_rms = rms * 512.0
                
                print(f"Packets: {packet_count:6d} | RMS: {rms:.4f} | Scaled: {scaled_rms:6.1f} | Peak: {peak:.4f}", flush=True)

except KeyboardInterrupt:
    print(f"\nStopped after sending {packet_count} packets.")
except Exception as e:
    print(f"Error: {e}")
finally:
    sock.close()