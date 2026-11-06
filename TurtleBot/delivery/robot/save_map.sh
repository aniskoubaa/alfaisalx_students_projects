#!/bin/bash
# Save the map that slam_toolbox is building, plus its pose graph for a later mapping session.
# Runs ON THE ROBOT while start_stack.sh map is running (see delivery/README.md, Connecting). Never uses sudo.
#
#   bash save_map.sh OUTPUT_PREFIX [--force] [--dry-run]
#   example: bash save_map.sh ~/robot_code/maps/route1
#
# Writes OUTPUT_PREFIX.pgm and OUTPUT_PREFIX.yaml (the map) and OUTPUT_PREFIX.posegraph and .data (the pose graph).
# Steps, one ros2 command at a time, each with a timeout (TB-25: every ros2 command is a new ROS participant):
#   1. ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '<prefix>'}}"
#   2. if that gives no map: ros2 run nav2_map_server map_saver_cli -f <prefix>
#   3. ros2 service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph "{filename: '<prefix>'}"
# Verified 2026-11-06 on the robot against real slam_toolbox (sim/run_mapping.sh): both service calls returned result=0.
# Refuses to overwrite an existing <prefix>.yaml unless --force. The prefix must not contain quotes.

TIMEOUT=60   # seconds per ros2 command
die() { echo "ERROR: $*" >&2; exit 1; }

PREFIX=""; FORCE=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [ -z "$PREFIX" ] || die "only one output prefix allowed"; PREFIX="$1" ;;
  esac
  shift
done
[ -n "$PREFIX" ] || die "give the output path prefix, for example ~/robot_code/maps/route1"
case "$PREFIX" in *\'*|*\"*) die "the prefix must not contain quotes" ;; esac
case "$PREFIX" in /*|[A-Za-z]:*) ;; *) PREFIX="$PWD/$PREFIX" ;; esac   # absolute: slam_toolbox saves relative to ITS working directory
OUTDIR="$(dirname "$PREFIX")"

if ! command -v ros2 >/dev/null 2>&1 && [ "$DRY" = 0 ]; then
  # shellcheck disable=SC1091
  [ -f /etc/turtlebot4/setup.bash ] && source /etc/turtlebot4/setup.bash >/dev/null 2>&1
  command -v ros2 >/dev/null 2>&1 || die "ros2 not found"
fi

SAVE_ARGS=(service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '$PREFIX'}}")
SERIALIZE_ARGS=(service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph "{filename: '$PREFIX'}")

if [ "$DRY" = 1 ]; then
  echo "[dry-run] mkdir -p $OUTDIR"
  echo "[dry-run] timeout $TIMEOUT ros2 ${SAVE_ARGS[*]}"
  echo "[dry-run] if that gives no map: timeout $TIMEOUT ros2 run nav2_map_server map_saver_cli -f $PREFIX"
  echo "[dry-run] timeout $TIMEOUT ros2 ${SERIALIZE_ARGS[*]}"
  exit 0
fi

if [ -f "$PREFIX.yaml" ] && [ "$FORCE" = 0 ]; then die "$PREFIX.yaml exists (use --force to overwrite)"; fi
mkdir -p "$OUTDIR" || die "cannot create $OUTDIR"

SAVED=0
echo "$(date +%T) saving the map with slam_toolbox"
out="$(timeout "$TIMEOUT" ros2 "${SAVE_ARGS[@]}" 2>&1)"
echo "$out" | tail -n 3
if echo "$out" | grep -q "result=0" && [ -f "$PREFIX.yaml" ]; then SAVED=1; fi
if [ "$SAVED" = 0 ]; then
  echo "$(date +%T) slam_toolbox save_map gave no map; trying map_saver_cli"
  timeout "$TIMEOUT" ros2 run nav2_map_server map_saver_cli -f "$PREFIX" 2>&1 | tail -n 3
  if [ -f "$PREFIX.yaml" ]; then SAVED=1; fi
fi

echo "$(date +%T) serializing the pose graph"
timeout "$TIMEOUT" ros2 "${SERIALIZE_ARGS[@]}" 2>&1 | tail -n 3

echo
ls -l "$PREFIX".* 2>/dev/null
if [ "$SAVED" = 1 ]; then echo "Map saved: $PREFIX.yaml"; else echo "ERROR: no map file was written" >&2; exit 1; fi
if [ ! -f "$PREFIX.posegraph" ]; then echo "WARNING: no $PREFIX.posegraph (the pose graph was not saved; the map itself is fine)"; fi
exit 0
