"""Bridge commands for the robot log (journal) and for the dock, undock and cancel-action buttons."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


class SystemMixin:
    # ---- Studio 2.0: robot log (journal)
    def h_journal(self, c):
        unit = c.get("unit") or JOURNAL_UNITS[0]
        try:
            argv = journal_argv(unit if isinstance(unit, str) else "", c.get("lines"), c.get("since"))
            n = clamp_int(c.get("lines"), 50, 2000, 300)
        except ValueError as e:
            raise BridgeError(str(e))
        grep = c.get("grep")
        if grep is not None and (not isinstance(grep, str) or len(grep) > 80 or "\0" in grep):
            raise BridgeError("grep must be plain text of at most 80 characters")
        if self.fake:
            text = "\n".join(self.fake_journal(unit, n))
        else:
            if not shutil.which("journalctl"):
                raise BridgeError("journalctl is not available on this machine.")
            try:
                p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12.0, encoding="utf-8",
                                   errors="replace", stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                raise BridgeError("journalctl took too long.")
            except OSError as e:
                raise BridgeError("cannot run journalctl: %s" % e)
            text = p.stdout or ""
            if journal_permission_problem(text) or (p.returncode != 0 and not text.strip()):
                raise BridgeError("This account may not read the robot log (journal). Ask a lab admin to add it to the "
                                  "systemd-journal group. Nothing was changed.", permission=True)
        lines = journal_lines(text, grep, n)
        return {"unit": unit, "requested": n, "since": c.get("since") or None, "grep": (grep or "").strip() or None,
                "count": len(lines), "lines": lines, "fake": self.fake}

    def fake_journal(self, unit, n):
        base = time.time() - 3600
        msgs = ["Started %s." % unit, "rplidar_node: scan published", "create3: battery state updated", "wifi: signal -55 dBm",
                "turtlebot4: dock status changed", "WARNING: odometry delayed 0.6 s", "ERROR: example error line for testing",
                "ros2: discovery server heartbeat"]
        out = []
        for i in range(n):
            ts = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(base + i * 3600.0 / max(1, n)))
            out.append("%s turtlebot4 %s[%d]: %s" % (ts, unit.split(".")[0], 1000 + i % 7, msgs[i % len(msgs)]))
        return out

    # ---- actions
    def _action(self, name, c):
        if not c.get("confirmed"):
            raise BridgeError("%s needs confirmation" % name)
        if os.path.exists(self.stop_file):
            raise BridgeError("e-stop/STOP file present: release first")
        self.need_ros()
        r = self.ros.start_action(name)
        r["fake"] = self.fake
        return r

    def h_undock(self, c):
        return self._action("undock", c)

    def h_dock(self, c):
        return self._action("dock", c)

    def h_cancel_action(self, c):
        self.need_ros()
        name = str(c.get("name", ""))
        return {"canceled": bool(self.ros.cancel_action(name))}
