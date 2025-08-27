#!/usr/bin/env bash
set -euo pipefail
export DBUS_SYSTEM_BUS_ADDRESS=${DBUS_SYSTEM_BUS_ADDRESS:-unix:path=/run/dbus/system_bus_socket}

echo "[btctl] Powering on + enabling agent..."
bluetoothctl power on
bluetoothctl agent NoInputNoOutput
bluetoothctl default-agent

echo "[btctl] Making device discoverable + pairable..."
bluetoothctl discoverable on
bluetoothctl pairable on

echo "[btctl] Ready for pairing. Open Bluetooth on your iPhone and connect to 'raspberrypi' (or your Pi’s BT name)."

# Optionally, loop + auto-trust new devices
while read -r line; do
  echo "[bluetoothctl] $line"
  if [[ "$line" =~ ^\[NEW\]\ Device ]]; then
    mac=$(echo "$line" | awk '{print $3}')
    echo "[btctl] Auto-trusting new device: $mac"
    bluetoothctl trust "$mac"
  fi
done < <(bluetoothctl monitor)
