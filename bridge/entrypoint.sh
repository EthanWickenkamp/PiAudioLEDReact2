#!/bin/ash
set -eu

# ---- minimal config (env-overridable) ----
ALOOP_INDEX="${ALOOP_INDEX:-9}"
ALOOP_ID="${ALOOP_ID:-Loopback}"
ALOOP_SUBS="${ALOOP_SUBS:-2}"

# Producer writes to:           hw:${ALOOP_ID},0,0
# We read (tap) from capture:   hw:${ALOOP_ID},1,0   (wrapped by dsnoop -> loop_tap)
IN_HW="${IN_HW:-hw:${ALOOP_ID},1,0}"

# Outputs
OUT_PCM="${OUT_PCM:-plughw:BossDAC,0}"   # real DAC (change as needed)
OUT_PCM2="${OUT_PCM2:-}"                 # optional mirror (e.g. hw:${ALOOP_ID},0,1)

RATE="${RATE:-48000}"   # safer @ 48k for BT chains
PERIOD="${PERIOD:-256}"
FRAGS="${FRAGS:-3}"

log() { echo "[$(date +'%H:%M:%S')] $*"; }

# ---- 1) Load loopback on host kernel ----
log "modprobe snd-aloop index=${ALOOP_INDEX} id=${ALOOP_ID} substreams=${ALOOP_SUBS}"
/sbin/modprobe snd-aloop index="${ALOOP_INDEX}" id="${ALOOP_ID}" pcm_substreams="${ALOOP_SUBS}" || true

# ---- 2) Wait for the card to appear ----
log "waiting for /proc/asound/${ALOOP_ID} …"
i=0
while [ ! -e "/proc/asound/${ALOOP_ID}" ] && [ $i -lt 80 ]; do
  i=$((i+1)); sleep 0.25
done
[ -e "/proc/asound/${ALOOP_ID}" ] || { echo "loopback '${ALOOP_ID}' not found"; exit 3; }
sleep 1

# ---- 3) Create minimal ALSA config INSIDE the container ----
# Defines a dsnoop tap called 'loop_tap' over the capture end we want to share.
cat >/etc/asound.conf <<EOF
pcm.loop_tap {
  type dsnoop
  ipc_key 12345
  slave {
    pcm "${IN_HW}"
    channels 2
    rate ${RATE}
    period_size ${PERIOD}
    buffer_size $((PERIOD*FRAGS))
  }
}
EOF

# (Optional): quick visibility
aplay -l || true
arecord -l || true

# ---- 4) Start the fan-out(s) from the shared tap ----
pids=""

log "alsaloop: loop_tap -> ${OUT_PCM} @ ${RATE}"
alsaloop -C loop_tap -P "${OUT_PCM}" -r "${RATE}" -p "${PERIOD}" -n "${FRAGS}" -t 10000 -S 75 -v &
pids="$pids $!"

if [ -n "${OUT_PCM2}" ]; then
  log "alsaloop (mirror): loop_tap -> ${OUT_PCM2} @ ${RATE}"
  alsaloop -C loop_tap -P "${OUT_PCM2}" -r "${RATE}" -p "${PERIOD}" -n "${FRAGS}" -t 10000 -S 75 -v &
  pids="$pids $!"
fi

# ---- 5) Wait / clean shutdown ----
trap 'log "stopping"; [ -n "$pids" ] && kill $pids 2>/dev/null || true; wait || true; exit 0' TERM INT
wait -n
