#!/bin/bash
# Stop the delivery software started by start_stack.sh, in reverse order. Runs ON THE ROBOT (see delivery/README.md,
# Connecting). Never uses sudo and never touches turtlebot4.service or any program that is not one of these launches.
#
#   bash stop_stack.sh [--dry-run]
#
# Sends SIGINT (like Ctrl+C, a clean shutdown) to the launch processes of your own user: nav2.launch.py, then
# delivery_stack.launch.py, then localization.launch.py and slam.launch.py. Waits up to 20 s for each group, then
# lists what is left (pgrep -af 'nav2|slam_toolbox|amcl|map_server'). It does not use SIGKILL; if something stays,
# it only tells you.

WAIT=20   # seconds to wait per group
die() { echo "ERROR: $*" >&2; exit 1; }

DRY=0
case "${1:-}" in
  "") ;;
  --dry-run) DRY=1 ;;
  -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) die "unknown argument: $1 (only --dry-run)" ;;
esac
if ! command -v pgrep >/dev/null 2>&1; then
  if [ "$DRY" = 1 ]; then echo "(dry run) pgrep not found here; on the robot it is used to find the launches"; else die "pgrep not found"; fi
fi
UID_NOW="$(id -u)"

# stop_group LABEL PATTERN... : SIGINT to the matching launch processes, wait, report.
stop_group() {
  local label="$1"; shift
  local pids="" p pat
  for pat in "$@"; do
    p="$(pgrep -u "$UID_NOW" -f "$pat" 2>/dev/null | tr '\n' ' ')"
    pids="$pids$p"
  done
  # shellcheck disable=SC2116,SC2086  # on purpose: squeeze the blanks between the pids
  pids="$(echo $pids)"
  if [ -z "$pids" ]; then echo "$label: not running"; return 0; fi
  if [ "$DRY" = 1 ]; then echo "[dry-run] kill -INT $pids   ($label), then wait up to $WAIT s"; return 0; fi
  echo "$label: sending SIGINT to $pids"
  # shellcheck disable=SC2086  # on purpose: one argument per pid
  kill -INT $pids 2>/dev/null
  local i=0 left
  while [ "$i" -lt "$WAIT" ]; do
    left=""
    for pat in "$@"; do left="$left$(pgrep -u "$UID_NOW" -f "$pat" 2>/dev/null)"; done
    if [ -z "$left" ]; then echo "$label: stopped"; return 0; fi
    sleep 1; i=$((i + 1))
  done
  echo "$label: still running after $WAIT s (left alone, check below)"
}

stop_group "delivery stack" "delivery_stack.launch.py"
stop_group "nav2" "nav2.launch.py"
stop_group "localization/slam" "localization.launch.py" "slam.launch.py"

echo
echo "Leftovers (pgrep -af 'nav2|slam_toolbox|amcl|map_server'):"
left="$(pgrep -af 'nav2|slam_toolbox|amcl|map_server' 2>/dev/null)"
if [ -z "$left" ]; then echo "none, all stopped"; else echo "$left"; echo "(not killed; look at them before doing anything)"; fi
exit 0
