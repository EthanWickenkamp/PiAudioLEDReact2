#!/bin/bash

# Start DBus for BlueZ and PulseAudio
dbus-daemon --system --nofork &
udevd &
pulseaudio --start

# Load PulseAudio modules (if available)
pactl load-module module-native-protocol-unix || true
pactl load-module module-bluetooth-policy || true
pactl load-module module-bluetooth-discover || true

# Optional: Set default sink
# pactl set-default-sink alsa_output.pci-0000_00_1f.3.analog-stereo

# Run the app
python3 /app/main.py
