#!/bin/ash
set -e

echo "▶ Loading snd-aloop (index=${ALOOP_INDEX}, id=${ALOOP_ID}, subs=${ALOOP_SUBS})"
/sbin/modprobe snd-aloop index=${ALOOP_INDEX} id=${ALOOP_ID} pcm_substreams=${ALOOP_SUBS} || true

# Wait longer and be more patient
echo "▶ Waiting for ALSA Loopback card to appear…"
for i in $(seq 1 240); do  # Increased from 120 to 240 (1 minute)
  [ -e /proc/asound/${ALOOP_ID} ] && break
  sleep 0.25
done

# Also wait for the specific subdevice
echo "▶ Waiting for subdevice to be ready…"
sleep 2  # Give it a moment after detection

if [ ! -e /proc/asound/${ALOOP_ID} ]; then
  echo "✖ Loopback card '${ALOOP_ID}' not found."
  exit 3
fi

echo "▶ ALSA devices:"
aplay -l || true
arecord -l || true

echo "▶ Starting alsaloop: ${IN_PCM} → ${OUT_PCM} @ ${RATE}Hz"
exec alsaloop -C "${IN_PCM}" -P "${OUT_PCM}" -r "${RATE}" -v