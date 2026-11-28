"""The health check and the periodic status and slow-status loops that report to the desktop."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


class TelemetryMixin:
    # ---- health
    def h_health(self, c):
        checks = []

        def add(name, ok, detail=""):
            checks.append({"name": name, "ok": ok, "detail": detail})
        snap = self.ros.snapshot() if self.ros.available else None
        add("ROS (rclpy)", self.ros.available, "fake mode" if self.fake else (self.ros.error or "ok"))
        if snap:
            o, s, b, d = snap["odom"], snap["scan"], snap["battery"], snap["dock"]
            add("/odom fresh", o["age_s"] is not None and o["age_s"] < 1.0, "age %s s, %s Hz" % (o["age_s"], o["rate_hz"]))
            add("/dock_status", d["is_docked"] is not None, "docked=%s visible=%s" % (d["is_docked"], d["dock_visible"]))
            add("/battery_state", None if b["percent"] is None else b["percent"] > 15, "%s %% %s V" % (b["percent"], b["voltage"]))
            if d["is_docked"] and not s["rate_hz"]:
                add("/scan", None, "lidar is off while docked (normal)")
            elif d["is_docked"]:
                add("/scan", True, "%s Hz while docked (lidar motor running), front %s m" % (s["rate_hz"], s["front_m"]))
            else:
                add("/scan", s["rate_hz"] is not None and s["rate_hz"] > 5, "%s Hz, front %s m" % (s["rate_hz"], s["front_m"]))
            if snap["wheels_enabled"] is not None:
                add("drive motors enabled (no e-stop)", snap["wheels_enabled"], "wheels_enabled=%s" % snap["wheels_enabled"])
            ready = self.ros.services_ready()
            add("services /e_stop /start_motor /stop_motor", all(ready.values()) if ready else None, json.dumps(ready))
        sysd = self.read_system()
        yr = time.gmtime().tm_year
        add("robot clock", yr >= 2026 and self.slow.get("clock_synced") is not False,
            "year %d, synced=%s (the robot clock can be years wrong without internet)" % (yr, self.slow.get("clock_synced")))
        t = sysd.get("temp_c")
        add("CPU temperature / throttling", None if t is None else (t < 80 and sysd.get("throttled") in (None, "0x0")),
            "%s C, throttled %s" % (t, sysd.get("throttled")))
        add("turtlebot4.service", None if self.slow["ros_service"] == "unknown" else self.slow["ros_service"] == "active",
            self.slow["ros_service"])
        df = sysd.get("disk_free_gb")
        add("disk free", None if df is None else df > 1.0, "%s GB" % df)
        add("no STOP file", not os.path.exists(self.stop_file), self.stop_file)
        net = self.slow.get("net", {})
        add("network", None if not net else net.get("wifi_mode") in ("ap", "client") or bool(net.get("addresses")),
            "wifi %s ssid %s, %s" % (net.get("wifi_mode"), net.get("ssid"), net.get("addresses")))
        return {"checks": checks}

    # ---- status
    def read_system(self):
        if self.fake:
            t = time.monotonic() - self.t0
            return {"cpu_pct": round(8 + 4 * math.sin(t / 4), 1), "load1": round(0.9 + 0.1 * math.sin(t / 7), 2),
                    "temp_c": round(51 + 2 * math.sin(t / 9), 1), "throttled": "0x0", "mem_used_mb": 740, "mem_total_mb": 3784,
                    "disk_free_gb": 40.2, "uptime_s": round(600 + t, 1)}
        cur = parse_proc_stat(read_text("/proc/stat") or "")
        cp = cpu_pct(self.cpu_prev, cur)
        self.cpu_prev = cur
        used, total = parse_meminfo(read_text("/proc/meminfo") or "")
        temp = read_text("/sys/class/thermal/thermal_zone0/temp", 32)
        try:
            temp_c = round(int(temp.strip()) / 1000.0, 1)
        except (AttributeError, ValueError):
            temp_c = None
        try:
            free = round(shutil.disk_usage(self.home).free / 1e9, 1)
        except OSError:
            free = None
        return {"cpu_pct": cp, "load1": parse_loadavg(read_text("/proc/loadavg") or ""), "temp_c": temp_c,
                "throttled": self.slow.get("throttled"), "mem_used_mb": used, "mem_total_mb": total, "disk_free_gb": free,
                "uptime_s": parse_uptime(read_text("/proc/uptime") or "")}

    def estop_status(self, wheels_enabled):
        now = time.monotonic()
        if wheels_enabled is None:
            on = self.estop_on
        else:
            on = not wheels_enabled
            if wheels_enabled and now - self.estop_t > 3.0:
                self.estop_app = False
        if on is True:
            src = "app" if self.estop_app else "robot"
        else:
            src = None
        return {"on": on, "source": src, "stop_file": os.path.exists(self.stop_file)}

    def build_status(self):
        s = self.ros.snapshot()
        slow = self.slow
        with self.runs_lock:
            runs = [r.info(self.run_alive(r)) for r in list(self.runs.values())[-10:]]
        runs = [{k: v for k, v in r.items() if k in ("run_id", "name", "pid", "alive", "started_wall", "motion")} for r in runs]
        wall = time.time()
        net = dict(slow.get("net") or {})
        estop = self.estop_status(s["wheels_enabled"])
        self.status_estop = estop.get("on")
        with self.tele_lock:
            tele = {"armed": self.tele["armed"], "max_linear": self.tele["max_linear"], "max_angular": self.tele["max_angular"]}
        return {"ev": "status", "t": round(time.monotonic(), 3), "wall": round(wall, 3),
                "battery": s["battery"], "dock": s["dock"], "odom": s["odom"], "scan": s["scan"], "hazards": s["hazards"],
                "estop": estop, "teleop": tele, "system": self.read_system(), "net": net,
                "clock": {"synced": slow.get("clock_synced"), "year": time.gmtime(wall).tm_year},
                "ros_service": slow.get("ros_service"), "runs": runs}

    def _status_loop(self):
        while not self.stop.is_set():
            p = self.status_period
            if p is None:
                self.status_wake.wait(1.0)
                self.status_wake.clear()
                continue
            try:
                self.emit(self.build_status(), True)
            except Exception as e:
                log("status failed:", repr(e))
            self.status_wake.wait(p)
            self.status_wake.clear()

    def _slow_loop(self):
        while not self.stop.is_set():
            if self.fake:
                self.slow = {"net": self.fake_net(), "clock_synced": False, "ros_service": "active", "throttled": "0x0"}
            else:
                try:
                    self.slow = collect_slow()
                except Exception as e:
                    log("slow refresh:", repr(e))
            self.stop.wait(SLOW_EVERY)
