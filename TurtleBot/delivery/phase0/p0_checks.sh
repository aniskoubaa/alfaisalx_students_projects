#!/bin/bash
# Phase 0, Part A: read-only checks A1 to A9 of the delivery Phase 0 checklist, with the robot docked.
# Runs ON THE ROBOT (log in with ssh first; see delivery/README.md, Connecting). Changes nothing, never uses sudo,
# publishes nothing, does not move the robot.
#
#   bash p0_checks.sh [--interactive] [--dry-run]
#
# --interactive  also run A7 (press front-panel buttons 3 and 4 when asked; NEVER press 1 or 2) and A8 (/joy:
#                move a stick of the TurtleBot 4 controller when asked). Without it these two are SKIP.
# --dry-run      print the commands that would run, run nothing, write no report.
#
# TB-25: every ros2 command is a new ROS participant and can stall the base for several seconds. The ros2 commands
# run one at a time, each with a timeout, and the script pauses 10 s between them. Expect 5 to 10 minutes.
# Report: ~/robot_code/logs/delivery/p0_checks_<date-time>.txt (every command, its output, and the verdicts).
# Verdicts: PASS = matches the checklist, CHECK = look at it yourself, FAIL = a Stop-if condition of the checklist,
# SKIP = not run. Exit code 1 if any FAIL.

PAUSE="${DELIVERY_PAUSE:-10}"   # seconds between ros2 commands (TB-25); the variable is for tests only
ROS_TIMEOUT=60                 # seconds for a topic echo
BASE_LOG_URL="http://192.168.186.2/logs-raw"
LOG_ROOT="$HOME/robot_code/logs/delivery"

die() { echo "ERROR: $*" >&2; exit 1; }
INTERACTIVE=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --interactive) INTERACTIVE=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

if ! command -v ros2 >/dev/null 2>&1 && [ "$DRY" = 0 ]; then
  # shellcheck disable=SC1091
  [ -f /etc/turtlebot4/setup.bash ] && source /etc/turtlebot4/setup.bash >/dev/null 2>&1
  command -v ros2 >/dev/null 2>&1 || die "ros2 not found"
fi

REPORT="$LOG_ROOT/p0_checks_$(date +%Y%m%d_%H%M%S).txt"
if [ "$DRY" = 0 ]; then mkdir -p "$LOG_ROOT" || die "cannot create $LOG_ROOT"; : > "$REPORT"; fi
SUMMARY=()      # lines "ID STATUS what | expected | got"
OUT=""          # output of the last run_cmd

note() { echo "$*"; if [ "$DRY" = 0 ]; then echo "$*" >> "$REPORT"; fi; }

# run_cmd SECONDS CMD... : run with a timeout (SIGINT first so ros2 prints what it has), keep the output in $OUT.
run_cmd() {
  local secs="$1"; shift
  if [ "$DRY" = 1 ]; then echo "[dry-run] timeout -s INT $secs $*"; OUT=""; return 0; fi
  note ""
  note "--- $(date +%T) \$ $*"
  OUT="$(timeout -s INT "$secs" "$@" 2>&1 < /dev/null)"
  local rc=$?
  printf '%s\n' "$OUT" >> "$REPORT"
  note "(exit code $rc)"
  return $rc
}

# run_sh SECONDS 'shell pipeline' : same for a pipeline (written as one string).
run_sh() {
  local secs="$1" cmd="$2"
  if [ "$DRY" = 1 ]; then echo "[dry-run] timeout -s INT $secs bash -c '$cmd'"; OUT=""; return 0; fi
  note ""
  note "--- $(date +%T) \$ $cmd"
  OUT="$(timeout -s INT "$secs" bash -c "$cmd" 2>&1 < /dev/null)"
  local rc=$?
  printf '%s\n' "$OUT" >> "$REPORT"
  note "(exit code $rc)"
  return $rc
}

ros_pause() { if [ "$DRY" = 1 ]; then echo "[dry-run] wait $PAUSE s"; else sleep "$PAUSE"; fi; }

# verdict ID STATUS WHAT EXPECTED GOT
verdict() {
  local line
  line="$(printf '%-3s %-5s %s | expected: %s | got: %s' "$1" "$2" "$3" "$4" "$5")"
  SUMMARY+=("$line")
  if [ "$DRY" = 0 ]; then note "VERDICT $line"; fi
}

# num_ok VALUE OP LIMIT : floating point comparison with awk (OP is lt, le, gt, ge)
num_ok() {
  awk -v a="$1" -v b="$3" -v op="$2" 'BEGIN{ if (a=="" ) exit 1;
    if(op=="lt") exit !(a+0<b+0); if(op=="le") exit !(a+0<=b+0); if(op=="gt") exit !(a+0>b+0); if(op=="ge") exit !(a+0>=b+0); exit 1}'
}

note "Phase 0, Part A checks, $(date '+%F %T %z'), host $(hostname 2>/dev/null)"
note "Robot must be docked. Nothing here changes anything."

# ---------------------------------------------------------------- A1 base health
run_cmd "$ROS_TIMEOUT" ros2 topic echo --once /dock_status
dock_out="$OUT"
if [ "$DRY" = 0 ]; then
  if echo "$dock_out" | grep -q "is_docked: true"; then verdict A1a PASS "/dock_status" "is_docked: true" "true"
  elif echo "$dock_out" | grep -q "is_docked: false"; then verdict A1a FAIL "/dock_status" "is_docked: true" "false (not docked)"
  else verdict A1a FAIL "/dock_status" "a message within ${ROS_TIMEOUT}s" "nothing (base not healthy?)"; fi
fi
ros_pause
run_cmd "$ROS_TIMEOUT" ros2 topic echo --once /battery_state
bat_out="$OUT"
if [ "$DRY" = 0 ]; then
  pct="$(echo "$bat_out" | awk '/^percentage:/{print $2; exit}')"
  cur="$(echo "$bat_out" | awk '/^current:/{print $2; exit}')"
  if [ -z "$pct" ]; then verdict A1b FAIL "/battery_state percentage" "above 0.5" "nothing"
  elif num_ok "$pct" gt 0.5; then verdict A1b PASS "/battery_state percentage" "above 0.5" "$pct"
  else verdict A1b CHECK "/battery_state percentage" "above 0.5" "$pct"; fi
  if num_ok "$cur" gt 0; then verdict A1c PASS "/battery_state current" "positive while charging" "$cur"
  else verdict A1c CHECK "/battery_state current" "positive while charging" "${cur:-nothing}"; fi
fi
run_sh 20 "curl -s --max-time 10 $BASE_LOG_URL | tail -n 20"
if [ "$DRY" = 0 ]; then
  last="$(echo "$OUT" | tail -n 1)"
  if [ -z "$OUT" ]; then verdict A1d FAIL "base log" "recent ongoing messages" "no answer from $BASE_LOG_URL"
  elif echo "$last" | grep -qi "configuring"; then verdict A1d FAIL "base log" "not ending at Configuring" "$last"
  else verdict A1d PASS "base log" "recent ongoing messages" "$last"; fi
fi
ros_pause

# ---------------------------------------------------------------- A2 clock
run_sh 20 'timedatectl | grep -E "Local time|synchronized"'
if [ "$DRY" = 0 ]; then
  if echo "$OUT" | grep -qi "synchronized: yes"; then verdict A2a PASS "clock synchronized" "yes (no is possible over the cable alone)" "yes"
  else verdict A2a CHECK "clock synchronized" "yes (no is possible over the cable alone)" "$(echo "$OUT" | grep -i synchronized)"; fi
  verdict A2b CHECK "local time" "today's date and time (robot time is EDT, UTC-4)" "$(echo "$OUT" | grep -i 'local time' | head -n 1)"
fi
now="$(date +%s)"
run_cmd "$ROS_TIMEOUT" ros2 topic echo --once /dock_status --field header.stamp
if [ "$DRY" = 0 ]; then
  stamp="$(echo "$OUT" | awk '/^sec:/{print $2; exit}')"
  if [ -z "$stamp" ]; then verdict A2c CHECK "base stamp vs date +%s" "sec within a few seconds of $now" "no stamp printed"
  else
    diff=$(( now > stamp ? now - stamp : stamp - now ))
    if [ "$diff" -le 5 ]; then verdict A2c PASS "base stamp vs date +%s" "within a few seconds" "differs by ${diff}s"
    elif [ "$diff" -le 60 ]; then verdict A2c CHECK "base stamp vs date +%s" "within a few seconds" "differs by ${diff}s"
    else verdict A2c FAIL "base stamp vs date +%s" "within a minute (do not fix; wait 20 min and check again)" "differs by ${diff}s"; fi
  fi
fi
ros_pause

# ---------------------------------------------------------------- A3 network, CPU, temperature, disk
run_sh 20 'nmcli -t -f NAME,DEVICE connection show --active'
if [ "$DRY" = 0 ]; then
  verdict A3a CHECK "active connection" "Students:wlan0, home Wi-Fi or the hotspot" "$(echo "$OUT" | tr '\n' ' ')"
fi
# shellcheck disable=SC2016  # the inner command substitution must reach the inner shell unexpanded
run_sh 20 'nmcli -g 802-11-wireless.powersave connection show "$(nmcli -t -f NAME,DEVICE connection show --active | grep ":wlan0$" | cut -d: -f1)"'
if [ "$DRY" = 0 ]; then
  if echo "$OUT" | grep -qiE "disable|^2$"; then verdict A3b PASS "Wi-Fi power save" "off (nmcli: disable)" "off"
  else verdict A3b CHECK "Wi-Fi power save" "off (nmcli: disable)" "${OUT:-nothing}"; fi
fi
run_sh 20 'uptime; vcgencmd measure_temp; free -m'
if [ "$DRY" = 0 ]; then
  load="$(echo "$OUT" | sed -n 's/.*load average[s]*: *\([0-9.]*\).*/\1/p' | head -n 1)"
  if num_ok "$load" lt 2; then verdict A3c PASS "load average (1 min)" "under 2 when idle" "$load"
  else verdict A3c CHECK "load average (1 min)" "under 2 when idle" "${load:-unknown}"; fi
  temp="$(echo "$OUT" | sed -n "s/.*temp=\([0-9.]*\).*/\1/p" | head -n 1)"
  if num_ok "$temp" lt 70; then verdict A3d PASS "temperature" "under 70 C on the dock" "$temp C"
  else verdict A3d CHECK "temperature" "under 70 C on the dock" "${temp:-unknown}"; fi
fi
run_sh 20 'df -h /home /tmp; df -BG --output=avail /home | tail -n 1'
if [ "$DRY" = 0 ]; then
  avail="$(echo "$OUT" | tail -n 1 | tr -dc '0-9')"
  if num_ok "$avail" ge 3; then verdict A3e PASS "free disk in /home" "several GB (mapping needs about 1 GB)" "${avail} GB"
  else verdict A3e CHECK "free disk in /home" "several GB (mapping needs about 1 GB)" "${avail:-unknown} GB"; fi
fi
run_sh 20 'pgrep -a unattended-upgrade || echo "no update job"'
if [ "$DRY" = 0 ]; then
  if echo "$OUT" | grep -q "no update job"; then verdict A3f PASS "update job" "no update job" "none"
  else verdict A3f CHECK "update job" "no update job" "$(echo "$OUT" | head -n 1)"; fi
fi
# [o]akd: the bracket stops grep from matching its own command line (pgrep -f matched this wrapper's text).
run_sh 20 'ps -eo pcpu,args | grep "[o]akd_container" | cut -c1-120 || true'
if [ "$DRY" = 0 ]; then
  if ! echo "$OUT" | grep -q "oakd_container"; then verdict A3g PASS "OAK-D process" "note whether one runs (it costs CPU)" "none running"
  else verdict A3g CHECK "OAK-D process" "note whether one runs (it costs CPU)" "running: $(echo "$OUT" | head -1 | cut -c1-40)"; fi
fi

# ---------------------------------------------------------------- A4 lidar
ros_pause
run_cmd 30 ros2 topic hz /scan
if [ "$DRY" = 0 ]; then
  rate="$(echo "$OUT" | awk '/average rate:/{r=$3} END{print r}')"
  if [ -z "$rate" ]; then verdict A4 CHECK "/scan rate" "about 7 to 8 Hz (or stopped on dock, TB-24)" "no messages (stopped on dock?)"
  elif num_ok "$rate" ge 6 && num_ok "$rate" le 9; then verdict A4 PASS "/scan rate" "about 7 to 8 Hz" "$rate Hz"
  else verdict A4 CHECK "/scan rate" "about 7 to 8 Hz" "$rate Hz"; fi
fi

# ---------------------------------------------------------------- A5 software installed
# shellcheck disable=SC2016  # the awk program is meant to reach the inner shell unexpanded
run_sh 30 'dpkg -l | grep -E "ros-jazzy-(slam-toolbox|nav2-bringup|nav2-route|turtlebot4-navigation) " | awk "{print \$2, \$3}"'
if [ "$DRY" = 0 ]; then
  miss=""
  for p in ros-jazzy-slam-toolbox ros-jazzy-nav2-bringup ros-jazzy-turtlebot4-navigation; do
    echo "$OUT" | grep -q "^$p " || miss="$miss $p"
  done
  if [ -z "$miss" ]; then verdict A5a PASS "packages" "slam-toolbox, nav2-bringup, turtlebot4-navigation" "all present"
  else verdict A5a FAIL "packages" "slam-toolbox, nav2-bringup, turtlebot4-navigation" "missing:$miss"; fi
  if echo "$OUT" | grep -q "^ros-jazzy-nav2-route "; then verdict A5b PASS "nav2-route (optional)" "optional" "present"
  else verdict A5b CHECK "nav2-route (optional)" "optional" "not installed"; fi
fi
run_sh 60 'ros2 bag --help > /dev/null && echo "ros2 bag OK"'
if [ "$DRY" = 0 ]; then
  if echo "$OUT" | grep -q "ros2 bag OK"; then verdict A5c PASS "ros2 bag" "ros2 bag OK" "OK"
  else verdict A5c CHECK "ros2 bag" "ros2 bag OK" "${OUT:-nothing}"; fi
fi

# ---------------------------------------------------------------- A6 button settings
CFG=/opt/ros/jazzy/share/turtlebot4_bringup/config/turtlebot4.yaml
run_sh 30 "find /opt/ros/jazzy/share/turtlebot4_bringup -name turtlebot4.yaml"
found="$(echo "$OUT" | head -n 1)"
[ -n "$found" ] && CFG="$found"
run_sh 20 "grep -n -A8 'buttons:' $CFG"
btn="$OUT"
run_sh 20 "grep -n -A14 'menu:' $CFG"
menu="$OUT"
run_sh 20 "grep -n -A10 'controller:' $CFG"
ctl="$OUT"
if [ "$DRY" = 0 ]; then
  ok=1
  for pair in "hmi_1:Select" "hmi_2:Back" "hmi_3:Scroll Up" "hmi_4:Scroll Down"; do
    echo "$btn" | grep -q "${pair%%:*}.*${pair#*:}" || ok=0
  done
  if [ "$ok" = 1 ]; then verdict A6a PASS "hmi_1..4 buttons" "Select, Back, Scroll Up, Scroll Down" "as upstream"
  else verdict A6a CHECK "hmi_1..4 buttons" "Select, Back, Scroll Up, Scroll Down" "differs or not found, see report (buttons 3 and 4 must only scroll)"; fi
  ok=1
  echo "$btn" | grep -q "create3_1.*Dock" || ok=0
  echo "$btn" | grep -q "create3_2.*Undock" || ok=0
  echo "$btn" | grep -qi "create3_power.*EStop" || ok=0
  if [ "$ok" = 1 ]; then verdict A6b PASS "create3 buttons" "Dock/Wall Follow Left; Undock/Wall Follow Right; EStop/Power" "as upstream"
  else verdict A6b CHECK "create3 buttons" "Dock/Wall Follow Left; Undock/Wall Follow Right; EStop/Power" "differs or not found, see report"; fi
  if echo "$ctl" | grep -q 'b:.*EStop' && echo "$ctl" | grep -qi 'l2' && echo "$ctl" | grep -qi 'r2' && echo "$ctl" | grep -qi 'home'; then
    verdict A6c PASS "controller" "b: EStop, l2/r2 wall follow, home dock/undock" "as upstream"
  else verdict A6c CHECK "controller" "b: EStop, l2/r2 wall follow, home dock/undock" "differs or not found, see report"; fi
  ok=1
  for e in "Dock" "Undock" "EStop" "Wall Follow Left" "Wall Follow Right" "Power" "Help"; do
    echo "$menu" | grep -q "$e" || ok=0
  done
  if [ "$ok" = 1 ]; then verdict A6d PASS "menu entries" "Dock, Undock, EStop, Wall Follow Left/Right, Power, Help" "all present"
  else verdict A6d CHECK "menu entries" "Dock, Undock, EStop, Wall Follow Left/Right, Power, Help" "some missing, see report"; fi
fi

# ---------------------------------------------------------------- A7 buttons and display (interactive)
if [ "$INTERACTIVE" = 1 ]; then
  ros_pause
  if [ "$DRY" = 0 ]; then
    echo
    echo "A7: within 30 s after the next line, press front-panel button 3 once and button 4 once."
    echo "    Do NOT press buttons 1 or 2 (button 1 is Select and runs the highlighted menu entry, e.g. Undock)."
    read -r -p "Press Enter, then press the buttons: " _x
  fi
  run_cmd 30 ros2 topic echo /hmi/buttons
  if [ "$DRY" = 0 ]; then
    # Each message is: button:\n- false\n- false\n- true\n- false\n---   ; look at element 3 and 4.
    seen="$(echo "$OUT" | awk '/^button:/{i=0; next} /^- /{i++; if($2=="true") p[i]=1} END{printf "%s%s", (p[3]?"3":""), (p[4]?"4":"")}')"
    if [ "$seen" = "34" ]; then verdict A7a PASS "/hmi/buttons" "a message for each press of 3 and 4" "3 and 4 seen"
    else verdict A7a CHECK "/hmi/buttons" "a message for each press of 3 and 4" "seen: ${seen:-none}"; fi
  fi
  ros_pause
  run_cmd 30 ros2 topic echo --once /hmi/display
  if [ "$DRY" = 0 ]; then
    if [ -n "$OUT" ]; then verdict A7b PASS "/hmi/display" "prints a message (note its fields)" "message printed"
    else verdict A7b CHECK "/hmi/display" "prints a message (note its fields)" "nothing in 30 s"; fi
  fi
else
  verdict A7 SKIP "buttons and display" "needs --interactive" "not run"
fi

# ---------------------------------------------------------------- A8 controller
run_sh 20 'bluetoothctl devices Paired'
if [ "$DRY" = 0 ]; then
  if [ -n "$OUT" ] && ! echo "$OUT" | grep -qi "not available\|no default controller\|not found"; then
    verdict A8a PASS "controller paired" "listed by name" "$(echo "$OUT" | head -n 1)"
  else verdict A8a CHECK "controller paired" "listed by name" "${OUT:-nothing}"; fi
fi
if [ "$INTERACTIVE" = 1 ]; then
  ros_pause
  if [ "$DRY" = 0 ]; then
    echo
    echo "A8: turn the controller on (round button), wait for a steady light, then move a stick while the next command waits."
    read -r -p "Press Enter to start the 30 s wait: " _x
  fi
  run_cmd 30 ros2 topic echo --once /joy
  if [ "$DRY" = 0 ]; then
    if [ -n "$OUT" ]; then verdict A8b PASS "/joy" "prints a message" "message printed"
    else verdict A8b CHECK "/joy" "prints a message" "nothing in 30 s"; fi
  fi
else
  verdict A8b SKIP "/joy" "needs --interactive" "not run"
fi

# ---------------------------------------------------------------- A9 HTTPS (optional)
run_sh 30 'curl -sS -o /dev/null -w "%{http_code}\n" --max-time 20 https://api.telegram.org'
if [ "$DRY" = 0 ]; then
  code="$(echo "$OUT" | tail -n 1)"
  if echo "$code" | grep -Eq '^[23][0-9][0-9]$'; then verdict A9 PASS "HTTPS to the internet (optional)" "a number such as 200 or 302" "$code"
  else verdict A9 CHECK "HTTPS to the internet (optional)" "a number such as 200 or 302" "${code:-no answer} (no phone message from the robot on this network)"; fi
fi

# ---------------------------------------------------------------- summary
if [ "$DRY" = 1 ]; then
  echo
  echo "[dry-run] done: nothing was run. Real run writes $LOG_ROOT/p0_checks_<date-time>.txt"
  exit 0
fi
echo
note "================ SUMMARY ================"
fails=0
for l in "${SUMMARY[@]}"; do
  note "$l"
  case "$l" in *" FAIL "*) fails=$((fails + 1)) ;; esac
done
note "FAIL: $fails. A FAIL on A1, A2 or A5 is a Stop-if condition of the checklist: bring the report back before going on."
note "Report: $REPORT"
if [ "$fails" -gt 0 ]; then exit 1; fi
exit 0
