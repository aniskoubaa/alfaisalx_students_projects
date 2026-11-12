"""End-to-end test of the TurtleBot Studio 2.1 Routes screen in a real browser (Playwright, installed Edge or Chrome, else Chromium).

It starts `studio.py --fake --no-browser --stay-open` with a NEW temporary STUDIO_CONFIG_DIR, HOME and fake robot home
(STUDIO_BRIDGE_HOME), connects through the first-run wizard, then drives the Routes screen: the route folders of the fake
robot, the current route, changing it with a confirmation, uploading a planned route folder (and the refusal of an
existing name), and the read-only trip status. No robot, no ROS, nothing outside the temporary folder is touched.

Usage: python test_studio_e2e_routes.py        (prints PASS/FAIL/SKIP, exit code = number of failures)
Environment: STUDIO_E2E_SHOTS=<folder> saves light and dark screenshots; STUDIO_E2E_HEADED=1 shows the browser.
axe-core is read from TurtleBot/tools/studio/ui/node_modules/axe-core/axe.min.js; without it the scan is skipped.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
AXE_JS = os.path.join(STUDIO_DIR, 'ui', 'node_modules', 'axe-core', 'axe.min.js')

try:
    from playwright.sync_api import sync_playwright, expect, Error as PwError
except Exception as e:  # not installed: nothing to test
    print('SKIP end-to-end test: Playwright is not importable (%s)' % e)
    sys.exit(0)

fails = 0
T_START = time.time()
SPENT = {'axe': 0.0, 'shots': 0.0}


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode(), flush=True)
    if not cond:
        fails += 1


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ================================================================ the studio process
TMP = tempfile.mkdtemp(prefix='tb4_studio_e2e_')
CFG = os.path.join(TMP, 'cfg')
HOME = os.path.join(TMP, 'home')
ROBOT = os.path.join(TMP, 'robot')
LOCAL = os.path.join(TMP, 'local_code')
for d in (HOME, os.path.join(ROBOT, 'robot_code'), LOCAL):
    os.makedirs(d)
with open(os.path.join(ROBOT, 'robot_code', 'hello.py'), 'w', encoding='utf-8', newline='\n') as f:
    f.write('print("hello from the robot")\n')
with open(os.path.join(ROBOT, 'robot_code', 'drive_test.py'), 'w', encoding='utf-8', newline='\n') as f:
    f.write('import time\nfor i in range(400):\n    print("tick", i, flush=True)\n    time.sleep(0.25)\n')
with open(os.path.join(LOCAL, 'local_only.py'), 'w', encoding='utf-8', newline='\n') as f:
    f.write('print("only on this computer")\n')

PORT = free_port()
env = dict(os.environ, HOME=HOME, USERPROFILE=HOME, APPDATA=os.path.join(HOME, 'AppData'), STUDIO_CONFIG_DIR=CFG,
           STUDIO_BRIDGE_HOME=ROBOT, STUDIO_FAKE_MAP_SCALE='0.3', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
proc = subprocess.Popen([sys.executable, '-u', os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--stay-open',
                         '--port', str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
TOKEN = None
for _ in range(200):
    try:
        with open(os.path.join(CFG, 'instance.json'), encoding='utf-8') as f:
            inst = json.load(f)
        TOKEN, PORT = inst['token'], inst['port']
        break
    except (OSError, ValueError, KeyError):
        time.sleep(0.1)
check('studio.py --fake starts and writes instance.json', TOKEN is not None)
BASE = 'http://127.0.0.1:%d' % PORT


def api(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={'X-Studio-Token': TOKEN, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'ok': False, 'http': e.code}


def bridge(cmd, **kw):
    return api('POST', '/api/bridge', dict(cmd=cmd, **kw))


class Stream(threading.Thread):
    """Reads Studio's event stream like a second page, to see the robot's status (docked, armed, pose) without the UI."""

    def __init__(self):
        threading.Thread.__init__(self, daemon=True)
        self.status = {}
        self.events = []
        self.resp = None

    def run(self):
        try:
            self.resp = urllib.request.urlopen(BASE + '/api/events?token=' + TOKEN, timeout=600)
            for raw in self.resp:
                line = raw.decode('utf-8', 'replace').strip()
                if line.startswith('data: '):
                    ev = json.loads(line[6:])
                    self.events.append(ev)
                    if ev.get('ev') == 'status':
                        self.status = ev
        except Exception:
            pass

    def wait(self, pred, timeout=6.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if pred(self.status):
                    return True
            except (KeyError, TypeError, AttributeError):
                pass
            time.sleep(0.1)
        try:
            return bool(pred(self.status))
        except (KeyError, TypeError, AttributeError):
            return False


STREAM = Stream()
if TOKEN is not None:
    STREAM.start()
SHOTS = os.environ.get('STUDIO_E2E_SHOTS')
if SHOTS:
    os.makedirs(SHOTS, exist_ok=True)
AXE = open(AXE_JS, encoding='utf-8').read() if os.path.isfile(AXE_JS) else None
if AXE is None:
    print('SKIP accessibility scan: %s not found (run npm ci in tools/studio/ui)' % AXE_JS)

errors = []          # console errors, page errors, failed requests, HTTP >= 400 (since the last check)
teleop_log = []      # every teleop body the page sent


class section:
    """Run one part of the test; an exception is reported as a FAIL (with a screenshot name) and the next part still runs."""
    page = None

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        print('--- %s (%d s into the run)' % (self.name, time.time() - T_START), flush=True)
        return self

    def __exit__(self, et, ev, tb):
        if ev is None or not isinstance(ev, Exception):
            return False
        import traceback
        mine = [f for f in traceback.extract_tb(tb) if f.filename == __file__]
        line = mine[-1].lineno if mine else 0
        check('section completed: ' + self.name, False, ('line %d: ' % line) + str(ev).strip().splitlines()[0][:160])
        try:
            if section.page is not None and os.environ.get('STUDIO_E2E_SHOTS'):
                section.page.screenshot(path=os.path.join(os.environ['STUDIO_E2E_SHOTS'], 'FAILED-%s.png' % re.sub(r'\W+', '-', self.name)))
        except Exception:
            pass
        try:       # close what is open (never press Escape: that is the E-STOP)
            for _ in range(4):
                dlg = section.page.get_by_role('dialog')
                if dlg.count() == 0:
                    break
                dlg.get_by_role('button', name='Close', exact=True).last.click(timeout=2000)
        except Exception:
            pass
        return True


def run():
    with sync_playwright() as pw:
        browser = None
        for kind in ('msedge', 'chrome', None):
            try:
                kw = {'headless': not os.environ.get('STUDIO_E2E_HEADED')}
                if kind:
                    kw['channel'] = kind
                browser = pw.chromium.launch(**kw)
                print('browser: %s' % (kind or 'bundled chromium'))
                break
            except Exception as e:
                print('browser %s not available: %s' % (kind or 'bundled chromium', str(e).splitlines()[0][:100]))
        if browser is None:
            print('SKIP end-to-end test: no browser could be started')
            return
        ctx = browser.new_context(viewport={'width': 1366, 'height': 860}, accept_downloads=True)
        page = ctx.new_page()
        page.set_default_timeout(8000)
        steps(page, ctx, browser)
        browser.close()


def steps(page, ctx, browser):
    section.page = page

    def on_console(m):
        if m.type == 'error':
            errors.append('console: ' + m.text[:200])

    page.on('console', on_console)
    page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)[:200]))
    page.on('requestfailed', lambda r: errors.append('failed: %s %s' % (r.url[:100], r.failure)) if '/api/events' not in r.url else None)
    def on_response(r):
        if r.status >= 400:
            try:
                body = r.text()[:80]
            except Exception:
                body = '?'
            errors.append('http %d %s %s (%s) %s' % (r.status, r.request.method, r.url.split('?')[0][-40:], r.headers.get('server', '?'), body))

    page.on('response', on_response)

    def on_request(r):
        if r.method == 'POST' and r.url.endswith('/api/bridge'):
            try:
                b = json.loads(r.post_data or '{}')
            except ValueError:
                return
            if b.get('cmd') == 'teleop':
                teleop_log.append((time.time(), b.get('vx'), b.get('wz')))

    page.on('request', on_request)

    def clean(label):
        """No console errors or failed requests since the last call."""
        time.sleep(0.2)
        bad = list(errors)
        del errors[:]
        check('no console errors or failed requests: ' + label, not bad, '; '.join(bad[:3]))

    def go(route):
        page.evaluate("location.hash = '#/%s'" % route)
        page.wait_for_timeout(500)

    def axe(label):
        if AXE is None:
            return
        t0 = time.time()
        axe_run(label)
        SPENT['axe'] += time.time() - t0

    def axe_run(label):
        for scheme in ('light', 'dark'):
            page.emulate_media(color_scheme=scheme)
            page.wait_for_timeout(150)
            if not page.evaluate('typeof window.axe !== "undefined"'):
                page.evaluate(AXE)
            res = page.evaluate("""() => axe.run(document, {resultTypes: ['violations']}).then(r => r.violations.map(v => ({
                id: v.id, impact: v.impact, n: v.nodes.length, t: v.nodes.slice(0, 2).map(n => n.target.join(' ')).join(' | ')})))""")
            bad = [v for v in res if v['impact'] in ('serious', 'critical')]
            check('axe (%s) %s: no serious or critical violations' % (scheme, label), not bad,
                  '; '.join('%s x%d %s' % (v['id'], v['n'], v['t'][:80]) for v in bad[:4]))
        page.emulate_media(color_scheme='light')

    def shot(name):
        if not SHOTS:
            return
        t0 = time.time()
        shot_run(name)
        SPENT['shots'] += time.time() - t0

    def shot_run(name):
        for scheme in ('light', 'dark'):
            page.emulate_media(color_scheme=scheme)
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(SHOTS, '%s-%s.png' % (name, scheme)))
        page.emulate_media(color_scheme='light')

    def text(sel='body'):
        return page.inner_text(sel)

    def dialog():
        return page.get_by_role('dialog')

    def close_dialog():
        dialog().get_by_role('button', name='Close', exact=True).last.click()
        expect(dialog()).to_have_count(0)

    def no_overflow(label):
        w = page.evaluate('[document.documentElement.scrollWidth, window.innerWidth]')
        check('no horizontal page scroll: ' + label, w[0] <= w[1], str(w))

    # ---------------------------------------------------------------- first run: wizard
    with section('first run: wizard'):
        page.goto('%s/?token=%s' % (BASE, TOKEN))
        expect(dialog()).to_contain_text('Set up TurtleBot Studio')
        check('first run: the setup wizard opens by itself', True)
        check('the token is removed from the address bar', 'token=' not in page.url, page.url)
        axe('wizard dialog')
        shot('wizard')
        d = dialog()
        d.get_by_label('Robot address').fill('fake')
        d.get_by_role('button', name='Use this address').click()
        d.get_by_role('button', name='Check robot identity').click()
        expect(d).to_contain_text('SHA256:')
        d.get_by_label('I compared them and they are the same').check()
        d.get_by_role('button', name='Trust this robot').click()
        d.get_by_role('button', name='Create key').click()
        expect(d).to_contain_text('Key created')
        d.get_by_role('button', name='Open terminal').click()      # fake mode: no terminal opens
        expect(d).to_contain_text('fake mode: no terminal')
        d.get_by_role('button', name='Test login').click()
        expect(d).to_contain_text('Logged in to fake-turtlebot4')
        check('wizard: all six steps complete in fake mode', len(d.get_by_text('Done', exact=True).all()) >= 5)
        d.get_by_role('button', name='Connect', exact=True).click()
        expect(page.get_by_role('status').first).to_contain_text('Connected', timeout=15000)
        page.wait_for_timeout(800)
        if dialog().count():      # the wizard may close by itself right after connecting
            try:
                dialog().get_by_role('button', name='Close', exact=True).last.click(timeout=2000)
            except PwError:
                pass
        expect(dialog()).to_have_count(0, timeout=5000)
        check('wizard: Connect connects to the fake robot', True)
        check('wizard: setup_done is saved', api('GET', '/api/settings').get('setup_done') is True)
        clean('wizard')

    # ---------------------------------------------------------------- Routes: list and current
    with section('Routes: list and current'):
        go('routes')
        expect(page.get_by_role('heading', name='Routes', exact=True)).to_be_visible()
        expect(page.get_by_test_id('route-row-home')).to_be_visible(timeout=10000)
        check('Routes: the fake robot lists the route folders home and route1', page.get_by_test_id('route-row-route1').count() == 1)
        expect(page.get_by_test_id('route-current')).to_contain_text('home')
        check('Routes: the current route is shown (home)', True)
        axe('Routes')
        shot('routes')
        page.get_by_test_id('route-row-route1').get_by_role('button', name=re.compile('^Use')).click()
        d = dialog()
        expect(d).to_contain_text('route1')
        check('Routes: changing the route asks first and names the new route', 'home' in d.inner_text(), d.inner_text()[:160])
        shot('routes-confirm')
        d.get_by_role('button', name=re.compile('^Use')).last.click()
        expect(page.get_by_test_id('route-current')).to_contain_text('route1', timeout=10000)
        check('Routes: the current route is now route1', bridge('routes_list').get('current') == 'route1')
        clean('Routes current')

    # ---------------------------------------------------------------- Routes: upload a planned folder
    with section('Routes: upload a route folder'):
        folder = os.path.join(TMP, 'campus_test')
        os.makedirs(folder)
        for n in ('route.yaml', 'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml'):
            with open(os.path.join(folder, n), 'w', encoding='utf-8', newline='\n') as f:
                f.write('# test file %s\nversion: 1\noutbound:\n  - {x: 1.0, y: 0.0, yaw: 0}\ninbound:\n  - {x: 0.0, y: 0.0, yaw: 180}\n' % n)
        with open(os.path.join(folder, 'map.pgm'), 'wb') as f:
            f.write(b'P5\n4 4\n255\n' + bytes([254]) * 16)
        page.get_by_label('Choose a route folder').set_input_files(folder)
        page.wait_for_timeout(500)
        main = page.locator('main')
        expect(main).to_contain_text('campus_test')
        page.get_by_role('button', name=re.compile('^Upload')).click()
        expect(page.get_by_test_id('route-row-campus_test')).to_be_visible(timeout=15000)
        check('Routes: the uploaded folder appears in the list', True)
        names = [r['name'] for r in bridge('routes_list').get('routes', [])]
        check('Routes: the robot has the uploaded route', 'campus_test' in names, str(names))
        page.get_by_label('Choose a route folder').set_input_files(folder)
        page.wait_for_timeout(500)
        expect(main).to_contain_text('already exists', timeout=10000)
        check('Routes: an existing name is refused with a clear message before sending',
              page.get_by_role('button', name=re.compile('^Upload')).is_disabled())
        up = api('POST', '/api/routes/upload', {'name': 'campus_test', 'files': [{'path': n, 'data_b64': 'eDogMQo='} for n in
                                                  ('route.yaml', 'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml')]})
        check('Routes: the backend also refuses an existing name', up.get('ok') is False and up.get('exists') is True, str(up)[:120])
        del errors[:]        # the refused upload answers with an error on purpose
        shot('routes-upload')

    # ---------------------------------------------------------------- Routes: trip status (read only)
    with section('Routes: trip status'):
        main = page.locator('main')
        expect(main).to_contain_text('delivery_menu started', timeout=10000)
        check('Routes: the menu log lines are shown', True)
        check('Routes: says trips are started from the robot menu, not from Studio', 'not part of this version' in main.inner_text())
        check('Routes: no button starts a trip', page.get_by_role('button', name=re.compile('start (a )?trip|go to food', re.I)).count() == 0)
        clean('Routes trip status')


try:
    if TOKEN is not None:
        run()
finally:
    try:
        api('POST', '/api/quit', {})
    except Exception:
        pass
    try:
        proc.wait(8)
    except subprocess.TimeoutExpired:
        proc.kill()
    check('studio.py stopped', proc.poll() is not None)
    shutil.rmtree(TMP, ignore_errors=True)

print('\ntime: %d s in total, %d s of it in axe scans, %d s in screenshots' % (time.time() - T_START, SPENT['axe'], SPENT['shots']))
print('\n%d failure(s)' % fails)
sys.exit(fails)
