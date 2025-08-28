#!/bin/ash
set -euo pipefail

log() { echo "[$(date +%H:%M:%S)] $*"; }

ALOOP_INDEX="${ALOOP_INDEX:-9}"
ALOOP_ID="${ALOOP_ID:-Loopback}"
ALOOP_SUBS="${ALOOP_SUBS:-2}"

IN_PCM="${IN_PCM:-hw:Loopback,1,0}"           # capture (comes from 0,0 writer)
OUT_PCM="${OUT_PCM:-plughw:BossDAC,0}"        # DAC
OUT_PCM2="${OUT_PCM2:-}"                      # optional mirror -> MUST be playback, e.g. hw:Loopback,0,1

RATE="${RATE:-44100}"
PERIOD="${PERIOD:-256}"
FRAGS="${FRAGS:-3}"

log "▶ Loading snd-aloop (index=${ALOOP_INDEX}, id=${ALOOP_ID}, subs=${ALOOP_SUBS})"
/sbin/modprobe snd-aloop index="${ALOOP_INDEX}" id="${ALOOP_ID}" pcm_substreams="${ALOOP_SUBS}" || true

log "▶ Waiting for ALSA Loopback card to appear…"
for i in $(seq 1 240); do
  [ -e "/proc/asound/${ALOOP_ID}" ] && break
  sleep 0.25
done
[ -e "/proc/asound/${ALOOP_ID}" ] || { echo "✖ Loopback card '${ALOOP_ID}' not found."; exit 3; }

log "▶ Waiting for subdevice to be ready…"
sleep 2

log "▶ ALSA devices:"
aplay -l || true
arecord -l || true

# Handle clean shutdown
pids=""
cleanup() {
  log "▶ Stopping alsaloop(s)…"
  [ -n "$pids" ] && kill $pids 2>/dev/null || true
  wait || true
}
trap cleanup TERM INT

log "▶ Starting alsaloop: ${IN_PCM} → ${OUT_PCM} @ ${RATE}Hz"
alsaloop -C "${IN_PCM}" -P "${OUT_PCM}" -r "${RATE}" -p "${PERIOD}" -n "${FRAGS}" -t 10000 -S 75 -v &
pids="$pids $!"

if [ -n "${OUT_PCM2}" ]; then
  log "▶ Starting mirror loop: ${IN_PCM} → ${OUT_PCM2} @ ${RATE}Hz"
  alsaloop -C "${IN_PCM}" -P "${OUT_PCM2}" -r "${RATE}" -t 10000 -S 75 -v &
  pids="$pids $!"
fi

wait -n
