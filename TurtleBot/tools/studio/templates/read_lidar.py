#!/usr/bin/env python3
"""Read the lidar and print the nearest thing ahead, left, right and behind the robot once a second.

MOVES THE ROBOT: no. It only listens. The lidar is OFF while the robot is on the dock, so undock first
(otherwise you will see "no scan yet").
Run it on the robot:      python3 read_lidar.py
How to stop it: Ctrl+C (it also ends by itself after SECONDS).
Change first: SECONDS, or HALF_ANGLE (how wide each direction is).

Why the angles are tricky: the lidar on this robot is bolted on turned by +90 degrees. A beam at laser angle a
points at robot angle a + 90 degrees. So straight ahead of the robot is laser angle -90 degrees. This program
asks TF (ROS's table of where every part is mounted) for that +90 and falls back to it if TF is silent.
Robot angles: 0 = ahead, +90 = left, -90 = right, 180 = behind.
"""
import math
import signal
import sys
import time

import rclpy
import tf2_ros
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from rclpy.time import Time
from sensor_msgs.msg import LaserScan

# ------------------------------------------------------------------ CONSTANTS (change these first)
SECONDS = 20                       # how long to run
HALF_ANGLE = math.radians(30)      # each direction covers +/- this angle around its centre
DIRECTIONS = {'ahead': 0, 'left': 90, 'behind': 180, 'right': -90}   # centre of each direction, robot degrees
FALLBACK_OFFSET = math.pi / 2      # lidar yaw if TF is missing (measured on this robot)

stop_requested = False


def on_signal(signum, frame):
    global stop_requested
    stop_requested = True


def wrap_angle(a):
    return math.atan2(math.sin(a), math.cos(a))      # e.g. 190 degrees becomes -170


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def nearest_in_direction(scan, offset, centre_deg, half_angle):
    """Nearest valid range within half_angle of a robot direction (inf if nothing is there)."""
    nearest = float('inf')
    for i, r in enumerate(scan.ranges):
        if not (scan.range_min < r < scan.range_max):    # skips inf, nan and out-of-range values
            continue
        robot_angle = scan.angle_min + i * scan.angle_increment + offset   # laser angle -> robot angle
        if abs(wrap_angle(robot_angle - math.radians(centre_deg))) <= half_angle:
            nearest = min(nearest, r)
    return nearest


class LidarReader(Node):
    def __init__(self):
        super().__init__('read_lidar')
        self.scan = None
        self.offset = None
        self.first_scan_time = None
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)   # fills the buffer from /tf
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

    def on_scan(self, msg):                  # ROS calls this for every scan (about 8 per second)
        self.scan = msg
        now = time.monotonic()
        self.first_scan_time = self.first_scan_time or now
        if self.offset is None:
            try:   # where is the lidar frame relative to the robot (base_link)?
                t = self.tf_buffer.lookup_transform('base_link', msg.header.frame_id, Time())
                self.offset = yaw_of(t.transform.rotation)
                print(f'lidar is turned {math.degrees(self.offset):.0f} degrees on the robot (from TF)')
            except tf2_ros.TransformException:
                if now - self.first_scan_time > 5.0:
                    self.offset = FALLBACK_OFFSET
                    print('warning: no TF for the lidar, assuming it is turned 90 degrees')

    def report(self):
        if self.scan is None or self.offset is None:
            return 'no scan yet (is the robot off the dock? the lidar is switched off on the dock)'
        parts = []
        for name, centre in DIRECTIONS.items():
            d = nearest_in_direction(self.scan, self.offset, centre, HALF_ANGLE)
            parts.append(f'{name} {d:.2f} m' if d < float('inf') else f'{name} -')
        return ' | '.join(parts)


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # we handle Ctrl+C ourselves
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    node = LidarReader()
    try:
        print(f'Reading the lidar for {SECONDS} s. Press Ctrl+C to stop. Walk around the robot and watch the numbers.')
        end = time.monotonic() + SECONDS
        next_report = time.monotonic() + 1.0
        while time.monotonic() < end and not stop_requested:
            rclpy.spin_once(node, timeout_sec=0.1)
            if time.monotonic() >= next_report:
                print(f'{time.strftime("%H:%M:%S")} {node.report()}', flush=True)
                next_report += 1.0
        print('Stopped.' if stop_requested else 'Done.')
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 130 if stop_requested else 0


if __name__ == '__main__':
    sys.exit(main())
