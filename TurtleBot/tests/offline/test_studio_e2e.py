"""End-to-end test of TurtleBot Studio 2.0 in a real browser (Playwright, installed Edge or Chrome, else bundled Chromium).

It starts `studio.py --fake --no-browser --stay-open` on a free port with a NEW temporary STUDIO_CONFIG_DIR (and a temporary
HOME), reads the address and token from instance.json, and drives the real page: first-run wizard, connect, Overview, E-STOP,
Programs, Code, Files, Wi-Fi, Topics, Settings, Diagnostics, Update check, Live (lidar canvas, arming, driving, battery rules),
Charts, Events, Logs, command palette, theme, the classic 1.3 page, the phone width, and an accessibility scan (axe-core) of
every screen. No robot, no ROS, nothing outside the temporary folder is touched.

Usage: python test_studio_e2e.py        (prints PASS/FAIL/SKIP, exit code = number of failures)
Environment: STUDIO_E2E_SHOTS=<folder> saves light and dark screenshots of every screen (1366x860) there.
             STUDIO_E2E_HEADED=1 shows the browser.
axe-core is read from TurtleBot/tools/studio/ui/node_modules/axe-core/axe.min.js (run `npm ci` in ui/ first); without it the
accessibility scan is skipped with a SKIP line.
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
           STUDIO_BRIDGE_HOME=ROBOT, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
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
        if dialog().count():
            close_dialog()
        check('wizard: Connect connects to the fake robot', True)
        check('wizard: setup_done is saved', api('GET', '/api/settings').get('setup_done') is True)
        clean('wizard')

    # ---------------------------------------------------------------- phone width: dialogs fit, E-STOP visible
    with section('phone width: dialogs fit, E-STOP visible'):
        page.set_viewport_size({'width': 390, 'height': 844})
        page.evaluate("location.hash = '#/overview'")
        page.wait_for_timeout(500)
        no_overflow('Overview on a phone')
        check('phone: E-STOP is visible', page.get_by_role('button', name=re.compile('^Emergency stop')).is_visible())
        page.set_viewport_size({'width': 1366, 'height': 860})

    # ---------------------------------------------------------------- Overview
    with section('Overview'):
        go('overview')
        pill = page.get_by_role('status').first
        expect(pill).to_contain_text('Connected')
        expect(pill).to_contain_text('typed address')
        check('status pill says the route in words, never "custom"', 'custom' not in text('header'))
        main = page.locator('main')
        expect(main).to_contain_text('Reached over')
        expect(main).to_contain_text('Connected since')
        check('Overview: compact card, address field hidden while connected', page.get_by_label('Robot address (optional)').count() == 0)
        page.get_by_role('button', name='Change robot').click()
        expect(page.get_by_label('Robot address (optional)')).to_be_visible()
        for n in ('Discover', 'Search the whole network', 'Setup wizard'):
            check('Change robot shows ' + n, page.get_by_role('button', name=n, exact=True).count() == 1)
        page.get_by_role('button', name='Change robot').click()
        expect(page.get_by_label('Robot address (optional)')).to_have_count(0)
        check('Overview: battery value shown', re.search(r'Battery\s+\d+\s*%', text('main')) is not None, text('main')[:80])
        for lab in ('Voltage', 'Dock', 'Motion and odometry', 'Lidar and hazards', 'Network', 'Robot system'):
            check('Overview: panel ' + lab, lab in text('main'))
        check('Overview: no middle-dot or raw route names', '·' not in text('body') and not re.search(r'\bcustom\b', text('main')))
        axe('Overview')
        shot('overview')
        clean('Overview')

    # ---------------------------------------------------------------- E-STOP by key, banner, release with confirm
    with section('E-STOP by key, banner, release with confirm'):
        page.locator('main').click(position={'x': 5, 'y': 5})
        page.keyboard.press('Escape')
        expect(page.get_by_role('alert').first).to_contain_text('E-stop is on')
        expect(dialog()).to_contain_text('E-stop sent')
        check('E-STOP key: result lists the steps and not raw data', 'Drive motors switched off' in text('role=dialog') and 'ev reply' not in text('role=dialog'),
              text('role=dialog')[:120])
        shot('estop-dialog')
        close_dialog()
        check('E-STOP: Studio reports the e-stop on', STREAM.wait(lambda s: s['estop']['on'] is True))
        shot('estop-banner')
        page.get_by_role('button', name='Release e-stop').first.click()
        expect(dialog()).to_contain_text('Release the e-stop?')
        dialog().get_by_role('button', name='Release e-stop').click()
        expect(page.get_by_role('alert')).to_have_count(0)
        check('E-STOP released with a confirmation', True)
        clean('E-STOP')

    # ---------------------------------------------------------------- Programs
    with section('Programs'):
        go('programs')
        expect(page.get_by_role('button', name='Run hello.py')).to_be_visible()
        page.get_by_role('button', name='Run hello.py').click()
        expect(page.locator('main')).to_contain_text('hello from the robot')
        check('Programs: a program that does not move runs without a question, live output', True)
        page.get_by_role('button', name='Run drive_test.py').click()
        expect(dialog()).to_contain_text('drive_test.py moves the robot')
        check('Programs: a motion program asks first, Start moving needs the box', dialog().get_by_role('button', name='Start moving').is_disabled())
        shot('motion-dialog')
        dialog().get_by_label(re.compile('I am next to the robot')).check()
        dialog().get_by_role('button', name='Start moving').click()
        expect(page.locator('main')).to_contain_text('tick 3', timeout=15000)
        check('Programs: motion program runs and its output streams live', True)
        axe('Programs (running)')
        shot('programs')
        clean('Programs')
        page.get_by_role('button', name='Stop all').click()
        deadline = time.time() + 10
        while time.time() < deadline and any(r.get('running') for r in (bridge('runs').get('runs') or [])):
            time.sleep(0.3)
        check('Programs: Stop ends the program', not any(r.get('running') for r in (bridge('runs').get('runs') or [])))
        time.sleep(1.0)
        codes = [x['code'] for x in api('GET', '/api/alerts')['alerts']]
        check('Programs: a program stopped by the user is "was stopped", not an error', 'program_failed' not in codes
              and any('drive_test.py was stopped' in x['text'] for x in api('GET', '/api/alerts')['alerts']), str(codes))

    # ---------------------------------------------------------------- Code
    with section('Code'):
        go('code')
        page.get_by_role('button', name=re.compile('hello.py')).first.click()
        expect(page.locator('.cm-content')).to_contain_text('hello from the robot')
        page.locator('.cm-content').click()
        page.keyboard.press('Control+End')
        page.keyboard.type('# edited by the e2e test')
        page.get_by_role('button', name=re.compile('^Save to')).click()
        expect(page.locator('body')).to_contain_text('Saved to the robot')
        with open(os.path.join(ROBOT, 'robot_code', 'hello.py'), encoding='utf-8') as f:
            check('Code: the edit is saved on the robot', '# edited by the e2e test' in f.read())
        page.get_by_role('button', name=re.compile('^Save to')).click()
        expect(page.locator('body')).to_contain_text('No changes to save')
        check('Code: saving again says "No changes to save"', True)
        axe('Code')
        shot('code')
        clean('Code')

    # ---------------------------------------------------------------- Files: dry run
    with section('Files: dry run'):
        go('files')
        page.get_by_label('Folder on this computer').fill(LOCAL)
        page.get_by_role('button', name='Use these folders').click()
        page.get_by_role('button', name='Preview upload (dry run)').click()
        expect(page.locator('main')).to_contain_text('local_only.py')
        check('Files: dry run lists the file it would upload', True)
        check('Files: the dry run uploaded nothing', not os.path.exists(os.path.join(ROBOT, 'robot_code', 'local_only.py')))
        axe('Files')
        shot('files')
        clean('Files')

    # ---------------------------------------------------------------- Wi-Fi: join success and FailNet
    with section('Wi-Fi: join success and FailNet'):
        go('wifi')
        expect(page.locator('main')).to_contain_text('Connect over Wi-Fi')
        check('Wi-Fi: "Studio talks to it via" uses words', 'via\ncustom' not in text('main') and 'typed address' in text('main'))

        def add_network(ssid, password):
            page.get_by_label(re.compile('^Network name')).fill(ssid)
            page.get_by_label(re.compile('^Wi-Fi password')).fill(password)
            box = page.get_by_label(re.compile('^Switch the robot to it now'))
            if not box.is_checked():
                box.check()
            page.get_by_role('button', name=re.compile('^Add .* to the robot')).click()
            expect(dialog()).to_be_visible()
            dialog().get_by_role('button', name='Open terminal').click()      # fake mode: no terminal opens

        add_network('LabNet5', 'test-password-1')
        expect(dialog()).to_contain_text(re.compile('joined|Joined'), timeout=30000)
        check('Wi-Fi: joining a network succeeds in fake mode', True)
        shot('wifi-joined')
        close_dialog()
        add_network('FailNet', 'test-password-2')
        expect(dialog()).to_contain_text(re.compile('could not join|failed|Failed', re.I), timeout=30000)
        check('Wi-Fi: the FailNet failure path says it failed and what happened', True)
        close_dialog()
        check('Wi-Fi: the password is not left in the form', page.get_by_label(re.compile('^Wi-Fi password')).input_value() == '')
        axe('Wi-Fi')
        shot('wifi')
        clean('Wi-Fi')

    # ---------------------------------------------------------------- Topics
    with section('Topics'):
        go('topics')
        page.get_by_role('button', name='Watch /odom', exact=True).click()
        expect(page.locator('main')).to_contain_text(re.compile(r'1 / 4'))
        expect(page.locator('main')).to_contain_text(re.compile(r'Hz'), timeout=15000)
        check('Topics: watching a topic shows live messages', True)
        axe('Topics')
        shot('topics')
        page.get_by_role('button', name=re.compile('Stop watching')).first.click()
        expect(page.locator('main')).to_contain_text('Nothing watched yet')
        clean('Topics')

    # ---------------------------------------------------------------- Tools, Diagnostics, Update check, Settings
    with section('Tools, Diagnostics, Update check, Settings'):
        go('tools')
        page.get_by_role('button', name='Show diagnostics').click()
        expect(dialog().locator('textarea')).to_have_value(re.compile('TurtleBot Studio diagnostics'))
        diag = dialog().locator('textarea').input_value()
        check('Diagnostics: the text has the route in words', 'typed address' in diag or 'Typed' in diag, diag[:200])
        check('Diagnostics: the text contains no token', TOKEN not in diag and 'token=' not in diag)
        shot('diagnostics')
        page.context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=BASE)
        dialog().get_by_role('button', name='Copy').click()
        try:
            clip = page.evaluate('navigator.clipboard.readText()')
            check('Diagnostics: the copied text contains no token', TOKEN not in clip and 'diagnostics' in clip)
        except PwError:
            print('SKIP clipboard read not allowed in this browser')
        close_dialog()
        page.get_by_role('button', name='Check for updates').click()
        expect(page.locator('main')).to_contain_text(re.compile('Could not check|up to date|newer|latest|available', re.I), timeout=20000)
        check('Update check: gives an answer (Could not check is fine in fake mode)', True)
        axe('Tools')
        shot('tools')
        clean('Tools')
        page.get_by_role('button', name='Open settings').click()
        expect(page.locator('main')).to_contain_text('Robot names and addresses')
        page.get_by_label(re.compile('^Robot host name')).fill('tb-e2e')
        expect(page.locator('main')).to_contain_text('You have unsaved changes')
        page.get_by_role('button', name='Save settings').click()
        expect(page.locator('main')).to_contain_text('No changes to save', timeout=10000)
        check('Settings: the change is persisted by Studio', api('GET', '/api/settings').get('robot_hostname') == 'tb-e2e')
        with open(os.path.join(CFG, 'settings.json'), encoding='utf-8') as f:
            check('Settings: and written to settings.json in the temporary folder', json.load(f).get('robot_hostname') == 'tb-e2e')
        axe('Settings')
        shot('settings')
        clean('Settings')

    # ---------------------------------------------------------------- Live
    with section('Live'):
        bridge('fake_battery', percent=None)
        go('live')
        canvas = page.locator('canvas').first
        expect(canvas).to_be_visible()
        page.wait_for_timeout(2500)
        drawn = page.evaluate("""() => { const c = document.querySelector('canvas'); const g = c.getContext('2d');
            const d = g.getImageData(0, 0, c.width, c.height).data; let n = 0;
            for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n; }""")
        check('Live: the lidar canvas has drawn pixels', drawn > 500, str(drawn))
        shot('live')
        axe('Live')
        page.get_by_role('button', name='Arm driving').click()
        dialog().get_by_label(re.compile('I am next to the robot')).check()
        dialog().get_by_role('button', name='Arm driving').click()
        expect(page.locator('body')).to_contain_text('Undock', timeout=8000)
        check('Live: arming is refused while the robot is docked (Undock first)', STREAM.status['dock']['is_docked'] is True and STREAM.status['teleop']['armed'] is False)
        if dialog().count():
            close_dialog()
        # undock from the Overview
        go('overview')
        page.get_by_role('button', name='Undock').click()
        dialog().get_by_label(re.compile('I am next to the robot')).check()
        dialog().get_by_role('button', name='Start moving').click()
        check('Overview: Undock works in fake mode', STREAM.wait(lambda s: s['dock']['is_docked'] is False, 25))

        # battery rules (hidden fake-only command)
        bridge('fake_battery', percent=9)
        go('live')
        page.get_by_role('button', name='Arm driving').click()
        dialog().get_by_label(re.compile('I am next to the robot')).check()
        dialog().get_by_role('button', name='Arm driving').click()
        expect(page.locator('body')).to_contain_text('Battery below 10 %', timeout=8000)
        check('Live: arming is refused below 10 % battery with the plain text', STREAM.status['teleop']['armed'] is False)
        if dialog().count():
            close_dialog()
        bridge('fake_battery', percent=None)

        page.get_by_role('button', name='Arm driving').click()
        dialog().get_by_label(re.compile('I am next to the robot')).check()
        dialog().get_by_role('button', name='Arm driving').click()
        expect(page.get_by_role('button', name=re.compile('^Disarm')).first).to_be_visible(timeout=8000)
        check('Live: armed after undock (amber bar and Disarm)', True)
        shot('live-armed')
        axe('Live (armed)')
        page.locator('main').click(position={'x': 5, 'y': 5})
        del teleop_log[:]
        page.keyboard.down('w')
        page.wait_for_timeout(1500)
        moving = [t for t in teleop_log if t[1]]
        check('Live: holding W sends forward commands', len(moving) >= 5, str(len(moving)))
        check('Live: forward speed is within the 0.15 m/s default limit', all(abs(t[1]) <= 0.1500001 for t in moving))
        check('Live: the pose x changes while W is held', STREAM.wait(lambda s: abs(s['odom']['x']) > 0.03, 3), str(STREAM.status.get('odom')))
        page.keyboard.up('w')
        page.wait_for_timeout(700)
        check('Live: releasing W sends a commanded zero', bool(teleop_log) and teleop_log[-1][1] == 0 and teleop_log[-1][2] == 0, str(teleop_log[-2:]))
        check('Live: the robot is not moving after release', STREAM.wait(lambda s: abs(s['odom']['vx']) < 0.001, 3))
        page.keyboard.press('Escape')
        expect(page.get_by_role('alert').first).to_contain_text('E-stop is on')
        page.wait_for_timeout(500)
        check('Live: E-STOP while armed disarms driving', STREAM.wait(lambda s: s['teleop']['armed'] is False, 3))
        if dialog().count():
            close_dialog()
        page.get_by_role('button', name='Release e-stop').first.click()
        dialog().get_by_role('button', name='Release e-stop').click()
        expect(page.get_by_role('alert')).to_have_count(0)
        # battery drops while armed
        bridge('fake_battery', percent=30)
        go('live')
        page.get_by_role('button', name='Arm driving').click()
        dialog().get_by_label(re.compile('I am next to the robot')).check()
        dialog().get_by_role('button', name='Arm driving').click()
        expect(page.get_by_role('button', name=re.compile('^Disarm')).first).to_be_visible(timeout=8000)
        bridge('fake_battery', percent=7)
        check('Live: a battery below 8 % disarms driving', STREAM.wait(lambda s: s['teleop']['armed'] is False, 5))
        bridge('fake_battery', percent=None)
        clean('Live')

    # ---------------------------------------------------------------- Charts and Events
    with section('Charts and Events'):
        go('charts')
        page.wait_for_timeout(2500)
        canv = page.evaluate("""() => [...document.querySelectorAll('main canvas')].map(c => { const g = c.getContext('2d');
            const d = g.getImageData(0, 0, c.width, c.height).data; let n = 0;
            for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n; })""")
        check('Charts: six charts render with drawn pixels', len(canv) >= 6 and all(n > 100 for n in canv), str(canv))
        axe('Charts')
        shot('charts')
        page.get_by_role('button', name='Show events').click()
        expect(page.locator('body')).to_contain_text('Mark all as read')
        body = text('body')
        check('Events: the drawer shows an alert (e-stop or battery)', re.search(r'E-stop|Battery|stop', body, re.I) is not None)
        axe('Events drawer')
        shot('events')
        clean('Charts')

    # ---------------------------------------------------------------- Logs
    with section('Logs'):
        page.get_by_role('button', name='Hide events').first.click()
        go('logs')
        page.get_by_role('button', name='Fetch log').click()
        expect(page.locator('main')).to_contain_text('turtlebot4.service', timeout=15000)
        check('Logs: fetch shows lines', 'Nothing fetched yet' not in text('main'))
        axe('Logs')
        shot('logs')
        clean('Logs')

    # ---------------------------------------------------------------- palette and theme
    with section('palette and theme'):
        page.keyboard.press('Control+k')
        expect(dialog()).to_contain_text('Command palette')
        page.keyboard.type('topics')
        page.keyboard.press('Enter')
        page.wait_for_timeout(600)
        check('Ctrl+K palette: typing "topics" and Enter opens Topics', page.url.endswith('/topics'), page.url)
        page.get_by_role('button', name='Colour theme').click()
        page.get_by_role('menuitemradio', name=re.compile('Dark')).click()
        check('Theme: choosing Dark sets data-theme', page.evaluate("document.documentElement.getAttribute('data-theme')") == 'dark')
        page.get_by_role('button', name='Colour theme').click()
        page.get_by_role('menuitemradio', name=re.compile('Light')).click()
        check('Theme: choosing Light sets data-theme', page.evaluate("document.documentElement.getAttribute('data-theme')") == 'light')
        clean('palette and theme')

    # ---------------------------------------------------------------- phone width, every screen
    with section('phone width, every screen'):
        page.set_viewport_size({'width': 390, 'height': 844})
        for r in ('overview', 'live', 'programs', 'code', 'files', 'charts', 'logs', 'wifi', 'topics', 'tools', 'settings'):
            go(r)
            page.wait_for_timeout(300)
            no_overflow('phone, ' + r)
            box = page.get_by_role('button', name=re.compile('^Emergency stop')).bounding_box()
            check('phone: E-STOP is on screen, ' + r, box is not None and box['x'] >= 0 and box['x'] + box['width'] <= 390 and 0 <= box['y'] < 100, str(box))
            if SHOTS:
                page.screenshot(path=os.path.join(SHOTS, 'phone-%s-light.png' % r))
        go('overview')
        page.get_by_role('button', name='Dock', exact=True).click()
        page.wait_for_timeout(500)
        db = dialog().bounding_box()
        check('phone: the motion dialog fits the screen', db is not None and db['x'] >= 0 and db['x'] + db['width'] <= 390 and db['y'] + db['height'] <= 844, str(db))
        top = page.evaluate("""() => { const r = document.querySelector('.estop').getBoundingClientRect();
            const e = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return !!(e && e.closest('.estop')); }""")
        check('phone: E-STOP stays clickable (not covered) with a dialog open', top is True)
        dialog().get_by_role('button', name='Cancel').click()
        page.goto('%s/?token=%s&wizard=1' % (BASE, TOKEN))
        page.wait_for_timeout(1500)
        check('phone: the wizard opens with ?wizard=1', dialog().count() == 1)
        if dialog().count():
            db = dialog().bounding_box()
            check('phone: the wizard dialog fits the screen', db is not None and db['x'] >= 0 and db['x'] + db['width'] <= 390 and db['y'] + db['height'] <= 844, str(db))
            no_overflow('phone, wizard open')
            dialog().get_by_role('button', name='Close', exact=True).last.click()
        page.set_viewport_size({'width': 1366, 'height': 860})
        clean('phone width')

    # ---------------------------------------------------------------- classic 1.3 UI
    with section('classic 1.3 UI'):
        page.goto('%s/classic/?token=%s' % (BASE, TOKEN))
        page.wait_for_timeout(1500)
        check('/classic/ loads the 1.3 interface', 'TurtleBot' in page.title() or 'TurtleBot' in text('body'), page.title())
        check('/classic/ is not the 2.0 interface', page.locator('#root').count() == 0 or page.locator('.estop').count() == 0)
        r = urllib.request.urlopen(BASE + '/classic/', timeout=10).read().decode('utf-8', 'replace')
        check('/classic/ serves the 1.3 page', 'app.js' in r and 'assets/index-' not in r)
        r2 = urllib.request.urlopen('%s/?token=%s' % (BASE, TOKEN), timeout=10).read().decode('utf-8', 'replace')
        check('/ serves the 2.0 page', 'assets/index-' in r2 or '/v2/assets/' in r2)
        clean('/classic/')
        del errors[:]


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
