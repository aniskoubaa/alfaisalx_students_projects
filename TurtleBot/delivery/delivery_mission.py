"""Deliver food from the food court to the lab with the TurtleBot 4: undock, drive the route with Nav2, wait for the
vendor's button, drive home, wait for the student's button, dock.

THIS PROGRAM MOVES THE ROBOT (Nav2 drives it, at the speed set in the navigation parameters). Supervised use only:
a person walks behind the robot with the TurtleBot 4 Bluetooth controller in hand. Controller button B = EMERGENCY
STOP (the base stops by itself). Do not use it unattended.

Needs (all on the robot):
  1. The navigation stack running with the route map: start it first with delivery/robot/start_stack.sh nav ...
     (see delivery/README.md). Start no other ROS program during a run (TB-25: every new ROS program can pause the
     base's topics for a while).
  2. A route.yaml written by tools/plan_route.py (format: delivery/route.example.yaml).
  3. The robot on its dock (it undocks itself), or --allow-undocked if it is already localized on the map.

How to run: log in to the robot with ssh (see delivery/README.md, Connecting), then on the robot:
    python3 delivery_mission.py --route route.yaml --dry-run      # connect, check topics and route, move nothing
    python3 delivery_mission.py --route route.yaml                # asks "is a person next to the robot?"
Real runs go detached, so a Wi-Fi drop (TB-10) does not kill them (--yes because nobody can answer a question):
    setsid nohup python3 delivery_mission.py --route route.yaml --yes > ~/robot_code/logs/delivery.out 2>&1 &
    tail -f ~/robot_code/logs/delivery.out

Options:
    --route FILE      route file (required)
    --dry-run         connect, check /odom, /dock_status, /battery_state, the buttons topic, Nav2 and the route,
                      show the first display text, never send a goal or a velocity
    --yes             skip the "is a person next to the robot?" question (needed when detached)
    --allow-undocked  start although the robot is not on the dock; then it must already be localized on the map
                      (no initial pose is sent) and the mission skips the undock
    --trip full|home  full (default): food court and back. home: "Back to the lab" from where the robot stands: the
                      robot must be undocked and localized (/amcl_pose must have given a position within 10 s, else
                      the run is refused); it skips the undock, drives route.inbound from the pose nearest to it,
                      docks with the normal retry and asks for no button. Already docked: nothing to do, exit 4
                      with outcome "returned". On success exit 4 and outcome "returned" too (nobody got food).
    --log-dir DIR     where the event log goes (default ~/robot_code/logs)

How to stop it at any time (Nav2 goal cancelled, base stopped, display shows Stopped):
    controller button B (emergency stop of the base), then one of:
    Ctrl+C in the terminal running it
    from another terminal on the robot:  touch ~/STOP          (delete it afterwards: rm ~/STOP)
    from another terminal on the robot:  pkill -INT -f delivery_mission.py

Safety built in: refuses to start when ~/STOP exists, the battery is below the route's minimum, or the robot is
not on the dock (unless --allow-undocked); waits for the base to be steady
(20 s after start and 5 s of /odom without a gap over 0.3 s, TB-25) before the first move; per-leg, undock and dock
timeouts. A stale /odom (over 2 s) or /scan (over 2 s, lidar running) during a leg is a HOLD, not an alarm: Nav2 is
cancelled, the base stopped, the display shows "Paused", and when the sensor is back (odometry: 5 s steady, at most
60 s; lidar: at most 30 s) the leg resumes with only the poses not yet reached (at most 3 holds per leg, hold time
does not count toward the leg timeout); otherwise the alarm. A bump, cliff or wheel drop during a leg raises the
alarm, but note: this robot's create3_republisher does NOT republish /hazard_detection (commented out in
republisher.yaml, ROADMAP TB-25 step 3), so the subscription will probably receive nothing and the hazard stop is
then not active; the Create 3 itself still stops on bumps and cliffs and Nav2 sees obstacles in the lidar. Backup
limit and proximity reports are ignored (proximity fires near walls, which is where the robot drives), and hazards are
not checked while docking or undocking. Battery below 15 percent raises the alarm; any alarm cancels navigation,
stops and never drives on again. Zero velocity is sent for 0.5 s on the way out, whatever happened.
Front-panel buttons: while this program has a text on the display, the stock menu does not run Select (1), 3 or 4
(tested on the real robot, 2026-11-06), and button 2 (Back) clears the text and brings the stock menu back. So the
prompts are answered with button 1 or the route's button 3 / 4, and while the robot drives, undocks, docks or prepares,
button 2 = STOP (the display says "2 = Stop"; exit 130, display "Stopped"). While it waits for an answer, button 2 only
puts the text back. The route settings button_placed and button_received stay 3 or 4.
Speed is limited by the Nav2 parameters (config/nav2_delivery.yaml), not by this program.

Exit codes: 0 delivered (also when the student did not press "received" and the robot docked anyway),
2 refused or setup failure (nothing moved), 3 alarm, the robot needs help (display shows NEED HELP and the reason),
4 returned without food (nobody pressed "food placed"), 130 stopped by you (Ctrl+C, SIGTERM, ~/STOP).
The event log is written to <log-dir>/delivery_<date>_<time>.log, one line per event, and the same events as JSON Lines
to delivery_<date>_<time>.jsonl next to it. Every line carries the run id (UTC stamp + 6 hex characters), and the last
line of the text log is exactly one summary line:
    SUMMARY run=<id> exit=<code> outcome=<...> duration_s=<n> holds=<n> retries=<n> blocked_s=<n>
        battery_start=<x> battery_end=<x>      (all on one line)

Also built in: Nav2 is driven with the delivery behavior tree config/delivery_through_poses_bt.xml (no Spin, no BackUp
recovery, 3 retries); the file must exist next to this program or the run is refused. During legs the mission polls
lifecycle_manager_navigation/is_active (std_srvs/Trigger) every 2 s: three "not active" answers in a row raise the alarm
"Nav2 stopped" (no answer yet never does). It also reads collision_monitor_state (nav2_msgs/CollisionMonitorState): a
non-zero action while the robot has moved under 5 cm in 3 s counts as blocked; after 8 s the display asks people to
step aside, after 120 s the alarm is "Blocked", and blocked time does not count toward the leg timeout (if that topic
never publishes, nothing changes). A failed dock is retried once, from 0.45 m in front of the dock.

Verified on the real robot since 2026-11-06, on a 1.1 m route in a small room: whole deliveries, the display texts, the
chimes (audible), undock and dock timing, the behavior tree path, button 2 = stop, --trip home. The longest /odom gap of
a run is printed at the end. NOT VERIFIED: a long route on campus, whether is_active ever reports a real Nav2 failure
(no real failure happened since), the CollisionMonitorState action_type values (STOP=1 SLOWDOWN=2 APPROACH=3 LIMIT=4,
0 = nothing; Jazzy sources), and the "attention" and "alarm" chimes.
"""
import argparse
import json
import math
import os
import signal
import sys
import time

PROGRAM_START = time.monotonic()      # the TB-25 settle time counts from here
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import delivery_core as core  # noqa: E402
from ros_buttons import ButtonPoller  # noqa: E402

# Behavior tree handed to Nav2 with every goal (no Spin / BackUp recovery, 3 retries); the path must exist on the robot.
BT_FILE = os.path.join(HERE, 'config', 'delivery_through_poses_bt.xml')

# ---------------------------------------------------------------- parameters
STARTUP_WAIT = 30.0           # s, wait for /odom, /dock_status and /battery_state at start
DRY_RUN_NAV_WAIT = 8.0        # s, how long the dry run waits for Nav2
ODOM_STALE = 2.0              # s, no /odom for this long while moving: hold
SCAN_STALE = 2.0              # s, no /scan for this long while undocked and moving: hold
ALIVE_PERIOD = 2.0            # s, send the Nav2 liveness call at most this often
ALIVE_TIMEOUT = 1.5           # s, no answer to a liveness call after this long counts as "not alive"
GET_STATE_TIMEOUT = 3.0       # s, no answer to a lifecycle get_state call after this long: ask again
GOAL_ANSWER_TIMEOUT = 5.0     # s, no answer to a navigation goal after this long: the leg fails (see go_through)
STOP_BURST = 0.5              # s, zero velocity is sent this long when stopping
STOP_RATE = 20                # Hz, rate of that burst
SERVER_WAIT = 5.0             # s, wait for the dock / undock action server
SERVICE_WAIT = 3.0            # s, wait for a costmap-clearing call
DEFAULT_LOG_DIR = '~/robot_code/logs'
STOP_FILE = os.path.expanduser('~/STOP')   # replaced by motion_shapes.STOP_FILE when that can be imported

# chimes: (frequency Hz, length s); kept short, the Create 3 plays them in order
CHIMES = {
    'start': [(523, 0.15), (659, 0.15), (784, 0.25)],
    'arrive': [(784, 0.2), (988, 0.2), (784, 0.2), (988, 0.4)],
    'thanks': [(659, 0.15), (784, 0.15), (1047, 0.35)],
    'attention': [(660, 0.15), (660, 0.15)],
    'alarm': [(880, 0.3), (440, 0.3), (880, 0.3), (440, 0.3), (880, 0.3), (440, 0.3)],
}

# Set by the signal handler; polled by the mission every 0.1 s.
stop_request = None
motion_active = False
RUN_ID = None   # set in main(); every console and log line carries it


def log(text):
    print(f'{time.strftime("%H:%M:%S")} ' + (f'run={RUN_ID} ' if RUN_ID else '') + text, flush=True)


def on_signal(signum, frame):
    global stop_request
    stop_request = signal.Signals(signum).name
    if not motion_active:
        raise KeyboardInterrupt   # before the mission starts: just leave; during it the mission loops stop the robot


# ---------------------------------------------------------------- ROS adapter
class RosRobot(core.Robot):
    """core.Robot on ROS 2. ONE node only (a TurtleBot4Navigator); all subscriptions sit on it (TB-25).
    ROS is imported here, not at the top of the file, so --help works without ROS."""

    def __init__(self, dry_run, bt_file=BT_FILE):
        global STOP_FILE
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from rclpy.signals import SignalHandlerOptions
        from action_msgs.msg import GoalStatus
        from action_msgs.srv import CancelGoal
        from builtin_interfaces.msg import Duration
        from geometry_msgs.msg import TwistStamped
        from irobot_create_msgs.action import Dock, Undock
        from irobot_create_msgs.msg import AudioNote, AudioNoteVector, HazardDetection, HazardDetectionVector
        from nav2_msgs.action import NavigateThroughPoses
        from nav2_msgs.srv import ClearEntireCostmap
        from nav2_simple_commander.robot_navigator import TaskResult
        from geometry_msgs.msg import PoseWithCovarianceStamped
        from nav_msgs.msg import Odometry
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import BatteryState, LaserScan
        from std_srvs.srv import Trigger
        from std_msgs.msg import String
        from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator
        self.rclpy, self.GoalStatus, self.TaskResult = rclpy, GoalStatus, TaskResult
        self.Duration, self.TwistStamped, self.String = Duration, TwistStamped, String
        self.AudioNote, self.AudioNoteVector, self.HazardDetection = AudioNote, AudioNoteVector, HazardDetection
        self.Dock, self.Undock = Dock, Undock
        self.dry_run = dry_run
        self.bt_file = bt_file
        self.Trigger = Trigger
        try:   # reuse the stop file name of the other motion programs when their folder is next to this one
            here = os.path.dirname(os.path.abspath(__file__))
            for folder in (os.path.join(here, '..', 'examples'), here, os.path.join(here, '..')):
                if os.path.exists(os.path.join(folder, 'motion_shapes.py')):
                    sys.path.append(folder)
                    import motion_shapes
                    STOP_FILE = motion_shapes.STOP_FILE
                    break
        except Exception:   # noqa: BLE001 - the default ~/STOP is the same file
            pass

        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # we handle Ctrl+C ourselves
        self.node = node = TurtleBot4Navigator()
        self.odom_watch = core.SteadyOdomWatch(started=PROGRAM_START)
        self.odom_time = self.scan_time = self.battery_level = None
        self.longest_odom_gap = 0.0
        self.motion_started = False
        self.hazard = core.HazardLatch()   # follows the latest /hazard_detection message
        self.state = [False] * 4
        self.latch = [False] * 4
        self.have_buttons = False
        self.stop_armed = self.stop_latched = False   # front-panel button 2 = stop, only while armed
        self.amcl_xy = None                           # (x, y) of the last /amcl_pose, map frame
        self.initial_pose_set = False
        self.nav_rejected = self.goal_unanswered = False
        self.NavigateThroughPoses, self.CancelGoal = NavigateThroughPoses, CancelGoal
        self.cancel_all_client = node.create_client(CancelGoal, 'navigate_through_poses/_action/cancel_goal')
        self.goal_poses = []   # core.Pose list of the goal sent last
        self.undock_run = self.dock_run = None
        self.tracker = core.BlockedTracker()   # collision monitor action + odometry -> blocked()
        self.alive_last = self.alive_future = None
        self.alive_sent = -1e9
        self.alive_seen = False
        self.alive_client = node.create_client(Trigger, 'lifecycle_manager_navigation/is_active')
        self.camera_stop_client = node.create_client(Trigger, 'oakd/stop_camera')
        try:   # optional: without the message package blocked() simply stays False
            from nav2_msgs.msg import CollisionMonitorState
            node.create_subscription(CollisionMonitorState, 'collision_monitor_state', self._on_collision, 10)
        except ImportError:
            pass
        node.create_subscription(Odometry, '/odom', self._on_odom, qos_profile_sensor_data)
        # same QoS as the Nav2 navigator uses for amcl_pose: latched, so the last pose arrives at once
        amcl_qos = QoSProfile(durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE,
                              history=HistoryPolicy.KEEP_LAST, depth=1)
        node.create_subscription(PoseWithCovarianceStamped, 'amcl_pose', self._on_amcl, amcl_qos)
        node.create_subscription(BatteryState, '/battery_state', self._on_battery, qos_profile_sensor_data)
        self.button_poller = ButtonPoller('delivery_mission_buttons', self._on_buttons)   # about 95 Hz: polled
        node.create_subscription(HazardDetectionVector, '/hazard_detection', self._on_hazard, qos_profile_sensor_data)
        node.create_subscription(LaserScan, '/scan', self._on_scan, qos_profile_sensor_data)
        self.display_pub = node.create_publisher(String, '/hmi/display/message', 10)
        self.audio_pub = node.create_publisher(AudioNoteVector, '/cmd_audio', 10)
        # /cmd_vel is only used for the zero-velocity burst when stopping.
        self.vel_pub = None if dry_run else node.create_publisher(TwistStamped, '/cmd_vel', 10)
        self.clear_clients = [node.create_client(ClearEntireCostmap, 'local_costmap/clear_entirely_local_costmap'),
                              node.create_client(ClearEntireCostmap, 'global_costmap/clear_entirely_global_costmap')]

    # ---- callbacks
    def _on_odom(self, msg):
        now = time.monotonic()
        if self.odom_time is not None and self.motion_started:   # the longest gap once the run has begun, for the log
            self.longest_odom_gap = max(self.longest_odom_gap, now - self.odom_time)
        self.odom_time = now
        self.odom_watch.update(self.odom_time)
        p = msg.pose.pose.position
        self.tracker.update_odom(self.odom_time, p.x, p.y)

    def _on_amcl(self, msg):
        p = msg.pose.pose.position
        if math.isfinite(p.x) and math.isfinite(p.y):
            self.amcl_xy = (float(p.x), float(p.y))

    def _on_collision(self, msg):
        self.tracker.set_action(msg.action_type)

    def _on_scan(self, msg):
        self.scan_time = time.monotonic()

    def _on_battery(self, msg):
        if math.isfinite(msg.percentage):
            self.battery_level = float(msg.percentage)

    def _on_buttons(self, msg):
        self.have_buttons = True
        before = self.state
        self.state = [bool(b) for b in msg.button]
        self.latch = [a or b for a, b in zip(self.latch, self.state)]
        # a press of button 2 (False -> True) counts as stop only while armed; a button held since before does not
        if self.stop_armed and len(before) > 1 and len(self.state) > 1 and self.state[1] and not before[1]:
            self.stop_latched = True

    def _on_hazard(self, msg):
        # Only a real bump, cliff or wheel drop counts. BACKUP_LIMIT and OBJECT_PROXIMITY (near walls) are ignored.
        H = self.HazardDetection
        names = {H.BUMP: 'BUMP', H.CLIFF: 'CLIFF', H.WHEEL_DROP: 'WHEEL_DROP'}
        text = None
        for d in msg.detections:
            if d.type in names:
                text = f'{names[d.type]} ({d.header.frame_id})'
        self.hazard.update(time.monotonic(), text)   # a message without one clears the hazard

    # ---- time
    def now(self):
        return time.monotonic()

    def sleep(self, seconds):
        end = time.monotonic() + seconds
        self.button_poller.poll()
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return
            self.rclpy.spin_once(self.node, timeout_sec=left)

    # ---- sensors
    def battery(self):
        return self.battery_level

    def is_docked(self):
        return self.node.is_docked

    def buttons(self):
        self.button_poller.poll()
        if not self.have_buttons:
            return [False] * 4
        out = [a or b for a, b in zip(self.latch, self.state)]
        self.latch = list(self.state)   # a tap released between two calls is reported once, then forgotten
        return out

    def odom_steady(self):
        return self.odom_watch.ready(time.monotonic())

    def safety_problem(self):
        hazard = self.hazard.current(time.monotonic())   # None when the last message was clean or is over 1 s old
        return f'Hazard {hazard}' if hazard else None

    def stale_sensor(self):
        now = time.monotonic()
        if self.odom_time is None or now - self.odom_time > ODOM_STALE:
            return 'odom'
        if self.node.is_docked is False and self.scan_time is not None and now - self.scan_time > SCAN_STALE:
            return 'scan'
        return None

    def after_undock(self):
        """The TurtleBot 4 power saver restarts the OAK-D camera on undock. The delivery does not use it, so stop it to
        free CPU for Nav2. Best effort and not waited for: without the service the run simply goes on."""
        if self.camera_stop_client.service_is_ready():
            self.camera_stop_client.call_async(self.Trigger.Request())
            log('asked the OAK-D camera to stop (not used by the delivery)')

    def poses_remaining(self):
        """Poses of the last goal not reached yet: the feedback's number_of_poses_remaining; if the feedback has no
        count, by position (core.poses_ahead from feedback.current_pose); if no feedback arrived at all, nothing was
        reached, so all of them."""
        fb = self.node.feedback
        if fb is None:
            return len(self.goal_poses) if self.goal_poses else None
        n = getattr(fb, 'number_of_poses_remaining', None)
        if n is not None:
            return int(n)
        try:
            p = fb.current_pose.pose.position
            return len(core.poses_ahead(self.goal_poses, p.x, p.y))
        except AttributeError:
            return None

    def set_stop_button(self, armed):
        self.stop_armed = bool(armed)
        self.stop_latched = False

    def position(self):
        return self.amcl_xy

    def stop_requested(self):
        if stop_request:
            return stop_request
        if self.stop_latched:
            return core.STOP_BUTTON_REASON
        if os.path.exists(STOP_FILE):
            return f'{STOP_FILE} exists'
        return None

    # ---- outputs
    def show(self, text):
        msg = self.String()
        msg.data = core.display_wire(text)
        self.display_pub.publish(msg)

    def chime(self, kind):
        msg = self.AudioNoteVector()
        msg.append = False
        for freq, length in CHIMES[kind]:
            note = self.AudioNote()
            note.frequency = int(freq)
            note.max_runtime = self.Duration(sec=int(length), nanosec=int((length % 1) * 1e9))
            msg.notes.append(note)
        self.audio_pub.publish(msg)

    # ---- navigation
    def set_initial_pose(self, pose):
        node = self.node
        node.setInitialPose(node.getPoseStamped([pose.x, pose.y], pose.yaw))
        self.initial_pose_set = True

    def wait_nav_ready(self, timeout):
        """amcl and bt_navigator active, and AMCL has published a pose. Re-publishes the initial pose every second
        (at least twice) until then, because AMCL ignores it while it is still starting. Stop-aware."""
        from lifecycle_msgs.srv import GetState
        node = self.node
        names = ('amcl', 'bt_navigator')
        clients = {n: node.create_client(GetState, f'{n}/get_state') for n in names}
        futures, active, next_poll, sent = {}, set(), {n: 0.0 for n in names}, {n: 0.0 for n in names}
        published, next_pub = 0, 0.0
        next_note = time.monotonic() + 15.0
        if self.initial_pose_set:
            node.initial_pose_received = False
        end = time.monotonic() + timeout
        try:
            while time.monotonic() < end:
                if self.stop_requested():
                    return False
                now = time.monotonic()
                for n, client in clients.items():
                    if n in active:
                        continue
                    f = futures.get(n)
                    if f is not None and f.done():
                        res = f.result()
                        futures[n] = None
                        if res is not None and res.current_state.label == 'active':
                            active.add(n)
                    elif f is not None and now - sent[n] > GET_STATE_TIMEOUT:
                        # A reply can get lost when the call is sent while the service is still being discovered, and
                        # that future then never finishes. Without this the mission refuses with Nav2 fully active.
                        log(f'no answer from {n}/get_state after {GET_STATE_TIMEOUT:g} s, asking again')
                        client.remove_pending_request(f)
                        futures[n] = None
                    elif f is None and now >= next_poll[n] and client.service_is_ready():
                        futures[n] = client.call_async(GetState.Request())
                        sent[n] = now
                        next_poll[n] = now + 1.0
                if self.initial_pose_set and now >= next_pub and (published < 2 or not node.initial_pose_received):
                    node.initial_pose.header.stamp = node.get_clock().now().to_msg()
                    node._setInitialPose()
                    published += 1
                    next_pub = now + 1.0
                pose_ok = node.initial_pose_received and (published >= 2 or not self.initial_pose_set)
                if len(active) == len(names) and pose_ok:
                    return True
                if now >= next_note:   # say what is still missing: a refusal alone cannot be diagnosed afterwards
                    missing = [n for n in names if n not in active] + ([] if pose_ok else ['a pose from AMCL'])
                    log('waiting for Nav2: still missing ' + ', '.join(missing))
                    next_note = now + 15.0
                self.sleep(0.2)
            return False
        finally:
            for c in clients.values():
                node.destroy_client(c)

    def clear_costmaps(self):
        from nav2_msgs.srv import ClearEntireCostmap
        for client in self.clear_clients:
            if client.service_is_ready():
                f = client.call_async(ClearEntireCostmap.Request())
                end = time.monotonic() + SERVICE_WAIT
                while not f.done() and time.monotonic() < end:
                    self.rclpy.spin_once(self.node, timeout_sec=0.1)

    def go_through(self, poses):
        node = self.node
        stamped = [node.getPoseStamped([p.x, p.y], p.yaw) for p in poses]
        node.result_future = node.goal_handle = node.feedback = node.status = None
        self.goal_poses = list(poses)
        self.nav_rejected = self.goal_unanswered = False
        # Not node.goThroughPoses(): it waits for the answer to the goal with no time limit. On the robot (2026-11-06)
        # the answer never came when Nav2 was resetting, and the whole mission froze, with the stop button and alarms.
        # Here no answer within GOAL_ANSWER_TIMEOUT, or a stop request, makes the leg fail the normal way.
        client = node.nav_through_poses_client
        end = time.monotonic() + GOAL_ANSWER_TIMEOUT
        while not client.wait_for_server(timeout_sec=0.2):
            self.button_poller.poll()
            if time.monotonic() > end or self.stop_requested():
                log('the navigation action server is not there')
                self.nav_rejected = True
                return
        goal = self.NavigateThroughPoses.Goal(poses=stamped, behavior_tree=self.bt_file)   # the delivery behavior tree
        node.info(f'Navigating with {len(stamped)} goals....')
        future = client.send_goal_async(goal, node._feedbackCallback)
        self.goal_unanswered = True
        while not future.done():
            self.sleep(0.05)
            if time.monotonic() > end or self.stop_requested():
                log(f'no answer to the navigation goal after {time.monotonic() - end + GOAL_ANSWER_TIMEOUT:.1f} s')
                self.nav_rejected = True
                return   # goal_unanswered stays True: cancel_nav then cancels every goal on the server
        self.goal_unanswered = False
        node.goal_handle = future.result()
        if node.goal_handle is None or not node.goal_handle.accepted:
            log('the navigation goal was rejected')
            self.nav_rejected = True
            return
        node.result_future = node.goal_handle.get_result_async()

    def nav_alive(self):
        """Non-blocking Nav2 liveness: the answer of the last lifecycle_manager_navigation/is_active call, at most one
        call per ALIVE_PERIOD. None until the first answer, and None if the service was never seen (wrong name or no
        lifecycle manager: that must not alarm). False when a call fails or times out, or the service vanished."""
        now = time.monotonic()
        f = self.alive_future
        if f is not None:
            if f.done():
                try:
                    res = f.result()
                    self.alive_last = bool(res is not None and res.success)
                except Exception:   # noqa: BLE001
                    self.alive_last = False
                self.alive_future = None
            elif now - self.alive_sent > ALIVE_TIMEOUT:
                self.alive_last = False
                self.alive_client.remove_pending_request(f)
                self.alive_future = None
        if self.alive_future is None and now - self.alive_sent >= ALIVE_PERIOD:
            if self.alive_client.service_is_ready():
                self.alive_seen = True
                self.alive_sent = now
                self.alive_future = self.alive_client.call_async(self.Trigger.Request())
            elif self.alive_seen:
                self.alive_sent = now
                self.alive_last = False
        return self.alive_last

    def blocked(self):
        return self.tracker.blocked(time.monotonic())

    def nav_done(self):
        node = self.node
        if self.nav_rejected:
            return 'failed'
        if not node.isTaskComplete():
            return None
        result = node.getResult()
        if result == self.TaskResult.SUCCEEDED:
            return 'succeeded'
        if result == self.TaskResult.CANCELED:
            return 'canceled'
        return 'failed'

    def cancel_nav(self):
        node = self.node
        if self.goal_unanswered:   # the server may have taken a goal whose answer was lost: cancel all goals it holds
            self.goal_unanswered = False
            f = self.cancel_all_client.call_async(self.CancelGoal.Request())   # zero id and time = every goal
            end = time.monotonic() + core.CANCEL_WAIT
            while not f.done() and time.monotonic() < end:
                self.rclpy.spin_once(node, timeout_sec=0.1)
            log('cancelled every navigation goal: ' + ('done' if f.done() else 'no answer'))
            return
        if node.goal_handle is None or node.result_future is None or node.result_future.done():
            return
        f = node.goal_handle.cancel_goal_async()
        end = time.monotonic() + core.CANCEL_WAIT
        while not f.done() and time.monotonic() < end:
            self.rclpy.spin_once(node, timeout_sec=0.1)
        while not node.result_future.done() and time.monotonic() < end:
            self.rclpy.spin_once(node, timeout_sec=0.1)

    # ---- dock and undock (own handling: the navigator's blocking helpers do not check the result)
    def undock_start(self):
        self.undock_run = _ActionRun(self, self.node.undock_action_client, self.Undock.Goal())

    def undock_done(self):
        return self.undock_run.poll()

    def dock_start(self):
        self.dock_run = _ActionRun(self, self.node.dock_action_client, self.Dock.Goal())

    def dock_done(self):
        return self.dock_run.poll()

    def stop_motion(self):
        for run in (self.undock_run, self.dock_run):
            if run is not None:
                run.cancel()
        if self.vel_pub is None:
            return
        end = time.monotonic() + STOP_BURST
        while time.monotonic() < end:
            msg = self.TwistStamped()
            msg.header.stamp = self.node.get_clock().now().to_msg()
            msg.header.frame_id = 'base_link'
            msg.twist.linear.x = 0.0
            msg.twist.angular.z = 0.0
            self.vel_pub.publish(msg)
            time.sleep(1.0 / STOP_RATE)

    def close(self):
        self.node.destroy_node()
        self.rclpy.try_shutdown()


class _ActionRun:
    """One send_goal / get_result round trip, polled without blocking. poll(): None running, True succeeded,
    False failed (rejected, no server, or a result status other than SUCCEEDED)."""

    def __init__(self, robot, client, goal):
        self.robot = robot
        self.handle = self.result_future = self.send_future = None
        self.failed = not client.wait_for_server(timeout_sec=SERVER_WAIT)
        if not self.failed:
            self.send_future = client.send_goal_async(goal)

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
        if not self.result_future.done():
            return None
        res = self.result_future.result()
        return res is not None and res.status == self.robot.GoalStatus.STATUS_SUCCEEDED

    def cancel(self):
        if self.handle is not None and self.result_future is not None and not self.result_future.done():
            self.handle.cancel_goal_async()


# ---------------------------------------------------------------- main
def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Deliver food with the TurtleBot 4 along a planned route. MOVES THE ROBOT.')
    p.add_argument('--route', required=True, help='route file written by tools/plan_route.py')
    p.add_argument('--dry-run', action='store_true', help='check everything and show the first text, never move')
    p.add_argument('--yes', action='store_true',
                   help='skip the "is a person next to the robot?" question (needed when detached)')
    p.add_argument('--allow-undocked', action='store_true',
                   help='start although the robot is not docked (it must already be localized on the map)')
    p.add_argument('--trip', choices=core.TRIPS, default='full',
                   help='full: food court and back (default). home: Back to the lab from where the robot stands')
    p.add_argument('--log-dir', default=DEFAULT_LOG_DIR, help=f'folder for the event log (default {DEFAULT_LOG_DIR})')
    return p.parse_args(argv)


def wait_for(robot, what, ready, seconds):
    log(f'waiting up to {seconds:.0f} s for {what}')
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if ready():
            return True
        robot.sleep(0.2)
    return ready()


def open_log(log_dir):
    folder = os.path.expanduser(log_dir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime('delivery_%Y%m%d_%H%M%S.log'))
    jsonl = open(path[:-4] + '.jsonl', 'a', buffering=1, encoding='utf-8')
    return open(path, 'a', buffering=1, encoding='utf-8'), jsonl, path


def main(argv=None):
    global motion_active, RUN_ID
    args = parse_args(argv)
    RUN_ID = core.new_run_id()
    try:
        route = core.load_route(args.route)
    except core.RouteError as e:
        log(f'REFUSING: {e}')
        return core.EXIT_REFUSED
    log(f'route {args.route} OK')
    problem = core.bt_file_problem(BT_FILE)
    if problem:
        log(f'REFUSING: {problem}')
        return core.EXIT_REFUSED
    log(f'behavior tree {BT_FILE} OK')
    for line in core.describe_route(route):
        log(f'  {line}')
    if os.path.exists(STOP_FILE):
        if not args.dry_run:
            log(f'REFUSING: {STOP_FILE} exists (left from an earlier stop). Delete it first: rm {STOP_FILE}')
            return core.EXIT_REFUSED
        log(f'warning: {STOP_FILE} exists; a real run would refuse to start until you delete it')

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    try:
        robot = RosRobot(args.dry_run)
    except ImportError as e:
        log(f'SETUP FAILED: ROS 2 / TurtleBot 4 packages not found ({e}). Run this on the robot with the ROS '
            'environment loaded (source /opt/ros/jazzy/setup.bash)')
        return core.EXIT_REFUSED
    logfile = jsonl = None
    code = core.EXIT_REFUSED
    try:
        got = wait_for(robot, '/odom, /dock_status and /battery_state (ROS starts slowly on the Pi)',
                       lambda: (robot.odom_time is not None and robot.node.is_docked is not None
                                and robot.battery_level is not None), STARTUP_WAIT)
        if not got:
            missing = [n for n, v in (('/odom', robot.odom_time), ('/dock_status', robot.node.is_docked),
                                      ('/battery_state', robot.battery_level)) if v is None]
            log('SETUP FAILED: missing ' + ', '.join(missing) +
                '. Restart the base application (see HOW-TO-CONNECT.md)')
            return core.EXIT_REFUSED
        log(f'odometry OK, docked: {robot.is_docked()}, battery {robot.battery() * 100:.0f} %')

        if args.dry_run:
            return dry_run(robot, route, args)

        problems = core.preflight_problems(robot, route, args.allow_undocked or args.trip == 'home')
        if problems:
            for p in problems:
                log(f'REFUSING: {p}')
            return core.EXIT_REFUSED
        if not args.yes:
            if not sys.stdin.isatty():
                log('REFUSING: no terminal to ask "is a person next to the robot?". Run with --yes when detached')
                return core.EXIT_REFUSED
            answer = input('The robot is about to DRIVE a long route. Is a person next to it with the controller '
                           '(button B = emergency stop)? Type yes: ')
            if answer.strip().lower() != 'yes':
                log('not confirmed, not moving')
                return core.EXIT_REFUSED

        logfile, jsonl, path = open_log(args.log_dir)
        log(f'event log: {path} (and {os.path.basename(path)[:-4]}.jsonl)')

        def logger(t, event, detail):
            logfile.write(f'{time.strftime("%H:%M:%S")} run={RUN_ID} {event} {detail}'.rstrip() + '\n')
            jsonl.write(json.dumps({'run': RUN_ID, 'time': time.strftime('%Y-%m-%dT%H:%M:%S'), 'mono': round(t, 3),
                                    'event': event, 'detail': detail}, ensure_ascii=False) + '\n')
            log(f'[{event}] {detail}'.rstrip())

        motion_active = True
        if stop_request:
            return core.EXIT_STOPPED
        log('starting. To stop: controller button B, Ctrl+C, "touch ~/STOP", or "pkill -INT -f delivery_mission.py"')
        robot.motion_started = True
        result = core.DeliveryMission(robot, route, args.allow_undocked, logger, run_id=RUN_ID, trip=args.trip).run()
        log(f'result: {result.outcome} (exit {result.code}) {result.reason}'.rstrip())
        summary = core.format_summary(result)
        logfile.write(summary + '\n')   # exactly one, and the last line of the text log
        jsonl.write(json.dumps({'run': RUN_ID, 'event': 'summary', 'detail': summary}, ensure_ascii=False) + '\n')
        log(summary)
        log(f'longest /odom gap during the run: {robot.longest_odom_gap:.3f} s')
        code = result.code
    except KeyboardInterrupt:
        code = core.EXIT_STOPPED
        log(f'stopped by {stop_request or "Ctrl+C"} before moving')
    finally:
        if not args.dry_run:
            try:
                robot.stop_motion()   # always: zero velocity for STOP_BURST s
            except Exception as e:   # noqa: BLE001
                log(f'warning: final stop failed: {e}')
        if logfile:
            logfile.close()
            jsonl.close()
        robot.close()
    return code


def dry_run(robot, route, args):
    """Everything except moving: topics, preflight, Nav2, first display text. Returns the exit code."""
    node = robot.node
    ok = True
    n_buttons = node.count_publishers('/hmi/buttons')
    log(f'/hmi/buttons publishers: {n_buttons}' + ('' if n_buttons else '  (none: the buttons would not work)'))
    ok = ok and n_buttons > 0
    for p in core.preflight_problems(robot, route, args.allow_undocked or args.trip == 'home'):
        log(f'problem: {p}')
        ok = False
    if robot.stop_requested():
        log(f'warning: stop requested ({robot.stop_requested()})')
    ready = robot.wait_nav_ready(DRY_RUN_NAV_WAIT)
    log('Nav2 and AMCL active and localized: ' +
        ('yes' if ready else 'NO (start the stack: delivery/robot/start_stack.sh nav ..., and give AMCL a pose)'))
    if args.trip == 'home':
        robot.sleep(core.HOME_POSITION_WAIT if robot.position() is None else 0)
        pos = robot.position()
        log('AMCL position: ' + (f'({pos[0]:.2f}, {pos[1]:.2f})' if pos else 'NONE (a real home trip would refuse)'))
        ok = ok and pos is not None
        first = core.display_text(f'Going to the lab\n{core.STOP_HINT}')
    else:
        first = core.display_text(f'Going to food court\n{core.STOP_HINT}')
    robot.show(first)
    log(f'display shows: {first!r}')
    if args.trip == 'home':
        log('the real run would: wait for steady odometry, drive the inbound poses from the pose nearest to the robot, '
            'dock (no button asked)')
    else:
        log('the real run would: set the initial pose, wait for steady odometry, undock, drive to the pickup, '
            f'wait for button 1 or {route.settings.button_placed}, drive home, '
            f'wait for button 1 or {route.settings.button_received}, dock; button 2 stops it while it drives')
    log('dry run: ' + ('all checks passed' if ok else 'PROBLEMS FOUND') + ', nothing was sent to /cmd_vel or to Nav2')
    return core.EXIT_DELIVERED if ok else core.EXIT_REFUSED


if __name__ == '__main__':
    sys.exit(main())
