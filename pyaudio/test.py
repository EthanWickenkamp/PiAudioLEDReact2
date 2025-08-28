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
INPUT_DEVICE = os.getenv('INPUT_DEVICE', 'hw:Loopback,1,1')
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
    
    print(f"Target device: {INPUT_DEVICE}")
    
    # Parse the ALSA device specification
    # Expected formats: "hw:Loopback,1,0", "hw:9,1,0", "hw:9,1"
    target_card_name = None
    target_card_num = None
    target_device_num = None
    
    if "hw:" in INPUT_DEVICE:
        hw_spec = INPUT_DEVICE.replace("hw:", "").split(",")
        
        # First part is card (name or number)
        if hw_spec[0].isdigit():
            target_card_num = int(hw_spec[0])
        else:
            target_card_name = hw_spec[0]
        
        # Second part is device number
        if len(hw_spec) >= 2 and hw_spec[1].isdigit():
            target_device_num = int(hw_spec[1])
    
    print(f"Parsed: card_name='{target_card_name}', card_num={target_card_num}, device_num={target_device_num}")
    
    # Search through available devices
    for i, device in enumerate(devices):
        device_name = device['name']
        print(f"Device {i}: {device_name}")
        
        # Skip devices without input capability
        if device['max_input_channels'] == 0:
            print(f"  -> Skipping (no input channels)")
            continue
        
        # Method 1: Look for exact hw specification in device name
        if target_card_num is not None and target_device_num is not None:
            expected_hw = f"hw:{target_card_num},{target_device_num}"
            if expected_hw in device_name:
                print(f"  -> MATCH: Found exact hw spec '{expected_hw}'")
                return i
        
        # Method 2: Look for card name + device number pattern
        if target_card_name and target_device_num is not None:
            # Look for patterns like "Loopback: PCM (hw:9,1)"
            if (target_card_name in device_name and 
                f",{target_device_num}" in device_name):
                print(f"  -> MATCH: Found card name '{target_card_name}' with device {target_device_num}")
                return i
        
        # Method 3: Fallback - just card name match (use first available)
        if target_card_name and target_card_name in device_name:
            print(f"  -> Partial match: Found card name '{target_card_name}' (will continue looking for exact match)")
            # Don't return yet, keep looking for exact match
    
    # If no exact match found, try partial matches as fallback
    print("No exact match found, trying fallback matches...")
    for i, device in enumerate(devices):
        device_name = device['name']
        if (device['max_input_channels'] > 0 and 
            target_card_name and target_card_name in device_name):
            print(f"FALLBACK: Using {device_name} (index {i})")
            return i
    
    print(f"ERROR: No matching device found for '{INPUT_DEVICE}'")
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