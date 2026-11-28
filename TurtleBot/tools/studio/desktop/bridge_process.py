"""The one long-lived ssh process that runs robot_bridge.py on the robot (class Bridge) and
its error type.
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


class BridgeError(Exception):
    pass


class Bridge:
    """One long-lived bridge process (ssh, or `python robot_bridge.py --fake`), JSON lines both ways."""

    def __init__(self, app):
        self.app = app
        self.proc = None
        self.lock = threading.Lock()
        self.pending = {}
        self.next_id = 1
        self.stderr_tail = collections.deque(maxlen=30)
        self.connected = False
        self.hello = None
        self.hello_evt = threading.Event()
        self.user_stop = False
        self.host = None
        self.via = None
        self.gen = 0

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, argv, host, via, payload=None, env=None):
        self.stop(quiet=True)
        self.gen += 1
        gen = self.gen
        self.user_stop = False
        self.connected = False
        self.hello = None
        self.hello_evt.clear()
        self.stderr_tail.clear()
        maps = getattr(self.app, 'maps', None)     # test doubles of the app have none
        if maps is not None:
            maps.clear()    # no map or mapping state from another robot or bridge process
        self.host, self.via = host, via
        self.app.conn('connecting', host, via)
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         env=env, **hide_flags())
        except OSError as e:
            self.app.conn('error', host, via, 'cannot start: %s' % e, kind='other')
            return False
        proc = self.proc
        threading.Thread(target=self._read_out, args=(proc, gen), daemon=True).start()
        threading.Thread(target=self._read_err, args=(proc,), daemon=True).start()
        threading.Thread(target=self._wait, args=(proc, gen), daemon=True).start()
        if payload is not None:
            try:
                proc.stdin.write(b'%d\n' % len(payload) + payload)
                proc.stdin.flush()
            except OSError:
                pass  # the exit handler reports the real reason
        return True

    def _read_out(self, proc, gen):
        try:
            for raw in proc.stdout:
                line = raw.decode('utf-8', 'replace').strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if not isinstance(ev, dict):
                        raise ValueError
                except ValueError:
                    self.app.log('warn', 'bridge output: ' + line[:200])
                    continue
                if gen != self.gen:
                    continue
                if ev.get('ev') == 'reply':
                    with self.lock:
                        slot = self.pending.pop(ev.get('id'), None)
                    if slot:
                        slot[1].append(ev)
                        slot[0].set()
                    continue
                if ev.get('ev') == 'hello' and not self.connected:
                    self.hello = ev
                    self.connected = True
                    self.hello_evt.set()
                    self.app.bus.publish(ev)
                    self.app.conn('connected', self.host, self.via)
                    self._send({'id': 0, 'cmd': 'status_on', 'period': 1.0})
                    continue
                if ev.get('ev') == 'status':
                    self.app.on_status(ev)
                if ev.get('ev') == 'map':
                    self.app.on_map(ev)     # decoded into the MapStore; the page gets the slim event
                    continue
                if ev.get('ev') == 'mapping':
                    self.app.maps.set_info(ev)
                self.app.bus.publish(ev)
        except (OSError, ValueError):
            pass

    def _read_err(self, proc):
        try:
            for raw in proc.stderr:
                line = raw.decode('utf-8', 'replace').rstrip()
                if line:
                    self.stderr_tail.append(line)
        except (OSError, ValueError):
            pass

    def _wait(self, proc, gen):
        code = proc.wait()
        time.sleep(0.2)  # let the stderr reader finish
        if gen != self.gen:
            return
        with self.lock:
            pend, self.pending = self.pending, {}
        for ident, slot in pend.items():
            slot[1].append({'ev': 'reply', 'id': ident, 'ok': False, 'error': 'bridge connection closed'})
            slot[0].set()
        was = self.connected
        self.connected = False
        self.hello_evt.set()
        if self.user_stop:
            self.app.conn('disconnected', self.host, self.via)
            return
        kind, msg = map_ssh_error('\n'.join(self.stderr_tail), code)
        if was and kind == 'other':
            msg = 'connection lost (%s)' % msg
        self.app.log('error', 'bridge ended (exit %s): %s' % (code, msg))
        if was and self.app.bridge_lost(self.host, self.via, msg, kind):
            return  # v1.3: the app reconnects by itself and shows the 'reconnecting' state instead of an error
        self.app.conn('error', self.host, self.via, msg, kind=kind, detail=list(self.stderr_tail)[-5:])

    def _send(self, obj):
        data = (json.dumps(obj) + '\n').encode()
        with self.lock:
            p = self.proc
            if p is None or p.poll() is not None:
                raise BridgeError('not connected')
            try:
                p.stdin.write(data)
                p.stdin.flush()
            except (OSError, ValueError):
                raise BridgeError('not connected')

    def request(self, cmd, timeout=15.0):
        """cmd: dict with 'cmd' and args. Returns the reply event (dict). Raises BridgeError on no connection / timeout."""
        if not self.connected:
            raise BridgeError('not connected')
        with self.lock:
            ident = self.next_id
            self.next_id += 1
            slot = (threading.Event(), [])
            self.pending[ident] = slot
        msg = dict(cmd)
        msg['id'] = ident
        try:
            self._send(msg)
        except BridgeError:
            with self.lock:
                self.pending.pop(ident, None)
            raise
        if not slot[0].wait(timeout):
            with self.lock:
                self.pending.pop(ident, None)
            raise BridgeError('timeout after %.0f s waiting for the robot' % timeout)
        return slot[1][0]

    def stop(self, quiet=False):
        p = self.proc
        if p is None:
            return
        self.user_stop = True
        if p.poll() is None:
            try:
                if self.connected:
                    self._send({'id': -1, 'cmd': 'shutdown'})
                    p.stdin.close()
            except Exception:
                pass
            try:
                p.wait(2.5)
            except subprocess.TimeoutExpired:
                p.terminate()
                try:
                    p.wait(2)
                except subprocess.TimeoutExpired:
                    p.kill()
        self.connected = False
        self.proc = None
