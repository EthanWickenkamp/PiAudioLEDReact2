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

# Ensure host bluetoothd is not running (avoid two owners of org.bluez)
if busctl --system get-name-owner org.bluez >/dev/null 2>&1; then
  die "Host already has org.bluez owner. Stop/disable host bluetoothd or run without starting bluetoothd here."
fi

# Print BlueZ daemon version or unknown if fails
echo "bluez: $(bluetoothd -v 2>/dev/null || echo unknown)"

# ensure radio kill switches is not blocking bluetooth
rfkill unblock bluetooth || true

# Start Bluetooth daemon
bluetoothd -n &
BTD_PID=$!
log "bluetoothd PID: $BTD_PID"
sleep 3

# Wait for org.bluez
# for i in {1..40}; do
#   if busctl --system get-name-owner org.bluez >/dev/null 2>&1; then break; fi
#   sleep 2
# done || true
# busctl --system get-name-owner org.bluez >/dev/null 2>&1 || die "org.bluez did not appear"

# Start auto-connect agent and make pairable/discoverable
bt-agent -c NoInputNoOutput &   
bluetoothctl power on
bluetoothctl pairable on
bluetoothctl discoverable on
AGENT_PID=$!
log "bt-agent PID: $AGENT_PID"

# Start BlueALSA daemon for A2DP sink, connects BlueZ to ALSA
bluealsa -p "${BLUEALSA_PROFILES}" &
BALSA_PID=$!
log "bluealsa PID: $BALSA_PID"

# Wait for org.bluealsa
# for i in {1..40}; do
#   if busctl --system get-name-owner org.bluealsa >/dev/null 2>&1; then break; fi
#   sleep 2
# done || true
# busctl --system get-name-owner org.bluealsa >/dev/null 2>&1 || die "org.bluealsa did not appear"

echo "Ready for pairing! Look for this device in iPhone Bluetooth settings."
echo "Device should appear as: $(bluetoothctl show | grep Name | cut -d: -f2)"

# Container main process:
{
  log "Bluetooth event monitor running…"
  # -L to line-buffer so logs appear immediately
  stdbuf -oL -eL bluetoothctl --monitor 2>/dev/null | \
  while IFS= read -r line; do
    # Pairing events:
    if [[ "$line" =~ Pairing\ successful ]]; then
      echo "🔔 Pairing successful."
    elif [[ "$line" =~ Device\ ([A-Fa-f0-9:]{17}).*Paired:\ yes ]]; then
      mac="${BASH_REMATCH[1]}"
      echo "🔔 Device paired: $mac"
    fi

    # (Optional) connection announce — uncomment if you want them:
    if [[ "$line" =~ Device\ ([A-Fa-f0-9:]{17}).*Connected:\ yes ]]; then
      echo "🔊 Connected: ${BASH_REMATCH[1]}"
    elif [[ "$line" =~ Device\ ([A-Fa-f0-9:]{17}).*Connected:\ no ]]; then
      echo "🔇 Disconnected: ${BASH_REMATCH[1]}"
    fi
  done
} &

# 4) A2DP → ALSA bridge (PID 1). Keeps container running; if it dies, container exits & restarts.
log "Launching bluealsa-aplay → ${ALSA_OUT}"
exec bluealsa-aplay --profile-a2dp --pcm="${ALSA_OUT}" --single-audio -v



# # 5) Bridge to your ALSA output
# ALSA_OUT=${ALSA_OUT:-plughw:0,0}   # set to your DAC (check with: aplay -l / -L)
# bluealsa-aplay --profile-a2dp --pcm="$ALSA_OUT" --single-audio -v &


# # Keep container running and show connection events
# echo "Monitoring Bluetooth events..."
# while true; do
#     echo "Starting monitor loop..."
    
#     # Monitor with timeout and restart logic
#     timeout 300 bluetoothctl --monitor 2>/dev/null | while read -r line; do
#         echo "BT Event: $line"
        
#         # Auto-trust when devices connect
#         if [[ "$line" =~ Device\ ([A-Fa-f0-9:]{17})\ Connected:\ yes ]]; then
#             mac="${BASH_REMATCH[1]}"
#             echo "Auto-trusting device: $mac"
#             bluetoothctl trust "$mac" || true
#         fi
#     done || true
    
#     echo "Monitor session ended, restarting in 5 seconds..."
#     sleep 5
# done