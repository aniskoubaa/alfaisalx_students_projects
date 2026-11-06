#!/bin/bash
# Closed-loop mapping + delivery simulation ON THE ROBOT, with the robot sitting on its dock and fully isolated from the
# real base. Same fake base and guards as run_e2e.sh, but the map is NOT handed over: the fake robot maps the route.
#   1. fake_base.py (fake Create 3 + lidar + the /wall_follow action) and the REAL slam_toolbox
#      (ros2 launch turtlebot4_navigation slam.launch.py sync:=false, exactly as robot/start_stack.sh map)
#   2. undock, then wall-follow with /wall_follow goals of 10 s (as the real controller does); at the glass room
#      opening the goal is cancelled and the robot drives across with /cmd_vel at 0.2 m/s (a person would do that);
#      at the pickup X turn round, wall-follow back to about 0.8 m from the dock, dock
#   3. the REAL robot/save_map.sh saves the map, SLAM is stopped, the saved map is checked (size, wall in the right place)
#   4. a route spec for tools/plan_route.py is built on the SLAM map (the SLAM frame starts at the dock, so the hall
#      coordinates are shifted by the dock pose; keepout lines over the glass room opening and the glass doors)
#   5. the REAL stack (delivery_stack.launch.py) and delivery_mission.py run on that SLAM map; analyse_run.py judges it
# Log in to the robot with ssh first (see delivery/README.md, Connecting). Never uses sudo.
#
#   bash run_mapping.sh [--keep] [--dry-run]
#
# --keep     keep the big generated files (hall map copy, ROS logs) in the run folder
# --dry-run  print what would be done; start nothing and write nothing
# The last line is 'E2E mapping: PASS (<run folder>)' or 'E2E mapping: FAIL (<run folder>)'.
#
# ISOLATION: exactly as run_e2e.sh. Everything runs with ROS_DOMAIN_ID=$SIM_DOMAIN (default 77); the script refuses to
# start when that is empty or 0 and checks every process it starts. Discovery is forced to this computer
# (ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST) and a discovery server setting is dropped. Nothing is written outside the
# run folder ~/robot_code/logs/delivery/sim_<time>_mapping/ (and /tmp). The real ~/STOP file is honoured.
# The real robot is never driven: the 0.2 m/s of the fake wall follower and of the /cmd_vel crossing go to the fake base.
#
# Environment knobs: SIM_DOMAIN (77), SIM_GOAL_X (25, pickup spot in m; use 40 to also cross the glass room opening),
# SIM_ACTIVE_WAIT (150, s for 'Managed nodes are active'), SIM_TOTAL_TIMEOUT (1800, s for the mission),
# SIM_MAP_TIMEOUT (900, s for the mapping drive), SIM_SLAM_WAIT (90, s for slam_toolbox to publish /map),
# SIM_RUN_DIR (override the run folder, must be under ~/robot_code/logs/delivery or /tmp), SIM_DRIFT (odometry error,
# for example 0.02 = 2 %; default none, the fake odometry is then perfect), SIM_MAP_ONLY=1 (stop after the map check, no
# delivery), SIM_SLAM_PARAMS (another slam_toolbox yaml, to compare settings).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELIVERY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NAV2_PARAMS="$DELIVERY_DIR/config/nav2_delivery.yaml"
SLAM_PARAMS="${SIM_SLAM_PARAMS:-$DELIVERY_DIR/config/slam_delivery.yaml}"
STACK_LAUNCH="$DELIVERY_DIR/launch/delivery_stack.launch.py"
# A background job of a non-interactive shell ignores SIGINT; this wrapper restores it (same as start_stack.sh).
RESET_INT='import os, signal, sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execvp(sys.argv[1], sys.argv[1:])'

SIM_DOMAIN="${SIM_DOMAIN:-77}"
GOAL_X="${SIM_GOAL_X:-25}"
ACTIVE_WAIT="${SIM_ACTIVE_WAIT:-150}"
TOTAL_TIMEOUT="${SIM_TOTAL_TIMEOUT:-1800}"
MAP_TIMEOUT="${SIM_MAP_TIMEOUT:-900}"
SLAM_WAIT="${SIM_SLAM_WAIT:-90}"

usage() { sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "ERROR: $*" >&2; exit 1; }

KEEP=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

# ---- the domain guard: used before anything is started and again before every process
guard() {
  if ! [[ "${ROS_DOMAIN_ID:-}" =~ ^[0-9]+$ ]] || [ "$((10#$ROS_DOMAIN_ID))" -eq 0 ]; then
    die "REFUSING: ROS_DOMAIN_ID is '${ROS_DOMAIN_ID:-}' (unset, not a number or 0). The simulator must never run in domain 0, the real robot's domain."
  fi
}
export ROS_DOMAIN_ID="$SIM_DOMAIN"
guard

PRESS="pickup:3,handoff:4"; EXPECT=0

RUN="${SIM_RUN_DIR:-$HOME/robot_code/logs/delivery/sim_$(date +%Y%m%d_%H%M%S)_mapping}"
ROUTE="$RUN/route"
MAP_PREFIX="$RUN/slam_map/map"
TOOLS="$RUN/mapping_tools.py"

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

if [ "$DRY" = 1 ]; then
  echo "(dry run) closed-loop mapping scenario, expected mission exit code $EXPECT, ROS_DOMAIN_ID=$ROS_DOMAIN_ID (guard passed)"
  echo "(dry run) run folder: $RUN"
  echo "[dry-run] source /etc/turtlebot4/setup.bash (if ros2 is not on the PATH), then ROS_DOMAIN_ID=$ROS_DOMAIN_ID, ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST, unset ROS_DISCOVERY_SERVER, ROS_LOG_DIR=$RUN/roslog"
  echo "[dry-run] python3 $SCRIPT_DIR/sim_map.py --out $RUN/src --goal-x $GOAL_X --pickup-timeout 600 --leg-timeout 600"
  echo "[dry-run] write $TOOLS (helper: drive, check-map, make-spec, check-gt)"
  echo "[dry-run] setsid nohup python3 $SCRIPT_DIR/fake_base.py --map $RUN/src/route_map.yaml --glass @$RUN/sim_world.json --dock-pose <dock of the hall> --run-dir $RUN/mapping_gt --scan-when-docked > $RUN/fake_base_map.log &"
  echo "[dry-run] setsid nohup ros2 launch turtlebot4_navigation slam.launch.py sync:=false > $RUN/slam.log &"
  echo "[dry-run] python3 $TOOLS drive --world $RUN/sim_world.json --goal-x $GOAL_X --timeout $MAP_TIMEOUT --slam-wait $SLAM_WAIT --out $RUN/mapping_drive.json"
  echo "[dry-run]    (waits for /map, /undock, then /wall_follow goals of 10 s; cancel + /cmd_vel 0.2 m/s across the glass room opening; turn round; wall-follow back to about 0.8 m from the dock; /dock)"
  echo "[dry-run] timeout 240 bash $DELIVERY_DIR/robot/save_map.sh $MAP_PREFIX   (the real save_map.sh: /slam_toolbox/save_map)"
  echo "[dry-run] stop slam and the mapping fake base (SIGINT, SIGTERM, SIGKILL on their process groups)"
  echo "[dry-run] python3 $TOOLS check-map --map $MAP_PREFIX.yaml --world $RUN/sim_world.json --goal-x $GOAL_X"
  echo "[dry-run] python3 $TOOLS check-gt --gt $RUN/mapping_gt/ground_truth.jsonl --world $RUN/sim_world.json"
  echo "[dry-run] python3 $TOOLS make-spec --src $RUN/src/route_spec.yaml --world $RUN/sim_world.json --out $RUN/slam_spec.yaml   (hall coordinates minus the dock pose)"
  echo "[dry-run] python3 $DELIVERY_DIR/tools/plan_route.py --map $MAP_PREFIX.yaml --spec $RUN/slam_spec.yaml --out $ROUTE   (preview.html is copied to $RUN/preview.html)"
  echo "[dry-run] setsid nohup python3 $SCRIPT_DIR/fake_base.py --map $RUN/src/route_map.yaml --glass @$RUN/sim_world.json --dock-pose <dock of the hall> --run-dir $RUN --press $PRESS --scan-when-docked > $RUN/fake_base.log &"
  echo "[dry-run] setsid nohup ros2 launch $STACK_LAUNCH map:=$ROUTE/map.yaml keepout_mask:=$ROUTE/keepout_mask.yaml speed_mask:=$ROUTE/speed_mask.yaml localization_params:=$RUN/localization.yaml nav2_params:=$NAV2_PARAMS > $RUN/nav2.log &"
  echo "[dry-run] wait up to $ACTIVE_WAIT s for 'Managed nodes are active' in nav2.log; sample top every 30 s into $RUN/top.log"
  echo "[dry-run] python3 $DELIVERY_DIR/delivery_mission.py --route $ROUTE/route.yaml --yes --log-dir $RUN/mission_log > $RUN/mission.out   (timeout $TOTAL_TIMEOUT s)"
  echo "[dry-run] stop every process group with SIGINT, then SIGTERM; python3 $SCRIPT_DIR/analyse_run.py --run-dir $RUN --expect-exit $EXPECT"
  echo "[dry-run] last line: E2E mapping: PASS or FAIL"
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
export SIM_DIR="$SCRIPT_DIR"
guard

mkdir -p "$RUN" "$RUN/roslog" "$RUN/slam_map" || die "cannot create $RUN"
export ROS_LOG_DIR="$RUN/roslog"
{
  echo "scenario: mapping (closed loop)"; echo "started: $(date '+%F %T %z')"; echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
  echo "goal_x: $GOAL_X"; echo "expected mission exit code: $EXPECT"
} > "$RUN/state.txt"
echo "run folder: $RUN"

PIDS=(); NAMES=(); SAMPLER_PID=""; CLEANED=0; WATCH_PID=""; LAST_PID=""; WATCH_RC=1

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

start_bg() {   # start_bg NAME CMD... : own session, log in the run folder; the pid is in LAST_PID
  local name="$1"; shift
  guard
  setsid nohup python3 -c "$RESET_INT" "$@" > "$RUN/$name.log" 2>&1 < /dev/null &
  local pid=$!
  LAST_PID="$pid"
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

stop_named() {   # stop_named PID : stop one of our processes now and forget it
  local pid="$1" i
  stop_group "$pid"
  for ((i=0; i<${#PIDS[@]}; i++)); do
    if [ "${PIDS[$i]}" = "$pid" ]; then
      kill -0 "$pid" 2>/dev/null && echo "WARNING: ${NAMES[$i]} (pid $pid) is still running" >&2
      PIDS[i]=""
    fi
  done
}

cleanup() {
  [ "$CLEANED" = 1 ] && return
  CLEANED=1
  trap '' INT TERM
  echo "stopping everything ..."
  [ -n "$SAMPLER_PID" ] && { kill "$SAMPLER_PID" 2>/dev/null; pkill -P "$SAMPLER_PID" 2>/dev/null; }
  [ -n "$WATCH_PID" ] && stop_group "$WATCH_PID"
  local i
  for ((i=${#PIDS[@]}-1; i>=0; i--)); do [ -n "${PIDS[$i]}" ] && stop_group "${PIDS[$i]}"; done
  # nothing of ours may be left running
  for ((i=0; i<${#PIDS[@]}; i++)); do
    [ -n "${PIDS[$i]}" ] && kill -0 "${PIDS[$i]}" 2>/dev/null && echo "WARNING: ${NAMES[$i]} (pid ${PIDS[$i]}) is still running" >&2
  done
  echo "stopped: $(date '+%F %T %z')" >> "$RUN/state.txt"
}
trap cleanup EXIT
trap 'echo "interrupted"; cleanup; echo "E2E mapping: FAIL ($RUN)"; exit 130' INT TERM

bail() {   # bail MESSAGE : stop everything, print the verdict line, exit 1
  echo "ERROR: $*" >&2
  echo "FAIL reason: $*" >> "$RUN/state.txt"
  cleanup
  echo "E2E mapping: FAIL ($RUN)"
  trap - EXIT
  exit 1
}

alive_check() {   # every process we still own must be running
  local i
  for ((i=0; i<${#PIDS[@]}; i++)); do
    [ -n "${PIDS[$i]}" ] || continue
    kill -0 "${PIDS[$i]}" 2>/dev/null || { echo "ERROR: ${NAMES[$i]} died; see $RUN/${NAMES[$i]}.log" >&2; tail -n 15 "$RUN/${NAMES[$i]}.log" >&2; return 1; }
  done
}

run_watched() {   # run_watched LABEL OUTFILE TIMEOUT CMD... : one program in its own session; exit code in WATCH_RC
  local label="$1" out="$2" limit="$3"; shift 3
  guard
  setsid nohup python3 -c "$RESET_INT" "$@" > "$out" 2>&1 < /dev/null &
  WATCH_PID=$!
  verify_domain "$WATCH_PID" "$label" || { cleanup; exit 1; }
  local start=$SECONDS nextnote=60 el
  while kill -0 "$WATCH_PID" 2>/dev/null; do
    sleep 2
    el=$((SECONDS - start))
    if [ "$el" -ge "$nextnote" ]; then echo "$(date +%T) $label running for $el s: $(tail -n 1 "$out" | cut -c1-100)"; nextnote=$((nextnote + 60)); fi
    if [ -e "$HOME/STOP" ]; then echo "$HOME/STOP appeared: stopping $label"; kill -s INT "$WATCH_PID" 2>/dev/null; fi
    if [ "$el" -ge "$limit" ]; then echo "total timeout $limit s: stopping $label"; kill -s INT "$WATCH_PID" 2>/dev/null; fi
    alive_check || { echo "stopping $label" >&2; kill -s INT "$WATCH_PID" 2>/dev/null; }
  done
  wait "$WATCH_PID"; WATCH_RC=$?
  WATCH_PID=""
}

# ---- the hall, the helper
python3 "$SCRIPT_DIR/sim_map.py" --out "$RUN/src" --goal-x "$GOAL_X" --pickup-timeout 600 --leg-timeout 600 || bail "sim_map.py failed"
cp "$RUN/src/sim_world.json" "$RUN/sim_world.json"
DOCK_POSE="$(python3 -c "import json, sys; d = json.load(open(sys.argv[1]))['dock_pose']; print('%s,%s,%s' % (d['x'], d['y'], d['yaw']))" "$RUN/sim_world.json")" \
  || bail "cannot read the dock pose from sim_world.json"

cat > "$TOOLS" <<'MAPPING_TOOLS_PY'
#!/usr/bin/env python3
"""Helper of run_mapping.sh (written into the run folder by the script). Subcommands:
  drive      drive the fake robot along the wall with /wall_follow goals while slam_toolbox maps (needs ROS 2)
  check-map  sanity check of the saved SLAM map (size, enough walls, the south wall where the dock-origin frame says)
  make-spec  shift the hall's route spec into the SLAM frame (origin = dock pose)
  check-gt   the mapping drive must not have bumped into anything or entered the glass room
Pure functions (next_action, shift_spec, map_report, gt_report) are imported by the offline tests.
It only talks to the fake base in the simulator domain; it refuses to run in domain 0."""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.environ.get('SIM_DIR') or os.path.dirname(os.path.abspath(__file__)))

APPROACH_M = 2.0        # m, stop wall-following this far before the glass room opening
PAST_M = 1.5            # m, drive this far past the far edge of the opening before wall-following again
CROSS_SPEED = 0.2       # m/s, crossing the opening by /cmd_vel
CROSS_MOVE_OUT_YAW = 0.12   # rad, heading away from the wall at the start of a crossing
CROSS_MOVE_OUT_M = 2.5  # m of travel at that heading: about 0.3 m further from the wall
TURN_RATE = 0.5         # rad/s, turning round in place
GOAL_RUNTIME_S = 10     # s, max_runtime of every /wall_follow goal (as the real controller does)
HOME_DISTANCE_M = 0.8   # m, the wall-follow back ends this far from the dock (/dock works within 1.0 m)
MAX_LEG_STEPS = 20
WALL_ROW_BAND_M = 0.15  # m, the south wall must have occupied cells within this band around the line fitted through it
WALL_SEARCH_M = 1.2     # m, how far from the expected y a wall cell is looked for
WALL_FIT_OUTLIER_M = 0.3   # m, cells this far from the first fit are left out of the second
WALL_AT_DOCK_M = 0.3    # m, the fitted wall must be this close to its expected y at the dock
MAX_TILT_DEG = 5.0      # a map more tilted than this is not a small heading error of the SLAM frame
MIN_WALL_FRACTION = 0.8
MIN_OCC_CELLS, MIN_FREE_CELLS = 300, 3000
END_WALL_WINDOW_M = 8.0     # m around the expected end wall where along_wall_report looks
END_WALL_TOLERANCE_M = 0.5  # m, the end wall may be this far off (the dock is close, so it should be very near)
GHOST_WALL_M = 0.4          # m, a second wall further than this from the first is a copy, not a thick wall
ROOM_TOLERANCE_M = 1.0      # m, the glass room may be this far off (after about 25 m of plain wall)
WALL_COLUMN_FRACTION = 0.3  # of the rows: a map column with this many occupied cells is a wall across them
ROOM_COLUMN_FRACTION = 0.5
STOP_FILE = os.path.expanduser('~/STOP')


# ---------------------------------------------------------------- pure functions
def next_action(x, d, target, room):
    """What to do next on a leg that travels in direction d (+1 = +x, -1 = -x) from x to target, with the glass room
    room = (x0, y0, x1, y1) in between? Returns ('follow', stop_x), ('cross', finish_x) or ('done', target).
    Wall-follow up to APPROACH_M before the room, drive across it, wall-follow on. Same coordinates for all."""
    lo, hi = room[0], room[2]
    trig, fin = (lo - APPROACH_M, hi + PAST_M) if d > 0 else (hi + APPROACH_M, lo - PAST_M)
    s, st, sf, star = d * x, d * trig, d * fin, d * target
    if star <= s:
        return 'done', target
    if star < st:
        return 'follow', target
    if s < st:
        return 'follow', trig
    if s < sf:
        return 'cross', fin
    return 'follow', target


def goal_problem(goal_x, room):
    """None when the pickup spot can be reached by this plan, else why not."""
    if room[0] - 1.0 < goal_x < room[2] + PAST_M + 0.5:
        return f'goal x {goal_x} lies in or next to the glass room (x {room[0]} to {room[2]})'
    return None


def shift_spec(spec, dx, dy, tilt_deg=0.0):
    """The hall's route spec in the SLAM frame, whose origin is the dock pose (dx, dy; the dock yaw must be 0). The hall
    walls lie tilt_deg from the SLAM x axis (the map's own measure, map_report), so everything is rotated by that."""
    cos_t, sin_t = math.cos(math.radians(tilt_deg)), math.sin(math.radians(tilt_deg))

    def pt(p):
        x_, y_ = float(p[0]) - dx, float(p[1]) - dy
        return [round(x_ * cos_t - y_ * sin_t, 6), round(x_ * sin_t + y_ * cos_t, 6)]

    def xy(d):
        out = dict(d)
        out['x'], out['y'] = pt((d['x'], d['y']))
        if 'yaw' in d and tilt_deg:
            out['yaw'] = round(float(d['yaw']) + tilt_deg, 6)
        return out

    out = dict(spec)
    dock = dict(spec['dock_pose'])
    if abs(float(dock.get('yaw', 0.0))) > 1e-9:
        raise ValueError('only a dock yaw of 0 is supported (the hall is shifted, not rotated)')
    out['dock_pose'] = xy(dock)
    for key in ('start', 'goal'):
        if key in spec:
            out[key] = xy(spec[key])
    if spec.get('via'):
        out['via'] = [xy(v) for v in spec['via']]
    if spec.get('keepout_lines'):
        out['keepout_lines'] = [dict(ln, **{'from': pt(ln['from']), 'to': pt(ln['to'])}) for ln in spec['keepout_lines']]
    if spec.get('keepout_polygons'):
        out['keepout_polygons'] = [dict(pg, points=[pt(p) for p in pg['points']]) for pg in spec['keepout_polygons']]
    if spec.get('slow_zones'):
        zones = []
        for z in spec['slow_zones']:
            z = dict(z)
            if 'points' in z:
                z['points'] = [pt(p) for p in z['points']]
            if 'center' in z:
                z['center'] = pt(z['center'])
            zones.append(z)
        out['slow_zones'] = zones
    return out


def skip_ranges(world):
    """x ranges (hall coordinates) where the south wall is not in the map: the glass room and the glass doors."""
    rngs = [(world['glass_room'][0], world['glass_room'][2])]
    for x1, _y1, x2, _y2 in world['glass_segments']:
        rngs.append((min(x1, x2), max(x1, x2)))
    return rngs


def map_report(w, h, res, ox, oy, pix, world, goal_x):
    """Judge a saved SLAM map (pixel values: 0 occupied, 254 free, 205 unknown) against the known hall. The map frame
    starts at the dock. Returns (problems, numbers); no problems means sane."""
    dock_x, dock_y = world['dock_pose']['x'], world['dock_pose']['y']
    n_occ = sum(1 for p in pix if p < 100)
    n_free = sum(1 for p in pix if p >= 240)
    ex, ey = w * res, h * res
    problems = []
    num = {'width_cells': w, 'height_cells': h, 'resolution': res, 'extent_m': [round(ex, 1), round(ey, 1)],
           'origin': [ox, oy], 'occupied_cells': n_occ, 'free_cells': n_free}
    gdx = goal_x - dock_x
    if not (gdx + 2.0 <= ex <= 100.0):
        problems.append(f'map is {ex:.1f} m wide; expected between {gdx + 2.0:.1f} and 100 m')
    if not (3.0 <= ey <= 40.0):
        problems.append(f'map is {ey:.1f} m high; expected between 3 and 40 m')
    if not (ox < 0.0 < ox + ex and oy < 0.0 < oy + ey):
        problems.append('the map does not contain its own origin (the dock)')
    if n_occ < MIN_OCC_CELLS:
        problems.append(f'only {n_occ} occupied cells (need {MIN_OCC_CELLS})')
    if n_free < MIN_FREE_CELLS:
        problems.append(f'only {n_free} free cells (need {MIN_FREE_CELLS})')
    # the south wall (hall y = 0) must be where the dock-origin frame puts it: y = -dock_y
    # A SLAM frame follows the robot's heading at the start, so the wall may be tilted a little: fit a line to it.
    wall_y = world.get('wall_y', 0.0) - dock_y
    skips = skip_ranges(world)
    columns, points = [], []
    x = 2.0
    while x <= gdx - 2.0:
        if not any(a - dock_x - 0.3 <= x <= b - dock_x + 0.3 for a, b in skips):
            col = int(math.floor((x - ox) / res))
            near = []
            y = wall_y - WALL_SEARCH_M
            while y <= wall_y + WALL_SEARCH_M + 1e-9:
                row = h - 1 - int(math.floor((y - oy) / res))
                if 0 <= col < w and 0 <= row < h and pix[row * w + col] < 100:
                    near.append(y)
                y += res
            columns.append((x, near))
            if near:
                points.append((x, min(near, key=lambda v: abs(v - wall_y))))
        x += res
    slope, at_dock = fit_line(points) if len(points) >= 2 else (0.0, wall_y)
    good = sum(1 for cx, near in columns if any(abs(v - (at_dock + slope * cx)) <= WALL_ROW_BAND_M for v in near))
    frac = good / len(columns) if columns else 0.0
    num['wall_fraction'] = round(frac, 3)
    num['wall_tilt_deg'] = round(math.degrees(math.atan(slope)), 2)
    num['wall_y_at_dock'] = round(at_dock, 2)
    if frac < MIN_WALL_FRACTION:
        problems.append(f'the south wall is a straight line in only {frac * 100:.0f} % of the columns '
                        f'(need {MIN_WALL_FRACTION * 100:.0f} %): the map is bent or broken')
    elif abs(at_dock - wall_y) > WALL_AT_DOCK_M:
        problems.append(f'the south wall is at y {at_dock:.2f} at the dock, expected {wall_y:.2f}: '
                        'the map frame is not where the dock-origin assumption says')
    if abs(num['wall_tilt_deg']) > MAX_TILT_DEG:
        problems.append(f'the south wall is tilted {num["wall_tilt_deg"]} degrees (limit {MAX_TILT_DEG})')
    return problems, num


def fit_line(points):
    """Least squares through (x, y) points, with one pass that drops outliers. Returns (slope, y at x = 0)."""
    def ls(pts):
        n = len(pts)
        mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
        den = sum((p[0] - mx) ** 2 for p in pts)
        b = sum((p[0] - mx) * (p[1] - my) for p in pts) / den if den else 0.0
        return b, my - b * mx
    b, a = ls(points)
    kept = [p for p in points if abs(p[1] - (a + b * p[0])) <= WALL_FIT_OUTLIER_M]
    return ls(kept) if len(kept) >= 2 else (b, a)


def wall_columns(w, h, res, ox, oy, pix, y0, y1):
    """(count of occupied cells per map column between y0 and y1, number of rows looked at)."""
    r0, r1 = h - 1 - int(math.floor((y1 - oy) / res)), h - 1 - int(math.floor((y0 - oy) / res))
    r0, r1 = max(r0, 0), min(r1, h - 1)
    counts = [0] * w
    for r in range(r0, r1 + 1):
        row = pix[r * w:(r + 1) * w]
        for c in range(w):
            if row[c] < 100:
                counts[c] += 1
    return counts, max(r1 - r0 + 1, 0)


def along_wall_report(w, h, res, ox, oy, pix, world, goal_x):
    """Are distances ALONG the wall right? A scan matcher on a long plain wall can shrink the map in that direction, and
    map_report's check of the wall's y position cannot see that. Measures the hall's end wall (hall x = 0), any second
    copy of it, and the glass room's west wall when the route passes it. Returns (problems, numbers)."""
    dock_x, dock_y = world['dock_pose']['x'], world['dock_pose']['y']
    problems, num = [], {}
    expected = -dock_x
    counts, rows = wall_columns(w, h, res, ox, oy, pix, 1.0 - dock_y, 5.0 - dock_y)
    window = [c for c in range(w) if abs(ox + (c + 0.5) * res - expected) <= END_WALL_WINDOW_M]
    if not rows or not window or max(counts[c] for c in window) < WALL_COLUMN_FRACTION * rows:
        problems.append(f'no end wall found near x {expected:.2f}')
    else:
        peak = max(window, key=lambda c: counts[c])
        peak_x = ox + (peak + 0.5) * res
        num['end_wall_x'] = round(peak_x, 2)
        if abs(peak_x - expected) > END_WALL_TOLERANCE_M:
            problems.append(f'the end wall is at x {peak_x:.2f}, expected {expected:.2f}: the map is wrong along the wall')
        ghosts = sorted(round(ox + (c + 0.5) * res, 1) for c in window if counts[c] >= WALL_COLUMN_FRACTION * rows
                        and abs(ox + (c + 0.5) * res - peak_x) > GHOST_WALL_M)
        if ghosts:
            num['ghost_end_walls'] = ghosts
            problems.append(f'a second end wall at x {ghosts[0]}: the map slipped along the wall on the way back')
    room = world['glass_room']
    if goal_x > room[2]:
        counts, rows = wall_columns(w, h, res, ox, oy, pix, room[1] + 0.5 - dock_y, room[3] - 0.5 - dock_y)
        expected = room[0] - dock_x
        first = next((c for c in range(w) if rows and counts[c] >= ROOM_COLUMN_FRACTION * rows
                      and ox + (c + 0.5) * res > 0.0), None)
        if first is None:
            problems.append('the glass room is not in the map')
        else:
            room_x = ox + (first + 0.5) * res
            num['room_x'] = round(room_x, 2)
            if abs(room_x - expected) > ROOM_TOLERANCE_M:
                problems.append(f'the glass room starts at x {room_x:.2f}, expected {expected:.2f}: '
                                'the map is wrong along the wall')
    return problems, num


def gt_report(samples, events, world):
    """The mapping drive's ground truth: no BUMP, never inside the glass room. Returns (problems, numbers)."""
    x0, y0, x1, y1 = world['glass_room']
    inside = [s for s in samples if x0 < s['x'] < x1 and y0 < s['y'] < y1]
    bumps = [e for e in events if e.get('event') == 'hazard' and e.get('type') == 'BUMP']
    goals = [e for e in events if e.get('event') == 'wall_follow_goal' and e.get('started')]
    problems = []
    if bumps:
        problems.append(f'{len(bumps)} BUMP during mapping, first at ({bumps[0].get("x")}, {bumps[0].get("y")})')
    if inside:
        problems.append(f'{len(inside)} samples inside the glass room, first at ({inside[0]["x"]}, {inside[0]["y"]})')
    return problems, {'wall_follow_goals': len(goals), 'bumps': len(bumps), 'samples': len(samples),
                      'max_speed': round(max((s['speed'] for s in samples), default=0.0), 3)}


# ---------------------------------------------------------------- subcommands without ROS
def load_world(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def cmd_check_map(a):
    import yaml
    import fake_base
    world = load_world(a.world)
    with open(a.map, 'r', encoding='utf-8') as fh:
        info = yaml.safe_load(fh)
    img = str(info['image'])
    img = img if os.path.isabs(img) else os.path.join(os.path.dirname(os.path.abspath(a.map)), img)
    w, h, pix = fake_base.read_pgm(img)
    problems, num = map_report(w, h, float(info['resolution']), float(info['origin'][0]), float(info['origin'][1]), pix,
                               world, a.goal_x)
    more, numbers = along_wall_report(w, h, float(info['resolution']), float(info['origin'][0]), float(info['origin'][1]),
                                      pix, world, a.goal_x)
    problems += more
    num.update(numbers)
    print('SLAM map: ' + json.dumps(num))
    for p in problems:
        print('PROBLEM: ' + p)
    print('SLAM map check: ' + ('FAIL' if problems else 'PASS'))
    return 1 if problems else 0


def cmd_make_spec(a):
    import yaml
    world = load_world(a.world)
    with open(a.src, 'r', encoding='utf-8') as fh:
        spec = yaml.safe_load(fh)
    out = shift_spec(spec, float(world['dock_pose']['x']), float(world['dock_pose']['y']), a.tilt_deg)
    with open(a.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('# Route spec on the SLAM map: the hall spec shifted by the dock pose (SLAM frame origin = dock) and\n'
                 f'# rotated by the tilt of the wall measured in that map ({a.tilt_deg} degrees).\n')
        yaml.safe_dump(out, fh, sort_keys=False, default_flow_style=None)
    print(f'wrote {a.out}: dock {out["dock_pose"]}, goal {out["goal"]}, {len(out.get("keepout_lines", []))} keepout lines, '
          f'tilt {a.tilt_deg} degrees')
    return 0


def cmd_check_gt(a):
    import analyse_run
    world = load_world(a.world)
    samples, events = analyse_run.load_log(a.gt)
    problems, num = gt_report(samples, events, world)
    print('mapping drive ground truth: ' + json.dumps(num))
    for p in problems:
        print('PROBLEM: ' + p)
    if not num['wall_follow_goals']:
        problems.append('no /wall_follow goal was ever accepted')
        print('PROBLEM: no /wall_follow goal was ever accepted')
    print('mapping drive check: ' + ('FAIL' if problems else 'PASS'))
    return 1 if problems else 0


# ---------------------------------------------------------------- the drive (ROS 2)
class Abort(Exception):
    pass


def cmd_drive(a):
    import fake_base
    problem = fake_base.domain_problem(os.environ)
    if problem:
        print(f'REFUSING TO START: {problem}', file=sys.stderr)
        return 2
    world = load_world(a.world)
    room = world['glass_room']
    dock_x = float(world['dock_pose']['x'])
    bad = goal_problem(a.goal_x, room)
    if bad:
        print('REFUSING: ' + bad, file=sys.stderr)
        return 2
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from builtin_interfaces.msg import Duration
    from geometry_msgs.msg import TwistStamped
    from irobot_create_msgs.action import Dock, Undock, WallFollow
    from irobot_create_msgs.msg import DockStatus, HazardDetectionVector
    from nav_msgs.msg import OccupancyGrid, Odometry

    t_start = time.monotonic()
    log_lines = []

    def say(text):
        line = f'{time.strftime("%H:%M:%S")} {text}'
        print(line, flush=True)
        log_lines.append(line)

    class Driver(Node):
        def __init__(self):
            super().__init__('mapping_driver')
            self.ox = self.oy = self.oyaw = 0.0
            self.have_odom = False
            self.odom_t = 0.0
            self.docked = None
            self.got_map = False
            self.bumps = 0
            self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
            self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)
            self.create_subscription(HazardDetectionVector, '/hazard_detection', self.on_haz, qos_profile_sensor_data)
            self.create_subscription(OccupancyGrid, '/map', self.on_map,
                                     QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                                                durability=DurabilityPolicy.TRANSIENT_LOCAL))
            self.cmd_pub = self.create_publisher(TwistStamped, '/cmd_vel', qos_profile_sensor_data)
            self.undock_c = ActionClient(self, Undock, '/undock')
            self.dock_c = ActionClient(self, Dock, '/dock')
            self.wf_c = ActionClient(self, WallFollow, '/wall_follow')

        def on_odom(self, m):
            self.ox, self.oy = m.pose.pose.position.x, m.pose.pose.position.y
            q = m.pose.pose.orientation
            self.oyaw = math.atan2(2 * q.w * q.z, 1 - 2 * q.z * q.z)
            self.have_odom, self.odom_t = True, time.monotonic()

        def on_dock(self, m):
            self.docked = bool(m.is_docked)

        def on_haz(self, m):
            for d in m.detections:
                if d.type == 1:   # HazardDetection.BUMP
                    self.bumps += 1

        def on_map(self, m):
            self.got_map = True

        @property
        def x(self):   # hall x of the robot (the odometry starts at the dock pose, dock yaw 0)
            return dock_x + self.ox

    rclpy.init()
    node = Driver()
    state = {'x_max': -1e9, 'x_min': 1e9, 'goals': 0}

    def spin(sec=0.05):
        rclpy.spin_once(node, timeout_sec=sec)
        state['x_max'] = max(state['x_max'], node.x)
        state['x_min'] = min(state['x_min'], node.x)

    def check():
        if os.path.exists(STOP_FILE):
            raise Abort('~/STOP exists')
        if time.monotonic() - t_start > a.timeout:
            raise Abort(f'total timeout of {a.timeout} s')
        if node.bumps:
            raise Abort('the fake base reported a BUMP')
        if node.have_odom and time.monotonic() - node.odom_t > 5.0:
            raise Abort('no /odom for 5 s')

    def wait_for(pred, limit, what):
        t0 = time.monotonic()
        while not pred():
            spin()
            check()
            if time.monotonic() - t0 > limit:
                raise Abort(f'timeout ({limit} s) waiting for {what}')

    def wait_future(fut, limit, what):
        wait_for(fut.done, limit, what)
        return fut.result()

    def publish(v, w):
        m = TwistStamped()
        m.header.stamp = node.get_clock().now().to_msg()
        m.header.frame_id = 'base_link'
        m.twist.linear.x, m.twist.angular.z = float(v), float(w)
        node.cmd_pub.publish(m)

    def hold_still(sec=0.6):
        t0 = time.monotonic()
        while time.monotonic() - t0 < sec:
            publish(0.0, 0.0)
            spin(0.05)

    def reached(d, stop_x):
        return d * (node.x - stop_x) >= 0

    def follow_until(d, stop_x):
        side = -d   # heading +x: the wall is on the right (-1); heading -x: on the left (+1)
        while not reached(d, stop_x):
            check()
            goal = WallFollow.Goal()
            goal.follow_side = side
            goal.max_runtime = Duration(sec=GOAL_RUNTIME_S, nanosec=0)
            gh = wait_future(node.wf_c.send_goal_async(goal), 10, '/wall_follow goal answer')
            if not gh.accepted:
                raise Abort('/wall_follow goal was rejected')
            state['goals'] += 1
            res_fut = gh.get_result_async()
            t0 = time.monotonic()
            while not res_fut.done():
                spin()
                check()
                if reached(d, stop_x) or time.monotonic() - t0 > GOAL_RUNTIME_S + 5:
                    wait_future(gh.cancel_goal_async(), 5, 'goal cancel')
                    wait_future(res_fut, 5, 'goal result after cancel')
                    break
        hold_still(1.0)
        say(f'wall follow reached x={node.x:.2f} (wanted {stop_x:.2f}, direction {d:+d}), {state["goals"]} goals so far')

    def cross(d, finish_x):
        yaw0 = node.oyaw
        limit = abs(finish_x - node.x) / CROSS_SPEED * 1.5 + 10
        say(f'crossing the glass room opening by /cmd_vel at {CROSS_SPEED} m/s from x={node.x:.2f} to {finish_x:.2f}')
        t0 = time.monotonic()
        x0 = node.x
        while not reached(d, finish_x):
            check()
            if time.monotonic() - t0 > limit:
                raise Abort('crossing took too long')
            # Wall-follow keeps the robot only 0.3 m from the wall. Move out first, to about 0.6 m, as a person would: with
            # odometry error a straight line from 0.3 m touches the glass front (measured with SIM_DRIFT=0.02).
            away = d * CROSS_MOVE_OUT_YAW if abs(node.x - x0) < CROSS_MOVE_OUT_M else 0.0
            err = math.atan2(math.sin(yaw0 + away - node.oyaw), math.cos(yaw0 + away - node.oyaw))
            publish(CROSS_SPEED, max(-0.3, min(0.3, 2.0 * err)))   # forward: the robot already faces direction d
            spin(0.1)
        hold_still(1.0)

    def turn_round():
        say('turning round in place')
        total, last = 0.0, node.oyaw
        t0 = time.monotonic()
        while total < math.pi - 0.12:
            check()
            if time.monotonic() - t0 > 40:
                raise Abort('turning round took too long')
            publish(0.0, TURN_RATE)
            spin(0.1)
            total += math.atan2(math.sin(node.oyaw - last), math.cos(node.oyaw - last))
            last = node.oyaw
        hold_still(1.0)

    def leg(d, target):
        for _ in range(MAX_LEG_STEPS):
            kind, at = next_action(node.x, d, target, room)
            if kind == 'done':
                return
            if kind == 'follow':
                follow_until(d, at)
            else:
                cross(d, at)
        raise Abort('leg did not finish in the planned number of steps')

    ok, reason = False, ''
    try:
        say(f'mapping drive: goal x {a.goal_x}, dock x {dock_x}, glass room {room}')
        wait_for(lambda: node.have_odom and node.docked is not None, 60, '/odom and /dock_status')
        for client, name in ((node.undock_c, '/undock'), (node.wf_c, '/wall_follow'), (node.dock_c, '/dock')):
            wait_for(lambda c=client: c.server_is_ready(), 60, f'action server {name}')
        wait_for(lambda: node.got_map and any(n == '/slam_toolbox/save_map' for n, _t in node.get_service_names_and_types()),
                 a.slam_wait, 'slam_toolbox (/map and /slam_toolbox/save_map)')
        say('slam_toolbox is up (map published, save_map service present)')
        if not node.docked:
            raise Abort('the robot is not docked at the start')
        gh = wait_future(node.undock_c.send_goal_async(Undock.Goal()), 10, '/undock answer')
        if not gh.accepted:
            raise Abort('/undock rejected')
        wait_future(gh.get_result_async(), 60, '/undock result')
        wait_for(lambda: node.docked is False, 10, 'dock_status undocked')
        hold_still(1.5)
        say(f'undocked at x={node.x:.2f}')
        leg(+1, a.goal_x)
        say(f'reached the pickup spot (x={node.x:.2f})')
        turn_round()
        leg(-1, dock_x + HOME_DISTANCE_M)
        dist = math.hypot(node.ox, node.oy)
        say(f'about {dist:.2f} m from the dock, docking')
        gh = wait_future(node.dock_c.send_goal_async(Dock.Goal()), 10, '/dock answer')
        if not gh.accepted:
            raise Abort('/dock rejected')
        wait_future(gh.get_result_async(), 150, '/dock result')
        wait_for(lambda: node.docked is True, 30, 'dock_status docked')
        say('docked again')
        hold_still(6.0)   # let slam_toolbox take its last scans and publish the map
        ok = True
    except Abort as e:
        reason = str(e)
        say(f'ABORT: {reason}')
    except KeyboardInterrupt:
        reason = 'interrupted'
        say('interrupted')
    finally:
        try:
            for _ in range(5):
                publish(0.0, 0.0)
                rclpy.spin_once(node, timeout_sec=0.05)
        except Exception:   # noqa: BLE001 - shutting down
            pass
        with open(a.out, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump({'ok': ok, 'reason': reason, 'wall_follow_goals': state['goals'], 'x_max': round(state['x_max'], 2),
                       'x_min': round(state['x_min'], 2), 'bumps': node.bumps, 'seconds': round(time.monotonic() - t_start, 1),
                       'log': log_lines}, fh, indent=1)
        node.destroy_node()
        rclpy.try_shutdown()
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description='Helper of run_mapping.sh.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('drive')
    p.add_argument('--world', required=True)
    p.add_argument('--goal-x', type=float, required=True)
    p.add_argument('--timeout', type=float, default=900.0)
    p.add_argument('--slam-wait', type=float, default=90.0)
    p.add_argument('--out', required=True)
    p = sub.add_parser('check-map')
    p.add_argument('--map', required=True)
    p.add_argument('--world', required=True)
    p.add_argument('--goal-x', type=float, required=True)
    p = sub.add_parser('make-spec')
    p.add_argument('--src', required=True)
    p.add_argument('--world', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--tilt-deg', type=float, default=0.0, help='tilt of the wall in the SLAM map (check-map prints it)')
    p = sub.add_parser('check-gt')
    p.add_argument('--gt', required=True)
    p.add_argument('--world', required=True)
    a = ap.parse_args(argv)
    return {'drive': cmd_drive, 'check-map': cmd_check_map, 'make-spec': cmd_make_spec, 'check-gt': cmd_check_gt}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
MAPPING_TOOLS_PY

# ---- 1. the fake base and the real slam_toolbox (same command as robot/start_stack.sh map)
# --scan-when-docked: start_stack.sh turns the real lidar motor on first, so the sim publishes /scan while docked too.
DRIFT_ARGS=()
[ -n "${SIM_DRIFT:-}" ] && DRIFT_ARGS=(--drift "$SIM_DRIFT")
start_bg fake_base_map python3 "$SCRIPT_DIR/fake_base.py" --map "$RUN/src/route_map.yaml" --glass "@$RUN/sim_world.json" \
  --dock-pose "$DOCK_POSE" --run-dir "$RUN/mapping_gt" --scan-when-docked "${DRIFT_ARGS[@]}"
FAKE_MAP_PID="$LAST_PID"
sleep 6
kill -0 "$FAKE_MAP_PID" 2>/dev/null || { tail -n 20 "$RUN/fake_base_map.log" >&2; bail "fake_base.py did not start (see $RUN/fake_base_map.log)"; }
( while true; do { date +%T; top -b -n1 | head -n 12; } >> "$RUN/top.log" 2>&1; sleep 30; done ) &
SAMPLER_PID=$!
start_bg slam ros2 launch turtlebot4_navigation slam.launch.py sync:=false params:="$SLAM_PARAMS"
SLAM_PID="$LAST_PID"

# ---- 2. the mapping drive
echo "$(date +%T) mapping drive (goal x $GOAL_X, timeout $MAP_TIMEOUT s)"
run_watched mapping_drive "$RUN/mapping_drive.log" "$((MAP_TIMEOUT + 60))" \
  python3 "$TOOLS" drive --world "$RUN/sim_world.json" --goal-x "$GOAL_X" --timeout "$MAP_TIMEOUT" --slam-wait "$SLAM_WAIT" --out "$RUN/mapping_drive.json"
tail -n 6 "$RUN/mapping_drive.log"
[ "$WATCH_RC" = 0 ] || { tail -n 15 "$RUN/slam.log" >&2; bail "the mapping drive failed (exit $WATCH_RC, see $RUN/mapping_drive.log)"; }

# ---- 3. save the map with the REAL save_map.sh, then stop slam and the mapping fake base
echo "$(date +%T) saving the map with robot/save_map.sh"
timeout 240 bash "$DELIVERY_DIR/robot/save_map.sh" "$MAP_PREFIX" > "$RUN/save_map.log" 2>&1
SAVE_RC=$?
tail -n 8 "$RUN/save_map.log"
echo "save_map_exit: $SAVE_RC" >> "$RUN/state.txt"
stop_named "$SLAM_PID"
stop_named "$FAKE_MAP_PID"
if [ "$SAVE_RC" != 0 ] || [ ! -f "$MAP_PREFIX.yaml" ] || [ ! -f "$MAP_PREFIX.pgm" ]; then bail "save_map.sh failed (exit $SAVE_RC, see $RUN/save_map.log)"; fi
ls -l "$MAP_PREFIX".* 2>/dev/null
python3 "$TOOLS" check-gt --gt "$RUN/mapping_gt/ground_truth.jsonl" --world "$RUN/sim_world.json" > "$RUN/check_gt.log" 2>&1; CHECK_RC=$?
cat "$RUN/check_gt.log"
[ "$CHECK_RC" = 0 ] || bail "the mapping drive hit something (see above)"
python3 "$TOOLS" check-map --map "$MAP_PREFIX.yaml" --world "$RUN/sim_world.json" --goal-x "$GOAL_X" > "$RUN/check_map.log" 2>&1; CHECK_RC=$?
cat "$RUN/check_map.log"
[ "$CHECK_RC" = 0 ] || bail "the saved SLAM map is not sane (see above)"
if [ "${SIM_MAP_ONLY:-0}" = 1 ]; then
  cleanup
  echo "E2E mapping: PASS, map only ($RUN)"
  trap - EXIT
  exit 0
fi

# ---- 4. route spec on the SLAM map, then plan_route.py on it
TILT_DEG="$(sed -n 's/.*"wall_tilt_deg": \([-0-9.]*\).*/\1/p' "$RUN/check_map.log" | head -n 1)"
python3 "$TOOLS" make-spec --src "$RUN/src/route_spec.yaml" --world "$RUN/sim_world.json" --tilt-deg "${TILT_DEG:-0}" --out "$RUN/slam_spec.yaml" || bail "make-spec failed"
python3 "$DELIVERY_DIR/tools/plan_route.py" --map "$MAP_PREFIX.yaml" --spec "$RUN/slam_spec.yaml" --out "$ROUTE" > "$RUN/plan_route.log" 2>&1 \
  || { cat "$RUN/plan_route.log" >&2; bail "plan_route.py failed on the SLAM map"; }
tail -n 4 "$RUN/plan_route.log"
cp "$ROUTE/preview.html" "$RUN/preview.html" 2>/dev/null || echo "WARNING: no preview.html in $ROUTE" >&2

# ---- 5. the real delivery on the SLAM map (same commands as run_e2e.sh; the hall is the ground truth, the dock is the odometry origin)
guard
start_bg fake_base python3 "$SCRIPT_DIR/fake_base.py" --map "$RUN/src/route_map.yaml" --glass "@$RUN/sim_world.json" \
  --dock-pose "$DOCK_POSE" --run-dir "$RUN" --press "$PRESS" --scan-when-docked --map-at-dock "${DRIFT_ARGS[@]}"
FAKE_PID="$LAST_PID"
sleep 6
kill -0 "$FAKE_PID" 2>/dev/null || { tail -n 20 "$RUN/fake_base.log" >&2; bail "fake_base.py did not start (see $RUN/fake_base.log)"; }
python3 "$DELIVERY_DIR/tools/make_localization_params.py" --route "$ROUTE/route.yaml" --base "$DELIVERY_DIR/config/localization_delivery.yaml" --out "$RUN/localization.yaml" \
  || bail "cannot write $RUN/localization.yaml"
start_bg nav2 ros2 launch "$STACK_LAUNCH" map:="$ROUTE/map.yaml" keepout_mask:="$ROUTE/keepout_mask.yaml" speed_mask:="$ROUTE/speed_mask.yaml" localization_params:="$RUN/localization.yaml" nav2_params:="$NAV2_PARAMS"

echo "waiting up to $ACTIVE_WAIT s for 'Managed nodes are active' ..."
active=0
for ((t=0; t<ACTIVE_WAIT; t+=2)); do
  if grep -q "Managed nodes are active" "$RUN/nav2.log" 2>/dev/null; then active=1; break; fi
  alive_check || bail "a process died while Nav2 started"
  [ -e "$HOME/STOP" ] && bail "$HOME/STOP appeared, stopping"
  sleep 2
done
if [ "$active" = 1 ]; then
  echo "Nav2 reports: Managed nodes are active"
else
  echo "WARNING: no 'Managed nodes are active' after $ACTIVE_WAIT s. Continuing; if the mission cannot reach Nav2 it will refuse and this run fails." >&2
fi
echo "active_seen: $active" >> "$RUN/state.txt"

guard
echo "$(date +%T) starting delivery_mission.py"
run_watched mission "$RUN/mission.out" "$TOTAL_TIMEOUT" \
  python3 "$DELIVERY_DIR/delivery_mission.py" --route "$ROUTE/route.yaml" --yes --log-dir "$RUN/mission_log"
CODE="$WATCH_RC"
echo "$CODE" > "$RUN/mission_exit.txt"
echo "mission exit code: $CODE (expected $EXPECT)"
sleep 2

cleanup

# ---- judge
python3 "$SCRIPT_DIR/analyse_run.py" --run-dir "$RUN" --expect-exit "$EXPECT" --scenario mapping
RC=$?
if [ "$KEEP" = 0 ]; then rm -rf "$RUN/roslog" "$RUN/src"; fi
if [ "$RC" = 0 ]; then echo "E2E mapping: PASS ($RUN)"; else echo "E2E mapping: FAIL ($RUN)"; fi
trap - EXIT
exit "$RC"
