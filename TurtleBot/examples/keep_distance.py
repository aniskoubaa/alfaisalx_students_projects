"""Hold a set distance to whatever is straight ahead: walk towards the robot and it backs off, walk away and it follows.

THIS PROGRAM MOVES THE ROBOT (forward up to 0.8 m, backward up to 0.2 m). Undock it, clear 1 m all round,
stand in front of it (or hold a big box / board in front of it) and stay next to it.

How it works: a proportional controller on the lidar distance straight ahead (the nearest object within
+/-10 deg, ignoring one or two stray beams):
    speed = GAIN * (distance - target)    forward if too far, backward if too close
    - forward speed at most --speed (default 0.10, capped at 0.15 m/s)
    - backward speed at most 0.05 m/s, and never more than 0.2 m behind the start point
      (the Create 3 base limits backing up, and nothing watches behind the robot)
    - never more than 0.8 m ahead of the start point
    - within +/-DEADBAND of the target, or nothing within ENGAGE_RANGE ahead: stand still
    - heading is held at the start heading
It runs for --duration s (default and max 60 s), then stops. All motion_shapes safety checks apply while
moving forward (obstacle within 0.25 m in +/-30 deg ahead, hazards, stale odometry/lidar, Ctrl+C / SIGTERM /
~/STOP), plus a 1.2 m fence and a total timeout (motion_common.Guard). If the base reports its BACKUP_LIMIT
hazard, the robot stops reversing for the rest of the run.

Needs motion_shapes.py and motion_common.py in the same folder. Run it on the robot:
    python3 keep_distance.py --dry-run
    python3 keep_distance.py --target 0.6 --duration 30
    setsid nohup python3 ~/robot_code/keep_distance.py --yes > ~/robot_code/keep.log 2>&1 &

How to stop it: Ctrl+C, or  touch ~/STOP  (then rm ~/STOP), or  pkill -INT -f keep_distance.py
Exit codes: 0 done, 1 aborted by a safety check, 2 setup failure, 130 stopped by you.
"""
import argparse
import math
import sys
import time

import motion_common as mc
import motion_shapes as ms
from motion_shapes import Abort, log

# ---------------------------------------------------------------- parameters
TARGET_DISTANCE = 0.60        # m, distance to hold (default --target)
MIN_TARGET, MAX_TARGET = 0.40, 1.0
GAIN = 0.5                    # 1/s, speed per metre of distance error
DEADBAND = 0.03               # m, closer to the target than this: stand still
MIN_COMMAND = 0.02            # m/s, smallest speed actually sent (smaller commands would not move the base)
FORWARD_SPEED = 0.10          # m/s, default max forward speed (capped at motion_shapes.MAX_LINEAR_SPEED 0.15)
REVERSE_SPEED = 0.05          # m/s, max backward speed (hard cap)
MAX_BEHIND = 0.20             # m, never back up more than this behind the start point
MAX_AHEAD = 0.80              # m, never drive more than this ahead of the start point
ENGAGE_RANGE = 1.5            # m, ignore objects farther than this (do not chase across the room)
FRONT_HALF_ANGLE = math.radians(10)   # "straight ahead" for the distance measurement
DURATION = 60.0               # s, default and maximum run time
SCAN_HOLD = 0.5               # s, scan older than this: stand still until a new one arrives
REPORT_EVERY = 1.0            # s, print a status line this often


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def control(front, target, progress, max_fwd, reverse_allowed):
    """Speed command (m/s, + forward) for distance `front`, with the robot `progress` m ahead of its start."""
    if not math.isfinite(front) or front > ENGAGE_RANGE:
        return 0.0
    error = front - target
    if abs(error) < DEADBAND:
        return 0.0
    v = GAIN * error
    v = max(-REVERSE_SPEED, min(max_fwd, v))
    if abs(v) < MIN_COMMAND:
        v = math.copysign(MIN_COMMAND, v)
    if v > 0 and progress >= MAX_AHEAD:
        return 0.0
    if v < 0 and (progress <= -MAX_BEHIND or not reverse_allowed):
        return 0.0
    return v


def parse_args():
    p = argparse.ArgumentParser(description='Keep a set distance to the object ahead. MOVES THE ROBOT.')
    p.add_argument('--target', type=float, default=TARGET_DISTANCE,
                   help=f'distance to hold in m (default {TARGET_DISTANCE}, {MIN_TARGET}..{MAX_TARGET})')
    p.add_argument('--duration', type=float, default=DURATION, help=f'run time in s (max {DURATION:.0f})')
    p.add_argument('--speed', type=float, default=FORWARD_SPEED, help='max forward speed in m/s (capped at 0.15)')
    p.add_argument('--dry-run', action='store_true', help='checks only (prints what it would do), never moves')
    p.add_argument('--yes', action='store_true', help='skip the "area clear?" question (needed when detached)')
    return p.parse_args()


def main():
    args = parse_args()
    target, m1 = ms.clamp_setting('--target', args.target, MIN_TARGET, MAX_TARGET, 'm')
    duration, m2 = ms.clamp_setting('--duration', args.duration, 1.0, DURATION, 's')
    max_fwd, m3 = ms.clamp_setting('--speed', args.speed, ms.MIN_LINEAR_SPEED, ms.MAX_LINEAR_SPEED, 'm/s')
    for m in (m1, m2, m3):
        if m:
            log(f'note: {m}')
    code = mc.preflight(args.dry_run)
    if code is not None:
        return code

    mc.init_ros()
    node = mc.FrontNode(True, args.dry_run, FRONT_HALF_ANGLE, 'near')

    def body():
        if not mc.startup_checks(node, args.dry_run, True, 0.0):
            log('dry run on the dock: no lidar. Nothing was sent to /cmd_vel')
            return 0
        v0 = control(node.front, target, 0.0, max_fwd, True)
        log(f'object straight ahead: {node.front:.2f} m (target {target:.2f} m) -> would start with '
            f'{v0:+.3f} m/s; runs {duration:.0f} s, range -{MAX_BEHIND:.2f}..+{MAX_AHEAD:.2f} m')
        if args.dry_run:
            log('dry run: all checks done, nothing was sent to /cmd_vel')
            return 0

        mc.confirm(args.yes)
        mc.start_motion()
        guard = mc.Guard(node, duration + 10.0).install()
        log('starting. To stop: Ctrl+C, or "touch ~/STOP", or "pkill -INT -f keep_distance.py"')
        x0, y0, yaw0, h0 = node.x, node.y, node.yaw, node.heading.total
        period = 1.0 / ms.CONTROL_RATE
        start = time.monotonic()
        next_tick = start
        next_report = start
        ref = (0.0, start)       # stall detection: (progress, time)
        reverse_allowed = True
        v = 0.0
        while time.monotonic() - start < duration:
            next_tick += period
            ms.spin_for(node, next_tick - time.monotonic())
            now = time.monotonic()
            progress, side = mc.to_start_frame(x0, y0, yaw0, node.x, node.y)
            if reverse_allowed and node.backup_limit_time is not None:
                reverse_allowed = False
                log('the base reported BACKUP_LIMIT: no more reversing in this run')
            if now - node.odom_time > ms.ODOM_HOLD or now - node.scan_time > SCAN_HOLD:
                guard.check(node, False)   # short dropout: stand still (Guard aborts after ODOM_STALE/SCAN_STALE)
                v = 0.0
                node.send(0.0, 0.0)
                ref = (progress, now)
                continue
            v = control(node.front, target, progress, max_fwd, reverse_allowed)
            guard.check(node, v > 0)       # all checks; the obstacle stop only applies when driving forward
            w = 0.0
            if v != 0.0:
                w = max(-ms.MAX_HEADING_CORRECTION,
                        min(ms.MAX_HEADING_CORRECTION, ms.HEADING_HOLD_GAIN * (h0 - node.heading.total)))
            node.send(v, w)
            if v == 0.0 or abs(progress - ref[0]) > ms.STALL_MIN_MOVE:
                ref = (progress, now)
            elif now - ref[1] > ms.STALL_TIME:
                raise Abort(1, f'stalled: no movement in odometry for {ms.STALL_TIME:.0f} s')
            if now >= next_report:
                next_report += REPORT_EVERY
                log(f'  t {now - start:4.1f} s  object {node.front:5.2f} m  speed {v:+.3f} m/s  '
                    f'position {progress:+.3f} m (side {side:+.3f})')
        node.send(0.0, 0.0)
        progress, side = mc.to_start_frame(x0, y0, yaw0, node.x, node.y)
        log(f'time up after {duration:.0f} s: object {node.front:.2f} m, robot {progress:+.3f} m from the start')
        log('done')
        return 0

    return mc.run_guarded(node, args.dry_run, body)


if __name__ == '__main__':
    sys.exit(main())
