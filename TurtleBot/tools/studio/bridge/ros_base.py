"""The single locked writer of stdout, the ROS error type and RosBase, the part of the ROS layer
that does not need rclpy. It does not create any ROS object."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip


# ======================================================================= single locked writer
class Writer:
    """All stdout output goes through one queue and one writer thread, so ROS callbacks never block on a slow pipe.
    Droppable events (status, msg) are dropped when the queue is long; replies are never dropped. An event with a key
    (the map, hundreds of KB) replaces a queued line with the same key that has not been written yet, so a slow link
    never holds more than one stale map and replies do not wait behind old ones."""

    def __init__(self, stream, on_broken=None, max_droppable=400):
        self.stream, self.on_broken, self.max_droppable = stream, on_broken, max_droppable
        self.q = collections.deque()            # [key or None, line]
        self.cv = threading.Condition()
        self.closed = False
        self.dropped = 0
        self.replaced = 0
        self.thread = threading.Thread(target=self._run, name="writer", daemon=True)
        self.thread.start()

    def emit(self, obj, droppable=False, key=None):
        try:
            line = (json.dumps(clean_json(obj), separators=(",", ":")) + "\n").encode("ascii")
        except Exception as e:
            line = (json.dumps({"ev": "log", "level": "error", "text": "encode error: %s" % e}) + "\n").encode("ascii")
        with self.cv:
            if self.closed:
                return
            if droppable and len(self.q) >= self.max_droppable:
                self.dropped += 1
                return
            if key is not None:
                for item in self.q:
                    if item[0] == key:
                        item[1] = line
                        self.replaced += 1
                        return
            self.q.append([key, line])
            self.cv.notify()

    def _run(self):
        while True:
            with self.cv:
                while not self.q and not self.closed:
                    self.cv.wait()
                if not self.q:
                    return
                data = b"".join(item[1] for item in self.q)
                self.q.clear()
            try:
                self.stream.write(data)
                self.stream.flush()
            except Exception:
                with self.cv:
                    self.closed = True
                if self.on_broken:
                    self.on_broken()
                return

    def close(self, timeout=1.0):
        with self.cv:
            self.closed = True
            self.cv.notify_all()
        self.thread.join(timeout)


# ======================================================================= ROS layer
class RosError(Exception):
    pass


class RosBase:
    fake = False
    available = False
    error = None

    def start(self, emit):
        raise NotImplementedError

    def shutdown(self):
        pass

    def snapshot(self):
        """-> {battery, dock, odom, scan, hazards, wheels_enabled} (see FakeRos for the shape)."""
        raise NotImplementedError

    def topics(self):
        raise NotImplementedError

    def watch_add(self, topic, typ, max_hz, on_msg):
        raise NotImplementedError

    def watch_remove(self, key):
        pass

    def zero_burst(self, n=10, hz=20.0):
        raise NotImplementedError

    def call_estop(self, on, timeout=3.0):
        raise NotImplementedError

    def lidar(self, on, timeout=5.0):
        raise NotImplementedError

    def start_action(self, name, timeout=5.0):
        raise NotImplementedError

    def cancel_action(self, name, timeout=3.0):
        raise NotImplementedError

    def cancel_all_actions(self):
        return []

    def services_ready(self):
        return {}

    # ---- Studio 2.0 (default: nothing available)
    def publish_cmd(self, vx, wz):
        """Publish ONE velocity command (manual driving). Zero velocity must always work."""
        raise NotImplementedError

    def is_docked(self):
        """True / False, or None when /dock_status has not been seen."""
        return None

    def scan_data(self):
        """Newest laser scan as {ranges, angle_min, angle_inc, range_min, range_max, yaw, seq, age_s} or None."""
        return None

    def pose_data(self):
        """Newest odometry as {x, y, yaw (rad), vx, wz, age_s} or None."""
        return None

    def ensure_map_subs(self):
        """Create the /map and /pose subscriptions (once, on the existing node)."""

    def map_data(self):
        """Newest map as {seq, width, height, resolution, origin (x, y, yaw), cells, age_s} or None."""
        return None

    def map_pose(self):
        """Robot pose in the map frame as {x, y, yaw, source: "slam" or "odom"} or None."""
        return None

    def map_reset(self):
        """Forget the last map and SLAM pose (a new mapping session starts or the old one ended)."""
