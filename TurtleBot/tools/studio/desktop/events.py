"""The event bus that feeds the browser pages (server-sent events) and the 1 Hz metrics history.
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


class Bus:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = set()
        self.last_conn = {'ev': 'conn', 'state': 'disconnected', 'host': None, 'via': None, 'error': None}
        self.last_status = None
        self.last_hello = None  # a page opened later still learns the robot's name and ROS version
        self.logs = collections.deque(maxlen=200)
        self.tap = None         # 2.0: optional callable(ev) that sees every published event (alerts); must not raise

    def publish(self, ev):
        self._publish(ev)
        tap = self.tap
        if tap is not None:
            try:
                tap(ev)
            except Exception:
                pass

    def _publish(self, ev):
        with self.lock:
            if ev.get('ev') == 'conn':
                self.last_conn = ev
                if ev.get('state') in ('disconnected', 'error', 'connecting', 'discovering'):
                    self.last_hello = None
            elif ev.get('ev') == 'hello':
                self.last_hello = ev
            elif ev.get('ev') == 'status':
                self.last_status = ev
            elif ev.get('ev') == 'log':
                self.logs.append(ev)
            for q in list(self.clients):
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    self.clients.discard(q)

    def subscribe(self):
        q = queue.Queue(maxsize=2000)
        with self.lock:
            pre = [self.last_conn] + ([self.last_hello] if self.last_hello else []) +                   ([self.last_status] if self.last_status else []) + list(self.logs)
            for ev in pre:
                q.put_nowait(ev)
            self.clients.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients.discard(q)

    def count(self):
        with self.lock:
            return len(self.clients)

    def close_all(self):
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass


# ============================================================================ 2.0: history and alerts


def finite_num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float('inf') else None


def history_sample(ev):
    """One status event -> the plotted numbers (None where the robot did not report one)."""
    g = lambda k: ev.get(k) if isinstance(ev.get(k), dict) else {}
    b, o, sc, sy, net = g('battery'), g('odom'), g('scan'), g('system'), g('net')
    vx = finite_num(o.get('vx'))
    return {'battery_pct': finite_num(b.get('percent')), 'voltage': finite_num(b.get('voltage')),
            'current_a': finite_num(b.get('current_a')), 'speed': None if vx is None else round(abs(vx), 3),
            'odom_hz': finite_num(o.get('rate_hz')), 'scan_hz': finite_num(sc.get('rate_hz')),
            'cpu_pct': finite_num(sy.get('cpu_pct')), 'temp_c': finite_num(sy.get('temp_c')),
            'wifi_dbm': finite_num(net.get('signal_dbm'))}


def clamp_minutes(v, default=15.0):
    m = finite_num(v)
    return default if m is None else min(HISTORY_KEEP_S / 60.0, max(1.0, m))


class History:
    """Metrics from the robot's status events, at most one sample per second, the newest HISTORY_KEEP_S seconds."""

    def __init__(self, keep=HISTORY_KEEP_S):
        self.rows = collections.deque(maxlen=int(keep))
        self.lock = threading.Lock()

    def add(self, ev, now=None):
        now = time.time() if now is None else now
        with self.lock:
            if self.rows and now - self.rows[-1][0] < 0.9:
                return False
            self.rows.append((now, history_sample(ev)))
            return True

    def query(self, minutes=15, now=None):
        now = time.time() if now is None else now
        cut = now - clamp_minutes(minutes) * 60.0
        with self.lock:
            rows = [r for r in self.rows if r[0] >= cut]
        return {'t': [round(t, 1) for t, _ in rows], 'series': {k: [smp.get(k) for _, smp in rows] for k in HISTORY_SERIES}}
