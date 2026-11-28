"""Bridge commands that switch the scan, pose and map streams on and off, and the loop that sends them."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .mapping_helpers import *  # bundle: skip


class StreamsMixin:
    # ---- Studio 2.0: scan and pose streams (read the subscriptions that already exist; no new ROS objects)
    def _start_stream(self, name, hz, lo, hi, default_hz, **extra):
        try:
            hz = clamp_float(hz, lo, hi, default_hz)
        except ValueError:
            raise BridgeError("hz must be a number")
        with self.stream_lock:
            self.streams[name] = dict(period=1.0 / hz, next=0.0, last_seq=None, **extra)
        return hz

    def h_scan_on(self, c):
        self.need_ros()
        try:
            mp = clamp_int(c.get("max_points"), 90, 720, 360)
        except ValueError:
            raise BridgeError("max_points must be a number")
        hz = self._start_stream("scan", c.get("hz"), 1.0, 10.0, 4.0, max_points=mp)
        return {"hz": hz, "max_points": mp}

    def h_scan_off(self, c):
        with self.stream_lock:
            self.streams["scan"] = None
        return {}

    def h_pose_on(self, c):
        self.need_ros()
        hz = self._start_stream("pose", c.get("hz"), 1.0, 20.0, 10.0)
        return {"hz": hz}

    def h_pose_off(self, c):
        with self.stream_lock:
            self.streams["pose"] = None
        return {}

    def h_map_on(self, c):
        self.need_ros()
        try:
            mc = clamp_int(c.get("max_cells"), 10000, 4000000, 1000000)
        except ValueError:
            raise BridgeError("max_cells must be a number")
        self.ros.ensure_map_subs()
        hz = self._start_stream("map", c.get("hz"), 0.2, 2.0, 0.5, max_cells=mc)
        return {"hz": hz, "max_cells": mc}

    def h_map_off(self, c):
        with self.stream_lock:
            self.streams["map"] = None
        return {}

    def _stream_tick(self, now):
        with self.stream_lock:
            due = [(k, v) for k, v in self.streams.items() if v is not None and now >= v["next"]]
            for k, v in due:
                v["next"] = now + v["period"]
        for k, v in due:
            if k == "scan":
                sc = self.ros.scan_data()
                if not sc or sc["age_s"] > 2.0 or sc["seq"] == v["last_seq"]:
                    continue
                v["last_seq"] = sc["seq"]
                ev = build_scan_event(sc["ranges"], sc["angle_min"], sc["angle_inc"], sc["range_min"], sc["range_max"],
                                      sc["yaw"], v["max_points"], now)
                ev["yaw_assumed"] = bool(sc.get("yaw_assumed"))
                self.emit(ev, True)
            elif k == "map":
                md = self.ros.map_data()
                if not md or md["seq"] == v["last_seq"]:
                    continue
                v["last_seq"] = md["seq"]
                self.map_seq += 1
                self.emit(build_map_event(self.map_seq, now, md["width"], md["height"], md["resolution"], md["origin"],
                                          md["cells"], v["max_cells"]), key="map")
            else:
                po = self.ros.pose_data()
                if not po or po["age_s"] > 2.0:
                    continue
                ev = {"ev": "pose", "t": round(now, 3), "x": round(po["x"], 3), "y": round(po["y"], 3),
                      "yaw": round(po["yaw"], 4), "vx": round(po["vx"], 3), "wz": round(po["wz"], 3)}
                if self.streams.get("map") is not None:
                    mp = self.ros.map_pose()
                    if mp:
                        ev["map"] = {"x": round(mp["x"], 3), "y": round(mp["y"], 3), "yaw": round(mp["yaw"], 4),
                                     "source": mp["source"]}
                self.emit(ev, True)

    def _stream_loop(self):
        while not self.stop.is_set():
            try:
                if self.ros.available:
                    self._stream_tick(time.monotonic())
            except Exception as e:
                log("stream:", repr(e))
            self.stop.wait(0.02)
