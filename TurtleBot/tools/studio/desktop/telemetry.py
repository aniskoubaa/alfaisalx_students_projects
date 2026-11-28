"""What Studio learns from the robot: event tap, status bookkeeping (history, alerts, known
addresses) and the diagnostics report.
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


class TelemetryMixin:
    def _tap(self, ev):
        """Every published event passes here: raises alerts for connection, driving and program events."""
        kind = ev.get('ev')
        if kind == 'conn':
            st, host = ev.get('state'), ev.get('host') or 'the robot'
            if st == 'connected':
                if self.conn_lost:
                    self.alerts.raise_alert('conn_restored', 'info', 'Connection to %s restored.' % host)
                else:
                    self.alerts.raise_alert('conn_connected', 'info', 'Connected to %s.' % host)
                self.conn_lost = False
            elif st == 'reconnecting':
                if not self.conn_lost:
                    self.conn_lost = True
                    self.alerts.raise_alert('conn_lost', 'critical', 'Connection to %s lost. Studio is reconnecting.' % host)
            elif st == 'error':
                self.alerts.raise_alert('conn_error', 'warn', 'Connection problem: %s' % (ev.get('error') or 'unknown'))
            elif st == 'disconnected':
                self.conn_lost = False
                self.alerts.raise_alert('conn_disconnected', 'info', 'Disconnected from %s.' % host)
        elif kind == 'teleop':
            self.tele_armed = bool(ev.get('armed'))
            if ev.get('armed'):
                self.alerts.raise_alert('teleop_armed', 'info', 'Manual driving is armed.')
            else:
                self.alerts.raise_alert('teleop_disarmed', 'info', 'Manual driving is off: %s' % (ev.get('reason') or 'disarmed'))
        elif kind == 'run_exit':
            name = self.run_names.get(ev.get('run_id'), 'A program')
            code = ev.get('code')
            if code != 0 and (str(ev.get('run_id')) in self.run_stopped or time.time() < self.estop_until):
                self.alerts.raise_alert('program_exited', 'info', '%s was stopped.' % name)
            elif code == 0:
                self.alerts.raise_alert('program_exited', 'info', '%s finished.' % name)
            else:
                self.alerts.raise_alert('program_failed', 'warn', '%s exited with an error%s.' % (
                    name, '' if code is None else ' (code %s)' % code))

    def on_status(self, ev):
        """Record metrics and raise alerts, then remember the robot's Wi-Fi address per SSID (client mode only)."""
        try:
            self.history.add(ev)
            self.alerts.check_status(ev, is_status_moving(ev, self.tele_armed))
        except Exception as e:
            self.log('warn', 'status bookkeeping failed: %s' % e)
        try:
            net = ev.get('net') or {}
            ssid, ip = net.get('ssid'), (net.get('addresses') or {}).get('wlan0')
            if net.get('wifi_mode') != 'client' or not ssid or not ip or not valid_host(ip):
                return
            known = self.settings.setdefault('known_addresses', {})
            old = known.get(ssid) or {}
            if old.get('ip') != ip or time.time() - old.get('seen', 0) > 3600:
                known[ssid] = {'ip': ip, 'seen': int(time.time())}
                self.save_settings()
        except Exception:
            pass

    # ---------------------------------------------------------------- v1.3: diagnostics
    def diagnostics(self):
        """Plain text for a bug report. Everything goes through redact(); no password or token is ever collected."""
        s, L = self.settings, []

        def sec(title):
            L.extend(['', '== %s ==' % title])

        def kv(k, v):
            L.append('%s: %s' % (k, v if v not in (None, '') else '-'))
        L.append('TurtleBot Studio diagnostics (%s)' % time.strftime('%Y-%m-%d %H:%M:%S'))
        sec('Studio')
        kv('Version', VERSION)
        kv('Running as', 'built app' if FROZEN else 'source (python studio.py)')
        kv('Fake robot mode', 'yes' if self.fake else 'no')
        sec('This computer')
        kv('Operating system', platform.platform())
        kv('Python', sys.version.split()[0])
        ssh = find_exe('ssh')
        kv('ssh -V', (self.ssh_version(ssh) or 'ssh found, version unknown') if ssh else 'ssh NOT FOUND')
        kv('Config folder', self.cfg)
        if self.fake:
            kv('Wi-Fi / wired', 'not queried (fake mode)')
        else:
            try:
                ln = self.laptop_net()
                wifi = ln.get('wifi') or {}
                kv('Wi-Fi name', wifi.get('ssid') if wifi else 'not connected / no Wi-Fi')
                kv('Wired connection up', 'yes' if any(w.get('up') for w in ln.get('wired') or []) else 'no')
            except Exception as e:
                kv('Wi-Fi / wired', 'could not read (%s)' % e)
        sec('Settings')
        for k in ('robot_hostname', 'robot_user', 'last_host', 'last_via', 'hotspot_ssid', 'hotspot_addr', 'cable_addr'):
            kv(k, route_words(s.get(k)) if k == 'last_via' else s.get(k))
        ki = self.key_info()
        kv('ssh key file present', 'yes' if ki['exists'] else 'no')
        kv('ssh key fingerprint (public)', ki['fingerprint'])
        tl = self.trusted_list()
        kv('Trusted robots', '%d (%s)' % (sum(1 for t in tl if t['enabled']),
                                          ', '.join(t['label'] for t in tl if t['enabled']) or 'none'))
        kv('Built-in lab key', 'on' if s.get('builtin_host_key', True) else 'off')
        kv('auto_reconnect', 'on' if s.get('auto_reconnect', True) else 'off')
        kv('update_check', 'on' if s.get('update_check', True) else 'off')
        kv('window_mode', s.get('window_mode', DEFAULT_WINDOW_MODE))
        sec('Connection')
        c = self.bus.last_conn
        kv('State', c.get('state'))
        kv('Host', c.get('host'))
        kv('Reached over', route_words(c.get('via')))
        kv('Last error', c.get('error'))
        if c.get('state') == 'reconnecting':
            kv('Reconnect attempt', c.get('attempt'))
        sec('Last robot search')
        if not self.last_cands:
            L.append('(none yet)')
        for cd in self.last_cands:
            L.append('%s  reachable=%s  %s ms%s' % (cd.get('host'), 'yes' if cd.get('reachable') else 'no', cd.get('ms'),
                                                     '  identity=' + cd['identity'] if cd.get('identity') else ''))
        sec('Robot status')
        st = self.bus.last_status if self.bridge.connected else None
        if not st:
            L.append('(not connected)')
        else:
            net = st.get('net') or {}
            kv('Battery %', (st.get('battery') or {}).get('percent'))
            kv('Robot Wi-Fi mode', net.get('wifi_mode'))
            kv('Robot Wi-Fi name', net.get('ssid'))
            kv('Robot IP addresses', ', '.join('%s=%s' % (k, v) for k, v in (net.get('addresses') or {}).items()))
        sec('Last 60 log lines')
        with self.bus.lock:
            logs = list(self.bus.logs)[-60:]
        for e in logs:
            L.append('%s %s %s' % (time.strftime('%H:%M:%S', time.localtime(e.get('t') or time.time())), e.get('level'), e.get('text')))
        return {'ok': True, 'text': redact('\n'.join(L) + '\n', secrets=(self.token,))}
