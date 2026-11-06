#!/bin/bash
# End-to-end delivery simulation ON THE ROBOT, with the robot sitting on its dock and fully isolated from the real base.
# Runs the REAL Nav2, AMCL, costmap filters and delivery_mission.py against fake_base.py (a fake Create 3 + lidar).
# Log in to the robot with ssh first (see delivery/README.md, Connecting). Never uses sudo.
#
#   bash run_e2e.sh <scenario> [--keep] [--dry-run]
#
# Scenarios (pass criteria in sim/README.md):
#   happy           vendor and student press their buttons; the mission must exit 0
#   pickup_timeout  nobody presses "food placed"; the robot drives home empty; exit 4
#   stall           /odom and /tf stop for 5 s while driving (TB-25); the mission holds and goes on; exit 0
#   nav_fail        the robot jams at the 3rd outbound pose; the mission raises the alarm; exit 3
#   dock_retry      the first /dock fails; the mission drives closer and docks at the second try; exit 0
# --keep    keep the big generated files (map copy, ROS logs) in the run folder
# --dry-run  print what would be done; start nothing and write nothing
#
# ISOLATION (the safety requirement): everything runs with ROS_DOMAIN_ID=$SIM_DOMAIN (default 77). The script
# refuses to start when that is empty or 0, and checks every process it starts. The real base listens on domain 0
# only. Discovery is forced to this computer (ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST) and a discovery server
# setting from /etc/turtlebot4/setup.bash is dropped, so the simulator does not even find the real base.
# Nothing is written outside the run folder ~/robot_code/logs/delivery/sim_<time>_<scenario>/ (and /tmp).
# The real ~/STOP file is still honoured: if it exists the script refuses to start, and if it appears during the run
# the mission stops (and so does everything else).
#
# Environment knobs: SIM_DOMAIN (77), SIM_GOAL_X (60, pickup spot in m; use 20 for a short run), SIM_ACTIVE_WAIT
# (150, s to wait for 'Managed nodes are active'), SIM_TOTAL_TIMEOUT (1800, s for the mission), SIM_RUN_DIR (override
# the run folder, must be under ~/robot_code/logs/delivery or /tmp), SIM_DRIFT (odometry error, for example 0.02 = 2 %;
# default none, the fake odometry is then perfect).
#
# The launch command is the same as in robot/start_stack.sh nav (launch/delivery_stack.launch.py, one process); only
# the log folder differs (start_stack.sh has no hook for it, so it is repeated here).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELIVERY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NAV2_PARAMS="$DELIVERY_DIR/config/nav2_delivery.yaml"
STACK_LAUNCH="$DELIVERY_DIR/launch/delivery_stack.launch.py"
# A background job of a non-interactive shell ignores SIGINT; this wrapper restores it (same as start_stack.sh).
RESET_INT='import os, signal, sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execvp(sys.argv[1], sys.argv[1:])'

SIM_DOMAIN="${SIM_DOMAIN:-77}"
GOAL_X="${SIM_GOAL_X:-60}"
ACTIVE_WAIT="${SIM_ACTIVE_WAIT:-150}"
TOTAL_TIMEOUT="${SIM_TOTAL_TIMEOUT:-1800}"

usage() { sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "ERROR: $*" >&2; exit 1; }

SCENARIO=""; KEEP=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    happy|pickup_timeout|stall|nav_fail|dock_retry) SCENARIO="$1" ;;
    --keep) KEEP=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done
[ -n "$SCENARIO" ] || { usage >&2; die "give a scenario: happy, pickup_timeout, stall, nav_fail or dock_retry"; }

# ---- the domain guard: used before anything is started and again before every process
guard() {
  if ! [[ "${ROS_DOMAIN_ID:-}" =~ ^[0-9]+$ ]] || [ "$((10#$ROS_DOMAIN_ID))" -eq 0 ]; then
    die "REFUSING: ROS_DOMAIN_ID is '${ROS_DOMAIN_ID:-}' (unset, not a number or 0). The simulator must never run in domain 0, the real robot's domain."
  fi
}
export ROS_DOMAIN_ID="$SIM_DOMAIN"
guard

# ---- scenario table
PRESS="pickup:3,handoff:4"; STALL=""; FAILPOSE=0; EXPECT=0; PICKUP_TO=600; LEG_TO=600; ALLOW_SHORT=""; DOCKFAIL=0
case "$SCENARIO" in
  happy) ;;
  pickup_timeout) PRESS=""; PICKUP_TO=25; EXPECT=4 ;;
  stall) STALL="25,5" ;;
  nav_fail) FAILPOSE=3; LEG_TO=120; EXPECT=3; ALLOW_SHORT="--allow-short" ;;
  dock_retry) DOCKFAIL=1 ;;
esac

RUN="${SIM_RUN_DIR:-$HOME/robot_code/logs/delivery/sim_$(date +%Y%m%d_%H%M%S)_$SCENARIO}"
ROUTE="$RUN/route"

# ---- refuse while a real run could be going on (domain 0 or any stack of ours)
busy=""
if command -v pgrep >/dev/null 2>&1; then
  for pat in delivery_mission.py fake_base.py slam.launch.py localization.launch.py delivery_stack.launch.py nav2.launch.py; do
    if pgrep -f "$pat" >/dev/null 2>&1; then busy="$busy $pat"; fi
  done
elif [ "$DRY" = 0 ]; then
  die "pgrep not found, cannot check for a running mission"
fi
[ -z "$busy" ] || die "REFUSING: already running:$busy. A real mission or navigation stack is up (maybe in domain 0). Stop it first (robot/stop_stack.sh)."
[ ! -e "$HOME/STOP" ] || die "REFUSING: $HOME/STOP exists. Delete it first: rm $HOME/STOP"

# --scan-when-docked: start_stack.sh turns the real lidar motor on before Nav2, so the sim does the same.
FAKE_ARGS=(--map "$ROUTE/map.yaml" --route "$ROUTE/route.yaml" --glass "@$RUN/sim_world.json" --run-dir "$RUN" --press "$PRESS" --scan-when-docked)
[ -n "$STALL" ] && FAKE_ARGS+=(--stall "$STALL")
[ "$FAILPOSE" != 0 ] && FAKE_ARGS+=(--fail-after-pose "$FAILPOSE")
[ -n "${SIM_DRIFT:-}" ] && FAKE_ARGS+=(--drift "$SIM_DRIFT")
[ "$DOCKFAIL" != 0 ] && FAKE_ARGS+=(--dock-fail-first "$DOCKFAIL")

if [ "$DRY" = 1 ]; then
  echo "(dry run) scenario $SCENARIO, expected mission exit code $EXPECT, ROS_DOMAIN_ID=$ROS_DOMAIN_ID (guard passed)"
  echo "(dry run) run folder: $RUN"
  echo "[dry-run] source /etc/turtlebot4/setup.bash (if ros2 is not on the PATH), then ROS_DOMAIN_ID=$ROS_DOMAIN_ID, ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST, unset ROS_DISCOVERY_SERVER, ROS_LOG_DIR=$RUN/roslog"
  echo "[dry-run] python3 $SCRIPT_DIR/sim_map.py --out $RUN/src --goal-x $GOAL_X --pickup-timeout $PICKUP_TO --leg-timeout $LEG_TO"
  echo "[dry-run] python3 $DELIVERY_DIR/tools/plan_route.py --map $RUN/src/route_map.yaml --spec $RUN/src/route_spec.yaml --out $ROUTE"
  echo "[dry-run] setsid nohup python3 $SCRIPT_DIR/fake_base.py ${FAKE_ARGS[*]} > $RUN/fake_base.log &"
  echo "[dry-run] setsid nohup ros2 launch $STACK_LAUNCH map:=$ROUTE/map.yaml keepout_mask:=$ROUTE/keepout_mask.yaml speed_mask:=$ROUTE/speed_mask.yaml localization_params:=$RUN/localization.yaml nav2_params:=$NAV2_PARAMS > $RUN/nav2.log &"
  echo "[dry-run] wait up to $ACTIVE_WAIT s for 'Managed nodes are active' in nav2.log; sample top every 30 s into $RUN/top.log"
  echo "[dry-run] python3 $DELIVERY_DIR/delivery_mission.py --route $ROUTE/route.yaml --yes --log-dir $RUN/mission_log > $RUN/mission.out   (timeout $TOTAL_TIMEOUT s)"
  echo "[dry-run] stop every process group with SIGINT, then SIGTERM; python3 $SCRIPT_DIR/analyse_run.py --run-dir $RUN --expect-exit $EXPECT $ALLOW_SHORT"
  exit 0
fi

# ---- ROS environment (after this the domain is forced again: setup.bash may set its own)
if ! command -v ros2 >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  [ -f /etc/turtlebot4/setup.bash ] && source /etc/turtlebot4/setup.bash >/dev/null 2>&1
  command -v ros2 >/dev/null 2>&1 || die "ros2 not found, even after /etc/turtlebot4/setup.bash"
fi
export ROS_DOMAIN_ID="$SIM_DOMAIN"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST ROS_LOCALHOST_ONLY=1
unset ROS_DISCOVERY_SERVER ROS_SUPER_CLIENT FASTRTPS_DEFAULT_PROFILES_FILE
export PYTHONDONTWRITEBYTECODE=1
guard

mkdir -p "$RUN" "$RUN/roslog" || die "cannot create $RUN"
export ROS_LOG_DIR="$RUN/roslog"
{
  echo "scenario: $SCENARIO"; echo "started: $(date '+%F %T %z')"; echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
  echo "expected mission exit code: $EXPECT"
} > "$RUN/state.txt"
echo "run folder: $RUN"

PIDS=(); NAMES=(); SAMPLER_PID=""; CLEANED=0; MISSION_PID=""

verify_domain() {   # the process must really carry the simulator domain
  local pid="$1" name="$2" val="" i
  # Just after the fork /proc/PID/environ still shows the old image, so look again until the exec has happened.
  for i in $(seq 1 25); do
    [ -r "/proc/$pid/environ" ] || return 0
    val="$(tr '\0' '\n' < "/proc/$pid/environ" | sed -n 's/^ROS_DOMAIN_ID=//p')"
    [ -n "$val" ] && break
    sleep 0.2
  done
  if ! [[ "$val" =~ ^[0-9]+$ ]] || [ "$((10#$val))" -eq 0 ]; then
    echo "ERROR: $name (pid $pid) has ROS_DOMAIN_ID='$val'. Stopping everything." >&2
    return 1
  fi
}

start_bg() {   # start_bg NAME CMD... : own session, log in the run folder
  local name="$1"; shift
  guard
  setsid nohup python3 -c "$RESET_INT" "$@" > "$RUN/$name.log" 2>&1 < /dev/null &
  local pid=$!
  PIDS+=("$pid"); NAMES+=("$name")
  echo "pid=$pid name=$name cmd: $*" >> "$RUN/state.txt"
  echo "$(date +%T) started $name (pid $pid)"
  verify_domain "$pid" "$name" || { cleanup; exit 1; }
}

stop_group() {   # SIGINT, then SIGTERM, then SIGKILL on the whole process group of one of OUR sessions
  local pid="$1" target="$1" sig i
  kill -0 "$pid" 2>/dev/null || return 0
  local pgid; pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  [ "$pgid" = "$pid" ] && target="-$pid"     # never signal a group that is not the one we created
  for sig in INT TERM KILL; do
    kill -s "$sig" -- "$target" 2>/dev/null
    for i in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || return 0; sleep 0.2; done
  done
}

cleanup() {
  [ "$CLEANED" = 1 ] && return
  CLEANED=1
  trap '' INT TERM
  echo "stopping everything ..."
  [ -n "$SAMPLER_PID" ] && { kill "$SAMPLER_PID" 2>/dev/null; pkill -P "$SAMPLER_PID" 2>/dev/null; }
  [ -n "$MISSION_PID" ] && stop_group "$MISSION_PID"
  local i
  for ((i=${#PIDS[@]}-1; i>=0; i--)); do stop_group "${PIDS[$i]}"; done
  # nothing of ours may be left running
  for ((i=0; i<${#PIDS[@]}; i++)); do
    kill -0 "${PIDS[$i]}" 2>/dev/null && echo "WARNING: ${NAMES[$i]} (pid ${PIDS[$i]}) is still running" >&2
  done
  echo "stopped: $(date '+%F %T %z')" >> "$RUN/state.txt"
}
trap cleanup EXIT
trap 'echo "interrupted"; cleanup; exit 130' INT TERM

# ---- map, spec and route
python3 "$SCRIPT_DIR/sim_map.py" --out "$RUN/src" --goal-x "$GOAL_X" --pickup-timeout "$PICKUP_TO" --leg-timeout "$LEG_TO" || die "sim_map.py failed"
python3 "$DELIVERY_DIR/tools/plan_route.py" --map "$RUN/src/route_map.yaml" --spec "$RUN/src/route_spec.yaml" --out "$ROUTE" > "$RUN/plan_route.log" 2>&1 \
  || { cat "$RUN/plan_route.log" >&2; die "plan_route.py failed"; }
tail -n 4 "$RUN/plan_route.log"
cp "$RUN/src/sim_world.json" "$RUN/sim_world.json"

# ---- the fake base first, then the stack (same commands as robot/start_stack.sh nav)
start_bg fake_base python3 "$SCRIPT_DIR/fake_base.py" "${FAKE_ARGS[@]}"
sleep 6
kill -0 "${PIDS[0]}" 2>/dev/null || { tail -n 20 "$RUN/fake_base.log" >&2; die "fake_base.py did not start (see $RUN/fake_base.log)"; }
python3 "$DELIVERY_DIR/tools/make_localization_params.py" --route "$ROUTE/route.yaml"   --base "$DELIVERY_DIR/config/localization_delivery.yaml" --out "$RUN/localization.yaml" || die "cannot write $RUN/localization.yaml"
start_bg nav2 ros2 launch "$STACK_LAUNCH" map:="$ROUTE/map.yaml" keepout_mask:="$ROUTE/keepout_mask.yaml"   speed_mask:="$ROUTE/speed_mask.yaml" localization_params:="$RUN/localization.yaml" nav2_params:="$NAV2_PARAMS"

echo "waiting up to $ACTIVE_WAIT s for 'Managed nodes are active' ..."
active=0
for ((t=0; t<ACTIVE_WAIT; t+=2)); do
  if grep -q "Managed nodes are active" "$RUN/nav2.log" 2>/dev/null; then active=1; break; fi
  for ((i=0; i<${#PIDS[@]}; i++)); do
    kill -0 "${PIDS[$i]}" 2>/dev/null || { echo "ERROR: ${NAMES[$i]} died; see $RUN/${NAMES[$i]}.log" >&2; tail -n 15 "$RUN/${NAMES[$i]}.log" >&2; exit 1; }
  done
  [ -e "$HOME/STOP" ] && die "$HOME/STOP appeared, stopping"
  sleep 2
done
if [ "$active" = 1 ]; then
  echo "Nav2 reports: Managed nodes are active"
else
  echo "WARNING: no 'Managed nodes are active' after $ACTIVE_WAIT s. While the robot is docked the lidar is off, so Nav2 may be waiting for the initial pose" >&2
  echo "         (the mission sends it). Continuing; if the mission cannot reach Nav2 it will refuse and this run fails." >&2
fi
echo "active_seen: $active" >> "$RUN/state.txt"

# ---- CPU sampling every 30 s
( while true; do { date +%T; top -b -n1 | head -n 12; } >> "$RUN/top.log" 2>&1; sleep 30; done ) &
SAMPLER_PID=$!

# ---- the mission (real delivery_mission.py; --yes because nobody can answer; the real ~/STOP is honoured)
guard
echo "$(date +%T) starting delivery_mission.py"
setsid nohup python3 -c "$RESET_INT" python3 "$DELIVERY_DIR/delivery_mission.py" --route "$ROUTE/route.yaml" --yes \
  --log-dir "$RUN/mission_log" > "$RUN/mission.out" 2>&1 < /dev/null &
MISSION_PID=$!
verify_domain "$MISSION_PID" delivery_mission || { exit 1; }
START=$SECONDS; nextnote=60
while kill -0 "$MISSION_PID" 2>/dev/null; do
  sleep 2
  el=$((SECONDS - START))
  if [ "$el" -ge "$nextnote" ]; then echo "$(date +%T) mission running for $el s: $(tail -n 1 "$RUN/mission.out" | cut -c1-100)"; nextnote=$((nextnote + 60)); fi
  if [ -e "$HOME/STOP" ]; then echo "$HOME/STOP appeared: stopping the mission"; kill -s INT "$MISSION_PID" 2>/dev/null; fi
  if [ "$el" -ge "$TOTAL_TIMEOUT" ]; then echo "total timeout $TOTAL_TIMEOUT s: stopping the mission"; kill -s INT "$MISSION_PID" 2>/dev/null; fi
  kill -0 "${PIDS[0]}" 2>/dev/null || { echo "ERROR: fake_base died during the run" >&2; kill -s INT "$MISSION_PID" 2>/dev/null; }
done
wait "$MISSION_PID"; CODE=$?
MISSION_PID=""
echo "$CODE" > "$RUN/mission_exit.txt"
echo "mission exit code: $CODE (expected $EXPECT)"
sleep 2

cleanup

# ---- judge
python3 "$SCRIPT_DIR/analyse_run.py" --run-dir "$RUN" --expect-exit "$EXPECT" $ALLOW_SHORT --scenario "$SCENARIO"
RC=$?
if [ "$KEEP" = 0 ]; then rm -rf "$RUN/roslog" "$RUN/src"; fi
if [ "$RC" = 0 ]; then echo "E2E $SCENARIO: PASS ($RUN)"; else echo "E2E $SCENARIO: FAIL ($RUN)"; fi
trap - EXIT
exit "$RC"
