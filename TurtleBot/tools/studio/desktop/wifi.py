"""Wi-Fi features: saving, joining and removing networks on the robot, the laptop's own network
and the robot hotspot.
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
from .updates import *  # bundle: skip


class WifiMixin:
    # ---------------------------------------------------------------- v1.1: Wi-Fi help
    def _robot_script_terminal(self, script, args):
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        if self.fake:
            return {'ok': False, 'error': 'not available in fake mode (no real robot)'}
        if not self.bridge.connected:
            return {'ok': False, 'error': 'connect to the robot first (cable or its hotspot)'}
        try:
            host = self._terminal_host()
            argv = build_ssh_argv(ssh, host, self.key_path(), self.known_hosts, build_robot_script_cmd(script, *args),
                                  batch=False, tty=True, user=self.user())
            self.write_known_hosts()
            self._launch_terminal(argv)
        except (BridgeError, OSError, ValueError) as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def robot_wifi_add(self, req):
        """Join any WPA2-personal network. The Wi-Fi password goes to the bridge once, in memory, and never into a
        log, a reply, argv, the environment or a file; this wrapper makes sure no error path can echo it."""
        try:
            return self._robot_wifi_add(req)
        except Exception as e:
            self.log('error', 'Wi-Fi add failed (%s)' % type(e).__name__)
            return {'ok': False, 'error': 'internal error (%s)' % type(e).__name__}
        finally:
            if isinstance(req, dict) and 'psk' in req:
                req['psk'] = None

    def _robot_wifi_add(self, req):
        ssid, psk = req.get('ssid'), req.get('psk')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not valid_ssid(ssid):
            return {'ok': False, 'error': 'invalid network name (empty, line break, or longer than 32 bytes)'}
        if ssid == self.settings['hotspot_ssid'] or ssid in PROTECTED_CONNECTIONS:
            return {'ok': False, 'error': "'%s' is the robot's own hotspot name and cannot be added as a network" % ssid}
        if not valid_psk(psk):
            return {'ok': False, 'error': 'the Wi-Fi password must have 8 to 63 characters (or be 64 hex digits)'}
        if not self.bridge.connected:
            return {'ok': False, 'error': 'connect to the robot first (cable or its hotspot)'}
        connect_now = bool(req.get('connect_now'))
        try:
            info = self.bridge.request({'cmd': 'wifi_info'}, 12)
        except BridgeError as e:
            return {'ok': False, 'error': str(e)}
        if info.get('ok') and any(ssid in (x.get('name'), x.get('ssid')) for x in info.get('saved') or []):
            return {'ok': False, 'error': 'a network with this name is already saved on the robot: remove it first'}
        nonce = secrets.token_hex(16)
        try:
            r = self.bridge.request({'cmd': 'wifi_secret_put', 'nonce': nonce, 'psk': psk, 'ttl': WIFI_SECRET_TTL}, 10)
        except BridgeError as e:
            return {'ok': False, 'error': 'could not hand the Wi-Fi password to the robot: %s' % e}
        if not r.get('ok'):
            return {'ok': False, 'error': 'the robot did not accept the Wi-Fi password: %s' % str(r.get('error'))[:120]}
        if self.fake:
            try:
                r = self.bridge.request({'cmd': 'wifi_fake_add', 'nonce': nonce, 'ssid': ssid, 'connect_now': connect_now}, 10)
            except BridgeError as e:
                return {'ok': False, 'error': str(e)}
            if not r.get('ok'):
                return {'ok': False, 'error': str(r.get('error'))[:200]}
            res = {'ok': True, 'fake': True, 'note': 'fake mode: no terminal, the robot is simulated'}
        else:
            res = self._robot_script_terminal(wifi_add_script(), [b64s(ssid), safe_conn_filename(ssid), '1' if connect_now else '0',
                                                                 nonce, str(WIFI_JOIN_TIMEOUT)])
            if not res.get('ok'):
                try:
                    self.bridge.request({'cmd': 'wifi_secret_drop', 'nonce': nonce}, 5)
                except BridgeError:
                    pass
                return res
            res['note'] = ('A terminal opened. Type only the robot (sudo) password there. The Wi-Fi password was sent from '
                           'here, is kept in the robot\'s memory for 3 minutes and never written to a log or file.')
        self.wifi_jobs[nonce] = ssid
        while len(self.wifi_jobs) > 8:
            self.wifi_jobs.popitem(last=False)
        self.log('info', 'Wi-Fi add requested for %s (connect now: %s)' % (''.join(c if c.isprintable() else '?' for c in ssid),
                                                                          'yes' if connect_now else 'no'))
        res.update({'nonce': nonce, 'ssid': ssid, 'connect_now': connect_now, 'ttl': WIFI_SECRET_TTL, 'timeout': WIFI_JOIN_TIMEOUT})
        return res

    def robot_wifi_status(self, req):
        nonce = req.get('nonce')
        if nonce is not None and not (isinstance(nonce, str) and NONCE_RE.match(nonce)):
            return {'ok': False, 'error': 'invalid nonce'}
        cmd = {'cmd': 'wifi_join_status'}
        if nonce:
            cmd['nonce'] = nonce
        try:
            r = self.bridge.request(cmd, 8)
        except BridgeError as e:
            return {'ok': False, 'error': str(e), 'kind': 'not_connected'}
        if not r.get('ok'):
            return {'ok': False, 'error': str(r.get('error'))[:200]}
        join, stored = r.get('join'), False
        want = self.wifi_jobs.get(nonce) if nonce else None
        if isinstance(join, dict) and want is not None and join.get('ssid') != want:
            join = None  # an old result file of another network
        if isinstance(join, dict) and join.get('state') == 'joined' and isinstance(join.get('ssid'), str) \
                and isinstance(join.get('ip'), str) and valid_host(join['ip']):
            with self.set_lock:
                known = self.settings.setdefault('known_addresses', {})
                known[join['ssid']] = {'ip': join['ip'], 'seen': int(time.time()), 't': int(time.time())}
                self.save_settings()
            stored = True
        return {'ok': True, 'secret': r.get('secret') or 'none', 'join': join, 'stored': stored}

    def robot_wifi_remove(self, req):
        name = req.get('name')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not isinstance(name, str) or not name or '\n' in name or '\r' in name or '\x00' in name or len(name.encode('utf-8')) > 120:
            return {'ok': False, 'error': 'invalid connection name'}
        hs = self.settings['hotspot_ssid']
        if name in PROTECTED_CONNECTIONS or name in (hs, 'netplan-wlan0-' + hs):
            return {'ok': False, 'error': "'%s' is the robot's own hotspot or cable link and cannot be removed here" % name}
        res = self._robot_script_terminal(WIFI_REMOVE_SCRIPT, [b64s(name)])
        if res.get('ok'):
            self.log('info', 'Wi-Fi remove requested for %s' % ''.join(c if c.isprintable() else '?' for c in name))
        return res

    def laptop_wifi_settings(self):
        try:
            if IS_WIN:
                os.startfile('ms-settings:network-wifi')  # noqa: S606 (fixed, harmless URI)
            elif sys.platform == 'darwin':
                r = subprocess.run(['open', 'x-apple.systempreferences:com.apple.Network-Settings.extension'], capture_output=True)
                if r.returncode != 0:
                    subprocess.run(['open', '/System/Library/PreferencePanes/Network.prefPane'], capture_output=True)
            else:
                for argv in (['nm-connection-editor'], ['gnome-control-center', 'wifi']):
                    if shutil.which(argv[0]):
                        subprocess.Popen(argv, stdin=subprocess.DEVNULL)
                        break
                else:
                    return {'ok': False, 'error': 'no Wi-Fi settings program found (open your desktop network settings)'}
        except OSError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def join_hotspot(self):
        warn = 'While your computer is on the robot hotspot it has no internet (unless it has a second connection).'
        if not IS_WIN:
            return {'ok': False, 'needs_settings': True, 'warning': warn,
                    'error': 'Join the Wi-Fi "%s" in your computer Wi-Fi settings.' % self.settings['hotspot_ssid']}
        hs = self.settings['hotspot_ssid']
        profiles = parse_netsh_profiles(_run_quiet(['netsh', 'wlan', 'show', 'profiles'], 4))
        name = next((p for p in profiles if p.lower() == hs.lower()), None)
        if not name:
            return {'ok': False, 'needs_settings': True, 'warning': warn,
                    'error': 'This computer has no saved "%s" network yet. Join it once in Wi-Fi settings.' % hs}
        try:
            r = subprocess.run(['netsh', 'wlan', 'connect', 'name=' + name], capture_output=True, text=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {'ok': False, 'error': str(e), 'warning': warn}
        out = (r.stdout or '').strip()
        return {'ok': r.returncode == 0, 'warning': warn, 'detail': out[-200:],
                'error': None if r.returncode == 0 else (out or 'netsh failed')}

    # ---------------------------------------------------------------- v1.1: laptop network, known addresses
    def laptop_net(self):
        osname = 'windows' if IS_WIN else ('macos' if sys.platform == 'darwin' else 'linux')
        if self.fake and not os.environ.get('STUDIO_REAL_LAPTOP_NET'):
            # the simulated robot gets a simulated computer network too, so screenshots and tests never show the real one
            return {'ok': True, 'wifi': {'ssid': 'HomeNet', 'signal_pct': 80, 'state': 'connected', 'interface': 'Wi-Fi'},
                    'wired': [], 'os': osname, 'fake': True}
        box = {}
        ths = [threading.Thread(target=lambda: box.__setitem__('wifi', laptop_wifi()), daemon=True),
               threading.Thread(target=lambda: box.__setitem__('wired', laptop_wired()), daemon=True)]
        for t in ths:
            t.start()
        for t in ths:
            t.join(8)
        return {'ok': True, 'wifi': box.get('wifi'), 'wired': box.get('wired') or [], 'os': osname}
