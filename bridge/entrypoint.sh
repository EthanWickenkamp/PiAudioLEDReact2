#!/bin/ash
set -e

echo "▶ Loading snd-aloop (index=${ALOOP_INDEX}, id=${ALOOP_ID}, subs=${ALOOP_SUBS})"
# /sbin/modprobe exists on Alpine; requires privileged container + /lib/modules mount
/sbin/modprobe snd-aloop index=${ALOOP_INDEX} id=${ALOOP_ID} pcm_substreams=${ALOOP_SUBS} || true

echo "▶ Waiting for ALSA Loopback card to appear…"
i=0
while [ ! -e /proc/asound/${ALOOP_ID} ] && [ $i -lt 120 ]; do
  i=$((i+1))
  sleep 0.25
done

if [ ! -e /proc/asound/${ALOOP_ID} ]; then
  echo "✖ ALSA Loopback card '${ALOOP_ID}' not found after wait. Exiting."
  exit 1
fi

echo "▶ ALSA devices (aplay -l / arecord -l):"
aplay -l || true
arecord -l || true

echo "▶ Starting alsaloop: ${IN_PCM} → ${OUT_PCM} @ ${RATE}Hz (p=${PERIOD}, n=${FRAGS})"
exec alsaloop -C "${IN_PCM}" -P "${OUT_PCM}" -r "${RATE}" -p "${PERIOD}" -n "${FRAGS}"
