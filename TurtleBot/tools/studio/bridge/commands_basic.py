"""Bridge commands that answer from state already in memory: ping, shutdown, status on/off, topics,
watching a topic, listing a folder and the lidar switch."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


class BasicCommandsMixin:
    # ---- simple commands
    def h_ping(self, c):
        return {"pong": True}

    def h_shutdown(self, c):
        self.teleop_disarm("bridge shutting down")
        threading.Timer(0.2, self.stop.set).start()
        return {"bye": True}

    def h_status_on(self, c):
        try:
            p = float(c.get("period", 1.0))
        except (TypeError, ValueError):
            raise BridgeError("period must be a number")
        self.status_period = min(60.0, max(0.2, p))
        self.status_wake.set()
        return {"period": self.status_period}

    def h_status_off(self, c):
        self.status_period = None
        return {}

    def h_topics(self, c):
        self.need_ros()
        return {"topics": self.ros.topics()}

    def h_watch(self, c):
        self.need_ros()
        topic = str(c.get("topic", ""))
        if not topic.startswith("/"):
            raise BridgeError("topic must start with /")
        try:
            max_hz = float(c.get("max_hz", 5))
        except (TypeError, ValueError):
            raise BridgeError("max_hz must be a number")
        max_hz = min(30.0, max(0.1, max_hz))
        with self.watch_lock:
            if len(self.watches) >= MAX_WATCHES:
                raise BridgeError("at most %d watches at once" % MAX_WATCHES)
            self.watch_counter += 1
            wid = self.watch_counter
            self.watches[wid] = None        # reserve the slot

        def on_msg(data, rate):
            self.emit({"ev": "msg", "watch_id": wid, "topic": topic, "t": round(time.monotonic(), 3), "rate_hz": rate,
                       "data": shrink_msg(data)}, True)
        try:
            key, typ = self.ros.watch_add(topic, c.get("type"), max_hz, on_msg)
        except Exception:
            with self.watch_lock:
                self.watches.pop(wid, None)
            raise
        with self.watch_lock:
            self.watches[wid] = key
        return {"watch_id": wid, "topic": topic, "type": typ}

    def h_unwatch(self, c):
        wid = c.get("watch_id")
        with self.watch_lock:
            if wid not in self.watches:
                raise BridgeError("no such watch")
            key = self.watches.pop(wid)
        if key is not None:
            self.ros.watch_remove(key)
        return {}

    def h_ls(self, c):
        d = self.resolve_dir(c.get("dir"))
        if not os.path.isdir(d):
            return {"dir": d, "exists": False, "files": []}
        return {"dir": d, "exists": True, "files": list_dir(d, bool(c.get("recursive")))}

    def h_lidar(self, c):
        self.need_ros()
        on = bool(c.get("on"))
        msg = self.ros.lidar(on)
        return {"on": on, "message": msg, "fake": self.fake}
