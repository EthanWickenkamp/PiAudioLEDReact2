#!/usr/bin/env bash
set -euo pipefail
export DBUS_SYSTEM_BUS_ADDRESS=${DBUS_SYSTEM_BUS_ADDRESS:-unix:path=/run/dbus/system_bus_socket}

BT_MAC=${BT_MAC:-}

bluetoothctl --timeout 5 power on || true
bluetoothctl agent NoInputNoOutput || true
bluetoothctl default-agent || true

if [[ -n "$BT_MAC" ]]; then
  bluetoothctl trust "$BT_MAC" || true
  bluetoothctl connect "$BT_MAC" || true
else
  echo "Set BT_MAC=AA:BB:CC:DD:EE:FF to auto-trust/connect."
fi

# Keep container alive
tail -f /dev/null
