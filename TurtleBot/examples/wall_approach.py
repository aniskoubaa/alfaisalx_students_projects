"""Drive slowly straight towards a wall until the lidar says it is --target m away; compare odometry with lidar.

THIS PROGRAM MOVES THE ROBOT (forward only, at most 1.0 m). Undock it, point it at a wall or a big flat box
0.5 to 1.5 m away, clear the floor in between, stay next to it.

How it works:
  1. Stands still for SETTLE_TIME s and takes the median lidar distance straight ahead (+/-5 deg) = start range.
  2. Plans to drive  min(start range - target, --max-travel)  metres, so even without the lidar it can never
     end closer than the target (as long as the wall does not move).
  3. Drives forward with motion_shapes.straight_command (slows down near the goal, holds the heading) and
     stops as soon as EITHER the lidar range (corrected for the distance driven since that scan) reaches the
     target OR odometry reaches the planned travel. It never drives closer than the target on purpose.
  4. Stands still again, takes the end range, and prints the odometry-vs-lidar calibration:
     distance driven by odometry, change of lidar range, their ratio and difference, and the slope of
     lidar range against odometry during the drive (should be -1.00).
All motion_shapes safety checks apply (obstacle within 0.25 m in +/-30 deg, hazards, stale odometry/lidar,
stall, Ctrl+C / SIGTERM / ~/STOP), plus a 1.2 m fence and a total timeout (motion_common.Guard).

Needs motion_shapes.py and motion_common.py in the same folder. Run it on the robot:
    python3 wall_approach.py --dry-run                     # measures the start range, never moves
    python3 wall_approach.py --target 0.5
    setsid nohup python3 ~/robot_code/wall_approach.py --yes --csv ~/robot_code/wall.csv > ~/robot_code/wall.log 2>&1 &

How to stop it: Ctrl+C, or  touch ~/STOP  (then rm ~/STOP), or  pkill -INT -f wall_approach.py
Exit codes: 0 done (also "already at the target"), 1 aborted by a safety check, 2 setup failure, 130 stopped by you.
"""
import argparse
import math
import statistics
import sys
import time

import motion_common as mc
import motion_shapes as ms
from motion_shapes import Abort, log

# ---------------------------------------------------------------- parameters
TARGET_DISTANCE = 0.50        # m, stop when the wall is this far from the lidar (default --target)
MIN_TARGET = 0.30             # m, never accept a closer target
MAX_TARGET = 2.0              # m
MAX_TRAVEL = 1.0              # m, never drive farther than this (--max-travel may only lower it)
MIN_TRAVEL = 0.02             # m, closer to the target than this: nothing to do
APPROACH_SPEED = 0.08         # m/s, default --speed (capped at motion_shapes.MAX_LINEAR_SPEED 0.15)
FRONT_HALF_ANGLE = math.radians(5)   # "straight ahead" for the range measurement
TARGET_TOLERANCE = 0.005      # m, stop when the estimated range is within this of the target
SETTLE_TIME = 1.5             # s, stand still this long before and after to average the lidar range
SCAN_HOLD = 0.5               # s, scan older than this: stand still until a new one arrives
TOTAL_TIMEOUT = 90.0          # s, whole run including settling
DRIVE_TIMEOUT_FACTOR = 2.0    # drive step timeout = factor * travel / speed + extra
DRIVE_TIMEOUT_EXTRA = 10.0    # s


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def plan_travel(start_range, target, max_travel):
    """Metres to drive: what is needed to reach the target, never more than max_travel, never negative."""
    if not math.isfinite(start_range):
        return 0.0
    return max(0.0, min(max_travel, start_range - target))


def fit_slope(xs, ys):
    """Least-squares slope of ys against xs (None if fewer than 3 points or no spread)."""
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx < 1e-6:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def median_front_since(node, t0):
    vals = [f for (t, f, _, _) in node.history if t >= t0 and math.isfinite(f)]
    return statistics.median(vals) if vals else float('inf'), len(vals)


# ---------------------------------------------------------------- driving
def measure(node, seconds, moving_allowed):
    """Median front range over `seconds` of standing still (with all safety checks once moving is allowed)."""
    t0 = time.monotonic()
    if moving_allowed:
        ms.stand_still(node, seconds, None)
    else:
        ms.spin_for(node, seconds)
    return median_front_since(node, t0)


def drive(node, guard, travel, target, speed, samples):
    """Forward until the lidar range reaches target or odometry reaches travel. Returns the stop reason."""
    period = 1.0 / ms.CONTROL_RATE
    timeout = DRIVE_TIMEOUT_FACTOR * travel / speed + DRIVE_TIMEOUT_EXTRA
    x0, y0, yaw0, h0 = node.x, node.y, node.yaw, node.heading.total
    start = time.monotonic()
    next_tick = start
    ref = (0.0, start)          # stall detection: (progress, time)
    last_scan = node.scan_count
    holds = 0
    while True:
        next_tick += period
        ms.spin_for(node, next_tick - time.monotonic())
        now = time.monotonic()
        guard.check(node, True)
        if now - start > timeout:
            raise Abort(1, f'drive timeout ({timeout:.1f} s)')
        if now - node.odom_time > ms.ODOM_HOLD or now - node.scan_time > SCAN_HOLD:
            node.send(0.0, 0.0)          # short dropout: stand still (Guard aborts after ODOM_STALE/SCAN_STALE)
            ref = (ref[0], now)
            holds += 1
            continue
        progress, _ = mc.to_start_frame(x0, y0, yaw0, node.x, node.y)
        t_scan, front, sx, sy = node.history[-1]
        at_scan, _ = mc.to_start_frame(x0, y0, yaw0, sx, sy)
        estimate = front - (progress - at_scan)      # range now = last range - distance driven since that scan
        if node.scan_count != last_scan:
            last_scan = node.scan_count
            if math.isfinite(front):
                samples.append((t_scan - start, at_scan, front))
        if estimate <= target + TARGET_TOLERANCE:
            reason = f'lidar range reached the target (estimate {estimate:.3f} m)'
            break
        if progress >= travel - ms.DISTANCE_TOLERANCE:
            reason = f'odometry reached the planned travel ({progress:.3f} m)'
            break
        remaining = min(estimate - target, travel - progress)
        v, w = ms.straight_command(remaining, h0 - node.heading.total, speed)
        node.send(v, w)
        if progress - ref[0] > ms.STALL_MIN_MOVE:
            ref = (progress, now)
        elif now - ref[1] > ms.STALL_TIME:
            raise Abort(1, f'stalled: no movement in odometry for {ms.STALL_TIME:.0f} s')
    node.send(0.0, 0.0)
    if holds:
        log(f'  held still for {holds} control cycles waiting for odometry or lidar')
    return reason, (x0, y0, yaw0)


def parse_args():
    p = argparse.ArgumentParser(description='Approach a wall to a target lidar distance. MOVES THE ROBOT.')
    p.add_argument('--target', type=float, default=TARGET_DISTANCE,
                   help=f'stop distance in m (default {TARGET_DISTANCE}, min {MIN_TARGET})')
    p.add_argument('--max-travel', type=float, default=MAX_TRAVEL, help=f'max drive in m (<= {MAX_TRAVEL})')
    p.add_argument('--speed', type=float, default=APPROACH_SPEED, help='forward speed in m/s (capped at 0.15)')
    p.add_argument('--csv', help='write the (time, odometry progress, lidar range) samples to this CSV file')
    p.add_argument('--dry-run', action='store_true', help='checks and start range only, never moves')
    p.add_argument('--yes', action='store_true', help='skip the "area clear?" question (needed when detached)')
    return p.parse_args()


def main():
    args = parse_args()
    notes = []
    target, m = ms.clamp_setting('--target', args.target, MIN_TARGET, MAX_TARGET, 'm')
    notes.append(m)
    max_travel, m = ms.clamp_setting('--max-travel', args.max_travel, 0.05, MAX_TRAVEL, 'm')
    notes.append(m)
    speed, m = ms.clamp_setting('--speed', args.speed, ms.MIN_LINEAR_SPEED, ms.MAX_LINEAR_SPEED, 'm/s')
    notes.append(m)
    for m in notes:
        if m:
            log(f'note: {m}')
    code = mc.preflight(args.dry_run)
    if code is not None:
        return code

    mc.init_ros()
    node = mc.FrontNode(True, args.dry_run, FRONT_HALF_ANGLE, 'median')

    def body():
        if not mc.startup_checks(node, args.dry_run, True, 0.0):
            log('dry run on the dock: no lidar, so no start range. Nothing was sent to /cmd_vel')
            return 0
        start_range, n = measure(node, SETTLE_TIME, False)
        travel = plan_travel(start_range, target, max_travel)
        log(f'range straight ahead (median of {n} scans, +/-{math.degrees(FRONT_HALF_ANGLE):.0f} deg): '
            f'{start_range:.3f} m; target {target:.2f} m; would drive {travel:.3f} m at {speed:.2f} m/s')
        if not math.isfinite(start_range):
            raise Abort(2, 'no valid lidar range straight ahead. Point the robot at a wall or a box')
        if start_range - target > max_travel:
            log(f'note: the wall is more than {max_travel:.2f} m beyond the target; '
                f'the robot will stop after {max_travel:.2f} m, short of the target')
        if travel < MIN_TRAVEL:
            log('already at (or inside) the target distance: not moving')
            return 0
        if args.dry_run:
            log('dry run: all checks done, nothing was sent to /cmd_vel')
            return 0

        mc.confirm(args.yes)
        mc.start_motion()
        guard = mc.Guard(node, TOTAL_TIMEOUT).install()
        log('starting. To stop: Ctrl+C, or "touch ~/STOP", or "pkill -INT -f wall_approach.py"')
        # Measure again now that the person has confirmed (someone may have moved since the first look).
        start_range, n = measure(node, SETTLE_TIME, True)
        travel = plan_travel(start_range, target, max_travel)
        if not math.isfinite(start_range):
            raise Abort(1, 'lost the lidar range straight ahead')
        log(f'start range {start_range:.3f} m (median of {n} scans), driving up to {travel:.3f} m')
        if travel < MIN_TRAVEL:
            log('already at the target distance: not moving')
            return 0
        samples = []
        reason, (x0, y0, yaw0) = drive(node, guard, travel, target, speed, samples)
        log(f'stopped: {reason}')
        end_range, n = measure(node, SETTLE_TIME, True)
        odom_fwd, odom_side = mc.to_start_frame(x0, y0, yaw0, node.x, node.y)
        lidar_change = start_range - end_range
        log('odometry vs lidar calibration:')
        log(f'  lidar range: start {start_range:.3f} m, end {end_range:.3f} m (median of {n} scans), '
            f'target {target:.3f} m')
        log(f'  odometry: forward {odom_fwd:.3f} m, sideways {odom_side:+.3f} m')
        log(f'  lidar range change {lidar_change:.3f} m vs odometry {odom_fwd:.3f} m: '
            f'difference {(lidar_change - odom_fwd) * 1000:+.0f} mm'
            + (f', ratio lidar/odometry {lidar_change / odom_fwd:.3f}' if odom_fwd > 0.05 else ''))
        slope = fit_slope([s[1] for s in samples], [s[2] for s in samples])
        if slope is not None:
            log(f'  slope of lidar range vs odometry during the drive: {slope:.3f} (ideal -1.000, {len(samples)} scans)')
        if math.isfinite(end_range) and end_range < target - 0.02:
            log(f'  warning: ended {(target - end_range) * 100:.0f} cm closer than the target')
        if args.csv:
            with open(args.csv, 'w') as f:
                f.write('t_s,odom_progress_m,lidar_front_m\n')
                for t, p, r in samples:
                    f.write(f'{t:.3f},{p:.4f},{r:.4f}\n')
            log(f'  wrote {len(samples)} samples to {args.csv}')
        log('done')
        return 0

    return mc.run_guarded(node, args.dry_run, body)


if __name__ == '__main__':
    sys.exit(main())
