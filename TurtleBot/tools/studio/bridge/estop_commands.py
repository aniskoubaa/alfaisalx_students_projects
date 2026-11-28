"""The emergency stop: stop everything that can move the robot, and release the stop afterwards.
Each step is a separate method so one failing step does not skip the others."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


class EstopMixin:
    # ---- e-stop
    def _parallel(self, funcs, deadline):
        res, threads = {}, {}
        for k, fn in funcs.items():
            def work(k=k, fn=fn):
                try:
                    res[k] = fn()
                except Exception as e:
                    res[k] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
            t = threading.Thread(target=work, daemon=True, name="estop-" + k)
            t.start()
            threads[k] = t
        end = time.monotonic() + deadline
        for k, t in threads.items():
            t.join(max(0.0, end - time.monotonic()))
            if k not in res:
                res[k] = {"ok": False, "error": "timeout"}
        return res

    def _estop_zero(self):
        if not self.ros.available:
            return {"ok": False, "error": "ROS not available: %s" % self.ros.error}
        n = self.ros.zero_burst(10, 20.0)
        return {"ok": n >= 10, "published": n}

    def _estop_stopfile(self):
        try:
            with open(self.stop_file, "a"):
                os.utime(self.stop_file, None)
            return {"ok": True, "path": self.stop_file}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def _pkill_motion(self):
        if self.fake or not shutil.which("pkill"):
            return {"ok": None, "note": "pkill skipped" + (" (fake)" if self.fake else " (not installed)")}
        pids = lambda: (run_cmd(["pgrep", "-f", MOTION_REGEX]) or "").split()
        found = pids()
        if not found:
            return {"ok": True, "matched": []}
        used = None
        for sig, wait in (("INT", 3.0), ("TERM", 2.0), ("KILL", 1.0)):
            run_cmd(["pkill", "-" + sig, "-f", MOTION_REGEX])
            used = sig
            end = time.monotonic() + wait
            while time.monotonic() < end:
                if not pids():
                    return {"ok": True, "matched": found, "signal": used}
                time.sleep(0.1)
        return {"ok": not pids(), "matched": found, "signal": used}

    def _estop_programs(self):
        with self.runs_lock:
            targets = [r for r in self.runs.values() if self.run_alive(r)]
        out = {"app_runs": {}, "pkill": None}
        res = self._parallel({"app": lambda: self.stop_many(targets), "pkill": self._pkill_motion}, 8.0)
        out["app_runs"], out["pkill"] = res["app"], res["pkill"]
        out["ok"] = True
        return out

    def _estop_service(self, on):
        try:
            if self.ros.available:
                ok, msg = self.ros.call_estop(on, 3.0)
                # The Create 3 (firmware I.0.0) answered success=False with an empty message on 2026-10-24
                # although the e-stop worked, so confirm it from /wheel_status (wheels_enabled) instead.
                confirmed, end = False, time.monotonic() + 1.5
                while time.monotonic() < end:
                    we = self.ros.snapshot().get("wheels_enabled")
                    if we is not None and we == (not on):
                        confirmed = True
                        break
                    time.sleep(0.1)
                return {"success": bool(ok) or confirmed, "service_reply": bool(ok), "confirmed_by_wheels": confirmed,
                        "message": msg}
            if shutil.which("ros2") and not self.fake:
                out = run_cmd(["timeout", "5", "ros2", "service", "call", "/e_stop", "irobot_create_msgs/srv/EStop",
                               "{e_stop_on: %s}" % ("true" if on else "false")], 7.0)
                return {"success": bool(out and "success=True" in out.replace(" ", "")) , "message": (out or "")[-200:]}
            return {"success": False, "message": "ROS not available: %s" % self.ros.error, "error": True}
        except Exception as e:
            return {"success": False, "message": str(e), "error": True}

    def _estop_cancel(self):
        return {"ok": True, "cancelled": self.ros.cancel_all_actions() if self.ros.available else []}

    def h_estop(self, c):
        self.teleop_disarm("e-stop")        # manual driving ends first; the zero burst below follows at once
        # step 1 starts first and immediately; the other steps never wait for it or for each other
        res = self._parallel({"zero_cmd_vel": self._estop_zero, "stop_file": self._estop_stopfile,
                              "programs": self._estop_programs, "e_stop_service": lambda: self._estop_service(True),
                              "cancel_goals": self._estop_cancel}, 7.0)
        svc = res["e_stop_service"]
        if svc.get("success"):
            self.estop_on = True
        self.estop_app, self.estop_t = True, time.monotonic()
        self.status_wake.set()
        out = {"steps": res, "fake": self.fake, "all_ok": all(
            (v.get("ok") is not False and v.get("success") is not False) for v in res.values())}
        return out

    def h_estop_release(self, c):
        svc = self._estop_service(False)
        rm = {"ok": True}
        try:
            if os.path.exists(self.stop_file):
                os.remove(self.stop_file)
        except OSError as e:
            rm = {"ok": False, "error": str(e)}
        if svc.get("success"):
            self.estop_on = False
            self.estop_app = False
            self.status_estop = False
        self.status_wake.set()
        return {"steps": {"e_stop_service": svc, "stop_file": rm}, "fake": self.fake,
                "all_ok": bool(svc.get("success")) and rm["ok"]}
