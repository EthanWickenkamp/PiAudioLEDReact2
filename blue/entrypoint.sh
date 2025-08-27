#!/usr/bin/env bash
set -euo pipefail

# Talk to the host's system bus
export DBUS_SYSTEM_BUS_ADDRESS=${DBUS_SYSTEM_BUS_ADDRESS:-unix:path=/run/dbus/system_bus_socket}

# Make sure BT isn't soft-blocked
rfkill unblock bluetooth || true

# Power adapter on (short-lived call is fine)
bluetoothctl power on || true

# Start a long-lived agent that auto-accepts pairing (no PIN)
# (bluez-tools provides bt-agent)
bt-agent -c NoInputNoOutput &
AGENT_PID=$!
echo "[btctl] bt-agent started (pid=$AGENT_PID)"

# Make the Pi discoverable & pairable
bluetoothctl discoverable on || true
bluetoothctl pairable on || true
bluetoothctl connectable on || true

echo "[btctl] Ready for pairing. Open Bluetooth on your phone and select the Pi."

# (Optional) auto-trust any device that connects
bluetoothctl --monitor | while read -r line; do
  # e.g., "Device AA:BB:CC:DD:EE:FF Connected: yes"
  if [[ "$line" =~ ^Device\ ([A-F0-9:]{17})\ Connected:\ yes$ ]]; then
    mac="${BASH_REMATCH[1]}"
    echo "[btctl] Auto-trusting $mac"
    bluetoothctl trust "$mac" || true
  fi
done

