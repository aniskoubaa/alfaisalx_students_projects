"""Failure scenarios for TurtleBot Studio that the other offline tests do not reach (found with coverage.py, see
TurtleBot/tools/studio/docs/TESTING.md). Each check asserts what is left behind after a failure: the current-route link,
a map that was being renamed, the menu file, a half uploaded route, a zip of a map.

No robot, no ssh, no ROS and no subprocess: the robot bridge services and the Studio object are used in this process
with temporary folders and small stand-ins for the parts that need a robot.
Usage: python test_studio_gaps.py     (prints PASS/FAIL, exit code = number of failures)
"""
import base64
import io
import os
import shutil
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
sys.path.insert(0, STUDIO_DIR)
import robot_bridge as rb  # noqa: E402
import studio as st  # noqa: E402

OUT = tempfile.mkdtemp(prefix='tb4_studio_gaps_')
fails = 0
ROUTE_FILES = ('route.yaml', 'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml')


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode(), flush=True)
    if not cond:
        fails += 1


def refuses(fn, *a, exc=rb.ServiceError, **kw):
    """The message of the refusal, or None when fn did not refuse."""
    try:
        fn(*a, **kw)
    except exc as e:
        return str(e)
    return None


def can_link():
    d = tempfile.mkdtemp(dir=OUT)
    try:
        os.symlink('x', os.path.join(d, 'l'))
        return True
    except (OSError, NotImplementedError):
        return False


LINKS = can_link()
if not LINKS:
    print('NOTE symbolic links are not available here (Windows without developer mode): link checks use the fake file only')


class Probe(rb.ProcessProbe):
    def __init__(self):
        self.on = set()

    def running(self, pattern):
        return pattern in self.on


def make_routes(names=('home', 'route1')):
    home = tempfile.mkdtemp(dir=OUT)
    routes = os.path.join(home, 'robot_code', 'routes')
    for n in names:
        os.makedirs(os.path.join(routes, n))
        for f in ROUTE_FILES:
            with open(os.path.join(routes, n, f), 'w') as fh:
                fh.write('x: 1\n')
    return home, routes


# ================================================================ current route link (write_current, read_current)
home, routes = make_routes()
rb.write_current(routes, 'home', True)
check('current: written, then read back as valid', rb.read_current(routes) == ('home', True))
rb.write_current(routes, 'route1', True)
check('current: replaced by another route', rb.read_current(routes) == ('route1', True))

# A real folder named current is never deleted or replaced.
home2, routes2 = make_routes()
os.makedirs(os.path.join(routes2, 'current'))
with open(os.path.join(routes2, 'current', 'keep.txt'), 'w') as f:
    f.write('mine')
msg = refuses(rb.write_current, routes2, 'home', True, exc=ValueError)
check('current: refuses to replace a real folder', msg is not None and 'real folder' in msg, str(msg))
check('current: the real folder and its file are untouched', os.path.isfile(os.path.join(routes2, 'current', 'keep.txt')))

# When links cannot be made: the real robot reports it and keeps the old route; the fake robot uses its name file.
home3, routes3 = make_routes()
rb.write_current(routes3, 'home', True)
real_symlink = os.symlink


def no_symlink(*a, **k):
    raise OSError('links not allowed')


os.symlink = no_symlink
try:
    err = refuses(rb.write_current, routes3, 'route1', False, exc=OSError)
    check('current: without links a real robot raises and keeps the old route', err is not None and rb.read_current(routes3)[0] == 'home', str(err))
    rb.write_current(routes3, 'route1', True)
    check('current: without links the fake robot keeps the name in .current_fake',
          open(os.path.join(routes3, rb.ROUTE_FAKE_CURRENT)).read().strip() == 'route1')
finally:
    os.symlink = real_symlink
check('current: the fake name file replaces a link and is read back', rb.read_current(routes3) == ('route1', True), str(rb.read_current(routes3)))
if LINKS:
    rb.write_current(routes3, 'home', True)
    check('current: a real link replaces the fake name file', rb.read_current(routes3) == ('home', True)
          and not os.path.exists(os.path.join(routes3, rb.ROUTE_FAKE_CURRENT)))

# If the final rename fails the temporary link is removed and the old route stays.
home4, routes4 = make_routes()
rb.write_current(routes4, 'home', True)
real_replace = os.replace


def bad_replace(a, b):
    raise OSError('disk full')


os.replace = bad_replace
try:
    err = refuses(rb.write_current, routes4, 'route1', True, exc=OSError)
finally:
    os.replace = real_replace
check('current: a failed rename raises', err is not None, str(err))
check('current: a failed rename keeps the old route and leaves no temporary link',
      rb.read_current(routes4)[0] == 'home' and not [n for n in os.listdir(routes4) if n.startswith('.current.tmp')], str(os.listdir(routes4)))

# read_current on odd states
home5, routes5 = make_routes(('only',))
check('read_current: nothing set gives (None, False)', rb.read_current(routes5) == (None, False))
with open(os.path.join(routes5, rb.ROUTE_FAKE_CURRENT), 'w') as f:
    f.write('gone\n')
check('read_current: a name whose folder is missing is not ok', rb.read_current(routes5) == ('gone', False))
with open(os.path.join(routes5, rb.ROUTE_FAKE_CURRENT), 'w') as f:
    f.write('../etc\n')
check('read_current: an invalid name is never ok', rb.read_current(routes5) == ('../etc', False))
os.makedirs(os.path.join(routes5, 'current'))
check('read_current: a real folder named current is not a link, so no name', rb.read_current(routes5) == (None, False))

# ================================================================ set_current refusals leave the link alone
home, routes = make_routes()
pr = Probe()
lib = rb.RouteLibrary(home, True, pr)
os.makedirs(os.path.join(routes, 'partial'))
with open(os.path.join(routes, 'partial', 'route.yaml'), 'w') as f:
    f.write('version: 1\n')
lib.set_current('home', True)
cases = [
    ('confirm is the text yes, not True', lambda: lib.set_current('route1', 'yes')),
    ('confirm missing (None)', lambda: lib.set_current('route1', None)),
    ('the name current', lambda: lib.set_current('current', True)),
    ('a hidden name', lambda: lib.set_current('.upload-x', True)),
    ('a path with ..', lambda: lib.set_current('../route1', True)),
    ('a route that does not exist', lambda: lib.set_current('nope', True)),
    ('an incomplete route', lambda: lib.set_current('partial', True)),
]
for label, fn in cases:
    m = refuses(fn)
    check('set_current refuses %s' % label, m is not None and lib.list()['current'] == 'home', str(m))
pr.on = {rb.ROUTE_MISSION_PATTERN}
m = refuses(lib.set_current, 'route1', True)
check('set_current refuses while a trip runs', m is not None and 'trip is running' in m and lib.list()['current'] == 'home', str(m))
pr.on = {rb.ROUTE_STACK_PATTERNS[0]}
m = refuses(lib.set_current, 'route1', True)
check('set_current refuses while the navigation stack runs', m is not None and 'navigation stack' in m and lib.list()['current'] == 'home', str(m))
pr.on = set()
check('set_current works when nothing runs', lib.set_current('route1', True) == {'current': 'route1'} and lib.list()['current'] == 'route1')

# ================================================================ upload finish and cleanup on the robot
home, routes = make_routes(('taken',))
lib = rb.RouteLibrary(home, True, Probe())
os.makedirs(os.path.join(routes, '.upload-taken'))
m = None
try:
    lib.upload_finish('taken')
except rb.ServiceError as e:
    m = e
check('upload_finish: never replaces an existing route (exists flag set)', m is not None and m.extra.get('exists') is True
      and os.path.isdir(os.path.join(routes, 'taken')) and os.path.isfile(os.path.join(routes, 'taken', 'route.yaml')))
check('upload_finish: no upload folder is a refusal', refuses(lib.upload_finish, 'fresh') is not None
      and not os.path.exists(os.path.join(routes, 'fresh')))
os.makedirs(os.path.join(routes, '.upload-fresh'))
for f in ROUTE_FILES:
    open(os.path.join(routes, '.upload-fresh', f), 'w').write('y: 2\n')
r = lib.upload_finish('fresh')
check('upload_finish: the upload folder becomes the route in one rename', r['route']['name'] == 'fresh' and r['route']['valid']
      and not os.path.exists(os.path.join(routes, '.upload-fresh')))
check('upload_finish: reserved and path names are refused', all(refuses(lib.upload_finish, n) for n in ('current', '..', 'a/b', '.hidden')))

with open(os.path.join(routes, '.upload-file'), 'w') as f:
    f.write('not a folder')
m = refuses(lib.upload_cleanup, 'file')
check('upload_cleanup: a plain file is refused and kept', m is not None and os.path.isfile(os.path.join(routes, '.upload-file')), str(m))
if LINKS:
    outside = tempfile.mkdtemp(dir=OUT)
    with open(os.path.join(outside, 'precious.txt'), 'w') as f:
        f.write('keep')
    os.symlink(outside, os.path.join(routes, '.upload-evil'))
    r = lib.upload_cleanup('evil')
    check('upload_cleanup: a link is removed and never followed', not os.path.lexists(os.path.join(routes, '.upload-evil'))
          and os.path.isfile(os.path.join(outside, 'precious.txt')) and r == {'exists': False}, str(r))
    os.symlink(outside, os.path.join(routes, '.upload-linked'))
    m = refuses(lib.upload_finish, 'linked')
    check('upload_finish: an upload folder that is a link is refused', m is not None and not os.path.exists(os.path.join(routes, 'linked')), str(m))

# ================================================================ map rename that fails halfway
mdir = tempfile.mkdtemp(dir=OUT)
for ext in rb.MAP_EXTS:
    with open(os.path.join(mdir, 'old' + ext), 'w') as f:
        f.write('image: old.pgm\nresolution: 0.05\n' if ext == '.yaml' else 'data' + ext)
ml = rb.MapLibrary(mdir)
real_rename = os.rename
calls = {'n': 0}


def flaky_rename(a, b):
    calls['n'] += 1
    if calls['n'] == 3:
        raise OSError('disk error')
    return real_rename(a, b)


os.rename = flaky_rename
try:
    m = refuses(ml.rename, 'old', 'new')
finally:
    os.rename = real_rename
check('rename: a failure on the third file is reported', m is not None and 'Rename failed' in m, str(m))
check('rename: every file is back under the old name', all(os.path.isfile(os.path.join(mdir, 'old' + e)) for e in rb.MAP_EXTS)
      and not any(os.path.exists(os.path.join(mdir, 'new' + e)) for e in rb.MAP_EXTS), str(sorted(os.listdir(mdir))))
check('rename: the old YAML still names the old image', 'image: old.pgm' in open(os.path.join(mdir, 'old.yaml')).read())
check('rename: after the failure the same rename works', ml.rename('old', 'new') == {'name': 'new'}
      and 'image: new.pgm' in open(os.path.join(mdir, 'new.yaml')).read() and not os.path.exists(os.path.join(mdir, 'old.pgm')))
with open(os.path.join(mdir, 'other.yaml'), 'w') as f:
    f.write('image: other.pgm\nresolution: 0.05\n')
m = None
try:
    ml.rename('new', 'other')
except rb.ServiceError as e:
    m = e
check('rename: onto an existing map is refused with the exists flag and changes nothing', m is not None and m.extra.get('exists') is True
      and os.path.isfile(os.path.join(mdir, 'new.pgm')))
busy = rb.MapLibrary(mdir, busy=lambda: 'new')
check('rename: a map that is being saved is refused', refuses(busy.rename, 'new', 'fresh') is not None and os.path.isfile(os.path.join(mdir, 'new.pgm')))

# ================================================================ menu save failures
home = tempfile.mkdtemp(dir=OUT)


class Checker:
    def __init__(self, ok=True):
        self.ok = ok

    def checker_ok(self):
        return True

    def check_file(self, path):
        return {'ok': self.ok, 'errors': [] if self.ok else ['bad entry'], 'warnings': []}


svc = rb.MenuService(home, Checker(True))
mpath = os.path.join(home, 'robot_code', 'menu', 'menu.yaml')
os.makedirs(os.path.dirname(mpath))
with open(mpath, 'w') as f:
    f.write('version: 1\n# original\n')
# A folder where the temporary file must go makes the write fail.
os.makedirs(mpath + '.tmp')
m = refuses(svc.put, 'version: 1\n# new\n', True)
check('menu put: a write failure is reported', m is not None and 'cannot save' in m, str(m))
check('menu put: the old menu file is unchanged after a write failure', open(mpath).read() == 'version: 1\n# original\n')
shutil.rmtree(mpath + '.tmp')
check('menu put: confirm must be True', refuses(rb.MenuService(home, Checker(True)).put, 'version: 1\n', 'true') is not None
      and open(mpath).read() == 'version: 1\n# original\n')
bad = rb.MenuService(home, Checker(False))
m = refuses(bad.put, 'version: 1\n# bad\n', True)
check('menu put: a text the checker rejects is not saved', m is not None and open(mpath).read() == 'version: 1\n# original\n', str(m))
check('menu put: a text over the size limit is refused before the checker', refuses(svc.put, 'x' * (rb.MENU_MAX_CHARS + 1), True) is not None)
check('menu put: good text is saved with a .bak of the old file', svc.put('version: 1\n# new\n', True)['path'] == mpath
      and open(mpath).read() == 'version: 1\n# new\n' and open(mpath + '.bak').read() == 'version: 1\n# original\n')

# the checker program: timeout and missing program
cdir = tempfile.mkdtemp(dir=OUT)
script = os.path.join(cdir, 'slow_checker.py')
with open(script, 'w') as f:
    f.write('import time\ntime.sleep(30)\n')
old_to = rb.MENU_CHECK_TIMEOUT
rb.MENU_CHECK_TIMEOUT = 0.5
try:
    m = refuses(rb.MenuChecker(cdir, script).check_file, os.path.join(cdir, 'x.yaml'))
finally:
    rb.MENU_CHECK_TIMEOUT = old_to
check('menu checker: a checker that never answers is a refusal that names the timeout', m is not None and 'timed out' in m, str(m))
m = refuses(rb.MenuChecker(cdir, os.path.join(cdir, 'missing.py')).check_file, os.path.join(cdir, 'x.yaml'))
check('menu checker: a missing checker program is a refusal that says where it looked', m is not None and 'missing.py' in m, str(m))
with open(script, 'w') as f:
    f.write('import sys\nsys.stderr.write("boom\\n")\nsys.exit(3)\n')
m = refuses(rb.MenuChecker(cdir, script).check_file, os.path.join(cdir, 'x.yaml'))
check('menu checker: an exit code other than 0 or 1 is a failure with its message, not a verdict', m is not None and 'boom' in m, str(m))

# ================================================================ route upload validation (desktop side)


def b64(data=b'x'):
    return base64.b64encode(data).decode()


def good_files():
    return [{'path': n, 'data_b64': b64()} for n in ROUTE_FILES]


ok, info = st.validate_route_upload('trip1', good_files())
check('validate_route_upload: a complete folder is accepted with its bytes', ok and sorted(r for r, _ in info) == sorted(ROUTE_FILES))
bad_cases = [
    ('a name with a space', ('my route', good_files())),
    ('the name current', ('current', good_files())),
    ('a name starting with a dot', ('.x', good_files())),
    ('a name of 49 characters', ('a' * 49, good_files())),
    ('no files', ('trip1', [])),
    ('65 files', ('trip1', good_files() + [{'path': 'f%d.txt' % i, 'data_b64': b64()} for i in range(61)])),
    ('a file without data', ('trip1', good_files() + [{'path': 'extra.txt'}])),
    ('a path with a folder', ('trip1', good_files() + [{'path': 'sub/extra.txt', 'data_b64': b64()}])),
    ('a path with backslash', ('trip1', good_files() + [{'path': 'sub\\extra.txt', 'data_b64': b64()}])),
    ('a path with ..', ('trip1', good_files() + [{'path': '..x', 'data_b64': b64()}])),
    ('a name with .. in the middle', ('trip1', good_files() + [{'path': 'a..b', 'data_b64': b64()}])),
    ('a hidden file', ('trip1', good_files() + [{'path': '.DS_Store', 'data_b64': b64()}])),
    ('a duplicate file', ('trip1', good_files() + [{'path': 'route.yaml', 'data_b64': b64()}])),
    ('base64 with junk characters', ('trip1', good_files() + [{'path': 'extra.txt', 'data_b64': '!!!'}])),
    ('a missing required file', ('trip1', good_files()[:-1])),
]
for label, (n, fl) in bad_cases:
    ok, info = st.validate_route_upload(n, fl)
    check('validate_route_upload refuses %s' % label, ok is False and isinstance(info, str) and info, str(info))
big = good_files()[:3] + [{'path': 'speed_mask.yaml', 'data_b64': b64(b'\0' * (st.ROUTE_UPLOAD_MAX + 1))}]
ok, info = st.validate_route_upload('trip1', big)
check('validate_route_upload refuses a folder over the size limit', ok is False and 'too large' in info, str(info))
ok, info = st.validate_route_upload('trip1', good_files() + [{'path': 'a.pgm', 'data_b64': b64(b'\0' * (st.ROUTE_UPLOAD_MAX // 2))},
                                                             {'path': 'b.pgm', 'data_b64': b64(b'\0' * (st.ROUTE_UPLOAD_MAX // 2 + 10))}])
check('validate_route_upload: the limit is the total, not per file', ok is False and 'too large' in info, str(info))

# ================================================================ Studio.route_upload / map_download_zip with a stand-in bridge
args = st.parse_args(['--fake', '--no-browser', '--config-dir', os.path.join(OUT, 'cfg'), '--fake-home', os.path.join(OUT, 'fh')])
app = st.Studio(args)


class StubBridge:
    """Answers bridge commands from a table; records every command."""

    def __init__(self, table):
        self.table, self.sent = table, []

    def request(self, cmd, timeout=10):
        self.sent.append(cmd['cmd'])
        a = self.table[cmd['cmd']]
        if isinstance(a, Exception):
            raise a
        return a(cmd) if callable(a) else a


uploads = []
app._upload = lambda local, remote, rels: uploads.append((remote, sorted(rels), sorted(os.listdir(local))))
body = {'name': 'trip9', 'files': good_files()}
app.bridge = StubBridge({'route_upload_cleanup': {'ok': True, 'exists': False},
                         'route_upload_finish': {'ok': True, 'route': {'name': 'trip9', 'valid': True}}})
r = app.route_upload(body)
check('route_upload: good upload sends the files to the hidden folder, then finishes', r.get('ok') is True and uploads
      and uploads[0][0].endswith('/.upload-trip9') and uploads[0][1] == sorted(ROUTE_FILES) and app.bridge.sent == ['route_upload_cleanup', 'route_upload_finish'], str(r))
uploads.clear()
app.bridge = StubBridge({'route_upload_cleanup': {'ok': True, 'exists': True}})
r = app.route_upload(body)
check('route_upload: an existing route stops before any file is copied', r.get('ok') is False and r.get('exists') is True and not uploads and app.bridge.sent == ['route_upload_cleanup'], str(r))
app.bridge = StubBridge({'route_upload_cleanup': {'ok': True, 'exists': False},
                         'route_upload_finish': {'ok': False, 'error': 'A route named trip9 already exists.', 'exists': True}})
r = app.route_upload(body)
check('route_upload: a refused finish is passed on with exists and the hidden folder is cleaned',
      r.get('ok') is False and r.get('exists') is True and app.bridge.sent == ['route_upload_cleanup', 'route_upload_finish', 'route_upload_cleanup'], str(r))


def boom(*a):
    raise st.BridgeError('upload failed: link lost')


app._upload = boom
app.bridge = StubBridge({'route_upload_cleanup': {'ok': True, 'exists': False}, 'route_upload_finish': {'ok': True}})
r = app.route_upload(body)
check('route_upload: a copy that fails reports it, never finishes, and cleans the hidden folder',
      r.get('ok') is False and 'link lost' in r.get('error', '') and app.bridge.sent == ['route_upload_cleanup', 'route_upload_cleanup'], str(r))
app.bridge = StubBridge({})
r = app.route_upload({'name': 'bad name', 'files': good_files()})
check('route_upload: an invalid request never reaches the robot', r.get('ok') is False and app.bridge.sent == [], str(r))

# map download
maps_reply = {'ok': True, 'maps': [{'name': 'lab', 'files': {'pgm': 10, 'yaml': 5, 'posegraph': None, 'data': None}},
                                   {'name': 'empty', 'files': {'pgm': None, 'yaml': None}}]}
app.bridge = StubBridge({'maps_list': maps_reply})
check('map zip: a bad name is 400', app.map_download_zip('../x')[0] == 400)
check('map zip: an unknown map is 404', app.map_download_zip('nope')[0] == 404)
check('map zip: a map with no files is 404', app.map_download_zip('empty')[0] == 404)
app.bridge = StubBridge({'maps_list': {'ok': False, 'error': 'robot busy'}})
s, b, ct = app.map_download_zip('lab')
check('map zip: a refusal by the robot is 502 with its message', s == 502 and b['error'] == 'robot busy')
app.bridge = StubBridge({'maps_list': st.BridgeError('not connected')})
check('map zip: no connection is 409', app.map_download_zip('lab')[0] == 409)
app.bridge = StubBridge({'maps_list': maps_reply})
seen_dirs = []


def fail_download(tmp, remote, rels):
    seen_dirs.append(tmp)
    raise st.BridgeError('copy failed')


app._download = fail_download
s, b, ct = app.map_download_zip('lab')
check('map zip: a failed copy is 502 and the temporary folder is removed', s == 502 and 'copy failed' in b['error'] and seen_dirs and not os.path.exists(seen_dirs[0]), str(b))


def part_download(tmp, remote, rels):
    seen_dirs.append(tmp)
    assert remote == st.MAP_REMOTE_DIR and rels == ['lab.pgm', 'lab.yaml'], (remote, rels)
    with open(os.path.join(tmp, 'lab.pgm'), 'wb') as f:
        f.write(b'P5 pgm')
    # lab.yaml did not arrive: the zip holds only what arrived


app._download = part_download
s, b, ct = app.map_download_zip('lab')
names = zipfile.ZipFile(io.BytesIO(b)).namelist() if s == 200 else []
check('map zip: only the files that arrived are zipped, asked for exactly the files the robot listed', s == 200 and ct == 'application/zip'
      and names == ['lab.pgm'] and not os.path.exists(seen_dirs[-1]), str(names))

# map preview with a bad answer
app.bridge = StubBridge({'map_preview': {'ok': True, 'width': 4, 'height': 4, 'encoding': 'gray', 'data': 'not base64 !'}})
s, b, ct = app.map_preview_png('lab', 256)
check('map preview: a corrupt picture from the robot is 502, not a crash', s == 502 and 'bad preview' in b['error'], str(b))
app.bridge = StubBridge({'map_preview': {'ok': False, 'error': 'There is no map named lab.'}})
check('map preview: "no map named" is 404', app.map_preview_png('lab', 256)[0] == 404)
app.bridge = StubBridge({})
check('map preview: a bad name is 400 and the robot is not asked', app.map_preview_png('a b', 256)[0] == 400 and app.bridge.sent == [])


# ================================================================ manual driving: why arming is refused (teleop_refusal)


class StubRos:
    available = True
    error = None

    def __init__(self):
        self.docked = False
        self.percent = 80.0

    def is_docked(self):
        return self.docked

    def snapshot(self):
        return {'battery': {'percent': self.percent}}


class Alive:
    def poll(self):
        return None


bhome = tempfile.mkdtemp(dir=OUT)
ros = StubRos()
bridge = rb.Bridge(ros, lambda m: None, bhome, True)
check('teleop: nothing in the way gives no refusal', bridge.teleop_refusal() is None)
open(os.path.join(bhome, 'STOP'), 'w').close()
check('teleop: the STOP file refuses', 'e-stop' in (bridge.teleop_refusal() or ''))
os.remove(os.path.join(bhome, 'STOP'))
bridge.estop_on = True
check('teleop: an active e-stop refuses', 'e-stop' in (bridge.teleop_refusal() or ''))
bridge.estop_on = None
ros.available, ros.error = False, 'no rclpy'
check('teleop: ROS not ready refuses and says why', 'no rclpy' in (bridge.teleop_refusal() or ''))
ros.available, ros.error = True, None
for state in ('starting', 'saving', 'stopping'):
    bridge.mapping = type('M', (), {'state': state})()
    check('teleop: mapping %s refuses' % state, 'Mapping' in (bridge.teleop_refusal() or ''))
bridge.mapping = type('M', (), {'state': 'mapping'})()
check('teleop: plain mapping does not refuse (driving while mapping is allowed)', bridge.teleop_refusal() is None)
bridge.mapping = None
ros.docked = True
check('teleop: docked refuses', 'docked' in (bridge.teleop_refusal() or ''))
ros.docked = None
check('teleop: unknown dock state refuses (never guessed)', 'not known' in (bridge.teleop_refusal() or ''))
ros.docked = False
bridge.runs['r1'] = rb.Run('r1', 'motion_shapes.py', 1, 'log', 'motion_shapes.py', 0.0, True, proc=Alive())
check('teleop: a running motion program refuses', 'motion program' in (bridge.teleop_refusal() or ''))
bridge.runs['r1'].motion = False
check('teleop: a running read-only program does not refuse', bridge.teleop_refusal() is None)
bridge.runs.clear()
ros.percent = 9.0
check('teleop: battery 9 percent refuses arming (deep) but does not stop a running session (not deep)',
      'Battery' in (bridge.teleop_refusal(deep=True) or '') and bridge.teleop_refusal(deep=False) is None)
ros.percent = 7.0
check('teleop: battery 7 percent stops a running session', 'Battery' in (bridge.teleop_refusal(deep=False) or ''))
ros.percent = float('nan')
check('teleop: an unreadable battery value refuses nothing', bridge.teleop_refusal(deep=True) is None)

# ================================================================ writing files on the robot (the code editor): h_write_file / h_read_file


def w(**kw):
    return bridge.h_write_file(dict({'dir': '~/robot_code'}, **kw))


def rejected(**kw):
    return refuses(w, exc=rb.BridgeError, **kw)


rc = os.path.join(bhome, 'robot_code')
r = w(path='programs/new.py', text='print(1)\n')
check('write_file: a new file is created (with its folder)', os.path.isfile(os.path.join(rc, 'programs', 'new.py')) and r['backup'] is None)
check('write_file: an existing file is refused without overwrite and not changed', rejected(path='programs/new.py', text='print(2)\n') is not None
      and open(os.path.join(rc, 'programs', 'new.py')).read() == 'print(1)\n')
old_sha = r['sha1']
m = rejected(path='programs/new.py', text='print(3)\n', overwrite=True, expect_sha1='0' * 40)
check('write_file: a file changed on the robot since it was opened is refused and kept', m is not None and 'changed on the robot' in m
      and open(os.path.join(rc, 'programs', 'new.py')).read() == 'print(1)\n', str(m))
r2 = w(path='programs/new.py', text='print(1)\n', overwrite=True, expect_sha1=old_sha)
check('write_file: the same text is not rewritten and makes no .bak', r2.get('unchanged') is True and not os.path.exists(os.path.join(rc, 'programs', 'new.py.bak')))
r3 = w(path='programs/new.py', text='print(4)\n', overwrite=True, expect_sha1=old_sha)
check('write_file: an overwrite keeps the old text in .bak', open(os.path.join(rc, 'programs', 'new.py')).read() == 'print(4)\n'
      and open(os.path.join(rc, 'programs', 'new.py.bak')).read() == 'print(1)\n' and r3['backup'].endswith('new.py.bak'))
check('write_file: no temporary .studio_ files are left behind', not [n for n in os.listdir(os.path.join(rc, 'programs')) if n.startswith('.studio_')])
for label, kw in (('a path with ..', dict(path='../escape.py', text='x')), ('an absolute path', dict(path='/etc/x', text='x')),
                  ('a double slash', dict(path='a//b.py', text='x')), ('a space in the name', dict(path='a b.py', text='x')),
                  ('text that is not a string', dict(path='programs/n2.py', text=b'x')),
                  ('text over 512 KB', dict(path='programs/n3.py', text='x' * (512 * 1024 + 1)))):
    check('write_file refuses %s' % label, rejected(**kw) is not None)
os.makedirs(os.path.join(rc, 'programs', 'adir'))
check('write_file: a folder with that name is refused', rejected(path='programs/adir', text='x', overwrite=True) is not None)
check('write_file: a directory outside home is refused', refuses(bridge.h_write_file, {'dir': os.path.dirname(bhome), 'path': 'x.py', 'text': 'x'}, exc=rb.BridgeError) is not None
      and not os.path.exists(os.path.join(os.path.dirname(bhome), 'x.py')))
check('write_file: the .ssh folder is refused', refuses(bridge.h_write_file, {'dir': '~/.ssh', 'path': 'authorized_keys', 'text': 'x'}, exc=rb.BridgeError) is not None
      and not os.path.exists(os.path.join(bhome, '.ssh', 'authorized_keys')))
rd = bridge.h_read_file({'dir': '~/robot_code', 'path': 'programs/new.py'})
check('read_file: returns the text and its sha1 for the next conflict check', rd['text'] == 'print(4)\n' and len(rd['sha1']) == 40)
with open(os.path.join(rc, 'programs', 'bin.dat'), 'wb') as f:
    f.write(b'\xff\xfe\x00\x01')
check('read_file: a binary file is refused', refuses(bridge.h_read_file, {'dir': '~/robot_code', 'path': 'programs/bin.dat'}, exc=rb.BridgeError) is not None)
check('read_file: a missing file is refused', refuses(bridge.h_read_file, {'dir': '~/robot_code', 'path': 'programs/none.py'}, exc=rb.BridgeError) is not None)

# ================================================================ which programs count as moving (Studio.motion_for_run)
app.bridge = StubBridge({'describe': st.BridgeError('not connected')})
cmd = {'cmd': 'run', 'path': 'totally_unknown_program.py'}
why = app.motion_for_run(cmd)
check('motion_for_run: a program that cannot be described counts as moving (the safe default)', cmd['motion'] is True and why, str(why))
cmd = {'cmd': 'run', 'path': 'totally_unknown_program.py'}
app.bridge = StubBridge({'describe': {'ok': False, 'error': 'x'}})
app.motion_for_run(cmd)
check('motion_for_run: a failed describe also counts as moving', cmd['motion'] is True)
cmd = {'cmd': 'run', 'path': 'totally_unknown_program.py', 'motion': True}
app.bridge = StubBridge({'describe': {'ok': True, 'programs': [{'name': 'totally_unknown_program.py'}]}})
app.motion_for_run(cmd)
check('motion_for_run: an explicit motion request is never lowered', cmd['motion'] is True)


# ================================================================ E-STOP: stopping motion programs that Studio did not start (_pkill_motion)


class FakeClock:
    """A virtual clock so the escalation waits (3 s, 2 s, 1 s) cost no real time."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += s


class Procs:
    """Stands in for pgrep/pkill: the matching processes die when a signal in dies_on arrives (None: never)."""

    def __init__(self, alive, dies_on):
        self.alive, self.dies_on, self.signals = list(alive), dies_on, []

    def run_cmd(self, args, timeout=3.0):
        if args[0] == 'pgrep':
            return ' '.join(self.alive) + ('\n' if self.alive else '') if self.alive else None
        if args[0] == 'pkill':
            sig = args[1].lstrip('-')
            self.signals.append(sig)
            if sig == self.dies_on:
                self.alive = []
            return ''
        return None


def run_pkill(alive, dies_on, fake=False, have_pkill=True):
    procs = Procs(alive, dies_on)
    b = rb.Bridge(StubRos(), lambda m: None, tempfile.mkdtemp(dir=OUT), fake)
    saved = (rb.run_cmd, rb.time, rb.shutil.which)
    rb.run_cmd, rb.time = procs.run_cmd, FakeClock()
    rb.shutil.which = lambda name: ('/usr/bin/' + name) if have_pkill else None
    try:
        return b._pkill_motion(), procs.signals
    finally:
        rb.run_cmd, rb.time, rb.shutil.which = saved


res, sigs = run_pkill([], None)
check('estop pkill: nothing running sends no signal', res == {'ok': True, 'matched': []} and sigs == [], str((res, sigs)))
res, sigs = run_pkill(['101'], 'INT')
check('estop pkill: a program that stops on SIGINT is not killed harder', res['ok'] is True and res['signal'] == 'INT' and sigs == ['INT'], str((res, sigs)))
res, sigs = run_pkill(['101', '102'], 'TERM')
check('estop pkill: escalates INT then TERM when the program ignores INT', res['ok'] is True and res['signal'] == 'TERM' and sigs == ['INT', 'TERM']
      and res['matched'] == ['101', '102'], str((res, sigs)))
res, sigs = run_pkill(['101'], 'KILL')
check('estop pkill: escalates to KILL as the last step', res['ok'] is True and res['signal'] == 'KILL' and sigs == ['INT', 'TERM', 'KILL'], str((res, sigs)))
res, sigs = run_pkill(['101'], None)
check('estop pkill: a program nothing can stop is reported as not stopped (ok False), never as done', res['ok'] is False and sigs == ['INT', 'TERM', 'KILL'], str((res, sigs)))
res, sigs = run_pkill(['101'], 'INT', fake=True)
check('estop pkill: the fake robot sends no signal and says it skipped', res.get('ok') is None and sigs == [], str((res, sigs)))
res, sigs = run_pkill(['101'], 'INT', have_pkill=False)
check('estop pkill: without pkill it says so instead of claiming success', res.get('ok') is None and 'not installed' in res.get('note', '') and sigs == [], str((res, sigs)))

shutil.rmtree(OUT, ignore_errors=True)
print('\n%s' % ('ALL PASSED' if not fails else '%d FAILED' % fails))
sys.exit(fails)
