"""Stub ROS + virtual-clock robot simulator for testing the examples off the robot.

Usage: python sim.py <scenario> [program args...]
Scenarios: shapes (runs more_shapes.main), wall (wall_approach.main), keep (keep_distance.main),
           report (sensor_report.main), snapshot (lidar_snapshot.main), light (lightring_status.main),
           health (health_check.main, with faked system commands and files, see install_health_stubs)
Env: SIM_ODOM_GAP="t0,len" injects an odom pause; SIM_DOCKED=1; SIM_WALL=x (wall distance ahead, m);
     SIM_OBJECT="x0,vx" moving object ahead (keep); SIM_ROOM=r circular room of radius r around the start
     (health defaults to 2.5 m; SIM_ROOM=0 gives no room, so no valid lidar beams);
     SIM_HEALTH="fault,fault" picks a faulty robot for health (empty = healthy). Faults: ap, no_wifi, nmcli_hang,
     service_down, ros_env, lidar_missing, base_silent, clock_skew, battery_low, hot, overheat, bad_thermal,
     throttled, no_vcgencmd, low_disk, no_clock_fix, stop_file, motion_running.
"""
import builtins
import io
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types

EX = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'examples'))
sys.dont_write_bytecode = True
sys.path.insert(0, EX)

# ------------------------------------------------------------ virtual clock
CLOCK = [1000.0]
time.monotonic = lambda: CLOCK[0]
_real_time = time.time
time.time = lambda: 1.7e9 + CLOCK[0]


def _sleep(s):
    advance(s)


time.sleep = _sleep


def NS(**kw):
    return types.SimpleNamespace(**kw)


def stamp_now():
    t = 1.7e9 + CLOCK[0]
    return NS(sec=int(t), nanosec=int((t % 1) * 1e9))


HEALTH = set(filter(None, os.environ.get('SIM_HEALTH', '').split(',')))
BASE_SKEW = -30.0 if 'clock_skew' in HEALTH else 0.0     # base clock behind the Pi (health fault clock_skew)


def base_stamp():
    """Header stamp from the Create 3 base (its own clock)."""
    t = 1.7e9 + CLOCK[0] + BASE_SKEW
    return NS(sec=int(t), nanosec=int((t % 1) * 1e9))


# ------------------------------------------------------------ world
W = {'x': 0.0, 'y': 0.0, 'th': 0.3, 'v': 0.0, 'w': 0.0,
     'next_odom': 0.0, 'next_scan': 0.0, 'next_dock': 0.0, 'next_imu': 0.0, 'next_batt': 0.0,
     'max_v': 0.0, 'max_w': 0.0, 'max_r': 0.0, 'cmds': 0, 'start': None, 'min_wall': 99.0}
WALL = float(os.environ.get('SIM_WALL', '0'))       # wall at distance WALL ahead of the start, perpendicular
OBJ = [float(v) for v in os.environ['SIM_OBJECT'].split(',')] if os.environ.get('SIM_OBJECT') else None
GAP = [float(v) for v in os.environ['SIM_ODOM_GAP'].split(',')] if os.environ.get('SIM_ODOM_GAP') else None
DOCKED = os.environ.get('SIM_DOCKED') == '1'
ROOM = float(os.environ.get('SIM_ROOM', '0'))       # circular room of this radius around the start point
BASE_SILENT = 'base_silent' in HEALTH                # no /odom, /dock_status, /battery_state, /imu
NO_SCAN = 'lidar_missing' in HEALTH
NODES = []
T0 = CLOCK[0]


def obstacle_distance_along(angle):
    """Ray from the robot at world angle: distance to the wall line / object, or inf."""
    best = float('inf')
    x0, y0, th0 = 0.0, 0.0, 0.3   # start pose
    fx, fy = math.cos(th0), math.sin(th0)
    targets = []
    if WALL:
        targets.append(WALL)
    if OBJ:
        targets.append(OBJ[0] + OBJ[1] * (CLOCK[0] - T0))
    dx, dy = math.cos(angle), math.sin(angle)
    for d in targets:
        # plane: (p - start) . f = d
        denom = dx * fx + dy * fy
        if denom <= 1e-6:
            continue
        s = (d - ((W['x'] - x0) * fx + (W['y'] - y0) * fy)) / denom
        if s > 0:
            # object is only 0.5 m wide if OBJ; wall is wide
            px, py = W['x'] + s * dx, W['y'] + s * dy
            lat = -(px - x0) * fy + (py - y0) * fx
            if OBJ and d != WALL and abs(lat) > 0.25:
                continue
            best = min(best, s)
    if ROOM:
        px, py = W['x'] - x0, W['y'] - y0
        b = px * dx + py * dy
        disc = b * b - (px * px + py * py - ROOM * ROOM)
        if disc >= 0 and -b + math.sqrt(disc) > 0:
            best = min(best, -b + math.sqrt(disc))
    return best


def integrate(dt):
    W['th'] += W['w'] * dt
    W['x'] += W['v'] * math.cos(W['th']) * dt
    W['y'] += W['v'] * math.sin(W['th']) * dt
    W['max_r'] = max(W['max_r'], math.hypot(W['x'], W['y']))
    if WALL:
        fx, fy = math.cos(0.3), math.sin(0.3)
        W['min_wall'] = min(W['min_wall'], WALL - (W['x'] * fx + W['y'] * fy))


def deliver(node):
    t = CLOCK[0]
    subs = node._subs
    if t >= W['next_odom']:
        W['next_odom'] = t + 0.05
        in_gap = GAP and GAP[0] <= t - T0 < GAP[0] + GAP[1]
        if '/odom' in subs and not in_gap and not BASE_SILENT:
            q = NS(x=0.0, y=0.0, z=math.sin(W['th'] / 2), w=math.cos(W['th'] / 2))
            msg = NS(header=NS(stamp=base_stamp(), frame_id='odom'),
                     pose=NS(pose=NS(position=NS(x=W['x'], y=W['y'], z=0.0), orientation=q)))
            subs['/odom'](msg)
    if t >= W['next_scan']:
        W['next_scan'] = t + 0.13
        if '/scan' in subs and not DOCKED and not NO_SCAN:
            n, amin, inc = 720, -3.124, 0.0087
            ranges = []
            for i in range(n):
                a = amin + i * inc + math.pi / 2          # robot frame
                r = obstacle_distance_along(W['th'] + a)
                ranges.append(r if 0.15 < r < 12.0 else float('inf'))
            for i in range(0, n, 4):                       # ~25 % invalid beams
                ranges[i] = float('inf')
            msg = NS(header=NS(stamp=stamp_now(), frame_id='rplidar_link'), ranges=ranges, angle_min=amin,
                     angle_increment=inc, range_min=0.15, range_max=12.0)
            subs['/scan'](msg)
    if t >= W['next_dock']:
        W['next_dock'] = t + 1.0
        if '/dock_status' in subs and not BASE_SILENT:
            subs['/dock_status'](NS(header=NS(stamp=base_stamp()), is_docked=DOCKED, dock_visible=True))
        if '/battery_state' in subs and not BASE_SILENT:
            subs['/battery_state'](NS(header=NS(stamp=base_stamp()),
                                      percentage=0.22 if 'battery_low' in HEALTH else 0.42))
    if t >= W['next_imu']:
        W['next_imu'] = t + 0.01
        if '/imu' in subs and not BASE_SILENT:
            subs['/imu'](NS(header=NS(stamp=base_stamp())))


def advance(dt):
    end = CLOCK[0] + max(1e-4, dt)
    while CLOCK[0] < end - 1e-12:
        step = min(0.005, end - CLOCK[0])
        integrate(step)
        CLOCK[0] += step
        for nd in NODES:
            deliver(nd)
        ev = os.environ.get('SIM_EVENT')   # "stopfile,t" or "sigint,t" or "sigterm,t" or "bump,t"
        if ev and 'motion_shapes' in sys.modules:
            kind, at = ev.split(',')
            if CLOCK[0] - T0 >= float(at) and not W.get('fired'):
                W['fired'] = True
                msm = sys.modules['motion_shapes']
                if kind == 'stopfile':
                    open(msm.STOP_FILE, 'w').close()
                elif kind in ('sigint', 'sigterm'):
                    import signal as S
                    S.raise_signal(S.SIGINT if kind == 'sigint' else S.SIGTERM)
                elif kind == 'bump':
                    for nd in NODES:
                        nd._subs['/hazard_detection'](NS(detections=[NS(type=1, header=NS(frame_id='bump_front_left'))]))


# ------------------------------------------------------------ stub modules
def module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


class Pub:
    def __init__(self, topic):
        self.topic = topic

    def publish(self, msg):
        if self.topic == '/cmd_vel':
            v, w = msg.twist.linear.x, msg.twist.angular.z
            assert abs(v) <= 0.15 + 1e-9 and abs(w) <= 1.0 + 1e-9, (v, w)
            W['v'], W['w'] = v, w
            W['max_v'] = max(W['max_v'], abs(v))
            W['max_w'] = max(W['max_w'], abs(w))
            W['cmds'] += 1
        elif self.topic == '/cmd_lightring':
            W.setdefault('lightring', []).append((msg.override_system, [(l.red, l.green, l.blue) for l in msg.leds]))

    def get_subscription_count(self):
        return 1


class Node:
    def __init__(self, name):
        self._subs = {}
        NODES.append(self)

    def create_publisher(self, mtype, topic, qos):
        return Pub(topic)

    def create_subscription(self, mtype, topic, cb, qos):
        self._subs[topic] = cb

    def get_clock(self):
        return NS(now=lambda: NS(to_msg=stamp_now))

    def count_publishers(self, topic):
        return 0 if topic == '/scan' and NO_SCAN else 1

    def destroy_node(self):
        NODES.remove(self)


def spin_once(node, timeout_sec=None):
    t = 0.05 if timeout_sec is None else timeout_sec
    advance(max(1e-4, min(t, 0.05)))


class TransformException(Exception):
    pass


class Buffer:
    def lookup_transform(self, a, b, t):
        return NS(transform=NS(rotation=NS(x=0.0, y=0.0, z=math.sin(math.pi / 4), w=math.cos(math.pi / 4))))


class Msg:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TwistStamped:
    def __init__(self):
        self.header = NS(stamp=None, frame_id='')
        self.twist = NS(linear=NS(x=0.0, y=0.0, z=0.0), angular=NS(x=0.0, y=0.0, z=0.0))


class LightringLeds:
    def __init__(self):
        self.header = NS(stamp=None)
        self.override_system = False
        self.leds = []


class HazardDetection:
    BACKUP_LIMIT, BUMP, CLIFF, STALL, WHEEL_DROP, OBJECT_PROXIMITY = 0, 1, 2, 3, 4, 5


rclpy = module('rclpy', init=lambda **kw: None, spin_once=spin_once, try_shutdown=lambda: None)
module('rclpy.node', Node=Node)
module('rclpy.qos', qos_profile_sensor_data=None)
module('rclpy.signals', SignalHandlerOptions=NS(NO=0))
module('rclpy.executors', ExternalShutdownException=type('ESE', (Exception,), {}))
rclpy.time = module('rclpy.time', Time=lambda: None)
module('tf2_ros', Buffer=Buffer, TransformListener=lambda b, n: None, TransformException=TransformException)
module('geometry_msgs'); module('geometry_msgs.msg', TwistStamped=TwistStamped)
module('nav_msgs'); module('nav_msgs.msg', Odometry=Msg)
module('sensor_msgs'); module('sensor_msgs.msg', LaserScan=Msg, BatteryState=Msg, Imu=Msg)
module('std_msgs'); module('std_msgs.msg', String=Msg)
module('irobot_create_msgs'); module('irobot_create_msgs.msg', DockStatus=Msg, HazardDetection=HazardDetection,
                                     HazardDetectionVector=Msg, LedColor=Msg, LightringLeds=LightringLeds)

# ------------------------------------------------------------ health_check: fake system commands and files
# Outputs as seen on the robot (Ubuntu 24.04, Pi 4); SIM_HEALTH faults change them. Nothing is written to disk.
LSUSB = ('Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub\n'
         'Bus 001 Device 003: ID 10c4:ea60 Silicon Labs CP210x UART Bridge\n'
         'Bus 001 Device 002: ID 2109:3431 VIA Labs, Inc. Hub\n'
         'Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\n')
MEMINFO = ('MemTotal:        3881468 kB\nMemFree:          912344 kB\nMemAvailable:    2310452 kB\n'
           'Buffers:           61232 kB\nCached:          1398712 kB\nSwapTotal:             0 kB\n')
FAKE_STOP = '/home/ubuntu/STOP'


def fake_files():
    """path -> content, or None for a missing file."""
    temp = ('84012\n' if 'overheat' in HEALTH else '78500\n' if 'hot' in HEALTH else
            'temperature unknown\n' if 'bad_thermal' in HEALTH else '48312\n')
    fix = 'no_clock_fix' not in HEALTH
    return {
        '/sys/class/thermal/thermal_zone0/temp': temp,
        '/proc/meminfo': MEMINFO,
        '/proc/loadavg': '1.52 1.31 1.20 3/512 12345\n',
        '/proc/uptime': '5123.45 17800.10\n',
        '/dev/RPLIDAR': None if 'lidar_missing' in HEALTH else '',
        '/etc/systemd/system/tb4-https-time.timer': '[Timer]\nOnBootSec=60\nOnUnitActiveSec=15min\n' if fix else None,
        '/etc/systemd/system/turtlebot4.service.d/10-wait-for-clock.conf':
            '[Unit]\nWants=tb4-https-time.service\nAfter=tb4-https-time.service\n' if fix else None,
        FAKE_STOP: '' if 'stop_file' in HEALTH else None,
    }


def fake_processes(pattern):
    """`pgrep -af pattern` on the simulated robot. The shell line contains the pattern text itself, so it only
    stays out of the result if the pattern uses the bracket trick."""
    procs = [(731, '/opt/ros/jazzy/lib/turtlebot4_node/turtlebot4_node --ros-args'),
             (4321, f'sh -c pgrep -af "{pattern}"'),
             (os.getpid(), 'python3 /home/ubuntu/robot_code/health_check.py')]
    if 'motion_running' in HEALTH:
        procs.append((2345, 'python3 /home/ubuntu/robot_code/motion_shapes.py square --yes'))
    hits = [f'{pid} {cmd}' for pid, cmd in procs if re.search(pattern, cmd)]
    return (0, '\n'.join(hits) + '\n', '') if hits else (1, '', '')


def fake_command(cmd):
    """(exit code, stdout, stderr) of a command on the simulated robot; raises like subprocess.run would."""
    prog = os.path.basename(cmd[0])
    if prog == 'nmcli':
        if 'nmcli_hang' in HEALTH:
            raise subprocess.TimeoutExpired(cmd, 4.0)
        if 'no_wifi' in HEALTH:
            return 0, 'lo:lo\n', ''
        return 0, ('netplan-wlan0-Turtlebot4' if 'ap' in HEALTH else 'Students') + ':wlan0\nlo:lo\n', ''
    if prog == 'ip':
        if 'no_wifi' in HEALTH:
            return 0, 'wlan0            DOWN           \n', ''
        addr = '10.42.0.1/24' if 'ap' in HEALTH else '10.87.10.205/18'
        return 0, f'wlan0            UP             {addr} \n', ''
    if prog == 'systemctl':
        return (3, 'inactive\n', '') if 'service_down' in HEALTH else (0, 'active\n', '')
    if prog == 'lsusb':
        missing = 'lidar_missing' in HEALTH
        return 0, ''.join(line for line in LSUSB.splitlines(True) if not (missing and 'CP210x' in line)), ''
    if prog == 'vcgencmd':
        if 'no_vcgencmd' in HEALTH:
            raise FileNotFoundError(2, 'No such file or directory', 'vcgencmd')
        return 0, 'throttled=0x50005\n' if 'throttled' in HEALTH else 'throttled=0x0\n', ''
    if prog == 'pgrep':
        return fake_processes(cmd[-1])
    raise FileNotFoundError(2, 'No such file or directory', cmd[0])


def install_health_stubs(hc):
    """Replace subprocess, the file reads and the disk / host queries for health_check (this process only)."""
    files = fake_files()
    real_open, real_exists, real_realpath = builtins.open, os.path.exists, os.path.realpath

    def fake_run(cmd, *a, **kw):
        rc, out, err = fake_command(list(cmd))
        if kw.get('check') and rc:
            raise subprocess.CalledProcessError(rc, cmd, out, err)
        return subprocess.CompletedProcess(cmd, rc, out, err)

    def fake_check_output(cmd, *a, **kw):
        rc, out, err = fake_command(list(cmd))
        if rc:
            raise subprocess.CalledProcessError(rc, cmd, out, err)
        return out

    def fake_open(path, *a, **kw):
        if isinstance(path, str) and path in files:
            if files[path] is None:
                raise FileNotFoundError(2, 'No such file or directory', path)
            return io.StringIO(files[path])
        return real_open(path, *a, **kw)

    subprocess.run, subprocess.check_output = fake_run, fake_check_output
    builtins.open = fake_open
    os.path.exists = lambda p: files[p] is not None if isinstance(p, str) and p in files else real_exists(p)
    os.path.realpath = lambda p, *a, **kw: '/dev/ttyUSB0' if p == '/dev/RPLIDAR' else real_realpath(p, *a, **kw)
    free = 1.5e9 if 'low_disk' in HEALTH else 37.2e9
    shutil.disk_usage = lambda p: NS(total=58.9e9, used=58.9e9 - free, free=free)
    os.cpu_count = lambda: 4
    socket.gethostname = lambda: 'turtlebot4'
    os.environ.update(ROS_DISTRO='jazzy', ROS_DOMAIN_ID='7' if 'ros_env' in HEALTH else '0',
                      RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
    hc.STOP_FILE = FAKE_STOP


# ------------------------------------------------------------ run
if __name__ == '__main__':
    scen = sys.argv[1]
    prog = {'shapes': 'more_shapes', 'wall': 'wall_approach', 'keep': 'keep_distance', 'report': 'sensor_report',
            'snapshot': 'lidar_snapshot', 'light': 'lightring_status', 'motion': 'motion_shapes',
            'health': 'health_check'}[scen]
    sys.argv = [prog + '.py'] + sys.argv[2:]
    import motion_shapes as _ms
    _ms.STOP_FILE = os.path.join(tempfile.gettempdir(), 'turtlebot_sim_STOP')
    if os.path.exists(_ms.STOP_FILE):
        os.remove(_ms.STOP_FILE)
    mod = __import__(prog)
    if scen == 'health':
        if 'SIM_ROOM' not in os.environ:
            ROOM = 2.5          # a room around the robot, so about 75 % of the beams are valid (72 % in the lab)
        install_health_stubs(mod)
    code = mod.main()
    fx, fy = math.cos(0.3), math.sin(0.3)
    fwd = W['x'] * fx + W['y'] * fy
    side = -W['x'] * fy + W['y'] * fx
    print(f'SIM exit={code} t={CLOCK[0] - T0:.1f}s true_end fwd={fwd:+.3f} side={side:+.3f} '
          f'dth={math.degrees(W["th"] - 0.3):+.1f}deg max_r={W["max_r"]:.3f} max_v={W["max_v"]:.3f} '
          f'max_w={W["max_w"]:.3f} cmds={W["cmds"]} final_cmd=({W["v"]},{W["w"]})'
          + (f' min_wall_gap={W["min_wall"]:.3f}' if WALL else ''))
    if 'lightring' in W:
        print('SIM lightring first', W['lightring'][0], 'last', W['lightring'][-1], 'n', len(W['lightring']))
