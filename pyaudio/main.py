import os
import socket
import time
import sys
import numpy as np
import sounddevice as sd
from typing import Optional

# Environment variables
DEVICE = os.getenv("INPUT_DEVICE", "hw:Loopback,1,0")
RATE = int(os.getenv("SAMPLE_RATE", "44100"))
FRAME = int(os.getenv("FRAME_SIZE", "1024"))
HOST = os.getenv("WLED_HOST", "192.168.50.123")
PORT = int(os.getenv("WLED_PORT", "21324"))

def print_separator(title: str):
    """Print a clear section separator"""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def check_environment():
    """Display all environment variables"""
    print_separator("ENVIRONMENT VARIABLES")
    print(f"INPUT_DEVICE: {DEVICE}")
    print(f"SAMPLE_RATE: {RATE}")
    print(f"FRAME_SIZE: {FRAME}")
    print(f"WLED_HOST: {HOST}")
    print(f"WLED_PORT: {PORT}")

def check_sounddevice_version():
    """Check sounddevice library info"""
    print_separator("SOUNDDEVICE INFO")
    print(f"sounddevice version: {sd.__version__}")
    try:
        print(f"PortAudio version: {sd.get_portaudio_version()}")
    except Exception as e:
        print(f"Error getting PortAudio version: {e}")

def list_all_devices():
    """List all available audio devices with detailed info"""
    print_separator("ALL AUDIO DEVICES")
    try:
        devices = sd.query_devices()
        print(f"Total devices found: {len(devices)}")
        print("\nDevice List:")
        print("-" * 80)
        for i, device in enumerate(devices):
            print(f"[{i:2d}] {device['name']:<30} | "
                  f"In:{device['max_input_channels']:2d} | "
                  f"Out:{device['max_output_channels']:2d} | "
                  f"Rate:{device['default_samplerate']:8.0f} | "
                  f"API: {sd.query_hostapis(device['hostapi'])['name']}")
        
        print("\nDefault devices:")
        try:
            default_input = sd.query_devices(kind='input')
            default_output = sd.query_devices(kind='output')
            print(f"Default input:  [{default_input['name']}]")
            print(f"Default output: [{default_output['name']}]")
        except Exception as e:
            print(f"Error getting default devices: {e}")
            
    except Exception as e:
        print(f"Error listing devices: {e}")
        return False
    return True

def search_for_device(search_term: str):
    """Search for devices containing specific terms"""
    print_separator(f"SEARCHING FOR DEVICES CONTAINING '{search_term}'")
    try:
        devices = sd.query_devices()
        matches = []
        for i, device in enumerate(devices):
            if search_term.lower() in device['name'].lower():
                matches.append((i, device))
                print(f"Found: [{i}] {device['name']} - "
                      f"Input channels: {device['max_input_channels']}")
        
        if not matches:
            print(f"No devices found containing '{search_term}'")
        return matches
    except Exception as e:
        print(f"Error searching devices: {e}")
        return []

def test_device_by_name(device_name: str):
    """Test if a specific device can be opened"""
    print_separator(f"TESTING DEVICE: {device_name}")
    try:
        # First try to find device by name
        devices = sd.query_devices()
        device_id = None
        
        for i, device in enumerate(devices):
            if device_name in device['name'] or device['name'] in device_name:
                device_id = i
                print(f"Found matching device: [{i}] {device['name']}")
                break
        
        if device_id is None:
            # Try to use the name directly
            print(f"No exact match found, trying device name directly: {device_name}")
            device_id = device_name
        
        # Test opening the device
        print(f"Testing device: {device_id}")
        with sd.InputStream(device=device_id, channels=2, samplerate=RATE, 
                           blocksize=FRAME, dtype='float32'):
            print("✓ Device can be opened successfully!")
            return True
            
    except sd.PortAudioError as e:
        print(f"✗ PortAudio Error: {e}")
        return False
    except Exception as e:
        print(f"✗ General Error: {e}")
        return False

def test_network_connection():
    """Test network connectivity to WLED host"""
    print_separator("NETWORK CONNECTIVITY TEST")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        
        # Try to connect
        test_data = b"test"
        sock.sendto(test_data, (HOST, PORT))
        print(f"✓ Successfully sent test data to {HOST}:{PORT}")
        sock.close()
        return True
    except socket.timeout:
        print(f"✗ Timeout connecting to {HOST}:{PORT}")
        return False
    except socket.error as e:
        print(f"✗ Socket error connecting to {HOST}:{PORT}: {e}")
        return False
    except Exception as e:
        print(f"✗ Error connecting to {HOST}:{PORT}: {e}")
        return False

def test_audio_stream():
    """Test actual audio streaming"""
    print_separator("AUDIO STREAM TEST")
    try:
        print(f"Attempting to open audio stream with device: {DEVICE}")
        
        def callback(indata, frames, time, status):
            if status:
                print(f"Stream status: {status}")
            # Just print level to show we're getting data
            level = np.sqrt(np.mean(indata**2))
            if level > 0.001:  # Only print if there's significant audio
                print(f"Audio level: {level:.4f}")
        
        with sd.InputStream(device=DEVICE, channels=2, samplerate=RATE,
                           blocksize=FRAME, dtype='float32', callback=callback):
            print("✓ Audio stream opened successfully!")
            print("Listening for 5 seconds (play some audio to see levels)...")
            time.sleep(5)
            print("Stream test complete")
            return True
            
    except Exception as e:
        print(f"✗ Audio stream error: {e}")
        return False

def wait_for_device(device_name: str, max_attempts: int = 30):
    """Wait for a specific device to become available"""
    print_separator(f"WAITING FOR DEVICE: {device_name}")
    
    for attempt in range(max_attempts):
        try:
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                if device_name.lower() in device['name'].lower():
                    print(f"✓ Device found after {attempt + 1} attempts: {device['name']}")
                    return True
            
            print(f"Attempt {attempt + 1}/{max_attempts}: Device not found, waiting...")
            time.sleep(2)
            
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error checking devices: {e}")
            time.sleep(2)
    
    print(f"✗ Device not found after {max_attempts} attempts")
    return False

def main():
    """Main debugging function"""
    print_separator("AUDIO DEVICE DEBUGGING STARTED")
    
    # Basic environment check
    check_environment()
    
    # Check sounddevice library
    check_sounddevice_version()
    
    # List all devices
    if not list_all_devices():
        print("Cannot proceed - no audio devices accessible")
        sys.exit(1)
    
    # Search for loopback devices
    loopback_devices = search_for_device("loopback")
    
    # Search for any ALSA devices
    alsa_devices = search_for_device("hw:")
    
    # Test the specific device we want to use
    device_works = test_device_by_name(DEVICE)
    
    # If the device doesn't work, wait for it
    if not device_works:
        print("Target device not working, waiting for it to become available...")
        if wait_for_device("loopback"):
            device_works = test_device_by_name(DEVICE)
    
    # Test network connection
    network_works = test_network_connection()
    
    # Final summary
    print_separator("DEBUGGING SUMMARY")
    print(f"Target device ({DEVICE}): {'✓ WORKING' if device_works else '✗ FAILED'}")
    print(f"Network connection: {'✓ WORKING' if network_works else '✗ FAILED'}")
    print(f"Loopback devices found: {len(loopback_devices)}")
    
    if device_works and network_works:
        print("\n🎉 All systems check passed! Attempting audio stream test...")
        test_audio_stream()
    else:
        print("\n❌ System checks failed. Check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDebugging interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)