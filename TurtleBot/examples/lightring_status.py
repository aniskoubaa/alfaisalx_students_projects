"""Show the robot's state on the light ring for a while, then give the light ring back to the robot.

Does NOT move the robot. Safe on the dock.

What the 6 LEDs show (updated twice a second):
    number of lit LEDs = battery level (6 lit = full, 1 lit = almost empty)
    colour: green battery >= 50 %, yellow 20..50 %, red < 20 %
    all LEDs blinking red: the lidar is stale (no /scan for LIDAR_STALE s) while the robot is OFF the dock
                           (on the dock the lidar is switched off on purpose, so that is not an error)
    all LEDs blinking white: no /battery_state yet
At the end (after --seconds, or on Ctrl+C / SIGTERM) it sends override_system: false, so the robot's own
light ring patterns come back. Message: irobot_create_msgs/msg/LightringLeds (as in hello_robot.py).

Run it on the robot:
    python3 lightring_status.py                    # 30 s
    python3 lightring_status.py --seconds 120
Exit codes: 0 done, 2 the light ring topic has no subscriber (base not running?).
"""
import argparse
import math
import signal
import sys
import time

import rclpy
from irobot_create_msgs.msg import DockStatus, LedColor, LightringLeds
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import BatteryState, LaserScan

# ---------------------------------------------------------------- parameters
SECONDS = 30.0                # default run time
MAX_SECONDS = 600.0
UPDATE = 0.5                  # s between light ring updates
LIDAR_STALE = 2.0             # s without /scan = stale
GOOD, LOW = 0.50, 0.20        # battery fractions for green / yellow / red
BRIGHT = 255
RELEASE_REPEAT = 3            # send the "give it back" message this many times
WAIT_SUBSCRIBER = 30.0        # s, wait this long for the base to subscribe to /cmd_lightring

GREEN, YELLOW, RED, WHITE, OFF = (0, BRIGHT, 0), (BRIGHT, 180, 0), (BRIGHT, 0, 0), (BRIGHT, BRIGHT, BRIGHT), (0, 0, 0)

stop_request = None


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def battery_colour(fraction):
    if fraction >= GOOD:
        return GREEN
    if fraction >= LOW:
        return YELLOW
    return RED


def pattern(battery, lidar_stale, docked, blink_on):
    """List of 6 (r, g, b) tuples for the current state."""
    if battery is None or not math.isfinite(battery):
        return [WHITE if blink_on else OFF] * 6
    if lidar_stale and not docked:
        return [RED if blink_on else OFF] * 6
    lit = max(1, min(6, int(math.ceil(battery * 6 - 1e-9))))
    colour = battery_colour(battery)
    return [colour if i < lit else OFF for i in range(6)]


# ---------------------------------------------------------------- ROS node
class LightringStatus(Node):
    def __init__(self):
        super().__init__('lightring_status')
        self.pub = self.create_publisher(LightringLeds, '/cmd_lightring', 10)
        self.battery = None
        self.docked = None
        self.scan_time = None
        self.create_subscription(BatteryState, '/battery_state', self.on_battery, qos_profile_sensor_data)
        self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

    def on_battery(self, msg):
        self.battery = msg.percentage        # 0..1 on the Create 3

    def on_dock(self, msg):
        self.docked = msg.is_docked

    def on_scan(self, msg):
        self.scan_time = time.monotonic()

    def show(self, colours, override):
        msg = LightringLeds()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.override_system = override
        msg.leds = [LedColor(red=r, green=g, blue=b) for r, g, b in colours]
        self.pub.publish(msg)


def on_signal(signum, frame):
    global stop_request
    stop_request = signal.Signals(signum).name


def spin_for(node, seconds):
    end = time.monotonic() + seconds
    while not stop_request:
        left = end - time.monotonic()
        if left <= 0:
            return
        rclpy.spin_once(node, timeout_sec=left)


def main():
    p = argparse.ArgumentParser(description='Show battery / lidar state on the light ring. Does not move the robot.')
    p.add_argument('--seconds', type=float, default=SECONDS, help=f'run time (default {SECONDS:.0f}, max {MAX_SECONDS:.0f})')
    args = p.parse_args()
    seconds = max(1.0, min(MAX_SECONDS, args.seconds))

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    node = LightringStatus()
    code = 0
    took_over = False
    try:
        end = time.monotonic() + WAIT_SUBSCRIBER
        while not stop_request and time.monotonic() < end and not node.pub.get_subscription_count():
            rclpy.spin_once(node, timeout_sec=0.5)
        if not node.pub.get_subscription_count():
            print('nobody listens on /cmd_lightring: is the Create 3 base running? (see HOW-TO-CONNECT.md)')
            return 2
        spin_for(node, 2.0)       # collect battery / dock / scan state first
        start = time.monotonic()
        print(f'{time.strftime("%H:%M:%S")} light ring shows the robot state for {seconds:.0f} s '
              '(Ctrl+C to stop early)', flush=True)
        last_line = None
        blink = False
        while not stop_request and time.monotonic() - start < seconds:
            now = time.monotonic()
            stale = node.scan_time is None or now - node.scan_time > LIDAR_STALE
            blink = not blink
            node.show(pattern(node.battery, stale, bool(node.docked), blink), True)
            took_over = True
            batt = 'unknown' if node.battery is None else f'{100 * node.battery:.0f} %'
            line = f'battery {batt}, docked {node.docked}, lidar {"stale" if stale else "ok"}'
            if line != last_line:
                print(f'{time.strftime("%H:%M:%S")} {line}', flush=True)
                last_line = line
            spin_for(node, UPDATE)
    finally:
        if took_over:
            for _ in range(RELEASE_REPEAT):          # give the light ring back to the robot
                node.show([OFF] * 6, False)
                time.sleep(0.1)
            print(f'{time.strftime("%H:%M:%S")} light ring handed back to the robot'
                  + (f' ({stop_request})' if stop_request else ''), flush=True)
        node.destroy_node()
        rclpy.try_shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
