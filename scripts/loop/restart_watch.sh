#!/usr/bin/env bash
# Records the machine's state every 15 s, synced to disk, so whatever ends the desktop session or the machine leaves
# its last reading behind. Also notes each new boot or session, and keeps the journal's warnings beside the samples.
# Read-only and light: one process, a few file reads per sample. `scripts/loop/restart_watch.sh report` reads it back.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/data/loop/restart-watch"
mkdir -p "$DIR"; LOG="$DIR/samples.log"; EV="$DIR/events.log"
if [ "${1:-}" = report ]; then
  echo "boots:"; journalctl --list-boots --no-pager | tail -4 | cut -c1-90
  echo "events:"; tail -25 "$EV" 2>/dev/null | cut -c1-200
  echo "last samples:"; tail -4 "$LOG" 2>/dev/null | cut -c1-230
  exit 0
fi
exec 9>"$DIR/lock"; flock -n 9 || exit 0
read_gpu() { for c in /sys/class/drm/card*/device; do [ -e "$c/mem_info_vram_used" ] || continue; h=$(ls -d "$c"/hwmon/hwmon* | head -1)
  printf ' %s:%sW,%sC,%sMiB,%s%%' "$(basename "$(readlink "$c")" | cut -c6-7)" "$(( $(cat "$h/power1_average" 2>/dev/null || cat "$h/power1_input" 2>/dev/null || echo 0)/1000000 ))" "$(( $(cat "$h/temp1_input" 2>/dev/null || echo 0)/1000 ))" "$(( $(cat "$c/mem_info_vram_used")/1048576 ))" "$(cat "$c/gpu_busy_percent" 2>/dev/null)"; done; }
echo "$(date -Is) watch started boot=$(cut -c1-8 /proc/sys/kernel/random/boot_id) sessions=$(loginctl list-sessions --no-legend | awk '{print $1}' | tr '\n' ' ')" >> "$EV"
journalctl -f -n0 -o short-iso --no-pager 2>/dev/null | grep --line-buffered -E "logged out|New session '|Removed session|Out of memory|oom-kill|segfault|dumped core|Hardware Error|mce:|GPU reset|ring .* timeout|Not enough memory for command|Starting (reboot|poweroff)|The system will|Power key|Started docker-desktop|Thermal|thermal.*critical" | cut -c1-220 >> "$EV" &
while :; do
  cpu=$(sensors 2>/dev/null | awk '/Package id 0/{print $4; exit}')
  echo "$(date -Is) load=$(cut -d' ' -f1 /proc/loadavg) mem_avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)G swap_free=$(awk '/SwapFree/{print int($2/1048576)}' /proc/meminfo)G psi=$(awk 'NR==2{print $2}' /proc/pressure/memory) cpu=$cpu gpu$(read_gpu)" >> "$LOG"
  sync "$LOG" "$EV" 2>/dev/null
  sleep 15
done
