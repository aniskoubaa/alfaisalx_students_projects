"""The fake robot used by demos and offline tests: a simulated room scan, a simulated map and FakeRos,
which answers like RosReal without any ROS. It never touches real hardware."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .ros_base import *  # bundle: skip


FAKE_ROOM = (-3.0, 3.0, -2.0, 2.0)          # x0, x1, y0, y1 of the fake room (metres, odom frame)
FAKE_DOOR_HALF = 0.3                         # the east wall has a gap |y| < 0.3: those beams get no return (null)
FAKE_BOX = (1.0, 1.4, 0.3, 0.7)              # a box inside the room


def fake_room_ranges(px, py, yaw, angle_min, angle_inc, n, yaw_off):
    """Ray-cast a fake rectangular room with a box and a doorway. Beam i has laser angle angle_min + i * angle_inc, robot
    angle = laser angle + yaw_off, world angle = yaw + robot angle. A robot outside the room is moved inside first."""
    x0, x1, y0, y1 = FAKE_ROOM
    px = min(x1 - 0.1, max(x0 + 0.1, px))
    py = min(y1 - 0.1, max(y0 + 0.1, py))
    bx0, bx1, by0, by1 = FAKE_BOX
    out = []
    for i in range(n):
        a = yaw + angle_min + i * angle_inc + yaw_off
        dx, dy = math.cos(a), math.sin(a)
        best, door = math.inf, False
        for lim, d, p0, axis in ((x1, dx, px, "x"), (x0, dx, px, "x"), (y1, dy, py, "y"), (y0, dy, py, "y")):
            if abs(d) < 1e-9:
                continue
            t = (lim - p0) / d
            if t <= 0 or t >= best:
                continue
            best = t
            door = axis == "x" and lim == x1 and abs(py + t * dy) < FAKE_DOOR_HALF
        if door:
            best = math.inf
        tmin, tmax = 0.0, math.inf
        for p0, d, lo, hi in ((px, dx, bx0, bx1), (py, dy, by0, by1)):
            if abs(d) < 1e-9:
                if p0 < lo or p0 > hi:
                    tmax = -1.0
                continue
            ta, tb = (lo - p0) / d, (hi - p0) / d
            tmin, tmax = max(tmin, min(ta, tb)), min(tmax, max(ta, tb))
        if tmax >= tmin and 0 < tmin < best:
            best = tmin
        out.append(best)
    return out


def fake_map_scale():
    """Time scale of the fake mapping (env STUDIO_FAKE_MAP_SCALE, default 1; tests use a small value)."""
    try:
        v = float(os.environ.get("STUDIO_FAKE_MAP_SCALE", "1"))
    except ValueError:
        return 1.0
    return v if math.isfinite(v) and v > 0 else 1.0


class FakeMapGrid:
    """Fake occupancy grid: 0.05 m cells over FAKE_ROOM plus a 1 m margin, in the odom frame (map frame = odom frame).
    Cell values like OccupancyGrid data as bytes: 0 free, 100 occupied, 255 unknown; row 0 = bottom row."""
    RES = 0.05
    MARGIN = 1.0
    CAST_S = 0.5            # seconds between ray casts while mapping
    RANGE_FROM, RANGE_TO, RANGE_GROW_S = 1.0, 12.0, 10.0

    def __init__(self, scale=1.0):
        x0, x1, y0, y1 = FAKE_ROOM
        self.scale = scale
        self.origin = (x0 - self.MARGIN, y0 - self.MARGIN, 0.0)
        self.width = round((x1 - x0 + 2 * self.MARGIN) / self.RES)
        self.height = round((y1 - y0 + 2 * self.MARGIN) / self.RES)
        self.lock = threading.Lock()
        self.cells = bytearray(b"\xff" * (self.width * self.height))
        self.seq = 0                    # grows whenever a cell changed
        self.t_start = None
        self._stop = threading.Event()
        self._thread = None

    def reset(self):
        with self.lock:
            self.cells = bytearray(b"\xff" * (self.width * self.height))
            self.seq = 0

    def usable_range(self, elapsed):
        f = min(1.0, max(0.0, elapsed / (self.RANGE_GROW_S * self.scale)))
        return self.RANGE_FROM + (self.RANGE_TO - self.RANGE_FROM) * f

    def _index(self, x, y):
        cx = math.floor((x - self.origin[0]) / self.RES)
        cy = math.floor((y - self.origin[1]) / self.RES)
        return (cy * self.width + cx) if 0 <= cx < self.width and 0 <= cy < self.height else None

    def cast(self, px, py, yaw, limit):
        """Ray cast from a pose with the fake lidar geometry: free along every beam, occupied at the hits within limit.
        Returns True when a cell changed."""
        n = 360
        inc = 2 * math.pi / n
        rs = fake_room_ranges(px, py, yaw, -math.pi, inc, n, SCAN_YAW_DEFAULT)
        step = self.RES * 0.7
        changed = False
        with self.lock:
            cells = self.cells
            for i, r in enumerate(rs):
                a = yaw - math.pi + i * inc + SCAN_YAW_DEFAULT
                dx, dy = math.cos(a), math.sin(a)
                hit = math.isfinite(r) and r <= limit
                reach = r if hit else limit
                k = 0.0
                while k < reach:
                    ix = self._index(px + k * dx, py + k * dy)
                    if ix is not None and cells[ix] == 255:
                        cells[ix] = 0
                        changed = True
                    k += step
                if hit:
                    ix = self._index(px + r * dx, py + r * dy)
                    if ix is not None and cells[ix] != 100:
                        cells[ix] = 100
                        changed = True
            if changed:
                self.seq += 1
        return changed

    def begin(self, pose_fn):
        """Start mapping from an empty grid: one cast every CAST_S * scale seconds from pose_fn() -> (x, y, yaw)."""
        self.end()
        self.reset()
        self.t_start = time.monotonic()
        self._stop = stop = threading.Event()

        def loop():
            while not stop.is_set():
                try:
                    x, y, yaw = pose_fn()
                    self.cast(x, y, yaw, self.usable_range(time.monotonic() - self.t_start))
                except Exception as e:
                    log("fake map:", repr(e))
                stop.wait(max(0.05, self.CAST_S * self.scale))
        self._thread = threading.Thread(target=loop, name="fakemap", daemon=True)
        self._thread.start()

    def end(self):
        self._stop.set()
        t, self._thread = self._thread, None
        if t is not None and t is not threading.current_thread():
            t.join(1.0)

    def mapping(self):
        return self._thread is not None and not self._stop.is_set()

    def reveal_all(self):
        """Fully reveal the room (the sample map): casts from a few poses with the full range."""
        for px, py in ((0.0, 0.0), (-2.0, 1.2), (2.0, -1.2), (-2.0, -1.2), (2.0, 1.2), (1.9, 0.0), (0.0, 1.4), (0.0, -1.4)):
            for yaw in (0.0, 1.5, 3.0, -1.5):
                self.cast(px, py, yaw, self.RANGE_TO)

    def snapshot(self):
        with self.lock:
            return {"seq": self.seq, "width": self.width, "height": self.height, "resolution": self.RES,
                    "origin": self.origin, "cells": bytes(self.cells)}

    def pgm_bytes(self):
        """P5 file content: 254 free, 0 occupied, 205 unknown, row 0 = top."""
        with self.lock:
            raw = bytes(self.cells)
        lut = bytearray(b"\xcd" * 256)
        for v in range(101):
            lut[v] = 254 if v < 50 else 0
        rows = [raw[y * self.width:(y + 1) * self.width] for y in range(self.height - 1, -1, -1)]
        pix = b"".join(rows).translate(bytes(lut))
        return b"P5\n# fake map\n%d %d\n255\n" % (self.width, self.height) + pix

    def save(self, prefix):
        """Write <prefix>.pgm, .yaml (map_server) and small placeholder .posegraph and .data files."""
        d = os.path.dirname(prefix)
        if d:
            os.makedirs(d, exist_ok=True)
        base = os.path.basename(prefix)
        yaml = ("image: %s.pgm\nmode: trinary\nresolution: %s\norigin: [%.3f, %.3f, 0.0]\nnegate: 0\n"
                "occupied_thresh: 0.65\nfree_thresh: 0.25\n" % (base, self.RES, self.origin[0], self.origin[1]))
        for ext, data in ((".pgm", self.pgm_bytes()), (".posegraph", b"fake pose graph\n"), (".data", b"fake pose graph data\n"),
                          (".yaml", yaml.encode("ascii"))):
            tmp = prefix + ext + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, prefix + ext)


class FakeRos(RosBase):
    """No ROS: simulated, slowly changing data so the desktop and the UI can be developed without a robot."""
    fake = True
    available = True

    def __init__(self):
        self.t0 = time.monotonic()
        self.docked = True
        self.lidar_on = True
        self.wheels_enabled = True
        self.emit = lambda *a, **k: None
        self.goals = {}
        self.watch_threads = {}
        self._lock = threading.Lock()
        self._plock = threading.Lock()
        self.px = self.py = self.pyaw = 0.0           # fake pose (odom frame), integrated from the published velocity
        self.pvx = self.pwz = 0.0
        self.battery_override = None                  # tests and the e2e run: a fixed battery percent (hidden fake_battery command)
        self._pt = time.monotonic()
        self._pseq = 0
        self.cmd_log = collections.deque(maxlen=200)  # (monotonic, vx, wz) of every publish_cmd, for tests
        self.map_grid = FakeMapGrid(fake_map_scale())

    def start(self, emit):
        self.emit = emit

    def _integrate(self):
        with self._plock:
            now = time.monotonic()
            dt = min(0.5, max(0.0, now - self._pt))
            self._pt = now
            mid = self.pyaw + self.pwz * dt / 2.0
            self.px += self.pvx * math.cos(mid) * dt
            self.py += self.pvx * math.sin(mid) * dt
            self.pyaw = wrap_pi(self.pyaw + self.pwz * dt)
            self._pseq += 1

    def publish_cmd(self, vx, wz):
        self._integrate()
        with self._plock:
            self.pvx, self.pwz = float(vx), float(wz)
            self.cmd_log.append((time.monotonic(), float(vx), float(wz)))

    def is_docked(self):
        return bool(self.docked)

    def pose_data(self):
        self._integrate()
        with self._plock:
            return {"x": self.px, "y": self.py, "yaw": self.pyaw, "vx": self.pvx, "wz": self.pwz, "age_s": 0.05,
                    "seq": self._pseq}

    def scan_data(self):
        if not self.lidar_on:
            return None
        pose = self.pose_data()
        n = 360
        inc = 2 * math.pi / n
        amin = -math.pi
        rs = fake_room_ranges(pose["x"], pose["y"], pose["yaw"], amin, inc, n, SCAN_YAW_DEFAULT)
        return {"ranges": rs, "angle_min": amin, "angle_inc": inc, "range_min": BODY_MIN_M, "range_max": 12.0,
                "yaw": SCAN_YAW_DEFAULT, "seq": int(time.monotonic() * 8), "age_s": 0.05, "yaw_assumed": False}

    def map_data(self):
        g = self.map_grid.snapshot()
        if g["seq"] == 0:
            return None
        g["age_s"] = 0.05
        return g

    def map_pose(self):
        p = self.pose_data()
        return {"x": p["x"], "y": p["y"], "yaw": p["yaw"], "source": "slam"}

    def map_reset(self):
        self.map_grid.reset()

    def shutdown(self):
        self.map_grid.end()
        for k in list(self.watch_threads):
            self.watch_remove(k)

    def snapshot(self):
        t = time.monotonic() - self.t0
        scan_on = self.lidar_on
        pz = self.pose_data()
        pct = self.battery_override if self.battery_override is not None else round(max(5.0, 87.0 - t * 0.01), 1)
        return {"battery": {"percent": pct, "voltage": round(15.9 - t * 0.0002, 2),
                            "charging": self.docked, "current_a": 0.5 if self.docked else -0.8, "full": False},
                "dock": {"is_docked": self.docked, "dock_visible": self.docked},
                "odom": {"x": round(pz["x"], 3), "y": round(pz["y"], 3), "yaw_deg": round(math.degrees(pz["yaw"]), 1),
                         "vx": round(pz["vx"], 3), "wz": round(pz["wz"], 3), "age_s": 0.05, "rate_hz": 19.9},
                "scan": {"rate_hz": 7.7 if scan_on else None, "front_m": round(1.2 + 0.1 * math.sin(t / 3.0), 3) if scan_on else None,
                         "min_m": round(0.6 + 0.05 * math.sin(t / 5.0), 3) if scan_on else None,
                         "age_s": 0.1 if scan_on else None, "scan_yaw_assumed": True},
                "hazards": [], "wheels_enabled": self.wheels_enabled}

    def topics(self):
        return [{"name": n, "types": [ty], "publishers": p, "subscribers": s} for n, ty, p, s in FAKE_TOPICS]

    def watch_add(self, topic, typ, max_hz, on_msg):
        key = object()
        stop = threading.Event()
        period = 1.0 / max(0.05, float(max_hz))

        def loop():
            n = 0
            while not stop.wait(period):
                n += 1
                t = time.monotonic() - self.t0
                if topic == "/odom":
                    data = {"header": {"stamp": {"sec": int(t), "nanosec": 0}, "frame_id": "odom"}, "child_frame_id": "base_link",
                            "pose": {"pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                              "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}},
                            "twist": {"twist": {"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}}}
                else:
                    data = {"fake": True, "topic": topic, "seq": n, "values": list(range(40))}
                on_msg(data, round(1.0 / period, 1))
        th = threading.Thread(target=loop, daemon=True, name="fakewatch")
        th.start()
        self.watch_threads[key] = stop
        return key, typ or dict((n, ty) for n, ty, _, _ in FAKE_TOPICS).get(topic, "std_msgs/msg/String")

    def watch_remove(self, key):
        s = self.watch_threads.pop(key, None)
        if s:
            s.set()

    def zero_burst(self, n=10, hz=20.0):
        time.sleep((n - 1) / hz)
        return n

    def call_estop(self, on, timeout=3.0):
        self.wheels_enabled = not on
        return True, "fake e-stop %s" % ("on" if on else "off")

    def lidar(self, on, timeout=5.0):
        self.lidar_on = bool(on)
        return "fake lidar %s" % ("on" if on else "off")

    def services_ready(self):
        return {"/e_stop": True, "/start_motor": True, "/stop_motor": True}

    def start_action(self, name, timeout=5.0):
        if name not in ("dock", "undock"):
            raise RosError("unknown action %s" % name)
        self.goals[name] = True
        self.emit({"ev": "action", "name": name, "state": "accepted", "detail": "fake"})

        def finish():
            time.sleep(0.4)
            if not self.goals.get(name):
                return
            self.emit({"ev": "action", "name": name, "state": "feedback", "detail": "fake"}, True)
            time.sleep(1.0)
            if self.goals.pop(name, None):
                self.docked = (name == "dock")
                self.emit({"ev": "action", "name": name, "state": "succeeded", "detail": "fake"})
        threading.Thread(target=finish, daemon=True).start()
        return {"accepted": True}

    def cancel_action(self, name, timeout=3.0):
        if self.goals.pop(name, None):
            self.emit({"ev": "action", "name": name, "state": "canceled", "detail": "fake"})
            return True
        return False

    def cancel_all_actions(self):
        names = list(self.goals)
        for n in names:
            self.cancel_action(n)
        return names
