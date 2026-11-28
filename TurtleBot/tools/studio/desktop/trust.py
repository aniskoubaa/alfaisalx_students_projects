"""The ssh key, the trusted host keys and the first-run setup wizard.
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


class TrustMixin:
    # ---------------------------------------------------------------- keys / executables
    def default_key(self):
        std = os.path.expanduser('~/.ssh/turtlebot4_ed25519')
        return std if os.path.isfile(std) else os.path.join(self.cfg, 'id_ed25519')

    def key_path(self, create=True):
        k = self.settings.get('key_path') or self.default_key()
        k = os.path.expanduser(k)
        if create and not os.path.isfile(k):
            if k != os.path.join(self.cfg, 'id_ed25519') and self.settings.get('key_path'):
                raise BridgeError('key file not found: ' + k)
            kg = find_exe('ssh-keygen')
            if not kg:
                raise BridgeError('ssh-keygen not found (install the OpenSSH client)')
            r = subprocess.run([kg, '-t', 'ed25519', '-N', '', '-f', k, '-C', 'turtlebot-studio'],
                               capture_output=True, text=True, timeout=30, **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
            if r.returncode != 0:
                raise BridgeError('ssh-keygen failed: ' + (r.stderr or r.stdout).strip()[-200:])
            self.log('info', 'created a new ssh key for this app: ' + k)
        return k

    def public_key_line(self):
        k = self.key_path()
        try:
            with open(k + '.pub', encoding='utf-8') as f:
                line = f.read().strip()
        except OSError:
            kg = find_exe('ssh-keygen')
            r = subprocess.run([kg, '-y', '-f', k], capture_output=True, text=True, timeout=15, **hide_flags()) if kg else None
            line = (r.stdout.strip() if r and r.returncode == 0 else '')
        if not PUB_LINE_RE.match(line):
            raise BridgeError('public key file missing or not understood: ' + k + '.pub')
        return line

    def trusted_list(self):
        out = [{'key': LAB_HOST_KEY, 'label': 'Built-in robot key', 'builtin': True,
                'enabled': bool(self.settings.get('builtin_host_key', True)), 'fingerprint': key_fingerprint(LAB_HOST_KEY),
                'added': None}]
        for e in self.settings.get('trusted_host_keys') or []:
            out.append({'key': e['key'], 'label': e.get('label') or 'Robot', 'builtin': False, 'enabled': True,
                        'fingerprint': key_fingerprint(e['key']), 'added': e.get('added')})
        return out

    def trusted_label(self, key):
        """Label of a trusted key (built-in key counts only while it is switched on), else None."""
        for e in self.trusted_list():
            if e['key'] == key and e['enabled']:
                return e['label']
        return None

    def _add_trusted(self, key, label):
        """Caller holds set_lock. The built-in key is switched on instead of being listed twice."""
        if key == LAB_HOST_KEY:
            self.settings['builtin_host_key'] = True
            return
        for e in self.settings['trusted_host_keys']:
            if e['key'] == key:
                e['label'] = label
                return
        self.settings['trusted_host_keys'].append({'key': key, 'label': label, 'added': int(time.time())})

    # ---------------------------------------------------------------- v1.2: first-run wizard
    def ssh_version(self, ssh):
        if self._ssh_ver is not None and self._ssh_ver[0] == ssh:
            return self._ssh_ver[1]
        ver = None
        try:
            r = subprocess.run([ssh, '-V'], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL, **hide_flags())
            lines = ((r.stderr or '') + (r.stdout or '')).strip().splitlines()
            ver = lines[0].strip()[:120] if lines else None
        except (OSError, subprocess.TimeoutExpired):
            pass
        self._ssh_ver = (ssh, ver)
        return ver

    def key_info(self):
        k = os.path.expanduser(self.settings.get('key_path') or self.default_key())
        exists, fp = os.path.isfile(k), None
        if exists:
            try:
                with open(k + '.pub', encoding='utf-8') as f:
                    line = f.read().strip()
                if PUB_LINE_RE.match(line):
                    fp = key_fingerprint(line)
            except OSError:
                pass
        return {'path': k, 'exists': exists, 'fingerprint': fp}

    def setup_status(self):
        ssh = find_exe('ssh')
        osname = 'windows' if IS_WIN else ('macos' if sys.platform == 'darwin' else 'linux')
        return {'ok': True, 'ssh': {'found': bool(ssh), 'path': ssh, 'version': self.ssh_version(ssh) if ssh else None},
                'keygen': {'found': bool(find_exe('ssh-keygen'))}, 'keyscan': {'found': bool(find_exe('ssh-keyscan'))},
                'key': self.key_info(), 'host': self.settings.get('last_host'), 'setup_done': bool(self.settings.get('setup_done')),
                'fake': self.fake, 'os': osname, 'user': self.user()}

    def create_key(self):
        try:
            k = os.path.expanduser(self.settings.get('key_path') or self.default_key())
            existed = os.path.isfile(k)
            self.key_path(create=True)
        except (BridgeError, OSError, subprocess.TimeoutExpired) as e:
            return {'ok': False, 'error': str(e)}
        info = self.key_info()
        return {'ok': True, 'path': info['path'], 'fingerprint': info['fingerprint'], 'created': not existed}

    def scan_host_key(self, req):
        host = strip_user(str(req.get('host') or self.settings.get('last_host') or '').strip())
        if not host or not valid_host(host):
            return {'ok': False, 'error': 'enter the robot address first', 'kind': 'other'}
        if self.fake:
            key = FAKE_HOST_KEY
        else:
            ks = find_exe('ssh-keyscan')
            if not ks:
                return {'ok': False, 'error': 'ssh-keyscan not found (install the OpenSSH client)', 'kind': 'no_ssh'}
            try:
                r = subprocess.run([ks, '-T', '6', '-t', 'ed25519', host], capture_output=True, text=True, timeout=15,
                                   stdin=subprocess.DEVNULL, **hide_flags())
            except (OSError, subprocess.TimeoutExpired) as e:
                return {'ok': False, 'error': 'could not run ssh-keyscan: %s' % e, 'kind': 'other'}
            key = parse_keyscan(r.stdout)
            if not key:
                return {'ok': False, 'kind': 'unreachable', 'error': 'no host key received from %s (is the robot on and reachable, '
                                                                      'and is SSH running?)' % host}
        label = self.trusted_label(key)
        return {'ok': True, 'host': host, 'key': key, 'fingerprint': key_fingerprint(key), 'trusted': label is not None,
                'label': label}

    def trust_key(self, req):
        key = req.get('key')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not isinstance(key, str) or not KEY_LINE_RE.match(key.strip()):
            return {'ok': False, 'error': 'host key must look like: ssh-ed25519 AAAA...'}
        key = ' '.join(key.split()[:2])
        label = ''.join(c for c in str(req.get('label') or '') if c.isprintable()).strip()[:60] or 'Robot'
        with self.set_lock:
            self._add_trusted(key, label)
            self.save_settings()
            self.write_known_hosts()
        self.log('info', 'trusted a robot host key (%s, %s)' % (label, key_fingerprint(key)))
        return {'ok': True, 'key': key, 'fingerprint': key_fingerprint(key), 'label': label, 'trusted': self.trusted_list()}

    def untrust_key(self, req):
        key = req.get('key')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not isinstance(key, str) or not KEY_LINE_RE.match(key.strip()):
            return {'ok': False, 'error': 'host key must look like: ssh-ed25519 AAAA...'}
        key = ' '.join(key.split()[:2])
        with self.set_lock:
            if key == LAB_HOST_KEY:
                self.settings['builtin_host_key'] = False
            else:
                keep = [e for e in self.settings['trusted_host_keys'] if e['key'] != key]
                if len(keep) == len(self.settings['trusted_host_keys']):
                    return {'ok': False, 'error': 'that key is not in the trusted list'}
                self.settings['trusted_host_keys'] = keep
            self.save_settings()
            self.write_known_hosts()
        self.log('info', 'removed a trusted robot host key (%s)' % key_fingerprint(key))
        return {'ok': True, 'trusted': self.trusted_list()}

    def test_login(self, req):
        if self.fake:
            return {'ok': True, 'hostname': 'fake-turtlebot4', 'fake': True}
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'kind': 'no_ssh', 'error': 'ssh not found: install the OpenSSH client'}
        host = strip_user(str(req.get('host') or '').strip())
        try:
            host = host or self._terminal_host()
            if not valid_host(host):
                return {'ok': False, 'kind': 'other', 'error': 'invalid host name or address'}
            key = self.key_path(create=False)
        except BridgeError as e:
            return {'ok': False, 'kind': 'other', 'error': str(e)}
        if not os.path.isfile(key):
            return {'ok': False, 'kind': 'key_missing', 'error': 'no ssh key yet: create one first'}
        self.write_known_hosts()
        argv = build_ssh_argv(ssh, host, key, self.known_hosts, 'echo studio-login-ok; hostname', connect_timeout=8,
                              user=self.user())
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL, **hide_flags())
        except subprocess.TimeoutExpired:
            return {'ok': False, 'kind': 'unreachable', 'error': 'robot not reachable (timed out)'}
        except OSError as e:
            return {'ok': False, 'kind': 'other', 'error': str(e)}
        lines = [x.strip() for x in (r.stdout or '').splitlines() if x.strip()]
        if r.returncode == 0 and lines and lines[0] == 'studio-login-ok':
            return {'ok': True, 'hostname': lines[1] if len(lines) > 1 else None}
        kind, msg = map_ssh_error(r.stderr, r.returncode)
        return {'ok': False, 'kind': kind, 'error': msg}
