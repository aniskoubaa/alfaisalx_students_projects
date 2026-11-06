#!/bin/bash
# Phase 0, Part B: soak test with mapping and navigation running, robot DOCKED, no goals sent (no motion).
# Runs ON THE ROBOT (see delivery/README.md, Connecting). Needs Ibrahim's OK and a person next to the robot.
# It starts programs and writes files under ~/robot_code/logs/delivery/; it changes no setting and uses no sudo.
#
# Start it detached, so a dropped ssh session does not end it (TB-10), then log out or just wait:
#   setsid nohup bash ~/robot_code/delivery/phase0/p0_soak.sh > ~/p0_soak_console.log 2>&1 < /dev/null &
# Short trial first (about 12 min): add   --baseline 1 --soak 5
# Print the timeline without running anything:   bash p0_soak.sh --dry-run
#
# Options:
#   --recorder PATH   record_timing.py (default: <this dir>/../../tools/timing/record_timing.py, else /tmp/record_timing.py)
#   --baseline MIN    quiet baseline before the stack, default 3
#   --soak MIN        minutes from the Nav2 start until the stop, default 70
#   --dry-run         print the timeline, skip all sleeps, start nothing
#
# Timeline: check /dock_status once (refuses unless docked) -> wait 60 s (TB-25: let the check's ROS participant
# settle) -> record_timing.py --light for the whole test -> baseline -> delivery_stack.launch.py (upstream
# parameters) -> top/uptime/temperature snapshots 20 and 50 min after Nav2 start (and one just before the stop) ->
# stop the stack -> 5 min of tail recording -> recorder ends -> summary file.
# During the run: NO ros2 commands and no TurtleBot Studio connection. Stop early with Ctrl+C (foreground)
# or: kill <pid of p0_soak.sh> (SIGTERM), or: touch ~/STOP. The script then stops the stack it started.
# Output directory: ~/robot_code/logs/delivery/p0_soak_<date-time>/ with p0_soak.jsonl, summary.txt, logs and top.txt.
# Fetch the files with scp and analyse with tools/timing/analyze_timing.py (see the Phase 0 checklist, B6).

# A background job of a non-interactive shell ignores SIGINT, and the launch would inherit that, so stop_stack.sh's
# SIGINT would not work. This tiny python wrapper restores the default SIGINT, then replaces itself with the command.
RESET_INT='import os, signal, sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execvp(sys.argv[1], sys.argv[1:])'

STARTUP_WAIT=60        # s between the dock check and the recorder start
STOP_GAP=20            # s to let the stack stop
TAIL_MIN=5             # minutes of recording after the stop
SNAP_MINUTES="20 50"   # snapshots, minutes after Nav2 start
LOG_ROOT="$HOME/robot_code/logs/delivery"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELIVERY_DIR="$(dirname "$SCRIPT_DIR")"
die() { echo "ERROR: $*" >&2; exit 1; }

RECORDER=""; BASELINE=3; SOAK=70; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --recorder) shift; RECORDER="${1:-}" ;;
    --baseline) shift; BASELINE="${1:-}" ;;
    --soak) shift; SOAK="${1:-}" ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done
case "$BASELINE" in ''|*[!0-9]*) die "--baseline needs whole minutes" ;; esac
case "$SOAK" in ''|*[!0-9]*) die "--soak needs whole minutes" ;; esac
[ "$SOAK" -ge 1 ] || die "--soak must be at least 1"

if [ -z "$RECORDER" ]; then
  if [ -f "$SCRIPT_DIR/../../tools/timing/record_timing.py" ]; then RECORDER="$SCRIPT_DIR/../../tools/timing/record_timing.py"
  else RECORDER=/tmp/record_timing.py; fi
fi
if [ "$DRY" = 0 ]; then
  [ -f "$RECORDER" ] || die "recorder not found: $RECORDER (copy tools/timing/record_timing.py to the robot, or use --recorder PATH)"
  command -v python3 >/dev/null 2>&1 || die "python3 not found"
  command -v pgrep >/dev/null 2>&1 || die "pgrep not found"
  if ! command -v ros2 >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    [ -f /etc/turtlebot4/setup.bash ] && source /etc/turtlebot4/setup.bash >/dev/null 2>&1
    command -v ros2 >/dev/null 2>&1 || die "ros2 not found"
  fi
  for pat in slam.launch.py nav2.launch.py localization.launch.py delivery_stack.launch.py 'python3 .*record_timing.py'; do
    if pgrep -f "$pat" >/dev/null 2>&1; then die "$pat is already running; run stop_stack.sh (or stop it) first"; fi
  done
fi

DURATION=$(( (BASELINE + SOAK + TAIL_MIN) * 60 ))   # recorder length, s
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$LOG_ROOT/p0_soak_$STAMP"
SUMMARY="$OUTDIR/summary.txt"
JSONL="$OUTDIR/p0_soak.jsonl"
TOPFILE="$OUTDIR/top.txt"

# Virtual clock for the dry run: offsets in seconds from the start.
VT=0
stamp() { if [ "$DRY" = 1 ]; then printf 'T+%02d:%02d:%02d' $((VT/3600)) $((VT%3600/60)) $((VT%60)); else date '+%F %T'; fi; }
nap() {   # nap SECONDS : sleep, or advance the virtual clock; watch for the STOP file
  if [ "$DRY" = 1 ]; then VT=$((VT + $1)); return 0; fi
  local left="$1"
  while [ "$left" -gt 0 ]; do
    if [ -e "$HOME/STOP" ]; then echo "$(stamp) ~/STOP found, ending the test early"; STOPPED_EARLY=1; return 1; fi
    sleep 1; left=$((left - 1))
  done
  return 0
}
# shellcheck disable=SC2034  # kept for the summary and for people reading the log
STOPPED_EARLY=0
T_START=""; T_RECORDER=""; T_NAV2=""; T_STOP_NAV2=""; T_END=""; T_SNAPS=""
STARTED_NAV2=0

log() { echo "$(stamp) $*"; }
launch_bg() {   # launch_bg NAME CMD...
  local name="$1"; shift
  if [ "$DRY" = 1 ]; then echo "    [dry-run] setsid nohup $* > $OUTDIR/$name.log 2>&1 < /dev/null &"; return 0; fi
  setsid nohup python3 -c "$RESET_INT" "$@" > "$OUTDIR/$name.log" 2>&1 < /dev/null &
}
snapshot() {
  local label="$1"
  T_SNAPS="$T_SNAPS
  $(stamp)  $label"
  log "snapshot: $label"
  if [ "$DRY" = 1 ]; then echo "    [dry-run] top -b -n 1 | head -n 25 >> $TOPFILE; uptime; vcgencmd measure_temp"; return 0; fi
  { echo "=== $(date '+%F %T') $label ==="
    top -b -n 1 | head -n 25
    uptime
    vcgencmd measure_temp 2>/dev/null || echo "vcgencmd not available"
    echo; } >> "$TOPFILE"
}

robot_state() {   # call a service that changes no wheels; a failure is reported, not fatal
  if [ "$DRY" = 1 ]; then echo "    [dry-run] timeout 40 ros2 service call /$1 $2"; return 0; fi
  timeout 40 ros2 service call "/$1" "$2" >/dev/null 2>&1 < /dev/null || log "WARNING: service /$1 did not answer"
}

restore_robot() {
  log "restore: lidar motor off (as on the dock)"
  robot_state stop_motor std_srvs/srv/Empty
}

cleanup() {
  trap - INT TERM
  if [ "$STARTED_NAV2" = 1 ] && pgrep -f delivery_stack.launch.py >/dev/null 2>&1; then
    log "cleanup: stopping the navigation stack"; pkill -INT -u "$(id -u)" -f delivery_stack.launch.py; sleep "$STOP_GAP"
  fi
  restore_robot
  log "interrupted; the recorder keeps running until its own end (pkill -f record_timing.py to end it)"
  write_summary "INTERRUPTED"
  exit 130
}

write_summary() {
  local state="$1"
  [ "$DRY" = 1 ] && return 0
  {
    echo "Phase 0 soak test: $state"
    echo "Written: $(date '+%F %T %z')"
    echo
    echo "Timestamps (robot wall clock):"
    echo "  start (dock checked)  ${T_START:-not reached}"
    echo "  recorder start        ${T_RECORDER:-not reached}"
    echo "  Nav2 start            ${T_NAV2:-not reached}"
    echo "  snapshots:${T_SNAPS:- none}"
    echo "  Nav2 stop             ${T_STOP_NAV2:-not reached}"
    echo "  recorder ended        ${T_END:-not reached}"
    echo
    echo "Durations: baseline ${BASELINE} min, soak ${SOAK} min after Nav2 start, tail ${TAIL_MIN} min."
    echo "Recorder: $RECORDER --light --duration $DURATION"
    echo
    echo "Files in $OUTDIR:"
    # shellcheck disable=SC2012
    ls -l "$OUTDIR" 2>/dev/null | sed 's/^/  /'
    echo
    echo "Next: copy the folder to your computer with scp, then in the repo's TurtleBot folder run"
    echo "  python tools/timing/analyze_timing.py p0_soak.jsonl --csv p0_gaps.csv --html p0_timeline.html"
    echo "Pass criteria are in the Phase 0 checklist, B6 (no /odom gap over 0.3 s from 10 min after Nav2 start)."
    echo "Check Nav2 came up: grep -i 'managed nodes are active' $OUTDIR/nav2.log"
  } > "$SUMMARY"
}

echo "Phase 0 soak test. Output: $OUTDIR"
echo "Baseline ${BASELINE} min, soak ${SOAK} min, recorder ${DURATION} s. Timeline times are $( [ "$DRY" = 1 ] && echo 'virtual (dry run)' || echo 'robot wall clock')."
if [ "$DRY" = 0 ]; then mkdir -p "$OUTDIR" || die "cannot create $OUTDIR"; fi

# 1. dock check, once, at the very start
log "check /dock_status (once)"
if [ "$DRY" = 1 ]; then
  echo "    [dry-run] timeout 60 ros2 topic echo --once /dock_status   (must say is_docked: true, else refuse)"
else
  dock_out="$(timeout 60 ros2 topic echo --once /dock_status 2>&1 < /dev/null)"
  echo "$dock_out" | grep -q "is_docked: true" || die "/dock_status does not say is_docked: true (got: $(echo "$dock_out" | head -n 2 | tr '\n' ' ')). Refusing."
fi
# Same conditions as a real run: lidar motor on (the TurtleBot 4 power saver stops it on the dock). The camera stays
# stopped by the same power saver; the delivery program stops it again after undocking.
log "lidar motor on (no wheels move; undone at the end)"
robot_state start_motor std_srvs/srv/Empty
T_START="$(stamp)"
trap cleanup INT TERM
log "wait ${STARTUP_WAIT} s before the recorder (TB-25)"
nap "$STARTUP_WAIT" || { write_summary "STOPPED EARLY (~/STOP)"; exit 1; }

# 2. recorder for the whole test
log "start recorder (--light, ${DURATION} s)"
T_RECORDER="$(stamp)"
launch_bg recorder python3 "$RECORDER" --light --duration "$DURATION" --out "$JSONL" --overwrite
REC_PID=$!
if [ "$DRY" = 0 ]; then sleep 2; kill -0 "$REC_PID" 2>/dev/null || die "the recorder did not start; see $OUTDIR/recorder.log"; fi

# 3. baseline, navigation stack
log "baseline ${BASELINE} min"
nap $((BASELINE * 60)) || { cleanup; }
# The stack a delivery really runs (launch/delivery_stack.launch.py), on a synthetic route: the robot stays on the dock
# and no goal is sent, so the map content does not matter here.
log "make a test route (sim/sim_map.py, tools/plan_route.py)"
ROUTE="$OUTDIR/route"
if [ "$DRY" = 1 ]; then
  echo "    [dry-run] python3 sim/sim_map.py --out $OUTDIR/src; python3 tools/plan_route.py ... --out $ROUTE; python3 tools/make_localization_params.py ..."
else
  if ! python3 "$DELIVERY_DIR/sim/sim_map.py" --out "$OUTDIR/src" > "$OUTDIR/route.log" 2>&1 \
    || ! python3 "$DELIVERY_DIR/tools/plan_route.py" --map "$OUTDIR/src/route_map.yaml" --spec "$OUTDIR/src/route_spec.yaml" --out "$ROUTE" >> "$OUTDIR/route.log" 2>&1 \
    || ! python3 "$DELIVERY_DIR/tools/make_localization_params.py" --route "$ROUTE/route.yaml" --base "$DELIVERY_DIR/config/localization_delivery.yaml" --out "$OUTDIR/localization.yaml"; then
    restore_robot; die "could not make the test route; see $OUTDIR/route.log"
  fi
fi
log "start the navigation stack (launch/delivery_stack.launch.py)"
T_NAV2="$(stamp)"; STARTED_NAV2=1
launch_bg nav2 ros2 launch "$DELIVERY_DIR/launch/delivery_stack.launch.py" map:="$ROUTE/map.yaml" keepout_mask:="$ROUTE/keepout_mask.yaml"   speed_mask:="$ROUTE/speed_mask.yaml" localization_params:="$OUTDIR/localization.yaml"

# 4. soak with snapshots (minutes after Nav2 start)
elapsed=0
for m in $SNAP_MINUTES; do
  if [ "$m" -lt "$SOAK" ]; then
    nap $(( (m - elapsed) * 60 )) || { cleanup; }
    elapsed=$m
    snapshot "${m} min after Nav2 start"
  fi
done
nap $(( (SOAK - elapsed) * 60 )) || { cleanup; }
snapshot "just before the stop (${SOAK} min after Nav2 start)"

# 5. stop the stack
log "stop the navigation stack (SIGINT)"
T_STOP_NAV2="$(stamp)"
if [ "$DRY" = 1 ]; then echo "    [dry-run] pkill -INT -u \$(id -u) -f delivery_stack.launch.py"; else pkill -INT -u "$(id -u)" -f delivery_stack.launch.py; fi
STARTED_NAV2=0

# 6. tail, then wait for the recorder to end
log "tail recording ${TAIL_MIN} min, then wait for the recorder to end"
nap $((TAIL_MIN * 60))
if [ "$DRY" = 0 ]; then
  i=0
  while kill -0 "$REC_PID" 2>/dev/null && [ "$i" -lt 180 ]; do sleep 1; i=$((i + 1)); done
  if kill -0 "$REC_PID" 2>/dev/null; then log "recorder still running, sending SIGINT"; kill -INT "$REC_PID"; sleep 5; fi
  left="$(pgrep -af 'nav2|slam_toolbox' 2>/dev/null)"
  [ -z "$left" ] || log "WARNING: still running: $left"
fi
T_END="$(stamp)"
restore_robot
log "done"
write_summary "FINISHED"
if [ "$DRY" = 1 ]; then
  echo
  echo "[dry-run] nothing was started. A real run writes $SUMMARY"
else
  echo "Summary: $SUMMARY"
fi
exit 0
