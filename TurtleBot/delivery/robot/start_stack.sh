#!/bin/bash
# Start the mapping or the navigation software for the delivery robot, detached, with logs.
# Runs ON THE ROBOT (log in with ssh first; see delivery/README.md, Connecting). Never uses sudo.
#
#   bash start_stack.sh map [--with-nav2] [--keep-camera] [--dry-run]
#       slam_toolbox mapping (ros2 launch turtlebot4_navigation slam.launch.py sync:=false params:=config/slam_delivery.yaml).
#       Nav2 is NOT started unless --with-nav2 (then with the upstream parameters, because the
#       delivery parameters need the filter masks, which do not exist while mapping).
#   bash start_stack.sh nav --route-dir DIR [--keep-camera] [--dry-run]
#       DIR holds map.yaml, keepout_mask.yaml, speed_mask.yaml and route.yaml. Starts launch/delivery_stack.launch.py:
#       the whole navigation stack in one process, with config/nav2_delivery.yaml and AMCL localized at the route's dock.
#
# The config and launch files are found relative to this script (../config, ../launch), so the whole
# delivery folder can be copied anywhere, for example ~/robot_code/delivery.
# Every launch runs as: setsid nohup ... < /dev/null &   (it survives the ssh session ending; a small python3
# wrapper in front restores SIGINT, which a background job of a script would otherwise ignore).
# Logs: ~/robot_code/logs/delivery/<date-time>/<name>.log and state.txt (what was started, with PIDs).
# Stop everything with stop_stack.sh. Refuses to start if one of these launches already runs.
# --dry-run prints the commands and runs nothing (no directories are created).
# The OAK-D camera container is stopped first, unless --keep-camera: the delivery does not use the camera, and that
# process keeps one CPU core at about 100 % even with the camera stopped (measured 2026-11-06). With it running the Pi
# reached a load of 18 during a trip. It stays off until the next reboot; nothing else on the robot needs it.
#
# TB-25: every new ROS participant can stall the Create 3 base topics for up to about 12 s. Start no other
# ROS program (no ros2 command, no TurtleBot Studio connection) while this runs and for a while after it,
# and wait until /odom is steady. delivery_mission.py waits for that by itself.

# A background job of a non-interactive shell ignores SIGINT, and the launch would inherit that, so stop_stack.sh's
# SIGINT would not work. This tiny python wrapper restores the default SIGINT, then replaces itself with the command.
RESET_INT='import os, signal, sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execvp(sys.argv[1], sys.argv[1:])'

PAUSE="${DELIVERY_PAUSE:-20}"   # seconds between the launches (TB-25: let the base settle); the variable is for tests only
LOG_ROOT="$HOME/robot_code/logs/delivery"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELIVERY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NAV2_PARAMS="$DELIVERY_DIR/config/nav2_delivery.yaml"
SLAM_PARAMS="$DELIVERY_DIR/config/slam_delivery.yaml"
STACK_LAUNCH="$DELIVERY_DIR/launch/delivery_stack.launch.py"

usage() { sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "ERROR: $*" >&2; exit 1; }

MODE=""; ROUTE_DIR=""; WITH_NAV2=0; DRY=0; KEEP_CAMERA=0
while [ $# -gt 0 ]; do
  case "$1" in
    map|nav) MODE="$1" ;;
    --route-dir) shift; ROUTE_DIR="${1:-}" ;;
    --route-dir=*) ROUTE_DIR="${1#*=}" ;;
    --with-nav2) WITH_NAV2=1 ;;
    --keep-camera) KEEP_CAMERA=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done
[ -n "$MODE" ] || { usage >&2; die "give a mode: map or nav"; }
if [ "$MODE" = nav ]; then
  [ -n "$ROUTE_DIR" ] || die "nav mode needs --route-dir DIR"
  if [ -d "$ROUTE_DIR" ]; then ROUTE_DIR="$(cd "$ROUTE_DIR" && pwd)"; fi
  for f in "$ROUTE_DIR/map.yaml" "$ROUTE_DIR/keepout_mask.yaml" "$ROUTE_DIR/speed_mask.yaml" \
           "$ROUTE_DIR/route.yaml" "$NAV2_PARAMS" "$STACK_LAUNCH"; do
    if [ ! -f "$f" ]; then
      if [ "$DRY" = 1 ]; then echo "WARNING (dry run): $f is missing"; else die "$f is missing"; fi
    fi
  done
fi

# ROS environment (the robot's login shell normally has it already).
if ! command -v ros2 >/dev/null 2>&1; then
  if [ "$DRY" = 1 ]; then
    echo "(dry run) would source /etc/turtlebot4/setup.bash because ros2 is not on the PATH"
  else
    # shellcheck disable=SC1091
    [ -f /etc/turtlebot4/setup.bash ] && source /etc/turtlebot4/setup.bash >/dev/null 2>&1
    command -v ros2 >/dev/null 2>&1 || die "ros2 not found, even after /etc/turtlebot4/setup.bash"
  fi
fi

# Refuse if any of these launches is already running (one stack at a time).
if command -v pgrep >/dev/null 2>&1; then
  busy=""
  for pat in "slam.launch.py" "localization.launch.py" "delivery_stack.launch.py" "nav2.launch.py"; do
    if pgrep -f "$pat" >/dev/null 2>&1; then busy="$busy $pat"; fi
  done
  [ -z "$busy" ] || die "already running:$busy. Run stop_stack.sh first."
else
  [ "$DRY" = 1 ] || die "pgrep not found, cannot check for a running stack"
fi

# The unused camera container (see the top of this file). The bracket keeps pgrep from finding this script's own shell.
CAMERA_PATTERN='__node:=oakd_contain[e]r'
if [ "$KEEP_CAMERA" = 0 ]; then
  if [ "$DRY" = 1 ]; then
    echo "(dry run) would stop the OAK-D camera container: pkill -INT -f $CAMERA_PATTERN"
  elif pgrep -f "$CAMERA_PATTERN" >/dev/null 2>&1; then
    pkill -INT -f "$CAMERA_PATTERN" && echo "stopped the OAK-D camera container (it comes back with the next reboot)"
  fi
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
LOGDIR="$LOG_ROOT/$STAMP"
STATE="$LOGDIR/state.txt"
if [ "$DRY" = 1 ]; then
  echo "(dry run) logs would go to $LOGDIR"
else
  mkdir -p "$LOGDIR" || die "cannot create $LOGDIR"
  {
    echo "started: $(date '+%F %T %z')"
    echo "mode: $MODE"
    echo "script: $SCRIPT_DIR/$(basename "$0")"
    if [ -n "$ROUTE_DIR" ]; then echo "route_dir: $ROUTE_DIR"; fi
  } > "$STATE"
  ln -sfn "$LOGDIR" "$LOG_ROOT/latest" 2>/dev/null
fi

# launch_bg NAME CMD...  : detached start, one log file per launch, one line in the state file.
launch_bg() {
  local name="$1"; shift
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] setsid nohup $* > $LOGDIR/$name.log 2>&1 < /dev/null &"
    return 0
  fi
  setsid nohup python3 -c "$RESET_INT" "$@" > "$LOGDIR/$name.log" 2>&1 < /dev/null &
  local pid=$!
  echo "$name pid=$pid log=$LOGDIR/$name.log cmd: $*" >> "$STATE"
  echo "$(date +%T) started $name (pid $pid)"
}

pause() {
  if [ "$DRY" = 1 ]; then echo "[dry-run] wait $PAUSE s"; else echo "waiting $PAUSE s ..."; sleep "$PAUSE"; fi
}

# The lidar motor is off while the robot is docked (TB-24), and without scans AMCL publishes no map -> odom transform,
# so Nav2's costmaps would wait for ever. Starting the motor moves no wheels.
if [ "$DRY" = 1 ]; then
  echo "[dry-run] timeout 40 ros2 service call /start_motor std_srvs/srv/Empty"
else
  timeout 40 ros2 service call /start_motor std_srvs/srv/Empty > "$LOGDIR/start_motor.log" 2>&1 || echo "WARNING: could not start the lidar motor (see $LOGDIR/start_motor.log)"
fi

if [ "$MODE" = map ]; then
  launch_bg slam ros2 launch turtlebot4_navigation slam.launch.py sync:=false params:="$SLAM_PARAMS"
  if [ "$WITH_NAV2" = 1 ]; then
    pause
    # Not the installed nav2.yaml: it sets use_sim_time true (see delivery/README.md, section 13).
    launch_bg nav2 ros2 launch turtlebot4_navigation nav2.launch.py params_file:="$DELIVERY_DIR/config/upstream/turtlebot4_nav2_jazzy.yaml"
  fi
else
  # AMCL starts localized at the route's dock pose, so the robot must be on the dock. Without an initial pose Nav2's
  # lifecycle manager gives up after 60 s waiting for the map frame.
  LOCALIZATION_PARAMS="$LOGDIR/localization.yaml"
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] python3 $DELIVERY_DIR/tools/make_localization_params.py --route $ROUTE_DIR/route.yaml --base $DELIVERY_DIR/config/localization_delivery.yaml --out $LOCALIZATION_PARAMS"
  else
    python3 "$DELIVERY_DIR/tools/make_localization_params.py" --route "$ROUTE_DIR/route.yaml"       --base "$DELIVERY_DIR/config/localization_delivery.yaml" --out "$LOCALIZATION_PARAMS" || die "cannot write $LOCALIZATION_PARAMS"
  fi
  launch_bg stack ros2 launch "$STACK_LAUNCH" map:="$ROUTE_DIR/map.yaml" keepout_mask:="$ROUTE_DIR/keepout_mask.yaml"     speed_mask:="$ROUTE_DIR/speed_mask.yaml" localization_params:="$LOCALIZATION_PARAMS" nav2_params:="$NAV2_PARAMS"
fi

echo
echo "Logs and state: $LOGDIR"
echo "TB-25 reminder: do not start other ROS programs now (no ros2 commands, do not connect TurtleBot Studio)."
echo "Wait for a steady /odom first. delivery_mission.py waits for that by itself."
echo "Check the logs for 'Managed nodes are active' (grep -i 'managed nodes' $LOGDIR/*.log); that is not a ROS command."
echo "Stop everything with: bash $SCRIPT_DIR/stop_stack.sh"
