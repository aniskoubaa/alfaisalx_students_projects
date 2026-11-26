"""Rectangle program: drive a rectangle with the TurtleBot 4.

THIS PROGRAM MOVES THE ROBOT. Undock it, clear about 1 m of floor all round (more for long sides), and stay next to it.
Speed is capped at 0.15 m/s and 1.0 rad/s whatever you ask for.

What it drives: a rectangle, --length m (default 0.40) ahead, then --width m (default 0.25) to the left, and back round,
turning left 90 degrees at each corner. Both sides are limited to 1.0 m like the square (0.05 m minimum).
It is a thin wrapper: it only chooses the shape and passes the options on to motion_shapes.py, so every safety
layer is that program's: start-up checks (/odom, /dock_status, lidar, hazards), refuses to start on the dock,
waits for steady /odom, stops for an obstacle closer than 0.25 m in front, for a bump or cliff, a stall,
stale odometry or lidar and a timeout, and always ends with zero velocity.

Needs motion_shapes.py, more_shapes.py and motion_common.py in the same folder. Run it on the robot
(dry run first: checks everything, prints the plan, never moves):
    python3 shape_rectangle.py --dry-run
    python3 shape_rectangle.py --length 0.50 --width 0.30
Started from TurtleBot Studio you do not need --yes: Studio asks you to confirm and then tells the program so
(STUDIO_MOTION_CONFIRMED=1, honoured only when there is no terminal). On the robot, in a terminal, the program
asks "is the area clear?" itself. Detached (no terminal) it needs --yes.

How to stop it: Ctrl+C, the Studio Stop button, or  touch ~/STOP  (then rm ~/STOP), or  pkill -INT -f shape_rectangle.py
Exit codes: 0 done, 1 aborted by a safety check, 2 setup failure / refused, 130 stopped by you.
"""
import sys

import motion_common as mc
import motion_shapes as base

PROG = 'shape_rectangle.py'
SHAPE = 'rectangle'
LENGTH = base.SIDE_LENGTH
WIDTH = base.RECTANGLE_WIDTH


def parse_args(argv=None):
    p = mc.shape_parser(__doc__, PROG)
    p.add_argument('--length', type=float, default=LENGTH,
                   help=f'long side in m, driven first (default {LENGTH}, max {base.MAX_SIDE_LENGTH})')
    p.add_argument('--width', type=float, default=WIDTH,
                   help=f'short side in m (default {WIDTH}, max {base.MAX_SIDE_LENGTH})')
    return p.parse_args(argv)


def underlying_argv(args):
    """The argv for motion_shapes.py main (pure, no ROS)."""
    return ['rectangle', '--side', repr(args.length), '--width', repr(args.width)] + mc.common_argv(args)


def plan(argv=None):
    """The timed segment plan this program would drive (pure, no ROS)."""
    return base.build_plan(base.parse_args(underlying_argv(parse_args(argv))))[0]


def main(argv=None):
    args = parse_args(argv)
    return mc.run_shape(base, underlying_argv(args), PROG, f'a rectangle {args.length:g} m x {args.width:g} m (motion_shapes.py rectangle)')


if __name__ == '__main__':
    sys.exit(main())
