#!/usr/bin/env python3
"""Drive in a circle (or several laps) with a radius you choose, and stop where you started.

MOVES THE ROBOT: yes. Undock first, clear about 1 m all round and stay next to it.
Run it on the robot:      python3 drive_circle.py --radius 0.3 --dry-run     (checks only, never moves)
                          python3 drive_circle.py --radius 0.3 --laps 1
How to stop it: Ctrl+C, or from another terminal:  touch ~/STOP   (delete it afterwards: rm ~/STOP).
Change first: RADIUS and SPEED in the CONSTANTS block below.

How it works: to drive a circle you send a forward speed v and a turn rate w together; the radius is
r = v / w, so w = v / r. The heading from /odom counts the laps (one lap = 360 degrees) and the program
slows down near the end. A negative --laps drives a right-hand circle. The lidar must show nothing closer
than STOP_DISTANCE straight ahead, otherwise the robot stops.
"""
import argparse
import math
import os
import signal
import sys
import time

import rclpy
import tf2_ros
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from rclpy.time import Time
from sensor_msgs.msg import LaserScan

try:   # robot-specific messages; missing on a plain ROS install
    from irobot_create_msgs.msg import DockStatus, HazardDetection, HazardDetectionVector
except ImportError:
    DockStatus = HazardDetection = HazardDetectionVector = None

# ------------------------------------------------------------------ CONSTANTS (change these first)
RADIUS = 0.30            # m, radius of the circle
SPEED = 0.10             # m/s forward speed along the circle
LAPS = 1.0               # how many laps (negative = circle to the right)
# Safety limits. Keep them: the robot is lab equipment and people stand next to it.
MAX_SPEED = 0.15         # m/s, any faster SPEED is lowered to this
MAX_TURN_SPEED = 1.0     # rad/s (a small radius lowers the speed so that v / r stays below this)
MIN_RADIUS, MAX_RADIUS, MAX_LAPS = 0.15, 0.5, 3.0
STOP_DISTANCE = 0.35     # m, stop if the lidar sees anything closer than this straight ahead
FRONT_HALF_ANGLE = math.radians(30)   # "straight ahead" = within 30 degrees of the front
TIME_LIMIT = 90.0        # s, the whole run must finish within this
MIN_TURN_SPEED = 0.15    # rad/s, slowest turn rate near the end of the circle
ANGLE_TOL = math.radians(1.0)   # done when we are this close to the target angle
ODOM_HOLD = 0.3          # s, /odom older than this: stand still and wait (the base pauses it now and then)
ODOM_STALE = 2.0         # s, no /odom for this long: stop and give up
ODOM_SETTLE_AFTER_START = 20.0   # s, never move earlier than this after the program started: a program that
                                # subscribes to /odom makes the base pause for up to ~12 s in its first ~17 s
ODOM_STEADY = 5.0        # s, and /odom must have arrived this long with no gap (can overlap the settle time)
ODOM_MAX_GAP = 0.3       # s, a longer gap between two /odom messages restarts the ODOM_STEADY wait
ODOM_STEADY_TIMEOUT = 30.0   # s, give up (and do not move) after this from the start of the wait, but never before
                             # settle time left + ODOM_STEADY + 10 s margin
SCAN_STALE = 1.0         # s, no lidar scan for this long: stop and give up
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
    return math.atan2(math.sin(a), math.cos(a))      # e.g. 359 degrees becomes -1 degree


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def clamp(value, low, high):
    return max(low, min(high, value))


def nearest_ahead(ranges, angle_min, angle_increment, range_min, range_max, offset, half_angle):
    """Nearest valid lidar range within half_angle of straight ahead (inf if none).

    The lidar is mounted turned by `offset` (+90 degrees here): a beam at laser angle a points at robot
    angle a + offset. So straight ahead of the robot is laser angle -90 degrees."""
    nearest = float('inf')
    for i, r in enumerate(ranges):
        if range_min < r < range_max and abs(wrap_angle(angle_min + i * angle_increment + offset)) <= half_angle:
            nearest = min(nearest, r)
    return nearest


class HeadingTracker:
    """Adds up small heading changes, so the total can pass 180 degrees."""

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
        super().__init__('drive_circle')
        # TurtleBot 4 (Jazzy) wants TwistStamped on /cmd_vel, not plain Twist. No publisher in a dry run.
        self.pub = None if dry_run else self.create_publisher(TwistStamped, '/cmd_vel', 10)
        self.odom_time = self.docked = self.hazard = self.scan_time = self.offset = None
        self.odom_watch = None
        self.started = time.monotonic()   # when this program started (see ODOM_SETTLE_AFTER_START)
        self.x = self.y = 0.0
        self.nearest_front = float('inf')
        self.heading = HeadingTracker()
        self.deadline = float('inf')
        self.tf_buffer = tf2_ros.Buffer()                      # TF tells us how the lidar is mounted
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.first_scan = None
        # sensor_data QoS = "best effort", which works with the robot's publishers.
        self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        if DockStatus is not None:
            self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)
            self.create_subscription(HazardDetectionVector, '/hazard_detection', self.on_hazard,
                                     qos_profile_sensor_data)

    def on_odom(self, msg):    # called for every /odom message (about 20 per second)
        p = msg.pose.pose
        self.x, self.y = p.position.x, p.position.y
        self.heading.update(yaw_of(p.orientation))
        self.odom_time = time.monotonic()
        if self.odom_watch is not None:    # only while wait_for_steady_odom() runs
            self.odom_watch.update(self.odom_time)

    def on_dock(self, msg):
        self.docked = msg.is_docked

    def on_hazard(self, msg):  # bumper, cliff sensor, wheel drop ... (the "backup limit" note is harmless)
        for d in msg.detections:
            if d.type != HazardDetection.BACKUP_LIMIT:
                self.hazard = f'type {d.type}'

    def on_scan(self, msg):    # called for every lidar scan (about 8 per second)
        now = time.monotonic()
        self.first_scan = self.first_scan or now
        if self.offset is None:
            try:
                t = self.tf_buffer.lookup_transform('base_link', msg.header.frame_id, Time())
                self.offset = yaw_of(t.transform.rotation)
            except tf2_ros.TransformException:
                if now - self.first_scan > 5.0:
                    self.offset = math.pi / 2          # measured on this robot: the lidar is turned +90 degrees
                    log('warning: no TF for the lidar, assuming it is turned 90 degrees')
        if self.offset is not None:
            self.nearest_front = nearest_ahead(msg.ranges, msg.angle_min, msg.angle_increment, msg.range_min,
                                               msg.range_max, self.offset, FRONT_HALF_ANGLE)
            self.scan_time = now

    def send(self, v, w):
        """Publish one velocity command: v m/s forward, w rad/s to the left. Always limited here."""
        if self.pub is None:
            return
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.linear.x = float(clamp(v, -MAX_SPEED, MAX_SPEED))
        msg.twist.angular.z = float(clamp(w, -MAX_TURN_SPEED, MAX_TURN_SPEED))
        self.pub.publish(msg)

    def stop(self):
        """Zero velocity several times, in case one message is lost. Called on every way out."""
        for _ in range(10):
            self.send(0.0, 0.0)
            time.sleep(0.05)

    def check(self, forward):
        """Raise Stop if anything says stop. Called in every control loop."""
        now = time.monotonic()
        if stop_request:
            raise Stop(130, f'{stop_request} received')
        if os.path.exists(STOP_FILE):
            raise Stop(130, f'{STOP_FILE} exists')
        if self.hazard:
            raise Stop(1, f'hazard reported by the base: {self.hazard}')
        if now - self.odom_time > ODOM_STALE:
            raise Stop(1, f'odometry is stale (none for {now - self.odom_time:.1f} s)')
        if self.scan_time is None or now - self.scan_time > SCAN_STALE:
            raise Stop(1, 'lidar is stale (no recent scan)')
        if forward and self.nearest_front < STOP_DISTANCE:
            raise Stop(1, f'obstacle {self.nearest_front:.2f} m ahead (limit {STOP_DISTANCE:.2f} m)')
        if now > self.deadline:
            raise Stop(1, f'time limit of {TIME_LIMIT:.0f} s reached')


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


# ------------------------------------------------------------------ moves
def circle_speeds(radius, speed):
    """(v, w) for a circle: w = v / r. If w would be above the cap, lower v so that v / r = the cap."""
    speed = clamp(speed, 0.0, MAX_SPEED)
    w = speed / radius
    if w > MAX_TURN_SPEED:
        w = MAX_TURN_SPEED
    return w * radius, w


def drive_circle(robot, radius, speed, laps):
    v_nominal, w_nominal = circle_speeds(radius, speed)
    direction = 1.0 if laps > 0 else -1.0
    target = abs(laps) * 2 * math.pi
    base = robot.heading.total

    def command():
        remaining = target - direction * (robot.heading.total - base)    # radians still to go
        if remaining < ANGLE_TOL:
            return None
        w = clamp(1.5 * remaining, MIN_TURN_SPEED, w_nominal)           # slow down near the end ...
        return w * radius, direction * w                                # ... but keep v / w = radius
    run(robot, command, True, 2 * target / w_nominal + 5)


def run(robot, command, forward, timeout):
    """Control loop. command() returns (v, w), or None when the move is done."""
    start = time.monotonic()
    while True:
        rclpy.spin_once(robot, timeout_sec=1.0 / RATE)
        robot.check(forward)
        if time.monotonic() - start > timeout:
            raise Stop(1, f'move timeout ({timeout:.0f} s)')
        if time.monotonic() - robot.odom_time > ODOM_HOLD:
            robot.send(0.0, 0.0)        # odometry paused: stand still until it comes back
            continue
        cmd = command()
        if cmd is None:
            return
        robot.send(*cmd)


def main():
    p = argparse.ArgumentParser(description='Drive in a circle with the TurtleBot 4. MOVES THE ROBOT.')
    p.add_argument('--radius', type=float, default=RADIUS, help=f'circle radius in m (default {RADIUS}, {MIN_RADIUS}..{MAX_RADIUS})')
    p.add_argument('--speed', type=float, default=SPEED, help=f'forward speed in m/s (default {SPEED}, max {MAX_SPEED})')
    p.add_argument('--laps', type=float, default=LAPS, help=f'laps, negative = right (default {LAPS:g}, max {MAX_LAPS:g})')
    p.add_argument('--dry-run', action='store_true', help='check the robot and print the plan, never move')
    p.add_argument('--yes', action='store_true', help='skip the "area clear?" question (needed when run from Studio)')
    args = p.parse_args()
    radius = clamp(args.radius, MIN_RADIUS, MAX_RADIUS)
    laps = clamp(args.laps, -MAX_LAPS, MAX_LAPS)
    v, w = circle_speeds(radius, args.speed)
    if v < 0.02:
        log('REFUSING: --speed is too low to drive a circle')
        return 2
    expected = abs(laps) * 2 * math.pi / w
    log(f'plan: {abs(laps):g} lap(s) {"left" if laps > 0 else "right"}, radius {radius:g} m, {v:.3f} m/s and {w:.2f} rad/s, about {expected:.0f} s')
    if expected > TIME_LIMIT:
        log(f'REFUSING: that needs about {expected:.0f} s, more than the {TIME_LIMIT:.0f} s limit. Use fewer laps')
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
        if robot.docked:
            log('warning: docked, so the lidar is off and not checked; a real run would refuse to start')
        else:
            if not wait_until(robot, lambda: robot.scan_time is not None, 30, '/scan (the lidar)'):
                raise Stop(2, 'no /scan from the lidar. Is the robot off the dock? Wait a few seconds after undocking')
            rclpy.spin_once(robot, timeout_sec=0.5)
            log(f'lidar OK: nearest thing straight ahead {robot.nearest_front:.2f} m')
            if robot.nearest_front < radius + STOP_DISTANCE:
                raise Stop(2, f'path not clear: need {radius + STOP_DISTANCE:.2f} m free ahead')
        if not args.dry_run:
            confirm(args.yes)
        wait_for_steady_odom(robot)     # the last check before moving (also in a dry run)
        if args.dry_run:
            log('dry run: all checks done, nothing was sent to /cmd_vel')
            return 0
        robot.deadline = time.monotonic() + TIME_LIMIT
        x0, y0 = robot.x, robot.y
        drive_circle(robot, radius, args.speed, laps)
        log(f'done: ended {100 * math.hypot(robot.x - x0, robot.y - y0):.1f} cm from the start (odometry)')
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
