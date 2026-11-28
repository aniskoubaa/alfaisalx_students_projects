"""Opens Studio's own window, keeps one Studio per user (instance file) and stops the built
app when its last page closes.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip


def say(*parts):
    """print() that never fails: the windowed (no console) build has sys.stdout = None or a closed pipe."""
    try:
        if sys.stdout is not None:
            print(*parts, flush=True)
    except (OSError, ValueError, AttributeError):
        pass


def browser_candidates(system, env, home=''):
    """Edge/Chrome/Chromium programs to try, best first. system: 'win32' | 'darwin' | 'linux'. Pure."""
    if system == 'win32':
        out = []
        for var, rel in (('ProgramFiles(x86)', 'Microsoft\\Edge\\Application\\msedge.exe'),
                         ('ProgramFiles', 'Microsoft\\Edge\\Application\\msedge.exe'),
                         ('ProgramFiles', 'Google\\Chrome\\Application\\chrome.exe'),
                         ('ProgramFiles(x86)', 'Google\\Chrome\\Application\\chrome.exe'),
                         ('LOCALAPPDATA', 'Google\\Chrome\\Application\\chrome.exe'),
                         ('LOCALAPPDATA', 'Microsoft\\Edge\\Application\\msedge.exe')):
            base = env.get(var)
            if base:
                out.append(base.rstrip('\\/') + '\\' + rel)
        return out
    if system == 'darwin':
        apps = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                '/Applications/Chromium.app/Contents/MacOS/Chromium']
        if home:
            apps += [home.rstrip('/') + a for a in apps[:2]]
        return apps
    return ['microsoft-edge', 'microsoft-edge-stable', 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']


def app_window_argv(browser_exe, url, profile_dir):
    """argv that opens url as a bare app window (no tabs or address bar) with its own browser profile. Pure."""
    return [browser_exe, '--app=' + url, '--user-data-dir=' + profile_dir, '--no-first-run', '--no-default-browser-check']


def find_app_browser(system, env, exists=os.path.isfile, which=shutil.which, home=''):
    """First installed Edge/Chrome/Chromium, or None. exists/which are injectable for tests."""
    for c in browser_candidates(system, env, home):
        if system == 'linux':
            found = which(c)
            if found:
                return found
        elif exists(c):
            return c
    return None


def window_command(system, mode, url, profile_dir, env=None, exists=os.path.isfile, which=shutil.which, home=''):
    """argv of the app window to open, or None when the normal browser should be used instead. Pure."""
    if mode != 'app':
        return None
    exe = find_app_browser(system, os.environ if env is None else env, exists, which, home)
    return app_window_argv(exe, url, profile_dir) if exe else None


def open_window(url, mode, cfg_dir):
    """Open Studio in its own window (Edge/Chrome --app) or, failing that, the default browser. Returns 'app' | 'browser' | None."""
    system = 'win32' if IS_WIN else ('darwin' if sys.platform == 'darwin' else 'linux')
    argv = window_command(system, mode, url, os.path.join(cfg_dir, 'window'), home=os.path.expanduser('~'))
    if argv:
        try:
            kw = {'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {'start_new_session': True}
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
            return 'app'
        except OSError:
            pass
    try:
        return 'browser' if webbrowser.open(url) else None
    except Exception:
        return None


def instance_path(cfg_dir):
    return os.path.join(cfg_dir, 'instance.json')


def write_instance(cfg_dir, port, token):
    """Record this running Studio so a second start can reuse its window. The config folder is private to the user."""
    info = {'pid': os.getpid(), 'port': port, 'token': token, 'version': VERSION, 'started': int(time.time())}
    tmp = instance_path(cfg_dir) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(info, f)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, instance_path(cfg_dir))


def read_instance(cfg_dir):
    try:
        with open(instance_path(cfg_dir), encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get('port'), int) and isinstance(d.get('token'), str):
            return d
    except (OSError, ValueError):
        pass
    return None


def remove_instance(cfg_dir, pid=None):
    """Delete instance.json (only if it is ours when pid is given)."""
    d = read_instance(cfg_dir)
    if pid is not None and d is not None and d.get('pid') != pid:
        return
    try:
        os.remove(instance_path(cfg_dir))
    except OSError:
        pass


def instance_alive(info, timeout=2.0):
    """True when the recorded Studio still answers with its token. A stale file (dead process, port reused) gives False."""
    if not info:
        return False
    try:
        c = http.client.HTTPConnection('127.0.0.1', info['port'], timeout=timeout)
        try:
            c.request('GET', '/api/settings', headers={'X-Studio-Token': info['token']})
            r = c.getresponse()
            body = r.read(200000)
        finally:
            c.close()
        return r.status == 200 and bool(json.loads(body.decode('utf-8')).get('version'))
    except (OSError, ValueError, http.client.HTTPException):
        return False


def stored_window_mode(cfg_dir):
    try:
        with open(os.path.join(cfg_dir, 'settings.json'), encoding='utf-8') as f:
            m = json.load(f).get('window_mode')
        return m if m in WINDOW_MODES else DEFAULT_WINDOW_MODE
    except (OSError, ValueError, AttributeError):
        return DEFAULT_WINDOW_MODE


def resolve_exit_when_closed(exit_flag, stay_flag, frozen, fake):
    """--stay-open wins, then --exit-when-closed; otherwise on only in the built app (and not in --fake demos). Pure."""
    if stay_flag:
        return False
    if exit_flag:
        return True
    return bool(frozen and not fake)


class CloseWatcher:
    """Decides when to stop because every Studio page was closed: after at least one page was seen, `grace`
    seconds with none connected. tick() is called about twice a second with the number of open event streams."""

    def __init__(self, grace=CLOSE_GRACE):
        self.grace = grace
        self.seen = False
        self.empty_since = None

    def tick(self, clients, now):
        if clients > 0:
            self.seen = True
            self.empty_since = None
            return False
        if not self.seen:
            return False
        if self.empty_since is None:
            self.empty_since = now
        return now - self.empty_since >= self.grace
