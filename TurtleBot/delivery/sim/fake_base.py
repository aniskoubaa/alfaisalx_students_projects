#!/usr/bin/env python3
"""Fake TurtleBot 4 base for the delivery simulator: imitates the Create 3 base, the lidar and the front panel so the
REAL Nav2, AMCL, costmap filters and delivery_mission.py can run with the robot sitting on its dock.

IT CANNOT MOVE THE REAL ROBOT. It refuses to start unless ROS_DOMAIN_ID is set and is not 0. The real base listens
on domain 0 only, so nothing published here reaches it. It writes only inside --run-dir, which must be under
~/robot_code/logs/delivery/ or /tmp.

Needs ROS 2 (Jazzy) with the TurtleBot 4 / Create 3 message packages, and numpy. Normally started by run_e2e.sh:
    ROS_DOMAIN_ID=77 python3 fake_base.py --map ROUTE_DIR/map.yaml --route ROUTE_DIR/route.yaml \
        --glass @sim_world.json --press "pickup:3,handoff:4" --run-dir ~/robot_code/logs/delivery/sim_X

What it provides (all on the default, un-namespaced topic names):
  subscribes  /cmd_vel (TwistStamped; clamped to 0.31 m/s and 1.9 rad/s, zero after 0.5 s without a command,
              ignored while docked), /hmi/display/message (logged; the fake human reads the prompts), /cmd_audio (logged)
  publishes   /odom 20 Hz + /tf odom->base_link 50 Hz (optional drift), /tf_static base_link->rplidar_link
              (+90 deg yaw) and base_link->base_footprint, /scan 5 Hz (360 beams, 0.15..12 m, ray cast on the map,
              NOT published while docked, like the real lidar), /dock_status 1 Hz, /battery_state 1 Hz,
              /hmi/buttons on change, /hazard_detection (empty vectors at 1 Hz; BUMP when the ground truth collides)
  actions     /undock (about 6 s, backs 0.3 m), /dock (succeeds only within 1.0 m of the dock pose),
              /wall_follow (irobot_create_msgs/WallFollow: follows the nearest wall on the chosen side at about 0.2 m/s,
              about 0.3 m from the robot centre (0.13 m from its edge), turns in at openings, ends after max_runtime;
              it senses the ground truth, so it also turns into the doorway of the glass room; /cmd_vel is ignored
              while it runs; --stall only silences /odom and /tf, the base keeps driving)
Ground truth: the robot's true pose lives in the map frame. Collisions and the nearest-obstacle distance use the map
plus the --glass segments (glass the lidar sees through). Log: RUN_DIR/ground_truth.jsonl (5 Hz poses + events).

Options (see --help): --press "pickup:3,handoff:4" (button N a few seconds after the prompt; leave an entry out and
nobody presses it), --stall "t0,len" (no /odom and /tf for len s, t0 s after the undock finished, TB-25),
--fail-after-pose N (the robot jams when it reaches the Nth outbound pose), --drift F, --scan-when-docked.

Pure functions (kinematics, ray cast, parsing) are importable without ROS; numpy is needed for the grid ones.
"""
import argparse
import json
import math
import os
import re
import signal
import sys
import threading
import time

try:
    import numpy as np
except ImportError:   # the pure tests skip the grid parts with a message
    np = None

# ---------------------------------------------------------------- constants (units in comments)
MAX_LIN = 0.31              # m/s, Create 3 limit with the cliff sensors on
MAX_ANG = 1.9               # rad/s
MAX_ACC_LIN = 1.0           # m/s^2, slew limit of the base
MAX_ACC_ANG = 3.0           # rad/s^2
WATCHDOG = 0.5              # s, no /cmd_vel for this long: zero velocity
TICK_HZ = 50.0              # integration and /tf rate
ODOM_HZ = 20.0
SCAN_HZ = 5.0
SCAN_BEAMS = 360
SCAN_RANGE_MIN, SCAN_RANGE_MAX = 0.15, 12.0   # m
RAY_STEP = 0.025            # m, half a 5 cm cell
LASER_X = -0.04             # m, lidar position in base_link (TurtleBot 4)
LASER_Z = 0.19
LASER_YAW = math.pi / 2     # rad, the lidar is mounted at +90 deg yaw
ROBOT_RADIUS = 0.17         # m, a true obstacle closer than this is a collision (BUMP)
BUMP_STOP_S = 3.0           # s, the base stays stopped after a bump
UNDOCK_PREP_S = 1.5         # s, before the base starts to back off
UNDOCK_SPEED = 0.10         # m/s
UNDOCK_DISTANCE = 0.30      # m
UNDOCK_SETTLE_S = 1.5
DOCK_RANGE = 1.0            # m, /dock succeeds only this close to the dock pose
DOCK_SPEED = 0.10           # m/s
DOCK_SEARCH_S = 4.0         # s, before a too-far /dock gives up
DOCK_SETTLE_S = 2.0
DOCK_TIMEOUT_S = 120.0
WF_SPEED = 0.20             # m/s, wall follower cruise speed
WF_TARGET = 0.30            # m, wall follower distance from the robot centre to the wall (0.13 m from the robot's edge)
WF_FRONT_STOP = 0.55        # m, a wall this close ahead: turn away from the wall in place
WF_LOST = 1.2               # m, no wall this close on the wall side: an opening, turn in
WF_RANGE = 3.0              # m, range of the wall follower's sensors
WF_KD, WF_KA = 1.5, 1.1     # steering gains on the distance error (rad/s per m) and the heading error (rad/s per rad)
WF_GAP = 0.3               # m, diag range beyond the straight-wall prediction that counts as a gap ahead
WF_PULL_MAX = 0.06          # m, the largest distance error the follower steers back from when the wall is too far
WF_MAX_TURN = 0.6           # rad/s, steering limit while following
WF_PERIOD_S = 0.1           # s, the follower recomputes its command this often
WF_ENGAGED_RANGE = 0.8      # m, 'engaged' feedback when a wall is this close on the wall side
STUCK_RADIUS = 0.8          # m, --fail-after-pose jams the robot this close to the pose
PRESS_DELAY_S = 4.0         # s, the fake human presses this long after the prompt appears
PRESS_HOLD_S = 1.0
LOG_HZ = 5.0
GT_RADIUS = 3.0             # m, nearest-obstacle search radius for the log
BATTERY_START = 0.90
BATTERY_DRAIN = 0.0001      # fraction per second while undocked
BATTERY_CHARGE = 0.0005     # fraction per second while docked
DEFAULT_MAX_RUNTIME = 3600  # s, the node ends by itself after this
SAFE_ROOTS = ('~/robot_code/logs/delivery', '/tmp')


# ---------------------------------------------------------------- pure helpers (no ROS)
def domain_problem(env):
    """None when ROS_DOMAIN_ID is set and not 0, else the reason the simulator must refuse to start."""
    raw = env.get('ROS_DOMAIN_ID')
    if raw is None or str(raw).strip() == '':
        return 'ROS_DOMAIN_ID is not set (the simulator needs its own domain, for example 77)'
    try:
        value = int(str(raw).strip())
    except ValueError:
        return f'ROS_DOMAIN_ID={raw!r} is not a number'
    if value == 0:
        return 'ROS_DOMAIN_ID is 0: that is the real robot\'s domain. Use another one, for example 77'
    if not 0 < value <= 232:
        return f'ROS_DOMAIN_ID={value} is out of range (1..232)'
    return None


def run_dir_ok(path, home=None):
    """True when path is inside ~/robot_code/logs/delivery or /tmp (after resolving symlinks)."""
    home = home or os.path.expanduser('~')
    real = os.path.realpath(path)
    for root in SAFE_ROOTS:
        base = os.path.realpath(root.replace('~', home, 1) if root.startswith('~') else root)
        if real == base or real.startswith(base + os.sep):
            return True
    return False


def wrap(a):
    """Angle in radians wrapped to [-pi, pi)."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def clamp_cmd(vx, wz):
    """Create 3 velocity limits."""
    return clamp(vx, -MAX_LIN, MAX_LIN), clamp(wz, -MAX_ANG, MAX_ANG)


def slew(cur, target, max_step):
    return cur + clamp(target - cur, -max_step, max_step)


def step_pose(x, y, yaw, v, w, dt):
    """Integrate a unicycle for dt seconds (exact arc; straight line when w is tiny)."""
    if abs(w) < 1e-9:
        return x + v * dt * math.cos(yaw), y + v * dt * math.sin(yaw), wrap(yaw)
    nyaw = yaw + w * dt
    r = v / w
    return x + r * (math.sin(nyaw) - math.sin(yaw)), y - r * (math.cos(nyaw) - math.cos(yaw)), wrap(nyaw)


def goto_step(x, y, yaw, tx, ty, tyaw, phase):
    """One control step of the docking approach: turn to the target, drive, turn to the final yaw.
    Returns (v, w, phase); phase 'done' means arrived."""
    dx, dy = tx - x, ty - y
    dist = math.hypot(dx, dy)
    heading = math.atan2(dy, dx)
    if phase == 'turn':
        err = wrap(heading - yaw)
        if dist < 0.03:
            phase = 'align'
        elif abs(err) < 0.05:
            phase = 'drive'
        else:
            return 0.0, clamp(1.5 * err, -0.6, 0.6), 'turn'
    if phase == 'drive':
        if dist < 0.02:
            phase = 'align'
        else:
            err = wrap(heading - yaw)
            v = 0.0 if abs(err) > 0.6 else min(DOCK_SPEED, 0.03 + dist * 0.5)
            return v, clamp(2.0 * err, -0.6, 0.6), 'drive'
    if phase == 'align':
        err = wrap(tyaw - yaw)
        if abs(err) < 0.02:
            return 0.0, 0.0, 'done'
        w = clamp(1.5 * err, -0.6, 0.6)
        if abs(w) < 0.15:
            w = math.copysign(0.15, err)
        return 0.0, w, 'align'
    return 0.0, 0.0, 'done'


def parse_press(text):
    """'pickup:3,handoff:4' -> {'pickup': 3, 'handoff': 4}. Names: pickup, handoff. Buttons 1..4."""
    out = {}
    if not text:
        return out
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r'(pickup|handoff):([1-4])', part)
        if not m:
            raise ValueError(f'bad --press entry {part!r} (use pickup:3 or handoff:4)')
        out[m.group(1)] = int(m.group(2))
    return out


def parse_stall(text):
    """'25,5' -> (25.0, 5.0): no /odom and /tf for 5 s, starting 25 s after the undock finished."""
    if not text:
        return None
    try:
        t0, length = [float(v) for v in text.split(',')]
    except ValueError:
        raise ValueError(f'bad --stall {text!r} (use "t0,len" in seconds)') from None
    if t0 < 0 or length <= 0:
        raise ValueError('--stall needs t0 >= 0 and len > 0')
    return t0, length


def parse_segments(text):
    """'x1,y1,x2,y2;x1,y1,x2,y2' or '@file.json' (a list of [x1,y1,x2,y2] or a dict with glass_segments)."""
    if not text:
        return []
    if text.startswith('@'):
        with open(os.path.expanduser(text[1:]), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data = data.get('glass_segments', [])
        return [[float(v) for v in seg] for seg in data]
    segs = []
    for part in text.split(';'):
        part = part.strip()
        if part:
            vals = [float(v) for v in part.split(',')]
            if len(vals) != 4:
                raise ValueError(f'bad glass segment {part!r} (use x1,y1,x2,y2)')
            segs.append(vals)
    return segs


def match_prompt(text):
    """Which prompt does a display text show? 'pickup' (food placed), 'handoff' (take your food) or None."""
    low = (text or '').lower()
    if 'food placed' in low:
        return 'pickup'
    if 'food is here' in low or 'your food' in low:
        return 'handoff'
    return None


def read_pgm(path):
    """(width, height, bytes) of a binary P5 file with maxval 255."""
    with open(path, 'rb') as fh:
        data = fh.read()
    if data[:2] != b'P5':
        raise ValueError(f'{path}: only binary PGM (P5) is supported')
    pos, tokens = 2, []
    while len(tokens) < 3:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':
            while data[pos:pos + 1] not in (b'\n', b''):
                pos += 1
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        tokens.append(int(data[start:pos]))
    w, h, maxval = tokens
    if maxval != 255:
        raise ValueError(f'{path}: maxval {maxval} is not supported (need 255)')
    pos += 1
    pix = data[pos:pos + w * h]
    if len(pix) < w * h:
        raise ValueError(f'{path}: image data too short')
    return w, h, pix


class Grid:
    """Occupancy grid from a Nav2 map yaml + PGM. occ[row, col] True = occupied (row 0 is the top of the image)."""

    def __init__(self, occ, res, ox, oy):
        self.occ, self.res, self.ox, self.oy = occ, res, ox, oy
        self.H, self.W = occ.shape

    @classmethod
    def load(cls, yaml_path):
        import yaml
        if np is None:
            raise RuntimeError('numpy is required for the grid')
        with open(yaml_path, 'r', encoding='utf-8') as fh:
            info = yaml.safe_load(fh)
        img = str(info['image'])
        img = img if os.path.isabs(img) else os.path.join(os.path.dirname(os.path.abspath(yaml_path)), img)
        w, h, pix = read_pgm(img)
        arr = np.frombuffer(pix, dtype=np.uint8).reshape(h, w).astype(np.float64) / 255.0
        occp = arr if int(info.get('negate', 0)) else 1.0 - arr
        occ = occp >= float(info.get('occupied_thresh', 0.65))
        return cls(occ, float(info['resolution']), float(info['origin'][0]), float(info['origin'][1]))

    def copy_with_segments(self, segs):
        """A copy with the segments (x1, y1, x2, y2 in metres) drawn as occupied cells (the glass of the ground truth)."""
        occ = self.occ.copy()
        for x1, y1, x2, y2 in segs:
            n = max(2, int(math.hypot(x2 - x1, y2 - y1) / (self.res / 4.0)) + 1)
            for i in range(n + 1):
                f = i / n
                c, r = self.cell(x1 + f * (x2 - x1), y1 + f * (y2 - y1))
                if 0 <= c < self.W and 0 <= r < self.H:
                    occ[r, c] = True
        return Grid(occ, self.res, self.ox, self.oy)

    def cell(self, x, y):
        return (int(math.floor((x - self.ox) / self.res)),
                self.H - 1 - int(math.floor((y - self.oy) / self.res)))

    def occupied_at(self, x, y):
        c, r = self.cell(x, y)
        return 0 <= c < self.W and 0 <= r < self.H and bool(self.occ[r, c])

    def nearest_obstacle(self, x, y, radius=GT_RADIUS):
        """Distance in metres from (x, y) to the nearest occupied cell edge; radius when none is that close."""
        c, r = self.cell(x, y)
        n = int(radius / self.res) + 2
        r0, r1, c0, c1 = max(r - n, 0), min(r + n + 1, self.H), max(c - n, 0), min(c + n + 1, self.W)
        if r0 >= r1 or c0 >= c1:
            return radius
        rr, cc = np.nonzero(self.occ[r0:r1, c0:c1])
        if rr.size == 0:
            return radius
        px = self.ox + (cc + c0 + 0.5) * self.res
        py = self.oy + (self.H - (rr + r0) - 0.5) * self.res
        d = float(np.min(np.hypot(px - x, py - y))) - self.res / 2.0
        return min(max(d, 0.0), radius)


def raycast(grid, x, y, yaw, n=SCAN_BEAMS, ang_min=-math.pi, rmin=SCAN_RANGE_MIN, rmax=SCAN_RANGE_MAX,
            step=RAY_STEP):
    """Ranges (float array, inf = no return) of n beams from (x, y). Beam i points at yaw + ang_min + i*2pi/n."""
    inc = 2 * math.pi / n
    ang = yaw + ang_min + inc * np.arange(n)
    rs = np.arange(rmin, rmax + step, step)
    px = x + np.cos(ang)[:, None] * rs[None, :]
    py = y + np.sin(ang)[:, None] * rs[None, :]
    cols = np.floor((px - grid.ox) / grid.res).astype(np.int64)
    rows = (grid.H - 1 - np.floor((py - grid.oy) / grid.res)).astype(np.int64)
    inside = (cols >= 0) & (cols < grid.W) & (rows >= 0) & (rows < grid.H)
    hit = np.zeros(px.shape, dtype=bool)
    hit[inside] = grid.occ[rows[inside], cols[inside]]
    first = np.argmax(hit, axis=1)
    has = hit[np.arange(n), first]
    return np.where(has, rs[first], np.inf)


def cast_rays(grid, x, y, angles, rmin=0.05, rmax=WF_RANGE, step=RAY_STEP):
    """Ranges (float array, inf = nothing within rmax) of single rays from (x, y) at the world angles (radians)."""
    ang = np.asarray(angles, dtype=np.float64)
    rs = np.arange(rmin, rmax + step, step)
    px = x + np.cos(ang)[:, None] * rs[None, :]
    py = y + np.sin(ang)[:, None] * rs[None, :]
    cols = np.floor((px - grid.ox) / grid.res).astype(np.int64)
    rows = (grid.H - 1 - np.floor((py - grid.oy) / grid.res)).astype(np.int64)
    inside = (cols >= 0) & (cols < grid.W) & (rows >= 0) & (rows < grid.H)
    hit = np.zeros(px.shape, dtype=bool)
    hit[inside] = grid.occ[rows[inside], cols[inside]]
    first = np.argmax(hit, axis=1)
    has = hit[np.arange(len(ang)), first]
    return np.where(has, rs[first], np.inf)


def wall_follow_ranges(grid, x, y, yaw, side):
    """The wall follower's sensors, cast from the robot centre: front, diag (45 deg towards the wall) and side (90 deg).
    side is 1 for a wall on the left (FOLLOW_LEFT) and -1 for the right (FOLLOW_RIGHT)."""
    r = cast_rays(grid, x, y, [yaw, yaw + side * math.pi / 4, yaw + side * math.pi / 2])
    return {'front': float(r[0]), 'diag': float(r[1]), 'side': float(r[2])}


def wall_follow_cmd(r, side, target=WF_TARGET, speed=WF_SPEED):
    """One control step of the wall follower. r = wall_follow_ranges(); side 1 = wall on the left, -1 = on the right.
    Returns (v, w, engaged). A wall ahead: turn away from the wall in place. No wall near on the wall side (an opening
    or a wall that ended): arc towards the wall. Otherwise steer on the distance to the wall and on the wall's heading
    (both estimated from the side and diag rays)."""
    front, diag, sd = r['front'], min(r['diag'], WF_RANGE), min(r['side'], WF_RANGE)
    engaged = min(sd, diag) < WF_ENGAGED_RANGE
    if front < WF_FRONT_STOP:
        return 0.0, -side * 0.8, True
    if min(sd, diag) >= WF_LOST:
        return 0.10, side * 0.6, False
    phi = math.atan2(sd - 0.7071 * diag, 0.7071 * diag)      # > 0: the robot points towards the wall
    if diag > 1.4142 * sd + WF_GAP:
        phi = 0.0      # the diag ray is far longer than a straight wall predicts: a gap or a recess ahead, keep the heading
    dist = sd * math.cos(phi)
    # Pulling in is capped at WF_PULL_MAX m of error, so a shallow recess (a glass door) is crossed, not entered.
    u = clamp(WF_KD * clamp(dist - target, -0.3, WF_PULL_MAX) - WF_KA * phi, -WF_MAX_TURN, WF_MAX_TURN)    # > 0: towards the wall
    v = speed * (1.0 - 0.5 * abs(u) / WF_MAX_TURN)
    if front < 1.0:
        v = min(v, 0.5 * speed + 0.1 * (front - WF_FRONT_STOP) / (1.0 - WF_FRONT_STOP))
    return v, side * u, engaged


def simulate_wall_follow(grid, x, y, yaw, side, seconds, dt=0.02, speed=WF_SPEED, stop_x=None):
    """Run the follower alone (the loop the fake base uses, with its slew limits) for the offline tests.
    Returns a list of (t, x, y, yaw, nearest obstacle distance). Stops early when x passes stop_x in the direction
    the robot is travelling (stop_x above the start: going +x, below: going -x)."""
    v = w = 0.0
    cmd = (0.0, 0.0)
    out = []
    t = nxt = 0.0
    sign = 0.0 if stop_x is None else (1.0 if stop_x >= x else -1.0)
    while t < seconds:
        if t >= nxt:
            cmd = wall_follow_cmd(wall_follow_ranges(grid, x, y, yaw, side), side, speed=speed)[:2]
            nxt = t + WF_PERIOD_S
        v = slew(v, cmd[0], MAX_ACC_LIN * dt)
        w = slew(w, cmd[1], MAX_ACC_ANG * dt)
        x, y, yaw = step_pose(x, y, yaw, v, w, dt)
        t += dt
        out.append((t, x, y, yaw, grid.nearest_obstacle(x, y, 0.5)))
        if stop_x is not None and sign * (x - stop_x) >= 0:
            break
    return out


# ---------------------------------------------------------------- the node (ROS imported here only)
def run(args):
    import rclpy
    from rclpy.action import ActionServer, CancelResponse, GoalResponse
    from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped, TwistStamped
    from irobot_create_msgs.action import Dock, Undock, WallFollow
    from irobot_create_msgs.msg import AudioNoteVector, DockStatus, HazardDetection, HazardDetectionVector
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import BatteryState, LaserScan
    from std_msgs.msg import String
    from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
    from turtlebot4_msgs.msg import UserButton
    import yaml

    scan_grid = Grid.load(args.map)
    segs = parse_segments(args.glass)
    truth_grid = scan_grid.copy_with_segments(segs)
    dock = parse_pose(args.dock_pose) if args.dock_pose else None
    route = None
    if args.route:
        with open(args.route, 'r', encoding='utf-8') as fh:
            route = yaml.safe_load(fh)
        if dock is None:
            d = route['dock_pose']
            dock = (float(d['x']), float(d['y']), math.radians(float(d['yaw'])))
    if dock is None:
        dock = (0.0, 0.0, 0.0)
    stuck_pose = None
    if args.fail_after_pose:
        out = (route or {}).get('outbound', [])
        if not 1 <= args.fail_after_pose <= len(out):
            raise SystemExit(f'--fail-after-pose {args.fail_after_pose}: the route has {len(out)} outbound poses')
        p = out[args.fail_after_pose - 1]
        stuck_pose = (float(p['x']), float(p['y']))
    stall = parse_stall(args.stall)
    press = parse_press(args.press)
    rng = np.random.default_rng(args.seed)

    def now_s():
        return time.monotonic()

    class FakeBase(Node):
        def __init__(self):
            super().__init__('fake_base')
            self.lock = threading.Lock()
            self.t0 = now_s()
            self.x, self.y, self.yaw = dock            # true pose, map frame
            self.ox = self.oy = self.oyaw = 0.0        # odometry pose, odom frame (starts at zero)
            self.v = self.w = 0.0                      # current (slewed) velocity
            self.cmd = (0.0, 0.0)
            self.cmd_time = -1e9
            self.mode = 'nav'                          # nav, undock, dock
            self.docked = True
            self.phase = None
            self.phase_t = 0.0
            self.mode_start_xy = (self.x, self.y)
            self.undock_done = None
            self.dock_goals = 0
            self.bump_until = 0.0
            self.bump_armed = True
            self.stuck = False
            self.stall_state = None
            self.battery = args.battery
            self.display_text = ''
            self.due = []                              # [(time, kind)] presses to do
            self.done_prompts = set()
            self.release_at = None
            self.wf_side = 0
            self.wf_cmd = (0.0, 0.0, False)
            self.wf_next = 0.0
            self.speed_true = 0.0
            self.log = open(os.path.join(args.run_dir, 'ground_truth.jsonl'), 'a', buffering=1, encoding='utf-8')
            g_main = MutuallyExclusiveCallbackGroup()
            g_act = ReentrantCallbackGroup()
            self.create_subscription(TwistStamped, '/cmd_vel', self.on_cmd, qos_profile_sensor_data, callback_group=g_main)
            self.create_subscription(String, '/hmi/display/message', self.on_display, 10, callback_group=g_main)
            self.create_subscription(AudioNoteVector, '/cmd_audio', self.on_audio, 10, callback_group=g_main)
            # Only for the log: what AMCL believes, next to the truth (analyse_run.py reports the difference).
            self.est = None
            self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self.on_amcl, 10, callback_group=g_main)
            self.odom_pub = self.create_publisher(Odometry, '/odom', qos_profile_sensor_data)
            self.scan_pub = self.create_publisher(LaserScan, '/scan', qos_profile_sensor_data)
            self.dock_pub = self.create_publisher(DockStatus, '/dock_status', qos_profile_sensor_data)
            self.batt_pub = self.create_publisher(BatteryState, '/battery_state', qos_profile_sensor_data)
            self.haz_pub = self.create_publisher(HazardDetectionVector, '/hazard_detection', qos_profile_sensor_data)
            self.btn_pub = self.create_publisher(UserButton, '/hmi/buttons', QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE))
            self.tf = TransformBroadcaster(self)
            self.static_tf = StaticTransformBroadcaster(self)
            self.publish_static()
            self.create_timer(1.0 / TICK_HZ, self.tick, callback_group=g_main)
            self.create_timer(1.0 / ODOM_HZ, self.pub_odom, callback_group=g_main)
            self.create_timer(1.0 / SCAN_HZ, self.pub_scan, callback_group=g_main)
            self.create_timer(1.0, self.pub_slow, callback_group=g_main)
            self.create_timer(1.0 / LOG_HZ, self.log_state, callback_group=g_main)
            self.create_timer(0.1, self.human, callback_group=g_main)
            self.create_timer(1.0, self.watch_runtime, callback_group=g_main)
            self.undock_srv = ActionServer(self, Undock, 'undock', self.exec_undock, goal_callback=self.on_goal,
                                           cancel_callback=self.on_cancel, callback_group=g_act)
            self.dock_srv = ActionServer(self, Dock, 'dock', self.exec_dock, goal_callback=self.on_goal,
                                         cancel_callback=self.on_cancel, callback_group=g_act)
            self.wall_srv = ActionServer(self, WallFollow, 'wall_follow', self.exec_wall_follow,
                                         goal_callback=self.on_wf_goal, cancel_callback=self.on_cancel, callback_group=g_act)
            self.last_tick = now_s()
            self.event('start', dock=list(dock), glass=len(segs), press=press, stall=stall,
                       fail_after_pose=args.fail_after_pose, domain=os.environ.get('ROS_DOMAIN_ID'))
            self.get_logger().info(f'fake base up: dock pose {dock}, map {args.map}, ROS_DOMAIN_ID={os.environ.get("ROS_DOMAIN_ID")}')

        # ---- small helpers
        def event(self, kind, **kw):
            rec = {'event': kind, 't': round(now_s() - self.t0, 3), 'wall': round(time.time(), 3)}
            rec.update(kw)
            self.log.write(json.dumps(rec) + '\n')

        def stamp(self):
            return self.get_clock().now().to_msg()

        def publish_static(self):
            out = []
            for child, tx, tz, yaw in (('rplidar_link', LASER_X, LASER_Z, LASER_YAW), ('base_footprint', 0.0, 0.0, 0.0)):
                if child == 'base_footprint' and args.no_footprint:
                    continue
                t = TransformStamped()
                t.header.stamp = self.stamp()
                t.header.frame_id = 'base_link'
                t.child_frame_id = child
                t.transform.translation.x, t.transform.translation.z = tx, tz
                t.transform.rotation.z, t.transform.rotation.w = math.sin(yaw / 2), math.cos(yaw / 2)
                out.append(t)
            self.static_tf.sendTransform(out)

        def is_stalled(self, now):
            if stall is None or self.undock_done is None:
                return False
            t = now - self.undock_done
            s = stall[0] <= t < stall[0] + stall[1]
            if s and self.stall_state != 'on':
                self.stall_state = 'on'
                self.event('stall_start', length=stall[1])
            elif not s and self.stall_state == 'on':
                self.stall_state = 'off'
                self.event('stall_end')
            return s

        # ---- inputs
        def on_cmd(self, msg):
            v, w = clamp_cmd(msg.twist.linear.x, msg.twist.angular.z)
            with self.lock:
                self.cmd = (v, w)
                self.cmd_time = now_s()

        def on_display(self, msg):
            text = msg.data
            if text != self.display_text:
                self.display_text = text
                self.get_logger().info('DISPLAY: ' + text.replace('\n', ' | '))
                self.event('display', text=text)
            kind = match_prompt(text)
            if kind and kind in press and kind not in self.done_prompts:
                self.done_prompts.add(kind)
                self.due.append((now_s() + args.press_delay, kind))

        def on_amcl(self, msg):
            p = msg.pose.pose.position
            ox, oy = (dock[0], dock[1]) if args.map_at_dock else (0.0, 0.0)
            with self.lock:
                self.est = (round(p.x, 3), round(p.y, 3), round(p.x + ox - self.x, 3), round(p.y + oy - self.y, 3))

        def on_audio(self, msg):
            freqs = [int(n.frequency) for n in msg.notes]
            self.get_logger().info(f'CHIME: {freqs}')
            self.event('chime', notes=freqs)

        def human(self):
            now = now_s()
            if self.release_at is not None and now >= self.release_at:
                self.release_at = None
                self.send_buttons(None)
            for item in list(self.due):
                if now >= item[0] and self.release_at is None:
                    self.due.remove(item)
                    self.send_buttons(press[item[1]])
                    self.release_at = now + PRESS_HOLD_S
                    self.event('press', prompt=item[1], button=press[item[1]])

        def send_buttons(self, n):
            msg = UserButton()
            state = [False] * 4
            if n:
                state[n - 1] = True
            msg.button = state
            self.btn_pub.publish(msg)

        # ---- physics
        def tick(self):
            now = now_s()
            dt = clamp(now - self.last_tick, 0.0, 0.1)
            self.last_tick = now
            with self.lock:
                if self.mode == 'nav':
                    tv, tw = self.cmd if now - self.cmd_time <= WATCHDOG else (0.0, 0.0)
                    if self.docked or self.stuck or now < self.bump_until:
                        tv = tw = 0.0
                    self.v = slew(self.v, tv, MAX_ACC_LIN * dt)
                    self.w = slew(self.w, tw, MAX_ACC_ANG * dt)
                else:
                    self.drive_scripted(now)
                if not self.stuck:
                    self.x, self.y, self.yaw = step_pose(self.x, self.y, self.yaw, self.v, self.w, dt)
                    kl, ka = 1.0 + args.drift, 1.0 - args.drift
                    # The yaw bias only while moving: at rest it would tilt the whole SLAM map before the first scan.
                    bias = args.drift * 0.05 if abs(self.v) > 0.01 or abs(self.w) > 0.01 else 0.0
                    self.ox, self.oy, self.oyaw = step_pose(self.ox, self.oy, self.oyaw, self.v * kl, self.w * ka + bias, dt)
                self.speed_true = abs(self.v)
                if self.mode in ('nav', 'wall') and not self.docked:
                    self.check_collision(now)
                    if stuck_pose and not self.stuck and math.hypot(self.x - stuck_pose[0], self.y - stuck_pose[1]) < STUCK_RADIUS:
                        self.stuck = True
                        self.v = self.w = 0.0
                        self.event('stuck', x=round(self.x, 2), y=round(self.y, 2))
                if not self.is_stalled(now):
                    self.send_tf()

        def check_collision(self, now):
            d = truth_grid.nearest_obstacle(self.x, self.y, 0.5)
            if d < ROBOT_RADIUS:
                if self.bump_armed:
                    self.bump_armed = False
                    self.bump_until = now + BUMP_STOP_S
                    self.v = self.w = 0.0
                    self.event('hazard', type='BUMP', x=round(self.x, 2), y=round(self.y, 2), dist=round(d, 3))
                    self.get_logger().error(f'GROUND-TRUTH COLLISION at ({self.x:.2f}, {self.y:.2f}): BUMP')
                    m = HazardDetectionVector()
                    m.header.stamp = self.stamp()
                    h = HazardDetection()
                    h.header.stamp, h.header.frame_id = self.stamp(), 'bump_front_center'
                    h.type = HazardDetection.BUMP
                    m.detections.append(h)
                    self.haz_pub.publish(m)
            elif d > ROBOT_RADIUS + 0.03:
                self.bump_armed = True

        def drive_scripted(self, now):
            """Undock, dock and wall-follow motions (the base ignores /cmd_vel while it does them)."""
            if self.mode == 'wall':
                if now >= self.wf_next:
                    self.wf_cmd = wall_follow_cmd(wall_follow_ranges(truth_grid, self.x, self.y, self.yaw, self.wf_side),
                                                  self.wf_side)
                    self.wf_next = now + WF_PERIOD_S
                tv, tw = self.wf_cmd[0], self.wf_cmd[1]
                if self.stuck or now < self.bump_until:
                    tv = tw = 0.0
                self.v = slew(self.v, tv, MAX_ACC_LIN / TICK_HZ)
                self.w = slew(self.w, tw, MAX_ACC_ANG / TICK_HZ)
                return
            if self.mode == 'undock':
                el = now - self.phase_t
                if self.phase == 'prep':
                    self.v = self.w = 0.0
                    if el >= UNDOCK_PREP_S:
                        self.phase, self.phase_t = 'back', now
                        self.mode_start_xy = (self.x, self.y)
                        self.docked = False
                        self.event('undocked')
                elif self.phase == 'back':
                    self.v, self.w = -UNDOCK_SPEED, 0.0
                    if math.hypot(self.x - self.mode_start_xy[0], self.y - self.mode_start_xy[1]) >= UNDOCK_DISTANCE:
                        self.phase, self.phase_t = 'settle', now
                        self.v = 0.0
                elif self.phase == 'settle':
                    self.v = self.w = 0.0
                    if el >= UNDOCK_SETTLE_S:
                        self.phase = 'done'
            elif self.mode == 'dock':
                if self.phase in ('turn', 'drive', 'align'):
                    self.v, self.w, self.phase = goto_step(self.x, self.y, self.yaw, dock[0], dock[1], dock[2], self.phase)
                    if self.phase == 'done':
                        self.v = self.w = 0.0
                        self.phase_t = now
                        self.phase = 'settle'
                elif self.phase == 'settle':
                    self.v = self.w = 0.0
                    if now - self.phase_t >= DOCK_SETTLE_S:
                        self.docked = True
                        self.phase = 'done'
                        self.event('docked')

        # ---- publishers
        def send_tf(self):
            t = TransformStamped()
            t.header.stamp = self.stamp()
            t.header.frame_id, t.child_frame_id = 'odom', 'base_link'
            t.transform.translation.x, t.transform.translation.y = self.ox, self.oy
            t.transform.rotation.z, t.transform.rotation.w = math.sin(self.oyaw / 2), math.cos(self.oyaw / 2)
            self.tf.sendTransform(t)

        def pub_odom(self):
            now = now_s()
            if self.is_stalled(now):
                return
            with self.lock:
                ox, oy, oyaw, v, w = self.ox, self.oy, self.oyaw, self.v, self.w
            m = Odometry()
            m.header.stamp = self.stamp()
            m.header.frame_id, m.child_frame_id = 'odom', 'base_link'
            m.pose.pose.position.x, m.pose.pose.position.y = ox, oy
            m.pose.pose.orientation.z, m.pose.pose.orientation.w = math.sin(oyaw / 2), math.cos(oyaw / 2)
            m.twist.twist.linear.x, m.twist.twist.angular.z = v, w
            for i in (0, 7, 14, 21, 28, 35):
                m.pose.covariance[i] = 0.01
                m.twist.covariance[i] = 0.01
            self.odom_pub.publish(m)

        def pub_scan(self):
            with self.lock:
                if self.docked and not args.scan_when_docked:
                    return
                x, y, yaw = self.x, self.y, self.yaw
            lx = x + LASER_X * math.cos(yaw)
            ly = y + LASER_X * math.sin(yaw)
            r = raycast(scan_grid, lx, ly, yaw + LASER_YAW)
            if args.scan_noise > 0:
                r = np.where(np.isfinite(r), r + rng.normal(0.0, args.scan_noise, len(r)), r)
            m = LaserScan()
            m.header.stamp = self.stamp()
            m.header.frame_id = 'rplidar_link'
            m.angle_min, m.angle_increment = -math.pi, 2 * math.pi / SCAN_BEAMS
            m.angle_max = m.angle_min + m.angle_increment * (SCAN_BEAMS - 1)
            m.scan_time, m.time_increment = 1.0 / SCAN_HZ, 0.0
            m.range_min, m.range_max = SCAN_RANGE_MIN, SCAN_RANGE_MAX
            m.ranges = [float(v) for v in r]
            self.scan_pub.publish(m)

        def pub_slow(self):
            with self.lock:
                docked = self.docked
                dist = math.hypot(self.x - dock[0], self.y - dock[1])
                rate = BATTERY_CHARGE if docked else -BATTERY_DRAIN
                self.battery = clamp(self.battery + rate, 0.0, 1.0)
                level = self.battery
            d = DockStatus()
            d.header.stamp = self.stamp()
            d.is_docked = docked
            d.dock_visible = dist < 2.0
            self.dock_pub.publish(d)
            b = BatteryState()
            b.header.stamp = self.stamp()
            b.percentage, b.voltage, b.current = float(level), 15.5, 1.0 if docked else -0.6
            b.power_supply_status = 0
            b.present = True
            self.batt_pub.publish(b)
            h = HazardDetectionVector()
            h.header.stamp = self.stamp()
            self.haz_pub.publish(h)

        def log_state(self):
            with self.lock:
                x, y, yaw, v, mode, docked = self.x, self.y, self.yaw, self.speed_true, self.mode, self.docked
                stuck = self.stuck
                est = self.est
            rec = {
                't': round(now_s() - self.t0, 3), 'x': round(x, 3), 'y': round(y, 3), 'yaw': round(yaw, 3),
                'speed': round(v, 3), 'wall': round(truth_grid.nearest_obstacle(x, y), 3),
                'mode': mode, 'docked': docked, 'stuck': stuck}
            if est:     # the last AMCL estimate and its error at that moment (AMCL publishes only after it moved)
                rec.update(est_x=est[0], est_y=est[1], est_err_x=est[2], est_err_y=est[3])
            self.log.write(json.dumps(rec) + '\n')

        def watch_runtime(self):
            if args.max_runtime and now_s() - self.t0 > args.max_runtime:
                self.get_logger().warn('max runtime reached, shutting down')
                raise KeyboardInterrupt

        # ---- actions
        def on_goal(self, goal):
            return GoalResponse.ACCEPT

        def on_cancel(self, goal_handle):
            return CancelResponse.ACCEPT

        def on_wf_goal(self, goal):
            with self.lock:
                busy = self.docked or self.mode != 'nav'
            if busy or int(goal.follow_side) not in (1, -1):
                return GoalResponse.REJECT
            return GoalResponse.ACCEPT

        def exec_wall_follow(self, gh):
            result = WallFollow.Result()
            side = int(gh.request.follow_side)
            req = gh.request.max_runtime
            limit = req.sec + req.nanosec * 1e-9
            limit = limit if limit > 0 else DEFAULT_MAX_RUNTIME
            with self.lock:
                started = (not self.docked) and self.mode == 'nav'
                if started:
                    self.mode, self.wf_side, self.wf_next, self.wf_cmd = 'wall', side, 0.0, (0.0, 0.0, False)
            self.event('wall_follow_goal', started=started, side=side, max_runtime=round(limit, 1))
            if not started:
                gh.abort()
                return result
            t0 = now_s()
            outcome = 'done'
            while now_s() - t0 < limit:
                if gh.is_cancel_requested:
                    outcome = 'canceled'
                    break
                with self.lock:
                    engaged = bool(self.wf_cmd[2])
                try:
                    fb = WallFollow.Feedback()
                    fb.engaged = engaged
                    gh.publish_feedback(fb)
                except Exception:   # noqa: BLE001 - feedback is optional
                    pass
                time.sleep(0.1)
            with self.lock:
                if self.mode == 'wall':
                    self.mode = 'nav'
                self.wf_cmd = (0.0, 0.0, False)
            run_s = now_s() - t0
            result.runtime.sec = int(run_s)
            result.runtime.nanosec = int((run_s - int(run_s)) * 1e9)
            self.event('wall_follow_end', outcome=outcome, runtime=round(run_s, 2), x=round(self.x, 2), y=round(self.y, 2))
            if outcome == 'canceled':
                gh.canceled()
            else:
                gh.succeed()
            return result

        def exec_undock(self, gh):
            result = Undock.Result()
            with self.lock:
                if self.docked and self.mode == 'nav':
                    self.mode, self.phase, self.phase_t = 'undock', 'prep', now_s()
                    started = True
                else:
                    started = False
            self.event('undock_goal', started=started)
            end = now_s() + 60.0
            while started and now_s() < end:
                if gh.is_cancel_requested:
                    with self.lock:
                        self.mode, self.v, self.w = 'nav', 0.0, 0.0
                    gh.canceled()
                    return result
                with self.lock:
                    if self.phase == 'done':
                        self.mode = 'nav'
                        self.undock_done = now_s()
                        break
                time.sleep(0.05)
            ok = (not started) or self.mode == 'nav'
            if hasattr(result, 'is_undocked'):
                result.is_undocked = bool(ok and not self.docked)
            if ok:
                gh.succeed()
            else:
                with self.lock:
                    self.mode = 'nav'
                gh.abort()
            return result

        def exec_dock(self, gh):
            result = Dock.Result()
            with self.lock:
                dist = math.hypot(self.x - dock[0], self.y - dock[1])
                already = self.docked
                self.dock_goals += 1
                forced_fail = self.dock_goals <= args.dock_fail_first
                if not already and not forced_fail and dist <= DOCK_RANGE and self.mode == 'nav':
                    self.mode, self.phase, self.phase_t = 'dock', 'turn', now_s()
                    started = True
                else:
                    started = False
            self.event('dock_goal', started=started, dist=round(dist, 2))
            if already:
                if hasattr(result, 'is_docked'):
                    result.is_docked = True
                gh.succeed()
                return result
            if not started:
                time.sleep(DOCK_SEARCH_S)
                if hasattr(result, 'is_docked'):
                    result.is_docked = False
                gh.abort()
                return result
            end = now_s() + DOCK_TIMEOUT_S
            while now_s() < end:
                if gh.is_cancel_requested:
                    with self.lock:
                        self.mode, self.v, self.w = 'nav', 0.0, 0.0
                    gh.canceled()
                    return result
                with self.lock:
                    if self.phase == 'done':
                        self.mode = 'nav'
                        break
                try:
                    fb = Dock.Feedback()
                    if hasattr(fb, 'sees_dock'):
                        fb.sees_dock = True
                    gh.publish_feedback(fb)
                except Exception:   # noqa: BLE001 - feedback is optional
                    pass
                time.sleep(0.2)
            ok = self.docked
            if hasattr(result, 'is_docked'):
                result.is_docked = bool(ok)
            if ok:
                gh.succeed()
            else:
                with self.lock:
                    self.mode = 'nav'
                gh.abort()
            return result

    def on_term(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_term)
    rclpy.init()
    node = FakeBase()
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.event('end')
        try:
            node.log.close()
            ex.shutdown()
            node.destroy_node()
        finally:
            rclpy.try_shutdown()
    return 0


def parse_pose(text):
    """'x,y,yaw_deg' -> (x, y, yaw_rad)."""
    x, y, yaw = [float(v) for v in text.split(',')]
    return x, y, math.radians(yaw)


def build_parser():
    p = argparse.ArgumentParser(description='Fake TurtleBot 4 base for the delivery simulator (domain guard: needs '
                                'ROS_DOMAIN_ID set and not 0).')
    p.add_argument('--map', required=True, help='map yaml of the route (map.yaml next to route.yaml)')
    p.add_argument('--route', help='route.yaml: dock pose and --fail-after-pose use it')
    p.add_argument('--dock-pose', help='x,y,yaw_deg (overrides the route file)')
    p.add_argument('--run-dir', required=True, help='folder for ground_truth.jsonl (under ~/robot_code/logs/delivery or /tmp)')
    p.add_argument('--glass', help='segments the scan sees through but the robot cannot pass: "x1,y1,x2,y2;..." or @sim_world.json')
    p.add_argument('--press', default='', help='fake human: "pickup:3,handoff:4" (button N after the prompt; leave out = never)')
    p.add_argument('--press-delay', type=float, default=PRESS_DELAY_S, help='seconds between prompt and press')
    p.add_argument('--stall', help='"t0,len": no /odom and /tf for len s, t0 s after the undock finished (TB-25)')
    p.add_argument('--fail-after-pose', type=int, default=0, help='the robot jams at the Nth outbound pose (needs --route)')
    p.add_argument('--drift', type=float, default=0.0, help='odometry error, for example 0.02 (2 percent)')
    p.add_argument('--scan-noise', type=float, default=0.005, help='range noise in m (sigma)')
    p.add_argument('--scan-when-docked', action='store_true', help='also publish /scan while docked (the real lidar is off)')
    p.add_argument('--dock-fail-first', type=int, default=0, metavar='N',
                   help='the first N /dock goals fail wherever the robot is (tests the mission retry)')
    p.add_argument('--map-at-dock', action='store_true',
                   help='the map frame starts at the dock (a SLAM map), so the logged AMCL error is taken in that frame')
    p.add_argument('--no-footprint', action='store_true', help='do not publish base_link -> base_footprint')
    p.add_argument('--battery', type=float, default=BATTERY_START, help='start level 0..1')
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--max-runtime', type=float, default=DEFAULT_MAX_RUNTIME, help='seconds until it ends by itself (0 = never)')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    problem = domain_problem(os.environ)
    if problem:
        print(f'REFUSING TO START: {problem}', file=sys.stderr)
        return 2
    if not run_dir_ok(args.run_dir) and os.environ.get('FAKE_BASE_ANY_DIR') != '1':
        print(f'REFUSING TO START: --run-dir {args.run_dir} is not under ~/robot_code/logs/delivery or /tmp', file=sys.stderr)
        return 2
    try:
        parse_press(args.press), parse_stall(args.stall), parse_segments(args.glass)
    except (ValueError, OSError) as e:
        print(f'bad argument: {e}', file=sys.stderr)
        return 2
    if np is None:
        print('numpy is required (sudo apt install python3-numpy)', file=sys.stderr)
        return 2
    os.makedirs(args.run_dir, exist_ok=True)
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
