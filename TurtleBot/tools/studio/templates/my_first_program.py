#!/usr/bin/env python3
"""Your first robot program: read the battery, the dock state and the position, and print a report every second.

MOVES THE ROBOT: no. It only listens, so it is safe to run on the dock.
Run it on the robot:      python3 my_first_program.py
How to stop it: Ctrl+C (it also ends by itself after SECONDS).
Change first: SECONDS, or add a line to the report in report() (try printing the speed from /odom).

The ROS 2 basics, in five lines:
  - A program that talks to the robot is a "node".
  - The robot's data comes on "topics" (/battery_state, /odom ...). To read one you "subscribe" to it
    and ROS calls your function every time a new message arrives.
  - rclpy.spin_once() is what lets ROS call those functions. Call it in a loop.
  - To move the robot you would "publish" on /cmd_vel (see spin_in_place.py).
  - The message type must match the topic: BatteryState for /battery_state, Odometry for /odom ...
"""
import math
import signal
import sys
import time

import rclpy                                         # the ROS 2 Python library
from nav_msgs.msg import Odometry                    # message type of /odom (position and speed)
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data        # "best effort" delivery, right for sensor topics
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import BatteryState             # message type of /battery_state

try:   # robot-specific messages; missing on a plain ROS install
    from irobot_create_msgs.msg import DockStatus    # message type of /dock_status
except ImportError:
    DockStatus = None

# ------------------------------------------------------------------ CONSTANTS (change these first)
SECONDS = 10             # how long to run
PERIOD = 1.0             # seconds between reports

stop_requested = False   # set to True by Ctrl+C or SIGTERM


def on_signal(signum, frame):
    global stop_requested
    stop_requested = True


def yaw_degrees(q):
    """Heading in degrees from an orientation quaternion (0 = the way the robot faced when ROS started)."""
    return math.degrees(math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z)))


class FirstProgram(Node):
    def __init__(self):
        super().__init__('my_first_program')          # the name this program shows up as in ROS
        self.battery = None                           # latest messages, filled in by the functions below
        self.docked = None
        self.odom = None
        self.odom_time = None
        # create_subscription(message type, topic name, function to call, quality of service)
        self.create_subscription(BatteryState, '/battery_state', self.on_battery, qos_profile_sensor_data)
        self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
        if DockStatus is not None:
            self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)

    # ROS calls these three functions by itself whenever a message arrives.
    def on_battery(self, msg):
        self.battery = msg.percentage                 # 0.0 to 1.0

    def on_dock(self, msg):
        self.docked = msg.is_docked                   # True or False

    def on_odom(self, msg):
        self.odom = msg.pose.pose                     # position (x, y in metres) and orientation
        self.odom_time = time.monotonic()

    def report(self):
        """One line of text with everything we know right now."""
        battery = 'no data' if self.battery is None else f'{100 * self.battery:.0f} %'
        docked = 'no data' if self.docked is None else ('yes' if self.docked else 'no')
        if self.odom is None:
            position = 'no data'
        else:
            age = time.monotonic() - self.odom_time   # how old the last odometry message is
            position = (f'x {self.odom.position.x:+.2f} m, y {self.odom.position.y:+.2f} m, '
                        f'heading {yaw_degrees(self.odom.orientation):+.0f} deg (age {age:.2f} s)')
        return f'battery {battery} | on the dock: {docked} | position: {position}'


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # we handle Ctrl+C ourselves, below
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    node = FirstProgram()
    try:
        print(f'Listening for {SECONDS} s. Press Ctrl+C to stop. (ROS starts slowly on the Pi: wait a few seconds.)')
        end = time.monotonic() + SECONDS
        next_report = time.monotonic() + PERIOD
        while time.monotonic() < end and not stop_requested:
            rclpy.spin_once(node, timeout_sec=0.1)    # let ROS deliver messages to the functions above
            if time.monotonic() >= next_report:
                print(f'{time.strftime("%H:%M:%S")} {node.report()}', flush=True)
                next_report += PERIOD
        print('Stopped.' if stop_requested else 'Done.')
    finally:                                          # runs on every way out
        node.destroy_node()
        rclpy.try_shutdown()
    return 130 if stop_requested else 0


if __name__ == '__main__':
    sys.exit(main())
