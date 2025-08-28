import socket, struct, time, math
import os

# ---------- Configuration ----------
WLED_HOST    = os.getenv('WLED_HOST', '192.168.50.165')  # Change to your WLED IP
WLED_SR_PORT = int(os.getenv('WLED_SR_PORT', '11988'))
MULTICAST_IP = '239.0.0.1'  # WLED multicast address

# WLED Audio Sync v2 packet format
PKT_FMT = "<6sffBB16Bff"
HEADER = b"00002\x00"

def create_test_packet(test_type="sine", intensity=100):
    """Create different types of test packets"""
    
    if test_type == "sine":
        # Simulate a sine wave audio signal
        t = time.time()
        freq = 440  # A4 note
        sample_raw = max(1.0, intensity * (0.5 + 0.5 * math.sin(2 * math.pi * freq * t / 100)))
        sample_smth = sample_raw * 0.8
        sample_peak = 1 if sample_raw > intensity * 0.7 else 0
        
        # Create FFT bands with some activity
        fft_bands = []
        for i in range(16):
            if 2 <= i <= 6:  # Simulate activity in mid frequencies
                band_val = int(max(1, intensity * 0.3 * (0.8 + 0.2 * math.sin(t + i))))
            else:
                band_val = max(1, int(intensity * 0.1))
            fft_bands.append(min(255, band_val))
        
        fft_magnitude = sample_raw * 10
        fft_major_peak = 440.0
    
    elif test_type == "bass":
        # Simulate bass-heavy music
        t = time.time()
        sample_raw = max(1.0, intensity * (0.6 + 0.4 * math.sin(2 * math.pi * t / 4)))
        sample_smth = sample_raw * 0.9
        sample_peak = 1 if (int(t * 2) % 4) == 0 else 0  # Peak every 2 seconds
        
        # Heavy bass in first few bands
        fft_bands = []
        for i in range(16):
            if i <= 3:  # Bass frequencies
                band_val = int(max(10, intensity * (0.8 + 0.2 * math.sin(t * 3 + i))))
            elif i <= 8:  # Mid frequencies
                band_val = int(max(5, intensity * 0.4))
            else:  # High frequencies
                band_val = max(1, int(intensity * 0.2))
            fft_bands.append(min(255, band_val))
        
        fft_magnitude = sample_raw * 15
        fft_major_peak = 80.0
    
    elif test_type == "quiet":
        # Very minimal activity to test threshold
        sample_raw = 2.0
        sample_smth = 1.5
        sample_peak = 0
        fft_bands = [1] * 16  # Minimal activity
        fft_magnitude = 1.0
        fft_major_peak = 100.0
    
    elif test_type == "silence":
        # Complete silence test
        sample_raw = 0.0
        sample_smth = 0.0
        sample_peak = 0
        fft_bands = [0] * 16
        fft_magnitude = 0.0
        fft_major_peak = 0.0
    
    else:  # "full" - full spectrum activity
        t = time.time()
        sample_raw = max(1.0, intensity * (0.7 + 0.3 * math.sin(2 * math.pi * t / 3)))
        sample_smth = sample_raw * 0.85
        sample_peak = 1 if (int(t * 4) % 3) == 0 else 0
        
        # Activity across all bands
        fft_bands = []
        for i in range(16):
            phase = t + i * 0.5
            band_val = int(max(5, intensity * 0.6 * (0.7 + 0.3 * math.sin(phase))))
            fft_bands.append(min(255, band_val))
        
        fft_magnitude = sample_raw * 12
        fft_major_peak = 1000.0 + 500 * math.sin(t)
    
    # Pack the packet
    packet = struct.pack(PKT_FMT,
                        HEADER,           # 6 bytes: "00002\0"
                        sample_raw,       # 4 bytes: float sampleRaw
                        sample_smth,      # 4 bytes: float sampleSmth
                        sample_peak,      # 1 byte:  uint8_t samplePeak
                        0,                # 1 byte:  uint8_t reserved
                        *fft_bands,       # 16 bytes: uint8_t fftResult[16]
                        fft_magnitude,    # 4 bytes: float FFT_Magnitude
                        fft_major_peak)   # 4 bytes: float FFT_MajorPeak
    
    return packet, sample_raw, sample_peak, fft_bands

def test_wled_connection():
    """Test different packet types and connection methods"""
    
    print("=== WLED Audio Sync Test Packet Sender ===")
    print(f"Target IP: {WLED_HOST}:{WLED_SR_PORT}")
    print(f"Multicast: {MULTICAST_IP}:{WLED_SR_PORT}")
    print(f"Packet size: {struct.calcsize(PKT_FMT)} bytes")
    print()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        tests = [
            ("silence", 0, "Test complete silence"),
            ("quiet", 50, "Test minimal activity"),
            ("sine", 100, "Test sine wave simulation"),
            ("bass", 150, "Test bass-heavy pattern"),
            ("full", 120, "Test full spectrum activity")
        ]
        
        for test_name, intensity, description in tests:
            print(f"\n--- {description} ---")
            print(f"Test: {test_name}, Intensity: {intensity}")
            
            # Test both direct IP and multicast
            targets = [
                (WLED_HOST, "Direct IP"),
                (MULTICAST_IP, "Multicast")
            ]
            
            for target_ip, method in targets:
                print(f"\nTesting {method} ({target_ip}):")
                
                for i in range(10):  # Send 10 packets per test
                    packet, sample_raw, sample_peak, fft_bands = create_test_packet(test_name, intensity)
                    
                    try:
                        sock.sendto(packet, (target_ip, WLED_SR_PORT))
                        
                        # Show packet details for first packet of each test
                        if i == 0:
                            print(f"  Sample Raw: {sample_raw:.1f}, Peak: {sample_peak}")
                            print(f"  FFT Bands: [{fft_bands[0]}, {fft_bands[1]}, {fft_bands[2]}, ..., {fft_bands[-1]}]")
                        
                        if i == 0:
                            print(f"  Sending packets", end="", flush=True)
                        elif i % 2 == 0:
                            print(".", end="", flush=True)
                    
                    except Exception as e:
                        print(f"  Error sending to {target_ip}: {e}")
                        break
                    
                    time.sleep(0.1)  # 10Hz packet rate
                
                print(" Done!")
            
            # Wait between tests
            print(f"\nWaiting 3 seconds before next test...")
            time.sleep(3)
        
        print(f"\n=== Continuous Test Mode ===")
        print("Sending continuous 'bass' pattern packets...")
        print("Check your WLED device now - audio reactive effects should be active!")
        print("Press Ctrl+C to stop")
        
        packet_count = 0
        start_time = time.time()
        
        while True:
            # Alternate between direct and multicast every 50 packets
            target_ip = WLED_HOST if (packet_count // 50) % 2 == 0 else MULTICAST_IP
            
            packet, sample_raw, sample_peak, fft_bands = create_test_packet("bass", 120)
            sock.sendto(packet, (target_ip, WLED_SR_PORT))
            
            packet_count += 1
            
            # Log every 50 packets
            if packet_count % 50 == 0:
                elapsed = time.time() - start_time
                rate = packet_count / elapsed
                target_type = "Direct" if target_ip == WLED_HOST else "Multicast"
                print(f"Packets: {packet_count:4d} | Rate: {rate:.1f}/s | Target: {target_type} | Raw: {sample_raw:.1f}")
            
            time.sleep(0.05)  # 20Hz packet rate
            
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        rate = packet_count / elapsed if elapsed > 0 else 0
        print(f"\n\nTest completed!")
        print(f"Total packets sent: {packet_count}")
        print(f"Average rate: {rate:.1f} packets/second")
        print(f"Duration: {elapsed:.1f} seconds")
    
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        sock.close()

if __name__ == "__main__":
    print("WLED Audio Sync Test Tool")
    print("=" * 40)
    print("Make sure your WLED device is:")
    print("1. Connected to the network")
    print("2. Audio Reactive usermod is enabled")
    print("3. Sync -> Audio Sync is set to 'Receive'")
    print("4. You have selected an audio-reactive effect")
    print("5. Device has been rebooted after changing sync settings")
    print()
    print("Starting tests automatically in 3 seconds...")
    time.sleep(3)
    
    test_wled_connection()