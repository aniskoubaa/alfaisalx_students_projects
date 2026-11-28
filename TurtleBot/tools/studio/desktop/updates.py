"""The update notice: asks GitHub whether a newer Studio exists.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip
from .wifi_scripts import *  # bundle: skip
from .laptop_network import *  # bundle: skip
from .programs import *  # bundle: skip
from .events import *  # bundle: skip
from .alerts import *  # bundle: skip
from .mapping import *  # bundle: skip
from .bridge_process import *  # bundle: skip
from .connection import *  # bundle: skip
from .forwarding import *  # bundle: skip
from .telemetry import *  # bundle: skip
from .file_sync import *  # bundle: skip
from .terminals import *  # bundle: skip
from .settings import *  # bundle: skip
from .trust import *  # bundle: skip
from .map_api import *  # bundle: skip


class UpdatesMixin:
    # ---------------------------------------------------------------- v1.3: update notice
    def update_status(self):
        with self.update_lock:
            u = dict(self.update)
        newer = bool(u['latest']) and version_newer(u['latest'], VERSION)
        return {'ok': True, 'current': VERSION, 'latest': u['latest'], 'page': u['page'] or DEFAULT_UPDATE_PAGE,
                'notes': u['notes'], 'newer': newer, 'checked': u['checked'], 'error': u['error'],
                'dismissed': self.settings.get('update_dismissed')}

    def check_updates(self, force=False):
        """Reads version.json from GitHub (or STUDIO_UPDATE_URL): at most once a day unless forced. Sends nothing
        about this computer. Every failure (offline, file not published yet) is silent apart from one log line."""
        if not force:
            last = (self.settings.get('update_last') or {}).get('t') or 0
            if not self.settings.get('update_check', True) or time.time() - last < UPDATE_EVERY:
                return self.update_status()
        url = os.environ.get('STUDIO_UPDATE_URL') or DEFAULT_UPDATE_URL
        info, err = None, None
        try:
            parts = urllib.parse.urlsplit(url)
            if parts.scheme not in ('http', 'https') or not parts.hostname:
                raise ValueError('not an http(s) address')
            req = urllib.request.Request(url, headers={'User-Agent': 'TurtleBotStudio/' + VERSION})
            local = parts.hostname in ('127.0.0.1', 'localhost', '::1')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if local else urllib.request.build_opener()
            with opener.open(req, timeout=5) as r:
                raw = r.read(65536)
            info = parse_update_info(raw)
            if info is None:
                err = 'the version file is not understood'
        except Exception as e:
            err = str(e)[:120] or type(e).__name__
        now = time.time()
        with self.update_lock:
            self.update['checked'] = now
            if info:
                self.update.update(latest=info['version'], page=info['page'], notes=info['notes'], error=None)
            else:
                self.update['error'] = err
        if info:
            with self.set_lock:
                self.settings['update_last'] = {'t': now, 'latest': info['version']}
                self.save_settings()
        elif not self._update_logged:
            self._update_logged = True
            self.log('info', 'update check skipped: %s' % err)
        st = self.update_status()
        st['result'] = 'failed' if not info else 'newer' if st['newer'] else 'latest'
        if st['newer']:
            self.bus.publish({'ev': 'update', 'current': VERSION, 'latest': st['latest'], 'page': st['page'], 'notes': st['notes']})
        return st

    def start_update_check(self):
        """5 s after start (hidden --update-delay), in the background. Not in --fake unless STUDIO_UPDATE_URL is set."""
        if self.fake and not os.environ.get('STUDIO_UPDATE_URL'):
            return
        t = threading.Timer(self.update_delay, self.check_updates)
        t.daemon = True
        t.start()
