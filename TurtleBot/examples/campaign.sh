#!/bin/bash
# Run a list of motion programs one after the other, with a sensor report before and after, all logged.
#
# THIS SCRIPT MOVES THE ROBOT (it runs motion_shapes.py / more_shapes.py commands). Undock first, clear
# 1 m all round, stay next to the robot. Every command gets --yes added (there is nobody to answer), so you
# confirm the safety checklist by starting the campaign.
#
# Commands come from a file (one per line, "#" comments and blank lines ignored), or the DEFAULT list below:
#     motion_shapes.py square --side 0.3
#     more_shapes.py star
# Each line is run as  python3 <this folder>/<line> --yes  (with --dry-run too if you pass --dry-run here).
# The campaign stops at the first command that exits non-zero (safety abort, setup failure, stop by you).
#
# Run it on the robot, detached so a Wi-Fi drop does not matter:
#     bash ~/robot_code/campaign.sh --dry-run                       # all commands as dry runs, nothing moves
#     setsid nohup bash ~/robot_code/campaign.sh > /dev/null 2>&1 &
#     setsid nohup bash ~/robot_code/campaign.sh my_list.txt > /dev/null 2>&1 &
#     tail -f ~/robot_code/logs/campaign_*.log                    # the newest log
# How to stop it: touch ~/STOP (the running program stops the robot, the campaign stops; then rm ~/STOP),
#     or  pkill -TERM -f campaign.sh  (the campaign passes it on to the running program, which stops the
#     robot). Use -TERM, not -INT: a script started in the background from another script ignores SIGINT.
# Exit code: 0 all done, otherwise the exit code of the command that failed (130 = stopped by you).

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${LOG_DIR:-$HOME/robot_code/logs}"
STOP_FILE="$HOME/STOP"
PAUSE=5                 # s between commands
COMMAND_TIMEOUT=360     # s, outer limit per command (the programs have their own, shorter timeouts)
REPORT_SECONDS=10       # s of sensor_report before and after

DEFAULT_COMMANDS=(
  "motion_shapes.py rotate"
  "motion_shapes.py square --side 0.3"
  "more_shapes.py polygon --sides 6 --side 0.25"
  "more_shapes.py star --side 0.3"
  "more_shapes.py circle --radius 0.25"
  "more_shapes.py zigzag --legs 4 --side 0.25"
)

DRY=""
LIST=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY="--dry-run" ;;
    -h|--help) sed -n '2,/^$/p' "$0"; exit 0 ;;
    *) LIST="$a" ;;
  esac
done

# ROS environment (the same as motion_test.sh); harmless if already sourced.
[ -f /etc/turtlebot4/setup.bash ] && source /etc/turtlebot4/setup.bash >/dev/null 2>&1

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/campaign_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1     # everything below goes to the screen (if any) and the log
say(){ echo "$(date +%T) $*"; }

COMMANDS=()
if [ -n "$LIST" ]; then
  if [ ! -f "$LIST" ]; then say "command list $LIST not found"; exit 2; fi
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"; line="$(echo "$line" | xargs)"
    [ -n "$line" ] && COMMANDS+=("$line")
  done < "$LIST"
else
  COMMANDS=("${DEFAULT_COMMANDS[@]}")
fi
if [ "${#COMMANDS[@]}" -eq 0 ]; then say "no commands to run"; exit 2; fi
for c in "${COMMANDS[@]}"; do
  prog="${c%% *}"
  case "$prog" in
    motion_shapes.py|more_shapes.py) ;;
    *) say "REFUSING: only motion_shapes.py and more_shapes.py commands are allowed, not: $c"; exit 2 ;;
  esac
  [ -f "$DIR/$prog" ] || { say "REFUSING: $DIR/$prog not found"; exit 2; }
done

CHILD=""
on_stop(){
  say "campaign: stop signal received"
  # SIGTERM, not SIGINT: background jobs of a script may ignore SIGINT. timeout passes it on to the
  # program, which stops the robot exactly as for Ctrl+C.
  [ -n "$CHILD" ] && kill -TERM "$CHILD" 2>/dev/null && wait "$CHILD"
  say "campaign stopped by you"; exit 130
}
trap on_stop INT TERM

report(){
  say "---- sensor report ($1) ----"
  timeout -s INT $((REPORT_SECONDS + 60)) python3 "$DIR/sensor_report.py" --seconds "$REPORT_SECONDS" \
    --json "${LOG%.log}_$1.json" || say "sensor_report failed (exit $?)"
}

say "campaign log: $LOG"
say "host $(hostname), ${#COMMANDS[@]} command(s)${DRY:+, DRY RUN}:"
for c in "${COMMANDS[@]}"; do say "  $c"; done
if [ -f "$STOP_FILE" ] && [ -z "$DRY" ]; then say "REFUSING: $STOP_FILE exists. rm $STOP_FILE"; exit 2; fi
report before

code=0
i=0
for c in "${COMMANDS[@]}"; do
  i=$((i + 1))
  if [ -f "$STOP_FILE" ] && [ -z "$DRY" ]; then say "$STOP_FILE exists, stopping the campaign"; code=130; break; fi
  say "==== [$i/${#COMMANDS[@]}] python3 $c --yes $DRY ===="
  # shellcheck disable=SC2086  # word splitting of the command line is intended
  timeout -s INT "$COMMAND_TIMEOUT" python3 "$DIR"/$c --yes $DRY &
  CHILD=$!
  wait "$CHILD"
  code=$?
  CHILD=""
  say "==== [$i/${#COMMANDS[@]}] exit code $code ===="
  if [ "$code" -ne 0 ]; then say "stopping the campaign at the first failure"; break; fi
  [ "$i" -lt "${#COMMANDS[@]}" ] && sleep "$PAUSE"
done

report after
if [ "$code" -eq 0 ]; then say "campaign done: all ${#COMMANDS[@]} command(s) succeeded"
else say "campaign stopped: command $i exited with $code"; fi
say "log: $LOG"
exit "$code"
