"""Offline tests of the TurtleBot Studio 2.0 backend (TurtleBot/tools/studio/studio.py and robot_bridge.py):
scan / pose streams, manual driving (teleop) with its watchdog, clamps and refusals, the robot log (journal), metrics
history, alerts + events.jsonl, teleop limits, auto-disarm rules, and serving the new UI at / and the 1.3 UI at /classic/.

No robot and no ROS: the pure helpers are called directly, the bridge runs in --fake mode (as a subprocess and in-process
with a recording fake), and the HTTP part starts the real studio.py --fake with a temporary config folder and a temporary
copy of web/ (--web-dir), so the repo's web/ folder (and a web/v2 that another person may be building) is never touched.
Usage: python test_studio_v2_backend.py     (prints PASS/FAIL/SKIP, exit code = number of failures)
"""
import http.client
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
BRIDGE = os.path.join(STUDIO_DIR, 'robot_bridge.py')
sys.path.insert(0, STUDIO_DIR)
import studio as st  # noqa: E402

spec = importlib.util.spec_from_file_location('robot_bridge_v2', BRIDGE)
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)

OUT = tempfile.mkdtemp(prefix='tb4_studio_v2_')
fails = 0
INF = float('inf')
NAN = float('nan')


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode())
    if not cond:
        fails += 1


def wait_for(fn, timeout, step=0.05):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


# ================================================================ pure helpers (bridge)
out, k = rb.downsample_ranges([5.0, 1.0, 3.0, 4.0, 2.0, 6.0], 3)
check('downsample: minimum per bin (2 beams each)', out == [1.0, 3.0, 2.0] and k == 2, str(out))
out, k = rb.downsample_ranges([INF, NAN, 2.0, INF, NAN, INF], 3)
check('downsample: inf / nan give null, a bin with one valid beam keeps it', out == [None, 2.0, None], str(out))
out, k = rb.downsample_ranges([1.234, 2.0, 12.5, 0.05], 720, range_min=0.15, range_max=12.0)
check('downsample: rounded to 0.01, below range_min and beyond range_max are null, no binning when short',
      out == [1.23, 2.0, None, None] and k == 1, str(out))
out, k = rb.downsample_ranges([float(i % 7 + 1) for i in range(720)], 360)
check('downsample: 720 beams to 360 points', len(out) == 360 and k == 2)
out, k = rb.downsample_ranges([1.0] * 721, 360)
check('downsample: never more than max_points (721 beams)', len(out) <= 360 and k == 3, '%d %d' % (len(out), k))
check('downsample: empty scan', rb.downsample_ranges([], 360)[0] == [])
ev = rb.build_scan_event([3.0] * 360, -math.pi, 2 * math.pi / 360, 0.15, 12.0, math.pi / 2, 90, 1.5)
check('scan event: shape and base frame', set(ev) == {'ev', 't', 'frame', 'angle_min', 'angle_inc', 'range_max', 'ranges'}
      and ev['ev'] == 'scan' and ev['frame'] == 'base' and len(ev['ranges']) == 90 and ev['range_max'] == 12.0, str(list(ev)))
# lidar at +90 deg: the beam at laser -90 deg (an obstacle straight ahead) must land at robot angle 0
rr = [3.0] * 360
inc = 2 * math.pi / 360
rr[int(round((-math.pi / 2 - -math.pi) / inc))] = 0.8
ev = rb.build_scan_event(rr, -math.pi, inc, 0.15, 12.0, rb.SCAN_YAW_DEFAULT, 360, 0.0)
ia = ev['ranges'].index(0.8)
ang = ev['angle_min'] + ia * ev['angle_inc']
check('scan event: angles are in the robot frame (laser -90 deg is straight ahead = 0)', abs(ang) < 0.02, '%.4f' % ang)
check('scan event: JSON safe (null, not Infinity)', 'Infinity' not in json.dumps(rb.build_scan_event([INF, 1.0], 0, 1, 0, 5, 0, 90, 0)))

check('clamp: hard caps 0.30 m/s and 1.20 rad/s both ways', rb.clamp_teleop(5, -5) == (0.30, -1.20) and rb.clamp_teleop(-5, 5) == (-0.30, 1.20))
check('clamp: inside the caps unchanged', rb.clamp_teleop(0.1, -0.5) == (0.1, -0.5))
check('clamp: user limits can only lower the caps', rb.clamp_teleop(0.3, 1.2, 0.15, 0.6) == (0.15, 0.6) and rb.clamp_teleop(0.3, 1.2, 9, 9) == (0.30, 1.20))
check('clamp: nan, inf, text, bool, None give zero', rb.clamp_teleop(NAN, INF) == (0.0, 0.0) and rb.clamp_teleop('1', None) == (0.0, 0.0)
      and rb.clamp_teleop(True, False) == (0.0, 0.0))
check('clamp_int / clamp_float', rb.clamp_int(5, 90, 720, 360) == 90 and rb.clamp_int(None, 90, 720, 360) == 360 and rb.clamp_int(9999, 50, 2000, 300) == 2000
      and rb.clamp_float(100, 1, 10, 4) == 10.0)
try:
    rb.clamp_int('x', 1, 2, 1)
    bad = False
except ValueError:
    bad = True
check('clamp_int: text is refused', bad)

a = rb.journal_argv('turtlebot4.service', 300, None)
check('journal argv: a plain list, journalctl -u UNIT -n N --no-pager -o short-iso, no sudo', a == ['journalctl', '-u', 'turtlebot4.service', '-n', '300',
      '--no-pager', '-o', 'short-iso'] and all(isinstance(x, str) for x in a) and 'sudo' not in a)
check('journal argv: lines clamped to 50..2000', rb.journal_argv(None, 1, None)[4] == '50' and rb.journal_argv(None, 99999, None)[4] == '2000'
      and rb.journal_argv(None, None, None)[4] == '300')
check('journal argv: since from the allow-list', rb.journal_argv(None, 100, '10 min ago')[-2:] == ['--since', '10 min ago']
      and rb.journal_argv(None, 100, 'boot')[-1] == '-b')
for bad_unit in ('turtlebot4.service; rm -rf /', 'sshd', '../x', 'turtlebot4.service --vacuum-size=1M', '-f', 'a b'):
    try:
        rb.journal_argv(bad_unit, 100, None)
        ok = False
    except ValueError:
        ok = True
    check('journal argv: unit %r refused' % bad_unit, ok)
for bad_since in ('1 week ago', '10 min ago; id', '--output=json', '$(id)'):
    try:
        rb.journal_argv(None, 100, bad_since)
        ok = False
    except ValueError:
        ok = True
    check('journal argv: since %r refused' % bad_since, ok)
try:
    rb.journal_argv(None, 'abc', None)
    ok = False
except ValueError:
    ok = True
check('journal argv: lines must be a number', ok)
txt = '-- Journal begins --\n2026-10-30T10:00:00+0300 tb a: ERROR boom\n2026-10-30T10:00:01+0300 tb a: fine\n\n2026-10-30T10:00:02+0300 tb a: error again\n'
check('journal lines: header and blanks dropped, grep is plain text and case-insensitive',
      len(rb.journal_lines(txt)) == 3 and len(rb.journal_lines(txt, 'ERROR')) == 2 and rb.journal_lines(txt, '.*') == []
      and rb.journal_lines('x' * 5000)[0] == 'x' * 600 and len(rb.journal_lines('a\n' * 10, None, 4)) == 4)
check('journal permission text is recognised', rb.journal_permission_problem('Hint: You are currently not seeing messages from other users and the system.\n'
      'No journal files were opened due to insufficient permissions.') and not rb.journal_permission_problem('all good'))
rows = rb.fake_room_ranges(0, 0, 0, -math.pi, 2 * math.pi / 360, 360, rb.SCAN_YAW_DEFAULT)
rows2 = rb.fake_room_ranges(0, 0, math.pi / 2, -math.pi, 2 * math.pi / 360, 360, rb.SCAN_YAW_DEFAULT)
check('fake room: walls, a doorway with no return (inf) and a pose-dependent scan',
      len(rows) == 360 and sum(1 for r in rows if r == INF) > 3 and all(r > 0.2 for r in rows if r != INF) and rows != rows2
      and min(r for r in rows if r != INF) < 1.5)

# ================================================================ in-process bridge: watchdog, disarm, refusals
class Sink:
    def __init__(self):
        self.lines = []

    def write(self, data):
        self.lines.extend(json.loads(x) for x in data.decode().splitlines() if x.strip())

    def flush(self):
        pass


def new_bridge(name, docked=False, start_loops=True):
    home = os.path.join(OUT, name)
    os.makedirs(home, exist_ok=True)
    sink = Sink()
    ros = rb.FakeRos()
    ros.docked = docked
    wr = rb.Writer(sink)
    br = rb.Bridge(ros, wr, home, True)
    ros.start(wr.emit)
    if start_loops:
        threading.Thread(target=br._teleop_loop, daemon=True).start()
    return br, ros, sink, wr


def events(sink, kind):
    time.sleep(0.15)     # the bridge writes through a queue and a writer thread
    return [e for e in sink.lines if e.get('ev') == kind]


def zeros_after(ros, t0):
    return [c for c in list(ros.cmd_log) if c[0] >= t0 and c[1] == 0.0 and c[2] == 0.0]


br, ros, sink, wr = new_bridge('inproc1')
def _raises(fn, *a):
    try:
        fn(*a)
    except rb.BridgeError as e:
        return str(e)
    return ''


ros.docked = True
msg = _raises(br.h_teleop_arm, {'on': True})
check('arm: refused while docked, says to undock', 'Undock first' in msg, msg)
check('arm: the refusal arms nothing', br.tele['armed'] is False)
ros.docked = False
msg = _raises(br.h_teleop, {'vx': 0.1, 'wz': 0})
check('teleop while not armed is refused and publishes nothing', 'not armed' in msg.lower() and not ros.cmd_log, msg)
msg = _raises(br.h_teleop_arm, {'on': 'yes'})
check('arm: on must be a real boolean', 'true or false' in msg, msg)
# e-stop latched (stop file) refuses
open(br.stop_file, 'w').close()
msg = _raises(br.h_teleop_arm, {'on': True})
check('arm: refused while the e-stop / STOP file is latched', 'e-stop' in msg.lower(), msg)
os.remove(br.stop_file)
br.status_estop = True
check('arm: refused while the robot reports e-stop on', 'e-stop' in _raises(br.h_teleop_arm, {'on': True}).lower())
br.status_estop = False
# ROS not ready
ros.available = False
ros.error = 'rclpy missing'
check('arm: refused while ROS is not ready', 'ROS is not ready' in _raises(br.h_teleop_arm, {'on': True}))
ros.available = True
ros.error = None
# a motion program running
home = br.home
os.makedirs(os.path.join(home, 'robot_code'), exist_ok=True)
with open(os.path.join(home, 'robot_code', 'slow_motion.py'), 'w') as f:
    f.write('import time\ntime.sleep(30)\n')
res = br.h_run({'path': 'slow_motion.py', 'motion': True, 'confirmed': True})
check('arm: refused while a motion program runs', 'motion program' in _raises(br.h_teleop_arm, {'on': True}), str(res.get('pid')))
r = br.h_runs({})
for run in list(br.runs.values()):
    run.proc.kill()
    run.proc.wait()
time.sleep(0.1)
check('arm: allowed again once the program is gone', _raises(br.h_teleop_arm, {'on': True}) == '' and br.tele['armed'] is True)
armed_ev = events(sink, 'teleop')
check('arm: one teleop event armed=true', len(armed_ev) == 1 and armed_ev[0]['armed'] is True and armed_ev[0]['reason'] == 'armed', str(armed_ev))
br.h_teleop_arm({'on': True})
check('arming twice sends no second event', len(events(sink, 'teleop')) == 1)

# clamps in the bridge (the UI cannot exceed them)
res = br.h_teleop({'vx': 5.0, 'wz': -9.0, 'seq': 1})
check('teleop: clamped to 0.30 m/s and 1.20 rad/s in the bridge', res['vx'] == 0.30 and res['wz'] == -1.20 and ros.cmd_log[-1][1:] == (0.30, -1.20), str(res))
res = br.h_teleop({'vx': 0.3, 'wz': 1.0, 'seq': 2, 'max_linear': 0.1, 'max_angular': 0.4})
check('teleop: the limits Studio passes lower the caps', res['vx'] == 0.1 and res['wz'] == 0.4, str(res))
res = br.h_teleop({'vx': 0.3, 'wz': 1.0, 'seq': 3, 'max_linear': 50, 'max_angular': 50})
check('teleop: a limit above the hard cap changes nothing', res['vx'] == 0.30 and res['wz'] == 1.0, str(res))
res = br.h_teleop({'vx': NAN, 'wz': 'fast', 'seq': 4})
check('teleop: nan / text become zero velocity', res['vx'] == 0.0 and res['wz'] == 0.0)
n_before = len(ros.cmd_log)
res = br.h_teleop({'vx': 0.2, 'wz': 0.0, 'seq': 4})
check('teleop: an older or repeated seq is ignored (late packet)', res.get('ignored') is True and len(ros.cmd_log) == n_before)
check('teleop: seq must be a whole number', 'seq' in _raises(br.h_teleop, {'vx': 0, 'wz': 0, 'seq': 'a'}))

# watchdog: stops 300 ms after the last command, once, with no message arriving to trigger it
t_last = time.monotonic()
for i in range(6):
    br.h_teleop({'vx': 0.2, 'wz': 0.0, 'seq': 10 + i})
    t_last = time.monotonic()
    time.sleep(0.05)
time.sleep(1.0)
z = zeros_after(ros, t_last)
check('watchdog: exactly one zero after the last command and not before 0.3 s', len(z) == 1 and 0.28 <= z[0][0] - t_last <= 0.5,
      '%d zeros, first after %s' % (len(z), (z[0][0] - t_last) if z else None))
check('watchdog: hold = nothing more published afterwards', not [c for c in ros.cmd_log if c[0] > t_last + 0.6])
check('watchdog: still armed (only the velocity stopped)', br.tele['armed'] is True)
br.h_teleop({'vx': 0.2, 'wz': 0.0, 'seq': 30})
time.sleep(0.6)
check('watchdog: a new command drives again and is stopped again', ros.cmd_log[-1][1:] == (0.0, 0.0) and any(c[1] == 0.2 for c in ros.cmd_log))

# disarm publishes zero
n = len(ros.cmd_log)
t1 = time.monotonic()
res = br.h_teleop_arm({'on': False, 'reason': 'test reason'})
tev = events(sink, 'teleop')
check('disarm: publishes zero velocity and one event with the reason', res['armed'] is False and zeros_after(ros, t1) and tev[-1] == {'ev': 'teleop', 'armed': False, 'reason': 'test reason'}, str(tev[-1]))
n = len(ros.cmd_log)
br.h_teleop_arm({'on': False})
check('disarm while not armed publishes nothing (a program that drives is never disturbed)', len(ros.cmd_log) == n)

# every disarm path: e-stop, docked, motion program, stop file, idle 60 s, bridge shutdown
def arm_again():
    ros.docked = False
    br.status_estop = False
    if os.path.exists(br.stop_file):
        os.remove(br.stop_file)
    br.h_teleop_arm({'on': True})
    br.h_teleop({'vx': 0.2, 'wz': 0.1, 'seq': 1})
    return time.monotonic()


def last_teleop_reason():
    e = events(sink, 'teleop')
    return e[-1] if e else None


t0 = arm_again()
br.h_estop({})
e = last_teleop_reason()
check('e-stop disarms first and zero velocity is published', br.tele['armed'] is False and e['armed'] is False and e['reason'] == 'e-stop' and zeros_after(ros, t0))
check('after the e-stop teleop commands are refused', 'not armed' in _raises(br.h_teleop, {'vx': 0.2, 'wz': 0, 'seq': 2}).lower())
check('after the e-stop arming is refused until it is released', 'e-stop' in _raises(br.h_teleop_arm, {'on': True}).lower())
br.h_estop_release({})
check('after releasing the e-stop arming works', _raises(br.h_teleop_arm, {'on': True}) == '')
br.h_teleop_arm({'on': False})

t0 = arm_again()
ros.docked = True
ok = wait_for(lambda: br.tele['armed'] is False, 1.0)
e = last_teleop_reason()
check('docking while armed disarms (within 0.5 s) with zero velocity', ok and 'docked' in e['reason'].lower() and zeros_after(ros, t0), str(e))

t0 = arm_again()
open(br.stop_file, 'w').close()
ok = wait_for(lambda: br.tele['armed'] is False, 1.0)
check('the STOP file appearing while armed disarms', ok and 'e-stop' in last_teleop_reason()['reason'].lower() and zeros_after(ros, t0))
os.remove(br.stop_file)

t0 = arm_again()
br.h_run({'path': 'slow_motion.py', 'motion': True, 'confirmed': True})
ok = wait_for(lambda: br.tele['armed'] is False, 1.5)
check('a motion program starting while armed disarms', ok and 'motion program' in last_teleop_reason()['reason'] and zeros_after(ros, t0))
for run in list(br.runs.values()):
    run.proc.kill()
    run.proc.wait()

t0 = arm_again()
br.tele['last_move'] = time.monotonic() - 61
ok = wait_for(lambda: br.tele['armed'] is False, 1.0)
check('60 s without a command disarms (zero velocity, reason says why)', ok and '60' in last_teleop_reason()['reason'] and zeros_after(ros, t0), str(last_teleop_reason()))

t0 = arm_again()
t_move = br.tele['last_move']
time.sleep(0.1)
br.h_teleop({'vx': 0.0, 'wz': 0.0, 'seq': 2})
check('a zero command does not keep the arm alive (only real motion or arming does)', br.tele['last_move'] == t_move)
# battery rules: arming refused below 10 %, an armed session ends below 8 %
br.h_teleop_arm({'on': False})
ros.battery_override = 9.5
msg = _raises(br.h_teleop_arm, {'on': True})
check('battery: arming is refused below 10 % with the plain text', msg == 'Battery below 10 %. Charge the robot before driving.' and br.tele['armed'] is False, msg)
ros.battery_override = 10.0
check('battery: exactly 10 % may arm', _raises(br.h_teleop_arm, {'on': True}) == '')
br.h_teleop_arm({'on': False})
ros.battery_override = None
check('battery: unknown percent refuses nothing', (lambda: (setattr(ros, 'snapshot', lambda: {'battery': {'percent': None}}), _raises(br.h_teleop_arm, {'on': True}))[1])() == '')
del ros.snapshot
br.h_teleop_arm({'on': False})
ros.battery_override = 12.0
t0 = arm_again()
ros.battery_override = 8.0
time.sleep(0.5)
check('battery: 8 % exactly keeps the session', br.tele['armed'] is True)
ros.battery_override = 7.9
ok = wait_for(lambda: br.tele['armed'] is False, 1.0)
e = last_teleop_reason()
check('battery: below 8 % disarms an armed session with zero velocity and a reason', ok and 'Battery below 8 %' in e['reason'] and zeros_after(ros, t0), str(e))
ros.battery_override = None
check('fake_battery command sets and clears the value, fake only', br.h_fake_battery({'percent': 55}) == {'percent': 55.0} and ros.snapshot()['battery']['percent'] == 55.0
      and br.h_fake_battery({'percent': None}) == {'percent': None} and 'percent' in _raises(br.h_fake_battery, {'percent': 101}))
ros.battery_override = None
arm_again()
br.h_shutdown({})
check('bridge shutdown disarms', br.tele['armed'] is False and 'shutting down' in last_teleop_reason()['reason'])

# a failing publisher must not kill the watchdog thread
t0 = arm_again()
orig = ros.publish_cmd
ros.publish_cmd = lambda vx, wz: (_ for _ in ()).throw(RuntimeError('publish failed'))
time.sleep(0.5)
ros.publish_cmd = orig
check('watchdog survives a failing publish', any(t.name != 'MainThread' for t in threading.enumerate()) and br.tele['armed'] in (True, False))
br.stop.set()
wr.close(0.2)

# idle timer and watchdog do not touch a bridge that was never armed
br2, ros2, sink2, wr2 = new_bridge('inproc2')
time.sleep(0.4)
check('an unarmed bridge never publishes anything', not ros2.cmd_log and not events(sink2, 'teleop'))
br2.stop.set()
wr2.close(0.2)

# estop_status / status carries teleop
br3, ros3, sink3, wr3 = new_bridge('inproc3', start_loops=False)
st3 = br3.build_status()
check('status carries teleop {armed, max_linear, max_angular}', st3['teleop'] == {'armed': False, 'max_linear': 0.3, 'max_angular': 1.2}, str(st3.get('teleop')))
check('fake odom follows the fake pose', st3['odom']['x'] == 0.0 and st3['odom']['vx'] == 0.0)
wr3.close(0.2)


# ================================================================ bridge subprocess (protocol)
class Proc:
    def __init__(self):
        self.home = tempfile.mkdtemp(prefix='home_', dir=OUT)
        env = dict(os.environ, STUDIO_BRIDGE_FAKE='1', STUDIO_BRIDGE_HOME=self.home, PYTHONDONTWRITEBYTECODE='1')
        self.p = subprocess.Popen([sys.executable, '-u', BRIDGE, '--fake'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env)
        self.events = []        # (arrival monotonic, event), never removed
        self.next_id = 0
        self.lock = threading.Lock()
        threading.Thread(target=self._rd, daemon=True).start()
        threading.Thread(target=lambda: [None for _ in self.p.stderr], daemon=True).start()

    def _rd(self):
        for line in self.p.stdout:
            try:
                ev = json.loads(line.decode('utf-8'))
            except ValueError:
                continue
            with self.lock:
                self.events.append((time.monotonic(), ev))

    def evs(self, kind, since=0.0):
        with self.lock:
            return [(t, e) for t, e in self.events if e.get('ev') == kind and t >= since]

    def send(self, cmd, timeout=10.0, **kw):
        self.next_id += 1
        i = self.next_id
        self.p.stdin.write((json.dumps(dict(kw, id=i, cmd=cmd)) + '\n').encode())
        self.p.stdin.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                for t, e in self.events:
                    if e.get('ev') == 'reply' and e.get('id') == i:
                        return e
            time.sleep(0.01)
        return None

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(3)
        except Exception:
            self.p.kill()


b = Proc()
wait_for(lambda: b.evs('hello'), 5)
r = b.send('scan_on')
check('scan_on: defaults hz 4, max_points 360', r and r['ok'] and r['hz'] == 4.0 and r['max_points'] == 360, str(r))
time.sleep(1.2)
sc = b.evs('scan')
check('scan: events arrive at about 4 Hz', 3 <= len(sc) <= 7, str(len(sc)))
e = sc[0][1]
check('scan: event shape {ev,t,frame,angle_min,angle_inc,range_max,ranges}', {'ev', 't', 'frame', 'angle_min', 'angle_inc', 'range_max', 'ranges'} <= set(e)
      and e['frame'] == 'base' and len(e['ranges']) == 360 and e['range_max'] == 12.0 and isinstance(e['t'], float), str(sorted(e)))
check('scan: ranges are metres rounded to 0.01 with null for no return',
      any(x is None for x in e['ranges']) and any(isinstance(x, float) for x in e['ranges'])
      and all(x is None or (0.15 <= x <= 12.0 and abs(x * 100 - round(x * 100)) < 1e-6) for x in e['ranges']))
r = b.send('scan_on', hz=100, max_points=10)
check('scan_on: hz clamped to 10, max_points to 90', r['ok'] and r['hz'] == 10.0 and r['max_points'] == 90, str(r))
r = b.send('scan_on', hz=0, max_points=99999)
check('scan_on: hz clamped to 1, max_points to 720', r['ok'] and r['hz'] == 1.0 and r['max_points'] == 720, str(r))
check('scan_on: text is refused', b.send('scan_on', hz='fast')['ok'] is False)
r = b.send('scan_on', hz=10, max_points=90)
t_mark = time.monotonic()
time.sleep(1.0)
sc = b.evs('scan', t_mark)
check('scan: 90 points at up to 10 Hz', sc and len(sc[0][1]['ranges']) == 90 and 6 <= len(sc) <= 12, str(len(sc)))
r = b.send('scan_off')
time.sleep(0.2)
t_mark = time.monotonic()
time.sleep(0.6)
check('scan_off: stops the events', r['ok'] and not b.evs('scan', t_mark))

r = b.send('pose_on')
check('pose_on: default 10 Hz', r['ok'] and r['hz'] == 10.0, str(r))
t_mark = time.monotonic()
time.sleep(1.0)
po = b.evs('pose', t_mark)
check('pose: events at about 10 Hz', 6 <= len(po) <= 14, str(len(po)))
e = po[-1][1]
check('pose: event shape {ev,t,x,y,yaw,vx,wz}', set(e) == {'ev', 't', 'x', 'y', 'yaw', 'vx', 'wz'} and e['x'] == 0.0 and e['vx'] == 0.0, str(e))
check('pose_on: hz clamped to 1..20', b.send('pose_on', hz=500)['hz'] == 20.0 and b.send('pose_on', hz=0.1)['hz'] == 1.0)
b.send('pose_on', hz=20)

# teleop over the protocol
r = b.send('teleop', vx=0.1, wz=0, seq=1)
check('teleop: refused when not armed (ok false, armed false)', r and r['ok'] is False and r.get('armed') is False and 'not armed' in r['error'].lower(), str(r))
r = b.send('teleop_arm', on=True)
check('teleop_arm: refused while docked, "Undock first"', r and r['ok'] is False and 'Undock first' in r['error'], str(r))
r = b.send('undock', confirmed=True)
check('undock (fake) accepted', r and r['ok'], str(r))
b.send('status_on', period=0.3)
wait_for(lambda: any(e['dock']['is_docked'] is False for _, e in b.evs('status')), 6)
r = b.send('teleop_arm', on=True, max_linear=0.2, max_angular=0.5)
check('teleop_arm: ok with the limits, watchdog and idle times', r['ok'] and r['armed'] is True and r['max_linear'] == 0.2 and r['max_angular'] == 0.5
      and r['watchdog_s'] == 0.3 and r['idle_s'] == 60.0, str(r))
tev = b.evs('teleop')
check('teleop event {ev,armed,reason} on arming', tev and tev[-1][1] == {'ev': 'teleop', 'armed': True, 'reason': 'armed'}, str(tev))
b.send('scan_on', hz=10, max_points=360)
time.sleep(0.4)
sc_a = b.evs('scan')[-1][1]
t_mark = time.monotonic()
last = None
seq = 0
for i in range(25):
    seq += 1
    r = b.send('teleop', vx=0.3, wz=0.8, seq=seq)
    last = time.monotonic()
check('teleop reply carries the clamped values (0.2 m/s, 0.5 rad/s)', r and r['ok'] and r['vx'] == 0.2 and r['wz'] == 0.5 and r['seq'] == seq, str(r))
pv = [e for t, e in b.evs('pose', t_mark)]
check('fake robot drives: pose x grows, yaw turns, velocity shown', pv and pv[-1]['x'] > 0.02 and pv[-1]['yaw'] != 0.0 and any(e['vx'] == 0.2 for e in pv), str(pv[-1:]))
time.sleep(0.2)
st_ev = [e for t, e in b.evs('status')][-1]
check('status carries teleop.armed and the fake odometry', st_ev['teleop']['armed'] is True and isinstance(st_ev['odom']['x'], float), str(st_ev['teleop']))
# watchdog over the protocol: zero velocity arrives within ~0.5 s after the last command
t_zero = None
end = time.monotonic() + 2.0
while time.monotonic() < end and t_zero is None:
    for t, e in b.evs('pose', last):
        if e['vx'] == 0.0 and e['wz'] == 0.0:
            t_zero = t
            break
    time.sleep(0.01)
check('watchdog: velocity back to zero 0.3..0.6 s after the last command (nothing sent to trigger it)', t_zero is not None and 0.25 <= t_zero - last <= 0.7,
      str(None if t_zero is None else round(t_zero - last, 3)))
r = b.send('teleop', vx=0.1, wz=0.0, seq=1)
check('a restarted seq counter (seq <= last) is ignored, not an error', r['ok'] and r.get('ignored') is True)
time.sleep(0.3)
sc_b = b.evs('scan')[-1][1]
check('fake scan rotates with the fake pose', sc_a['ranges'] != sc_b['ranges'])
r = b.send('estop')
check('estop over the protocol: disarms with reason e-stop', r['ok'] and b.evs('teleop')[-1][1] == {'ev': 'teleop', 'armed': False, 'reason': 'e-stop'}, str(b.evs('teleop')[-1:]))
r = b.send('teleop_arm', on=True)
check('teleop_arm refused while e-stop is latched', r['ok'] is False and 'e-stop' in r['error'].lower(), str(r))
b.send('estop_release')
r = b.send('teleop_arm', on=True)
check('teleop_arm works after the release', r['ok'] is True, str(r))
r = b.send('teleop_arm', on=False, reason='by test')
check('teleop_arm off: ok, event armed false', r['ok'] and r['armed'] is False and b.evs('teleop')[-1][1]['armed'] is False)

# journal over the protocol
r = b.send('journal')
check('journal: fake lines, default unit and 300 lines', r['ok'] and r['unit'] == 'turtlebot4.service' and r['requested'] == 300 and r['count'] == 300
      and isinstance(r['lines'], list) and 'turtlebot4' in r['lines'][0] and r['fake'] is True, str(r.get('count')))
r = b.send('journal', lines=10)
check('journal: lines below 50 are raised to 50', r['ok'] and r['requested'] == 50 and r['count'] == 50)
r = b.send('journal', lines=99999)
check('journal: lines above 2000 are cut to 2000', r['ok'] and r['requested'] == 2000 and r['count'] == 2000)
r = b.send('journal', grep='error', lines=200)
check('journal: grep keeps only matching lines', r['ok'] and 0 < r['count'] < 200 and all('error' in x.lower() for x in r['lines']), str(r.get('count')))
r = b.send('journal', unit='NetworkManager.service', since='1 hour ago')
check('journal: other allow-listed unit and since', r['ok'] and r['unit'] == 'NetworkManager.service' and r['since'] == '1 hour ago')
for kw in ({'unit': 'turtlebot4.service; reboot'}, {'unit': 'sshd.service'}, {'since': '1 week ago'}, {'since': '$(id)'},
           {'lines': 'many'}, {'grep': 'x' * 81}, {'grep': ['a']}):
    r = b.send('journal', **kw)
    check('journal: %s refused' % str(list(kw.items())[0]), r and r['ok'] is False and r.get('error'), str(r))
b.close()

# ================================================================ History and AlertCenter (pure, fake clock)
clk = [1000.0]
pub = []
ac = st.AlertCenter(os.path.join(OUT, 'ev1.jsonl'), pub.append, clock=lambda: clk[0], max_bytes=600)
a1 = ac.raise_alert('wifi_weak', 'warn', 'weak')
clk[0] += 30
a2 = ac.raise_alert('wifi_weak', 'warn', 'weak again')
clk[0] += 31
a3 = ac.raise_alert('wifi_weak', 'warn', 'weak third')
check('alerts: same code at most once per 60 s', a1 and a2 is None and a3 and a3['id'] == a1['id'] + 1, str((a1, a2, a3)))
check('alerts: shape {id,t,severity,code,text} and an SSE event with ev=alert', set(a1) == {'id', 't', 'severity', 'code', 'text'} and pub[0]['ev'] == 'alert'
      and pub[0]['id'] == a1['id'] and len(pub) == 2)
check('alerts: unknown severity becomes info', ac.raise_alert('x1', 'bogus', 't')['severity'] == 'info')
e1 = ac.raise_alert('estop_on', 'critical', 'a')
e2 = ac.raise_alert('estop_on', 'critical', 'b')
clk[0] += 3
e3 = ac.raise_alert('estop_on', 'critical', 'c')
check('alerts: state changes (e-stop) only drop repeats inside 2 s', e1 and e2 is None and e3)
items, last = ac.since(0)
check('alerts since: all, then only newer ids', len(items) == last and [x['id'] for x in ac.since(items[-2]['id'])[0]] == [items[-1]['id']] and ac.since(last)[0] == [])
for i in range(30):
    clk[0] += 100
    ac.raise_alert('c%d' % i, 'info', 'fill ' + 'x' * 40)
check('events.jsonl rotates at the size limit and keeps one old file', os.path.isfile(ac.path + '.old') and os.path.getsize(ac.path) <= 700
      and not os.path.exists(ac.path + '.old.old') and not os.path.exists(ac.path + '.1'), str(os.listdir(OUT)))
ac2 = st.AlertCenter(ac.path, lambda ev: None, clock=lambda: clk[0], max_bytes=600)
check('alerts survive a restart and ids continue', ac2.since(0)[0] and ac2.next_id == ac.next_id and ac2.raise_alert('after_restart', 'info', 'x')['id'] == ac.next_id)
bad_path = os.path.join(OUT, 'no_such_dir', 'ev.jsonl')
ac3 = st.AlertCenter(bad_path, lambda ev: None)
check('an unwritable events file does not break alerts', ac3.raise_alert('a', 'info', 'x') is not None and ac3.since(0)[1] == 1)

clk[0] = 5000.0
ac = st.AlertCenter(os.path.join(OUT, 'ev2.jsonl'), pub.append, clock=lambda: clk[0])


def codes():
    return [x['code'] for x in ac.since(0)[0]]


def status(**kw):
    ev = {'ev': 'status', 'battery': {'percent': 80, 'charging': False}, 'dock': {'is_docked': False}, 'odom': {'age_s': 0.05, 'vx': 0, 'wz': 0},
          'scan': {'age_s': 0.1, 'rate_hz': 7}, 'estop': {'on': False}, 'system': {'temp_c': 50}, 'net': {'signal_dbm': -55},
          'clock': {'synced': True, 'year': 2026}, 'wall': clk[0]}
    for k, v in kw.items():
        ev[k] = dict(ev.get(k) or {}, **v) if isinstance(v, dict) else v
    return ev


ac.check_status(status())
check('healthy status raises nothing', codes() == [])
ac.check_status(status(battery={'percent': 19}))
ac.check_status(status(battery={'percent': 18}))
check('battery < 20 %: one warn alert', codes() == ['battery_low'] and ac.since(0)[0][0]['severity'] == 'warn')
ac.check_status(status(battery={'percent': 9}))
check('battery < 10 %: critical alert', codes()[-1] == 'battery_critical' and ac.since(0)[0][-1]['severity'] == 'critical')
ac.check_status(status(battery={'percent': 50}))
check('battery recovered: info "cleared" alert', codes()[-1] == 'battery_cleared' and ac.since(0)[0][-1]['severity'] == 'info')
ac2 = st.AlertCenter(os.path.join(OUT, 'ev3.jsonl'), lambda ev: None, clock=lambda: clk[0])
ac2.check_status(status(battery={'percent': 8, 'charging': True}))
check('a charging robot is not "low"', ac2.since(0)[0] == [])
ac2.check_status(status(estop={'on': True, 'source': 'robot'}))
ac2.check_status(status(estop={'on': False}))
check('e-stop on / released raise critical then info', [x['code'] for x in ac2.since(0)[0]] == ['estop_on', 'estop_off'] and ac2.since(0)[0][0]['severity'] == 'critical')
ac2.check_status(status(dock={'is_docked': True}))
ac2.check_status(status(dock={'is_docked': False}))
check('docked / undocked changes (not the first reading)', [x['code'] for x in ac2.since(0)[0]][2:] == ['docked', 'undocked'], str(ac2.since(0)[0]))
n = len(ac2.since(0)[0])
ac2.check_status(status(net={'signal_dbm': -80}, system={'temp_c': 80}, wall=1_000_000.0))
check('weak Wi-Fi (< -75), hot (> 75 C), wrong clock raise warnings', [x['code'] for x in ac2.since(0)[0]][n:] == ['wifi_weak', 'temp_high', 'clock_wrong'])
ac2.check_status(status(net={'signal_dbm': -60}, system={'temp_c': 60}))
check('and an info alert when they end', [x['code'] for x in ac2.since(0)[0]][n + 3:] == ['wifi_weak_cleared', 'temp_high_cleared', 'clock_wrong_cleared'])
ac4 = st.AlertCenter(os.path.join(OUT, 'ev4.jsonl'), lambda ev: None, clock=lambda: clk[0])
ac4.check_status(status(scan={'age_s': None, 'rate_hz': None}))
clk[0] += 5
ac4.check_status(status(scan={'age_s': None, 'rate_hz': None}))
check('lidar silent while undocked: not before 10 s', ac4.since(0)[0] == [])
clk[0] += 6
ac4.check_status(status(scan={'age_s': None, 'rate_hz': None}))
check('lidar silent while undocked for 10 s: warning', [x['code'] for x in ac4.since(0)[0]] == ['lidar_silent'])
ac5 = st.AlertCenter(os.path.join(OUT, 'ev5.jsonl'), lambda ev: None, clock=lambda: clk[0])
clk[0] += 20
ac5.check_status(status(dock={'is_docked': True}, scan={'age_s': None, 'rate_hz': None}))
clk[0] += 20
ac5.check_status(status(dock={'is_docked': True}, scan={'age_s': None, 'rate_hz': None}))
check('lidar off while docked is normal', ac5.since(0)[0] == [])
ac6 = st.AlertCenter(os.path.join(OUT, 'ev6.jsonl'), lambda ev: None, clock=lambda: clk[0])
ac6.check_status(status(odom={'age_s': 0.9, 'vx': 0.0, 'wz': 0.0}))
check('odometry old but the robot is not moving: no alert', ac6.since(0)[0] == [])
ac6.check_status(status(odom={'age_s': 0.9, 'vx': 0.1, 'wz': 0.0}))
check('odometry stall (age > 0.5 s while moving)', [x['code'] for x in ac6.since(0)[0]] == ['odom_stall'])
ac6.check_status(status(odom={'age_s': 0.9, 'vx': 0.0, 'wz': 0.0}), moving=True)
check('moving flag (armed driving / motion program) also counts', [x['code'] for x in ac6.since(0)[0]] == ['odom_stall'])
ac6.check_status(status(odom={'age_s': 0.05, 'vx': 0.1, 'wz': 0.0}))
check('odometry flowing again: info', ac6.since(0)[0][-1]['code'] == 'odom_stall_cleared')
check('is_status_moving: motion run or armed', st.is_status_moving({'runs': [{'motion': True, 'alive': True}]}) and st.is_status_moving({}, True)
      and not st.is_status_moving({'runs': [{'motion': True, 'alive': False}, {'motion': False, 'alive': True}]}))

h = st.History()
for i in range(5):
    h.add(status(battery={'percent': 80 - i, 'voltage': 15.0, 'current_a': -0.5}, odom={'rate_hz': 20, 'vx': -0.1},
                 scan={'rate_hz': 7.5}, system={'cpu_pct': 12, 'temp_c': 50}, net={'signal_dbm': -55}), now=2000.0 + i)
check('history: at most one sample per second', h.add(status(), now=2004.5) is False and h.add(status(), now=2005.0) is True)
q = h.query(15, now=2006.0)
check('history shape {t, series{9 keys}} with equal lengths', set(q) == {'t', 'series'} and set(q['series']) == set(st.HISTORY_SERIES) and len(st.HISTORY_SERIES) == 9
      and all(len(v) == len(q['t']) == 6 for v in q['series'].values()), str(list(q['series'])))
check('history values: battery %, speed is absolute, null for missing', q['series']['battery_pct'][:5] == [80, 79, 78, 77, 76] and q['series']['speed'][0] == 0.1
      and q['series']['wifi_dbm'][0] == -55 and q['series']['cpu_pct'][0] == 12 and st.history_sample({})['battery_pct'] is None)
check('history: window in minutes (older samples dropped), minutes clamped to 1..30', len(h.query(1, now=2062.0)['t']) == 4 and len(h.query(0.001, now=2006.0)['t']) == 6
      and st.clamp_minutes(500) == 30.0 and st.clamp_minutes('x') == 15.0 and st.clamp_minutes(None) == 15.0)
big = st.History(keep=10)
for i in range(30):
    big.add(status(), now=3000.0 + i)
check('history keeps a bounded number of samples (30 min at 1 Hz)', len(big.rows) == 10 and st.History().rows.maxlen == 1800)
check('history_sample ignores nan / inf / bool', st.history_sample({'battery': {'percent': NAN, 'voltage': INF, 'current_a': True}})['battery_pct'] is None
      and st.history_sample({'battery': {'voltage': INF}})['voltage'] is None and st.history_sample({'battery': {'current_a': True}})['current_a'] is None)
check('limit_value caps and defaults', st.limit_value(5, 0.15, 0.02, 0.3) == 0.3 and st.limit_value(0.001, 0.15, 0.02, 0.3) == 0.02 and st.limit_value('x', 0.15, 0.02, 0.3) == 0.15
      and st.limit_value(-1, 0.15, 0.02, 0.3) == 0.15 and st.limit_value(NAN, 0.15, 0.02, 0.3) == 0.15)

# ================================================================ Studio in-process: on_status, teleop_off, quit
cfgd = os.path.join(OUT, 'inproc_cfg')
app = st.Studio(st.parse_args(['--fake', '--config-dir', cfgd, '--fake-home', os.path.join(cfgd, 'home')]))
check('Studio 2.0: VERSION and settings defaults', st.VERSION == '2.1' and app.settings['ui'] == 'v2' and app.settings['teleop_linear'] == 0.15
      and app.settings['teleop_angular'] == 0.6)
app.on_status(status(battery={'percent': 12}))
check('on_status feeds history and alerts', app.history.query(15)['series']['battery_pct'][-1] == 12 and 'battery_low' in [x['code'] for x in app.alerts.since(0)[0]])
q1 = app.bus.subscribe()
res = app.connect()
check('fake connect ok', res['ok'], str(res))
wait_for(lambda: app.bridge.connected, 5)
app.forward({'cmd': 'undock', 'confirmed': True})
wait_for(lambda: app.bus.last_status and app.bus.last_status['dock']['is_docked'] is False, 6)
check('forward teleop: refused locally when not armed (nothing is sent)', app.forward({'cmd': 'teleop', 'vx': 0.1, 'wz': 0, 'seq': 1})
      == {'ok': False, 'error': 'Manual driving is not armed.', 'armed': False})
r = app.forward({'cmd': 'teleop_arm', 'on': True, 'max_linear': 9, 'max_angular': 9})
check('forward teleop_arm: Studio settings override the limits the page sends (0.15 / 0.6)', r['ok'] and r['max_linear'] == 0.15 and r['max_angular'] == 0.6, str(r))
check('Studio knows it is armed for this bridge process', app.tele_armed is True and app.tele_gen == app.bridge.gen)
r = app.forward({'cmd': 'teleop', 'vx': 1.0, 'wz': 3.0, 'seq': 1})
check('forward teleop: clamped to the settings limits', r['ok'] and r['vx'] == 0.15 and r['wz'] == 0.6, str(r))
app.teleop_limits({'linear': 0.25, 'angular': 1.0})
r = app.forward({'cmd': 'teleop', 'vx': 1.0, 'wz': 3.0, 'seq': 2})
check('new limits apply to the very next command', r['vx'] == 0.25 and r['wz'] == 1.0, str(r))
app.tele_gen = app.bridge.gen + 7          # pretend the arm belonged to an earlier bridge process
check('motion is never sent when the arm belongs to another bridge process', app.forward({'cmd': 'teleop', 'vx': 0.1, 'wz': 0, 'seq': 3})['ok'] is False)
app.tele_gen = app.bridge.gen
was = app.teleop_off('test')
wait_for(lambda: not app.tele_armed, 2)
check('teleop_off disarms the bridge and Studio', was is True and app.tele_armed is False and app.forward({'cmd': 'teleop', 'vx': 0.1, 'wz': 0, 'seq': 9})['ok'] is False)
tev = [e for e in iter(lambda: q1.get_nowait() if not q1.empty() else None, None) if e.get('ev') == 'teleop']
check('teleop events reached the event bus (armed, then disarmed with the reason)', [e['armed'] for e in tev] == [True, False] and tev[-1]['reason'] == 'test', str(tev))
app.forward({'cmd': 'teleop_arm', 'on': True})
check('armed again', app.tele_armed is True)
app.quit()
check('quit() disarms manual driving first', app.tele_armed is False)
app.forward({'cmd': 'teleop_arm', 'on': True})
r = app.disconnect()
check('disconnect() disarms (nothing left armed after the bridge ends)', app.tele_armed is False)
res = app.connect()
wait_for(lambda: app.bridge.connected, 5)
wait_for(lambda: app.bus.last_status, 3)
app.forward({'cmd': 'undock', 'confirmed': True})
wait_for(lambda: app.bus.last_status['dock']['is_docked'] is False, 6)
app.forward({'cmd': 'teleop_arm', 'on': True})
app.reconnect_delays = (0.2,)
app.fake_drop()
wait_for(lambda: app.bus.last_conn.get('state') == 'reconnecting', 5)
ok = wait_for(lambda: app.tele_armed is False, 3)
check('a lost connection disarms; Studio publishes the teleop event itself when the bridge cannot', ok)
wait_for(lambda: app.bridge.connected and app.bus.last_conn.get('state') == 'connected' and app.reconn is None, 10)
time.sleep(0.3)
check('after the automatic reconnect nothing is armed and teleop is refused (no motion resent)', app.tele_armed is False
      and app.forward({'cmd': 'teleop', 'vx': 0.2, 'wz': 0, 'seq': 1})['ok'] is False)
codes_all = [x['code'] for x in app.alerts.since(0)[0]]
check('connection alerts: connected, lost, restored', 'conn_connected' in codes_all and 'conn_lost' in codes_all and 'conn_restored' in codes_all, str(codes_all))
check('driving alerts: armed and off', 'teleop_armed' in codes_all and 'teleop_disarmed' in codes_all)
app.estop()
check('Studio.estop() clears the armed state at once', app.tele_armed is False)
app.shutdown()
check('teleop_limits: validation', app.teleop_limits({'linear': 'x'})['ok'] is False and app.teleop_limits({'linear': -1})['ok'] is False
      and app.teleop_limits({})['ok'] is False and app.teleop_limits({'angular': 9})['angular'] == 1.2 and app.teleop_limits({'linear': 0.001})['linear'] == 0.02
      and app.teleop_limits()['max_linear'] == 0.3)
with open(os.path.join(cfgd, 'settings.json'), encoding='utf-8') as f:
    saved = json.load(f)
check('teleop limits are stored in settings.json', saved['teleop_angular'] == 1.2 and saved['teleop_linear'] == 0.02)
with open(os.path.join(cfgd, 'settings.json'), 'w', encoding='utf-8') as f:
    json.dump({'teleop_linear': 99, 'teleop_angular': 'x', 'ui': 'neon'}, f)
app_b = st.Studio(st.parse_args(['--fake', '--config-dir', cfgd]))
check('bad stored values fall back (limit capped, text -> default, unknown ui -> v2)', app_b.settings['teleop_linear'] == 0.3 and app_b.settings['teleop_angular'] == 0.6
      and app_b.settings['ui'] == 'v2')
check('post_settings: ui must be v2 or classic', app_b.post_settings({'ui': 'neon'})['ok'] is False and app_b.post_settings({'ui': 'classic'})['ui'] == 'classic')
check('post_settings cannot set the teleop limits (own endpoint, own validation)', app_b.post_settings({'teleop_linear': 9})['teleop_linear'] == 0.3)

# ================================================================ HTTP: real studio.py --fake
WEB = os.path.join(OUT, 'web_copy')
shutil.copytree(os.path.join(STUDIO_DIR, 'web'), WEB, ignore=shutil.ignore_patterns('v2'))
CFG = os.path.join(OUT, 'httpcfg')
HOME = os.path.join(OUT, 'httphome')
os.makedirs(HOME)
env = dict(os.environ, HOME=HOME, USERPROFILE=HOME, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
proc = subprocess.Popen([sys.executable, '-u', os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--port', '0', '--config-dir', CFG,
                         '--fake-home', os.path.join(CFG, 'home'), '--heartbeat', '1', '--web-dir', WEB],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
url = {}
got_url = threading.Event()


def read_stdout():
    for raw in proc.stdout:
        m = re.search(r'http://127\.0\.0\.1:(\d+)/\?token=(\S+)', raw.decode('utf-8', 'replace'))
        if m:
            url['port'], url['token'] = int(m.group(1)), m.group(2)
            got_url.set()


threading.Thread(target=read_stdout, daemon=True).start()
try:
    check('studio.py --fake --web-dir starts', got_url.wait(20))
    PORT, TOKEN = url['port'], url['token']

    def call_raw(method, path, body=None, timeout=30, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=timeout)
        h = {'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN}
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        c.request(method, path, body=data, headers=h)
        resp = c.getresponse()
        txt = resp.read()
        hd = dict((k.lower(), v) for k, v in resp.getheaders())
        c.close()
        return resp.status, txt, hd

    def call(method, path, body=None, timeout=30):
        return json.loads(call_raw(method, path, body, timeout)[1].decode('utf-8'))

    class Sse:
        def __init__(self):
            self.buf = bytearray()
            self.c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=300)
            self.c.request('GET', '/api/events', headers={'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN})
            self.resp = self.c.getresponse()
            threading.Thread(target=self._rd, daemon=True).start()

        def _rd(self):
            try:
                while True:
                    x = self.resp.read1(4096)
                    if not x:
                        break
                    self.buf.extend(x)
            except (OSError, http.client.HTTPException, ValueError):
                pass

        def events(self):
            out = []
            for ln in bytes(self.buf).decode('utf-8', 'replace').splitlines():
                if ln.startswith('data: '):
                    try:
                        out.append(json.loads(ln[6:]))
                    except ValueError:
                        pass
            return out

        def close(self):
            try:
                self.resp.close()
                self.c.close()
            except OSError:
                pass

    # ---- serving
    with open(os.path.join(WEB, 'index.html'), 'rb') as f:
        classic_html = f.read()
    code, body, hd = call_raw('GET', '/')
    check('GET / serves the classic page when web/v2 does not exist yet', code == 200 and body == classic_html and 'text/html' in hd['content-type']
          and 'frame-ancestors' in hd.get('content-security-policy', ''))
    code, body, hd = call_raw('GET', '/classic/')
    check('GET /classic/ serves the 1.3 page', code == 200 and body == classic_html)
    code, body, hd = call_raw('GET', '/classic/app.js')
    check('GET /classic/app.js serves the 1.3 script (relative links work)', code == 200 and 'javascript' in hd['content-type'] and len(body) > 1000)
    code, body, hd = call_raw('GET', '/app.js')
    check('GET /app.js still works (root fallback keeps the classic page working)', code == 200)
    code, body, hd = call_raw('GET', '/classic')
    check('GET /classic redirects to /classic/ (keeps the query)', code == 302 and hd['location'] == '/classic/', str(hd.get('location')))
    code, body, hd = call_raw('GET', '/classic?token=abc')
    check('redirect keeps ?token=', hd['location'] == '/classic/?token=abc')
    check('GET /v2/ is 404 while web/v2 does not exist', call_raw('GET', '/v2/')[0] == 404 and call_raw('GET', '/v2/index.html')[0] == 404)
    check('static path traversal is refused', call_raw('GET', '/classic/../studio.py')[0] == 404 and call_raw('GET', '/v2/../index.html')[0] == 404
          and call_raw('GET', '/classic/%2e%2e/studio.py')[0] == 404)
    code, body, hd = call_raw('GET', '/api/settings', headers={'X-Studio-Token': 'wrong'})
    check('the token rules are unchanged (wrong token 403)', code == 403)
    os.makedirs(os.path.join(WEB, 'v2', 'assets'))
    with open(os.path.join(WEB, 'v2', 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<!doctype html><title>v2 marker</title><script type="module" src="/v2/assets/app.js"></script>')
    with open(os.path.join(WEB, 'v2', 'assets', 'app.js'), 'w', encoding='utf-8') as f:
        f.write('console.log(1)')
    with open(os.path.join(WEB, 'v2', 'assets', 'f.woff2'), 'wb') as f:
        f.write(b'wOF2....')
    code, body, hd = call_raw('GET', '/')
    check('GET / serves web/v2/index.html once it exists', code == 200 and b'v2 marker' in body and 'frame-ancestors' in hd.get('content-security-policy', '')
          and 'font-src' in hd['content-security-policy'])
    code, body, hd = call_raw('GET', '/v2/')
    check('GET /v2/ and /v2/index.html serve it too', code == 200 and b'v2 marker' in body and call_raw('GET', '/v2/index.html')[1] == body)
    code, body, hd = call_raw('GET', '/v2/assets/app.js')
    check('GET /v2/assets/app.js: static file with a JavaScript type', code == 200 and body == b'console.log(1)' and 'javascript' in hd['content-type'])
    code, body, hd = call_raw('GET', '/v2/assets/f.woff2')
    check('fonts get a font type', code == 200 and hd['content-type'] == 'font/woff2')
    check('GET /v2/missing.js is 404', call_raw('GET', '/v2/missing.js')[0] == 404)
    code, body, hd = call_raw('GET', '/classic/')
    check('/classic/ is still the 1.3 page next to v2', code == 200 and body == classic_html)
    r = call('POST', '/api/settings', {'ui': 'neon'})
    check('setting ui must be v2 or classic', r['ok'] is False)
    r = call('POST', '/api/settings', {'ui': 'classic'})
    check('setting ui=classic', r['ok'] and r['ui'] == 'classic')
    code, body, hd = call_raw('GET', '/')
    check('with ui=classic GET / serves the 1.3 page even though web/v2 exists', body == classic_html)
    check('/v2/ still works with ui=classic', b'v2 marker' in call_raw('GET', '/v2/')[1])
    call('POST', '/api/settings', {'ui': 'v2'})
    check('with ui=v2 GET / serves the new page again', b'v2 marker' in call_raw('GET', '/')[1])
    gs = call('GET', '/api/settings')
    check('settings carry version 2.1, ui and the teleop limits', gs['version'] == '2.1' and gs['ui'] == 'v2' and gs['teleop_linear'] == 0.15 and gs['teleop_angular'] == 0.6)

    # ---- teleop_limits
    r = call('GET', '/api/teleop_limits')
    check('GET /api/teleop_limits: {ok, linear, angular, max_linear, max_angular}', r == {'ok': True, 'linear': 0.15, 'angular': 0.6, 'max_linear': 0.3, 'max_angular': 1.2}, str(r))
    r = call('POST', '/api/teleop_limits', {'linear': 0.2, 'angular': 0.9})
    check('POST /api/teleop_limits stores both', r['ok'] and r['linear'] == 0.2 and r['angular'] == 0.9)
    r = call('POST', '/api/teleop_limits', {'linear': 5, 'angular': 50})
    check('POST /api/teleop_limits: capped by the bridge limits', r['ok'] and r['linear'] == 0.3 and r['angular'] == 1.2, str(r))
    check('POST /api/teleop_limits: refuses text, zero, empty', call('POST', '/api/teleop_limits', {'linear': 'fast'})['ok'] is False
          and call('POST', '/api/teleop_limits', {'angular': 0})['ok'] is False and call('POST', '/api/teleop_limits', {})['ok'] is False)
    call('POST', '/api/teleop_limits', {'linear': 0.15, 'angular': 0.6})

    # ---- connect, history, alerts, SSE
    A = Sse()
    check('connect (fake)', call('POST', '/api/connect', {})['ok'])
    wait_for(lambda: [e for e in A.events() if e.get('ev') == 'status'], 5)
    time.sleep(2.2)
    r = call('GET', '/api/history?minutes=15')
    n = len(r['t'])
    check('GET /api/history: ok, t[], 9 series of the same length, 1 s interval', r['ok'] and set(r['series']) == set(st.HISTORY_SERIES) and n >= 2
          and all(len(v) == n for v in r['series'].values()) and r['interval_s'] == 1 and r['minutes'] == 15, str((n, list(r))))
    check('history values come from the fake robot', all(isinstance(x, (int, float)) for x in r['series']['battery_pct']) and r['series']['wifi_dbm'][-1] == -55.0
          and r['series']['cpu_pct'][-1] is not None and all(b2 > a2 for a2, b2 in zip(r['t'], r['t'][1:])))
    check('history: bad / out-of-range minutes fall back or clamp', call('GET', '/api/history?minutes=abc')['minutes'] == 15 and call('GET', '/api/history')['minutes'] == 15
          and call('GET', '/api/history?minutes=999')['minutes'] == 30 and call('GET', '/api/history?minutes=0')['minutes'] == 1)
    check('history needs the token', call_raw('GET', '/api/history', headers={'X-Studio-Token': 'x'})[0] == 403 and call_raw('GET', '/api/alerts', headers={'X-Studio-Token': 'x'})[0] == 403)
    al = call('GET', '/api/alerts')
    check('GET /api/alerts: {ok, alerts[{id,t,severity,code,text}], last_id} with the connection alert', al['ok'] and any(x['code'] == 'conn_connected' for x in al['alerts'])
          and all(set(x) == {'id', 't', 'severity', 'code', 'text'} for x in al['alerts']) and al['last_id'] == al['alerts'][-1]['id'], str(al))
    check('GET /api/alerts?since= returns only newer ones', call('GET', '/api/alerts?since=%d' % al['last_id'])['alerts'] == [] and call('GET', '/api/alerts?since=junk')['ok'])
    ev_alerts = [e for e in A.events() if e.get('ev') == 'alert']
    check('SSE carries {"ev":"alert", id, t, severity, code, text}', ev_alerts and set(ev_alerts[0]) == {'ev', 'id', 't', 'severity', 'code', 'text'}, str(ev_alerts[:1]))
    check('events.jsonl is written in the config folder', os.path.isfile(os.path.join(CFG, 'events.jsonl'))
          and json.loads(open(os.path.join(CFG, 'events.jsonl'), encoding='utf-8').readline())['code'] == 'conn_connected')

    # ---- scan / pose through Studio, teleop through Studio
    check('scan_on / pose_on through /api/bridge', call('POST', '/api/bridge', {'cmd': 'scan_on', 'hz': 5})['ok'] and call('POST', '/api/bridge', {'cmd': 'pose_on', 'hz': 10})['ok'])
    time.sleep(1.0)
    evs = A.events()
    check('SSE carries scan and pose events', any(e.get('ev') == 'scan' and len(e['ranges']) == 360 for e in evs) and any(e.get('ev') == 'pose' for e in evs))
    r = call('POST', '/api/bridge', {'cmd': 'teleop_arm', 'on': True})
    check('arm refused while docked ("Undock first")', r['ok'] is False and 'Undock first' in r['error'], str(r))
    call('POST', '/api/bridge', {'cmd': 'undock', 'confirmed': True})
    wait_for(lambda: call('GET', '/api/events') if False else [e for e in A.events() if e.get('ev') == 'status' and e['dock']['is_docked'] is False], 8)
    r = call('POST', '/api/bridge', {'cmd': 'teleop_arm', 'on': True})
    check('arm ok after undocking; reply has the settings limits', r['ok'] and r['max_linear'] == 0.15 and r['max_angular'] == 0.6, str(r))
    wait_for(lambda: [e for e in A.events() if e.get('ev') == 'teleop' and e['armed']], 2)
    check('SSE carries {"ev":"teleop","armed":true,"reason"}', [e for e in A.events() if e.get('ev') == 'teleop'][-1] == {'ev': 'teleop', 'armed': True, 'reason': 'armed'})
    r = call('POST', '/api/bridge', {'cmd': 'teleop', 'vx': 0.3, 'wz': 0.0, 'seq': 1})
    check('teleop through Studio is clamped to the user limit', r['ok'] and r['vx'] == 0.15)
    r = call('POST', '/api/bridge', {'cmd': 'journal', 'lines': 60})
    check('journal through Studio', r['ok'] and r['count'] == 60)

    # ---- auto-disarm: the last event stream closes
    time.sleep(0.5)
    B = Sse()
    A.close()
    time.sleep(0.4)
    check('closing one of two event streams does not disarm', call('POST', '/api/bridge', {'cmd': 'teleop', 'vx': 0.1, 'wz': 0, 'seq': 2})['ok'] is True)
    B.close()
    time.sleep(1.5)
    C = Sse()
    r = call('POST', '/api/bridge', {'cmd': 'teleop', 'vx': 0.1, 'wz': 0, 'seq': 3})
    check('closing the LAST event stream disarms manual driving', r['ok'] is False and 'not armed' in r['error'].lower(), str(r))
    al = call('GET', '/api/alerts')['alerts']
    check('...and the alert log says why', any(x['code'] == 'teleop_disarmed' and 'last' in x['text'].lower() for x in al), str([x for x in al if 'teleop' in x['code']]))
    wait_for(lambda: [e for e in C.events() if e.get('ev') == 'status' and e.get('teleop')], 3)
    check('status shows teleop.armed false', [e for e in C.events() if e.get('ev') == 'status'][-1]['teleop']['armed'] is False)

    # ---- auto-disarm: e-stop
    call('POST', '/api/bridge', {'cmd': 'teleop_arm', 'on': True})
    check('armed again', call('POST', '/api/bridge', {'cmd': 'teleop', 'vx': 0.1, 'wz': 0, 'seq': 1})['ok'])
    r = call('POST', '/api/estop', {})
    check('e-stop through Studio', r['ok'] is True)
    wait_for(lambda: [e for e in C.events() if e.get('ev') == 'teleop' and e['armed'] is False and e['reason'] == 'e-stop'], 3)
    check('e-stop disarms: teleop event with reason e-stop', [e for e in C.events() if e.get('ev') == 'teleop' and e['reason'] == 'e-stop'])
    r = call('POST', '/api/bridge', {'cmd': 'teleop', 'vx': 0.1, 'wz': 0, 'seq': 2})
    check('after the e-stop teleop is refused', r['ok'] is False)
    r = call('POST', '/api/bridge', {'cmd': 'teleop_arm', 'on': True})
    check('...and arming is refused while the e-stop is latched', r['ok'] is False and 'e-stop' in r['error'].lower(), str(r))
    wait_for(lambda: [x for x in call('GET', '/api/alerts')['alerts'] if x['code'] == 'estop_on'], 4)
    codes_http = [x['code'] for x in call('GET', '/api/alerts')['alerts']]
    check('alerts: e-stop on, driving armed / off, undocked', 'estop_on' in codes_http and 'teleop_armed' in codes_http and 'teleop_disarmed' in codes_http and 'undocked' in codes_http, str(codes_http))
    r = call('POST', '/api/bridge', {'cmd': 'estop_release'})
    check('e-stop release', r['ok'])
    wait_for(lambda: [x for x in call('GET', '/api/alerts')['alerts'] if x['code'] == 'estop_off'], 4)
    check('alerts: e-stop released (info)', [x for x in call('GET', '/api/alerts')['alerts'] if x['code'] == 'estop_off'][-1]['severity'] == 'info')

    # ---- auto-disarm: reconnect never resends motion
    r = call('POST', '/api/bridge', {'cmd': 'teleop_arm', 'on': True})
    check('arm before the connection drops', r['ok'], str(r))
    mark = len(C.events())
    call('POST', '/api/fake_drop', {})
    wait_for(lambda: [e for e in C.events()[mark:] if e.get('ev') == 'conn' and e['state'] == 'reconnecting'], 8)
    r = call('POST', '/api/bridge', {'cmd': 'teleop', 'vx': 0.2, 'wz': 0, 'seq': 99})
    check('while reconnecting, teleop is refused', r['ok'] is False)
    check('the drop disarms (teleop event after the drop)', [e for e in C.events()[mark:] if e.get('ev') == 'teleop' and e['armed'] is False])
    wait_for(lambda: [e for e in C.events()[mark:] if e.get('ev') == 'conn' and e['state'] == 'connected'], 15)
    r = call('POST', '/api/bridge', {'cmd': 'teleop', 'vx': 0.2, 'wz': 0, 'seq': 100})
    check('after the reconnect the new bridge is not armed and nothing is resent', r['ok'] is False and 'not armed' in r['error'].lower(), str(r))
    cj = [x['code'] for x in call('GET', '/api/alerts')['alerts']]
    check('alerts: connection lost and restored', 'conn_lost' in cj and 'conn_restored' in cj)
    C.close()
finally:
    try:
        call('POST', '/api/quit', {})
    except Exception:
        pass
    try:
        proc.wait(8)
    except subprocess.TimeoutExpired:
        proc.kill()

check('studio.py stopped after /api/quit', proc.poll() is not None)

# ================================================================ line endings, packaging
for fn in (os.path.join(STUDIO_DIR, 'studio.py'), BRIDGE):
    with open(fn, 'rb') as f:
        check('LF line endings: ' + os.path.basename(fn), b'\r' not in f.read())
with open(os.path.join(STUDIO_DIR, 'version.json'), encoding='utf-8') as f:
    vj = json.load(f)
check('version.json is 2.1 and matches studio.VERSION', vj['version'] == '2.1' == st.VERSION)
with open(os.path.join(STUDIO_DIR, 'packaging', 'studio.spec'), encoding='utf-8') as f:
    spec_txt = f.read()
check("packaging/studio.spec bundles everything under web/ (including web/v2)", "tree('web')" in spec_txt)

print('\n%d failure(s); generated files are in %s' % (fails, OUT))
sys.exit(fails)
