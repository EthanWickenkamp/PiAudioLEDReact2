
#!/bin/bash
set -e

echo "Starting minimal Bluetooth pairing setup..."

# Start D-Bus
mkdir -p /var/run/dbus
dbus-daemon --system --fork

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
bluetoothctl --monitor
