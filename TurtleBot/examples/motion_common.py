"""Shared safety plumbing for the programs that move the robot: more_shapes.py, wall_approach.py and
keep_distance.py. This file is not a program; copy it to the robot next to them (and next to
motion_shapes.py, which it builds on).

What it adds on top of motion_shapes.py:
  - wait_steady_odom(): waits for 3 s of steady /odom as the last step before moving (start_motion does it too).
  - startup_checks(): the same start-up sequence as motion_shapes.py (wait for /odom and /dock_status,
    refuse if docked, wait for /scan, check the way ahead, check for hazards), plus confirm() for the
    "is the area clear?" question and start_motion().
  - Guard: wraps motion_shapes.check_safety so that EVERY safety check (also the ones inside
    motion_shapes.run_segment and stand_still) additionally enforces this program's own total timeout
    and a "fence": abort if odometry says the robot is more than FENCE_RADIUS from where it started.
  - FrontNode: the MotionShapes node plus a narrow "straight ahead" lidar distance (front) and a record of
    the base's BACKUP_LIMIT hazard (which motion_shapes ignores).
  - run_guarded(): the try / except / finally that always sends zero velocity at the end.

  - shape_parser(), common_argv(), run_shape(), studio_confirmed(): the shared part of the one-program-per-shape
    wrappers (shape_circle.py, shape_square.py, ...). They hold no motion logic: they pass their options on to
    motion_shapes.main or more_shapes.main, so every safety layer is the one of those programs.

Stop signals (Ctrl+C, SIGTERM, ~/STOP) are handled by motion_shapes.on_signal / check_safety, so the
stop behaviour is identical to motion_shapes.py.
"""
import argparse
import math
import os
import signal
import sys
import time

import rclpy
from rclpy.signals import SignalHandlerOptions

import motion_shapes as ms
from motion_shapes import Abort, log

# ---------------------------------------------------------------- parameters
FENCE_RADIUS = 1.2          # m, abort if odometry puts the robot farther than this from its start point
PLAN_MAX_RADIUS = 1.0       # m, a planned path may not go farther than this from the start point
                            # (FENCE_RADIUS is a little larger so odometry noise and overshoot do not trip it)


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def sector_ranges(ranges, angle_min, angle_increment, range_min, range_max, offset, half_angle):
    """Sorted list of the valid ranges within +/-half_angle of straight ahead of the robot.

    offset is the lidar's yaw in the robot frame (a beam at laser angle a points at robot angle a + offset).
    """
    out = []
    for i, r in enumerate(ranges):
        if not (range_min < r < range_max):   # also drops inf and nan
            continue
        a = ms.wrap_angle(angle_min + i * angle_increment + offset)
        if abs(a) <= half_angle:
            out.append(r)
    out.sort()
    return out


def front_distance(values, mode):
    """One distance from the sorted sector ranges.

    mode 'median': the middle value (robust distance to a wall straight ahead).
    mode 'near':   the 3rd smallest value (the nearest object, ignoring one or two stray beams).
    Returns inf if there are no values.
    """
    if not values:
        return float('inf')
    if mode == 'median':
        n = len(values)
        return values[n // 2] if n % 2 else 0.5 * (values[n // 2 - 1] + values[n // 2])
    return values[min(2, len(values) - 1)]


def to_start_frame(x0, y0, yaw0, x, y):
    """Odometry position (x, y) expressed in the start frame (x forward, y left at the start)."""
    dx, dy = x - x0, y - y0
    return math.cos(yaw0) * dx + math.sin(yaw0) * dy, -math.sin(yaw0) * dx + math.cos(yaw0) * dy


# ---------------------------------------------------------------- ROS node
class FrontNode(ms.MotionShapes):
    """MotionShapes plus a narrow front distance, a short scan history and BACKUP_LIMIT tracking."""

    def __init__(self, use_lidar, dry_run, front_half_angle, front_mode, history=200):
        self.front_half_angle = front_half_angle
        self.front_mode = front_mode
        self.front = float('inf')     # distance straight ahead (see front_distance)
        self.front_beams = 0          # number of valid beams in the front sector of the last scan
        self.scan_count = 0
        self.history = []             # (monotonic time, front, odom x, odom y) of the last scans
        self.history_len = history
        self.backup_limit_time = None
        super().__init__(use_lidar, dry_run)

    def on_scan(self, msg):
        super().on_scan(msg)          # sets nearest_front (+/-30 deg obstacle check), scan, scan_time
        if self.lidar_offset is None:
            return
        values = sector_ranges(msg.ranges, msg.angle_min, msg.angle_increment, msg.range_min, msg.range_max,
                               self.lidar_offset, self.front_half_angle)
        self.front = front_distance(values, self.front_mode)
        self.front_beams = len(values)
        self.scan_count += 1
        self.history.append((self.scan_time, self.front, self.x, self.y))
        del self.history[:-self.history_len]

    def on_hazard(self, msg):
        super().on_hazard(msg)        # BUMP, CLIFF, ... -> self.hazard (BACKUP_LIMIT is ignored there)
        for d in msg.detections:
            if ms.HazardDetection is not None and d.type == ms.HazardDetection.BACKUP_LIMIT:
                self.backup_limit_time = time.monotonic()


# ---------------------------------------------------------------- guard: total timeout + fence
_original_check_safety = ms.check_safety


class Guard:
    """Adds a total timeout and a distance fence to motion_shapes.check_safety.

    install() replaces motion_shapes.check_safety with self.check, so run_segment and stand_still from
    motion_shapes use it too. The original check runs first (stop request, STOP file, hazard, stale
    odometry/lidar, obstacle ahead); its own deadline is disabled because this guard keeps the deadline.
    """

    def __init__(self, node, total_timeout, fence_radius=FENCE_RADIUS):
        self.x0, self.y0 = node.x, node.y
        self.total_timeout = total_timeout
        self.deadline = time.monotonic() + total_timeout
        self.fence_radius = fence_radius

    def install(self):
        ms.check_safety = self.check
        return self

    def check(self, node, forward, _deadline=None):
        _original_check_safety(node, forward, math.inf)
        if time.monotonic() > self.deadline:
            raise Abort(1, f'total timeout of {self.total_timeout:.0f} s reached')
        d = math.hypot(node.x - self.x0, node.y - self.y0)
        if d > self.fence_radius:
            raise Abort(1, f'left the safety fence: {d:.2f} m from the start point (limit {self.fence_radius:.2f} m)')


# ---------------------------------------------------------------- start-up and shutdown
def preflight(dry_run):
    """Checks before ROS starts. Returns an exit code to stop with, or None to continue."""
    if ms.DockStatus is None:
        log('warning: irobot_create_msgs not found, so no dock check and no hazard (bump/cliff) stop')
    if os.path.exists(ms.STOP_FILE):
        if not dry_run:
            log(f'REFUSING: {ms.STOP_FILE} exists (left from an earlier stop). Delete it first: rm {ms.STOP_FILE}')
            return 2
        log(f'warning: {ms.STOP_FILE} exists; a real run would refuse to start until you delete it')
    return None


def init_ros():
    """rclpy without its own Ctrl+C handling: motion_shapes.on_signal stops the robot cleanly instead."""
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, ms.on_signal)
    signal.signal(signal.SIGTERM, ms.on_signal)


def startup_checks(node, dry_run, use_lidar, need_front):
    """Steps 1-3 of motion_shapes.main. need_front: metres that must be clear ahead (0 = no check)."""
    got = ms.wait_for(node, '/odom and /dock_status (ROS starts slowly on the Pi)',
                      lambda: node.odom_time is not None and (ms.DockStatus is None or node.is_docked is not None),
                      ms.STARTUP_WAIT)
    if node.odom_time is None:
        raise Abort(2, 'no /odom from the Create 3 base. Restart the base application (see HOW-TO-CONNECT.md)')
    if not got:
        raise Abort(2, 'no /dock_status from the base. Restart the base application (see HOW-TO-CONNECT.md)')
    log(f'odometry OK, docked: {node.is_docked}')
    if node.is_docked:
        if not dry_run:
            raise Abort(2, 'the robot is on the dock. Undock it first (see README.md)')
        log('warning: the robot is docked; a real run would refuse to start')

    lidar_checked = False
    if use_lidar and node.is_docked and dry_run:
        log('lidar check skipped: the lidar is switched off while docked')
    elif use_lidar:
        if not ms.wait_for(node, '/scan', lambda: node.scan is not None, ms.STARTUP_WAIT):
            raise Abort(2, 'no /scan from the lidar. Is the robot off the dock? (see README.md)')
        ms.spin_for(node, 0.5)    # a few more scans so the front distance is not from a single scan
        s = node.scan
        front = getattr(node, 'front', None)
        extra = f', straight ahead {front:.2f} m' if front is not None else ''
        log(f'lidar OK: nearest within +/-30 deg in front {node.nearest_front:.2f} m{extra}, '
            f'nearest anywhere {ms.nearest_any(s.ranges, s.range_min, s.range_max):.2f} m')
        if need_front > 0 and node.nearest_front < need_front:
            raise Abort(1, f'path not clear: {node.nearest_front:.2f} m in front, need more than {need_front:.2f} m')
        lidar_checked = True

    node.hazard = None
    ms.spin_for(node, 1.0)
    if node.hazard:
        raise Abort(2, f'the base reports a hazard before starting: {node.hazard}')
    return lidar_checked


def confirm(yes):
    """Ask the person next to the robot, unless --yes. Raises Abort(2) if not confirmed."""
    if yes:
        return
    if not sys.stdin.isatty():
        raise Abort(2, 'no terminal to ask "is the area clear?". Run with --yes when detached')
    try:
        answer = input('The robot is about to MOVE. Is 1 m around it clear and are you next to it? Type yes: ')
    except EOFError:
        answer = ''
    if answer.strip().lower() != 'yes':
        raise Abort(2, 'not confirmed, not moving')


def wait_steady_odom(node):
    """Wait for 3 s of steady /odom (motion_shapes.wait_for_steady_odom). Call it as the very last step before
    moving, also in a dry run; it raises Abort(2) after 30 s."""
    ms.wait_for_steady_odom(node)


def start_motion(node):
    """Waits for steady /odom (the last check), then: from here on, Ctrl+C / SIGTERM no longer raise; the control loop sees them and stops the robot."""
    wait_steady_odom(node)
    ms.motion_active = True
    if ms.stop_request:
        raise Abort(130, f'{ms.stop_request} received')


def run_guarded(node, dry_run, body):
    """Run body() and return an exit code. Always sends zero velocity at the end (unless dry run)."""
    code = 0
    try:
        code = body() or 0
    except Abort as e:
        code = e.code
        log(('STOPPED: ' if code == 130 else 'ABORTED: ' if code == 1 else 'SETUP FAILED: ') + str(e))
    except KeyboardInterrupt:
        code = 130
        log(f'stopped by {ms.stop_request or "Ctrl+C"} before moving')
    finally:
        if not dry_run:
            ms.stop_robot(node)   # zero velocity for STOP_BURST s, even after an error
        node.destroy_node()
        rclpy.try_shutdown()
    return code


# ---------------------------------------------------------------- one-program-per-shape wrappers
STUDIO_MARKER = 'STUDIO_MOTION_CONFIRMED'   # set to "1" by TurtleBot Studio's robot_bridge.py, only for a program
                                            # that moves the robot and that the person confirmed in Studio's dialog


def studio_confirmed(env=None, stdin_is_tty=None):
    """True if Studio has already asked "is the area clear?" for this very run.

    Counts only when there is no terminal to ask on (Studio starts programs with stdin closed): in a terminal the
    normal question is still asked, even if the variable is set by mistake. --dry-run never needs it."""
    env = os.environ if env is None else env
    if stdin_is_tty is None:
        stdin_is_tty = sys.stdin is not None and sys.stdin.isatty()
    return env.get(STUDIO_MARKER) == '1' and not stdin_is_tty


def shape_parser(doc, prog, no_lidar=True):
    """argparse parser with the options every shape program shares (same defaults and caps as the base programs)."""
    p = argparse.ArgumentParser(prog=prog, description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--speed', type=float, default=ms.LINEAR_SPEED,
                   help=f'forward speed in m/s (default {ms.LINEAR_SPEED}, capped at {ms.MAX_LINEAR_SPEED})')
    p.add_argument('--turn-speed', type=float, default=ms.ANGULAR_SPEED,
                   help=f'turn speed in rad/s (default {ms.ANGULAR_SPEED}, capped at {ms.MAX_ANGULAR_SPEED})')
    if no_lidar:
        p.add_argument('--no-lidar', action='store_true', help='do not use the lidar (NO obstacle stop)')
    p.add_argument('--dry-run', action='store_true', help='run all checks and print the plan, never move')
    p.add_argument('--yes', action='store_true',
                   help='skip the "area clear?" question (needed when there is no terminal; Studio asks you itself)')
    return p


def common_argv(args):
    """The shared options of a parsed wrapper, as an argv list for motion_shapes.main / more_shapes.main."""
    out = ['--speed', repr(args.speed), '--turn-speed', repr(args.turn_speed)]
    for flag, attr in (('--no-lidar', 'no_lidar'), ('--dry-run', 'dry_run'), ('--yes', 'yes')):
        if getattr(args, attr, False):
            out.append(flag)
    return out


def run_shape(module, argv, prog, what, env=None, stdin_is_tty=None):
    """Print which shape this is and run module.main(argv) (motion_shapes or more_shapes). Returns its exit code."""
    argv = list(argv)
    log(f'{prog}: drives {what}. THIS PROGRAM MOVES THE ROBOT.')
    log(f'stop it with Ctrl+C, the Studio Stop button, "touch ~/STOP" or "pkill -INT -f {prog}"')
    if '--yes' not in argv and '--dry-run' not in argv and studio_confirmed(env, stdin_is_tty):
        argv.append('--yes')
        log(f'started from TurtleBot Studio ({STUDIO_MARKER}=1): Studio already asked you to confirm, '
            'so the terminal question is skipped. All other safety checks stay on.')
    return module.main(argv)
