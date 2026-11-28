"""Alert rules: turns status events into de-duplicated alerts, plus small value helpers.
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


class AlertCenter:
    """Alerts with severity, de-duplicated per code, kept in memory and in <config>/events.jsonl (rotated at max_bytes,
    one old file kept). Conditions are edge-triggered: an alert is raised when a condition starts and an info alert when it
    ends. publish(ev) is called with {'ev': 'alert', ...} for every alert that is kept."""

    def __init__(self, path, publish, clock=time.time, max_bytes=EVENTS_MAX_BYTES, keep=500):
        self.path, self.publish, self.clock, self.max_bytes = path, publish, clock, max_bytes
        self.lock = threading.RLock()
        self.items = collections.deque(maxlen=keep)
        self.last_t = {}
        self.next_id = 1
        self.active = {}
        self.batt_level = 0
        self.prev_docked = None
        self.prev_estop = None
        self.lidar_bad_since = None
        self._load()

    def _load(self):
        for fn in (self.path + '.old', self.path):
            try:
                with open(fn, encoding='utf-8') as f:
                    for line in f:
                        try:
                            a = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(a, dict) and isinstance(a.get('id'), int) and a.get('severity') in ALERT_SEVERITIES:
                            self.items.append({k: a.get(k) for k in ('id', 't', 'severity', 'code', 'text')})
                            self.next_id = max(self.next_id, a['id'] + 1)
            except OSError:
                pass

    def raise_alert(self, code, severity, text):
        """Returns the alert dict, or None when the same code (for program alerts: the same code and text) was already
        raised recently."""
        now = self.clock()
        window = ALERT_EDGE_DEDUP_S if code in ALERT_EDGE_CODES else ALERT_DEDUP_S
        key = (code, str(text)) if code in ALERT_PER_TEXT_CODES else code
        with self.lock:
            last = self.last_t.get(key)
            if last is not None and 0 <= now - last < window:
                return None
            self.last_t[key] = now
            a = {'id': self.next_id, 't': round(now, 3), 'severity': severity if severity in ALERT_SEVERITIES else 'info',
                 'code': str(code), 'text': str(text)[:300]}
            self.next_id += 1
            self.items.append(a)
            self._persist(a)
        try:
            self.publish(dict(a, ev='alert'))
        except Exception:
            pass
        return a

    def _persist(self, a):
        try:
            try:
                if os.path.getsize(self.path) >= self.max_bytes:
                    os.replace(self.path, self.path + '.old')
            except OSError:
                pass
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(a) + '\n')
        except OSError:
            pass

    def since(self, since_id=0, limit=500):
        with self.lock:
            out = [dict(a) for a in self.items if a['id'] > since_id]
            last = self.next_id - 1
        return out[-limit:], last

    def _cond(self, code, active, severity, text, clear_text):
        was = self.active.get(code, False)
        if active and not was:
            self.active[code] = True
            self.raise_alert(code, severity, text)
        elif not active and was:
            self.active[code] = False
            self.raise_alert(code + '_cleared', 'info', clear_text)

    def check_status(self, ev, moving=False):
        """Evaluate one status event. moving = a motion program runs or manual driving is armed."""
        g = lambda k: ev.get(k) if isinstance(ev.get(k), dict) else {}
        b, d, o, sc, es, sy, net, ck = g('battery'), g('dock'), g('odom'), g('scan'), g('estop'), g('system'), g('net'), g('clock')
        now = self.clock()
        # battery (a robot that is charging is not "low")
        pct = finite_num(b.get('percent'))
        if pct is not None:
            if b.get('charging') is True:
                lvl = 0
            else:
                prev = self.batt_level
                lvl = 2 if (pct < 10 or (prev == 2 and pct < 12)) else 1 if (pct < 20 or (prev >= 1 and pct < 22)) else 0
            if lvl != self.batt_level:
                old, self.batt_level = self.batt_level, lvl
                if lvl == 2:
                    self.raise_alert('battery_critical', 'critical', 'Battery is critically low (%d %%). Dock the robot now.' % pct)
                elif lvl == 1 and old == 0:
                    self.raise_alert('battery_low', 'warn', 'Battery is low (%d %%). Dock the robot soon.' % pct)
                else:
                    self.raise_alert('battery_cleared', 'info', 'Battery is %d %%.' % pct)
        # dock
        dk = d.get('is_docked')
        if isinstance(dk, bool):
            if self.prev_docked is not None and dk != self.prev_docked:
                self.raise_alert('docked' if dk else 'undocked', 'info', 'The robot is docked.' if dk else 'The robot left the dock.')
            self.prev_docked = dk
        # e-stop
        on = es.get('on')
        if isinstance(on, bool):
            if on and self.prev_estop is not True:
                self.raise_alert('estop_on', 'critical', 'E-stop is on (%s).' % (es.get('source') or 'unknown source'))
            elif not on and self.prev_estop is True:
                self.raise_alert('estop_off', 'info', 'E-stop released.')
            self.prev_estop = on
        # lidar silent while undocked for 10 s (it is off while docked)
        silent = dk is False and (sc.get('age_s') is None or finite_num(sc.get('age_s')) is None or sc['age_s'] > 3.0)
        if silent:
            self.lidar_bad_since = self.lidar_bad_since or now
        else:
            self.lidar_bad_since = None
        self._cond('lidar_silent', silent and now - self.lidar_bad_since >= 10.0, 'warn',
                   'The lidar is not sending scans although the robot is undocked.', 'The lidar is sending scans again.')
        # odometry stall while moving (TB-25)
        age = finite_num(o.get('age_s'))
        vx, wz = finite_num(o.get('vx')) or 0.0, finite_num(o.get('wz')) or 0.0
        stalled = age is not None and age > 0.5 and (moving or abs(vx) > 0.02 or abs(wz) > 0.02)
        self._cond('odom_stall', stalled, 'warn', 'Odometry paused for %.1f s while the robot was moving (TB-25).' % (age or 0.0),
                   'Odometry is flowing again.')
        # Wi-Fi, temperature, clock
        dbm = finite_num(net.get('signal_dbm'))
        if dbm is not None:
            weak = dbm < -75 or (self.active.get('wifi_weak', False) and dbm < -72)
            self._cond('wifi_weak', weak, 'warn', 'Wi-Fi signal is weak (%d dBm).' % dbm, 'Wi-Fi signal is fine again (%d dBm).' % dbm)
        temp = finite_num(sy.get('temp_c'))
        if temp is not None:
            hot = temp > 75 or (self.active.get('temp_high', False) and temp > 72)
            self._cond('temp_high', hot, 'warn', 'The robot computer is hot (%d C).' % temp, 'The robot computer cooled down (%d C).' % temp)
        wall = finite_num(ev.get('wall'))
        if wall is None and finite_num(ck.get('year')) is not None:
            wrong = abs(ck['year'] - time.gmtime(now).tm_year) >= 1
        else:
            wrong = wall is not None and abs(wall - now) > 86400
        self._cond('clock_wrong', wrong, 'warn', 'The robot clock is wrong. Log timestamps will be off.', 'The robot clock is correct again.')


def is_status_moving(ev, tele_armed=False):
    runs = ev.get('runs') if isinstance(ev.get('runs'), list) else []
    return bool(tele_armed) or any(isinstance(r, dict) and r.get('motion') and r.get('alive') for r in runs)


def limit_value(v, default, lo, hi):
    n = finite_num(v)
    return default if n is None or n <= 0 else min(hi, max(lo, n))
