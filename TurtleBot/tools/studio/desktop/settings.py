"""Loading and saving settings, logging, connection state, and the settings page API.
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


class SettingsMixin:
    # ---------------------------------------------------------------- settings / logging
    def _load_settings(self):
        s = {'last_host': None, 'last_via': None, 'key_path': None, 'local_dir': None,
             'remote_dir': DEFAULT_REMOTE_DIR, 'motion_files': [], 'trust_host_key': None, 'known_addresses': {},
             'builtin_host_key': True, 'trusted_host_keys': [], 'setup_done': False,
             'auto_reconnect': True, 'update_check': True, 'update_last': {}, 'update_dismissed': None,
             'window_mode': DEFAULT_WINDOW_MODE, 'ui': 'v2', 'teleop_linear': TELEOP_DEFAULT_LINEAR,
             'teleop_angular': TELEOP_DEFAULT_ANGULAR}
        s.update(DEFAULT_SETTINGS)
        d = {}
        try:
            with open(os.path.join(self.cfg, 'settings.json'), encoding='utf-8') as f:
                d = json.load(f)
            if not isinstance(d, dict):
                d = {}
            for k in s:
                if k in d:
                    s[k] = d[k]
        except (OSError, ValueError):
            d = {}
        # keep the file's values only when they pass the same checks as POST /api/settings, else the default
        if not (isinstance(s['robot_hostname'], str) and DNS_LABEL_RE.match(s['robot_hostname'])):
            s['robot_hostname'] = DEFAULT_SETTINGS['robot_hostname']
        if not (isinstance(s['robot_user'], str) and USER_RE.match(s['robot_user'])):
            s['robot_user'] = DEFAULT_SETTINGS['robot_user']
        if not valid_ssid(s['hotspot_ssid']):
            s['hotspot_ssid'] = DEFAULT_SETTINGS['hotspot_ssid']
        for k in ('hotspot_addr', 'cable_addr'):
            if not (isinstance(s[k], str) and valid_host(s[k]) and '@' not in s[k]):
                s[k] = DEFAULT_SETTINGS[k]
        s['builtin_host_key'] = bool(s['builtin_host_key'])
        s['auto_reconnect'] = bool(s['auto_reconnect'])
        s['update_check'] = bool(s['update_check'])
        s['window_mode'] = s['window_mode'] if s['window_mode'] in WINDOW_MODES else DEFAULT_WINDOW_MODE
        s['ui'] = s['ui'] if s['ui'] in UI_CHOICES else 'v2'
        s['teleop_linear'] = limit_value(s['teleop_linear'], TELEOP_DEFAULT_LINEAR, TELEOP_MIN_LINEAR, TELEOP_MAX_LINEAR)
        s['teleop_angular'] = limit_value(s['teleop_angular'], TELEOP_DEFAULT_ANGULAR, TELEOP_MIN_ANGULAR, TELEOP_MAX_ANGULAR)
        ul = s['update_last'] if isinstance(s['update_last'], dict) else {}
        s['update_last'] = ({'t': float(ul['t']), 'latest': ul['latest']} if isinstance(ul.get('t'), (int, float))
                            and isinstance(ul.get('latest'), str) and VERSION_RE.match(ul['latest']) else {})
        ud = s['update_dismissed']
        s['update_dismissed'] = ud if isinstance(ud, str) and VERSION_RE.match(ud) else None
        tk = []
        for e in (s['trusted_host_keys'] if isinstance(s['trusted_host_keys'], list) else []):
            if isinstance(e, dict) and isinstance(e.get('key'), str) and KEY_LINE_RE.match(e['key']) \
                    and e['key'] not in [x['key'] for x in tk]:
                tk.append({'key': e['key'], 'label': str(e.get('label') or 'Robot')[:60], 'added': e.get('added')})
        old = s.get('trust_host_key')  # one-slot setting of v1.0/1.1: migrate into the list
        if isinstance(old, str) and KEY_LINE_RE.match(old.strip()):
            old = ' '.join(old.split()[:2])
            if old != LAB_HOST_KEY and old not in [x['key'] for x in tk]:
                tk.append({'key': old, 'label': LEGACY_TRUST_LABEL, 'added': int(time.time())})
        s['trust_host_key'] = None
        s['trusted_host_keys'] = tk
        # a config that already knows a robot has been set up before: no wizard for existing users
        s['setup_done'] = bool(d['setup_done']) if 'setup_done' in d else bool(d.get('last_host'))
        return s

    def save_settings(self):
        tmp = os.path.join(self.cfg, 'settings.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=2)
        os.replace(tmp, os.path.join(self.cfg, 'settings.json'))

    def user(self):
        return self.settings.get('robot_user') or ROBOT_USER

    def trusted_keys(self):
        """Every key ssh may accept for the robot alias: the built-in one (unless switched off) + the user's own list."""
        keys = [LAB_HOST_KEY] if self.settings.get('builtin_host_key', True) else []
        for e in self.settings.get('trusted_host_keys') or []:
            if e['key'] not in keys:
                keys.append(e['key'])
        return keys

    def write_known_hosts(self):
        want = ''.join('%s %s\n' % (PIN_ALIAS, k) for k in self.trusted_keys())
        try:
            with open(self.known_hosts, encoding='utf-8') as f:
                if f.read() == want:
                    return
        except OSError:
            pass
        with open(self.known_hosts, 'w', encoding='utf-8', newline='\n') as f:
            f.write(want)

    def log(self, level, text):
        self.bus.publish({'ev': 'log', 'level': level, 'text': text, 't': time.time()})
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write('%s %s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), level, text))
        except OSError:
            pass

    def conn(self, state, host=None, via=None, error=None, **extra):
        if self.reconn is not None and state in ('connecting', 'error', 'disconnected'):
            return  # an automatic reconnect is running: the banner shows it, not every failed try
        ev = {'ev': 'conn', 'state': state, 'host': host, 'via': via, 'error': error}
        ev.update(extra)
        self.bus.publish(ev)

    def get_settings(self):
        s = dict(self.settings)
        s.update({'ok': True, 'default_key': self.default_key(), 'config_dir': self.cfg, 'fake': self.fake,
                  'version': VERSION, 'motion_defaults': MOTION_FILES, 'pinned_host_key': LAB_HOST_KEY,
                  'lab_host_key': LAB_HOST_KEY, 'defaults': dict(DEFAULT_SETTINGS), 'trusted': self.trusted_list(),
                  'default_remote_dir': DEFAULT_REMOTE_DIR})
        return s

    def post_settings(self, req):
        with self.set_lock:
            upd, trust_add, trust_clear = {}, None, False
            for k in ('last_host', 'key_path', 'local_dir', 'remote_dir', 'motion_files', 'trust_host_key', 'robot_hostname',
                      'robot_user', 'hotspot_ssid', 'hotspot_addr', 'cable_addr', 'builtin_host_key', 'setup_done',
                      'auto_reconnect', 'update_check', 'update_dismissed', 'window_mode', 'ui'):
                if k not in req:
                    continue
                v = req[k]
                if k == 'motion_files':
                    if not isinstance(v, list) or not all(isinstance(x, str) and '/' not in x for x in v):
                        return {'ok': False, 'error': 'motion_files must be a list of file names'}
                elif k == 'trust_host_key':  # old one-slot setting: now an entry of trusted_host_keys
                    if v in (None, ''):
                        trust_clear = True
                    elif not KEY_LINE_RE.match(str(v).strip()):
                        return {'ok': False, 'error': 'host key must look like: ssh-ed25519 AAAA...'}
                    else:
                        trust_add = ' '.join(str(v).split()[:2])
                    continue
                elif k in ('builtin_host_key', 'setup_done', 'auto_reconnect', 'update_check'):
                    if not isinstance(v, bool):
                        return {'ok': False, 'error': k + ' must be true or false'}
                elif k == 'window_mode':
                    if v not in WINDOW_MODES:
                        return {'ok': False, 'error': 'window_mode must be app or browser'}
                elif k == 'ui':
                    if v not in UI_CHOICES:
                        return {'ok': False, 'error': 'ui must be v2 or classic'}
                elif k == 'update_dismissed':
                    if v not in (None, '') and not (isinstance(v, str) and VERSION_RE.match(v)):
                        return {'ok': False, 'error': 'update_dismissed must be a version number'}
                elif k in DEFAULT_SETTINGS:
                    v = DEFAULT_SETTINGS[k] if v in (None, '') else v
                    ok = isinstance(v, str)
                    if ok and k == 'robot_hostname':
                        ok = bool(DNS_LABEL_RE.match(v))
                    elif ok and k == 'robot_user':
                        ok = bool(USER_RE.match(v))
                    elif ok and k == 'hotspot_ssid':
                        ok = valid_ssid(v)
                    elif ok:
                        ok = valid_host(v) and '@' not in v
                    if not ok:
                        return {'ok': False, 'error': 'invalid ' + k.replace('_', ' ')}
                elif k == 'last_host':
                    if v and not valid_host(v):
                        return {'ok': False, 'error': 'invalid host'}
                elif v is not None and not isinstance(v, str):
                    return {'ok': False, 'error': k + ' must be text'}
                upd[k] = (v or None) if k not in ('motion_files', 'builtin_host_key', 'setup_done', 'auto_reconnect', 'update_check') else v
            self.settings.update(upd)
            if not self.settings.get('remote_dir'):
                self.settings['remote_dir'] = DEFAULT_REMOTE_DIR
            if trust_clear:
                self.settings['trusted_host_keys'] = [e for e in self.settings['trusted_host_keys'] if e.get('label') != LEGACY_TRUST_LABEL]
            if trust_add:
                self._add_trusted(trust_add, LEGACY_TRUST_LABEL)
            self.save_settings()
            self.write_known_hosts()
        if trust_add:
            self.log('warn', 'a different robot host key is trusted (settings): only do this for another TurtleBot')
        return self.get_settings()
