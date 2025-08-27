#!/bin/bash
set -e

# Helper function die() print X and error message, then exit with status 1
die(){ echo "✖ $*" >&2; exit 1; }
# Helper function log() to print checkmark and message
log(){ echo "▶ $*"; }

echo "Starting Bluetooth pairing setup..."

# Use host D-Bus (don't start our own)
# export DBUS_SYSTEM_BUS_ADDRESS="unix:path=/run/dbus/system_bus_socket"

# Test if -S for socket exists, otherwise use die() with error message
[[ -S /run/dbus/system_bus_socket ]] || die "Host D-Bus socket missing"
echo "Using host D-Bus at /run/dbus/system_bus_socket"

# Print BlueZ daemon version or unknown if fails
echo "bluez: $(bluetoothd -v 2>/dev/null || echo unknown)"

# ensure radio kill switches is not blocking bluetooth
rfkill unblock bluetooth

# Start Bluetooth daemon
bluetoothd &
echo "Started bluetoothd with PID $!"
sleep 3

# Power on and make discoverable, done in main.conf now
# bluetoothctl power on
# bluetoothctl discoverable on
# bluetoothctl pairable on

# Start auto-pairing agent
bluetoothctl <<'EOF'
agent NoInputNoOutput
default-agent
EOF

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