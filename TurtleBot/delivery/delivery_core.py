"""Pure logic of the delivery mission (no ROS, no clock of its own): route file, odometry watch, button edges,
display text and the DeliveryMission state machine. Run on the robot through delivery_mission.py, tested
off the robot with a fake robot in tests/offline/test_delivery_mission.py.

The state machine talks to the robot only through the Robot interface below. The ROS adapter in
delivery_mission.py implements it; the tests implement it with a virtual clock.

Flow (exit code in brackets):
  preflight (route ok, docked, battery) [2] -> initial pose = dock pose -> wait for Nav2 [2]
  -> wait for steady /odom (TB-25) [2] -> undock -> outbound leg (one retry) -> pickup: wait for the
  "food placed" button (timeout: drive home empty [4]) -> inbound leg (one retry) -> handoff: wait for
  the "received" button (timeout: dock anyway) -> dock [0 or 4].
  Home trip (trip='home', "Back to the lab" in the front-panel menu): the robot is already undocked and localized;
  drive the inbound poses from the one nearest the robot, dock [4, outcome 'returned']; docked already: nothing to do.
  Alarm at any step [3]: cancel navigation, stop, chime, show NEED HELP, never drive on.
  Stop request (Ctrl+C, SIGTERM, ~/STOP file, front-panel button 2 while driving) at any step [130]: cancel
  navigation, stop, show Stopped.
Front-panel buttons: while a text is on the display the stock menu does not run Select, 3 or 4 (tested on the real
robot, 2026-11-06); only button 2 (Back) clears the text and brings the stock menu back. So the mission uses 1 (always)
and the route's 3 or 4 to answer its prompts, and 2 as the stop button while it drives.
"""
import abc
import math
import os
import textwrap
import time
import uuid
import xml.etree.ElementTree as ET
from collections import deque, namedtuple
from dataclasses import dataclass, field

# ---------------------------------------------------------------- constants (units in comments)
DISPLAY_LINES = 5            # lines on the TurtleBot 4 display
DISPLAY_CHARS = 18           # characters per line
BUTTON_IGNORE_S = 0.5        # s, presses in the first 0.5 s after arming a button wait do not count
RESHOW_PERIOD = 0.5          # s, re-publish the display text this often while waiting for a button: the stock menu
                             # acts on button 2 when it is RELEASED and wipes the text, and then button 1 would run a
                             # stock menu entry, so the gap must be short (tested on the robot 2026-11-06)
POLL = 0.1                   # s, step of every wait loop
LOW_BATTERY = 0.15           # 0..1, below this during a run: alarm
UNDOCK_TIMEOUT = 60.0        # s, undock action
DOCK_TIMEOUT = 120.0         # s, dock action
DOCK_VERIFY = 10.0           # s, /dock_status must show the new state this long after the action ended
DOCK_RETRY_DISTANCE = 0.45   # m from the dock pose, where the second dock try starts (see dock_retry_pose)
NAV_READY_TIMEOUT = 120.0    # s, wait for Nav2 and AMCL
ODOM_WAIT_TIMEOUT = 60.0     # s, wait for steady /odom (20 s settle + 5 s steady + margin)
RETRY_PAUSE = 2.0            # s, stand still before the second try of a leg
CANCEL_WAIT = 3.0            # s, wait for a cancelled navigation goal to report back
HOLD_ODOM_LIMIT = 60.0       # s, a stale /odom during a leg: wait this long for steady odometry, then alarm
HOLD_SCAN_LIMIT = 30.0       # s, a stale /scan during a leg: wait this long for the lidar, then alarm
MAX_HOLDS = 3                # holds allowed per leg; the next one raises the alarm
HAZARD_MAX_AGE = 1.0         # s, a hazard report older than this (no newer message) counts as gone
ALIVE_POLL = 2.0             # s, ask the robot for the Nav2 liveness this often during a leg
ALIVE_FAILS = 3              # polls in a row that say "not alive" before the alarm
BLOCK_WINDOW = 3.0           # s, the robot counts as not moving when it moved less than BLOCK_MIN_MOVE in this time
BLOCK_MIN_MOVE = 0.05        # m
BLOCK_NOTICE = 8.0           # s, blocked this long (continuously): ask people to step aside
BLOCK_ALARM = 120.0          # s, blocked this long (continuously): alarm
COLLISION_DO_NOTHING = 0     # nav2_msgs/CollisionMonitorState action_type values (STOP=1 SLOWDOWN=2 APPROACH=3 LIMIT=4)

# same rule as motion_shapes.SteadyOdom (TB-25); a test checks both give the same answers
ODOM_STEADY = 5.0            # s, /odom must flow this long without a gap
ODOM_MAX_GAP = 0.3           # s, a longer gap between two /odom messages restarts the window
ODOM_SETTLE_AFTER_START = 20.0   # s, never move earlier than this after the program started

SAFE_BUTTONS = (3, 4)        # allowed route settings; button 1 (Select) is always accepted too, 2 (Back) is stop
SELECT_BUTTON, STOP_BUTTON = 1, 2   # no stock menu entry runs while a text is on the display (tested 2026-11-06)
STOP_BUTTON_REASON = 'button 2'     # what Robot.stop_requested() returns after a press of button 2 while armed
HOME_POSITION_WAIT = 10.0    # s, home trip: AMCL must have published a position within this time
EXIT_DELIVERED, EXIT_REFUSED, EXIT_ALARM, EXIT_NO_FOOD, EXIT_STOPPED = 0, 2, 3, 4, 130

TRIPS = ('full', 'home')     # full = food court and back; home = "Back to the lab" from where the robot stands
STOP_HINT = '2 = Stop'       # last display line while the robot works; button 2 stops it
PICKUP_TEXT = 'Food placed?\n>Back to the lab\nPress button 1'   # same look as the front-panel menu program
HANDOFF_TEXT = 'Your food is here\n>Done, thank you\nPress button 1'

Pose = namedtuple('Pose', 'x y yaw')   # map frame, metres, yaw in degrees


class RouteError(ValueError):
    """The route file is not usable. The message says what is wrong and where."""


@dataclass
class Settings:
    pickup_timeout_s: float
    handoff_timeout_s: float
    hands_clear_s: float
    min_battery_start: float
    leg_timeout_s: float
    button_placed: int
    button_received: int
    max_speed: float = 0.20


@dataclass
class Route:
    dock_pose: Pose
    outbound: list
    inbound: list
    settings: Settings
    frame_id: str = 'map'
    map: str = ''


# ---------------------------------------------------------------- route file
def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RouteError(f'{where} must be a number, got {value!r}')
    return float(value)


def _pose(value, where):
    if not isinstance(value, dict):
        raise RouteError(f'{where} must be a mapping like {{x: 1.0, y: 0.5, yaw: 0.0}}, got {value!r}')
    for key in ('x', 'y', 'yaw'):
        if key not in value:
            raise RouteError(f'{where} is missing "{key}"')
    return Pose(_number(value['x'], f'{where}.x'), _number(value['y'], f'{where}.y'),
                _number(value['yaw'], f'{where}.yaw'))


def _pose_list(data, key):
    if key not in data:
        raise RouteError(f'route is missing "{key}"')
    items = data[key]
    if not isinstance(items, list) or not items:
        raise RouteError(f'"{key}" is empty: a leg needs at least one pose (the last one is the destination)')
    return [_pose(p, f'{key}[{i}]') for i, p in enumerate(items)]


def _positive(settings, key):
    v = _number(settings[key], f'settings.{key}')
    if v <= 0:
        raise RouteError(f'settings.{key} must be greater than 0, got {v:g}')
    return v


def _button(settings, key):
    v = settings[key]
    if isinstance(v, bool) or not isinstance(v, int):
        raise RouteError(f'settings.{key} must be a whole number, got {v!r}')
    if v == SELECT_BUTTON:
        raise RouteError(f'settings.{key} is 1: button 1 (Select) is always accepted in addition to the setting, so '
                         'the setting must be 3 or 4')
    if v == STOP_BUTTON:
        raise RouteError(f'settings.{key} is 2: button 2 (Back) is the stop button while the robot drives. Use 3 or 4')
    if v not in SAFE_BUTTONS:
        raise RouteError(f'settings.{key} is {v}: the front panel has buttons 1 to 4; use 3 or 4 (safe)')
    return v


def parse_route(data):
    """Validate an already loaded route mapping and return a Route. Raises RouteError."""
    if not isinstance(data, dict):
        raise RouteError('the route file must contain a mapping (version, dock_pose, outbound, inbound, settings)')
    if 'version' not in data:
        raise RouteError('route is missing "version"')
    if data['version'] != 1:
        raise RouteError(f'route version {data["version"]!r} is not supported (expected 1)')
    frame = data.get('frame_id', 'map')
    if frame != 'map':
        raise RouteError(f'frame_id is {frame!r}; only "map" is supported')
    if 'dock_pose' not in data:
        raise RouteError('route is missing "dock_pose"')
    dock_pose = _pose(data['dock_pose'], 'dock_pose')
    outbound = _pose_list(data, 'outbound')
    inbound = _pose_list(data, 'inbound')
    if 'settings' not in data or not isinstance(data['settings'], dict):
        raise RouteError('route is missing "settings"')
    s = data['settings']
    required = ('pickup_timeout_s', 'handoff_timeout_s', 'hands_clear_s', 'min_battery_start',
                'leg_timeout_s', 'button_placed', 'button_received')
    for key in required:
        if key not in s:
            raise RouteError(f'settings is missing "{key}"')
    hands = _number(s['hands_clear_s'], 'settings.hands_clear_s')
    if hands < 0:
        raise RouteError(f'settings.hands_clear_s must be 0 or more, got {hands:g}')
    battery = _number(s['min_battery_start'], 'settings.min_battery_start')
    if not 0.0 <= battery <= 1.0:
        raise RouteError(
            f'settings.min_battery_start must be between 0 and 1 (a fraction, not percent), got {battery:g}')
    placed, received = _button(s, 'button_placed'), _button(s, 'button_received')
    if placed == received:
        raise RouteError(f'button_placed and button_received are both {placed}; they must differ')
    max_speed = _number(s.get('max_speed', 0.20), 'settings.max_speed')
    return Route(dock_pose, outbound, inbound,
                 Settings(_positive(s, 'pickup_timeout_s'), _positive(s, 'handoff_timeout_s'), hands, battery,
                          _positive(s, 'leg_timeout_s'), placed, received, max_speed),
                 frame, str(data.get('map', '')))


def load_route(path):
    """Read and validate a route.yaml. Raises RouteError (also for an unreadable file or bad YAML)."""
    import yaml   # lazily: `delivery_mission.py --help` must work even without it
    try:
        with open(path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise RouteError(f'cannot read route file {path}: {e}') from e
    except yaml.YAMLError as e:
        raise RouteError(f'route file {path} is not valid YAML: {e}') from e
    return parse_route(data)


def describe_route(route):
    """Lines that summarise a route (used by the dry run)."""
    s = route.settings
    return [f'dock pose: x {route.dock_pose.x:g} y {route.dock_pose.y:g} yaw {route.dock_pose.yaw:g} deg',
            f'outbound: {len(route.outbound)} poses, pickup at x {route.outbound[-1].x:g} y {route.outbound[-1].y:g}',
            f'inbound: {len(route.inbound)} poses, handoff at x {route.inbound[-1].x:g} y {route.inbound[-1].y:g}',
            f'buttons: food placed = {s.button_placed}, food received = {s.button_received}',
            f'timeouts: pickup {s.pickup_timeout_s:g} s, handoff {s.handoff_timeout_s:g} s, leg {s.leg_timeout_s:g} s, '
            f'hands clear {s.hands_clear_s:g} s; refuse to start below {s.min_battery_start * 100:.0f} % battery']


# ---------------------------------------------------------------- odometry watch (TB-25)
class SteadyOdomWatch:
    """Safe-to-move rule, same as motion_shapes.SteadyOdom: the program is at least settle_after seconds old AND /odom
    has arrived for `steady` seconds with no gap over max_gap. Pure: all times are passed in (any clock).

    started = time the program started (None = no settle time). Call update(t) for every /odom message,
    ready(now) any time. A gap over max_gap restarts the window.
    """

    def __init__(self, steady=ODOM_STEADY, max_gap=ODOM_MAX_GAP, started=None, settle_after=ODOM_SETTLE_AFTER_START):
        self.steady, self.max_gap = steady, max_gap
        self.started, self.settle_after = started, settle_after
        self.window_start = None
        self.last = None
        self.gaps = 0
        self.last_gap = 0.0
        self.longest_gap = 0.0

    def update(self, t):
        """Record a message. Returns the gap (s) if it was over max_gap and restarted the window, else None."""
        gap = None
        if self.last is not None:
            self.longest_gap = max(self.longest_gap, t - self.last)
            if t - self.last > self.max_gap + 1e-9:
                gap = t - self.last
                self.gaps += 1
                self.last_gap = gap
                self.window_start = t
        if self.window_start is None:
            self.window_start = t
        self.last = t
        return gap

    def age(self, now):
        """Seconds since the last message (inf before the first)."""
        return float('inf') if self.last is None else now - self.last

    def ready(self, now):
        if self.started is not None and now - self.started < self.settle_after:
            return False
        return (self.last is not None and now - self.last <= self.max_gap + 1e-9
                and self.last - self.window_start >= self.steady)


# ---------------------------------------------------------------- buttons
class ButtonEdge:
    """Turns samples of the 4 buttons into single press events.

    A press is a rising edge (False -> True). A held button counts once. Samples in the first ignore_s seconds after
    arming only set the baseline, so a button that was pressed (or is still held) before the wait began does not count.
    update(now, sample) returns the list of button numbers (1..4) that went down since the last sample.
    """

    def __init__(self, armed_at, ignore_s=BUTTON_IGNORE_S):
        self.armed_at, self.ignore_s = armed_at, ignore_s
        self.prev = None

    def update(self, now, sample):
        if sample is None:
            return []
        cur = [bool(b) for b in list(sample)[:4]]
        cur += [False] * (4 - len(cur))
        if now - self.armed_at < self.ignore_s:
            self.prev = cur
            return []
        prev = self.prev if self.prev is not None else [False] * 4
        self.prev = cur
        return [i + 1 for i in range(4) if cur[i] and not prev[i]]


# ---------------------------------------------------------------- hazards and progress
class HazardLatch:
    """Follows the LATEST hazard report: update(now, text) with the reason text, or None for a message without a
    relevant detection (clears it). current(now) is the reason, or None when there is none or no message has come
    for max_age seconds (so one bump does not latch an alarm forever)."""

    def __init__(self, max_age=HAZARD_MAX_AGE):
        self.max_age = max_age
        self.text = None
        self.time = None

    def update(self, now, text):
        self.text, self.time = text, now

    def current(self, now):
        if self.text is None or self.time is None or now - self.time > self.max_age:
            return None
        return self.text


def dock_retry_pose(handoff, dock, distance=DOCK_RETRY_DISTANCE):
    """Where to drive before the second dock try: on the line from the handoff pose to the dock, `distance` from the
    dock pose, keeping the handoff yaw. A handoff pose that is already that close is returned unchanged.

    Not the handoff pose itself: a dock that failed there usually means AMCL is off along the wall, so the robot
    believes it IS at the handoff pose and a leg to that pose ends at once without moving. A failed dock also suggests
    the robot is further away than it believes, which makes moving closer the safe direction."""
    gap = math.hypot(handoff.x - dock.x, handoff.y - dock.y)
    if gap <= distance:
        return handoff
    k = distance / gap
    return Pose(dock.x + (handoff.x - dock.x) * k, dock.y + (handoff.y - dock.y) * k, handoff.yaw)


def poses_ahead(poses, x, y):
    """The poses of a straight-ish path that the robot at (x, y) has not passed yet; never one behind the robot.
    Pose i (not the last) is behind the robot when the robot is beyond it along the segment to pose i+1. Everything up
    to and including the last such pose is dropped; the final pose is always kept."""
    last_behind = -1
    for i in range(len(poses) - 1):
        dx, dy = poses[i + 1].x - poses[i].x, poses[i + 1].y - poses[i].y
        if (x - poses[i].x) * dx + (y - poses[i].y) * dy > 0:
            last_behind = i
    return list(poses[last_behind + 1:])


def home_poses(inbound, x, y):
    """The inbound poses a robot at (x, y) still has to drive on the way home: from the pose nearest to the robot to
    the end (the last pose, next to the dock, is always included). Used by the "Back to the lab" trip."""
    nearest = min(range(len(inbound)), key=lambda i: math.hypot(inbound[i].x - x, inbound[i].y - y))
    return list(inbound[nearest:])


class BlockedTracker:
    """Pure helper for Robot.blocked(): the collision monitor reports a non-zero action AND odometry shows the robot
    moved less than min_move metres in the last `window` seconds. Needs odometry that covers the whole window and is
    fresh (newest sample under 1 s old), otherwise it says False: this feature must never stop a run by itself."""

    def __init__(self, window=BLOCK_WINDOW, min_move=BLOCK_MIN_MOVE):
        self.window, self.min_move = window, min_move
        self.samples = deque()
        self.action = COLLISION_DO_NOTHING

    def update_odom(self, t, x, y):
        self.samples.append((t, x, y))
        while len(self.samples) > 2 and self.samples[1][0] < t - self.window:
            self.samples.popleft()

    def set_action(self, action_type):
        self.action = int(action_type)

    def blocked(self, now):
        if self.action == COLLISION_DO_NOTHING or not self.samples:
            return False
        if now - self.samples[-1][0] > 1.0 or self.samples[0][0] > now - self.window + 0.5:
            return False
        _, x, y = self.samples[-1]
        recent = [q for q in self.samples if q[0] >= now - self.window]
        return all(math.hypot(q[1] - x, q[2] - y) < self.min_move for q in recent)


def new_run_id():
    """UTC stamp plus 6 hex characters, e.g. 20261105T101530Z-a1b2c3."""
    return time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:6]


def _battery_text(value):
    return 'na' if value is None else f'{value:.2f}'


def format_summary(result):
    """The one final line of a run, easy to parse: SUMMARY run=... exit=... outcome=... key=value ..."""
    return (f'SUMMARY run={result.run_id} exit={result.code} outcome={result.outcome} '
            f'duration_s={result.duration_s:.0f} holds={result.holds} retries={result.retries} '
            f'blocked_s={result.blocked_s:.0f} battery_start={_battery_text(result.battery_start)} '
            f'battery_end={_battery_text(result.battery_end)}')


def bt_file_problem(path):
    """None if the behavior tree file exists and is XML with a BehaviorTree, else a message for the preflight."""
    if not os.path.isfile(path):
        return (f'behavior tree file {path} is missing (it belongs next to delivery_mission.py in config/; '
                'copy the whole delivery folder to the robot)')
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        return f'behavior tree file {path} cannot be read: {e}'
    if root.find('BehaviorTree') is None:
        return f'behavior tree file {path} has no BehaviorTree element'
    return None


# ---------------------------------------------------------------- display
def display_wire(text, width=DISPLAY_CHARS):
    """What to publish on /hmi/display/message for display_text() output. The real turtlebot4_node cuts the message
    every `width` characters and does not split on newlines (measured on the robot, 2026-11-06), so a line break has to
    be written as spaces up to the end of the line."""
    lines = text.split('\n')
    return ''.join(ln.ljust(width) for ln in lines[:-1]) + lines[-1]


def display_text(lines, width=DISPLAY_CHARS, rows=DISPLAY_LINES):
    """Text for the robot display: every line wrapped to `width` characters, at most `rows` lines. lines is a string
    (lines separated by newline) or a list of strings. Returns one string with newlines."""
    if isinstance(lines, str):
        lines = lines.split('\n')
    out = []
    for raw in lines:
        text = ' '.join(str(raw).split())
        if not text:
            out.append('')
            continue
        out.extend(textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False))
    while out and not out[-1]:
        out.pop()
    return '\n'.join(out[:rows])


# ---------------------------------------------------------------- robot interface
class Robot(abc.ABC):
    """What the mission needs from the robot. The ROS adapter and the test fake implement all of it.

    Time: now() is a monotonic clock in seconds. sleep(s) waits s seconds AND lets ROS callbacks run (on the robot it
    spins the node; in tests it advances a virtual clock). Every wait in the mission is built from sleep(POLL).
    Sensor getters return None when no data has arrived yet.
    Start methods return at once; the matching *_done / nav_done poll for the result.
    """

    @abc.abstractmethod
    def now(self): ...

    @abc.abstractmethod
    def sleep(self, seconds): ...

    @abc.abstractmethod
    def battery(self):
        """Battery charge 0..1, or None."""

    @abc.abstractmethod
    def is_docked(self):
        """True / False from /dock_status, or None if unknown."""

    @abc.abstractmethod
    def buttons(self):
        """Latest front-panel state as a list of 4 bools (index 0 = button 1), or None. The adapter latches a press
        that was released again between two calls, so a quick tap is not lost."""

    @abc.abstractmethod
    def odom_steady(self):
        """True when SteadyOdomWatch says the base is safe to move (20 s since start and 5 s of steady /odom)."""

    @abc.abstractmethod
    def safety_problem(self):
        """A reason string if the base reports a real hazard right now (bump, cliff or wheel drop; never backup limit
        or proximity), else None. The mission asks only during navigation legs, not while docking or undocking."""

    @abc.abstractmethod
    def stale_sensor(self):
        """'odom' if /odom is older than 2 s, 'scan' if the lidar is running (undocked) but its scans are older than
        2 s, else None. These are transient (TB-25, lidar restarts), so the mission holds instead of alarming."""

    def nav_alive(self):
        """True / False if Nav2 is alive (lifecycle_manager_navigation/is_active), None if not known yet. Polled by the
        mission every ALIVE_POLL s during legs and must not block. None never raises an alarm."""
        return None

    def blocked(self):
        """True while the collision monitor reports a non-zero action and the robot has moved under 5 cm by odometry
        in the last 3 s. False when the topic never publishes."""
        return False

    def after_undock(self):  # noqa: B027 (optional hook: the default does nothing)
        """Called once after a good undock. The ROS adapter stops the OAK-D camera here. Optional."""

    def set_stop_button(self, armed):  # noqa: B027 (optional hook: the default does nothing)
        """armed=True: from now on a press of front-panel button 2 makes stop_requested() return 'button 2' (the mission
        arms it while it drives, undocks, docks or prepares). armed=False: button 2 means nothing (the mission disarms
        it while it waits for an answer, because there button 2 only brings the text back). Optional."""

    def position(self):
        """(x, y) of the robot in the map frame from AMCL (/amcl_pose), or None if AMCL has published none."""
        return None

    @abc.abstractmethod
    def poses_remaining(self):
        """How many poses of the goal sent last are not reached yet (NavigateThroughPoses feedback
        number_of_poses_remaining, or by position with poses_ahead if the feedback has no count). The count includes
        the pose being driven to, so the poses still to send are goal[-n:]. None if unknown."""

    @abc.abstractmethod
    def stop_requested(self):
        """A reason string (e.g. 'SIGINT', '~/STOP file') if the person asked to stop, else None."""

    @abc.abstractmethod
    def show(self, text):
        """Publish text on the robot display (already limited to 5 lines x 18 characters)."""

    @abc.abstractmethod
    def chime(self, kind):
        """Play a sound: 'start', 'arrive', 'thanks' or 'alarm'."""

    @abc.abstractmethod
    def set_initial_pose(self, pose):
        """Tell AMCL where the robot is (Pose in the map frame)."""

    @abc.abstractmethod
    def wait_nav_ready(self, timeout):
        """Block (spinning, stop-aware) until Nav2 and AMCL are active and localized. True if ready in time."""

    @abc.abstractmethod
    def clear_costmaps(self):
        """Clear the global and local costmaps (before the second try of a leg)."""

    @abc.abstractmethod
    def undock_start(self): ...

    @abc.abstractmethod
    def undock_done(self):
        """None while running, True if it succeeded, False if it failed."""

    @abc.abstractmethod
    def go_through(self, poses):
        """Start a NavigateThroughPoses goal with these Poses. A rejected goal shows up as nav_done() == 'failed'."""

    @abc.abstractmethod
    def nav_done(self):
        """None while running, else 'succeeded', 'failed' or 'canceled'."""

    @abc.abstractmethod
    def cancel_nav(self):
        """Cancel the running navigation goal (no-op if none)."""

    @abc.abstractmethod
    def dock_start(self): ...

    @abc.abstractmethod
    def dock_done(self):
        """None while running, True if it succeeded, False if it failed."""

    @abc.abstractmethod
    def stop_motion(self):
        """Cancel any dock/undock goal and send zero velocity for a while. Safe to call at any time, repeatedly."""


# ---------------------------------------------------------------- mission
class _Finish(Exception):
    def __init__(self, reason=''):
        super().__init__(reason)
        self.reason = reason


class _Refuse(_Finish):
    pass


class _Stop(_Finish):
    pass


class _Alarm(_Finish):
    pass


class _DockFailed(_Alarm):
    """The dock action failed or /dock_status did not confirm. The mission retries once from the handoff pose."""


@dataclass
class MissionResult:
    code: int
    outcome: str
    reason: str = ''
    events: list = field(default_factory=list)   # (time, event, detail)
    run_id: str = ''
    duration_s: float = 0.0
    holds: int = 0
    retries: int = 0
    blocked_s: float = 0.0
    battery_start: object = None
    battery_end: object = None


def preflight_problems(robot, route, allow_undocked=False):
    """List of reasons the mission must not start (empty = fine). Also used by the dry run."""
    problems = []
    docked = robot.is_docked()
    if docked is None:
        problems.append('no /dock_status from the base')
    elif not docked and not allow_undocked:
        problems.append('the robot is not on the dock (put it on the dock, or use --allow-undocked if it is already '
                        'localized on the route map)')
    battery = robot.battery()
    if battery is None:
        problems.append('no /battery_state')
    elif battery < route.settings.min_battery_start:
        problems.append(f'battery {battery * 100:.0f} % is below the minimum '
                        f'{route.settings.min_battery_start * 100:.0f} %')
    return problems


class DeliveryMission:
    """Runs one delivery with a Robot. run() returns a MissionResult and never raises."""

    def __init__(self, robot, route, allow_undocked=False, logger=None, run_id=None, trip='full'):
        if trip not in TRIPS:
            raise ValueError(f'trip must be one of {TRIPS}, got {trip!r}')
        self.robot, self.route, self.trip = robot, route, trip
        # the home trip starts away from the dock by definition; a docked robot is then "nothing to do", not a refusal
        self.allow_undocked = allow_undocked or trip == 'home'
        self.run_id = run_id or new_run_id()
        self.holds = self.retries = 0
        self.blocked_s = 0.0
        self.logger = logger          # optional callable(time, event, detail), called for every event
        self.events = []
        self._nav_active = False
        self._last_shown = None
        self._food_message = None

    # ---- helpers
    def _emit(self, event, detail=''):
        t = self.robot.now()
        self.events.append((t, event, detail))
        if self.logger:
            self.logger(t, event, detail)

    def _show(self, text, force=True):
        text = display_text(text)
        if text != self._last_shown:
            self._emit('show', text.replace('\n', ' | '))
            self._last_shown = text
        if force:
            self.robot.show(text)

    def _chime(self, kind):
        self._emit('chime', kind)
        self.robot.chime(kind)

    def _arm(self, armed):
        """Front-panel button 2 is the stop button while the robot works, and only then."""
        self._emit('stop_button', 'armed' if armed else 'disarmed')
        self.robot.set_stop_button(armed)

    def _tick(self, moving, battery_check=True):
        """Checked in every wait step: stop request, low battery, and (moving=True, navigation legs only) hazards.
        Not used while docking or undocking: the dock contact is expected there."""
        reason = self.robot.stop_requested()
        if reason:
            raise _Stop(reason)
        if battery_check:
            b = self.robot.battery()
            if b is not None and b < LOW_BATTERY:
                raise _Alarm(f'Battery low {b * 100:.0f}%')
        if moving:
            problem = self.robot.safety_problem()
            if problem:
                raise _Alarm(problem)

    def _pause(self, seconds, moving=False):
        end = self.robot.now() + seconds
        while self.robot.now() < end:
            self._tick(moving)
            self.robot.sleep(POLL)

    # ---- steps
    def _preflight(self):
        problems = preflight_problems(self.robot, self.route, self.allow_undocked)
        reason = self.robot.stop_requested()
        if reason:
            problems.append(f'stop requested ({reason})')
        if problems:
            raise _Refuse('; '.join(problems))
        self._emit('preflight_ok', f'battery {self.robot.battery():.2f}, docked {self.robot.is_docked()}')

    def _prepare(self, initial_pose=True):
        self._show(f'Starting\nplease wait\n{STOP_HINT}')   # the front-panel menu program goes silent on this text
        docked = self.robot.is_docked()
        if docked and initial_pose:
            self.robot.set_initial_pose(self.route.dock_pose)
            self._emit('initial_pose', f'{tuple(self.route.dock_pose)}')
        elif initial_pose:
            self._emit('initial_pose', 'skipped: --allow-undocked, the robot must already be localized')
        else:
            self._emit('initial_pose', 'skipped: home trip, the robot must already be localized')
        if not self.robot.wait_nav_ready(NAV_READY_TIMEOUT):
            reason = self.robot.stop_requested()
            if reason:
                raise _Stop(reason)
            raise _Refuse('Nav2 / AMCL did not become ready')
        self._emit('nav_ready')
        end = self.robot.now() + ODOM_WAIT_TIMEOUT
        while not self.robot.odom_steady():
            self._tick(False)
            if self.robot.now() > end:
                raise _Refuse(f'odometry not steady within {ODOM_WAIT_TIMEOUT:.0f} s (TB-25: wait a minute, run again)')
            self.robot.sleep(POLL)
        self._emit('odom_steady')

    def _undock(self):
        if not self.robot.is_docked():
            self._emit('undock', 'skipped: not docked')
            return
        self._emit('undock_start')
        self.robot.undock_start()
        end = self.robot.now() + UNDOCK_TIMEOUT
        while True:
            self._tick(False)
            done = self.robot.undock_done()
            if done is not None:
                break
            if self.robot.now() > end:
                raise _Alarm('Undock timeout')
            self.robot.sleep(POLL)
        if not done:
            raise _Alarm('Undock failed')
        if not self._wait_docked(False, DOCK_VERIFY, moving=False):
            raise _Alarm('Undock failed')
        self._emit('undocked')
        self.robot.after_undock()

    def _wait_docked(self, want, timeout, moving, battery_check=True):
        end = self.robot.now() + timeout
        while True:
            if self.robot.is_docked() is want:
                return True
            if self.robot.now() > end:
                return False
            self._tick(moving, battery_check)
            self.robot.sleep(POLL)

    def _remaining(self, sent):
        """The part of the pose list `sent` that is still ahead of the robot (never a pose behind it)."""
        n = self.robot.poses_remaining()
        if n is None:
            raise _Alarm('Progress unknown')
        n = max(1, min(int(n), len(sent)))
        return list(sent[-n:])

    def _hold(self, kind):
        """Navigation is cancelled and the base stopped; wait for the sensor to come back. Alarm after the limit."""
        limit = HOLD_ODOM_LIMIT if kind == 'odom' else HOLD_SCAN_LIMIT
        label = 'odometry' if kind == 'odom' else 'lidar'
        before = self._last_shown
        self._show(f'Paused\nwaiting for\n{label}\n{STOP_HINT}')
        self._emit('hold', f'{kind} stale, waiting up to {limit:g} s')
        start = self.robot.now()
        while True:
            self._tick(False)
            if self.robot.stale_sensor() is None and (kind != 'odom' or self.robot.odom_steady()):
                break
            if self.robot.now() - start > limit:
                raise _Alarm(f'{label.capitalize()} lost')
            self.robot.sleep(POLL)
        self._emit('hold_end', f'{kind} back after {self.robot.now() - start:.1f} s')
        if before:
            self._show(before)

    def _leg(self, name, poses):
        """Drive one leg. 'failed': clear the costmaps and send only the poses not yet reached, once. A stale /odom or
        /scan: cancel, stop, hold until it is back, resume with the remaining poses (at most MAX_HOLDS per leg; hold
        time is added to the leg deadline and does not count as a retry). Never sends a pose behind the robot."""
        s = self.route.settings
        deadline = self.robot.now() + s.leg_timeout_s
        remaining = list(poses)
        failures = holds = 0
        alive_fails = 0
        next_alive = self.robot.now() + ALIVE_POLL
        blocked_since = None
        notice_text = None      # text to put back after "Please step aside"
        last_t = self.robot.now()
        while True:
            self._emit('leg_start',
                       f'{name}: {len(remaining)} of {len(poses)} poses, failures {failures}, holds {holds}')
            self.robot.go_through(list(remaining))
            self._nav_active = True
            result = stale = None
            while True:
                self._tick(True)   # raises; run() then cancels navigation and stops
                stale = self.robot.stale_sensor()
                if stale:
                    break
                now = self.robot.now()
                if now >= next_alive:   # Nav2 liveness: a bond break resets every Nav2 node
                    next_alive = now + ALIVE_POLL
                    alive = self.robot.nav_alive()
                    alive_fails = alive_fails + 1 if alive is False else 0
                    if alive_fails >= ALIVE_FAILS:
                        raise _Alarm('Nav2 stopped')
                if self.robot.blocked():   # people in the way: wait, ask to step aside, alarm after BLOCK_ALARM
                    if blocked_since is None:
                        blocked_since = now
                    else:
                        deadline += now - last_t   # blocked time does not count toward the leg timeout
                        self.blocked_s += now - last_t
                    if now - blocked_since >= BLOCK_NOTICE and notice_text is None:
                        notice_text = self._last_shown or ''
                        self._emit('blocked', f'{now - blocked_since:.0f} s, asking people to step aside')
                        self._show(f'Please step\naside\n{STOP_HINT}')
                        self._chime('attention')
                    if now - blocked_since >= BLOCK_ALARM:
                        raise _Alarm('Blocked')
                else:
                    if notice_text is not None:
                        self._emit('unblocked', f'after {now - blocked_since:.0f} s')
                        if notice_text:
                            self._show(notice_text)
                    blocked_since = notice_text = None
                last_t = now
                result = self.robot.nav_done()
                if result is not None:
                    break
                if self.robot.now() > deadline:
                    raise _Alarm('Leg timeout')
                self.robot.sleep(POLL)
            if stale:
                remaining = self._remaining(remaining)
                self._halt()
                holds += 1
                blocked_since = notice_text = None
                if holds > MAX_HOLDS:
                    raise _Alarm('Odometry lost' if stale == 'odom' else 'Lidar lost')
                began = self.robot.now()
                self.holds += 1
                self._hold(stale)
                deadline += self.robot.now() - began
                last_t = self.robot.now()
                continue
            self._nav_active = False
            self._emit('leg_end', f'{name}: {result}')
            if result == 'succeeded':
                return
            if result == 'canceled':
                raise _Alarm('Navigation canceled')
            failures += 1
            if failures >= 2 or self.robot.now() > deadline:
                raise _Alarm('Navigation failed')
            remaining = self._remaining(remaining)
            self.retries += 1
            self._emit('retry', f'{name}: clearing costmaps and sending the {len(remaining)} remaining poses')
            self.robot.clear_costmaps()
            self._pause(RETRY_PAUSE)

    def _wait_button(self, numbers, timeout, text):
        """Show text and wait for a press of one of the buttons `numbers` (a tuple of 1..4). True if pressed, False on
        timeout. Re-shows the text every RESHOW_PERIOD s and after any other button event (button 2 clears the text
        when it is released). The stop button is disarmed meanwhile: here button 2 only re-shows."""
        edge = ButtonEdge(self.robot.now())
        start = self.robot.now()
        label = '/'.join(str(n) for n in numbers)
        self._arm(False)
        try:
            self._show(text)
            last_show = self.robot.now()
            self._emit('wait_button', f'button {label}, timeout {timeout:g} s')
            while True:
                self._tick(False)
                now = self.robot.now()
                pressed = edge.update(now, self.robot.buttons())
                hit = [n for n in pressed if n in numbers]
                if hit:
                    self._emit('button', str(hit[0]))
                    return True
                if pressed:
                    self._emit('other_button', ','.join(str(p) for p in pressed))
                    self._show(text)
                    last_show = now
                elif now - last_show >= RESHOW_PERIOD:
                    self._show(text)
                    last_show = now
                if now - start > timeout:
                    self._emit('button_timeout', label)
                    return False
                self.robot.sleep(POLL)
        finally:
            self._arm(True)

    def _dock_once(self):
        self._emit('dock_start')
        self.robot.dock_start()
        end = self.robot.now() + DOCK_TIMEOUT
        while True:
            self._tick(False, battery_check=False)   # low battery must not stop the last step: the dock charges it
            done = self.robot.dock_done()
            if done is not None:
                break
            if self.robot.now() > end:
                raise _DockFailed('Dock failed')
            self.robot.sleep(POLL)
        if not done or not self._wait_docked(True, DOCK_VERIFY, moving=False, battery_check=False):
            raise _DockFailed('Dock failed')
        self._emit('docked')

    def _dock(self):
        """Dock; if that fails, ONCE: chime, show 'Docking again', drive closer to the dock (dock_retry_pose, leg
        checks) and dock again. No retry after a stop request or with a low battery; a second failure is the alarm."""
        try:
            self._dock_once()
            return
        except _DockFailed as first:
            failure = first
        reason = self.robot.stop_requested()
        if reason:
            raise _Stop(reason)
        b = self.robot.battery()
        if b is not None and b < LOW_BATTERY:
            raise failure
        self.retries += 1
        self._emit('dock_retry', 'dock failed, driving closer to the dock and docking once more')
        self.robot.stop_motion()
        self._chime('attention')
        self._show(f'Docking again\n{STOP_HINT}')
        self._leg('dock_retry', [dock_retry_pose(self.route.inbound[-1], self.route.dock_pose)])
        self._dock_once()

    def _mission(self):
        self._arm(True)
        if self.trip == 'home':
            return self._mission_home()
        r = self.route
        s = r.settings
        placed = (SELECT_BUTTON, s.button_placed)
        received = (SELECT_BUTTON, s.button_received)
        self._preflight()
        self._prepare()
        self._show(f'Going to food court\n{STOP_HINT}')
        self._chime('start')
        self._undock()
        self._leg('outbound', r.outbound)

        # pickup
        self._chime('arrive')
        food = self._wait_button(placed, s.pickup_timeout_s, PICKUP_TEXT)
        if food:
            self._chime('thanks')
            self._show('Thank you!')
            self._pause(s.hands_clear_s)
            self._show(f'Going to the lab\n{STOP_HINT}')
        else:
            self._show(f'No food\nGoing to the lab\n{STOP_HINT}')
            self._emit('no_food')
        self._leg('inbound', r.inbound)

        # handoff
        if food:
            self._chime('arrive')
            got = self._wait_button(received, s.handoff_timeout_s, HANDOFF_TEXT)
            if got:
                self._chime('thanks')
                self._show(f'Thank you!\nDocking\n{STOP_HINT}')
            else:
                self._emit('handoff_timeout', 'docking anyway, food message stays')
                self._show(HANDOFF_TEXT)
        else:
            got = False
            self._show(f'No food today\nDocking\n{STOP_HINT}')
        self._dock()
        if food and not got:
            self._show(HANDOFF_TEXT)
        elif food:
            self._show('Thank you!\nDocked')
        else:
            self._show('No food delivered')
        return (EXIT_DELIVERED, 'delivered', '') if food else (EXIT_NO_FOOD, 'no_food', 'pickup timeout')

    def _wait_position(self):
        """Home trip: AMCL must have published a position. Returns (x, y), or refuses after HOME_POSITION_WAIT s."""
        end = self.robot.now() + HOME_POSITION_WAIT
        while True:
            self._tick(False)
            pos = self.robot.position()
            if pos is not None:
                self._emit('position', f'{pos[0]:.2f} {pos[1]:.2f}')
                return pos
            if self.robot.now() > end:
                raise _Refuse('No position from AMCL (robot not on the map)')
            self.robot.sleep(POLL)

    def _mission_home(self):
        """Back to the lab: the robot is away from the dock and already localized on the route map. Drive the
        inbound poses from the one nearest the robot, dock with the normal retry, no handoff prompt."""
        r = self.route
        self._preflight()
        if self.robot.is_docked():
            self._emit('home', 'already docked, nothing to do')
            self._show('Already docked')
            return EXIT_NO_FOOD, 'returned', 'already docked'
        self._prepare(initial_pose=False)
        x, y = self._wait_position()
        poses = home_poses(r.inbound, x, y)
        self._emit('home', f'{len(poses)} of {len(r.inbound)} inbound poses from ({x:.2f}, {y:.2f})')
        self._show(f'Going to the lab\n{STOP_HINT}')
        self._chime('start')
        self._leg('inbound', poses)
        self._show(f'Docking\n{STOP_HINT}')
        self._dock()
        self._show('Back at the lab')
        return EXIT_NO_FOOD, 'returned', 'back to the lab trip'

    def _halt(self):
        """Cancel navigation and stop the base. Each step is tried even if the one before raised."""
        if self._nav_active:
            try:
                self.robot.cancel_nav()
            except Exception as e:   # noqa: BLE001 - stopping must go on
                self._emit('error', f'cancel_nav: {e}')
            self._nav_active = False
        try:
            self.robot.stop_motion()
        except Exception as e:   # noqa: BLE001
            self._emit('error', f'stop_motion: {e}')

    def _battery_or_none(self):
        try:
            return self.robot.battery()
        except Exception:   # noqa: BLE001
            return None

    def run(self):
        """Run the mission. Never raises; returns a MissionResult (exit code, outcome, event list, run summary)."""
        code, outcome, reason = EXIT_ALARM, 'alarm', ''
        t0 = self.robot.now()
        battery_start = self._battery_or_none()
        self._emit('start', f'run {self.run_id}')
        try:
            try:
                code, outcome, reason = self._mission()
            except _Refuse as e:
                code, outcome, reason = EXIT_REFUSED, 'refused', e.reason
                self._halt()
                self._emit('refused', reason)
                self._safe_show(f'Cannot start\n{reason}')
            except _Stop as e:
                code, outcome, reason = EXIT_STOPPED, 'stopped', e.reason
                self._halt()
                self._emit('stopped', reason)
                self._safe_show('Stopped')
            except _Alarm as e:
                code, outcome, reason = self._alarm(e.reason)
            except Exception as e:   # noqa: BLE001 - never drive on after a bug
                code, outcome, reason = self._alarm(f'Internal error {type(e).__name__}', detail=repr(e))
        finally:
            try:
                self.robot.set_stop_button(False)
            except Exception as e:   # noqa: BLE001
                self._emit('error', f'set_stop_button: {e}')
            self._halt()
            self._emit('end', f'{outcome} code {code}')
        return MissionResult(code, outcome, reason, list(self.events), self.run_id, self.robot.now() - t0, self.holds,
                             self.retries, self.blocked_s, battery_start, self._battery_or_none())

    def _alarm(self, reason, detail=''):
        self._halt()
        self._emit('alarm', detail or reason)
        try:
            self.robot.chime('alarm')
        except Exception:   # noqa: BLE001
            pass
        self._safe_show(f'NEED HELP\n{reason}')
        return EXIT_ALARM, 'alarm', reason

    def _safe_show(self, text):
        try:
            self._show(text)
        except Exception as e:   # noqa: BLE001
            self._emit('error', f'show: {e}')
