"""Drive a shape (square, rotate, back_and_forth, triangle, figure_eight) using odometry, with safety checks.

THIS PROGRAM MOVES THE ROBOT. Before running it: undock the robot, clear about 1 m of floor around it,
and stay next to it. Speed is capped at 0.15 m/s whatever you ask for.

How it works: each shape is a list of segments (drive straight, turn in place, or drive a full circle).
Each segment is closed-loop on /odom: distance is measured from where the segment started, and heading is
the sum of the yaw changes, so turns of more than 180 degrees work. While driving forward the lidar must
show nothing closer than OBSTACLE_STOP_DISTANCE in front, otherwise the robot stops and the program aborts.

Run it on the robot (dry run first: checks everything, prints the plan, never moves):
    python3 motion_shapes.py square --dry-run
    python3 motion_shapes.py square
Detached, so a Wi-Fi drop does not kill it (needs --yes because there is nobody to answer the prompt):
    setsid nohup python3 ~/robot_code/motion_shapes.py square --yes > ~/robot_code/shapes.log 2>&1 &
    tail -f ~/robot_code/shapes.log

How to stop it at any time (the robot stops and the program exits):
    Ctrl+C in the terminal running it
    from another terminal on the robot:  touch ~/STOP          (delete it afterwards: rm ~/STOP)
    from another terminal on the robot:  pkill -INT -f motion_shapes.py

Exit codes: 0 done, 1 aborted by a safety check, 2 setup failure (docked, no odometry, no lidar,
STOP file present, ...), 130 stopped by you (Ctrl+C, SIGTERM or the STOP file).
On this TurtleBot 4 (ROS 2 Jazzy) /cmd_vel takes geometry_msgs/msg/TwistStamped, not Twist.
See README.md in this folder for the full instructions.
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
from sensor_msgs.msg import LaserScan

try:
    from irobot_create_msgs.msg import DockStatus, HazardDetection, HazardDetectionVector
except ImportError:
    DockStatus = HazardDetection = HazardDetectionVector = None

# ---------------------------------------------------------------- parameters
SIDE_LENGTH = 0.40            # m, side of the square/triangle and length of the back_and_forth leg
MAX_SIDE_LENGTH = 1.0         # m, longest side allowed from the command line (the clear area is about 1 m)
LINEAR_SPEED = 0.10           # m/s, normal forward speed
MAX_LINEAR_SPEED = 0.15       # m/s, hard cap: any faster --speed is lowered to this
MIN_LINEAR_SPEED = 0.03       # m/s, slowest speed used when slowing down near the goal
ANGULAR_SPEED = 0.5           # rad/s, normal turning speed
MAX_ANGULAR_SPEED = 1.0       # rad/s, hard cap: any faster --turn-speed is lowered to this
MIN_ANGULAR_SPEED = 0.15      # rad/s, slowest turning speed used near the goal
DISTANCE_TOLERANCE = 0.01     # m, a straight segment is done within 1 cm of its length
ANGLE_TOLERANCE = math.radians(1.5)   # a turn is done within 1.5 degrees of its angle
LINEAR_SLOWDOWN = 1.0         # 1/s, speed = this * remaining distance near the goal (slows in the last ~10 cm)
ANGULAR_SLOWDOWN = 1.5        # 1/s, turn rate = this * remaining angle near the goal
HEADING_HOLD_GAIN = 1.5       # rad/s per rad of heading error, keeps straight segments straight
MAX_HEADING_CORRECTION = 0.3  # rad/s, largest steering correction on a straight segment
CIRCLE_RADIUS = 0.20          # m, radius of each circle of the figure eight
OBSTACLE_STOP_DISTANCE = 0.25           # m, stop if anything is closer than this in front
OBSTACLE_HALF_ANGLE = math.radians(30)  # "in front" means within +/-30 degrees of straight ahead
LIDAR_OFFSET_FALLBACK = math.pi / 2     # lidar yaw in the robot frame if TF is missing (measured +90 deg)
TOTAL_TIMEOUT = 120.0         # s, the whole shape must finish within this
SEGMENT_TIMEOUT_FACTOR = 2.0  # a segment may take 2x its expected time ...
SEGMENT_TIMEOUT_EXTRA = 5.0   # ... plus 5 s
ODOM_HOLD = 0.3               # s, odometry older than this: send zero velocity and wait for fresh data
ODOM_STALE = 2.0              # s, abort if no odometry for this long (gaps of 0.4 to 1 s were seen on 2026-10-04)
SCAN_STALE = 1.0              # s, abort if no lidar scan for this long
STALL_TIME = 3.0              # s, abort if we command motion but odometry shows no progress for this long
STALL_MIN_MOVE = 0.005        # m, movement that counts as progress
STALL_MIN_TURN = math.radians(1.0)    # turn that counts as progress
STARTUP_WAIT = 30.0           # s, how long to wait for /odom, /scan and /dock_status at start
PAUSE = 0.5                   # s, stand still between segments
STOP_BURST = 0.5              # s, how long to keep sending zero velocity when stopping
CONTROL_RATE = 20             # Hz, control loop rate
STOP_FILE = os.path.expanduser('~/STOP')   # if this file exists, the robot stops

SHAPES = ['square', 'rotate', 'back_and_forth', 'triangle', 'figure_eight']

# Set by the signal handler; checked every control cycle.
stop_request = None
motion_active = False


class Abort(Exception):
    """Stop the run. code is the exit code (1 safety, 2 setup, 130 stopped by the user)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def log(text):
    print(f'{time.strftime("%H:%M:%S")} {text}', flush=True)


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def wrap_angle(a):
    """Wrap an angle to [-pi, pi]."""
    return math.atan2(math.sin(a), math.cos(a))


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class HeadingTracker:
    """Adds up small yaw changes so the total can go past +/-180 degrees (e.g. 360 for a full turn)."""

    def __init__(self):
        self.last = None
        self.total = 0.0

    def update(self, yaw):
        if self.last is not None:
            self.total += wrap_angle(yaw - self.last)
        self.last = yaw
        return self.total


def clamp_setting(name, value, low, high, unit):
    """Return (value limited to [low, high], message or None)."""
    if value > high:
        return high, f'{name} {value:g} {unit} is above the cap, using {high:g} {unit}'
    if value < low:
        return low, f'{name} {value:g} {unit} is below the minimum, using {low:g} {unit}'
    return value, None


def nearest_in_sector(ranges, angle_min, angle_increment, range_min, range_max, offset, half_angle):
    """Nearest valid range within +/-half_angle of straight ahead of the robot.

    offset is the lidar's yaw in the robot frame: a beam at laser angle a points at robot angle a + offset.
    Returns inf if no valid beam is in the sector.
    """
    nearest = float('inf')
    for i, r in enumerate(ranges):
        if not (range_min < r < range_max):   # also drops inf and nan
            continue
        a = wrap_angle(angle_min + i * angle_increment + offset)
        if abs(a) <= half_angle and r < nearest:
            nearest = r
    return nearest


def nearest_any(ranges, range_min, range_max):
    valid = [r for r in ranges if range_min < r < range_max]
    return min(valid) if valid else float('inf')


def arc_speeds(radius, speed, max_turn):
    """Forward and turn speed for a circle: w = v / r, lowering v if w would exceed max_turn."""
    w = speed / radius
    if w > max_turn:
        w = max_turn
        speed = w * radius
    return speed, w


def plan_segments(shape, side, radius):
    """List of segments for a shape. Kinds: straight (distance m), turn (angle rad, + is left),
    arc (angle rad, + is a left circle, - a right circle; radius m)."""
    left90, left120, half = math.pi / 2, 2 * math.pi / 3, math.pi
    if shape == 'square':
        segs = []
        for _ in range(4):
            segs += [{'kind': 'straight', 'distance': side}, {'kind': 'turn', 'angle': left90}]
        return segs
    if shape == 'triangle':
        segs = []
        for _ in range(3):
            segs += [{'kind': 'straight', 'distance': side}, {'kind': 'turn', 'angle': left120}]
        return segs
    if shape == 'rotate':
        return [{'kind': 'turn', 'angle': 2 * math.pi}]
    if shape == 'back_and_forth':
        # Drive out, turn round, drive back, turn round. No reversing: the Create 3 limits driving
        # backwards and the lidar check only covers the front.
        return [{'kind': 'straight', 'distance': side}, {'kind': 'turn', 'angle': half},
                {'kind': 'straight', 'distance': side}, {'kind': 'turn', 'angle': half}]
    if shape == 'figure_eight':
        return [{'kind': 'arc', 'angle': 2 * math.pi, 'radius': radius},
                {'kind': 'arc', 'angle': -2 * math.pi, 'radius': radius}]
    raise ValueError(f'unknown shape {shape}')


def add_timing(segs, speed, turn_speed):
    """Fill in the speeds, expected time and timeout of each segment."""
    for s in segs:
        if s['kind'] == 'straight':
            s['v'], s['w'] = speed, 0.0
            s['expected'] = s['distance'] / speed
        elif s['kind'] == 'turn':
            s['v'], s['w'] = 0.0, turn_speed
            s['expected'] = abs(s['angle']) / turn_speed
        else:
            s['v'], s['w'] = arc_speeds(s['radius'], speed, turn_speed)
            s['expected'] = abs(s['angle']) / s['w']
        s['timeout'] = SEGMENT_TIMEOUT_FACTOR * s['expected'] + SEGMENT_TIMEOUT_EXTRA
    return segs


def describe_segment(s):
    if s['kind'] == 'straight':
        what = f'forward {s["distance"]:.2f} m at {s["v"]:.2f} m/s'
    elif s['kind'] == 'turn':
        side = 'left' if s['angle'] > 0 else 'right'
        what = f'turn {side} {math.degrees(abs(s["angle"])):.0f} deg at {s["w"]:.2f} rad/s'
    else:
        side = 'left' if s['angle'] > 0 else 'right'
        what = f'full {side} circle, radius {s["radius"]:.2f} m, at {s["v"]:.2f} m/s and {s["w"]:.2f} rad/s'
    return f'{what} (about {s["expected"]:.1f} s, timeout {s["timeout"]:.1f} s)'


def planned_end_pose(segs):
    """Where the plan should end, in the start frame (x forward, y left): (x, y, total heading change)."""
    x = y = h = 0.0
    for s in segs:
        if s['kind'] == 'straight':
            x += s['distance'] * math.cos(h)
            y += s['distance'] * math.sin(h)
        elif s['kind'] == 'turn':
            h += s['angle']
        # a full circle ends where it started, with the same heading
    return round(x, 9) + 0.0, round(y, 9) + 0.0, h   # + 0.0 avoids printing -0.000


def straight_command(remaining, heading_error, speed):
    """(v, w) for a straight segment: slow down near the end, steer to hold the heading."""
    v = max(MIN_LINEAR_SPEED, min(speed, LINEAR_SLOWDOWN * remaining))
    w = max(-MAX_HEADING_CORRECTION, min(MAX_HEADING_CORRECTION, HEADING_HOLD_GAIN * heading_error))
    return v, w


def turn_command(remaining, turn_speed):
    """Turn rate for an in-place turn; remaining is signed, so an overshoot turns back."""
    w = max(MIN_ANGULAR_SPEED, min(turn_speed, ANGULAR_SLOWDOWN * abs(remaining)))
    return math.copysign(w, remaining)


def arc_command(remaining, radius, w_nominal, direction):
    """(v, w) on a circle; slows down near the end but keeps v / w = radius so the circle stays round."""
    w = max(MIN_ANGULAR_SPEED, min(w_nominal, ANGULAR_SLOWDOWN * remaining))
    return w * radius, direction * w


# ---------------------------------------------------------------- ROS node
class MotionShapes(Node):
    def __init__(self, use_lidar, dry_run):
        super().__init__('motion_shapes')
        self.use_lidar = use_lidar
        self.pub = None if dry_run else self.create_publisher(TwistStamped, '/cmd_vel', 10)
        self.odom_time = None
        self.x = self.y = self.yaw = 0.0
        self.heading = HeadingTracker()
        self.scan = None
        self.scan_time = None
        self.first_scan_time = None
        self.lidar_offset = None
        self.nearest_front = float('inf')
        self.is_docked = None
        self.hazard = None
        # Best effort subscriptions accept both best effort and reliable publishers.
        self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
        if DockStatus is not None:
            self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)
            self.create_subscription(HazardDetectionVector, '/hazard_detection', self.on_hazard,
                                     qos_profile_sensor_data)
        if use_lidar:
            self.tf_buffer = tf2_ros.Buffer()
            self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
            self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

    def on_odom(self, msg):
        p = msg.pose.pose
        self.x, self.y, self.yaw = p.position.x, p.position.y, yaw_of(p.orientation)
        self.heading.update(self.yaw)
        self.odom_time = time.monotonic()

    def on_dock(self, msg):
        self.is_docked = msg.is_docked

    def on_hazard(self, msg):
        for d in msg.detections:
            if d.type != HazardDetection.BACKUP_LIMIT:
                names = {HazardDetection.BUMP: 'BUMP', HazardDetection.CLIFF: 'CLIFF',
                         HazardDetection.STALL: 'STALL', HazardDetection.WHEEL_DROP: 'WHEEL_DROP',
                         HazardDetection.OBJECT_PROXIMITY: 'OBJECT_PROXIMITY'}
                self.hazard = f'{names.get(d.type, d.type)} ({d.header.frame_id})'

    def on_scan(self, msg):
        now = time.monotonic()
        if self.first_scan_time is None:
            self.first_scan_time = now
        if self.lidar_offset is None:
            try:
                t = self.tf_buffer.lookup_transform('base_link', msg.header.frame_id, rclpy.time.Time())
                self.lidar_offset = yaw_of(t.transform.rotation)
                log(f'lidar yaw in the robot frame (from TF): {math.degrees(self.lidar_offset):.0f} deg')
            except tf2_ros.TransformException:
                if now - self.first_scan_time > 5.0:
                    self.lidar_offset = LIDAR_OFFSET_FALLBACK
                    log(f'warning: no TF from base_link to {msg.header.frame_id}, '
                        f'assuming the lidar is turned {math.degrees(LIDAR_OFFSET_FALLBACK):.0f} deg')
        if self.lidar_offset is not None:
            self.nearest_front = nearest_in_sector(msg.ranges, msg.angle_min, msg.angle_increment,
                                                   msg.range_min, msg.range_max,
                                                   self.lidar_offset, OBSTACLE_HALF_ANGLE)
            self.scan = msg
            self.scan_time = now

    def send(self, v, w):
        if self.pub is None:
            return
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.linear.x = float(v)
        msg.twist.angular.z = float(w)
        self.pub.publish(msg)


# ---------------------------------------------------------------- run-time helpers
def on_signal(signum, frame):
    global stop_request
    stop_request = signal.Signals(signum).name
    if not motion_active:
        raise KeyboardInterrupt   # before driving: just leave; while driving: the loop stops the robot


def spin_for(node, seconds):
    end = time.monotonic() + seconds
    while True:
        left = end - time.monotonic()
        if left <= 0:
            return
        rclpy.spin_once(node, timeout_sec=left)


def wait_for(node, what, ready, seconds):
    """Spin until ready() is true or the time runs out. Returns True if ready."""
    log(f'waiting up to {seconds:.0f} s for {what}')
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if ready():
            return True
        rclpy.spin_once(node, timeout_sec=0.2)
    return ready()


def check_safety(node, forward, deadline):
    """Raise Abort if anything says stop. Called every control cycle, also while standing still."""
    now = time.monotonic()
    if stop_request:
        raise Abort(130, f'{stop_request} received')
    if os.path.exists(STOP_FILE):
        raise Abort(130, f'{STOP_FILE} exists')
    if node.hazard:
        raise Abort(1, f'hazard reported by the base: {node.hazard}')
    if now - node.odom_time > ODOM_STALE:
        raise Abort(1, f'odometry is stale (none for {now - node.odom_time:.1f} s)')
    if node.use_lidar:
        if now - node.scan_time > SCAN_STALE:
            raise Abort(1, f'lidar is stale (no scan for {now - node.scan_time:.1f} s)')
        if forward and node.nearest_front < OBSTACLE_STOP_DISTANCE:
            raise Abort(1, f'obstacle {node.nearest_front:.2f} m ahead (limit {OBSTACLE_STOP_DISTANCE:.2f} m)')
    if now > deadline:
        raise Abort(1, f'total timeout of {TOTAL_TIMEOUT:.0f} s reached')


def run_segment(node, seg, target_heading, deadline):
    """Drive one segment. target_heading is the planned total heading at the end of the segment."""
    period = 1.0 / CONTROL_RATE
    x0, y0, h0 = node.x, node.y, node.heading.total
    start = time.monotonic()
    ref = (node.x, node.y, node.heading.total, start)   # stall detection reference
    next_tick = start
    holds = 0
    while True:
        next_tick += period
        spin_for(node, next_tick - time.monotonic())
        now = time.monotonic()
        h = node.heading.total
        check_safety(node, seg['kind'] != 'turn', deadline)
        if now - start > seg['timeout']:
            raise Abort(1, f'segment timeout ({seg["timeout"]:.1f} s)')
        if now - node.odom_time > ODOM_HOLD:
            # Short odometry dropout: stand still until fresh data arrives (check_safety aborts after ODOM_STALE).
            node.send(0.0, 0.0)
            ref = (node.x, node.y, h, now)   # standing still on purpose is not a stall
            holds += 1
            continue

        if seg['kind'] == 'straight':
            remaining = seg['distance'] - math.hypot(node.x - x0, node.y - y0)
            if remaining < DISTANCE_TOLERANCE:
                break
            v, w = straight_command(remaining, target_heading - h, seg['v'])
        elif seg['kind'] == 'turn':
            remaining = target_heading - h
            if abs(remaining) < ANGLE_TOLERANCE:
                break
            v, w = 0.0, turn_command(remaining, seg['w'])
        else:
            direction = 1.0 if seg['angle'] > 0 else -1.0
            remaining = abs(seg['angle']) - direction * (h - h0)
            if remaining < ANGLE_TOLERANCE:
                break
            v, w = arc_command(remaining, seg['radius'], seg['w'], direction)
        node.send(v, w)

        # Stall: commanding motion but odometry does not change.
        if math.hypot(node.x - ref[0], node.y - ref[1]) > STALL_MIN_MOVE or abs(h - ref[2]) > STALL_MIN_TURN:
            ref = (node.x, node.y, h, now)
        elif now - ref[3] > STALL_TIME:
            raise Abort(1, f'stalled: no movement in odometry for {STALL_TIME:.0f} s')
    node.send(0.0, 0.0)
    if holds:
        log(f'  held still for {holds} control cycles waiting for odometry')
    return time.monotonic() - start


def stand_still(node, seconds, deadline):
    period = 1.0 / CONTROL_RATE
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        node.send(0.0, 0.0)
        spin_for(node, period)
        check_safety(node, False, deadline)


def stop_robot(node):
    """Send zero velocity for STOP_BURST seconds so the stop is not lost."""
    end = time.monotonic() + STOP_BURST
    while time.monotonic() < end:
        node.send(0.0, 0.0)
        time.sleep(1.0 / CONTROL_RATE)


def parse_args():
    p = argparse.ArgumentParser(description='Drive a shape with the TurtleBot 4. MOVES THE ROBOT.')
    p.add_argument('shape', choices=SHAPES)
    p.add_argument('--side', type=float, default=SIDE_LENGTH,
                   help=f'side / leg length in m (default {SIDE_LENGTH}, max {MAX_SIDE_LENGTH})')
    p.add_argument('--speed', type=float, default=LINEAR_SPEED,
                   help=f'forward speed in m/s (default {LINEAR_SPEED}, capped at {MAX_LINEAR_SPEED})')
    p.add_argument('--turn-speed', type=float, default=ANGULAR_SPEED,
                   help=f'turn speed in rad/s (default {ANGULAR_SPEED}, capped at {MAX_ANGULAR_SPEED})')
    p.add_argument('--no-lidar', action='store_true', help='do not use the lidar (NO obstacle stop)')
    p.add_argument('--dry-run', action='store_true', help='run all checks and print the plan, never move')
    p.add_argument('--yes', action='store_true', help='skip the "area clear?" question (needed when detached)')
    return p.parse_args()


def main():
    global motion_active
    args = parse_args()

    # Settings and plan.
    side, msg1 = clamp_setting('--side', args.side, 0.05, MAX_SIDE_LENGTH, 'm')
    speed, msg2 = clamp_setting('--speed', args.speed, MIN_LINEAR_SPEED, MAX_LINEAR_SPEED, 'm/s')
    turn_speed, msg3 = clamp_setting('--turn-speed', args.turn_speed, MIN_ANGULAR_SPEED, MAX_ANGULAR_SPEED, 'rad/s')
    for m in (msg1, msg2, msg3):
        if m:
            log(f'note: {m}')
    segs = add_timing(plan_segments(args.shape, side, CIRCLE_RADIUS), speed, turn_speed)
    expected = sum(s['expected'] for s in segs) + PAUSE * len(segs)
    log(f'shape {args.shape}: {len(segs)} segments, about {expected:.0f} s in total')
    for i, s in enumerate(segs, 1):
        log(f'  {i}. {describe_segment(s)}')
    if expected > TOTAL_TIMEOUT:
        log(f'REFUSING: the plan needs about {expected:.0f} s, more than TOTAL_TIMEOUT {TOTAL_TIMEOUT:.0f} s. '
            'Use a shorter --side or a higher --speed.')
        return 2
    use_lidar = not args.no_lidar
    if not use_lidar:
        log('WARNING: --no-lidar given, the robot will NOT stop for obstacles. Watch it closely.')
    if DockStatus is None:
        log('warning: irobot_create_msgs not found, so no dock check and no hazard (bump/cliff) stop')
    if os.path.exists(STOP_FILE):
        if not args.dry_run:
            log(f'REFUSING: {STOP_FILE} exists (left from an earlier stop). Delete it first: rm {STOP_FILE}')
            return 2
        log(f'warning: {STOP_FILE} exists; a real run would refuse to start until you delete it')

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # we handle Ctrl+C ourselves
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    node = MotionShapes(use_lidar, args.dry_run)
    code = 0
    try:
        # 1. Base answering? Docked?
        got = wait_for(node, '/odom and /dock_status (ROS starts slowly on the Pi)',
                       lambda: node.odom_time is not None and (DockStatus is None or node.is_docked is not None),
                       STARTUP_WAIT)
        if node.odom_time is None:
            raise Abort(2, 'no /odom from the Create 3 base. Restart the base application (see HOW-TO-CONNECT.md)')
        if not got:
            raise Abort(2, 'no /dock_status from the base. Restart the base application (see HOW-TO-CONNECT.md)')
        log(f'odometry OK, docked: {node.is_docked}')
        if node.is_docked:
            if not args.dry_run:
                raise Abort(2, 'the robot is on the dock. Undock it first (see README.md)')
            log('warning: the robot is docked; a real run would refuse to start')

        # 2. Lidar (off while docked, so a dry run on the dock skips it).
        if use_lidar and node.is_docked and args.dry_run:
            log('lidar check skipped: the lidar is switched off while docked')
        elif use_lidar:
            if not wait_for(node, '/scan', lambda: node.scan is not None, STARTUP_WAIT):
                raise Abort(2, 'no /scan from the lidar. Is the robot off the dock? (see README.md)')
            s = node.scan
            log(f'lidar OK: nearest in front {node.nearest_front:.2f} m, '
                f'nearest anywhere {nearest_any(s.ranges, s.range_min, s.range_max):.2f} m')
            first = segs[0]
            if first['kind'] == 'straight':
                need = first['distance'] + OBSTACLE_STOP_DISTANCE
            elif first['kind'] == 'arc':
                need = first['radius'] + OBSTACLE_STOP_DISTANCE
            else:
                need = 0.0   # turning in place on the spot
            if node.nearest_front < need:
                raise Abort(1, f'path not clear: {node.nearest_front:.2f} m in front, need more than {need:.2f} m')

        # 3. Hazards right now (bump, cliff, wheel drop): listen for a moment with a clean slate.
        node.hazard = None
        spin_for(node, 1.0)
        if node.hazard:
            raise Abort(2, f'the base reports a hazard before starting: {node.hazard}')

        if args.dry_run:
            log('dry run: all checks done, nothing was sent to /cmd_vel')
            return 0

        # 4. Ask the person next to the robot.
        if not args.yes:
            if not sys.stdin.isatty():
                raise Abort(2, 'no terminal to ask "is the area clear?". Run with --yes when detached')
            answer = input('The robot is about to MOVE. Is 1 m around it clear and are you next to it? Type yes: ')
            if answer.strip().lower() != 'yes':
                raise Abort(2, 'not confirmed, not moving')

        # 5. Drive.
        motion_active = True
        if stop_request:
            raise Abort(130, f'{stop_request} received')
        x0, y0, yaw0, h_start = node.x, node.y, node.yaw, node.heading.total
        deadline = time.monotonic() + TOTAL_TIMEOUT
        target = h_start
        log('starting. To stop: Ctrl+C, or "touch ~/STOP", or "pkill -INT -f motion_shapes.py"')
        for i, s in enumerate(segs, 1):
            if s['kind'] in ('turn', 'arc'):
                target += s['angle']   # a full circle also adds 360 degrees to the summed heading
            log(f'segment {i}/{len(segs)}: {describe_segment(s)}')
            took = run_segment(node, s, target, deadline)
            log(f'segment {i} done in {took:.1f} s')
            stand_still(node, PAUSE, deadline)

        # 6. Planned vs measured.
        px, py, ph = planned_end_pose(segs)
        dx, dy = node.x - x0, node.y - y0
        mx = math.cos(yaw0) * dx + math.sin(yaw0) * dy     # odometry change in the start frame
        my = -math.sin(yaw0) * dx + math.cos(yaw0) * dy
        mh = node.heading.total - h_start
        log(f'planned end: x {px:+.3f} m, y {py:+.3f} m, heading change {math.degrees(ph):+.1f} deg')
        log(f'odometry end: x {mx:+.3f} m, y {my:+.3f} m, heading change {math.degrees(mh):+.1f} deg')
        log(f'error: position {math.hypot(mx - px, my - py) * 100:.1f} cm, heading {math.degrees(mh - ph):+.1f} deg '
            '(odometry only; the real error is larger, measure it on the floor)')
        log('done')
    except Abort as e:
        code = e.code
        log(('STOPPED: ' if code == 130 else 'ABORTED: ' if code == 1 else 'SETUP FAILED: ') + str(e))
    except KeyboardInterrupt:
        code = 130
        log(f'stopped by {stop_request or "Ctrl+C"} before moving')
    finally:
        if not args.dry_run:
            stop_robot(node)   # always, even after an error: zero velocity for STOP_BURST s
        node.destroy_node()
        rclpy.try_shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
