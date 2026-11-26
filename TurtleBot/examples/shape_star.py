"""Star program: drive a 5-point star with the TurtleBot 4.

THIS PROGRAM MOVES THE ROBOT. Undock it, clear about 1 m of floor all round, and stay next to it.
Speed is capped at 0.15 m/s and 1.0 rad/s whatever you ask for.

What it drives: a 5-point star: 5 x (forward --side metres, default 0.30 m, max 0.60 m, then turn left 144 degrees).
It is a thin wrapper: it only chooses the shape and passes the options on to more_shapes.py, so every safety
layer is that program's: start-up checks (/odom, /dock_status, lidar, hazards), refuses to start on the dock,
waits for steady /odom, stops for an obstacle closer than 0.25 m in front, for a bump or cliff, a stall,
stale odometry or lidar and a timeout, and always ends with zero velocity. It also stays within a 1.2 m fence from its start.

Needs motion_shapes.py, more_shapes.py and motion_common.py in the same folder. Run it on the robot
(dry run first: checks everything, prints the plan, never moves):
    python3 shape_star.py --dry-run
    python3 shape_star.py --side 0.25
Started from TurtleBot Studio you do not need --yes: Studio asks you to confirm and then tells the program so
(STUDIO_MOTION_CONFIRMED=1, honoured only when there is no terminal). On the robot, in a terminal, the program
asks "is the area clear?" itself. Detached (no terminal) it needs --yes.

How to stop it: Ctrl+C, the Studio Stop button, or  touch ~/STOP  (then rm ~/STOP), or  pkill -INT -f shape_star.py
Exit codes: 0 done, 1 aborted by a safety check, 2 setup failure / refused, 130 stopped by you.
"""
import sys

import motion_common as mc
import more_shapes as base

PROG = 'shape_star.py'
SHAPE = 'star'
SIDE = base.SIDE_LENGTH


def parse_args(argv=None):
    p = mc.shape_parser(__doc__, PROG)
    p.add_argument('--side', type=float, default=SIDE,
                   help=f'length of each line of the star in m (default {SIDE}, max {base.MAX_SIDE_LENGTH})')
    return p.parse_args(argv)


def underlying_argv(args):
    """The argv for more_shapes.py main (pure, no ROS)."""
    return ['star', '--side', repr(args.side)] + mc.common_argv(args)


def plan(argv=None):
    """The timed segment plan this program would drive (pure, no ROS). more_shapes.build_plan returns
    (shape, segs, loops, notes); this is segs, before the timing is added."""
    return base.build_plan(base.parse_args(underlying_argv(parse_args(argv))))[1]


def main(argv=None):
    args = parse_args(argv)
    return mc.run_shape(base, underlying_argv(args), PROG, f'a 5-point star with {args.side:g} m lines (more_shapes.py star)')


if __name__ == '__main__':
    sys.exit(main())
