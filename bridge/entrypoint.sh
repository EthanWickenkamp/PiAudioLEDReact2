#!/bin/ash
set -eu
log(){ echo "▶ $*"; }

# ---- minimal config (env-overridable) ----
ALOOP_INDEX="${ALOOP_INDEX}"
ALOOP_ID="${ALOOP_ID}"
ALOOP_SUBS="${ALOOP_SUBS}"

IN_PCM="${IN_PCM}"   # capture from BT sink tap
# Outputs
DAC_PCM="${DAC_PCM}"   # real DAC (change as needed)
OUT_PCM="${OUT_PCM}"   # optional mirror (e.g. hw:${ALOOP_ID},0,1)

RATE="${RATE:-48000}"   # safer @ 48k for BT chains
PERIOD="${PERIOD:-256}"
FRAGS="${FRAGS:-3}"


# ---- 1) Load loopback on host kernel ----
log "modprobe snd-aloop index=${ALOOP_INDEX} id=${ALOOP_ID} pcm_substreams=${ALOOP_SUBS}"
/sbin/modprobe snd-aloop index="${ALOOP_INDEX}" id="${ALOOP_ID}" pcm_substreams="${ALOOP_SUBS}" || true


# ---- 2) Wait for the card to appear ----
log "waiting for /proc/asound/${ALOOP_ID} …"
i=0
while [ ! -e "/proc/asound/${ALOOP_ID}" ] && [ $i -lt 80 ]; do
  i=$((i+1)); sleep 0.25
done
[ -e "/proc/asound/${ALOOP_ID}" ] || { echo "loopback '${ALOOP_ID}' not found"; exit 3; }
sleep 1


# 1) Two FIFOs for fan-out
mkfifo /tmp/dac /tmp/mirror

# 2) Start the two sinks
aplay -D "${DAC_PCM}" -f S16_LE -r "${RATE}" -c 2 /tmp/dac &
aplay -D "${OUT_PCM}" -f S16_LE -r "${RATE}" -c 2 /tmp/mirror &

# 3) Single capture → tee to both sinks
arecord -D "plughw:${IN_PCM#hw:}" -f S16_LE -r "${RATE}" -c 2 \
  --period-size "${PERIOD}" --buffer-size "$((PERIOD*FRAGS))" \
| tee /tmp/dac > /tmp/mirror











# # ---- 3) Create minimal ALSA config INSIDE the container ----
# # Defines a dsnoop tap called 'loop_tap' over the capture end we want to share.
# cat >/etc/asound.conf <<EOF
# pcm.loop_tap {
#   type dsnoop
#   ipc_key 12345
#   slave {
#     pcm "${IN_HW}"
#     channels 2
#     rate ${RATE}
#     period_size ${PERIOD}
#     buffer_size $((PERIOD*FRAGS))
#   }
# }
# EOF

# # (Optional): quick visibility
# aplay -l || true
# arecord -l || true

# # ---- 4) Start the fan-out(s) from the shared tap ----
# pids=""

# log "alsaloop: loop_tap -> ${OUT_PCM} @ ${RATE}"
# alsaloop -C loop_tap -P "${OUT_PCM}" -r "${RATE}" -p "${PERIOD}" -n "${FRAGS}" -t 10000 -S 75 -v &
# pids="$pids $!"

# if [ -n "${OUT_PCM2}" ]; then
#   log "alsaloop (mirror): loop_tap -> ${OUT_PCM2} @ ${RATE}"
#   alsaloop -C loop_tap -P "${OUT_PCM2}" -r "${RATE}" -p "${PERIOD}" -n "${FRAGS}" -t 10000 -S 75 -v &
#   pids="$pids $!"
# fi

# # ---- 5) Wait / clean shutdown ----
# trap 'log "stopping"; [ -n "$pids" ] && kill $pids 2>/dev/null || true; wait || true; exit 0' TERM INT
# wait -n
