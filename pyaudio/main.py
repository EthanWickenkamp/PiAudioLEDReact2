import os
import socket
import time
import threading
import numpy as np
import sounddevice as sd
from typing import Optional
import json

# Environment variables
DEVICE = os.getenv("INPUT_DEVICE", "hw:Loopback,1,0")
RATE = int(os.getenv("SAMPLE_RATE", "44100"))
FRAME = int(os.getenv("FRAME_SIZE", "1024"))
HOST = os.getenv("WLED_HOST", "192.168.50.123")
PORT = int(os.getenv("WLED_PORT", "21324"))

# Audio analysis parameters
CHANNELS = 2
DTYPE = 'float32'

# Global variables for audio processing
audio_data = np.zeros(FRAME)
data_lock = threading.Lock()
running = False

class AudioAnalyzer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.1)  # Non-blocking
        
        # Audio analysis buffers
        self.fft_size = FRAME
        self.freqs = np.fft.fftfreq(self.fft_size, 1/RATE)
        self.window = np.hanning(self.fft_size)
        
        # LED parameters (adjust based on your WLED setup)
        self.num_leds = 144  # Adjust to your LED count
        self.brightness = 128  # 0-255
        
        print(f"[AudioAnalyzer] Initialized for {self.num_leds} LEDs")
        print(f"[AudioAnalyzer] Target: {HOST}:{PORT}")
    
    def audio_callback(self, indata, frames, time, status):
        """Callback function for audio input"""
        global audio_data, data_lock
        
        if status:
            print(f"[Audio] Status: {status}")
        
        # Convert to mono by averaging channels
        mono_data = np.mean(indata, axis=1) if indata.ndim > 1 else indata
        
        with data_lock:
            audio_data = mono_data.copy()
    
    def analyze_audio(self, data):
        """Analyze audio data and extract features"""
        if len(data) == 0:
            return None
        
        # Apply window to reduce spectral leakage
        windowed = data * self.window
        
        # Compute FFT
        fft = np.fft.fft(windowed)
        magnitude = np.abs(fft[:len(fft)//2])  # Only positive frequencies
        
        # Calculate volume (RMS)
        volume = np.sqrt(np.mean(data**2))
        
        # Frequency bands for LED visualization
        # Split spectrum into bands (bass, mid, treble, etc.)
        freq_bands = self.split_frequency_bands(magnitude)
        
        return {
            'volume': volume,
            'bands': freq_bands,
            'peak_freq': self.freqs[np.argmax(magnitude)]
        }
    
    def split_frequency_bands(self, magnitude, num_bands=8):
        """Split frequency spectrum into bands"""
        band_size = len(magnitude) // num_bands
        bands = []
        
        for i in range(num_bands):
            start_idx = i * band_size
            end_idx = (i + 1) * band_size
            band_energy = np.mean(magnitude[start_idx:end_idx])
            bands.append(band_energy)
        
        return bands
    
    def create_led_data(self, analysis):
        """Create LED data based on audio analysis"""
        if analysis is None:
            # Return black/off LEDs
            return [0, 0, 0] * self.num_leds
        
        volume = analysis['volume']
        bands = analysis['bands']
        
        led_data = []
        
        # Simple visualization: map frequency bands to different sections of LED strip
        leds_per_band = self.num_leds // len(bands)
        
        for i, band_energy in enumerate(bands):
            # Scale band energy to color intensity
            intensity = min(255, int(band_energy * 1000))  # Adjust scaling as needed
            
            # Create color based on frequency band
            if i < 2:  # Bass - Red
                color = [intensity, 0, 0]
            elif i < 4:  # Mid - Green
                color = [0, intensity, 0]
            else:  # High - Blue
                color = [0, 0, intensity]
            
            # Apply volume scaling
            volume_scale = min(1.0, volume * 10)  # Adjust scaling
            color = [int(c * volume_scale) for c in color]
            
            # Add colors for this band's LEDs
            start_led = i * leds_per_band
            end_led = min(self.num_leds, (i + 1) * leds_per_band)
            
            for _ in range(start_led, end_led):
                led_data.extend(color)
        
        return led_data
    
    def send_to_wled(self, led_data):
        """Send LED data to WLED via UDP"""
        try:
            # WLED UDP format: [DRGB, channel, data...]
            # DRGB protocol: first byte is 1, second byte is timeout
            packet = bytearray([1, 1])  # DRGB protocol, 1 second timeout
            packet.extend(led_data)
            
            self.sock.sendto(packet, (HOST, PORT))
            
        except socket.error as e:
            # Don't spam errors, just log occasionally
            if time.time() % 10 < 0.1:  # Every ~10 seconds
                print(f"[WLED] Network error: {e}")
        except Exception as e:
            print(f"[WLED] Send error: {e}")
    
    def process_audio_loop(self):
        """Main audio processing loop"""
        global audio_data, data_lock, running
        
        print("[AudioAnalyzer] Starting processing loop...")
        
        while running:
            try:
                with data_lock:
                    current_data = audio_data.copy()
                
                # Analyze audio
                analysis = self.analyze_audio(current_data)
                
                # Create LED visualization
                led_data = self.create_led_data(analysis)
                
                # Send to WLED
                self.send_to_wled(led_data)
                
                # Debug output (occasionally)
                if analysis and time.time() % 5 < 0.05:  # Every ~5 seconds
                    print(f"[Audio] Volume: {analysis['volume']:.4f}, "
                          f"Peak: {analysis['peak_freq']:.0f}Hz, "
                          f"Bands: {len(analysis['bands'])}")
                
                time.sleep(0.02)  # ~50 FPS
                
            except Exception as e:
                print(f"[AudioAnalyzer] Processing error: {e}")
                time.sleep(1)
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            self.sock.close()
        except:
            pass

def wait_for_audio_device(device_name: str, max_attempts: int = 30):
    """Wait for audio device to become available"""
    print(f"[Setup] Waiting for audio device: {device_name}")
    
    for attempt in range(max_attempts):
        try:
            devices = sd.query_devices()
            
            # Try to find device by name matching
            for i, device in enumerate(devices):
                if ("loopback" in device_name.lower() and 
                    "loopback" in device['name'].lower()):
                    print(f"[Setup] Found Loopback device: {device['name']}")
                    return True
                elif device_name in device['name'] or device['name'] in device_name:
                    print(f"[Setup] Found matching device: {device['name']}")
                    return True
            
            print(f"[Setup] Attempt {attempt + 1}/{max_attempts}: Device not ready")
            time.sleep(2)
            
        except Exception as e:
            print(f"[Setup] Error checking devices: {e}")
            time.sleep(2)
    
    print(f"[Setup] Device not found after {max_attempts} attempts")
    return False

def main():
    global running
    
    print("="*60)
    print(" AUDIO PROCESSOR STARTING")
    print("="*60)
    print(f"Device: {DEVICE}")
    print(f"Sample Rate: {RATE}")
    print(f"Frame Size: {FRAME}")
    print(f"WLED Target: {HOST}:{PORT}")
    print("="*60)
    
    # Wait for audio device
    if not wait_for_audio_device(DEVICE):
        print("[ERROR] Audio device not available!")
        return 1
    
    # List available devices for debugging
    try:
        print("\n[Info] Available audio devices:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            print(f"  [{i}] {device['name']} - In:{device['max_input_channels']}")
    except Exception as e:
        print(f"[Warning] Could not list devices: {e}")
    
    # Initialize analyzer
    analyzer = AudioAnalyzer()
    
    try:
        # Test network connection
        print(f"\n[Setup] Testing connection to {HOST}:{PORT}")
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        test_sock.settimeout(5)
        test_sock.sendto(b"test", (HOST, PORT))
        test_sock.close()
        print("[Setup] Network connection OK")
        
    except Exception as e:
        print(f"[Warning] Network test failed: {e}")
    
    try:
        print(f"\n[Setup] Opening audio stream: {DEVICE}")
        
        # Start audio processing thread
        running = True
        process_thread = threading.Thread(target=analyzer.process_audio_loop)
        process_thread.daemon = True
        process_thread.start()
        
        # Start audio stream
        with sd.InputStream(
            device=DEVICE,
            channels=CHANNELS,
            samplerate=RATE,
            blocksize=FRAME,
            dtype=DTYPE,
            callback=analyzer.audio_callback
        ):
            print("[Audio] Stream started successfully!")
            print("[Audio] Processing audio... Press Ctrl+C to stop")
            
            # Keep main thread alive
            while running:
                time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n[Shutdown] Interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Audio stream error: {e}")
        return 1
    
    finally:
        print("[Shutdown] Cleaning up...")
        running = False
        analyzer.cleanup()
        print("[Shutdown] Complete")
    
    return 0

if __name__ == "__main__":
    exit(main())