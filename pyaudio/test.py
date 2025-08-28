import os, time, sys
import numpy as np
import sounddevice as sd

INPUT_DEVICE = os.getenv('IN_PCM', 'hw:Loopback,1,1')  # we will match this substring
SAMPLE_RATE  = int(os.getenv('SAMPLE_RATE', '48000'))
FRAME_SIZE   = int(os.getenv('FRAME_SIZE', '1024'))
CHANNELS     = 2

def resolve_input_device(sub):
    # Prefer ALSA devices and those with input channels
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    def hostapi_name(idx): return hostapis[devices[idx]['hostapi']]['name']
    # Try exact/parenthesized forms first
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and (
            sub in d['name'] or f"({sub})" in d['name']
        ) and hostapi_name(i) == 'ALSA':
            return i
    # Fallback: any hostapi
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and (sub in d['name'] or f"({sub})" in d['name']):
            return i
    # Last resort: print devices to help debug
    print("No PortAudio input device matched:", sub)
    print("Available devices:")
    for i, d in enumerate(devices):
        print(f"[{i}] {d['name']}  in:{d['max_input_channels']} out:{d['max_output_channels']}")
    sys.exit(2)

dev_index = resolve_input_device(INPUT_DEVICE)

print("\n=== Starting Audio Test ===")
print(f"Match String:  {INPUT_DEVICE}")
print(f"Device Index:  {dev_index}  Name: {sd.query_devices(dev_index)['name']}")
print(f"Sample Rate:   {SAMPLE_RATE} Hz")
print(f"Channels:      {CHANNELS}")
print(f"Frame Size:    {FRAME_SIZE}")
print("\nListening for audio... (Ctrl+C to stop)\n")

try:
    with sd.InputStream(device=dev_index,
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
            left, right = data[:, 0], data[:, 1]
            rms  = max(np.sqrt((left**2).mean()), np.sqrt((right**2).mean()))
            peak = max(np.abs(left).max(), np.abs(right).max())
            max_peak = max(max_peak, peak)
            if   rms > 0.01:  status, bar = "🔊 STRONG", "████████████"
            elif rms > 0.001: status, bar = "🔉 MEDIUM", "██████░░░░░░"
            elif rms > 0.0001:status, bar = "🔈 WEAK  ", "███░░░░░░░░░"
            else:              status, bar = "🔇 SILENT", "░░░░░░░░░░░░"
            print(f"{status} {bar}  peak:{peak:.3f}", end="\r")
except KeyboardInterrupt:
    print("\nStopped.")
