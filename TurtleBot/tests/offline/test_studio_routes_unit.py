"""Unit tests of the pure route helpers and RouteLibrary of the TurtleBot Studio robot bridge
(TurtleBot/tools/studio/robot_bridge.py, design in docs/DESIGN-MAPPING.md section 4, Routes).
No robot, no ROS. Symbolic-link checks are skipped where the OS does not allow links.
Usage: python test_studio_routes_unit.py     (prints PASS/FAIL, exit code = number of failures)
"""
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
sys.path.insert(0, STUDIO_DIR)
import robot_bridge as rb  # noqa: E402

fails = 0
OUT = tempfile.mkdtemp(prefix='tb4_routes_unit_')


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode(), flush=True)
    if not cond:
        fails += 1


def skip(name, why):
    print('SKIP %s  [%s]' % (name, why), flush=True)


def can_symlink():
    d = tempfile.mkdtemp(dir=OUT)
    try:
        os.mkdir(os.path.join(d, 't'))
        os.symlink('t', os.path.join(d, 'l'))
        return True
    except (OSError, NotImplementedError):
        return False


LINKS = can_symlink()
EXAMPLE = """version: 1
frame_id: map
map: "map.yaml"
dock_pose: {x: 0.050, y: 0.156, yaw: -31.6}
outbound:                      # the LAST pose is the pickup pose
  - {x: -0.550, y: 0.540, yaw: 157.5}
  - {x: -0.884, y: 0.673, yaw: 164.4}
inbound:                       # the LAST pose is the handoff pose in front of the dock, facing it
  - {x: -1.243, y: 0.714, yaw: -2.1}
settings:
  max_speed: 0.2
"""

# ---- count_waypoints
check('count_waypoints: the real example is 2 outbound and 1 inbound', rb.count_waypoints(EXAMPLE) == {'outbound': 2, 'inbound': 1}, str(rb.count_waypoints(EXAMPLE)))
check('count_waypoints: empty text', rb.count_waypoints('') == {'outbound': 0, 'inbound': 0})
check('count_waypoints: None', rb.count_waypoints(None) == {'outbound': 0, 'inbound': 0})
check('count_waypoints: empty lists', rb.count_waypoints('outbound: []\ninbound: []\n') == {'outbound': 0, 'inbound': 0})
check('count_waypoints: items under other keys are not counted',
      rb.count_waypoints('outbound:\n  - {x: 1, y: 2, yaw: 0}\nextras:\n  - {x: 9, y: 9, yaw: 9}\ninbound:\n  - {x: 3, y: 4, yaw: 0}\n') == {'outbound': 1, 'inbound': 1})
check('count_waypoints: commented items and CRLF',
      rb.count_waypoints('outbound:\r\n  # - {x: 1}\r\n  - {x: 1, y: 2, yaw: 0}\r\n') == {'outbound': 1, 'inbound': 0})
check('count_waypoints: items before any section are not counted', rb.count_waypoints('  - {x: 1}\ninbound:\n') == {'outbound': 0, 'inbound': 0})

# ---- route_missing
check('route_missing: all present', rb.route_missing(list(rb.ROUTE_REQUIRED) + ['map.pgm']) == [])
check('route_missing: nothing present', rb.route_missing([]) == list(rb.ROUTE_REQUIRED))
check('route_missing: names the absent ones in order', rb.route_missing(['route.yaml', 'speed_mask.yaml']) == ['map.yaml', 'keepout_mask.yaml'])
check('route_missing: None', rb.route_missing(None) == list(rb.ROUTE_REQUIRED))


def new_routes():
    d = tempfile.mkdtemp(dir=OUT)
    for n in ('home', 'other'):
        os.mkdir(os.path.join(d, n))
    return d


# ---- read_current / write_current
d = new_routes()
check('read_current: no current at all', rb.read_current(d) == (None, False))
if LINKS:
    rb.write_current(d, 'home', False)
    check('write_current: makes a link to home', os.path.islink(os.path.join(d, 'current')) and rb.read_current(d) == ('home', True), str(rb.read_current(d)))
    rb.write_current(d, 'other', False)
    check('write_current: replaces the link', rb.read_current(d) == ('other', True), str(rb.read_current(d)))
    check('write_current: no temporary link is left', [f for f in os.listdir(d) if f.startswith('.current.tmp')] == [])
    shutil.rmtree(os.path.join(d, 'other'))
    check('read_current: a link to a missing folder is not ok', rb.read_current(d) == ('other', False), str(rb.read_current(d)))
else:
    skip('write_current/read_current with real links', 'no symbolic links here')

d = new_routes()
rb.write_current(d, 'home', True)
check('write_current (fake): current is readable afterwards', rb.read_current(d) == ('home', True), str(rb.read_current(d)))
rb.write_current(d, 'other', True)
check('write_current (fake): can be changed', rb.read_current(d) == ('other', True), str(rb.read_current(d)))
if not LINKS:
    check('write_current (fake, no links): the target is in .current_fake', os.path.isfile(os.path.join(d, '.current_fake')))

if not LINKS:
    d = new_routes()
    try:
        rb.write_current(d, 'home', False)
        check('write_current (real, no links) raises instead of faking', False)
    except OSError:
        check('write_current (real, no links) raises instead of faking', True)

d = new_routes()
os.mkdir(os.path.join(d, 'current'))
open(os.path.join(d, 'current', 'keep.txt'), 'w').write('x')
for fake in (False, True):
    try:
        rb.write_current(d, 'home', fake)
        refused = False
    except ValueError:
        refused = True
    check('write_current refuses when current is a real folder (fake=%s)' % fake, refused)
check('write_current leaves that folder and its file alone', os.path.isfile(os.path.join(d, 'current', 'keep.txt')))
check('read_current: a real folder named current is not a link target', rb.read_current(d) == (None, False))

# ---- tail_text_lines
f = os.path.join(OUT, 'menu.log')
check('tail_text_lines: missing file', rb.tail_text_lines(os.path.join(OUT, 'nope.log'), 5) == [])
with open(f, 'w') as fh:
    fh.write('\n'.join('line %d' % i for i in range(10)) + '\n\n')
check('tail_text_lines: the last n lines', rb.tail_text_lines(f, 3) == ['line 7', 'line 8', 'line 9'], str(rb.tail_text_lines(f, 3)))
check('tail_text_lines: fewer lines than asked', len(rb.tail_text_lines(f, 50)) == 10)
with open(f, 'w') as fh:
    fh.write('x' * 1000 + '\n')
check('tail_text_lines: long lines are cut', len(rb.tail_text_lines(f, 1)[0]) == 300)

# ---- RouteLibrary with a scripted probe


class Probe(rb.ProcessProbe):
    def __init__(self):
        self.on = set()

    def running(self, pattern):
        return pattern in self.on


home = tempfile.mkdtemp(dir=OUT)
routes = os.path.join(home, 'robot_code', 'routes')
for n in ('good', 'bad'):
    os.makedirs(os.path.join(routes, n))
for fname in rb.ROUTE_REQUIRED:
    open(os.path.join(routes, 'good', fname), 'w').write(EXAMPLE if fname == 'route.yaml' else 'x: 1\n')
open(os.path.join(routes, 'bad', 'route.yaml'), 'w').write('version: 1\n')
open(os.path.join(routes, 'stray.txt'), 'w').write('x')
os.makedirs(os.path.join(routes, '.hidden'))
pr = Probe()
lib = rb.RouteLibrary(home, True, pr)
r = lib.list()
check('list: sorted routes, no files, no dot folders', [x['name'] for x in r['routes']] == ['bad', 'good'], str([x['name'] for x in r['routes']]))
check('list: valid and missing', r['routes'][1]['valid'] is True and r['routes'][0]['missing'] == ['map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml'])
check('list: waypoints from route.yaml', r['routes'][1]['waypoints'] == {'outbound': 2, 'inbound': 1})
check('list: no current yet', r['current'] is None and r['current_ok'] is False)


def err(fn, *a):
    try:
        fn(*a)
    except rb.ServiceError as e:
        return str(e)
    return None


check('set_current: needs confirm', err(lib.set_current, 'good', None) is not None and err(lib.set_current, 'good', 'yes') is not None)
check('set_current: bad names', all(err(lib.set_current, n, True) for n in ('../good', 'good/..', '', None, '.hidden', 'a b')))
check('set_current: no such folder', err(lib.set_current, 'nope', True) is not None)
e = err(lib.set_current, 'bad', True)
check('set_current: invalid folder names the missing files', e is not None and 'missing' in e and 'speed_mask.yaml' in e, str(e))
pr.on = {'delivery_mission.py'}
e = err(lib.set_current, 'good', True)
check('set_current: refused while a trip runs', e is not None and 'trip' in e, str(e))
pr.on = {'nav2.launch.py'}
check('set_current: refused while the navigation stack runs', err(lib.set_current, 'good', True) is not None)
pr.on = set()
check('nothing changed after the refusals', lib.list()['current'] is None)
check('set_current: works', lib.set_current('good', True) == {'current': 'good'} and lib.list()['current'] == 'good' and lib.list()['current_ok'] is True)

# trip_status
t = lib.trip_status()
check('trip_status: no log file gives no lines', t['lines'] == [] and t['log_path'].replace('\\', '/').endswith('logs/delivery/menu.log'))
pr.on = {'delivery_menu.py', 'localization.launch.py'}
t = lib.trip_status()
check('trip_status: flags follow the processes', t['menu_running'] is True and t['mission_running'] is False and t['stack_running'] is True)
os.makedirs(os.path.dirname(lib.log_path))
with open(lib.log_path, 'w') as fh:
    fh.write('a\nb\nc\n')
check('trip_status: lines', lib.trip_status(2)['lines'] == ['b', 'c'])

# fake seeding
fh_home = tempfile.mkdtemp(dir=OUT)
fl = rb.RouteLibrary(fh_home, True, rb.FakeTripProbe())
check('seed_fake: seeds once', fl.seed_fake() is True and fl.seed_fake() is False)
r = fl.list()
check('seed_fake: home and route1 valid, current home', [x['name'] for x in r['routes']] == ['home', 'route1'] and all(x['valid'] for x in r['routes'])
      and r['current'] == 'home' and r['current_ok'] is True, str(r))
check('seed_fake: home has 2 outbound and 1 inbound', r['routes'][0]['waypoints'] == {'outbound': 2, 'inbound': 1})
check('seed_fake: map.pgm is a P5 file', open(os.path.join(fl.dir, 'home', 'map.pgm'), 'rb').read(2) == b'P5')
check('seed_fake: menu log lines', len(fl.trip_status()['lines']) >= 3)

shutil.rmtree(OUT, ignore_errors=True)
print('\n%d failure(s)' % fails)
sys.exit(fails)
