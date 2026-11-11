"""Offline tests of the TurtleBot Studio 2.1 mapping feature in the robot bridge (TurtleBot/tools/studio/robot_bridge.py):
names, map YAML, PGM, grid encoding, pose composition, the mapping state machine (scripted runner and probe), the map
library on a temporary folder, the teleop refusal while mapping changes state, and the bridge as a subprocess in --fake
mode (start, growing map events, pose with map, save, list, preview, rename, delete, stop).

No robot, no ROS, no network; everything lives in temporary folders.
Usage: python test_studio_mapping.py     (prints PASS/FAIL, exit code = number of failures)
"""
import array
import base64
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zlib

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['STUDIO_FAKE_MAP_SCALE'] = '0.2'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
BRIDGE = os.path.join(STUDIO_DIR, 'robot_bridge.py')

spec = importlib.util.spec_from_file_location('robot_bridge_map', BRIDGE)
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)

OUT = tempfile.mkdtemp(prefix='tb4_studio_map_')
fails = 0


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode())
    if not cond:
        fails += 1


def wait_for(fn, timeout, step=0.02):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


def raises(fn, *a, **kw):
    """The ServiceError raised by fn, or None."""
    try:
        fn(*a, **kw)
    except rb.ServiceError as e:
        return e
    return None


def unz(b64):
    return zlib.decompress(base64.b64decode(b64))


def mkdir(prefix):
    return tempfile.mkdtemp(prefix=prefix, dir=OUT)


# ================================================================ pure helpers
check('name: letters, digits, _ and -', all(rb.valid_map_name(n) for n in ('a', 'Route_1', 'x-y', '9lab', 'A' * 48)))
check('name: bad names refused', not any(rb.valid_map_name(n) for n in
      ('', '_a', '-a', 'a b', 'a/b', '..', '../x', 'a.b', 'a\\b', 'A' * 49, 'a\n', None, 5, 'café')))

y = rb.parse_map_yaml("image: room.pgm\nmode: trinary\nresolution: 0.05\norigin: [-4.0, -3.0, 0.0]\nnegate: 0\n"
                      "occupied_thresh: 0.65\nfree_thresh: 0.25\n")
check('yaml: all fields', y['image'] == 'room.pgm' and y['resolution'] == 0.05 and y['origin'] == [-4.0, -3.0, 0.0]
      and y['negate'] == 0 and y['occupied_thresh'] == 0.65 and y['free_thresh'] == 0.25 and y['mode'] == 'trinary', str(y))
y = rb.parse_map_yaml("# comment\nimage: 'a b.pgm'   # trailing\nresolution: 5e-2\norigin: [1, 2, 3.5]\nnegate: 1\n")
check('yaml: comments, quotes, exponent, defaults', y['image'] == 'a b.pgm' and y['resolution'] == 0.05 and y['origin'] == [1.0, 2.0, 3.5]
      and y['negate'] == 1 and y['occupied_thresh'] == 0.65 and y['free_thresh'] == 0.25, str(y))
check('yaml: origin with two numbers gets yaw 0', rb.parse_map_yaml('image: a.pgm\nresolution: 0.1\norigin: [1, 2]')['origin'] == [1.0, 2.0, 0.0])
for bad in ('resolution: 0.05\n', 'image: a.pgm\n', 'image: a.pgm\nresolution: 0\n', 'image: a.pgm\nresolution: x\n', ''):
    try:
        rb.parse_map_yaml(bad)
        ok = False
    except ValueError:
        ok = True
    check('yaml: refused %r' % bad[:30], ok)
t = rb.rewrite_yaml_image("image: old.pgm\nresolution: 0.05\n", 'new.pgm')
check('yaml: image line rewritten, the rest kept', t == "image: new.pgm\nresolution: 0.05\n", repr(t))
check('yaml: image line added when missing', rb.rewrite_yaml_image("resolution: 0.05\n", 'n.pgm').startswith('image: n.pgm\n'))

p5 = b'P5\n# a comment\n3 2\n255\n' + bytes([0, 10, 20, 30, 40, 250])
check('pgm: P5 with comment', rb.read_pgm(p5) == (3, 2, bytes([0, 10, 20, 30, 40, 250])))
p2 = b'P2\n# c1\n3 2 # c2\n255\n0 10 20\n30 40\n250\n'
check('pgm: P2 ascii with comments', rb.read_pgm(p2) == (3, 2, bytes([0, 10, 20, 30, 40, 250])))
check('pgm: P5 header with a raster that starts with a whitespace value', rb.read_pgm(b'P5 2 1 255\n' + bytes([10, 32]))[2] == bytes([10, 32]))
for name, bad in (('wrong magic', b'P6\n1 1\n255\n\x00\x00\x00'), ('maxval 65535', b'P5\n1 1\n65535\n\x00\x00'),
                  ('short raster', b'P5\n3 3\n255\n\x00\x01'), ('truncated header', b'P5\n3'), ('empty', b''),
                  ('P2 above maxval', b'P2\n1 1\n100\n200\n')):
    try:
        rb.read_pgm(bad)
        ok = False
    except ValueError:
        ok = True
    check('pgm: refused (%s)' % name, ok)
check('pgm: header only', rb.pgm_header(p5)[:4] == ('P5', 3, 2, 255))

data = bytes(range(12))          # 4 x 3
check('sample: stride 1 is the same grid', rb.sample_grid(4, 3, data, 1) == (4, 3, data))
check('sample: stride 2 takes every second cell of every second row', rb.sample_grid(4, 3, data, 2) == (2, 2, bytes([0, 2, 8, 10])))
check('sample: stride 3 gives ceil sizes', rb.sample_grid(4, 3, data, 3)[:2] == (2, 1) and rb.sample_grid(4, 3, data, 3)[2] == bytes([0, 3]))
check('stride: 1 when it fits, grows with the grid', rb.choose_stride(100, 100, 10000) == 1 and rb.choose_stride(101, 100, 10000) == 2
      and rb.choose_stride(4000, 4000, 1000000) == 4)
sw, sh, _ = rb.sample_grid(4000, 3000, bytes(4000 * 3000), rb.choose_stride(4000, 3000, 1000000))
check('stride: sampled grid never exceeds max_cells', sw * sh <= 1000000, '%d' % (sw * sh))

check('encode: int8 data, unknown -1 becomes 255', rb.cells_bytes([-1, 0, 100, 5]) == bytes([255, 0, 100, 5]))
check('encode: array(b) like tobytes()', rb.cells_bytes(array.array('b', [-1, 0, 100])) == array.array('b', [-1, 0, 100]).tobytes()
      == bytes([255, 0, 100]))
check('encode: zlib + base64 round trip', unz(rb.encode_cells([-1, 0, 100, 50] * 100)) == bytes([255, 0, 100, 50] * 100))
ev = rb.build_map_event(3, 12.3456, 4, 3, 0.05, (-1.0, -2.0, 0.0), array.array('b', [-1] * 12), 1000000)
check('map event: shape', ev['ev'] == 'map' and ev['seq'] == 3 and ev['width'] == 4 and ev['height'] == 3 and ev['stride'] == 1
      and ev['encoding'] == 'cells' and ev['origin'] == {'x': -1.0, 'y': -2.0, 'yaw': 0.0} and ev['resolution'] == 0.05
      and unz(ev['data']) == bytes([255] * 12), str({k: v for k, v in ev.items() if k != 'data'}))
big = bytes([255, 0, 100] * (300 * 200 // 3))
ev = rb.build_map_event(1, 0.0, 300, 200, 0.05, (0, 0, 0), big, 10000)
check('map event: sampled when over max_cells (stride, sampled size and resolution)', ev['stride'] == 3 and ev['width'] == 100
      and ev['height'] == 67 and abs(ev['resolution'] - 0.15) < 1e-9 and len(unz(ev['data'])) == 100 * 67, str((ev['stride'], ev['width'], ev['height'])))

pi = math.pi
a = rb.compose_map_pose((1.0, 2.0, 0.5), (3.0, -1.0, 1.0), (3.0, -1.0, 1.0))
check('map pose: no odometry since the slam pose gives the slam pose', all(abs(u - v) < 1e-9 for u, v in zip(a, (1.0, 2.0, 0.5))), str(a))
a = rb.compose_map_pose((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 2.0, 0.3))
check('map pose: identity map<-odom gives the odometry', all(abs(u - v) < 1e-9 for u, v in zip(a, (1.0, 2.0, 0.3))), str(a))
# the map frame is turned 90 degrees and shifted against odom: odom (1,0) is map (10, 1)
a = rb.compose_map_pose((10.0, 1.0, pi / 2), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
check('map pose: rotated frame, robot moved 1 m forward since the slam pose', all(abs(u - v) < 1e-9 for u, v in zip(a, (10.0, 2.0, pi / 2))), str(a))
a = rb.compose_map_pose((0.0, 0.0, pi), (1.0, 1.0, pi / 2), (1.0, 2.0, pi / 2))
check('map pose: yaw stays within -pi..pi', -pi - 1e-9 <= a[2] <= pi + 1e-9 and abs(math.cos(a[2]) + 1.0) < 1e-9, str(a))

check('detect: slam only', rb.detect_stack(lambda p: p == 'slam.launch.py') == (True, None))
check('detect: each other stack pattern is named', all(rb.detect_stack(lambda p, q=q: p == q) == (False, q)
      for q in ('localization.launch.py', 'delivery_stack.launch.py', 'nav2.launch.py')))
check('detect: nothing', rb.detect_stack(lambda p: False) == (False, None))
check('tail: last 20 non-empty lines', rb.tail_lines('\n'.join(str(i) for i in range(30)) + '\n\n') == [str(i) for i in range(10, 30)])


# ================================================================ MappingService with a scripted runner and probe
class ScriptRunner(rb.StackRunner):
    def __init__(self):
        self.calls = []
        self.missing = []
        self.hooks = {}                  # script -> fn(args) -> (ok, output)
        self.gates = {}                  # script -> threading.Event the run waits for

    def scripts_ok(self):
        return not self.missing

    def missing_scripts(self):
        return list(self.missing)

    def run(self, script, args, timeout):
        self.calls.append((script, list(args), timeout))
        g = self.gates.get(script)
        if g is not None:
            g.wait(5)
        fn = self.hooks.get(script)
        return fn(args) if fn else (True, 'done')


class ScriptProbe(rb.ProcessProbe):
    def __init__(self):
        self.slam = False
        self.other = None

    def running(self, pattern):
        return self.slam if pattern == rb.SLAM_PATTERN else self.other == pattern


def make_service(maps_dir=None):
    runner, probe, events, disarms = ScriptRunner(), ScriptProbe(), [], []
    maps_dir = maps_dir or mkdir('maps_')
    svc = rb.MappingService(runner, probe, maps_dir, events.append, disarm=disarms.append, probe_period=60,
                            seen_wait=0.3, gone_wait=0.3)
    runner.hooks['start_stack.sh'] = lambda args: (setattr(probe, 'slam', True), (True, 'slam pid 1'))[1]

    def save(args):
        open(args[0] + '.yaml', 'w').write('image: x.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n')
        return True, 'saved'
    runner.hooks['save_map.sh'] = save
    runner.hooks['stop_stack.sh'] = lambda args: (setattr(probe, 'slam', False), (True, 'stopped'))[1]
    return svc, runner, probe, events, disarms


def states(events):
    return [e['state'] for e in events]


svc, runner, probe, events, disarms = make_service()
i0 = svc.status()
check('service: starts idle with the documented fields', i0['state'] == 'idle' and set(i0) == {
      'state', 'since', 'last_error', 'last_saved', 'unsaved', 'scripts_ok', 'other_stack', 'maps_dir'}
      and i0['unsaved'] is False and i0['last_error'] is None and i0['last_saved'] is None and i0['scripts_ok'] is True, str(i0))
r = svc.start()
check('start: replies at once with state starting', r['state'] == 'starting')
check('start: idle -> starting -> mapping', wait_for(lambda: svc.status()['state'] == 'mapping', 3) and states(events) == ['starting', 'mapping'], str(states(events)))
res = events[-1].get('result') or {}
check('start: result {op:start, ok:true, output_tail}', res.get('op') == 'start' and res.get('ok') is True and res.get('output_tail') == ['slam pid 1'], str(res))
check('start: unsaved is true while mapping, no error', svc.status()['unsaved'] is True and svc.status()['last_error'] is None)
check('start: runs start_stack.sh map with the 120 s timeout', runner.calls[0] == ('start_stack.sh', ['map'], 120.0), str(runner.calls[0]))
check('start: disarms driving first', disarms == ['mapping is starting'])
check('events: carry ev:mapping and the MappingInfo fields', all(e['ev'] == 'mapping' and 'state' in e and 'maps_dir' in e for e in events))
e = raises(svc.start)
check('start: refused unless idle (mapping)', e is not None and 'already running' in str(e))

# save
e = raises(svc.save, '../x')
check('save: bad name refused', e is not None and 'Bad map name' in str(e))
for bad in ('', None, 'a b', 'a/b'):
    check('save: bad name %r refused' % (bad,), raises(svc.save, bad) is not None)
n_calls = len(runner.calls)
check('save: bad names ran nothing', len(runner.calls) == n_calls and svc.status()['state'] == 'mapping')
events.clear()
runner.gates['save_map.sh'] = threading.Event()
r = svc.save('room1')
check('save: replies at once with state saving, driving disarmed', r['state'] == 'saving' and disarms[-1] == 'mapping is saving')
check('save: busy_name while saving', svc.busy_name() == 'room1')
check('save: nothing else can start meanwhile', raises(svc.start) is not None and raises(svc.stop) is not None and raises(svc.save, 'other') is not None)
runner.gates['save_map.sh'].set()
check('save: saving -> mapping with last_saved and unsaved false', wait_for(lambda: svc.status()['state'] == 'mapping', 3)
      and states(events) == ['saving', 'mapping'] and svc.status()['last_saved']['name'] == 'room1' and svc.status()['unsaved'] is False)
res = events[-1].get('result') or {}
check('save: result {op:save, ok:true, name}', res.get('op') == 'save' and res.get('ok') is True and res.get('name') == 'room1', str(res))
check('save: runs save_map.sh <maps>/<name> with the 200 s timeout and no --force',
      runner.calls[-1] == ('save_map.sh', [os.path.join(svc.maps_dir, 'room1')], 200.0), str(runner.calls[-1]))
check('save: busy_name is None again', svc.busy_name() is None)
e = raises(svc.save, 'room1')
check('save: existing map without overwrite gives exists:true', e is not None and e.extra.get('exists') is True, str(e))
check('save: the refusal changed nothing', svc.status()['state'] == 'mapping')
events.clear()
svc.save('room1', overwrite=True)
check('save: overwrite passes --force', wait_for(lambda: svc.status()['state'] == 'mapping' and states(events)[-1:] == ['mapping'], 3)
      and runner.calls[-1][1][-1] == '--force', str(runner.calls[-1]))

# save failure
runner.hooks['save_map.sh'] = lambda args: (False, 'x\nERROR: no map yet')
events.clear()
svc.save('room2')
check('save failure: back to mapping, last_error set, result ok false', wait_for(lambda: states(events)[-1:] == ['mapping'], 3)
      and svc.status()['state'] == 'mapping' and svc.status()['last_error'] == 'ERROR: no map yet'
      and events[-1]['result']['ok'] is False and events[-1]['result']['name'] == 'room2'
      and events[-1]['result']['output_tail'] == ['x', 'ERROR: no map yet'], str(events[-1]))
check('save failure: last_saved is still the earlier save', svc.status()['last_saved']['name'] == 'room1')
runner.hooks['save_map.sh'] = lambda args: (True, 'saved but no file')
events.clear()
svc.save('room3')
check('save: a script that wrote no YAML counts as failed', wait_for(lambda: states(events)[-1:] == ['mapping'], 3)
      and events[-1]['result']['ok'] is False and not os.path.exists(os.path.join(svc.maps_dir, 'room3.yaml')))

# stop
events.clear()
runner.gates['stop_stack.sh'] = threading.Event()
r = svc.stop()
check('stop: replies at once with state stopping, driving disarmed', r['state'] == 'stopping' and disarms[-1] == 'mapping is stopping')
runner.gates['stop_stack.sh'].set()
check('stop: mapping -> stopping -> idle, unsaved cleared', wait_for(lambda: svc.status()['state'] == 'idle', 3)
      and states(events) == ['stopping', 'idle'] and svc.status()['unsaved'] is False
      and events[-1]['result']['op'] == 'stop' and events[-1]['result']['ok'] is True)
check('stop: runs stop_stack.sh with the 90 s timeout', runner.calls[-1] == ('stop_stack.sh', [], 90.0), str(runner.calls[-1]))
check('stop: refused when idle', raises(svc.stop) is not None)
check('save: refused when idle', raises(svc.save, 'x') is not None)

# start failures
runner.hooks['start_stack.sh'] = lambda args: (False, 'a\nERROR: already running: slam.launch.py')
events.clear()
svc.start(keep_camera=True)
check('start failure: starting -> error with the script text', wait_for(lambda: svc.status()['state'] == 'error', 3)
      and states(events) == ['starting', 'error'] and svc.status()['last_error'] == 'ERROR: already running: slam.launch.py'
      and events[-1]['result']['ok'] is False and events[-1]['result']['op'] == 'start'
      and events[-1]['result']['output_tail'] == ['a', 'ERROR: already running: slam.launch.py'], str(events[-1]))
check('start: keep_camera adds --keep-camera', runner.calls[-1][1] == ['map', '--keep-camera'], str(runner.calls[-1]))
check('error: start refused', raises(svc.start) is not None and 'error' in str(raises(svc.start)))
r = svc.reset()
check('reset: error -> idle (no SLAM), error cleared', r['state'] == 'idle' and r['last_error'] is None and states(events)[-1] == 'idle')
runner.hooks['start_stack.sh'] = lambda args: (True, 'script ok but nothing started')
svc.start()
check('start: script ok but no SLAM process -> error', wait_for(lambda: svc.status()['state'] == 'error', 3)
      and 'not running' in (svc.status()['last_error'] or ''))
probe.slam = True
r = svc.reset()
check('reset: error -> mapping when SLAM is running', r['state'] == 'mapping' and r['unsaved'] is True and r['last_error'] is None)
check('reset: outside error it changes nothing', svc.reset()['state'] == 'mapping')

# stop that fails
runner.hooks['stop_stack.sh'] = lambda args: (True, 'sent SIGINT')          # the probe still sees SLAM
svc.stop()
check('stop: SLAM still running -> error', wait_for(lambda: svc.status()['state'] == 'error', 3)
      and 'still running' in (svc.status()['last_error'] or ''))
runner.hooks['stop_stack.sh'] = lambda args: (False, 'ERROR: pgrep not found')
probe.slam = False
svc.stop()
check('stop: failed script -> error', wait_for(lambda: svc.status()['state'] == 'error' and 'pgrep' in (svc.status()['last_error'] or ''), 3))
runner.hooks['stop_stack.sh'] = lambda args: (True, 'slam: not running')
svc.stop()
check('stop: allowed in error, SLAM gone -> idle', wait_for(lambda: svc.status()['state'] == 'idle', 3) and svc.status()['last_error'] is None)

# refusals at start
probe.other = 'nav2.launch.py'
e = raises(svc.start)
check('start: refused when a navigation stack runs (other_stack)', e is not None and e.extra.get('other_stack') == 'nav2.launch.py'
      and svc.status()['other_stack'] == 'nav2.launch.py' and svc.status()['state'] == 'idle', str(e))
probe.other = None
runner.missing = ['save_map.sh']
e = raises(svc.start)
check('start: refused when the scripts are missing', e is not None and e.extra.get('scripts_missing') is True and 'save_map.sh' in str(e)
      and svc.status()['scripts_ok'] is False, str(e))
runner.missing = []

# probe: outside start and crash
svc, runner, probe, events, disarms = make_service()
probe.slam = True
svc.probe_once()
check('probe: SLAM started outside Studio -> mapping, unsaved', svc.status()['state'] == 'mapping' and svc.status()['unsaved'] is True and states(events) == ['mapping'])
svc.probe_once()
check('probe: nothing changes while it keeps running', states(events) == ['mapping'])
probe.slam = False
svc.probe_once()
check('probe: SLAM gone without a stop -> error', svc.status()['state'] == 'error' and 'no longer running' in svc.status()['last_error'] and states(events) == ['mapping', 'error'])
check('crash: stop and reset leave the error', svc.reset()['state'] == 'idle')
probe.other = 'localization.launch.py'
n = len(events)
svc.probe_once()
check('probe: a navigation stack seen -> other_stack in an event', svc.status()['other_stack'] == 'localization.launch.py' and len(events) == n + 1
      and events[-1]['other_stack'] == 'localization.launch.py')
svc.probe_once()
check('probe: no event when nothing changed', len(events) == n + 1)

# the probe thread itself, and close() leaves the SLAM alone
svc2, runner2, probe2, events2, _ = make_service()
svc2.probe_period = 0.05
probe2.slam = True
svc2.start_probe()
check('probe thread: finds an outside SLAM by itself', wait_for(lambda: svc2.status()['state'] == 'mapping', 2))
svc2.close()
check('close: runs no script (SLAM keeps running)', runner2.calls == [] and probe2.slam is True)

# a runner that raises
svc3, runner3, probe3, events3, _ = make_service()
runner3.hooks['start_stack.sh'] = lambda args: 1 / 0
svc3.start()
check('runner exception -> error state, not a dead thread', wait_for(lambda: svc3.status()['state'] == 'error', 3)
      and 'ZeroDivisionError' in svc3.status()['last_error'])

# ================================================================ real runner and probe (no robot)
home = mkdir('home_')
rr = rb.RealStackRunner(home)
check('real runner: delivery folder is ~/robot_code/delivery', rr.delivery == os.path.join(home, 'robot_code', 'delivery'))
check('real runner: scripts missing are named', rr.scripts_ok() is False and rr.missing_scripts() == list(rb.MAP_SCRIPTS))
os.makedirs(os.path.join(home, 'robot_code', 'delivery', 'robot'))
for sname in rb.MAP_SCRIPTS:
    open(os.path.join(home, 'robot_code', 'delivery', 'robot', sname), 'w').write('echo "args: $@"; echo "dir: $(basename "$PWD")"\n')
check('real runner: scripts found', rr.scripts_ok() is True)
if os.name == 'posix' and shutil.which('bash'):
    ok, out = rr.run('start_stack.sh', ['map', '--keep-camera'], 20)
    check('real runner: bash <script> args, cwd = home, output captured', ok and 'args: map --keep-camera' in out
          and ('dir: ' + os.path.basename(home)) in out, out)
    open(os.path.join(home, 'robot_code', 'delivery', 'robot', 'stop_stack.sh'), 'w').write('echo bad >&2; exit 3\n')
    ok, out = rr.run('stop_stack.sh', [], 20)
    check('real runner: non-zero exit is not ok, stderr captured', ok is False and 'bad' in out, out)
    open(os.path.join(home, 'robot_code', 'delivery', 'robot', 'save_map.sh'), 'w').write('echo started; sleep 20\n')
    t0 = time.time()
    ok, out = rr.run('save_map.sh', ['x'], 0.5)
    check('real runner: timeout stops the script', ok is False and 'timed out' in out and time.time() - t0 < 10, out)
else:
    print('SKIP real runner (needs a POSIX system with bash)')
os.environ['STUDIO_DELIVERY_DIR'] = os.path.join(home, 'elsewhere')
check('real runner: STUDIO_DELIVERY_DIR overrides the folder', rb.RealStackRunner(home).delivery == os.path.join(home, 'elsewhere'))
del os.environ['STUDIO_DELIVERY_DIR']
check('real probe: a pattern nothing runs is false', rb.RealProcessProbe().running('zz_no_such_launch_%d.py' % os.getpid()) is False)

# ================================================================ MapLibrary on a temp folder
mdir = mkdir('lib_')
lib = rb.MapLibrary(mdir)
check('library: missing folder lists nothing', rb.MapLibrary(os.path.join(mdir, 'nope')).list() == [])
g = rb.FakeMapGrid(0.2)
g.reveal_all()
g.save(os.path.join(mdir, 'alpha'))
time.sleep(0.05)
os.utime(os.path.join(mdir, 'alpha.yaml'), (time.time() - 100, time.time() - 100))
for ext in ('.pgm', '.posegraph', '.data'):
    os.utime(os.path.join(mdir, 'alpha' + ext), (time.time() - 100, time.time() - 100))
g.save(os.path.join(mdir, 'beta'))
open(os.path.join(mdir, 'notes.txt'), 'w').write('x')
open(os.path.join(mdir, 'bad name.yaml'), 'w').write('image: x.pgm\nresolution: 0.05\n')
ents = lib.list()
check('library: lists valid maps newest first (not other files or bad names)', [e['name'] for e in ents] == ['beta', 'alpha'], str([e['name'] for e in ents]))
e0 = ents[0]
check('library: entry fields', e0['width'] == g.width and e0['height'] == g.height and e0['resolution'] == 0.05
      and e0['origin'] == [g.origin[0], g.origin[1], 0.0] and e0['bytes'] > g.width * g.height and e0['mtime'] > 0
      and set(e0['files']) == {'pgm', 'yaml', 'posegraph', 'data'} and all(isinstance(v, int) for v in e0['files'].values()), str(e0))
os.remove(os.path.join(mdir, 'beta.data'))
check('library: a missing file is null', lib.entry('beta')['files']['data'] is None)
g.save(os.path.join(mdir, 'beta'))

pv = lib.preview('alpha', 512)
raw = unz(pv['data'])
check('preview: gray, zlib+base64, sampled size matches the data', pv['encoding'] == 'gray' and pv['width'] * pv['height'] == len(raw)
      and pv['stride'] == 1 and pv['width'] == g.width, str({k: v for k, v in pv.items() if k != 'data'}))
check('preview: only the PGM values 254, 0 and 205', set(raw) <= {254, 0, 205} and 0 in raw and 254 in raw)
pv = lib.preview('alpha', 64)
check('preview: max_px samples down (160x120 -> stride 3, 54x40)', pv['stride'] == 3 and (pv['width'], pv['height']) == (54, 40)
      and len(unz(pv['data'])) == 54 * 40, str((pv['stride'], pv['width'], pv['height'])))
w0, h0, pix0 = rb.read_pgm(open(os.path.join(mdir, 'alpha.pgm'), 'rb').read())
check('preview: row 0 is the top row of the PGM', unz(lib.preview('alpha', 1024)['data'])[:w0] == pix0[:w0])
check('preview: unknown map refused', raises(lib.preview, 'nothere') is not None)
check('preview: bad name refused', raises(lib.preview, '../alpha') is not None)

# rename
e = raises(lib.rename, 'alpha', 'beta')
check('rename: onto an existing map refused (exists:true), nothing moved', e is not None and e.extra.get('exists') is True
      and os.path.exists(os.path.join(mdir, 'alpha.pgm')))
open(os.path.join(mdir, 'gamma.data'), 'w').write('stray')
e = raises(lib.rename, 'alpha', 'gamma')
check('rename: onto an existing stray file of that name refused too', e is not None and os.path.exists(os.path.join(mdir, 'alpha.yaml')))
os.remove(os.path.join(mdir, 'gamma.data'))
check('rename: bad new names refused', all(raises(lib.rename, 'alpha', n) is not None for n in ('../x', 'a b', '', None, 'alpha')))
check('rename: unknown source refused', raises(lib.rename, 'zzz', 'yyy') is not None)
r = lib.rename('alpha', 'alpha2')
check('rename: reply {name}', r == {'name': 'alpha2'})
check('rename: all four files moved', all(os.path.exists(os.path.join(mdir, 'alpha2' + x)) for x in rb.MAP_EXTS)
      and not any(os.path.exists(os.path.join(mdir, 'alpha' + x)) for x in rb.MAP_EXTS))
ytxt = open(os.path.join(mdir, 'alpha2.yaml')).read()
check('rename: the YAML image line points at the new PGM, the rest is kept', 'image: alpha2.pgm' in ytxt and 'alpha.pgm' not in ytxt
      and rb.parse_map_yaml(ytxt)['resolution'] == 0.05 and 'origin:' in ytxt)
check('rename: the renamed map still previews', lib.preview('alpha2', 64)['width'] > 0)
busy = rb.MapLibrary(mdir, busy=lambda: 'alpha2')
check('rename and delete: refused for the map being saved', raises(busy.rename, 'alpha2', 'q') is not None and raises(busy.delete, 'alpha2', True) is not None
      and os.path.exists(os.path.join(mdir, 'alpha2.yaml')))

# delete
check('delete: needs confirm true (missing, false, text)', all(raises(lib.delete, 'alpha2', c) is not None for c in (None, False, 'true', 1)))
check('delete: nothing was removed without confirm', os.path.exists(os.path.join(mdir, 'alpha2.yaml')))
r = lib.delete('alpha2', True)
check('delete: removes every file and lists them', sorted(r['deleted']) == ['alpha2.data', 'alpha2.pgm', 'alpha2.posegraph', 'alpha2.yaml'], str(r))
check('delete: unknown map refused', raises(lib.delete, 'alpha2', True) is not None)
check('delete: the other map is untouched', [e['name'] for e in lib.list()] == ['beta'])

# path escape
open(os.path.join(OUT, 'x.yaml'), 'w').write('image: x.pgm\nresolution: 0.05\n')
for fn, args in ((lib.preview, ('../x',)), (lib.rename, ('beta', '../x')), (lib.rename, ('../x', 'zzz')), (lib.delete, ('../x', True)),
                 (lib.delete, ('..\\x', True)), (lib.preview, ('beta/../../x',))):
    check('path escape refused: %s%s' % (fn.__name__, args), raises(fn, *args) is not None)
check('path escape: the file outside is still there', os.path.exists(os.path.join(OUT, 'x.yaml')))
open(os.path.join(mdir, 'evil.yaml'), 'w').write('image: ../x.pgm\nresolution: 0.05\n')
open(os.path.join(OUT, 'x.pgm'), 'wb').write(b'P5\n1 1\n255\n\x00')
check('path escape: a YAML image outside the folder is not read (falls back to <name>.pgm, which is missing)', raises(lib.preview, 'evil') is not None)
try:
    link = os.path.join(mdir, 'linked.yaml')
    os.symlink(os.path.join(OUT, 'x.yaml'), link)
    sym = True
except (OSError, NotImplementedError, AttributeError):
    sym = False
if sym:
    check('path escape: a symlink out of the folder is refused', raises(lib.delete, 'linked', True) is not None and os.path.exists(os.path.join(OUT, 'x.yaml')))
else:
    print('SKIP symlink escape (no symlinks)')

# seed
sd = mkdir('seed_')
sl = rb.MapLibrary(os.path.join(sd, 'maps'))
check('seed: an empty library gets demo_room', sl.seed_demo() is True and [e['name'] for e in sl.list()] == ['demo_room'])
check('seed: not again when a map exists', sl.seed_demo() is False)
dm = sl.preview('demo_room', 1024)
dr = unz(dm['data'])
check('seed: the sample room is fully revealed (free and occupied, little unknown inside)', dr.count(0) > 300 and dr.count(254) > 4000)

# ================================================================ fake grid
fg = rb.FakeMapGrid(1.0)
check('fake grid: 0.05 m cells over the room plus 1 m margin (160 x 120)', (fg.width, fg.height) == (160, 120) and fg.origin == (-4.0, -3.0, 0.0))
check('fake grid: usable range grows 1 m to 12 m over 10 s', fg.usable_range(0) == 1.0 and abs(fg.usable_range(5) - 6.5) < 1e-9 and fg.usable_range(99) == 12.0)
check('fake grid: scaled time', rb.FakeMapGrid(0.2).usable_range(2.0) == 12.0)
check('fake grid: starts unknown', set(fg.snapshot()['cells']) == {255} and fg.snapshot()['seq'] == 0)
fg.cast(0.0, 0.0, 0.0, 1.0)
c1 = fg.snapshot()['cells']
fg.cast(0.0, 0.0, 0.0, 6.0)
c2 = fg.snapshot()['cells']
check('fake grid: more range reveals more cells', c2.count(255) < c1.count(255) < len(c1) and fg.snapshot()['seq'] == 2)
check('fake grid: a second identical cast changes nothing (seq stays)', fg.cast(0.0, 0.0, 0.0, 6.0) is False and fg.snapshot()['seq'] == 2)
fg.cast(0.0, 0.0, 0.0, 12.0)
cells = fg.snapshot()['cells']
ix = fg._index(-3.0, 0.0)
check('fake grid: the west wall is occupied where the beam hits', 100 in cells[ix - 2:ix + 3] or 100 in cells[ix - 2 * fg.width:ix + 3 * fg.width:fg.width], '')
check('fake grid: the cell at the robot is free', cells[fg._index(0.0, 0.0)] == 0)
# the box at x 1.0..1.4, y 0.3..0.7 hides what is behind it from (0, 0); another view reveals it
behind = fg._index(1.8, 0.6)
check('fake grid: the area behind the box is hidden from the centre', cells[behind] == 255, str(cells[behind]))
fg.cast(2.4, 0.0, 0.0, 12.0)
check('fake grid: driving reveals it', fg.snapshot()['cells'][behind] != 255)
pgm = fg.pgm_bytes()
wp, hp, pp = rb.read_pgm(pgm)
check('fake grid: P5 PGM 254 free / 0 occupied / 205 unknown, row 0 = top', (wp, hp) == (160, 120) and set(pp) <= {254, 0, 205} and len(pp) == 160 * 120
      and pp[:wp] == fg.snapshot()['cells'][-fg.width:].translate(bytes([254 if v < 50 else 0 if v <= 100 else 205 for v in range(256)])))
sv = mkdir('save_')
fg.save(os.path.join(sv, 'sub', 'm1'))
ym = rb.parse_map_yaml(open(os.path.join(sv, 'sub', 'm1.yaml')).read())
check('fake grid: save writes pgm, map_server yaml, posegraph, data',
      all(os.path.getsize(os.path.join(sv, 'sub', 'm1' + x)) > 0 for x in rb.MAP_EXTS) and ym['image'] == 'm1.pgm' and ym['resolution'] == 0.05
      and ym['origin'] == [-4.0, -3.0, 0.0] and ym['negate'] == 0 and ym['occupied_thresh'] == 0.65 and ym['free_thresh'] == 0.25
      and ym['mode'] == 'trinary')
fg2 = rb.FakeMapGrid(0.2)
fg2.begin(lambda: (0.0, 0.0, 0.0))
check('fake grid: begin() starts mapping and the map grows by itself', wait_for(lambda: fg2.snapshot()['seq'] >= 2, 2) and fg2.mapping())
fg2.end()
sq = fg2.snapshot()['seq']
time.sleep(0.3)
check('fake grid: end() stops it', fg2.snapshot()['seq'] == sq and not fg2.mapping())

# fake runner + probe, timers scaled
fros = rb.FakeRos()
frun = rb.FakeStackRunner(fros, scale=0.2)
fpro = rb.FakeProcessProbe(frun)
t0 = time.time()
ok, out = frun.run('start_stack.sh', ['map'], 5)
check('fake runner: start takes 1.5 s x scale and the probe sees SLAM', ok and 0.25 <= time.time() - t0 < 1.5 and fpro.running('slam.launch.py') and not fpro.running('nav2.launch.py'))
sv2 = mkdir('fsave_')
ok, out = frun.run('save_map.sh', [os.path.join(sv2, 'a')], 5)
check('fake runner: save writes real files', ok and os.path.exists(os.path.join(sv2, 'a.yaml')) and os.path.exists(os.path.join(sv2, 'a.pgm')))
ok, out = frun.run('save_map.sh', [os.path.join(sv2, 'a')], 5)
check('fake runner: save refuses an existing map like the script', ok is False and 'exists' in out)
ok, out = frun.run('save_map.sh', [os.path.join(sv2, 'a'), '--force'], 5)
check('fake runner: --force overwrites', ok)
ok, out = frun.run('stop_stack.sh', [], 5)
check('fake runner: stop ends SLAM', ok and not fpro.running('slam.launch.py'))
check('fake runner: save outside a mapping session fails', frun.run('save_map.sh', [os.path.join(sv2, 'b')], 5)[0] is False)
fros.shutdown()


# ================================================================ bridge in-process: handlers and the teleop refusal
class RecWriter:
    def __init__(self):
        self.evs = []
        self.lock = threading.Lock()

    def emit(self, obj, droppable=False):
        with self.lock:
            self.evs.append(obj)

    def of(self, kind):
        with self.lock:
            return [e for e in self.evs if e.get('ev') == kind]


bhome = mkdir('bridge_home_')
w = RecWriter()
ros = rb.FakeRos()
ros.docked = False
br = rb.Bridge(ros, w, bhome, True)
br.start_threads()
br.mapping.probe_period = 60
check('bridge: the fake home has the sample map', [e['name'] for e in br.maps.list()] == ['demo_room'])
check('bridge: mapping_status is idle', br.h_mapping_status({})['state'] == 'idle')
armed = br.h_teleop_arm({'on': True})
check('teleop: arming works while idle', armed['armed'] is True)
r = br.h_mapping_start({})
check('mapping_start: reply is MappingInfo state starting', r['state'] == 'starting' and 'maps_dir' in r)
check('mapping_start: driving was disarmed', br.tele['armed'] is False and any(e.get('armed') is False for e in w.of('teleop')))
try:
    br.h_teleop_arm({'on': True})
    msg = None
except rb.BridgeError as e:
    msg = str(e)
check('teleop: arming refused while mapping is starting, in words', msg == 'Mapping is starting; driving is blocked until it is ready.', str(msg))
check('teleop_refusal: names the state for saving and stopping', 'saving' in rb.MAPPING_BUSY_TEXT['saving'] and 'stopping' in rb.MAPPING_BUSY_TEXT['stopping'])
try:
    br.h_mapping_start({})
    refused = False
except rb.BridgeError:
    refused = True
check('mapping_start again: BridgeError', refused)
try:
    br.h_mapping_start({'keep_camera': 'yes'})
    refused = False
except rb.BridgeError:
    refused = True
check('mapping_start: bad keep_camera type refused', refused)
check('fake mapping reaches the mapping state', wait_for(lambda: br.mapping.state == 'mapping', 5))
check('teleop: arming works again once mapping', br.h_teleop_arm({'on': True})['armed'] is True)
br.h_mapping_save({'name': 'ip1'})
check('mapping_save: disarms driving', br.tele['armed'] is False)
try:
    br.h_teleop_arm({'on': True})
    msg = None
except rb.BridgeError as e:
    msg = str(e)
check('teleop: arming refused while saving', msg is not None and 'saving' in msg, str(msg))
wait_for(lambda: br.mapping.state == 'mapping', 5)
try:
    br.h_mapping_save({'name': 'ip1'})
    ex = None
except rb.BridgeError as e:
    ex = e
check('mapping_save: existing map -> BridgeError with exists:true', ex is not None and ex.extra.get('exists') is True)
for bad in ({'name': '../x'}, {'name': 5}, {}, {'name': 'ok', 'overwrite': 'yes'}):
    try:
        br.h_mapping_save(bad)
        refused = False
    except rb.BridgeError:
        refused = True
    check('mapping_save: bad arguments %r refused' % bad, refused)
try:
    br.h_map_delete({'name': 'ip1'})
    refused = False
except rb.BridgeError:
    refused = True
check('map_delete: refused without confirm', refused and os.path.exists(os.path.join(bhome, 'robot_code', 'maps', 'ip1.yaml')))
check('map_delete: with confirm', sorted(br.h_map_delete({'name': 'ip1', 'confirm': True})['deleted']) == ['ip1.data', 'ip1.pgm', 'ip1.posegraph', 'ip1.yaml'])
check('map_on: max_cells clamped, hz clamped', br.h_map_on({'hz': 99, 'max_cells': 5}) == {'hz': 2.0, 'max_cells': 10000}
      and br.h_map_on({'hz': 0, 'max_cells': 99999999}) == {'hz': 0.2, 'max_cells': 4000000} and br.h_map_on({}) == {'hz': 0.5, 'max_cells': 1000000})
try:
    br.h_map_on({'hz': 'fast'})
    refused = False
except rb.BridgeError:
    refused = True
check('map_on: text refused (hz)', refused)
check('map_off', br.h_map_off({}) == {} and br.streams['map'] is None)
br.h_mapping_stop({})
check('mapping_stop: ends idle', wait_for(lambda: br.mapping.state == 'idle', 5))
br.stop.set()
br.mapping.close()
ros.shutdown()

# ================================================================ the bridge as a subprocess (--fake)


class Proc:
    def __init__(self):
        self.home = mkdir('e2e_home_')
        env = dict(os.environ, STUDIO_BRIDGE_FAKE='1', STUDIO_BRIDGE_HOME=self.home, STUDIO_FAKE_MAP_SCALE='0.2',
                   PYTHONDONTWRITEBYTECODE='1')
        self.p = subprocess.Popen([sys.executable, '-u', BRIDGE, '--fake'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env)
        self.events = []
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

    def evs(self, kind):
        with self.lock:
            return [e for t, e in self.events if e.get('ev') == kind]

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


def known(ev):
    raw = unz(ev['data'])
    return len(raw) - raw.count(255), raw


b = Proc()
maps = os.path.join(b.home, 'robot_code', 'maps')
check('e2e: hello', wait_for(lambda: b.evs('hello'), 8) and b.evs('hello')[0]['fake'] is True)
r = b.send('maps_list')
check('e2e: maps_list shows demo_room (newest first, dir)', r and r['ok'] and [m['name'] for m in r['maps']] == ['demo_room']
      and r['dir'] == maps and r['maps'][0]['width'] == 160 and r['maps'][0]['height'] == 120, str(r))
r = b.send('mapping_status')
check('e2e: mapping_status idle, scripts ok', r and r['ok'] and r['state'] == 'idle' and r['scripts_ok'] is True and r['other_stack'] is None, str(r))
check('e2e: save while idle refused', b.send('mapping_save', name='early')['ok'] is False)
check('e2e: stop while idle refused', b.send('mapping_stop')['ok'] is False)
r = b.send('mapping_start')
check('e2e: mapping_start replies state starting', r and r['ok'] and r['state'] == 'starting', str(r))
check('e2e: mapping_start again refused', b.send('mapping_start')['ok'] is False)
check('e2e: events starting then mapping', wait_for(lambda: [e['state'] for e in b.evs('mapping')][-2:] == ['starting', 'mapping'], 6),
      str([e['state'] for e in b.evs('mapping')]))
r = b.send('map_on', hz=2)
check('e2e: map_on reply', r and r['ok'] and r['hz'] == 2.0 and r['max_cells'] == 1000000, str(r))
r2 = b.send('pose_on', hz=10)
check('e2e: pose_on', r2 and r2['ok'])
check('e2e: at least two map events', wait_for(lambda: len(b.evs('map')) >= 2, 6), str(len(b.evs('map'))))
me = b.evs('map')
m0 = me[0]
check('e2e: map event shape (design 4)', {'ev', 'seq', 't', 'width', 'height', 'resolution', 'origin', 'stride', 'encoding', 'data'} <= set(m0)
      and m0['encoding'] == 'cells' and m0['stride'] == 1 and m0['width'] == 160 and m0['height'] == 120 and m0['resolution'] == 0.05
      and m0['origin'] == {'x': -4.0, 'y': -3.0, 'yaw': 0.0} and len(unz(m0['data'])) == 160 * 120, str({k: v for k, v in m0.items() if k != 'data'}))
wait_for(lambda: len(b.evs('map')) >= 3, 4)
me = b.evs('map')
counts = [known(e)[0] for e in me]
check('e2e: the number of known cells grows between map events', len(counts) >= 2 and counts[-1] > counts[0] and counts == sorted(counts), str(counts))
check('e2e: seq grows', [e['seq'] for e in me] == sorted({e['seq'] for e in me}))
raw = known(me[-1])[1]
check('e2e: cells are 0..100 or 255', set(raw) <= set(range(101)) | {255} and 100 in raw and 0 in raw)
n_events = len(b.evs('map'))
time.sleep(1.2)
check('e2e: no map events when the map did not change (growth is over)', len(b.evs('map')) - n_events <= 2, '%d' % (len(b.evs('map')) - n_events))
wait_for(lambda: b.evs('pose'), 3)
pe = b.evs('pose')
check('e2e: pose events carry map {x, y, yaw, source}', pe and all(set(e['map']) == {'x', 'y', 'yaw', 'source'} and e['map']['source'] == 'slam' for e in pe[-3:])
      and abs(pe[-1]['map']['x'] - pe[-1]['x']) < 1e-6, str(pe[-1:]))

# save
b.send('map_off')
r = b.send('mapping_save', name='bad name')
check('e2e: save with a bad name refused', r and r['ok'] is False)
r = b.send('mapping_save', name='test1')
check('e2e: mapping_save replies state saving', r and r['ok'] and r['state'] == 'saving', str(r))
check('e2e: events saving then mapping with last_saved', wait_for(lambda: [e['state'] for e in b.evs('mapping')][-2:] == ['saving', 'mapping'], 6)
      and b.evs('mapping')[-1]['last_saved']['name'] == 'test1' and b.evs('mapping')[-1]['unsaved'] is False
      and b.evs('mapping')[-1]['result'] == {'op': 'save', 'ok': True, 'name': 'test1', 'output_tail': b.evs('mapping')[-1]['result']['output_tail']},
      str(b.evs('mapping')[-1:]))
check('e2e: the four files exist', all(os.path.exists(os.path.join(maps, 'test1' + x)) for x in rb.MAP_EXTS))
r = b.send('mapping_save', name='test1')
check('e2e: saving test1 again without overwrite gives exists:true', r and r['ok'] is False and r.get('exists') is True, str(r))
r = b.send('mapping_save', name='test1', overwrite=True)
check('e2e: with overwrite it saves again', r and r['ok'] and wait_for(lambda: [e['state'] for e in b.evs('mapping')][-2:] == ['saving', 'mapping'], 6))
r = b.send('maps_list')
check('e2e: maps_list now has test1 and demo_room, test1 first', r['ok'] and [m['name'] for m in r['maps']] == ['test1', 'demo_room'], str(r))
r = b.send('map_preview', name='test1', max_px=64)
rw = unz(r['data']) if r.get('ok') else b''
check('e2e: map_preview gray, sampled to the right size', r['ok'] and r['encoding'] == 'gray' and r['stride'] == 3 and (r['width'], r['height']) == (54, 40)
      and len(rw) == 54 * 40 and set(rw) <= {254, 0, 205}, str({k: v for k, v in r.items() if k != 'data'}))
check('e2e: map_preview unknown map refused', b.send('map_preview', name='nothere')['ok'] is False)
check('e2e: map_preview path escape refused', b.send('map_preview', name='../x')['ok'] is False)
r = b.send('map_rename', name='test1', new_name='demo_room')
check('e2e: rename onto an existing map refused', r['ok'] is False)
r = b.send('map_rename', name='test1', new_name='test2')
check('e2e: map_rename', r['ok'] and r['name'] == 'test2' and os.path.exists(os.path.join(maps, 'test2.yaml'))
      and not os.path.exists(os.path.join(maps, 'test1.yaml')) and 'image: test2.pgm' in open(os.path.join(maps, 'test2.yaml')).read(), str(r))
r = b.send('map_delete', name='test2')
check('e2e: map_delete without confirm refused', r['ok'] is False and os.path.exists(os.path.join(maps, 'test2.yaml')))
r = b.send('map_delete', name='test2', confirm=True)
check('e2e: map_delete with confirm', r['ok'] and len(r['deleted']) == 4 and not os.path.exists(os.path.join(maps, 'test2.yaml')), str(r))
r = b.send('mapping_stop')
check('e2e: mapping_stop replies state stopping', r and r['ok'] and r['state'] == 'stopping', str(r))
check('e2e: events stopping then idle', wait_for(lambda: [e['state'] for e in b.evs('mapping')][-2:] == ['stopping', 'idle'], 6))
check('e2e: stop result', b.evs('mapping')[-1]['result']['op'] == 'stop' and b.evs('mapping')[-1]['result']['ok'] is True)
r = b.send('mapping_status')
check('e2e: idle again, last_saved remembered, nothing unsaved', r['state'] == 'idle' and r['last_saved']['name'] == 'test1' and r['unsaved'] is False, str(r))
r = b.send('mapping_start')
wait_for(lambda: b.evs('mapping')[-1]['state'] == 'mapping', 6)
r = b.send('mapping_stop')
wait_for(lambda: b.evs('mapping')[-1]['state'] == 'idle', 6)
check('e2e: a second session starts and stops again', b.evs('mapping')[-1]['state'] == 'idle')
b.close()

shutil.rmtree(OUT, ignore_errors=True)
print('\n%d failure(s)' % fails)
sys.exit(fails)
