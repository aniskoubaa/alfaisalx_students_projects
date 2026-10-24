"""Offline tests of TurtleBot Studio 1.3 upgrades U5 (installer) and U6 (own window, no console):
app-window command per OS (pure), single instance (instance.json), exit when the window is closed, Quit Studio,
window_mode setting, version.json, installer script, Linux install script, workflow and spec.

No robot and no real browser is opened (--no-browser everywhere). The process tests start the real studio.py --fake.
Usage: python test_studio_window.py     (prints PASS/FAIL/SKIP, exit code = number of failures)
"""
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, STUDIO_DIR)
import studio as st  # noqa: E402

OUT = tempfile.mkdtemp(prefix='tb4_studio_win_')
fails = 0


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode())
    if not cond:
        fails += 1


def skip(name, why):
    print(f'SKIP {name}  [{why}]')


def read(*parts):
    with open(os.path.join(*parts), encoding='utf-8', newline='') as f:
        return f.read()


# ---------------------------------------------------------------- app window command (pure)
URL = 'http://127.0.0.1:8765/?token=abc'
PROF = '/cfg/window'
env_w = {'ProgramFiles': r'C:\Program Files', 'ProgramFiles(x86)': r'C:\Program Files (x86)', 'LOCALAPPDATA': r'C:\Users\u\AppData\Local'}
edge_x86 = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
chrome_pf = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
chrome_la = r'C:\Users\u\AppData\Local\Google\Chrome\Application\chrome.exe'

a = st.window_command('win32', 'app', URL, PROF, env=env_w, exists=lambda p: p in (edge_x86, chrome_pf))
check('windows: Edge is preferred when both exist', a and a[0] == edge_x86, str(a))
check('windows: --app=URL, own --user-data-dir, no first-run, no default-browser check',
      a[1:] == ['--app=' + URL, '--user-data-dir=' + PROF, '--no-first-run', '--no-default-browser-check'], str(a))
a = st.window_command('win32', 'app', URL, PROF, env=env_w, exists=lambda p: p == chrome_pf)
check('windows: Chrome in Program Files when there is no Edge', a and a[0] == chrome_pf, str(a))
a = st.window_command('win32', 'app', URL, PROF, env=env_w, exists=lambda p: p == chrome_la)
check('windows: Chrome in LocalAppData is found', a and a[0] == chrome_la, str(a))
check('windows: no browser installed -> None (fall back to the default browser)',
      st.window_command('win32', 'app', URL, PROF, env=env_w, exists=lambda p: False) is None)
check('windows: no environment variables -> None, no crash', st.window_command('win32', 'app', URL, PROF, env={}, exists=lambda p: True) is None)
check('window_mode browser -> None even when Edge exists',
      st.window_command('win32', 'browser', URL, PROF, env=env_w, exists=lambda p: True) is None)

chrome_mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
edge_mac = '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
a = st.window_command('darwin', 'app', URL, PROF, env={}, exists=lambda p: p == edge_mac)
check('macOS: Edge app found', a and a[0] == edge_mac and a[1] == '--app=' + URL, str(a))
a = st.window_command('darwin', 'app', URL, PROF, env={}, exists=lambda p: p in (chrome_mac, edge_mac))
check('macOS: Chrome first', a and a[0] == chrome_mac, str(a))
a = st.window_command('darwin', 'app', URL, PROF, env={}, exists=lambda p: p == '/Users/u' + edge_mac, home='/Users/u')
check('macOS: per-user Applications folder is searched', a and a[0] == '/Users/u' + edge_mac, str(a))
check('macOS: nothing installed -> None', st.window_command('darwin', 'app', URL, PROF, env={}, exists=lambda p: False) is None)

installed = {'chromium': '/usr/bin/chromium', 'google-chrome': '/usr/bin/google-chrome'}
a = st.window_command('linux', 'app', URL, PROF, env={}, which=lambda n: installed.get(n))
check('linux: google-chrome comes before chromium', a and a[0] == '/usr/bin/google-chrome' and '--user-data-dir=' + PROF in a, str(a))
check('linux: nothing on PATH -> None', st.window_command('linux', 'app', URL, PROF, env={}, which=lambda n: None) is None)

# ---------------------------------------------------------------- exit-when-closed logic (pure)
w = st.CloseWatcher(45)
check('closewatcher: no page ever seen -> never stops', not any(w.tick(0, t) for t in (0, 100, 1000)))
w = st.CloseWatcher(45)
w.tick(1, 0)
check('closewatcher: page open -> keeps running', not w.tick(1, 500))
check('closewatcher: page closed, inside the grace -> keeps running', not w.tick(0, 510) and not w.tick(0, 554))
check('closewatcher: page closed for the full grace -> stop', w.tick(0, 555.5))
w = st.CloseWatcher(45)
w.tick(1, 0)
w.tick(0, 10)
w.tick(1, 30)
check('closewatcher: a page reopening (reload) restarts the grace', not w.tick(0, 40) and not w.tick(0, 80) and w.tick(0, 85.1))
check('default grace is 45 s', st.CLOSE_GRACE == 45.0 and st.CloseWatcher().grace == 45.0)
r = st.resolve_exit_when_closed
check('exit-when-closed: built app default on, source default off, fake default off',
      r(False, False, True, False) is True and r(False, False, False, False) is False and r(False, False, True, True) is False)
check('exit-when-closed: flags win (--stay-open beats --exit-when-closed)',
      r(True, False, False, True) is True and r(False, True, True, False) is False and r(True, True, True, False) is False)

# ---------------------------------------------------------------- instance.json helpers and settings
d = os.path.join(OUT, 'inst')
os.makedirs(d)
check('instance: nothing there -> None', st.read_instance(d) is None)
st.write_instance(d, 4321, 'tok123')
i = st.read_instance(d)
check('instance: written with pid, port, token, version, started',
      i and i['pid'] == os.getpid() and i['port'] == 4321 and i['token'] == 'tok123' and i['version'] == st.VERSION and i['started'] > 0, str(i))
st.remove_instance(d, os.getpid() + 1)
check('instance: another pid cannot remove it', st.read_instance(d) is not None)
st.remove_instance(d, os.getpid())
check('instance: own pid removes it', st.read_instance(d) is None)
with open(st.instance_path(d), 'w') as f:
    f.write('{not json')
check('instance: garbage file is ignored', st.read_instance(d) is None)
st.write_instance(d, 1, 'x')
check('instance: a recorded Studio that does not answer is stale', st.instance_alive(st.read_instance(d), timeout=1.0) is False)
check('instance: None is not alive', st.instance_alive(None) is False)

cd = os.path.join(OUT, 'wm')
os.makedirs(cd)
with open(os.path.join(cd, 'settings.json'), 'w') as f:
    json.dump({'window_mode': 'browser'}, f)
check('stored_window_mode reads the saved choice', st.stored_window_mode(cd) == 'browser')
with open(os.path.join(cd, 'settings.json'), 'w') as f:
    json.dump({'window_mode': 'weird'}, f)
check('stored_window_mode: unknown value -> app', st.stored_window_mode(cd) == 'app' and st.stored_window_mode(os.path.join(OUT, 'nope')) == 'app')
app = st.Studio(st.parse_args(['--fake', '--config-dir', cd, '--fake-home', os.path.join(cd, 'home')]))
check('window_mode: invalid saved value loads as app', app.settings['window_mode'] == 'app')
check('window_mode: invalid POST is refused', app.post_settings({'window_mode': 'popup'}).get('ok') is False)
j = app.post_settings({'window_mode': 'browser'})
check('window_mode: browser accepted and saved', j.get('ok') and app.get_settings()['window_mode'] == 'browser' and read(cd, 'settings.json').count('"window_mode": "browser"') == 1)
check('diagnostics mention window_mode', 'window_mode' in app.diagnostics()['text'])
app.shutdown()

# ---------------------------------------------------------------- say() never raises without a console
old_out = sys.stdout
sys.stdout = None
try:
    st.say('no console')
    ok = True
except Exception:
    ok = False
sys.stdout = old_out
check('say() is silent when sys.stdout is None (windowed build)', ok)

# ---------------------------------------------------------------- files: version.json, installer, linux script, spec, workflow
vj = json.loads(read(STUDIO_DIR, 'version.json'))
check('version.json version == studio.VERSION', vj['version'] == st.VERSION, '%s vs %s' % (vj['version'], st.VERSION))
nsi = read(STUDIO_DIR, 'packaging', 'installer.nsi')
check('installer.nsi: version define from /DAPP_VERSION=', '${APP_VERSION}' in nsi and '!ifndef APP_VERSION' in nsi)
check('installer.nsi: RequestExecutionLevel user, per-user folder', re.search(r'(?m)^RequestExecutionLevel user\s*$', nsi) and r'$LOCALAPPDATA\Programs\TurtleBot Studio' in nsi)
check('installer.nsi: MUI2, fixed uninstall key with the required values',
      '!include "MUI2.nsh"' in nsi and r'Software\Microsoft\Windows\CurrentVersion\Uninstall\TurtleBotStudio' in nsi
      and all(x in nsi for x in ('DisplayName', 'DisplayVersion', 'Publisher', 'AlfaisalX Lab', 'DisplayIcon', 'UninstallString', 'NoModify', 'NoRepair')))
check('installer.nsi: shortcuts, desktop component, launch on finish', all(x in nsi for x in ('$SMPROGRAMS', '$DESKTOP', 'MUI_FINISHPAGE_RUN', 'Launch TurtleBot Studio')))
check('installer.nsi: uninstaller keeps %APPDATA%\\TurtleBotStudio and says so', r'$APPDATA\TurtleBotStudio' in nsi and 'RMDir /r "$APPDATA' not in nsi and 'RMDir /r "$LOCALAPPDATA' not in nsi)
check('installer.nsi: output name TurtleBotStudio-Setup-<version>.exe', 'TurtleBotStudio-Setup-${APP_VERSION}.exe' in nsi)
check('installer.nsi: no password, key or token text', not re.search(r'(?i)password\s*=|BEGIN [A-Z ]*PRIVATE|token=', nsi))
spec = read(STUDIO_DIR, 'packaging', 'studio.spec')
check('spec: windowed on Windows and macOS, console kept on Linux, macOS .app BUNDLE',
      'console=' in spec and 'BUNDLE(' in spec and "'darwin'" in spec and 'win32' in spec)
sh_path = os.path.join(STUDIO_DIR, 'packaging', 'install-linux.sh')
sh = read(STUDIO_DIR, 'packaging', 'install-linux.sh')
check('install-linux.sh: LF line endings, add-only paths, undo text',
      '\r' not in sh and '.local/bin' in sh and 'turtlebot-studio' in sh and '.local/share/applications' in sh and 'turtlebot-studio.desktop' in sh and 'rm ' in sh and 'sudo' not in sh)
bash = shutil.which('bash')
if bash:
    p = subprocess.run([bash, '-n', sh_path], capture_output=True, text=True)
    check('install-linux.sh: bash -n passes', p.returncode == 0, p.stderr.strip())
else:
    skip('install-linux.sh: bash -n', 'no bash on PATH')
wf = read(REPO, '.github', 'workflows', 'turtlebot-studio-build.yml')
check('workflow: installs NSIS, builds the installer, uploads setup exe, macOS zip and Linux script',
      'choco install nsis -y' in wf and '--installer' in wf and 'TurtleBotStudio-Setup' in wf and 'TurtleBotStudio-macOS.zip' in wf and 'install-linux.sh' in wf)
check('workflow: read-only permissions and no release step', re.search(r'(?m)^permissions:\n  contents: read', wf) and 'contents: write' not in wf.split('# Releasing later')[0])
check('workflow: runs the new window tests too', 'test_studio_window.py' in wf and 'test_studio_upgrades.py' in wf)
bp = read(STUDIO_DIR, 'packaging', 'build.py')
check('build.py: --installer, makensis lookup, instance.json + --version-file in the smoke test',
      '--installer' in bp and 'makensis' in bp and 'instance.json' in bp and '--version-file' in bp and '--stay-open' in bp)
check('packaging/.gitignore keeps build output and the generated icon out of git', 'dist/' in read(STUDIO_DIR, 'packaging', '.gitignore') and 'studio.ico' in read(STUDIO_DIR, 'packaging', '.gitignore'))

# ---------------------------------------------------------------- real processes: single instance, quit, exit when closed
PROCS = []


def start(cfg, *extra, stdout=None):
    argv = [sys.executable, '-u', os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--port', '0', '--config-dir', cfg,
            '--fake-home', os.path.join(cfg, 'home'), '--heartbeat', '1', *extra]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    p = subprocess.Popen(argv, stdout=stdout or subprocess.DEVNULL, stderr=subprocess.STDOUT, env=env)
    PROCS.append(p)
    return p


def wait_instance(cfg, proc, timeout=20, not_pid=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        i = st.read_instance(cfg)
        if i and i['pid'] != not_pid and proc.poll() is None:
            return i
        if proc.poll() is not None:
            return None
        time.sleep(0.1)
    return None


def get_json(info, path, timeout=10):
    c = http.client.HTTPConnection('127.0.0.1', info['port'], timeout=timeout)
    c.request('GET', path, headers={'X-Studio-Token': info['token']})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, json.loads(body.decode('utf-8'))


def post_json(info, path, body=None, timeout=10):
    c = http.client.HTTPConnection('127.0.0.1', info['port'], timeout=timeout)
    c.request('POST', path, body=json.dumps(body or {}).encode(), headers={'X-Studio-Token': info['token'], 'Content-Type': 'application/json'})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, json.loads(data.decode('utf-8'))


def wait_exit(proc, timeout):
    try:
        return proc.wait(timeout)
    except subprocess.TimeoutExpired:
        return None


try:
    # --- single instance
    cfg = os.path.join(OUT, 'single')
    os.makedirs(cfg)
    p1 = start(cfg, '--stay-open')
    i1 = wait_instance(cfg, p1)
    check('first start writes instance.json with its own pid and token', i1 and i1['pid'] == p1.pid and i1['token'] and i1['port'] > 0, str(i1 and {k: v for k, v in i1.items() if k != 'token'}))
    if i1:
        t0 = time.time()
        p2 = start(cfg, '--stay-open')
        code2 = wait_exit(p2, 15)
        check('second start with the same config exits 0 quickly', code2 == 0 and time.time() - t0 < 10, 'code=%r after %.1f s' % (code2, time.time() - t0))
        check('the first instance is still running and answers', p1.poll() is None and get_json(i1, '/api/settings')[0] == 200)
        i1b = st.read_instance(cfg)
        check('instance.json still belongs to the first instance', i1b and i1b['pid'] == p1.pid and i1b['port'] == i1['port'])
        # a different config folder is a different Studio
        cfg_b = os.path.join(OUT, 'single_b')
        os.makedirs(cfg_b)
        pb = start(cfg_b, '--stay-open')
        ib = wait_instance(cfg_b, pb)
        check('another config folder starts its own instance', ib and ib['pid'] == pb.pid and ib['port'] != i1['port'])
        # --- stale file: kill hard, the file stays, a new start ignores it
        p1.kill()
        p1.wait(10)
        check('after a hard kill the stale instance.json is still there', st.read_instance(cfg) is not None)
        p3 = start(cfg, '--stay-open')
        i3 = wait_instance(cfg, p3, not_pid=p1.pid)
        check('a stale instance.json is ignored: the new start runs and rewrites it', i3 and i3['pid'] == p3.pid and p3.poll() is None, str(i3 and i3['pid']))
        # --- Quit endpoint
        if i3:
            st_code, res = post_json(i3, '/api/quit')
            check('POST /api/quit answers ok', st_code == 200 and res.get('ok') is True, str(res))
            code3 = wait_exit(p3, 15)
            check('Quit: the process ends cleanly (exit 0) and instance.json is gone', code3 == 0 and st.read_instance(cfg) is None, 'code=%r' % code3)
            st_code, _ = (None, None)
        st_b, _ = (None, None)
        if ib:
            c = http.client.HTTPConnection('127.0.0.1', ib['port'], timeout=5)
            c.request('POST', '/api/quit', body=b'{}', headers={'X-Studio-Token': 'wrong', 'Content-Type': 'application/json'})
            resp = c.getresponse()
            resp.read()
            c.close()
            check('Quit needs the session token', resp.status == 403 and pb.poll() is None, str(resp.status))
            post_json(ib, '/api/quit')
            wait_exit(pb, 15)

    # --- exit when closed
    cfg = os.path.join(OUT, 'closed')
    os.makedirs(cfg)
    log = open(os.path.join(OUT, 'closed.log'), 'wb')
    p = start(cfg, '--exit-when-closed', '--close-grace', '3', stdout=log)
    i = wait_instance(cfg, p)
    check('--exit-when-closed run starts', bool(i))
    if i:
        time.sleep(4.5)
        check('no page was ever opened: Studio keeps running past the grace time', p.poll() is None)
        s = http.client.HTTPConnection('127.0.0.1', i['port'], timeout=10)
        s.request('GET', '/api/events', headers={'X-Studio-Token': i['token']})
        resp = s.getresponse()
        first = resp.fp.readline()
        check('event stream opened', resp.status == 200 and first.startswith(b': hello'), repr(first))
        time.sleep(1.5)
        check('a page is open: Studio keeps running', p.poll() is None)
        resp.close()
        s.close()   # the window was closed
        t0 = time.time()
        code = wait_exit(p, 20)
        took = time.time() - t0
        check('window closed: Studio stops itself after the grace time, exit 0', code == 0 and 2.0 <= took <= 12.0, 'code=%r after %.1f s' % (code, took))
        check('window closed: instance.json removed', st.read_instance(cfg) is None)
        log.close()
        check('window closed: log says why it stopped', b'Stopped.' in open(os.path.join(OUT, 'closed.log'), 'rb').read() and 'No Studio window open' in read(cfg, 'studio.log'))

    # --- a reload (close and reopen within the grace) must not stop it
    cfg = os.path.join(OUT, 'reload')
    os.makedirs(cfg)
    p = start(cfg, '--exit-when-closed', '--close-grace', '4')
    i = wait_instance(cfg, p)
    if i:
        s = http.client.HTTPConnection('127.0.0.1', i['port'], timeout=10)
        s.request('GET', '/api/events', headers={'X-Studio-Token': i['token']})
        r1 = s.getresponse()
        r1.fp.readline()
        r1.close()
        s.close()
        time.sleep(2)
        s = http.client.HTTPConnection('127.0.0.1', i['port'], timeout=10)
        s.request('GET', '/api/events', headers={'X-Studio-Token': i['token']})
        r2 = s.getresponse()
        r2.fp.readline()
        time.sleep(4.5)
        check('a page reloaded inside the grace keeps Studio running', p.poll() is None)
        r2.close()
        s.close()
        post_json(i, '/api/quit')
        wait_exit(p, 15)
    else:
        check('reload run starts', False)
finally:
    for p in PROCS:
        if p.poll() is None:
            p.kill()
    for p in PROCS:
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            pass

shutil.rmtree(OUT, ignore_errors=True) if fails == 0 else print('generated files are in', OUT)
print('\n%d failure(s)' % fails)
sys.exit(fails)
