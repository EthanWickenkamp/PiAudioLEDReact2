#!/bin/ash
set -e

echo "▶ Loading snd-aloop (index=${ALOOP_INDEX}, id=${ALOOP_ID}, subs=${ALOOP_SUBS})"
/sbin/modprobe snd-aloop index=${ALOOP_INDEX} id=${ALOOP_ID} pcm_substreams=${ALOOP_SUBS} || true

echo "▶ Waiting for ALSA Loopback card to appear…"
for i in $(seq 1 120); do
  [ -e /proc/asound/${ALOOP_ID} ] && break
  sleep 0.25
done

if [ ! -e /proc/asound/${ALOOP_ID} ]; then
  echo "✖ Loopback card '${ALOOP_ID}' not found. Is the module built or available on the host?"
  exit 3
fi

echo "▶ ALSA devices (aplay -l / arecord -l):"
aplay -l || true
arecord -l || true

echo "▶ Starting alsaloop: ${IN_PCM} → ${OUT_PCM} @ ${RATE}Hz"
# Minimal, no invalid -p/-n flags:
exec alsaloop -C "${IN_PCM}" -P "${OUT_PCM}" -r "${RATE}"

