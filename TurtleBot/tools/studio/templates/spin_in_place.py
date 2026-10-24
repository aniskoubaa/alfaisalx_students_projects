#!/usr/bin/env python3
"""Spin the robot on the spot ("make it turn in a circle") and stop exactly after the turns you asked for.

MOVES THE ROBOT: yes (it only turns, it does not drive away). Undock first and stay next to it.
Run it on the robot:      python3 spin_in_place.py --turns 1 --dry-run     (checks only, never moves)
                          python3 spin_in_place.py --turns 1
How to stop it: Ctrl+C, or from another terminal:  touch ~/STOP   (delete it afterwards: rm ~/STOP).
Change first: TURNS and SPEED in the CONSTANTS block below.

How it works: it reads the robot's heading from /odom, adds up every small change, and sends a turn command
on /cmd_vel until the sum reaches your target. It slows down near the end so it stops on the mark.
"""
import argparse
import math
import os
import signal
import sys
import time

import rclpy
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions

try:   # robot-specific messages; missing on a plain ROS install
    from irobot_create_msgs.msg import DockStatus, HazardDetection, HazardDetectionVector
except ImportError:
    DockStatus = HazardDetection = HazardDetectionVector = None

# ------------------------------------------------------------------ CONSTANTS (change these first)
TURNS = 1.0              # how many full turns (negative = turn right)
SPEED = 0.5              # turn speed in rad/s (0.5 rad/s = one turn in about 12.6 s)
# Safety limits. Keep them: the robot is lab equipment and people stand next to it.
MAX_SPEED = 1.0          # rad/s, any faster SPEED is lowered to this
MAX_TURNS = 5.0          # most turns in one run
TIME_LIMIT = 90.0        # s, the whole run must finish within this
MIN_SPEED = 0.15         # rad/s, slowest turn near the end (below this the wheels barely move)
TOLERANCE = math.radians(1.0)   # done when we are this close to the target angle
ODOM_HOLD = 0.3          # s, /odom older than this: stand still and wait (the base pauses it now and then)
ODOM_STALE = 2.0         # s, no /odom for this long: stop and give up
ODOM_SETTLE_AFTER_START = 20.0   # s, never move earlier than this after the program started: a program that
                                # subscribes to /odom makes the base pause for up to ~12 s in its first ~17 s
ODOM_STEADY = 5.0        # s, and /odom must have arrived this long with no gap (can overlap the settle time)
ODOM_MAX_GAP = 0.3       # s, a longer gap between two /odom messages restarts the ODOM_STEADY wait
ODOM_STEADY_TIMEOUT = 30.0   # s, give up (and do not move) after this from the start of the wait, but never before
                             # settle time left + ODOM_STEADY + 10 s margin
RATE = 20                # control loop runs this many times per second
STOP_FILE = os.path.expanduser('~/STOP')   # create this file and the robot stops

stop_request = None      # set by the signal handler, checked in every loop


class Stop(Exception):
    """Leave the program. code: 1 = safety stop, 2 = could not start, 130 = you stopped it."""

    def __init__(self, code, why):
        super().__init__(why)
        self.code = code


def log(text):
    print(f'{time.strftime("%H:%M:%S")} {text}', flush=True)


# ------------------------------------------------------------------ pure helpers (no ROS needed)
def wrap_angle(a):
    """Wrap an angle into -pi..pi, so 359 degrees becomes -1 degree."""
    return math.atan2(math.sin(a), math.cos(a))


def yaw_of(q):
    """Heading (rotation about the vertical axis) from an orientation quaternion."""
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def clamp(value, low, high):
    return max(low, min(high, value))


def turn_rate(remaining, speed):
    """Turn rate for the angle still to go: full speed, slowing down in the last ~40 degrees. Sign = direction."""
    w = clamp(1.5 * abs(remaining), MIN_SPEED, speed)
    return math.copysign(w, remaining)


class HeadingTracker:
    """Adds up small heading changes, so the total can pass 180 degrees (a full turn is 360)."""

    def __init__(self):
        self.last, self.total = None, 0.0

    def update(self, yaw):
        if self.last is not None:
            self.total += wrap_angle(yaw - self.last)
        self.last = yaw
        return self.total


# ------------------------------------------------------------------ the ROS node
class Robot(Node):
    """A ROS 2 node = one program talking to the robot. It listens (subscriptions) and talks (publisher)."""

    def __init__(self, dry_run):
        super().__init__('spin_in_place')
        # TurtleBot 4 (Jazzy) wants TwistStamped on /cmd_vel, not plain Twist. No publisher in a dry run.
        self.pub = None if dry_run else self.create_publisher(TwistStamped, '/cmd_vel', 10)
        self.odom_time = self.docked = self.hazard = None
        self.odom_watch = None
        self.started = time.monotonic()   # when this program started (see ODOM_SETTLE_AFTER_START)
        self.heading = HeadingTracker()
        # sensor_data QoS = "best effort", which works with the robot's publishers.
        self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
        if DockStatus is not None:
            self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)
            self.create_subscription(HazardDetectionVector, '/hazard_detection', self.on_hazard,
                                     qos_profile_sensor_data)

    def on_odom(self, msg):    # called for every /odom message (about 20 per second)
        self.heading.update(yaw_of(msg.pose.pose.orientation))
        self.odom_time = time.monotonic()
        if self.odom_watch is not None:    # only while wait_for_steady_odom() runs
            self.odom_watch.update(self.odom_time)

    def on_dock(self, msg):
        self.docked = msg.is_docked

    def on_hazard(self, msg):  # bumper, cliff sensor, wheel drop ... (the "backup limit" note is harmless)
        for d in msg.detections:
            if d.type != HazardDetection.BACKUP_LIMIT:
                self.hazard = f'type {d.type}'

    def send(self, v, w):
        """Publish one velocity command: v m/s forward, w rad/s to the left. Always limited here."""
        if self.pub is None:
            return
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.linear.x = float(clamp(v, -0.15, 0.15))
        msg.twist.angular.z = float(clamp(w, -MAX_SPEED, MAX_SPEED))
        self.pub.publish(msg)

    def stop(self):
        """Zero velocity several times, in case one message is lost. Called on every way out."""
        for _ in range(10):
            self.send(0.0, 0.0)
            time.sleep(0.05)

    def check(self):
        """Raise Stop if anything says stop. Called in every control loop."""
        if stop_request:
            raise Stop(130, f'{stop_request} received')
        if os.path.exists(STOP_FILE):
            raise Stop(130, f'{STOP_FILE} exists')
        if self.hazard:
            raise Stop(1, f'hazard reported by the base: {self.hazard}')
        age = time.monotonic() - self.odom_time
        if age > ODOM_STALE:
            raise Stop(1, f'odometry is stale (none for {age:.1f} s)')


def on_signal(signum, frame):
    global stop_request
    stop_request = signal.Signals(signum).name


def wait_until(robot, ready, seconds, what):
    log(f'waiting up to {seconds:.0f} s for {what} (ROS starts slowly on the Pi)')
    end = time.monotonic() + seconds
    while not ready() and time.monotonic() < end:
        if stop_request:
            raise Stop(130, f'{stop_request} received')
        rclpy.spin_once(robot, timeout_sec=0.2)   # lets ROS call on_odom() and friends
    return ready()


class SteadyOdom:
    """Tells when it is safe to move: the program is ODOM_SETTLE_AFTER_START s old and /odom has been steady
    (no gap over ODOM_MAX_GAP for ODOM_STEADY seconds; that window may overlap the settle time)."""

    def __init__(self, started=None):
        self.started = started   # time.monotonic() when the program started (None = no settle time)
        self.start = None      # arrival time that starts the current unbroken run
        self.last = None       # arrival time of the latest /odom message
        self.gaps = 0          # how many gaps over ODOM_MAX_GAP were seen
        self.last_gap = 0.0    # length of the latest such gap
        self.longest = 0.0     # longest gap between two messages

    def update(self, t):
        """Call for every /odom message (t = time.monotonic()). A long gap restarts the run."""
        if self.last is not None:
            self.longest = max(self.longest, t - self.last)
            if t - self.last > ODOM_MAX_GAP + 1e-9:     # 1e-9: rounding must not turn 0.3 into a gap
                self.gaps += 1
                self.last_gap = t - self.last
                self.start = t
        if self.start is None:
            self.start = t
        self.last = t

    def worst_gap(self, now):
        """Longest gap so far, counting a pause that is still going on."""
        return max(self.longest, 0.0 if self.last is None else now - self.last)

    def ready(self, now):
        """True when the program has settled, the run is long enough and /odom is not paused right now."""
        if self.started is not None and now - self.started < ODOM_SETTLE_AFTER_START:
            return False
        return (self.last is not None and now - self.last <= ODOM_MAX_GAP + 1e-9
                and self.last - self.start >= ODOM_STEADY)


def wait_for_steady_odom(robot):
    """Last check before moving: wait until the program is 20 s old and /odom has been steady for 5 s, so the first
    move does not land in a pause. A program that subscribes to /odom makes the base pause for up to ~12 s in its
    first ~17 s (ROADMAP.md TB-25). The time limit is max(30 s, settle time left + 5 s + 10 s margin)."""
    begin, seen = time.monotonic(), 0
    watch = robot.odom_watch = SteadyOdom(robot.started)
    limit = max(ODOM_STEADY_TIMEOUT, robot.started + ODOM_SETTLE_AFTER_START - begin + ODOM_STEADY + 10.0)
    log(f'waiting until {ODOM_SETTLE_AFTER_START:.0f} s after start and {ODOM_STEADY:.0f} s of steady /odom before moving: a program '
        'that subscribes to /odom makes the base pause for up to about 12 s in the first ~17 s after it starts ...')
    try:
        while True:
            now = time.monotonic()
            if stop_request:
                raise Stop(130, f'{stop_request} received')
            if os.path.exists(STOP_FILE):
                raise Stop(130, f'{STOP_FILE} exists')
            if watch.ready(now):
                log(f'odometry steady for {ODOM_STEADY:.1f} s, {now - robot.started:.1f} s after start '
                    f'(waited {now - begin:.1f} s, {watch.gaps} gaps over {ODOM_MAX_GAP:.1f} s)')
                return
            if now - begin > limit:
                raise Stop(2, f'odometry not steady within {limit:.0f} s (longest gap {watch.worst_gap(now):.1f} s). '
                              'Starting or stopping a ROS program can pause the base; wait a minute and run again (see ROADMAP.md TB-25)')
            rclpy.spin_once(robot, timeout_sec=0.05)
            if watch.gaps > seen:
                seen = watch.gaps
                log(f'/odom paused for {watch.last_gap:.1f} s, waiting again for {ODOM_STEADY:.0f} s of steady odometry')
    finally:
        robot.odom_watch = None


def confirm(yes):
    if yes:
        return
    if not sys.stdin.isatty():
        raise Stop(2, 'no terminal to ask "is the area clear?". Run with --yes when detached')
    try:
        answer = input('The robot is about to MOVE. Is 1 m around it clear and are you next to it? Type yes: ')
    except EOFError:
        answer = ''
    if answer.strip().lower() != 'yes':
        raise Stop(2, 'not confirmed, not moving')


def spin(robot, turns, speed):
    """Turn until the summed heading change reaches turns * 360 degrees."""
    target = turns * 2 * math.pi
    start = time.monotonic()
    base = robot.heading.total          # heading when we start
    while True:
        rclpy.spin_once(robot, timeout_sec=1.0 / RATE)
        robot.check()
        if time.monotonic() - start > TIME_LIMIT:
            raise Stop(1, f'time limit of {TIME_LIMIT:.0f} s reached')
        if time.monotonic() - robot.odom_time > ODOM_HOLD:
            robot.send(0.0, 0.0)        # odometry paused: stand still until it comes back
            continue
        remaining = target - (robot.heading.total - base)
        if abs(remaining) < TOLERANCE:
            return
        robot.send(0.0, turn_rate(remaining, speed))


def main():
    p = argparse.ArgumentParser(description='Spin the TurtleBot 4 on the spot. MOVES THE ROBOT.')
    p.add_argument('--turns', type=float, default=TURNS, help=f'full turns, negative = right (default {TURNS}, max {MAX_TURNS})')
    p.add_argument('--speed', type=float, default=SPEED, help=f'turn speed in rad/s (default {SPEED}, max {MAX_SPEED})')
    p.add_argument('--dry-run', action='store_true', help='check the robot and print the plan, never move')
    p.add_argument('--yes', action='store_true', help='skip the "area clear?" question (needed when run from Studio)')
    args = p.parse_args()
    turns = clamp(args.turns, -MAX_TURNS, MAX_TURNS)
    speed = clamp(abs(args.speed), MIN_SPEED, MAX_SPEED)
    expected = abs(turns) * 2 * math.pi / speed
    log(f'plan: turn {"left" if turns >= 0 else "right"} {abs(turns):g} turn(s) at {speed:g} rad/s, about {expected:.0f} s')
    if expected > TIME_LIMIT:
        log(f'REFUSING: that needs about {expected:.0f} s, more than the {TIME_LIMIT:.0f} s limit. Use fewer turns or a higher speed')
        return 2
    if os.path.exists(STOP_FILE) and not args.dry_run:
        log(f'REFUSING: {STOP_FILE} exists (left from an earlier stop). Delete it first: rm {STOP_FILE}')
        return 2

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # we handle Ctrl+C ourselves, to stop the wheels
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    robot = Robot(args.dry_run)
    code = 0
    try:
        if DockStatus is None:
            raise Stop(2, 'irobot_create_msgs not found, so the dock cannot be checked')
        wait_until(robot, lambda: robot.odom_time is not None and robot.docked is not None, 30, '/odom and /dock_status')
        if robot.odom_time is None or robot.docked is None:
            raise Stop(2, 'no /odom or /dock_status from the base. Restart the base application (see HOW-TO-CONNECT.md)')
        if robot.docked and not args.dry_run:
            raise Stop(2, 'the robot is on the dock. Undock it first')
        log(f'odometry OK, docked: {robot.docked}')
        if not args.dry_run:
            confirm(args.yes)
        wait_for_steady_odom(robot)     # the last check before moving (also in a dry run)
        if args.dry_run:
            log('dry run: all checks done, nothing was sent to /cmd_vel')
            return 0
        spin(robot, turns, speed)
        log(f'done: turned {math.degrees(robot.heading.total):.0f} degrees in total (odometry)')
    except Stop as e:
        code = e.code
        log(('STOPPED: ' if code == 130 else 'ABORTED: ' if code == 1 else 'SETUP FAILED: ') + str(e))
    finally:
        robot.stop()                    # always, even after an error or Ctrl+C
        robot.destroy_node()
        rclpy.try_shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
