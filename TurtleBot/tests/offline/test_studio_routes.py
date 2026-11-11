"""Offline tests of the TurtleBot Studio 2.1 routes feature (TurtleBot/tools/studio, design in docs/DESIGN-MAPPING.md):
the route folders on the robot, the `current` link, the read-only trip status from the menu log, and the upload of a
route folder made by delivery/tools/plan_route.py.

No robot and no ROS: the bridge runs in --fake mode as a subprocess with a temporary robot home, and the HTTP part starts
the real studio.py --fake with a temporary config folder, a temporary fake robot home and a temporary copy of web/.
Usage: python test_studio_routes.py     (prints PASS/FAIL, exit code = number of failures)
"""
import base64
import http.client
import json
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

OUT = tempfile.mkdtemp(prefix='tb4_studio_routes_')
fails = 0
REQUIRED = ('route.yaml', 'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml')


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode(), flush=True)
    if not cond:
        fails += 1


def wait_for(fn, timeout, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


class Proc:
    """The fake bridge as a subprocess, commands on stdin, events on stdout."""

    def __init__(self):
        self.home = tempfile.mkdtemp(prefix='home_', dir=OUT)
        env = dict(os.environ, STUDIO_BRIDGE_FAKE='1', STUDIO_BRIDGE_HOME=self.home, PYTHONDONTWRITEBYTECODE='1')
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
                self.events.append(ev)

    def send(self, cmd, timeout=10.0, **kw):
        self.next_id += 1
        i = self.next_id
        self.p.stdin.write((json.dumps(dict(kw, id=i, cmd=cmd)) + '\n').encode())
        self.p.stdin.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                for e in self.events:
                    if e.get('ev') == 'reply' and e.get('id') == i:
                        return e
            time.sleep(0.01)
        return {'ok': False, 'error': 'no reply (timeout)'}

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(3)
        except Exception:
            self.p.kill()


def names(r):
    return [x.get('name') for x in r.get('routes', [])]


def entry(r, name):
    return next((x for x in r.get('routes', []) if x.get('name') == name), {})


# ================================================================ bridge (fake robot)
b = Proc()
try:
    check('fake bridge says hello', wait_for(lambda: any(e.get('ev') == 'hello' for e in list(b.events)), 15))
    r = b.send('routes_list')
    check('routes_list answers', r.get('ok') is True, str(r)[:160])
    check('routes_list: the fake robot has the seeded routes home and route1', {'home', 'route1'} <= set(names(r)), str(names(r)))
    check('routes_list: current points to home', r.get('current') == 'home' and r.get('current_ok') is True, str(r.get('current')))
    check('routes_list: seeded routes are valid', entry(r, 'home').get('valid') is True and entry(r, 'route1').get('valid') is True)
    check('routes_list: the folder is robot_code/routes', str(r.get('dir', '')).replace('\\', '/').endswith('robot_code/routes'), str(r.get('dir')))
    check('routes_list: the current link itself is not listed as a route', 'current' not in names(r))
    wp = entry(r, 'home').get('waypoints') or {}
    check('routes_list: waypoint counts are read from route.yaml', isinstance(wp.get('outbound'), int) and wp['outbound'] >= 1, str(wp))

    # an incomplete folder made by hand
    broken = os.path.join(b.home, 'robot_code', 'routes', 'broken')
    os.makedirs(broken, exist_ok=True)
    with open(os.path.join(broken, 'route.yaml'), 'w', encoding='utf-8') as f:
        f.write('version: 1\n')
    r = b.send('routes_list')
    e = entry(r, 'broken')
    check('routes_list: an incomplete folder is listed as not valid', e.get('valid') is False, str(e))
    check('routes_list: it names the missing files', set(e.get('missing') or []) == {'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml'},
          str(e.get('missing')))

    r = b.send('route_set_current', name='route1')
    check('route_set_current without confirm is refused', r.get('ok') is False, str(r)[:120])
    r = b.send('route_set_current', name='nope', confirm=True)
    check('route_set_current to a folder that does not exist is refused', r.get('ok') is False)
    r = b.send('route_set_current', name='../home', confirm=True)
    check('route_set_current with a path is refused', r.get('ok') is False)
    r = b.send('route_set_current', name='broken', confirm=True)
    check('route_set_current to an incomplete folder is refused', r.get('ok') is False and 'missing' in str(r.get('error', '')).lower(), str(r)[:160])
    check('current is unchanged after the refusals', b.send('routes_list').get('current') == 'home')

    r = b.send('route_set_current', name='route1', confirm=True)
    check('route_set_current route1 with confirm works', r.get('ok') is True and r.get('current') == 'route1', str(r)[:160])
    check('routes_list now says current = route1', b.send('routes_list').get('current') == 'route1')

    # trips: read-only status, and no change of current while a trip runs (hidden fake-only command)
    t = b.send('trip_status')
    check('trip_status answers', t.get('ok') is True, str(t)[:160])
    check('trip_status: process flags are booleans', all(isinstance(t.get(k), bool) for k in ('menu_running', 'mission_running', 'stack_running')),
          str({k: t.get(k) for k in ('menu_running', 'mission_running', 'stack_running')}))
    check('trip_status: the fake menu log has lines', isinstance(t.get('lines'), list) and len(t['lines']) >= 1, str(t.get('lines'))[:120])
    check('trip_status: names menu.log', str(t.get('log_path', '')).replace('\\', '/').endswith('logs/delivery/menu.log'), str(t.get('log_path')))
    t5 = b.send('trip_status', lines=1)
    check('trip_status: lines limits the answer', len(t5.get('lines') or []) <= 1)
    f = b.send('fake_trip', running=True)
    check('fake_trip (fake only) marks a trip as running', f.get('ok') is True, str(f)[:120])
    check('trip_status reports the running trip', b.send('trip_status').get('mission_running') is True)
    r = b.send('route_set_current', name='home', confirm=True)
    check('route_set_current is refused while a trip runs', r.get('ok') is False and 'trip' in str(r.get('error', '')).lower(), str(r)[:160])
    b.send('fake_trip', running=False)
    r = b.send('route_set_current', name='home', confirm=True)
    check('route_set_current works again after the trip', r.get('ok') is True and r.get('current') == 'home')
finally:
    b.close()

# ================================================================ desktop: upload helpers
check('ROUTE_UPLOAD_MAX is 32 MB', getattr(st, 'ROUTE_UPLOAD_MAX', None) == 32 * 1024 * 1024)
vu = getattr(st, 'validate_route_upload', None)
check('validate_route_upload exists', callable(vu))
if callable(vu):
    good = [{'path': n, 'data_b64': base64.b64encode(b'x: 1\n').decode()} for n in REQUIRED]
    ok, info = vu('campus1', good)
    check('validate_route_upload accepts a complete flat folder', ok is True, str(info)[:120])
    ok, info = vu('bad name!', good)
    check('validate_route_upload refuses a bad name', ok is False)
    ok, info = vu('campus1', good[:3])
    check('validate_route_upload names a missing file', ok is False and 'speed_mask.yaml' in str(info), str(info)[:120])
    ok, info = vu('campus1', good + [{'path': 'sub/x.yaml', 'data_b64': ''}])
    check('validate_route_upload refuses nested paths', ok is False)
    ok, info = vu('campus1', good + [{'path': '../x.yaml', 'data_b64': ''}])
    check('validate_route_upload refuses ..', ok is False)
    ok, info = vu('campus1', good + [{'path': 'map.pgm', 'data_b64': '***not base64***'}])
    check('validate_route_upload refuses bad base64', ok is False)
    ok, info = vu('campus1', good + [dict(good[0])])
    check('validate_route_upload refuses duplicate files', ok is False)

# ================================================================ HTTP: real studio.py --fake
WEB = os.path.join(OUT, 'web_copy')
shutil.copytree(os.path.join(STUDIO_DIR, 'web'), WEB, ignore=shutil.ignore_patterns('v2'))
CFG = os.path.join(OUT, 'httpcfg')
HOME = os.path.join(OUT, 'httphome')
FAKE_HOME = os.path.join(CFG, 'home')
os.makedirs(HOME)
env = dict(os.environ, HOME=HOME, USERPROFILE=HOME, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
proc = subprocess.Popen([sys.executable, '-u', os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--port', '0', '--config-dir', CFG,
                         '--fake-home', FAKE_HOME, '--heartbeat', '1', '--web-dir', WEB],
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
    check('studio.py --fake starts', got_url.wait(20))
    PORT, TOKEN = url['port'], url['token']

    def call(method, path, body=None, timeout=60, raw=None):
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=timeout)
        h = {'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN}
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
        if data is not None:
            h['Content-Type'] = 'application/json'
        c.request(method, path, body=data, headers=h)
        resp = c.getresponse()
        txt = resp.read()
        c.close()
        try:
            return resp.status, json.loads(txt.decode('utf-8'))
        except ValueError:
            return resp.status, {}

    s, j = call('POST', '/api/connect', {})
    check('connect to the fake robot', j.get('ok') is True, str(j)[:120])
    wait_for(lambda: call('POST', '/api/bridge', {'cmd': 'ping'})[1].get('ok'), 15, 0.3)

    def upload(name, files):
        return call('POST', '/api/routes/upload', {'name': name, 'files': files})

    big = os.urandom(1_500_000)        # bigger than the general 1 MB request limit
    files = [{'path': n, 'data_b64': base64.b64encode(('# %s\nimage: map.pgm\n' % n).encode()).decode()} for n in REQUIRED]
    files.append({'path': 'map.pgm', 'data_b64': base64.b64encode(big).decode()})
    s, j = upload('uploaded1', files)
    check('upload of a complete route folder (over 1 MB) works', s == 200 and j.get('ok') is True, '%s %s' % (s, str(j)[:160]))
    on_disk = os.path.join(FAKE_HOME, 'robot_code', 'routes', 'uploaded1')
    check('the files arrive in robot_code/routes/<name>', os.path.isfile(os.path.join(on_disk, 'route.yaml'))
          and os.path.getsize(os.path.join(on_disk, 'map.pgm')) == len(big), on_disk)
    s, j = call('POST', '/api/bridge', {'cmd': 'routes_list'})
    check('routes_list shows the uploaded route as valid', entry(j, 'uploaded1').get('valid') is True, str(names(j)))
    s, j = upload('uploaded1', files)
    check('upload to an existing name is refused', j.get('ok') is False and j.get('exists') is True, str(j)[:160])
    s, j = upload('uploaded2', files[1:])
    check('upload without route.yaml is refused and names it', j.get('ok') is False and 'route.yaml' in str(j.get('error', '')), str(j)[:160])
    check('a refused upload writes nothing', not os.path.exists(os.path.join(FAKE_HOME, 'robot_code', 'routes', 'uploaded2')))
    s, j = upload('uploaded3', files + [{'path': 'x/../../evil.txt', 'data_b64': ''}])
    check('upload with a path outside the folder is refused', j.get('ok') is False)
    s, j = upload('bad name', files)
    check('upload with a bad name is refused', j.get('ok') is False)
    s, j = call('POST', '/api/routes/upload', raw=b'{"name": "x", "files": []}', timeout=10)
    check('upload with no files is refused', j.get('ok') is False)
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=10)
    c.putrequest('POST', '/api/bridge')
    c.putheader('Host', '127.0.0.1:%d' % PORT)
    c.putheader('X-Studio-Token', TOKEN)
    c.putheader('Content-Length', str(2_000_000))
    c.endheaders()
    resp = c.getresponse()
    check('other endpoints keep the 1 MB request limit', resp.status == 413, str(resp.status))
    c.close()
finally:
    try:
        call('POST', '/api/quit', {})
    except Exception:
        pass
    try:
        proc.wait(8)
    except subprocess.TimeoutExpired:
        proc.kill()

check('studio.py stopped', proc.poll() is not None)
shutil.rmtree(OUT, ignore_errors=True)
print('\n%d failure(s)' % fails)
sys.exit(fails)
