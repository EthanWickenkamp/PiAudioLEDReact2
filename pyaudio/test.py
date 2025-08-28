import os, time
import numpy as np
import sounddevice as sd

# --- Env ---
INPUT_DEVICE = os.getenv('IN_PCM', 'hw:Loopback,1,1')  # fed by bridge writing to 0,1
SAMPLE_RATE  = int(os.getenv('SAMPLE_RATE', '48000'))  # must match bridge RATE
FRAME_SIZE   = int(os.getenv('FRAME_SIZE', '1024'))
CHANNELS     = 2

print("\n=== Starting Audio Test ===")
print(f"Target Device: {INPUT_DEVICE}")
print(f"Sample Rate:   {SAMPLE_RATE} Hz")
print(f"Channels:      {CHANNELS}")
print(f"Frame Size:    {FRAME_SIZE}")
print("\nListening for audio... (Ctrl+C to stop)\n")

try:
    # Use the device string directly. If this fails, we can add a resolver later.
    with sd.InputStream(device=INPUT_DEVICE,
                        channels=CHANNELS,
                        samplerate=SAMPLE_RATE,
                        blocksize=FRAME_SIZE,
                        dtype='float32') as stream:

        print("✅ Audio stream opened successfully!")
        max_peak = 0.0
        while True:
            data, overflowed = stream.read(FRAME_SIZE)
            if overflowed:
                print("⚠️  Overflow")

            # simple stereo level meter
            left  = data[:, 0]
            right = data[:, 1]
            rms   = max(np.sqrt(np.mean(left**2)), np.sqrt(np.mean(right**2)))
            peak  = max(np.max(np.abs(left)), np.max(np.abs(right)))
            max_peak = max(max_peak, peak)

            if   rms > 0.01:  status, bar = "🔊 STRONG", "████████████"
            elif rms > 0.001: status, bar = "🔉 MEDIUM", "██████░░░░░░"
            elif rms > 0.0001:status, bar = "🔈 WEAK  ", "███░░░░░░░░░"
            else:              status, bar = "🔇 SILENT", "░░░░░░░░░░░░"

            print(f"{status} {bar}  peak:{peak:.3f}", end="\r")

except KeyboardInterrupt:
    print("\nStopped.")
