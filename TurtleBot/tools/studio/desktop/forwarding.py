"""Sends page commands on to the bridge: teleop limits and the emergency stop.
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


class ForwardingMixin:
    # ---------------------------------------------------------------- bridge forwarding
    def forward(self, req):
        cmd = dict(req)
        name = cmd.get('cmd')
        if not isinstance(name, str) or not name:
            return {'ok': False, 'error': 'missing cmd'}
        reasons = None
        if name == 'run':
            reasons = self.motion_for_run(cmd)
        if name in ('teleop_arm', 'teleop'):
            # the limits always come from Studio's settings, whatever the page sent; the bridge caps them again
            cmd['max_linear'] = self.settings.get('teleop_linear', TELEOP_DEFAULT_LINEAR)
            cmd['max_angular'] = self.settings.get('teleop_angular', TELEOP_DEFAULT_ANGULAR)
        if name == 'stop':      # before the request: the program's exit event can arrive before the answer
            if cmd.get('run_id') == 'all':
                self.estop_until = time.time() + 12.0
            elif cmd.get('run_id'):
                self.run_stopped.add(str(cmd.get('run_id')))
        if name == 'teleop' and (not self.tele_armed or self.tele_gen != self.bridge.gen):
            # never send motion unless this very bridge process was armed (no resend after a reconnect)
            return {'ok': False, 'error': 'Manual driving is not armed.', 'armed': False}
        try:
            r = self.bridge.request(cmd, 8 if name == 'estop' else 2 if name == 'teleop'
                                else 25 if name in ('menu_check', 'menu_put') else 15)
        except BridgeError as e:
            return {'ok': False, 'error': str(e)}
        if name.startswith('mapping_') and isinstance(r, dict) and r.get('ok'):
            self.maps.set_info(r)
        if reasons is not None and isinstance(r, dict):
            r['motion_decision'] = {'motion': bool(cmd.get('motion')), 'reasons': reasons}
        if name == 'teleop_arm' and isinstance(r, dict) and r.get('ok'):
            if cmd.get('on') is True:
                self.tele_armed, self.tele_gen = True, self.bridge.gen
            else:
                self.tele_armed = False
        if name == 'run' and isinstance(r, dict) and r.get('ok') and r.get('run_id'):
            pname = os.path.basename(str(cmd.get('path', ''))) or 'program'
            self.run_names[r['run_id']] = pname
            self.alerts.raise_alert('program_started', 'info', 'Started %s.' % pname)
        return r

    def teleop_off(self, reason, wait=2.0):
        """Disarm manual driving (the bridge publishes zero velocity). Safe to call at any time and from any thread."""
        was = self.tele_armed
        self.tele_armed = False
        confirmed = False
        if self.bridge.connected:
            try:
                r = self.bridge.request({'cmd': 'teleop_arm', 'on': False, 'reason': reason}, wait)
                confirmed = bool(r.get('ok'))
            except BridgeError:
                pass
        if was and not confirmed:   # the bridge could not say it: tell the page ourselves
            self.bus.publish({'ev': 'teleop', 'armed': False, 'reason': reason})
        return was

    def client_gone(self):
        """An event stream (page) closed. When it was the last one nobody is watching the robot: stop manual driving."""
        if self.closing or self.bus.count() > 0:
            return
        if self.tele_armed or self.bridge.connected:
            threading.Thread(target=self.teleop_off, args=('The last Studio page was closed.',), daemon=True,
                             name='teleop-off').start()

    def teleop_limits(self, req=None):
        if req is not None:
            upd = {}
            for key, setting, lo, hi, unit in (('linear', 'teleop_linear', TELEOP_MIN_LINEAR, TELEOP_MAX_LINEAR, 'm/s'),
                                               ('angular', 'teleop_angular', TELEOP_MIN_ANGULAR, TELEOP_MAX_ANGULAR, 'rad/s')):
                if key not in req:
                    continue
                n = finite_num(req[key])
                if n is None or n <= 0:
                    return {'ok': False, 'error': '%s must be a number above 0 (%s, at most %.2f)' % (key, unit, hi)}
                upd[setting] = round(min(hi, max(lo, n)), 3)
            if not upd:
                return {'ok': False, 'error': 'give linear and/or angular'}
            with self.set_lock:
                self.settings.update(upd)
                self.save_settings()
        return {'ok': True, 'linear': self.settings['teleop_linear'], 'angular': self.settings['teleop_angular'],
                'max_linear': TELEOP_MAX_LINEAR, 'max_angular': TELEOP_MAX_ANGULAR}

    def estop(self):
        self.tele_armed = False     # the bridge disarms manual driving first thing; Studio stops sending at once
        self.estop_until = time.time() + 15.0
        out = {'ok': False}
        try:
            r = self.bridge.request({'cmd': 'estop'}, 8)
            out['bridge'] = r
            out['ok'] = bool(r.get('ok'))
        except BridgeError as e:
            out['bridge'] = {'ok': False, 'error': str(e)}
        if not out['ok']:
            out['fallback'] = self._estop_fallback()
            out['ok'] = bool(out['fallback'].get('ok'))
        self.log('warn' if out['ok'] else 'error', 'E-stop requested: %s' % ('sent' if out['ok'] else 'FAILED, check the robot!'))
        return out

    def _estop_fallback(self):
        if self.fake:
            return {'ok': False, 'error': 'no robot in fake mode'}
        host = self.bridge.host or self.settings.get('last_host') or self.args.host_override
        ssh = find_exe('ssh')
        if not host or not ssh or not valid_host(host):
            return {'ok': False, 'error': 'no known robot address or no ssh'}
        cmd = ("touch ~/STOP; pkill -INT -f '%s'; source /etc/turtlebot4/setup.bash >/dev/null 2>&1; "
               "timeout 5 ros2 service call /e_stop irobot_create_msgs/srv/EStop '{e_stop_on: true}'" % MOTION_PKILL_REGEX)
        try:
            argv = build_ssh_argv(ssh, host, self.key_path(create=False), self.known_hosts, cmd, connect_timeout=5,
                                  user=self.user())
            r = subprocess.run(argv, capture_output=True, text=True, timeout=15, **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
        except (OSError, subprocess.TimeoutExpired, BridgeError) as e:
            return {'ok': False, 'error': str(e)}
        # pkill finds nothing -> exit 1 is normal; success means ssh reached the robot and the service call ran.
        reached = r.returncode != 255
        return {'ok': reached and 'success' in (r.stdout or '').lower(), 'reached': reached, 'exit': r.returncode,
                'stdout': (r.stdout or '')[-400:], 'stderr': (r.stderr or '')[-300:]}
