#!/usr/bin/env python3
"""Front-panel menu of the delivery robot: "Go to food court" / "Back to the lab" at the top of the TurtleBot 4 display
menu, then Dock, Undock, EStop, Wall Follow Left, Wall Follow Right, Power and Help.

THIS PROGRAM CAN MOVE THE ROBOT, but only after a person presses a front-panel button: Dock, Undock and Wall Follow are
the same actions the stock menu runs, and a delivery trip needs a second press ("1 = Yes") before anything starts. The
trip itself is delivery_mission.py (it has the speed limits, hazard and stale-sensor stops, the stop button and the
timeouts). This program sends no /cmd_vel at all. ~/STOP stops an action it started and refuses to start new ones.

Why: the stock menu of turtlebot4_node cannot take custom entries and changing it needs sudo. Publishing text on
/hmi/display/message puts that node in "menu override": it shows the text, the buttons 1, 3 and 4 do nothing, and
button 2 clears the override. So this program draws its own menu through that channel and publishes it again right
after every button press and every 3 s. The logic is in menu_core.py (no ROS, tested offline).

It runs as a systemd USER service (robot/install_menu.sh, no sudo). One long-lived node only, no /odom subscription, all
clients created at the start (TB-25: every new ROS participant can stall the base topics for up to 12 s).

    python3 delivery_menu.py --help
    python3 delivery_menu.py --dry-run    # draws the menu and logs what it would do; sends no goal, no service call and
                                          # starts no process (trips and stack start are only logged)
    python3 delivery_menu.py              # the real thing (normally started by systemd)

Needs the ROS environment (source /etc/turtlebot4/setup.bash). Stop it with Ctrl+C or SIGTERM: it leaves cleanly. A
running mission and the navigation stack are NOT stopped: they were started in their own session and carry on (the
mission owns the screen and the buttons while it runs; a restarted menu notices it with pgrep and stays silent).

Files: ~/robot_code/logs/delivery/menu.log (time stamp, every press and state change), menu_<date>_<time>.out (output of
start_stack.sh and the mission of one trip). Route folder: env DELIVERY_ROUTE_DIR, default ~/robot_code/routes/current
(must hold route.yaml, written by tools/plan_route.py).

NOT VERIFIED: nothing here has run on the robot yet. Open points: the exact action and service names (dock, undock,
wall_follow, e_stop, robot_power in the robot's namespace), the WheelStatus field wheels_enabled, how fast the stock
node shows the menu again after button 2, and the systemd user service (robot/install_menu.sh).
"""
import argparse
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import delivery_core as core  # noqa: E402
import menu_core as mc  # noqa: E402
from ros_buttons import ButtonPoller  # noqa: E402

STACK_PATTERN = 'delivery_stack.launch.py'    # pgrep -f: the navigation stack runs
MISSION_PATTERN = 'delivery_mission.py'       # pgrep -f: a mission runs (the same pattern deploy.py checks)
START_STACK = os.path.join(HERE, 'robot', 'start_stack.sh')
STOP_STACK = os.path.join(HERE, 'robot', 'stop_stack.sh')
MISSION = os.path.join(HERE, 'delivery_mission.py')
DEFAULT_LOG_DIR = mc.DEFAULT_OUT_DIR
STOP_FILE = os.path.expanduser('~/STOP')
PGREP_CACHE_S = 1.0     # s, do not fork pgrep more often than this
LOG_CHUNK = 20000       # characters read from the end of an output file


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Front-panel menu of the delivery robot (Go to food court / Back to the '
                                            'lab and the stock entries). Long-lived; started by systemd.')
    p.add_argument('--dry-run', action='store_true',
                   help='draw the menu and log what would happen; no goal, no service call, no process is started')
    p.add_argument('--route-dir', default=None,
                   help=f'folder with route.yaml (default: env DELIVERY_ROUTE_DIR, else {mc.DEFAULT_ROUTE_DIR})')
    p.add_argument('--log-dir', default=DEFAULT_LOG_DIR,
                   help=f'menu.log and the trip output files (default {DEFAULT_LOG_DIR})')
    return p.parse_args(argv)


def resolve_route_dir(environ, home=None):
    return mc.route_dir_from(environ, home or os.path.expanduser('~'))


def pgrep_regex(pattern):
    """'delivery_mission.py' -> '[d]elivery_mission.py': the pgrep command line itself (or a shell running it) does not
    match its own pattern."""
    return '[' + pattern[0] + ']' + pattern[1:]


def pgrep(pattern):
    try:
        r = subprocess.run(['pgrep', '-f', pgrep_regex(pattern)], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def clean_env():
    """Environment for child processes: never DELIVERY_PAUSE (it shortens the pauses that protect the base, TB-25)."""
    env = dict(os.environ)
    env.pop('DELIVERY_PAUSE', None)
    return env


class _Goal:
    """One action goal, polled without blocking. poll(): None running, True succeeded, False failed or rejected."""

    def __init__(self, client, goal, success_status):
        self.success_status = success_status
        self.cancelled = False
        self.handle = self.result_future = None
        self.failed = not client.wait_for_server(timeout_sec=0.0)
        self.send_future = None if self.failed else client.send_goal_async(goal)

    def poll(self):
        if self.failed:
            return False
        if self.result_future is None:
            if not self.send_future.done():
                return None
            self.handle = self.send_future.result()
            if self.handle is None or not self.handle.accepted:
                self.failed = True
                return False
            self.result_future = self.handle.get_result_async()
            if self.cancelled:
                self.handle.cancel_goal_async()
        if not self.result_future.done():
            return None
        res = self.result_future.result()
        return res is not None and res.status == self.success_status

    def cancel(self):
        self.cancelled = True
        if self.handle is not None and self.result_future is not None and not self.result_future.done():
            self.handle.cancel_goal_async()


class RosMenuIO(mc.MenuIO):
    """menu_core.MenuIO on ROS 2. ONE node, created once; ROS is imported here, so --help and tests work without it."""

    def __init__(self, dry_run, log_dir):
        self.dry_run = dry_run
        self.log_dir = os.path.expanduser(log_dir)
        self.log_path = os.path.join(self.log_dir, 'menu.log')
        import rclpy
        from rclpy.action import ActionClient
        from rclpy.qos import qos_profile_sensor_data
        from rclpy.signals import SignalHandlerOptions
        from action_msgs.msg import GoalStatus
        from builtin_interfaces.msg import Duration
        from irobot_create_msgs.action import Dock, Undock, WallFollow
        from irobot_create_msgs.msg import DockStatus, WheelStatus
        from irobot_create_msgs.srv import EStop, RobotPower
        from std_msgs.msg import String
        os.makedirs(self.log_dir, exist_ok=True)   # only after the imports worked: nothing is created without ROS
        self.rclpy, self.String, self.Duration = rclpy, String, Duration
        self.Dock, self.Undock, self.WallFollow = Dock, Undock, WallFollow
        self.EStop, self.RobotPower = EStop, RobotPower
        self.success_status = GoalStatus.STATUS_SUCCEEDED
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # we handle Ctrl+C and SIGTERM ourselves
        self.node = node = rclpy.create_node('delivery_menu')
        self.state = [False] * 4
        self.latch = [False] * 4
        self.is_docked = self.wheels = None
        self.goal = None
        self.stack_proc = self.mission_proc = None
        self.pgrep_at = {}
        self.pgrep_value = {}
        self.button_poller = ButtonPoller('delivery_menu_buttons', self._on_buttons)   # about 95 Hz: polled, not spun
        node.create_subscription(DockStatus, '/dock_status', self._on_dock, qos_profile_sensor_data)
        node.create_subscription(WheelStatus, '/wheel_status', self._on_wheels, qos_profile_sensor_data)
        self.display_pub = node.create_publisher(String, '/hmi/display/message', 10)
        # every client now, at the start (TB-25: nothing new is created while the robot works)
        self.clients = {'dock': ActionClient(node, Dock, 'dock'), 'undock': ActionClient(node, Undock, 'undock'),
                        'wall': ActionClient(node, WallFollow, 'wall_follow')}
        self.estop_client = node.create_client(EStop, 'e_stop')
        self.power_client = node.create_client(RobotPower, 'robot_power')

    # ---- callbacks
    def _on_buttons(self, msg):
        self.state = [bool(b) for b in msg.button]
        self.latch = [a or b for a, b in zip(self.latch, self.state)]

    def _on_dock(self, msg):
        self.is_docked = bool(msg.is_docked)

    def _on_wheels(self, msg):
        self.wheels = bool(msg.wheels_enabled)

    # ---- time
    def now(self):
        return time.monotonic()

    def wall_time(self):
        return time.time()

    def sleep(self, seconds):
        end = time.monotonic() + seconds
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return
            self.rclpy.spin_once(self.node, timeout_sec=left)

    # ---- screen, buttons, state
    def publish(self, text):
        msg = self.String()
        msg.data = core.display_wire(text)
        self.display_pub.publish(msg)

    def buttons(self):
        self.button_poller.poll()
        out = [a or b for a, b in zip(self.latch, self.state)]
        self.latch = list(self.state)   # a tap released between two calls is reported once, then forgotten
        return out

    def docked(self):
        return self.is_docked

    def wheels_enabled(self):
        return self.wheels

    def stop_file_exists(self):
        return os.path.exists(STOP_FILE)

    def path_exists(self, path):
        return os.path.isfile(os.path.expanduser(path))

    def read_text(self, path):
        try:
            with open(os.path.expanduser(path), encoding='utf-8', errors='replace') as f:
                return f.read()[-LOG_CHUNK:]
        except OSError:
            return ''

    def log(self, line):
        text = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {line}'
        print(text, flush=True)
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(text + '\n')
        except OSError:
            pass

    # ---- processes
    def _cached_pgrep(self, pattern):
        now = time.monotonic()
        if now - self.pgrep_at.get(pattern, -1e9) >= PGREP_CACHE_S:
            self.pgrep_value[pattern] = pgrep(pattern)
            self.pgrep_at[pattern] = now
        return self.pgrep_value[pattern]

    def stack_running(self):
        return self._cached_pgrep(STACK_PATTERN) if not self.dry_run else False

    def _spawn(self, cmd, out_path, cwd=None):
        out = open(os.path.expanduser(out_path), 'ab')
        try:   # its own session: it survives this program (a restart of the menu must not stop it)
            return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, cwd=cwd,
                                    env=clean_env(), start_new_session=True)
        finally:
            out.close()

    def start_stack(self, route_dir, out_path):
        cmd = ['bash', START_STACK, 'nav', '--route-dir', route_dir]
        if self.dry_run:
            self.log('DRY RUN would run: ' + ' '.join(cmd))
            self.stack_proc = None
            return
        self.log('running: ' + ' '.join(cmd))
        self.stack_proc = self._spawn(cmd, out_path)

    def stack_poll(self):
        if self.dry_run:
            return 0
        return None if self.stack_proc is None else self.stack_proc.poll()

    def stack_cancel(self):
        if self.stack_proc is not None and self.stack_proc.poll() is None:
            self.stack_proc.terminate()

    def stop_stack_background(self):
        if self.dry_run:
            self.log('DRY RUN would run: bash ' + STOP_STACK)
            return
        self.log('running in the background: bash ' + STOP_STACK)
        subprocess.Popen(['bash', STOP_STACK], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=clean_env(), start_new_session=True)

    def start_mission(self, args, out_path):
        cmd = ['python3', MISSION, *args]
        if self.dry_run:
            self.log('DRY RUN would run: ' + ' '.join(cmd))
            self.mission_proc = None
            return
        self.log('running: ' + ' '.join(cmd))
        self.mission_proc = self._spawn(cmd, out_path, cwd=HERE)

    def mission_poll(self):
        if self.dry_run:
            return mc.NO_CODE
        if self.mission_proc is not None and self.mission_proc.poll() is None:
            return None
        if self._cached_pgrep(MISSION_PATTERN):   # started by hand, or by a menu that has been restarted
            return None
        return mc.NO_CODE if self.mission_proc is None else self.mission_proc.poll()

    # ---- actions and services
    def start_action(self, kind):
        if self.dry_run:
            self.log(f'DRY RUN would send the {kind} goal')
            self.goal = None
            return True
        if kind == 'dock':
            self.goal = _Goal(self.clients['dock'], self.Dock.Goal(), self.success_status)
        elif kind == 'undock':
            self.goal = _Goal(self.clients['undock'], self.Undock.Goal(), self.success_status)
        else:
            goal = self.WallFollow.Goal()
            goal.follow_side = (self.WallFollow.Goal.FOLLOW_LEFT if kind == 'wall_left'
                                else self.WallFollow.Goal.FOLLOW_RIGHT)
            goal.max_runtime = self.Duration(sec=mc.WALL_FOLLOW_SECONDS)
            self.goal = _Goal(self.clients['wall'], goal, self.success_status)
        return not self.goal.failed

    def action_poll(self):
        if self.dry_run:
            return True
        return None if self.goal is None else self.goal.poll()

    def action_cancel(self):
        if self.goal is not None:
            self.goal.cancel()

    def call_estop(self, on):
        if self.dry_run:
            self.log(f'DRY RUN would call e_stop with e_stop_on={on}')
            return True
        if not self.estop_client.service_is_ready():
            return False
        request = self.EStop.Request()
        request.e_stop_on = bool(on)
        self.estop_client.call_async(request)
        return True

    def call_power(self):
        if self.dry_run:
            self.log('DRY RUN would call robot_power')
            return True
        if not self.power_client.service_is_ready():
            return False
        self.power_client.call_async(self.RobotPower.Request())
        return True

    def close(self):
        try:
            self.node.destroy_node()
        finally:
            self.rclpy.try_shutdown()


# ---------------------------------------------------------------- main
stop_signal = None


def on_signal(signum, frame):
    global stop_signal
    stop_signal = signal.Signals(signum).name


def main(argv=None):
    args = parse_args(argv)
    route_dir = args.route_dir or resolve_route_dir(os.environ)
    log_dir = os.path.expanduser(args.log_dir)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    try:
        io = RosMenuIO(args.dry_run, log_dir)
    except ImportError as e:
        print(f'SETUP FAILED: ROS 2 / TurtleBot 4 packages not found ({e}). Run this on the robot with the ROS '
              'environment loaded (source /etc/turtlebot4/setup.bash)', file=sys.stderr)
        return core.EXIT_REFUSED
    menu = mc.Menu(io, route_dir, log_dir)
    try:
        io.log(f'delivery_menu started{" (DRY RUN)" if args.dry_run else ""}, pid {os.getpid()}')
        menu.run(lambda: stop_signal is not None)
        io.log(f'leaving on {stop_signal}; a running mission and the navigation stack are left alone')
    finally:
        try:
            if menu.state == 'action':
                io.action_cancel()   # the goal this program started; the base stops by itself
        finally:
            io.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
