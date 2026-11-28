#!/usr/bin/env python3
"""TurtleBot Studio robot bridge: JSON lines on stdin/stdout between the desktop app and the robot (spec TB-27 sec. 1 and 2).

ONE self-contained file (stdlib + rclpy), streamed over ssh at connect time, nothing is installed on the robot:
    ssh ... "source /etc/turtlebot4/setup.bash >/dev/null 2>&1; exec python3 -u -c \\
      \\"import sys;b=sys.stdin.buffer;n=int(b.readline());exec(compile(b.read(n).decode(),'robot_bridge','exec'))\\""
then the desktop writes "<len>\\n" + these bytes, then command lines. Started that way there is no __file__ and
sys.argv is ['-c'], so nothing here depends on either; the mode comes from the environment:
    STUDIO_BRIDGE_FAKE=1   force fake mode (no ROS, simulated data) even without --fake
    STUDIO_BRIDGE_HOME=dir home directory used for ~, ~/STOP and ~/robot_code/logs (default: real home; in fake mode
                           a fresh temporary directory), for tests.
Direct use for development:  python3 robot_bridge.py [--fake]   (commands on stdin, events on stdout)

Protocol (one JSON object per line). Command: {"id":1,"cmd":"ping",...}. Every command gets exactly one
{"ev":"reply","id":1,"ok":true|false,"error":"..",...}. Everything else is an unsolicited event (hello, status, msg,
run_output, run_exit, action). Diagnostics go to stderr. Times: "t" = time.monotonic() of the robot, "wall" = time.time()
(may be years wrong on the robot).

Safety: the only velocity this program ever publishes is zero (estop) and, since Studio 2.0, bounded manual driving
("teleop"): it needs teleop_arm first, is clamped here to 0.30 m/s and 1.20 rad/s (and to the limits Studio passes), stops
300 ms after the last command, and is disarmed by e-stop, the ~/STOP file, docking, a running motion program, 60 s
without non-zero commands and by this bridge ending. It starts no motion by itself: "run" of a motion
program needs confirmed=true, undock/dock need confirmed=true, and a ~/STOP file blocks them. Runs are detached
(own session), so they survive the bridge; logs in ~/robot_code/logs/. CPU: raw (undeserialised) subscriptions, the
scan is evaluated only at the status period, nmcli/systemctl results are cached for 10 s.
"""
import argparse
import base64
import collections
import hashlib
import json
import math
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

VERSION = "1"
MOTION_REGEX = (r"motion_shapes\.py|drive_test\.py|motion_test\.sh|more_shapes\.py|wall_approach\.py|"
                r"keep_distance\.py|campaign\.sh")
MAX_MSG_BYTES = 16 * 1024
MAX_ARRAY = 32
MAX_WATCHES = 4
SLOW_EVERY = 10.0           # s, nmcli / systemctl / vcgencmd cache
HAZARD_WINDOW = 2.0         # s
FRONT_HALF_DEG = 15.0
BODY_MIN_M = 0.15
SCAN_YAW_DEFAULT = math.pi / 2          # lidar mounted at +90 deg yaw (used when TF is not available)
FAKE_TOPICS = [
    ("/odom", "nav_msgs/msg/Odometry", 1, 3), ("/battery_state", "sensor_msgs/msg/BatteryState", 1, 2),
    ("/dock_status", "irobot_create_msgs/msg/DockStatus", 1, 2), ("/scan", "sensor_msgs/msg/LaserScan", 1, 2),
    ("/hazard_detection", "irobot_create_msgs/msg/HazardDetectionVector", 1, 2),
    ("/wheel_status", "irobot_create_msgs/msg/WheelStatus", 1, 2), ("/imu", "sensor_msgs/msg/Imu", 1, 2),
    ("/cmd_vel", "geometry_msgs/msg/TwistStamped", 0, 2), ("/ip", "std_msgs/msg/String", 1, 1),
    ("/hmi/display", "turtlebot4_msgs/msg/UserDisplay", 1, 1),
    ("/diagnostics_toplevel_state", "diagnostic_msgs/msg/DiagnosticStatus", 1, 1), ("/tf", "tf2_msgs/msg/TFMessage", 3, 4),
]
TELEOP_MAX_LINEAR = 0.30    # m/s, hard cap of manual driving (the lab programs use 0.15)
TELEOP_MAX_ANGULAR = 1.20   # rad/s
TELEOP_WATCHDOG_S = 0.30    # no teleop message for this long -> zero velocity, once
TELEOP_IDLE_S = 60.0        # armed but no non-zero command for this long -> disarm
TELEOP_ARM_MIN_PCT = 10     # arming is refused when the battery is known and below this percent
TELEOP_STOP_PCT = 8         # an armed session is disarmed when the battery drops below this percent
JOURNAL_UNITS = ("turtlebot4.service", "NetworkManager.service", "ssh.service", "systemd-timesyncd.service",
                 "chrony.service")
JOURNAL_SINCE = ("10 min ago", "1 hour ago", "6 hours ago", "1 day ago", "boot")
JOURNAL_LINE_MAX = 600
HAZARD_NAMES = {0: "backup_limit", 1: "bump", 2: "cliff", 3: "stall", 4: "wheel_drop", 5: "object_proximity"}
