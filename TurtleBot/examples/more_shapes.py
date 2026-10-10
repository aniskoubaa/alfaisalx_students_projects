"""More shapes for the TurtleBot 4: polygon, star, circle, square_spiral, zigzag, and a repeatability test.

THIS PROGRAM MOVES THE ROBOT. Undock it, clear about 1 m of floor all round, stay next to it.
Speed is capped at 0.15 m/s and 1.0 rad/s whatever you ask for.

How it works: each shape is a list of segments (drive straight, turn in place, drive a circle) driven by
motion_shapes.run_segment, closed-loop on /odom, with all the motion_shapes safety checks (obstacle ahead,
bump/cliff hazards, stale odometry or lidar, stall, segment timeouts, Ctrl+C / SIGTERM / ~/STOP).
On top of that (motion_common.py): the planned path may not go more than 1.0 m from the start point
(checked before moving), odometry may not go more than 1.2 m from it (checked while moving), and the whole
run has a total timeout of 1.5 x the expected time + 20 s (at most 300 s).

Shapes:
    polygon        N sides (--sides, 3..12) of --side m, turning left 360/N deg at each corner
    star           5-point star: 5 x (forward --side, turn left 144 deg)
    circle         one full left circle of --radius m
    square_spiral  legs of --step, --step, 2*step, 2*step, ... up to --max-leg (<= 0.5 m), turning left 90 deg
    zigzag         slalom along a line: turn +30, then --legs legs of --side with -60/+60 turns in between,
                   then turn back to the start heading (ends --legs * side * cos30 ahead of the start,
                   on the start line when --legs is even, 0.5 * side * sin30 off it when odd)
    repeatability  drive a closed shape (--shape, e.g. square) --loops times and print the odometry error
                   after each loop (how much the end point drifts loop after loop)

Needs motion_shapes.py and motion_common.py in the same folder. Run it on the robot (dry run first):
    python3 more_shapes.py polygon --sides 6 --side 0.3 --dry-run
    python3 more_shapes.py star --dry-run
    python3 more_shapes.py circle --radius 0.25 --dry-run
    python3 more_shapes.py square_spiral --dry-run
    python3 more_shapes.py zigzag --legs 4 --dry-run
    python3 more_shapes.py repeatability --shape square --loops 3 --dry-run
Detached (recommended, needs --yes):
    setsid nohup python3 ~/robot_code/more_shapes.py star --yes > ~/robot_code/more_shapes.log 2>&1 &
    tail -f ~/robot_code/more_shapes.log

How to stop it: Ctrl+C, or  touch ~/STOP  (then rm ~/STOP), or  pkill -INT -f more_shapes.py
Exit codes: 0 done, 1 aborted by a safety check, 2 setup failure / refused plan, 130 stopped by you.
"""
import argparse
import math
import sys

import motion_common as mc
import motion_shapes as ms
from motion_shapes import log

# ---------------------------------------------------------------- parameters
SIDE_LENGTH = 0.30            # m, default side of polygon / star, leg of zigzag
MAX_SIDE_LENGTH = 0.60        # m, longest side allowed from the command line
POLYGON_SIDES = 5             # default number of polygon sides
MIN_SIDES, MAX_SIDES = 3, 12
STAR_TURN = math.radians(144)  # a 5-point star: 5 x 144 deg = 720 deg, back to the start heading
CIRCLE_RADIUS = 0.25          # m, default radius of the circle
MIN_RADIUS, MAX_RADIUS = 0.15, 0.45   # m, 2 x radius must stay within PLAN_MAX_RADIUS
SPIRAL_STEP = 0.10            # m, square_spiral leg growth
SPIRAL_MAX_LEG = 0.50         # m, square_spiral longest leg (hard cap 0.5 m)
ZIGZAG_LEGS = 4               # default number of zigzag legs
ZIGZAG_SIDE = 0.25            # m, default zigzag leg (4 x 0.25 x cos30 = 0.87 m, inside the 1 m limit)
ZIGZAG_ANGLE = math.radians(60)   # turn between zigzag legs (alternating sign)
MAX_ZIGZAG_LEGS = 8
LOOPS = 3                     # default repeatability loops
MAX_LOOPS = 5
LINEAR_SPEED = 0.10           # m/s, default forward speed (capped at motion_shapes.MAX_LINEAR_SPEED 0.15)
ANGULAR_SPEED = 0.5           # rad/s, default turn speed (capped at motion_shapes.MAX_ANGULAR_SPEED 1.0)
TIMEOUT_FACTOR = 1.5          # total timeout = TIMEOUT_FACTOR * expected time + TIMEOUT_EXTRA ...
TIMEOUT_EXTRA = 20.0          # s
MAX_TOTAL_TIMEOUT = 300.0     # s ... but never more than this; longer plans are refused

SHAPES = ['polygon', 'star', 'circle', 'square_spiral', 'zigzag', 'repeatability']
CLOSED_SHAPES = ['polygon', 'star', 'circle'] + ms.SHAPES   # shapes allowed for repeatability


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def straight(d):
    return {'kind': 'straight', 'distance': d}


def turn(a):
    return {'kind': 'turn', 'angle': a}


def plan_more(shape, side=SIDE_LENGTH, sides=POLYGON_SIDES, radius=CIRCLE_RADIUS, step=SPIRAL_STEP,
              max_leg=SPIRAL_MAX_LEG, legs=ZIGZAG_LEGS):
    """Segments of a shape (same format as motion_shapes.plan_segments; + angles turn left)."""
    if shape == 'polygon':
        segs = []
        for _ in range(sides):
            segs += [straight(side), turn(2 * math.pi / sides)]
        return segs
    if shape == 'star':
        segs = []
        for _ in range(5):
            segs += [straight(side), turn(STAR_TURN)]
        return segs
    if shape == 'circle':
        return [{'kind': 'arc', 'angle': 2 * math.pi, 'radius': radius}]
    if shape == 'square_spiral':
        max_leg = min(max_leg, SPIRAL_MAX_LEG)
        lengths = []
        k = 1
        while step * k <= max_leg + 1e-9:
            lengths += [step * k, step * k]
            k += 1
        segs = []
        for i, d in enumerate(lengths):
            segs.append(straight(d))
            if i < len(lengths) - 1:
                segs.append(turn(math.pi / 2))
        return segs
    if shape == 'zigzag':
        half = ZIGZAG_ANGLE / 2
        segs = [turn(half)]
        heading = half
        for i in range(legs):
            segs.append(straight(side))
            if i < legs - 1:
                a = -ZIGZAG_ANGLE if heading > 0 else ZIGZAG_ANGLE
                segs.append(turn(a))
                heading += a
        segs.append(turn(-heading))   # back to the start heading
        return segs
    if shape in ms.SHAPES:
        return ms.plan_segments(shape, side, ms.CIRCLE_RADIUS)
    raise ValueError(f'unknown shape {shape}')


def simulate_plan(segs, arc_samples=72):
    """Follow the plan on paper. Returns (end x, end y, total heading change, max distance from start).

    Start frame: x forward, y left. Arcs are sampled so their farthest point counts too.
    """
    x = y = h = 0.0
    far = 0.0
    for s in segs:
        if s['kind'] == 'straight':
            x += s['distance'] * math.cos(h)
            y += s['distance'] * math.sin(h)
        elif s['kind'] == 'turn':
            h += s['angle']
        else:
            r, a = s['radius'], s['angle']
            d = 1.0 if a > 0 else -1.0            # left circle: centre to the left of the robot
            cx, cy = x - d * r * math.sin(h), y + d * r * math.cos(h)
            for k in range(1, arc_samples + 1):
                hk = h + a * k / arc_samples
                px, py = cx + d * r * math.sin(hk), cy - d * r * math.cos(hk)
                far = max(far, math.hypot(px, py))
            h += a
            x, y = cx + d * r * math.sin(h), cy - d * r * math.cos(h)
        far = max(far, math.hypot(x, y))
    return round(x, 9) + 0.0, round(y, 9) + 0.0, h, far


def is_closed(segs, tol=1e-6):
    """True if the plan ends where it started, facing the same way (heading change a multiple of 360)."""
    x, y, h, _ = simulate_plan(segs)
    turns = h / (2 * math.pi)
    return math.hypot(x, y) < tol and abs(turns - round(turns)) < tol


def heading_change(seg):
    """How much a segment changes the summed heading (turns and arcs; straight segments do not)."""
    return seg['angle'] if seg['kind'] in ('turn', 'arc') else 0.0


def total_timeout_for(expected):
    return TIMEOUT_FACTOR * expected + TIMEOUT_EXTRA


def front_needed(segs):
    """Clear distance needed in front at the start, like motion_shapes.main (first segment only)."""
    first = segs[0]
    if first['kind'] == 'straight':
        return first['distance'] + ms.OBSTACLE_STOP_DISTANCE
    if first['kind'] == 'arc':
        return first['radius'] + ms.OBSTACLE_STOP_DISTANCE
    return 0.0


# ---------------------------------------------------------------- driving
def drive_plan(node, segs, target, label):
    """Drive segs one after the other. target: summed heading before the plan. Returns the new target."""
    for i, s in enumerate(segs, 1):
        target += heading_change(s)
        log(f'{label}segment {i}/{len(segs)}: {ms.describe_segment(s)}')
        took = ms.run_segment(node, s, target, None)   # deadline is kept by motion_common.Guard
        log(f'{label}segment {i} done in {took:.1f} s')
        ms.stand_still(node, ms.PAUSE, None)
    return target


def parse_args():
    p = argparse.ArgumentParser(description='Drive more shapes with the TurtleBot 4. MOVES THE ROBOT.')
    p.add_argument('shape', choices=SHAPES)
    p.add_argument('--sides', type=int, default=POLYGON_SIDES, help=f'polygon sides ({MIN_SIDES}..{MAX_SIDES})')
    p.add_argument('--side', type=float, default=None,
                   help=f'side / leg length in m (default {SIDE_LENGTH}, zigzag {ZIGZAG_SIDE}; max {MAX_SIDE_LENGTH})')
    p.add_argument('--radius', type=float, default=CIRCLE_RADIUS,
                   help=f'circle radius in m ({MIN_RADIUS}..{MAX_RADIUS})')
    p.add_argument('--step', type=float, default=SPIRAL_STEP, help='square_spiral leg growth in m')
    p.add_argument('--max-leg', type=float, default=SPIRAL_MAX_LEG, help='square_spiral longest leg (<= 0.5 m)')
    p.add_argument('--legs', type=int, default=ZIGZAG_LEGS, help=f'zigzag legs (1..{MAX_ZIGZAG_LEGS})')
    p.add_argument('--shape', dest='of', choices=CLOSED_SHAPES, default='square',
                   help='repeatability: which closed shape to repeat (default square)')
    p.add_argument('--loops', type=int, default=LOOPS, help=f'repeatability: how many times (1..{MAX_LOOPS})')
    p.add_argument('--speed', type=float, default=LINEAR_SPEED, help='forward speed in m/s (capped at 0.15)')
    p.add_argument('--turn-speed', type=float, default=ANGULAR_SPEED, help='turn speed in rad/s (capped at 1.0)')
    p.add_argument('--no-lidar', action='store_true', help='do not use the lidar (NO obstacle stop)')
    p.add_argument('--dry-run', action='store_true', help='run all checks and print the plan, never move')
    p.add_argument('--yes', action='store_true', help='skip the "area clear?" question (needed when detached)')
    return p.parse_args()


def build_plan(args):
    """Returns (segs of one loop, loops, notes) or raises ValueError with the reason."""
    notes = []

    def clamp(name, value, low, high, unit):
        v, m = ms.clamp_setting(name, value, low, high, unit)
        if m:
            notes.append(m)
        return v

    if args.side is None:
        args.side = ZIGZAG_SIDE if args.shape == 'zigzag' else SIDE_LENGTH
    side = clamp('--side', args.side, 0.05, MAX_SIDE_LENGTH, 'm')
    sides = int(clamp('--sides', args.sides, MIN_SIDES, MAX_SIDES, 'sides'))
    radius = clamp('--radius', args.radius, MIN_RADIUS, MAX_RADIUS, 'm')
    step = clamp('--step', args.step, 0.05, SPIRAL_MAX_LEG, 'm')
    max_leg = clamp('--max-leg', args.max_leg, step, SPIRAL_MAX_LEG, 'm')
    legs = int(clamp('--legs', args.legs, 1, MAX_ZIGZAG_LEGS, 'legs'))
    loops = 1
    shape = args.shape
    if shape == 'repeatability':
        shape = args.of
        loops = int(clamp('--loops', args.loops, 1, MAX_LOOPS, 'loops'))
    segs = plan_more(shape, side, sides, radius, step, max_leg, legs)
    if args.shape == 'repeatability' and not is_closed(segs):
        raise ValueError(f'{shape} does not end where it starts, so it cannot be repeated')
    return shape, segs, loops, notes


def main():
    args = parse_args()
    speed, m1 = ms.clamp_setting('--speed', args.speed, ms.MIN_LINEAR_SPEED, ms.MAX_LINEAR_SPEED, 'm/s')
    turn_speed, m2 = ms.clamp_setting('--turn-speed', args.turn_speed, ms.MIN_ANGULAR_SPEED,
                                      ms.MAX_ANGULAR_SPEED, 'rad/s')
    try:
        shape, segs, loops, notes = build_plan(args)
    except ValueError as e:
        log(f'REFUSING: {e}')
        return 2
    for m in [m1, m2] + notes:
        if m:
            log(f'note: {m}')
    segs = ms.add_timing(segs, speed, turn_speed)

    # Plan on paper: where it ends, how far it goes, how long it takes.
    ex, ey, eh, far = simulate_plan(segs)
    one = sum(s['expected'] for s in segs) + ms.PAUSE * len(segs)
    expected = one * loops
    total_timeout = total_timeout_for(expected)
    log(f'{args.shape}{" of " + shape if loops > 1 or args.shape == "repeatability" else ""}: '
        f'{len(segs)} segments x {loops} loop(s), about {expected:.0f} s, total timeout {total_timeout:.0f} s')
    for i, s in enumerate(segs, 1):
        log(f'  {i}. {ms.describe_segment(s)}')
    log(f'planned end: x {ex:+.3f} m, y {ey:+.3f} m, heading change {math.degrees(eh):+.1f} deg; '
        f'farthest point {far:.2f} m from the start')
    if far > mc.PLAN_MAX_RADIUS + 1e-9:
        log(f'REFUSING: the path goes {far:.2f} m from the start, more than {mc.PLAN_MAX_RADIUS:.1f} m. '
            'Use a shorter --side / fewer --legs / smaller --radius.')
        return 2
    if total_timeout > MAX_TOTAL_TIMEOUT:
        log(f'REFUSING: the plan needs a {total_timeout:.0f} s timeout, more than {MAX_TOTAL_TIMEOUT:.0f} s. '
            'Use fewer --loops, a shorter shape or a higher --speed.')
        return 2

    use_lidar = not args.no_lidar
    if not use_lidar:
        log('WARNING: --no-lidar given, the robot will NOT stop for obstacles. Watch it closely.')
    code = mc.preflight(args.dry_run)
    if code is not None:
        return code

    mc.init_ros()
    node = ms.MotionShapes(use_lidar, args.dry_run)

    def body():
        mc.startup_checks(node, args.dry_run, use_lidar, front_needed(segs))
        if args.dry_run:
            log('dry run: all checks done, nothing was sent to /cmd_vel')
            return 0
        mc.confirm(args.yes)
        mc.start_motion()
        mc.Guard(node, total_timeout).install()
        x0, y0, yaw0, h0 = node.x, node.y, node.yaw, node.heading.total
        log('starting. To stop: Ctrl+C, or "touch ~/STOP", or "pkill -INT -f more_shapes.py"')
        target = h0
        rows = []
        prev = (0.0, 0.0)
        for k in range(1, loops + 1):
            label = f'loop {k}/{loops} ' if loops > 1 else ''
            target = drive_plan(node, segs, target, label)
            mx, my = mc.to_start_frame(x0, y0, yaw0, node.x, node.y)
            mh = node.heading.total - h0
            px, py, ph = ex, ey, eh * k          # closed shapes: same end point every loop
            err = math.hypot(mx - px, my - py)
            drift = math.hypot(mx - prev[0], my - prev[1]) if loops > 1 else err
            prev = (mx, my)
            rows.append((k, mx, my, err, math.degrees(mh - ph), drift))
            log(f'{label}end: odometry x {mx:+.3f} m, y {my:+.3f} m, heading change {math.degrees(mh):+.1f} deg '
                f'(planned x {px:+.3f}, y {py:+.3f}, {math.degrees(ph):+.1f} deg); '
                f'error {err * 100:.1f} cm, {math.degrees(mh - ph):+.1f} deg')
        if loops > 1:
            log('repeatability summary (odometry only; measure on the floor for the real error):')
            log('  loop   x [m]    y [m]   pos err [cm]  heading err [deg]  moved since last loop end [cm]')
            for k, mx, my, err, herr, drift in rows:
                log(f'  {k:4d}  {mx:+.3f}  {my:+.3f}  {err * 100:12.1f}  {herr:+17.1f}  {drift * 100:30.1f}')
            log(f'  mean position error {sum(r[3] for r in rows) / len(rows) * 100:.1f} cm, '
                f'final heading error {rows[-1][4]:+.1f} deg')
        else:
            log('(odometry only; the real error is larger, measure it on the floor)')
        log('done')
        return 0

    return mc.run_guarded(node, args.dry_run, body)


if __name__ == '__main__':
    sys.exit(main())
