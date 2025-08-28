#!/usr/bin/env python3
"""
Minimal Audio Input Test using sounddevice
Tests audio input and provides simple feedback
"""

import sounddevice as sd
import numpy as np
import os
import time
from datetime import datetime

# Configuration from environment variables
INPUT_DEVICE = os.getenv('INPUT_DEVICE', 'hw:Loopback,1,0')
SAMPLE_RATE = int(os.getenv('SAMPLE_RATE', '44100'))
FRAME_SIZE = int(os.getenv('FRAME_SIZE', '1024'))
CHANNELS = 2  # Stereo

def list_audio_devices():
    """List all available audio devices"""
    print("\n=== Available Audio Devices ===")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        print(f"Device {i}: {device['name']}")
        print(f"  Max input channels: {device['max_input_channels']}")
        print(f"  Max output channels: {device['max_output_channels']}")
        print(f"  Default sample rate: {device['default_samplerate']}")
        if INPUT_DEVICE in device['name'] or 'Loopback' in device['name']:
            print(f"  *** POTENTIAL MATCH ***")
        print()

def find_device_index():
    """Find the device index for our target device"""
    devices = sd.query_devices()
    
    # Try exact match first
    for i, device in enumerate(devices):
        if INPUT_DEVICE in device['name'] or device['name'] in INPUT_DEVICE:
            print(f"Found exact match: {device['name']} (index {i})")
            return i
    
    # Try partial match for Loopback
    for i, device in enumerate(devices):
        if 'Loopback' in device['name'] and device['max_input_channels'] > 0:
            print(f"Found Loopback device: {device['name']} (index {i})")
            return i
    
    # Fall back to default
    print(f"No match found for '{INPUT_DEVICE}', using default input device")
    return None

def test_audio_stream():
    """Test audio input stream"""
    device_index = find_device_index()
    
    print(f"\n=== Starting Audio Test ===")
    print(f"Target Device: {INPUT_DEVICE}")
    print(f"Device Index: {device_index}")
    print(f"Sample Rate: {SAMPLE_RATE} Hz")
    print(f"Channels: {CHANNELS}")
    print(f"Frame Size: {FRAME_SIZE}")
    print("\nListening for audio... (Press Ctrl+C to stop)\n")
    
    try:
        # Test basic device access
        with sd.InputStream(device=device_index, channels=CHANNELS, 
                          samplerate=SAMPLE_RATE, blocksize=FRAME_SIZE,
                          dtype=np.float32) as stream:
            
            print("✅ Audio stream opened successfully!")
            
            sample_count = 0
            start_time = time.time()
            max_level = 0.0
            
            while True:
                # Read audio data
                data, overflowed = stream.read(FRAME_SIZE)
                
                if overflowed:
                    print("⚠️  Audio buffer overflow detected")
                
                # Calculate audio levels
                if CHANNELS == 2:
                    left_channel = data[:, 0]
                    right_channel = data[:, 1]
                    left_rms = np.sqrt(np.mean(left_channel**2))
                    right_rms = np.sqrt(np.mean(right_channel**2))
                    left_peak = np.max(np.abs(left_channel))
                    right_peak = np.max(np.abs(right_channel))
                    overall_level = max(left_rms, right_rms)
                    overall_peak = max(left_peak, right_peak)
                else:
                    audio_rms = np.sqrt(np.mean(data**2))
                    audio_peak = np.max(np.abs(data))
                    overall_level = audio_rms
                    overall_peak = audio_peak
                    left_rms = right_rms = audio_rms
                    left_peak = right_peak = audio_peak
                
                # Track maximum
                if overall_peak > max_level:
                    max_level = overall_peak
                
                sample_count += 1
                
                # Simple level indicator
                if overall_level > 0.01:
                    status = "🔊 STRONG"
                    indicator = "████████████"
                elif overall_level > 0.001:
                    status = "🔉 MEDIUM"
                    indicator = "██████░░░░░░"
                elif overall_level > 0.0001:
                    status = "🔈 WEAK  "
                    indicator = "███░░░░░░░░░"
                else:
                    status = "🔇 SILENT"
                    indicator = "░░░░░░░░░░░░"
                
                # Print status (overwrite line)
                runtime = time.time() - start_time
                print(f"\r{status} | {indicator} | "
                      f"RMS: L={left_rms:.4f} R={right_rms:.4f} | "
                      f"Peak: L={left_peak:.4f} R={right_peak:.4f} | "
                      f"Max: {max_level:.4f} | "
                      f"Samples: {sample_count} | "
                      f"Time: {runtime:.1f}s", end="", flush=True)
                
                # Detailed report every 100 samples
                if sample_count % 100 == 0:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
                          f"Sample #{sample_count} - Max level so far: {max_level:.4f}")
                
                time.sleep(0.01)  # Small delay
                
    except KeyboardInterrupt:
        print(f"\n\n🛑 Test stopped by user")
        print(f"Final stats: {sample_count} samples processed, max level: {max_level:.4f}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("This could indicate:")
        print("  - Device access permission issues")
        print("  - Incorrect device specification")
        print("  - Audio system not available")
        return False
    
    return True

def main():
    print("🎵 SoundDevice Audio Input Test")
    print("=" * 50)
    
    # Show device info
    try:
        list_audio_devices()
    except Exception as e:
        print(f"Error listing devices: {e}")
        return
    
    # Run the test
    try:
        success = test_audio_stream()
        if success:
            print("\n✅ Audio test completed!")
        else:
            print("\n❌ Audio test failed!")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")

if __name__ == "__main__":
    main()