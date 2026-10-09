#!/bin/bash
# Full movement test: undock, check the lidar, drive 20 cm only if the way is clear, dock again.
# Run on the robot:  bash ~/robot_code/motion_test.sh
source /etc/turtlebot4/setup.bash >/dev/null 2>&1
cd "$(dirname "$0")"
say(){ echo "$(date +%T) $*"; }

docked=$(timeout 60 ros2 topic echo --once /dock_status 2>/dev/null | awk '/is_docked/{print $2}')
say "Docked at start: ${docked:-unknown}"
if [ "$docked" != "false" ]; then
  say "Undocking"
  timeout 60 ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}" 2>&1 | grep -E "accepted|status" || say "undock: no answer"
fi

say "Waiting for the lidar to spin up"
sleep 8
python3 clearance_check.py 0.6
clear=$?

say "Lidar readings for 10 s:"
timeout -s INT 25 python3 scan_test.py 2>&1 | grep "Nearest" | head -5

if [ "$clear" -eq 0 ]; then
  say "Path is clear, driving forward 20 cm"
  timeout -s INT 40 python3 drive_test.py 2>&1 | tail -2
  say "Drive finished"
elif [ "$clear" -eq 1 ]; then
  say "Something is closer than 0.6 m in front, NOT driving"
else
  say "No lidar data, NOT driving"
fi

say "Spinning once on the spot (360 degrees, built-in rotate_angle action)"
timeout 60 ros2 action send_goal /rotate_angle irobot_create_msgs/action/RotateAngle "{angle: 6.283, max_rotation_speed: 0.6}" 2>&1 | grep -E "accepted|status" || say "rotate: no answer"

say "Docking"
timeout 120 ros2 action send_goal /dock irobot_create_msgs/action/Dock "{}" 2>&1 | grep -E "accepted|status" || say "dock: no answer"
docked=$(timeout 60 ros2 topic echo --once /dock_status 2>/dev/null | awk '/is_docked/{print $2}')
say "Docked at end: ${docked:-unknown}"
