"""Manual driving from the desktop: the checks before driving, arming, the drive command and its
safety loop. It also holds the small state questions those checks ask (e-stop, battery)."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


class TeleopMixin:
    # ---- Studio 2.0: manual driving (teleop)
    def estop_active(self):
        return self.estop_on is True or self.status_estop is True or os.path.exists(self.stop_file)

    def motion_running(self):
        with self.runs_lock:
            return any(r.motion and self.run_alive(r) for r in self.runs.values())

    def battery_percent(self):
        """Battery percent from the robot, or None when it is not known (then nothing is refused because of it)."""
        try:
            p = self.ros.snapshot()["battery"]["percent"]
        except Exception:
            return None
        return float(p) if isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p) else None

    def teleop_refusal(self, deep=False):
        """Why manual driving is not allowed right now (text), or None. deep=True also looks for motion programs that were
        not started by this bridge (pgrep; only when arming)."""
        if self.estop_active():
            return "The e-stop is on. Release it first."
        if not self.ros.available:
            return "ROS is not ready: %s" % (self.ros.error or "not started")
        why = MAPPING_BUSY_TEXT.get(getattr(getattr(self, "mapping", None), "state", None))
        if why:
            return why
        d = self.ros.is_docked()
        if d is True:
            return "The robot is docked. Undock first."
        if d is None:
            return "The robot state is not known yet. Wait a few seconds and try again."
        if self.motion_running():
            return "A motion program is running. Stop it first."
        pct = self.battery_percent()
        if pct is not None and pct < (TELEOP_ARM_MIN_PCT if deep else TELEOP_STOP_PCT):
            return ("Battery below %d %%. Charge the robot before driving." % TELEOP_ARM_MIN_PCT) if deep else                    ("Battery below %d %%. Manual driving was stopped." % TELEOP_STOP_PCT)
        if deep and not self.fake and shutil.which("pgrep") and (run_cmd(["pgrep", "-f", MOTION_REGEX]) or "").split():
            return "A motion program is running. Stop it first."
        return None


    def _zero(self, repeats=1):
        for i in range(repeats):
            try:
                self.ros.publish_cmd(0.0, 0.0)
            except Exception as e:
                log("zero velocity failed:", repr(e))
            if i < repeats - 1:
                time.sleep(0.02)

    def teleop_disarm(self, reason):
        """Disarm and publish zero velocity. Does nothing when not armed (so a program that drives is never disturbed by a
        stray zero). Returns True when it was armed."""
        with self.tele_lock:
            was = self.tele["armed"]
            self.tele["armed"] = False
            self.tele["zeroed"] = True
        if was:
            self._zero(3)
            self.emit({"ev": "teleop", "armed": False, "reason": reason})
        return was

    def h_teleop_arm(self, c):
        on = c.get("on")
        if not isinstance(on, bool):
            raise BridgeError("on must be true or false")
        if not on:
            reason = c.get("reason")
            reason = " ".join(reason.split())[:80] if isinstance(reason, str) and reason.strip() else "disarmed"
            was = self.teleop_disarm(reason)
            return {"armed": False, "was_armed": was}
        why = self.teleop_refusal(deep=True)
        if why:
            raise BridgeError(why, armed=False)
        try:
            ml = clamp_float(c.get("max_linear"), 0.0, TELEOP_MAX_LINEAR, TELEOP_MAX_LINEAR)
            ma = clamp_float(c.get("max_angular"), 0.0, TELEOP_MAX_ANGULAR, TELEOP_MAX_ANGULAR)
        except ValueError:
            raise BridgeError("max_linear and max_angular must be numbers")
        now = time.monotonic()
        with self.tele_lock:
            changed = not self.tele["armed"]
            self.tele.update(armed=True, last_cmd=now, last_move=now, zeroed=True, seq=-1, max_linear=ml, max_angular=ma,
                             armed_t=now)
        if changed:
            self.emit({"ev": "teleop", "armed": True, "reason": "armed"})
        return {"armed": True, "max_linear": ml, "max_angular": ma, "watchdog_s": TELEOP_WATCHDOG_S, "idle_s": TELEOP_IDLE_S}

    def h_teleop(self, c):
        with self.tele_lock:
            armed = self.tele["armed"]
        if not armed:
            raise BridgeError("Manual driving is not armed.", armed=False)
        why = self.teleop_refusal()
        if why:
            self.teleop_disarm(why)
            raise BridgeError(why, armed=False)
        seq = c.get("seq")
        if seq is not None and (isinstance(seq, bool) or not isinstance(seq, int)):
            raise BridgeError("seq must be a whole number")
        now = time.monotonic()
        with self.tele_lock:
            if not self.tele["armed"]:
                raise BridgeError("Manual driving is not armed.", armed=False)
            if seq is not None and seq <= self.tele["seq"]:
                return {"armed": True, "ignored": True, "seq": seq}       # an older command that arrived late
            if seq is not None:
                self.tele["seq"] = seq
            # limits sent with the command (Studio's current settings) replace the ones from arming; the hard caps apply always
            ul = c.get("max_linear") if c.get("max_linear") is not None else self.tele["max_linear"]
            ua = c.get("max_angular") if c.get("max_angular") is not None else self.tele["max_angular"]
            vx, wz = clamp_teleop(c.get("vx"), c.get("wz"), ul, ua)
            self.tele["last_cmd"] = now
            self.tele["zeroed"] = (vx == 0.0 and wz == 0.0)
            if not self.tele["zeroed"]:
                self.tele["last_move"] = now
            self.ros.publish_cmd(vx, wz)         # under the lock: the watchdog can never publish an older value after it
        return {"armed": True, "vx": vx, "wz": wz, "seq": seq}

    def _teleop_loop(self):
        """Watchdog. Runs on its own thread so it works whether or not messages arrive: it never waits for one."""
        last_deep = 0.0
        while not self.stop.is_set():
            now = time.monotonic()
            trip, why = False, None
            with self.tele_lock:
                if self.tele["armed"]:
                    if not self.tele["zeroed"] and now - self.tele["last_cmd"] > TELEOP_WATCHDOG_S:
                        self.tele["zeroed"] = True
                        trip = True
                        try:
                            self.ros.publish_cmd(0.0, 0.0)
                        except Exception as e:
                            log("watchdog zero failed:", repr(e))
                    if now - self.tele["last_move"] > TELEOP_IDLE_S:
                        why = "No command for %d s." % TELEOP_IDLE_S
                    elif os.path.exists(self.stop_file):
                        why = "The e-stop is on."
            if why is None and now - last_deep > 0.25:
                last_deep = now
                with self.tele_lock:
                    armed = self.tele["armed"]
                if armed:
                    why = self.teleop_refusal()
            if why:
                self.teleop_disarm(why)
            elif trip:
                log("teleop watchdog: zero velocity sent")
            self.stop.wait(0.02)
