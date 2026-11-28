"""Everything needed to join another Wi-Fi network: the join status file, the abstract-socket listener
and WifiSecrets, which keeps a password in memory only. It does not store passwords on disk."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


# ---- v1.2: join any Wi-Fi network (S-c)
MOTION_CONFIRMED_ENV = "STUDIO_MOTION_CONFIRMED"   # see h_run and motion_common.studio_confirmed (examples)
WIFI_STATUS_PATH = os.environ.get("STUDIO_WIFI_STATUS") or "/run/turtlebot-studio-wifi.json"
NONCE_RE = re.compile(r"[0-9a-f]{32}")
SECRET_KEEP = 6          # secret records (states only, never the password) kept for wifi_join_status
JOIN_KEYS = {"state": str, "ssid": str, "ip": str, "prev": str, "reason": str, "fallback": str, "fallback_ok": bool,
             "removed": bool, "t": (int, float)}


def read_join_status(path=None, reader=read_text):
    """The JSON the root join job writes (no secrets in it), reduced to known keys and types; None if absent or broken."""
    text = reader(path or WIFI_STATUS_PATH, 4096)
    try:
        d = json.loads(text) if text else None
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("state") not in ("joining", "joined", "failed"):
        return None
    out = {}
    for k, t in JOIN_KEYS.items():
        v = d.get(k)
        if v is not None and isinstance(v, t) and not (t is not bool and isinstance(v, bool)):
            out[k] = v[:200] if isinstance(v, str) else v
    return out


def abstract_listener(nonce):
    """Linux: listening unix socket in the abstract namespace (no file, no permissions to fix)."""
    sk = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sk.bind("\0turtlebot-studio-wifi-" + nonce)
        sk.listen(1)
    except OSError:
        sk.close()
        raise
    return sk


def peer_is_me(conn):
    """SO_PEERCRED: the process on the other end runs as the same user as this bridge."""
    try:
        cred = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3I"))
        return struct.unpack("3I", cred)[1] == os.getuid()
    except (AttributeError, OSError, ValueError, struct.error):
        return False


class WifiSecrets:
    """Holds a Wi-Fi password in memory for at most ttl seconds and hands it to exactly ONE local reader of the same
    user. States per nonce: waiting | fetched | expired. The password is never printed, logged or returned."""

    def __init__(self, listen=abstract_listener, peer_ok=peer_is_me, clock=time.monotonic):
        self.listen, self.peer_ok, self.clock = listen, peer_ok, clock
        self.lock = threading.Lock()
        self.items = collections.OrderedDict()

    def put(self, nonce, psk, ttl, serve=True):
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise ValueError("bad nonce")
        if not isinstance(psk, str) or not 8 <= len(psk) <= 64:
            raise ValueError("bad password length")
        try:
            ttl = min(300.0, max(5.0, float(ttl)))
        except (TypeError, ValueError):
            raise ValueError("bad ttl")
        with self.lock:
            for e in self.items.values():
                if e["state"] == "waiting":
                    e["state"] = "expired"
                    e["psk"] = None
                    e["stop"].set()
        e = {"state": "waiting", "psk": psk, "deadline": self.clock() + ttl, "stop": threading.Event(), "sock": None}
        if serve:
            e["sock"] = self.listen(nonce)  # OSError propagates; nothing is stored then
        with self.lock:
            self.items[nonce] = e
            while len(self.items) > SECRET_KEEP:
                self.items.popitem(last=False)
        if serve:
            threading.Thread(target=self._serve, args=(e,), name="wifi-secret", daemon=True).start()
        return ttl

    def _serve(self, e):
        sk = e["sock"]
        try:
            while not e["stop"].is_set():
                left = e["deadline"] - self.clock()
                if left <= 0:
                    break
                sk.settimeout(min(left, 0.5))
                try:
                    conn, _ = sk.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    if not self.peer_ok(conn):
                        continue
                    conn.settimeout(5)
                    with self.lock:
                        psk = e["psk"]
                    if psk is None:
                        break
                    conn.sendall(psk.encode("utf-8"))
                    with self.lock:
                        e["state"] = "fetched"
                    return
                except OSError:
                    continue
                finally:
                    conn.close()
        finally:
            with self.lock:
                e["psk"] = None
                if e["state"] == "waiting":
                    e["state"] = "expired"
            try:
                sk.close()
            except OSError:
                pass

    def state(self, nonce):
        with self.lock:
            e = self.items.get(nonce) if isinstance(nonce, str) else None
            if e is None:
                return "none"
            if e["state"] == "waiting" and self.clock() > e["deadline"]:
                e["state"], e["psk"] = "expired", None
            return e["state"]

    def take(self, nonce):
        """Fake mode (no socket): hand over the password once, or None."""
        with self.lock:
            e = self.items.get(nonce) if isinstance(nonce, str) else None
            if e is None or e["state"] != "waiting" or self.clock() > e["deadline"]:
                return None
            psk, e["psk"], e["state"] = e["psk"], None, "fetched"
            return psk

    def drop(self, nonce):
        with self.lock:
            e = self.items.get(nonce) if isinstance(nonce, str) else None
            if e is not None:
                if e["state"] == "waiting":
                    e["state"] = "expired"
                e["psk"] = None
                e["stop"].set()
