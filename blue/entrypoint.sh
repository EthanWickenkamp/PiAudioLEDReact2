#!/bin/bash
set -e

echo "Starting minimal Bluetooth pairing setup..."

# Use host D-Bus (don't start our own)
export DBUS_SYSTEM_BUS_ADDRESS="unix:path=/run/dbus/system_bus_socket"

# Start Bluetooth daemon
bluetoothd &
sleep 3

# Power on and make discoverable
bluetoothctl power on
bluetoothctl discoverable on
bluetoothctl pairable on

# Start auto-pairing agent
bt-agent -c NoInputNoOutput &

echo "Ready for pairing! Look for this device in iPhone Bluetooth settings."
echo "Device should appear as: $(bluetoothctl show | grep Name | cut -d: -f2)"

# Keep container running and show connection events
echo "Monitoring Bluetooth events..."
while true; do
    echo "Starting monitor loop..."
    
    # Monitor with timeout and restart logic
    timeout 300 bluetoothctl --monitor 2>/dev/null | while read -r line; do
        echo "BT Event: $line"
        
        # Auto-trust when devices connect
        if [[ "$line" =~ Device\ ([A-Fa-f0-9:]{17})\ Connected:\ yes ]]; then
            mac="${BASH_REMATCH[1]}"
            echo "Auto-trusting device: $mac"
            bluetoothctl trust "$mac" || true
        fi
    done || true
    
    echo "Monitor session ended, restarting in 5 seconds..."
    sleep 5
done