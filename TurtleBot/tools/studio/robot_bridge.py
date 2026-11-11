#!/usr/bin/env python3
"""TurtleBot Studio robot bridge: JSON lines on stdin/stdout between the desktop app and the robot (spec TB-27 sec. 1 and 2).

ONE self-contained file (stdlib + rclpy), streamed over ssh at connect time, nothing is installed on the robot:
    ssh ... "source /etc/turtlebot4/setup.bash >/dev/null 2>&1; exec python3 -u -c \\
      \\"import sys;b=sys.stdin.buffer;n=int(b.readline());exec(compile(b.read(n).decode(),'robot_bridge','exec'))\\""
then the desktop writes "<len>\\n" + these bytes, then command lines. Started that way there is no __file__ and
sys.argv is ['-c'], so nothing here depends on either; the mode comes from the environment:
    STUDIO_BRIDGE_FAKE=1   force fake mode (no ROS, simulated data) even without --fake
    STUDIO_BRIDGE_HOME=dir home directory used for ~, ~/STOP and ~/robot_code/logs (default: real home; in fake mode
                           a fresh temporary directory), for tests.
Direct use for development:  python3 robot_bridge.py [--fake]   (commands on stdin, events on stdout)

Protocol (one JSON object per line). Command: {"id":1,"cmd":"ping",...}. Every command gets exactly one
{"ev":"reply","id":1,"ok":true|false,"error":"..",...}. Everything else is an unsolicited event (hello, status, msg,
run_output, run_exit, action). Diagnostics go to stderr. Times: "t" = time.monotonic() of the robot, "wall" = time.time()
(may be years wrong on the robot).

Safety: the only velocity this program ever publishes is zero (estop) and, since Studio 2.0, bounded manual driving
("teleop"): it needs teleop_arm first, is clamped here to 0.30 m/s and 1.20 rad/s (and to the limits Studio passes), stops
300 ms after the last command, and is disarmed by e-stop, the ~/STOP file, docking, a running motion program, 60 s
without non-zero commands and by this bridge ending. It starts no motion by itself: "run" of a motion
program needs confirmed=true, undock/dock need confirmed=true, and a ~/STOP file blocks them. Runs are detached
(own session), so they survive the bridge; logs in ~/robot_code/logs/. CPU: raw (undeserialised) subscriptions, the
scan is evaluated only at the status period, nmcli/systemctl results are cached for 10 s.
"""
import argparse
import base64
import collections
import hashlib
import json
import math
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

VERSION = "1"
MOTION_REGEX = (r"motion_shapes\.py|drive_test\.py|motion_test\.sh|more_shapes\.py|wall_approach\.py|"
                r"keep_distance\.py|campaign\.sh")
MAX_MSG_BYTES = 16 * 1024
MAX_ARRAY = 32
MAX_WATCHES = 4
SLOW_EVERY = 10.0           # s, nmcli / systemctl / vcgencmd cache
HAZARD_WINDOW = 2.0         # s
FRONT_HALF_DEG = 15.0
BODY_MIN_M = 0.15
SCAN_YAW_DEFAULT = math.pi / 2          # lidar mounted at +90 deg yaw (used when TF is not available)
FAKE_TOPICS = [
    ("/odom", "nav_msgs/msg/Odometry", 1, 3), ("/battery_state", "sensor_msgs/msg/BatteryState", 1, 2),
    ("/dock_status", "irobot_create_msgs/msg/DockStatus", 1, 2), ("/scan", "sensor_msgs/msg/LaserScan", 1, 2),
    ("/hazard_detection", "irobot_create_msgs/msg/HazardDetectionVector", 1, 2),
    ("/wheel_status", "irobot_create_msgs/msg/WheelStatus", 1, 2), ("/imu", "sensor_msgs/msg/Imu", 1, 2),
    ("/cmd_vel", "geometry_msgs/msg/TwistStamped", 0, 2), ("/ip", "std_msgs/msg/String", 1, 1),
    ("/hmi/display", "turtlebot4_msgs/msg/UserDisplay", 1, 1),
    ("/diagnostics_toplevel_state", "diagnostic_msgs/msg/DiagnosticStatus", 1, 1), ("/tf", "tf2_msgs/msg/TFMessage", 3, 4),
]
TELEOP_MAX_LINEAR = 0.30    # m/s, hard cap of manual driving (the lab programs use 0.15)
TELEOP_MAX_ANGULAR = 1.20   # rad/s
TELEOP_WATCHDOG_S = 0.30    # no teleop message for this long -> zero velocity, once
TELEOP_IDLE_S = 60.0        # armed but no non-zero command for this long -> disarm
TELEOP_ARM_MIN_PCT = 10     # arming is refused when the battery is known and below this percent
TELEOP_STOP_PCT = 8         # an armed session is disarmed when the battery drops below this percent
JOURNAL_UNITS = ("turtlebot4.service", "NetworkManager.service", "ssh.service", "systemd-timesyncd.service",
                 "chrony.service")
JOURNAL_SINCE = ("10 min ago", "1 hour ago", "6 hours ago", "1 day ago", "boot")
JOURNAL_LINE_MAX = 600
HAZARD_NAMES = {0: "backup_limit", 1: "bump", 2: "cliff", 3: "stall", 4: "wheel_drop", 5: "object_proximity"}


def log(*a):
    try:
        sys.stderr.write("[bridge] " + " ".join(str(x) for x in a) + "\n")
        sys.stderr.flush()
    except Exception:
        pass


# ======================================================================= pure helpers (tested offline, no ROS)
def clean_json(o, depth=0):
    """Make anything JSON safe: non-finite floats -> None, bytes/arrays/tuples -> lists, unknown objects -> str."""
    if depth > 24:
        return str(o)
    if o is None or isinstance(o, (bool, int, str)):
        return o
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): clean_json(v, depth + 1) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v, depth + 1) for v in o]
    if isinstance(o, (bytes, bytearray)):
        return [int(b) for b in o]
    if hasattr(o, "tolist"):
        try:
            return clean_json(o.tolist(), depth + 1)
        except Exception:
            pass
    try:
        return clean_json(list(o), depth + 1)
    except TypeError:
        return str(o)


def truncate_arrays(o, n=MAX_ARRAY, smax=2000):
    """Arrays longer than n keep n items plus a final "…(+N)" marker; strings longer than smax are cut the same way."""
    if isinstance(o, dict):
        return {k: truncate_arrays(v, n, smax) for k, v in o.items()}
    if isinstance(o, list):
        if len(o) > n:
            return [truncate_arrays(v, n, smax) for v in o[:n]] + ["…(+%d)" % (len(o) - n)]
        return [truncate_arrays(v, n, smax) for v in o]
    if isinstance(o, str) and len(o) > smax:
        return o[:smax] + "…(+%d)" % (len(o) - smax)
    return o


def shrink_msg(data, limit=MAX_MSG_BYTES):
    """Message dict -> JSON safe dict with arrays > 32 truncated and total JSON <= limit bytes."""
    d = clean_json(data)
    for n, smax in ((MAX_ARRAY, 2000), (16, 500), (8, 200), (4, 100), (2, 60), (1, 40), (0, 20)):
        t = truncate_arrays(d, n, smax)
        if len(json.dumps(t, separators=(",", ":"))) <= limit:
            return t
    return {"…truncated": "(+%d bytes)" % len(json.dumps(d))}


def battery_flags(status, current, percent, docked, eps=0.05):
    """(charging, full) from sensor_msgs/BatteryState. The Create 3 always reports power_supply_status 0 (UNKNOWN), so
    the sign of the current decides: > +0.05 A charging, < -0.05 A on battery, otherwise unknown."""
    if status == 1:
        charging = True
    elif status in (2, 3):
        charging = False
    elif current is None:
        charging = None
    elif current > eps:
        charging = True
    elif current < -eps:
        charging = False
    else:
        charging = None
    full = status == 4 or bool(docked and percent is not None and percent >= 99 and current is not None and abs(current) <= eps)
    return charging, full


def wrap_pi(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def yaw_deg_from_quat(x, y, z, w):
    return math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


def scan_front_min(ranges, angle_min, angle_inc, yaw_off=SCAN_YAW_DEFAULT, range_min=BODY_MIN_M, range_max=None,
                   front_half_deg=FRONT_HALF_DEG):
    """(front_m, min_m) of a laser scan. robot angle = laser angle + yaw_off (lidar mounted at +90 deg, so straight
    ahead is laser -90 deg). Front = beams within +-front_half_deg of straight ahead. inf/nan, beams closer than
    range_min (robot body) and beyond range_max are ignored. None when there is no valid beam."""
    half = math.radians(front_half_deg)
    front = low = None
    for i, r in enumerate(ranges):
        if not (r == r) or r == math.inf or r < range_min or (range_max is not None and r > range_max):
            continue
        if low is None or r < low:
            low = r
        if (front is None or r < front) and abs(wrap_pi(angle_min + i * angle_inc + yaw_off)) <= half:
            front = r
    return (None if front is None else round(float(front), 3)), (None if low is None else round(float(low), 3))


# ---- Studio 2.0: scan / pose streams, teleop, journal (pure helpers, tested offline)
def clamp_int(v, lo, hi, default):
    """Integer in [lo, hi]; None/missing -> default; anything that is not a number raises ValueError."""
    if v is None:
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("must be a number")
    return int(min(hi, max(lo, round(v))))


def clamp_float(v, lo, hi, default):
    if v is None:
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("must be a number")
    return float(min(hi, max(lo, v)))


def clamp_teleop(vx, wz, user_linear=None, user_angular=None, max_linear=TELEOP_MAX_LINEAR, max_angular=TELEOP_MAX_ANGULAR):
    """Manual-drive command -> (vx, wz) limited to +-min(hard cap, user limit). Non-numbers, nan and inf give 0."""
    lim_l, lim_a = max_linear, max_angular
    for u, name in ((user_linear, "l"), (user_angular, "a")):
        if isinstance(u, (int, float)) and not isinstance(u, bool) and math.isfinite(u) and u >= 0:
            if name == "l":
                lim_l = min(lim_l, float(u))
            else:
                lim_a = min(lim_a, float(u))

    def one(v, lim):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return 0.0
        return float(max(-lim, min(lim, v)))
    return one(vx, lim_l), one(wz, lim_a)


def downsample_ranges(ranges, max_points, range_min=0.0, range_max=None):
    """Laser ranges -> (out, k): out has at most max_points entries, each the MINIMUM valid range of k neighbouring beams
    (so a thin obstacle is never lost), rounded to 0.01 m. inf, nan, beams closer than range_min (robot body) and beyond
    range_max give None (JSON null). k = beams per bin."""
    n = len(ranges)
    k = max(1, -(-n // max(1, int(max_points))))
    out = []
    for i in range(0, n, k):
        low = None
        for r in ranges[i:i + k]:
            if r is None or not (r == r) or r in (math.inf, -math.inf) or r < range_min or r <= 0.0:
                continue
            if range_max is not None and r > range_max:
                continue
            if low is None or r < low:
                low = r
        out.append(None if low is None else round(float(low), 2))
    return out, k


def build_scan_event(ranges, angle_min, angle_inc, range_min, range_max, yaw_off, max_points, t):
    """The 'scan' event: ranges downsampled and the angles given in the ROBOT frame (0 = straight ahead, counter-clockwise
    positive): angle of ranges[i] = angle_min + i * angle_inc."""
    out, k = downsample_ranges(ranges, max_points, range_min or 0.0, range_max)
    inc = angle_inc * k
    first = wrap_pi(angle_min + angle_inc * (k - 1) / 2.0 + yaw_off)     # centre of the first bin
    rmax = range_max if range_max and math.isfinite(range_max) else 12.0
    return {"ev": "scan", "t": round(t, 3), "frame": "base", "angle_min": round(first, 5), "angle_inc": round(inc, 6),
            "range_max": round(float(rmax), 2), "ranges": out}


def journal_argv(unit, lines, since):
    """journalctl argv (a list, never a shell string) or ValueError. Read-only, no sudo: unit and since come from fixed
    allow-lists, lines is a clamped integer. User text (grep) is never part of the command."""
    unit = unit or JOURNAL_UNITS[0]
    if unit not in JOURNAL_UNITS:
        raise ValueError("unit not allowed (use one of: %s)" % ", ".join(JOURNAL_UNITS))
    try:
        n = clamp_int(lines, 50, 2000, 300)
    except ValueError:
        raise ValueError("lines must be a number")
    argv = ["journalctl", "-u", unit, "-n", str(n), "--no-pager", "-o", "short-iso"]
    if since not in (None, ""):
        if since not in JOURNAL_SINCE:
            raise ValueError("since not allowed (use one of: %s)" % ", ".join(JOURNAL_SINCE))
        argv += ["-b"] if since == "boot" else ["--since", since]
    return argv


def journal_lines(text, grep=None, limit=2000):
    """journalctl output -> list of lines (each cut to 600 chars), optionally only those containing the plain text grep
    (case-insensitive), at most `limit`, newest last."""
    out = []
    g = (grep or "").strip().lower() if isinstance(grep, str) else ""
    for ln in (text or "").splitlines():
        ln = ln.rstrip()
        if not ln or ln.startswith("-- "):
            continue
        if g and g not in ln.lower():
            continue
        out.append(ln[:JOURNAL_LINE_MAX])
    return out[-limit:]


def journal_permission_problem(text):
    t = (text or "").lower()
    return "insufficient permissions" in t or "no journal files were opened" in t or "not seen by" in t


def parse_proc_stat(text):
    """/proc/stat first line -> (total, idle) jiffies or None."""
    for line in (text or "").splitlines():
        if line.startswith("cpu "):
            try:
                nums = [int(x) for x in line.split()[1:9]]
            except ValueError:
                return None
            nums += [0] * (8 - len(nums))
            return sum(nums), nums[3] + nums[4]
    return None


def cpu_pct(prev, cur):
    if not prev or not cur or cur[0] - prev[0] <= 0:
        return None
    return round(100.0 * (1.0 - (cur[1] - prev[1]) / (cur[0] - prev[0])), 1)


def parse_meminfo(text):
    """-> (used_mb, total_mb) or (None, None)."""
    kb = {}
    for line in (text or "").splitlines():
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            kb[m.group(1)] = int(m.group(2))
    if "MemTotal" not in kb or "MemAvailable" not in kb:
        return None, None
    return round((kb["MemTotal"] - kb["MemAvailable"]) / 1024.0), round(kb["MemTotal"] / 1024.0)


def parse_loadavg(text):
    try:
        return float((text or "").split()[0])
    except (ValueError, IndexError):
        return None


def parse_uptime(text):
    try:
        return round(float((text or "").split()[0]), 1)
    except (ValueError, IndexError):
        return None


def parse_throttled(text):
    m = re.search(r"throttled=(0x[0-9a-fA-F]+)", text or "")
    return m.group(1).lower() if m else None


def parse_wireless(text):
    """/proc/net/wireless -> {iface: {link, level}} (empty in access point mode)."""
    out = {}
    for line in (text or "").splitlines()[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        f = rest.split()
        try:
            out[name.strip()] = {"link": float(f[1].rstrip(".")), "level": float(f[2].rstrip("."))}
        except (ValueError, IndexError):
            continue
    return out


def split_nmcli(line):
    """nmcli -t line -> fields (':' separated, '\\:' is a literal colon)."""
    out, cur, i = [], "", 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ":":
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return out


def parse_nmcli_devices(text):
    """`nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device` -> [{device,type,state,connection}]."""
    out = []
    for line in (text or "").splitlines():
        f = split_nmcli(line.strip())
        if len(f) >= 4 and f[0]:
            out.append({"device": f[0], "type": f[1], "state": f[2], "connection": f[3] if f[3] != "--" else ""})
    return out


def parse_ip_addr(text):
    """`ip -o -4 addr show` -> {iface: first ipv4}, loopback skipped."""
    out = {}
    for line in (text or "").splitlines():
        m = re.match(r"\d+:\s+(\S+)\s+inet\s+([\d.]+)/", line)
        if m and m.group(1) != "lo" and m.group(1) not in out:
            out[m.group(1)] = m.group(2)
    return out


def cmdline_matches(cmdline, needle):
    """True when /proc/<pid>/cmdline text (NUL separated) still contains the program name: guards against pid reuse."""
    if not cmdline or not needle:
        return False
    return needle in cmdline.replace("\0", " ")


def safe_join(base, rel):
    """base/rel as an absolute path, or None when rel is empty or escapes base."""
    if not rel or "\0" in rel:
        return None
    base = os.path.realpath(base)
    p = os.path.realpath(os.path.join(base, rel))
    return p if p == base or p.startswith(base + os.sep) else None


def expand_home(path, home, default=None):
    p = default if path in (None, "") else str(path)
    if p == "~":
        return home
    if p.startswith("~/") or p.startswith("~\\"):
        return os.path.join(home, p[2:])
    return p if os.path.isabs(p) else os.path.join(home, p)


def hazard_name(t):
    return HAZARD_NAMES.get(int(t), "type%d" % int(t))


def sha1_file(path, limit=2 * 1024 * 1024):
    try:
        if os.path.getsize(path) > limit:
            return None
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def list_dir(directory, recursive=False, max_entries=5000):
    """ls reply body: non-recursive by default; recursive skips __pycache__, .git, logs."""
    files = []
    skip = {"__pycache__", ".git", "logs"}

    def walk(path, prefix):
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name)
        except OSError:
            return
        for e in entries:
            if len(files) >= max_entries:
                return
            try:
                is_dir = e.is_dir(follow_symlinks=False)
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if is_dir and e.name in skip and recursive:
                continue
            name = prefix + e.name
            files.append({"name": name, "size": 0 if is_dir else st.st_size, "mtime": round(st.st_mtime, 1),
                          "is_dir": is_dir, "sha1": None if is_dir else sha1_file(e.path)})
            if is_dir and recursive:
                walk(e.path, name + "/")
    walk(directory, "")
    return files


def read_text(path, limit=1 << 20):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except (OSError, ValueError):
        return None


def run_cmd(args, timeout=3.0):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except Exception:
        return None
    return p.stdout if p.returncode == 0 else None


def read_cmdline(pid):
    return read_text("/proc/%d/cmdline" % int(pid), 8192)


def pid_alive(pid, needle, reader=read_cmdline, linux=None):
    """Process exists AND its command line still contains needle (so a reused pid is not mistaken for the run)."""
    if not pid:
        return False
    if linux is None:
        linux = sys.platform.startswith("linux")
    if not linux:
        return False
    return cmdline_matches(reader(pid), needle)


def collect_net(run=run_cmd, reader=read_text):
    """Network facts for the status event (called at most every 10 s, in a worker thread)."""
    info = {"wifi_mode": None, "ssid": None, "signal_dbm": None, "link_quality": None, "addresses": {},
            "wlan0_ip": None, "powersave": None, "powersave_students": None}
    info["addresses"] = parse_ip_addr(run(["ip", "-o", "-4", "addr", "show"]) or "")
    info["wlan0_ip"] = info["addresses"].get("wlan0")
    devs = parse_nmcli_devices(run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"]) or "")
    wifi = [d for d in devs if d["type"] == "wifi"]
    if wifi:
        d = wifi[0]
        if d["state"] == "connected" and d["connection"]:
            show = (run(["nmcli", "-t", "-g", "802-11-wireless.mode,802-11-wireless.ssid", "connection", "show",
                         d["connection"]]) or "").splitlines()
            mode = show[0].strip() if show else ""
            info["ssid"] = (show[1].strip() if len(show) > 1 else "") or d["connection"]
            info["wifi_mode"] = "ap" if mode == "ap" else "client"
            w = parse_wireless(reader("/proc/net/wireless") or "").get(d["device"])
            if w:
                info["signal_dbm"], info["link_quality"] = w["level"], w["link"]
            ps = run(["nmcli", "-g", "802-11-wireless.powersave", "connection", "show", d["connection"]])
            if ps and ps.strip():
                # powersave_students: old name of the same value (the UI used to look at one fixed network)
                info["powersave"] = info["powersave_students"] = ps.split()[0].lower()
        else:
            info["wifi_mode"] = "down"
    return info


def collect_slow(run=run_cmd, reader=read_text):
    ntp = (run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]) or "").strip()
    svc = (run(["systemctl", "is-active", "turtlebot4.service"]) or "").strip()
    thr = parse_throttled(run(["vcgencmd", "get_throttled"]) or "") if shutil.which("vcgencmd") else None
    return {"net": collect_net(run, reader), "clock_synced": (ntp == "yes") if ntp else None,
            "ros_service": svc or "unknown", "throttled": thr}


# ---- v1.1: path safety, describe, wifi_info (pure helpers)
NAME_RE = re.compile(r"[A-Za-z0-9_.\-/]+")
MAX_TEXT_BYTES = 512 * 1024
MOVE_KEYWORDS = [("cmd_vel", r"cmd_vel"), ("TwistStamped", r"TwistStamped"), ("Twist(", r"Twist\("),
                 ("/undock", r"/undock"), ("Undock", r"Undock"), ("/dock", r"/dock(?!_status)"),
                 ("DriveDistance", r"DriveDistance"), ("drive_distance", r"drive_distance"),
                 ("RotateAngle", r"RotateAngle"), ("rotate_angle", r"rotate_angle"), ("DriveArc", r"DriveArc"),
                 ("navigate_to_position", r"navigate_to_position"), ("motion_shapes", r"motion_shapes"),
                 ("drive_test", r"drive_test")]


def valid_rel(rel):
    """Relative file name rules: [A-Za-z0-9_.-] plus '/' for subfolders, max 120 chars, no '..', not absolute."""
    if not isinstance(rel, str) or not rel or len(rel) > 120 or not NAME_RE.fullmatch(rel):
        return False
    if rel.startswith("/") or rel.endswith("/") or "//" in rel:
        return False
    return all(part not in ("", "..") for part in rel.split("/"))


def inside_root(real, root):
    """real path is root itself or below it (case-insensitive on Windows)."""
    a, b = os.path.normcase(os.path.realpath(real)), os.path.normcase(os.path.realpath(root))
    return a == b or a.startswith(b + os.sep)


def home_path_ok(real, home):
    """Real path must be inside home and not inside ~/.ssh."""
    return inside_root(real, home) and not inside_root(real, os.path.join(home, ".ssh"))


def code_only(text, ext):
    """The program text without comments and docstrings, so that a comment such as
    'to move, publish on /cmd_vel' does not mark a read-only program as moving.
    Falls back to the full text if a .py file does not parse (safer: more keywords, not fewer)."""
    if ext == ".sh":
        return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    if ext != ".py":
        return text
    try:
        import ast
        import io
        import tokenize
        lines = text.splitlines()
        drop = set()
        for node in ast.walk(ast.parse(text)):
            if (isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant)
                    and isinstance(node.value.value, str)):
                drop.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        kept = [l for i, l in enumerate(lines, 1) if i not in drop]
        out = []
        for tok in tokenize.generate_tokens(io.StringIO("\n".join(kept) + "\n").readline):
            if tok.type != tokenize.COMMENT:
                out.append(tok.string)
        return " ".join(out)
    except Exception:       # SyntaxError, tokenize.TokenError, ...: use the full text
        return text


def detect_moves(text, ext=".py"):
    """Names of the 'robot may move' keywords found in a program's code (comments and docstrings ignored)."""
    code = code_only(text, ext)
    return [name for name, pat in MOVE_KEYWORDS if re.search(pat, code)]


def first_paragraph(text, limit=600):
    text = text.strip()
    if not text:
        return ""
    para = re.split(r"\n\s*\n", text, maxsplit=1)[0]
    para = "\n".join(l.rstrip() for l in para.splitlines())
    return para[:limit]


def extract_docstring(text, ext):
    """First paragraph of the module docstring (.py) or of the leading # comment block (.py without docstring, .sh)."""
    if ext == ".py":
        try:
            import ast
            ds = ast.get_docstring(ast.parse(text))
            if ds:
                return first_paragraph(ds)
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            pass
    block = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#!"):
            continue
        if s.startswith("#"):
            block.append(s.lstrip("#").strip())
        elif not s and not block:
            continue
        else:
            break
    return first_paragraph("\n".join(block))


def extract_usage(text, max_lines=12):
    """argparse-like lines: 'option strings: help text' for every add_argument( found."""
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        if "add_argument(" not in line:
            continue
        chunk = " ".join(lines[i:i + 4])
        chunk = chunk[chunk.index("add_argument(") + len("add_argument("):]
        chunk = chunk.split("add_argument(")[0]          # never take the help text of the next option
        names = []
        for m in re.finditer(r"""^\s*(['"])(.*?)\1\s*,?""", chunk):
            names.append(m.group(2))
            rest = chunk[m.end():]
            while True:
                m2 = re.match(r"""\s*(['"])(.*?)\1\s*,?""", rest)
                if not m2:
                    break
                names.append(m2.group(2))
                rest = rest[m2.end():]
        h = re.search(r"""help\s*=\s*(['"])(.*?)\1""", chunk)
        if names:
            out.append(("%s: %s" % (", ".join(names), h.group(2)) if h else ", ".join(names))[:200])
        if len(out) >= max_lines:
            break
    return out


def describe_file(path):
    """describe entry for one program file, or None if unreadable. Reads at most 512 KB."""
    try:
        st = os.stat(path)
        with open(path, "rb") as f:
            raw = f.read(MAX_TEXT_BYTES)
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace")
    ext = os.path.splitext(path)[1].lower()
    reasons = detect_moves(text, ext)
    return {"name": os.path.basename(path), "size": st.st_size, "mtime": round(st.st_mtime, 1),
            "docstring": extract_docstring(text, ext), "usage": extract_usage(text) if ext == ".py" else [],
            "moves_detected": bool(reasons), "moves_reasons": reasons}


def _nm_bool(s):
    return str(s).strip().lower() in ("yes", "true", "1")


def _nm_powersave(s):
    t = (s or "").split()
    return t[0].lower() if t else None


def collect_wifi(run=run_cmd, reader=read_text):
    """wifi_info body from nmcli (read only; never asks for secrets)."""
    devs = parse_nmcli_devices(run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"]) or "")
    wl = [d for d in devs if d["type"] == "wifi"]
    wlan = {"state": None, "connection": None, "mode": None, "ssid": None, "ip": None, "signal_dbm": None, "powersave": None}

    def conn_fields(name):
        out = (run(["nmcli", "-g", "802-11-wireless.ssid,802-11-wireless.mode,802-11-wireless.powersave",
                    "connection", "show", name]) or "").split("\n")
        out += [""] * (3 - len(out))
        return out[0].strip() or None, out[1].strip() or None, _nm_powersave(out[2])
    if wl:
        d = wl[0]
        wlan["state"], wlan["connection"] = d["state"], d["connection"] or None
        wlan["ip"] = parse_ip_addr(run(["ip", "-o", "-4", "addr", "show"]) or "").get(d["device"])
        if d["connection"]:
            wlan["ssid"], wlan["mode"], wlan["powersave"] = conn_fields(d["connection"])
        w = parse_wireless(reader("/proc/net/wireless") or "").get(d["device"])
        if w and wlan["mode"] != "ap":
            wlan["signal_dbm"] = w["level"]
    saved = []
    listing = run(["nmcli", "-t", "-f", "NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY,ACTIVE", "connection", "show"]) or ""
    for line in listing.splitlines():
        f = split_nmcli(line.strip())
        if len(f) < 5 or "wireless" not in f[1]:
            continue
        ssid, mode, ps = conn_fields(f[0])
        try:
            prio = int(f[3])
        except ValueError:
            prio = 0
        saved.append({"name": f[0], "ssid": ssid, "mode": mode, "autoconnect": _nm_bool(f[2]), "priority": prio,
                      "powersave": ps, "active": _nm_bool(f[4])})
    res = {"wlan0": wlan, "saved": saved, "scan": []}
    if wlan["mode"] == "ap":
        res["scan_note"] = "the robot cannot scan while it runs its hotspot"
    else:
        seen = {}
        for line in (run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,CHAN", "dev", "wifi", "list", "--rescan", "no"], 6.0) or "").splitlines():
            f = split_nmcli(line.strip())
            if len(f) < 4 or not f[0]:
                continue
            try:
                sig = int(f[1])
            except ValueError:
                sig = None
            if f[0] not in seen or (sig or 0) > (seen[f[0]]["signal"] or 0):
                seen[f[0]] = {"ssid": f[0], "signal": sig, "security": f[2] or "open", "chan": f[3]}
        res["scan"] = sorted(seen.values(), key=lambda e: -(e["signal"] or 0))[:40]
    return res


# ---- v1.2: join any Wi-Fi network (S-c)
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


# ======================================================================= single locked writer
# ======================================================================= mapping helpers (pure, Studio 2.1)
MAP_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}")
MAP_EXTS = (".pgm", ".yaml", ".posegraph", ".data")
SLAM_PATTERN = "slam.launch.py"                      # pgrep -f patterns, the same as delivery/robot/start_stack.sh
OTHER_STACK_PATTERNS = ("localization.launch.py", "delivery_stack.launch.py", "nav2.launch.py")
NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
PGM_SPACE = (b" ", b"\t", b"\r", b"\n", b"\x0b", b"\x0c")


def valid_map_name(name):
    """True for a map name: 1 to 48 characters of A-Z a-z 0-9 _ -, starting with a letter or digit."""
    return isinstance(name, str) and MAP_NAME_RE.fullmatch(name) is not None


def parse_map_yaml(text):
    """Minimal map_server YAML (flat key: value lines, no PyYAML) -> {image, resolution, origin [x, y, yaw], negate,
    occupied_thresh, free_thresh, mode}. Raises ValueError without image or a positive resolution."""
    vals = {}
    for line in str(text).splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            vals[k.strip()] = v.strip()

    def unquote(s):
        return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"" else s

    def num(key, default):
        m = NUM_RE.match(vals.get(key, ""))
        return float(m.group(0)) if m else default

    image = unquote(vals.get("image", ""))
    if not image:
        raise ValueError("the map YAML has no image")
    res = num("resolution", 0.0)
    if res <= 0:
        raise ValueError("the map YAML has no valid resolution")
    org = [float(x) for x in NUM_RE.findall(vals.get("origin", ""))]
    if len(org) == 2:
        org.append(0.0)
    origin = org[:3] if len(org) >= 3 else [0.0, 0.0, 0.0]
    return {"image": image, "resolution": res, "origin": origin, "negate": int(num("negate", 0)),
            "occupied_thresh": num("occupied_thresh", 0.65), "free_thresh": num("free_thresh", 0.25),
            "mode": unquote(vals.get("mode", "trinary")) or "trinary"}


def rewrite_yaml_image(text, image):
    """The map YAML text with its image: line set to image (added at the top when missing)."""
    new, n = re.subn(r"(?m)^(\s*image\s*:).*$", lambda m: "%s %s" % (m.group(1), image), text, count=1)
    return new if n else "image: %s\n%s" % (image, text)


def pgm_header(data):
    """Header of a PGM (P5 binary or P2 ascii, '#' comments) -> (kind, width, height, maxval, offset after maxval)."""
    n = len(data)
    pos = 0

    def token():
        nonlocal pos
        while pos < n:
            ch = data[pos:pos + 1]
            if ch == b"#":
                while pos < n and data[pos:pos + 1] not in (b"\n", b"\r"):
                    pos += 1
            elif ch in PGM_SPACE:
                pos += 1
            else:
                break
        start = pos
        while pos < n and data[pos:pos + 1] not in PGM_SPACE and data[pos:pos + 1] != b"#":
            pos += 1
        if start == pos:
            raise ValueError("PGM header is incomplete")
        return bytes(data[start:pos])
    kind = token()
    if kind not in (b"P5", b"P2"):
        raise ValueError("not a PGM file (P5 or P2 expected)")
    try:
        w, h, mx = int(token()), int(token()), int(token())
    except ValueError:
        raise ValueError("PGM header is not numeric")
    if w < 1 or h < 1 or w > 100000 or h > 100000:
        raise ValueError("PGM size is not valid")
    if mx < 1 or mx > 255:
        raise ValueError("PGM maxval above 255 is not supported")
    return kind.decode(), w, h, mx, pos


def read_pgm(data):
    """PGM bytes (P5 or P2, maxval <= 255) -> (width, height, pixel bytes), row 0 = top row of the file."""
    kind, w, h, mx, pos = pgm_header(data)
    if kind == "P5":
        pix = bytes(data[pos + 1:pos + 1 + w * h])
    else:
        body = re.sub(rb"#[^\r\n]*", b"", bytes(data[pos:]))
        try:
            vals = [int(x) for x in body.split()]
        except ValueError:
            raise ValueError("PGM pixels are not numeric")
        if any(v < 0 or v > mx for v in vals[:w * h]):
            raise ValueError("PGM pixel above maxval")
        pix = bytes(vals[:w * h])
    if len(pix) != w * h:
        raise ValueError("PGM has %d pixels, expected %d" % (len(pix), w * h))
    return w, h, pix


def sample_grid(w, h, data, stride):
    """Every stride-th cell of every stride-th row (nearest sample, bytes slicing) -> (width, height, bytes)."""
    s = max(1, int(stride))
    rows = [data[y * w:(y + 1) * w][::s] for y in range(h)[::s]]
    return len(range(w)[::s]), len(rows), b"".join(rows)


def choose_stride(w, h, max_cells):
    """Smallest stride >= 1 for which the sampled grid has at most max_cells cells."""
    s = 1
    while ((w + s - 1) // s) * ((h + s - 1) // s) > max_cells and s < max(w, h):
        s += 1
    return s


def cells_bytes(cells):
    """OccupancyGrid data (int8: -1 unknown, 0..100) as bytes, like array('b').tobytes(): unknown becomes 255."""
    if isinstance(cells, (bytes, bytearray)):
        return bytes(cells)
    if hasattr(cells, "tobytes") and getattr(cells, "itemsize", 1) == 1:
        return cells.tobytes()
    return bytes(int(v) & 0xFF for v in cells)


def pack_cells(raw):
    """bytes -> base64 text of zlib data."""
    return base64.b64encode(zlib.compress(raw, 6)).decode("ascii")


def encode_cells(cells):
    """OccupancyGrid data -> base64 of zlib of one byte per cell (0..100, 255 unknown)."""
    return pack_cells(cells_bytes(cells))


def build_map_event(seq, t, width, height, resolution, origin, cells, max_cells):
    """The `map` event: the grid sampled to at most max_cells cells (stride in both directions; width, height and
    resolution are the sampled values), encoding "cells", row 0 = bottom row."""
    raw = cells_bytes(cells)
    stride = choose_stride(width, height, max_cells)
    w, h = width, height
    if stride > 1:
        w, h, raw = sample_grid(width, height, raw, stride)
    return {"ev": "map", "seq": seq, "t": round(t, 3), "width": w, "height": h,
            "resolution": round(resolution * stride, 6),
            "origin": {"x": round(origin[0], 4), "y": round(origin[1], 4), "yaw": round(origin[2], 4)},
            "stride": stride, "encoding": "cells", "data": pack_cells(raw)}


def pose_compose(a, b):
    """2D rigid transforms (x, y, yaw): a followed by b."""
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], wrap_pi(a[2] + b[2]))


def pose_inverse(p):
    c, s = math.cos(p[2]), math.sin(p[2])
    return (-(c * p[0] + s * p[1]), -(-s * p[0] + c * p[1]), wrap_pi(-p[2]))


def compose_map_pose(slam_pose, odom_at_slam, odom_now):
    """Pose in the map frame: the slam_toolbox pose moved forward by the odometry since it was published.
    map<-odom = slam * inverse(odom at that time); result = map<-odom * odometry now. All are (x, y, yaw)."""
    return pose_compose(pose_compose(slam_pose, pose_inverse(odom_at_slam)), odom_now)


def detect_stack(running):
    """running(pattern) -> bool. Returns (slam_running, name of a running navigation launch or None)."""
    other = None
    for pat in OTHER_STACK_PATTERNS:
        if running(pat):
            other = pat
            break
    return bool(running(SLAM_PATTERN)), other


def tail_lines(text, n=20):
    """The last n non-empty lines of a script output, as a list."""
    return [ln.rstrip()[:300] for ln in str(text or "").splitlines() if ln.strip()][-n:]


class Writer:
    """All stdout output goes through one queue and one writer thread, so ROS callbacks never block on a slow pipe.
    Droppable events (status, msg) are dropped when the queue is long; replies are never dropped."""

    def __init__(self, stream, on_broken=None, max_droppable=400):
        self.stream, self.on_broken, self.max_droppable = stream, on_broken, max_droppable
        self.q = collections.deque()
        self.cv = threading.Condition()
        self.closed = False
        self.dropped = 0
        self.thread = threading.Thread(target=self._run, name="writer", daemon=True)
        self.thread.start()

    def emit(self, obj, droppable=False):
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
            self.q.append(line)
            self.cv.notify()

    def _run(self):
        while True:
            with self.cv:
                while not self.q and not self.closed:
                    self.cv.wait()
                if not self.q:
                    return
                data = b"".join(self.q)
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


class RosReal(RosBase):
    def __init__(self):
        self.available = False
        self.error = None
        self.emit = lambda *a, **k: None
        self._lock = threading.Lock()
        self._odom = self._scan = self._wheel = None        # (raw bytes, receive monotonic)
        self._odom_n = self._scan_n = 0
        self._map = None                                    # (raw OccupancyGrid bytes, receive monotonic)
        self._map_n = 0
        self._slam = None                                   # ((x, y, yaw), odom (x, y, yaw) or None, receive monotonic)
        self._map_subs = False
        self._rate = {}
        self._battery = {}
        self._dock = {}
        self._haz = collections.deque(maxlen=64)
        self._dock_t = self._batt_t = None
        self._scan_frame = None
        self._scan_yaw = SCAN_YAW_DEFAULT
        self._yaw_assumed = True
        self._tf_started = False
        self._goals = {}
        self._clients = {}
        self._watches = {}
        self._own_subs = collections.Counter()
        self._own_pubs = collections.Counter()
        self._stop = threading.Event()
        self._cache = {}

    # ---- startup
    def start(self, emit):
        self.emit = emit
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import qos_profile_sensor_data
            from rclpy.serialization import deserialize_message
            from geometry_msgs.msg import Twist, TwistStamped
            from nav_msgs.msg import Odometry
            from sensor_msgs.msg import BatteryState, LaserScan
            from std_srvs.srv import Empty
            from irobot_create_msgs.msg import DockStatus, HazardDetectionVector, WheelStatus
            from irobot_create_msgs.srv import EStop
            try:
                from rclpy.signals import SignalHandlerOptions
                rclpy.init(args=None, signal_handler_options=SignalHandlerOptions.NO)
            except ImportError:
                rclpy.init(args=None)
        except Exception as e:
            self.error = "%s: %s" % (type(e).__name__, e)
            log("ROS not available:", self.error)
            return
        self.rclpy, self.deser, self.sensor_qos = rclpy, deserialize_message, qos_profile_sensor_data
        self.M = dict(Twist=Twist, TwistStamped=TwistStamped, Odometry=Odometry, LaserScan=LaserScan,
                      BatteryState=BatteryState, DockStatus=DockStatus, WheelStatus=WheelStatus, Empty=Empty,
                      EStop=EStop, HazardDetectionVector=HazardDetectionVector)
        try:
            self.node = rclpy.create_node("studio_bridge_%d" % os.getpid(), start_parameter_services=False,
                                          enable_rosout=False)
            # publishers first: the e-stop must have no set-up delay
            self.pub_cmd = self.node.create_publisher(TwistStamped, "/cmd_vel", 10)
            self.pub_unst = self.node.create_publisher(Twist, "/cmd_vel_unstamped", 10)
            self._own_pubs.update(["/cmd_vel", "/cmd_vel_unstamped"])
            q = qos_profile_sensor_data

            def sub(cls, topic, cb, raw=False):
                self.node.create_subscription(cls, topic, cb, q, raw=raw)
                self._own_subs[topic] += 1

            sub(Odometry, "/odom", self._cb_odom, raw=True)
            sub(LaserScan, "/scan", self._cb_scan, raw=True)
            sub(WheelStatus, "/wheel_status", self._cb_wheel, raw=True)      # ~30 Hz: bytes only, parsed per status tick
            sub(BatteryState, "/battery_state", self._cb_battery)
            sub(DockStatus, "/dock_status", self._cb_dock)
            sub(HazardDetectionVector, "/hazard_detection", self._cb_haz)
            self._svc = {"/e_stop": self.node.create_client(EStop, "/e_stop"),
                         "/start_motor": self.node.create_client(Empty, "/start_motor"),
                         "/stop_motor": self.node.create_client(Empty, "/stop_motor")}
            # Single-threaded on purpose: MultiThreadedExecutor cost about 97 % of a Pi 4 core on 2026-10-24,
            # the single-threaded one 11 % for the same subscriptions. Calls wait on futures in their own threads.
            self.executor = SingleThreadedExecutor()
            self.executor.add_node(self.node)
            self._spin = threading.Thread(target=self._spin_loop, name="rclpy", daemon=True)
            self._spin.start()
            self.available = True
        except Exception as e:
            self.error = "%s: %s" % (type(e).__name__, e)
            log("ROS set-up failed:", self.error)

    def _spin_loop(self):
        try:
            self.executor.spin()
        except Exception as e:
            log("executor stopped:", e)

    def shutdown(self):
        self._stop.set()
        if not self.available:
            return
        self.available = False
        try:
            self.executor.shutdown(timeout_sec=0.5)
        except Exception:
            pass
        try:
            self.node.destroy_node()
            self.rclpy.shutdown()
        except Exception:
            pass

    # ---- callbacks: tiny, never block
    def _cb_odom(self, data):
        self._odom = (data, time.monotonic())
        self._odom_n += 1

    def _cb_scan(self, data):
        self._scan = (data, time.monotonic())
        self._scan_n += 1

    def _cb_wheel(self, data):
        self._wheel = (data, time.monotonic())

    def _cb_battery(self, m):
        self._battery = {"percent": None if not math.isfinite(m.percentage) else round(m.percentage * 100.0, 1)
                         if m.percentage <= 1.5 else round(m.percentage, 1),
                         "voltage": round(m.voltage, 2) if math.isfinite(m.voltage) else None,
                         "charging": None, "_status": int(m.power_supply_status),
                         "current_a": round(m.current, 2) if math.isfinite(m.current) else None}
        self._batt_t = time.monotonic()

    def _cb_dock(self, m):
        self._dock = {"is_docked": bool(m.is_docked), "dock_visible": bool(m.dock_visible)}
        self._dock_t = time.monotonic()

    def _cb_haz(self, m):
        now = time.monotonic()
        for d in m.detections:
            self._haz.append((now, hazard_name(d.type)))

    # ---- snapshot (called at the status period, off the executor thread)
    def _rate_of(self, name, n, now):
        pn, pt, rate = self._rate.get(name, (0, now, None))
        if now - pt >= 0.5:
            rate = round((n - pn) / (now - pt), 1) if (n or pn) else None
            self._rate[name] = (n, now, rate)
        elif name not in self._rate:
            self._rate[name] = (pn, pt, rate)
        return rate

    def snapshot(self):
        now = time.monotonic()
        out = {"battery": {"percent": None, "voltage": None, "charging": None, "current_a": None, "full": None}, "dock": {"is_docked": None, "dock_visible": None},
               "odom": {"x": None, "y": None, "yaw_deg": None, "vx": None, "wz": None, "age_s": None, "rate_hz": None},
               "scan": {"rate_hz": None, "front_m": None, "min_m": None, "age_s": None},
               "hazards": [], "wheels_enabled": None}
        if not self.available:
            return out
        out["dock"].update(self._dock)
        out["battery"].update({k: v for k, v in self._battery.items() if not k.startswith("_")})
        if self._battery:
            b = out["battery"]
            b["charging"], b["full"] = battery_flags(self._battery.get("_status"), b.get("current_a"), b.get("percent"),
                                                     out["dock"].get("is_docked"))
        od = self._odom
        if od is not None:
            o = out["odom"]
            o["age_s"], o["rate_hz"] = round(now - od[1], 2), self._rate_of("odom", self._odom_n, now)
            try:
                m = self._cached("odom", od[0], lambda: self.deser(od[0], self.M["Odometry"]))
                p, q, tw = m.pose.pose.position, m.pose.pose.orientation, m.twist.twist
                o.update(x=round(p.x, 3), y=round(p.y, 3), yaw_deg=round(yaw_deg_from_quat(q.x, q.y, q.z, q.w), 1),
                         vx=round(tw.linear.x, 3), wz=round(tw.angular.z, 3))
            except Exception as e:
                log("odom decode:", e)
        sc = self._scan
        if sc is not None:
            s = out["scan"]
            s["age_s"], s["rate_hz"] = round(now - sc[1], 2), self._rate_of("scan", self._scan_n, now)
            try:
                m = self._cached("scan", sc[0], lambda: self.deser(sc[0], self.M["LaserScan"]))
                if self._scan_frame is None:
                    self._scan_frame = m.header.frame_id
                    self._start_tf(m.header.frame_id)
                rmax = m.range_max if m.range_max and math.isfinite(m.range_max) else None
                s["front_m"], s["min_m"] = scan_front_min(m.ranges, m.angle_min, m.angle_increment, self._scan_yaw,
                                                          max(BODY_MIN_M, m.range_min or 0.0), rmax)
            except Exception as e:
                log("scan decode:", e)
            s["scan_yaw_assumed"] = self._yaw_assumed
        out["hazards"] = sorted({n for t, n in list(self._haz) if now - t <= HAZARD_WINDOW})
        wh = self._wheel
        if wh is not None and now - wh[1] < 5.0:
            try:
                m = self._cached("wheel", wh[0], lambda: self.deser(wh[0], self.M["WheelStatus"]))
                out["wheels_enabled"] = bool(m.wheels_enabled)
            except Exception as e:
                log("wheel decode:", e)
        return out

    def _cached(self, key, raw, fn):
        c = self._cache.get(key)
        if c and c[0] is raw:
            return c[1]
        v = fn()
        self._cache[key] = (raw, v)
        return v

    def _start_tf(self, frame):
        if self._tf_started or not frame:
            return
        self._tf_started = True
        threading.Thread(target=self._tf_lookup, args=(frame,), name="tf", daemon=True).start()

    def _tf_lookup(self, frame):
        """One-shot TF lookup base_link <- scan frame, then the listener is dropped (it would cost CPU at /tf rates)."""
        lis = None
        try:
            import tf2_ros
            buf = tf2_ros.Buffer()
            lis = tf2_ros.TransformListener(buf, self.node, spin_thread=False)
            end = time.monotonic() + 10.0
            while time.monotonic() < end and not self._stop.is_set():
                try:
                    t = buf.lookup_transform("base_link", frame, self.rclpy.time.Time())
                    q = t.transform.rotation
                    self._scan_yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
                    self._yaw_assumed = False
                    log("scan yaw from TF: %.1f deg" % math.degrees(self._scan_yaw))
                    break
                except Exception:
                    time.sleep(0.3)
        except Exception as e:
            log("TF not used, assuming +90 deg:", e)
        finally:
            try:
                if lis is not None:
                    lis.unregister()
            except Exception:
                pass

    # ---- Studio 2.0: manual driving, scan and pose streams (reuse the existing node, publisher and subscriptions)
    def publish_cmd(self, vx, wz):
        ts = self.M["TwistStamped"]()
        ts.header.stamp = self.node.get_clock().now().to_msg()
        ts.twist.linear.x = float(vx)
        ts.twist.angular.z = float(wz)
        self.pub_cmd.publish(ts)
        if vx == 0.0 and wz == 0.0:
            self.pub_unst.publish(self.M["Twist"]())       # a zero must reach whichever topic the base listens to

    def is_docked(self):
        v = self._dock.get("is_docked")
        return None if v is None else bool(v)

    def scan_data(self):
        sc = self._scan
        if sc is None or not self.available:
            return None
        try:
            m = self._cached("scan", sc[0], lambda: self.deser(sc[0], self.M["LaserScan"]))
            if self._scan_frame is None:
                self._scan_frame = m.header.frame_id
                self._start_tf(m.header.frame_id)
            return {"ranges": m.ranges, "angle_min": m.angle_min, "angle_inc": m.angle_increment,
                    "range_min": max(BODY_MIN_M, m.range_min or 0.0), "range_max": m.range_max, "yaw": self._scan_yaw,
                    "seq": self._scan_n, "age_s": time.monotonic() - sc[1], "yaw_assumed": self._yaw_assumed}
        except Exception as e:
            log("scan decode:", e)
            return None

    def pose_data(self):
        od = self._odom
        if od is None or not self.available:
            return None
        try:
            m = self._cached("odom", od[0], lambda: self.deser(od[0], self.M["Odometry"]))
            p, q, tw = m.pose.pose.position, m.pose.pose.orientation, m.twist.twist
            return {"x": p.x, "y": p.y, "yaw": math.radians(yaw_deg_from_quat(q.x, q.y, q.z, q.w)),
                    "vx": tw.linear.x, "wz": tw.angular.z, "age_s": time.monotonic() - od[1], "seq": self._odom_n}
        except Exception as e:
            log("odom decode:", e)
            return None

    # ---- map (subscriptions are created on the first map_on and kept; decoded only when the stream asks)
    def ensure_map_subs(self):
        with self._lock:
            if self._map_subs:
                return
            if not self.available:
                raise RosError("ROS not available: %s" % (self.error or "not started"))
            try:
                from geometry_msgs.msg import PoseWithCovarianceStamped
                from nav_msgs.msg import OccupancyGrid
                from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
                qos = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
                self.M["OccupancyGrid"] = OccupancyGrid
                self.node.create_subscription(OccupancyGrid, "/map", self._cb_map, qos, raw=True)
                self.node.create_subscription(PoseWithCovarianceStamped, "/pose", self._cb_slam_pose, 10)
            except Exception as e:
                raise RosError("cannot subscribe to /map and /pose: %s: %s" % (type(e).__name__, e))
            self._own_subs.update(["/map", "/pose"])
            self._map_subs = True

    def _cb_map(self, data):
        self._map = (data, time.monotonic())
        self._map_n += 1

    def _cb_slam_pose(self, m):
        try:
            p, q = m.pose.pose.position, m.pose.pose.orientation
            slam = (p.x, p.y, math.radians(yaw_deg_from_quat(q.x, q.y, q.z, q.w)))
            od = self.pose_data()
            odom = (od["x"], od["y"], od["yaw"]) if od and od["age_s"] < 1.0 else None
            self._slam = (slam, odom, time.monotonic())
        except Exception as e:
            log("slam pose:", e)

    def map_data(self):
        mp = self._map
        if mp is None or not self.available:
            return None
        try:
            m = self._cached("map", mp[0], lambda: self.deser(mp[0], self.M["OccupancyGrid"]))
            i = m.info
            if i.width < 1 or i.height < 1 or len(m.data) != i.width * i.height:
                return None
            q = i.origin.orientation
            yaw = math.radians(yaw_deg_from_quat(q.x, q.y, q.z, q.w))
            return {"seq": self._map_n, "width": i.width, "height": i.height, "resolution": i.resolution,
                    "origin": (i.origin.position.x, i.origin.position.y, yaw), "cells": m.data,
                    "age_s": time.monotonic() - mp[1]}
        except Exception as e:
            log("map decode:", e)
            return None

    def map_pose(self):
        od = self.pose_data()
        if od is None or od["age_s"] > 2.0:
            return None
        now = (od["x"], od["y"], od["yaw"])
        sl = self._slam
        if sl is None or sl[1] is None:
            return {"x": now[0], "y": now[1], "yaw": now[2], "source": "odom"}
        x, y, yaw = compose_map_pose(sl[0], sl[1], now)
        return {"x": x, "y": y, "yaw": yaw, "source": "slam"}

    # ---- graph
    def topics(self):
        out = []
        for name, types in sorted(self.node.get_topic_names_and_types()):
            pubs = max(0, self.node.count_publishers(name) - self._own_pubs.get(name, 0))
            subs = max(0, self.node.count_subscribers(name) - self._own_subs.get(name, 0))
            out.append({"name": name, "types": list(types), "publishers": pubs, "subscribers": subs})
        return out

    def watch_add(self, topic, typ, max_hz, on_msg):
        if not typ:
            types = dict(self.node.get_topic_names_and_types()).get(topic)
            if not types:
                raise RosError("topic %s not found (give a type)" % topic)
            typ = types[0]
        from rosidl_runtime_py.utilities import get_message
        from rosidl_runtime_py import message_to_ordereddict
        cls = get_message(typ)
        state = {"n": 0, "last": 0.0, "t0": time.monotonic(), "rate": None, "n0": 0}
        min_dt = 1.0 / max(0.05, float(max_hz))

        def cb(data):
            now = time.monotonic()
            state["n"] += 1
            if now - state["t0"] >= 1.0:
                state["rate"] = round((state["n"] - state["n0"]) / (now - state["t0"]), 1)
                state["n0"], state["t0"] = state["n"], now
            if now - state["last"] < min_dt:
                return
            state["last"] = now
            try:
                on_msg(message_to_ordereddict(self.deser(data, cls)), state["rate"])
            except Exception as e:
                log("watch decode:", e)

        s = self.node.create_subscription(cls, topic, cb, self.sensor_qos, raw=True)
        key = object()
        self._watches[key] = (s, topic)
        self._own_subs[topic] += 1
        return key, typ

    def watch_remove(self, key):
        w = self._watches.pop(key, None)
        if w:
            self._own_subs[w[1]] -= 1
            try:
                self.node.destroy_subscription(w[0])
            except Exception:
                pass

    # ---- publish / services / actions
    def zero_burst(self, n=10, hz=20.0):
        sent = 0
        for i in range(n):
            ts = self.M["TwistStamped"]()
            ts.header.stamp = self.node.get_clock().now().to_msg()
            self.pub_cmd.publish(ts)
            self.pub_unst.publish(self.M["Twist"]())
            sent += 1
            if i < n - 1:
                time.sleep(1.0 / hz)
        return sent

    def _call(self, name, req, timeout):
        cl = self._svc[name]
        end = time.monotonic() + timeout
        while not cl.service_is_ready():
            if time.monotonic() >= end:
                raise RosError("service %s not available" % name)
            time.sleep(0.05)
        done = threading.Event()
        fut = cl.call_async(req)
        fut.add_done_callback(lambda f: done.set())
        if not done.wait(max(0.1, end - time.monotonic())):
            try:
                cl.remove_pending_request(fut)
            except Exception:
                pass
            raise RosError("service %s timed out after %.0f s" % (name, timeout))
        return fut.result()

    def call_estop(self, on, timeout=3.0):
        req = self.M["EStop"].Request()
        req.e_stop_on = bool(on)
        r = self._call("/e_stop", req, timeout)
        return bool(r.success), str(r.message)

    def lidar(self, on, timeout=5.0):
        self._call("/start_motor" if on else "/stop_motor", self.M["Empty"].Request(), timeout)
        return "lidar motor %s" % ("start" if on else "stop")

    def services_ready(self):
        return {n: bool(c.service_is_ready()) for n, c in self._svc.items()}

    def _client(self, name):
        if name in self._clients:
            return self._clients[name]
        from rclpy.action import ActionClient
        from irobot_create_msgs.action import Dock, Undock
        cls = {"dock": Dock, "undock": Undock}[name]
        c = (ActionClient(self.node, cls, "/" + name), cls)
        self._clients[name] = c
        return c

    def start_action(self, name, timeout=5.0):
        if name not in ("dock", "undock"):
            raise RosError("unknown action %s" % name)
        client, cls = self._client(name)
        if not client.wait_for_server(timeout_sec=2.0):
            raise RosError("action server /%s not available" % name)
        last_fb = [0.0]

        def fb(msg):
            if time.monotonic() - last_fb[0] >= 1.0:
                last_fb[0] = time.monotonic()
                self.emit({"ev": "action", "name": name, "state": "feedback", "detail": str(msg.feedback)[:200]}, True)

        done = threading.Event()
        fut = client.send_goal_async(cls.Goal(), feedback_callback=fb)
        fut.add_done_callback(lambda f: done.set())
        if not done.wait(timeout):
            raise RosError("goal for /%s not answered in %.0f s" % (name, timeout))
        gh = fut.result()
        if not gh.accepted:
            self.emit({"ev": "action", "name": name, "state": "rejected", "detail": ""})
            return {"accepted": False}
        self._goals[name] = gh
        self.emit({"ev": "action", "name": name, "state": "accepted", "detail": ""})

        def res(f):
            self._goals.pop(name, None)
            try:
                st = f.result().status
            except Exception as e:
                self.emit({"ev": "action", "name": name, "state": "aborted", "detail": str(e)})
                return
            state = {4: "succeeded", 5: "canceled", 6: "aborted"}.get(st, "aborted")
            self.emit({"ev": "action", "name": name, "state": state, "detail": "status %s" % st})
        gh.get_result_async().add_done_callback(res)
        return {"accepted": True}

    def cancel_action(self, name, timeout=3.0):
        gh = self._goals.get(name)
        if gh is None:
            return False
        done = threading.Event()
        fut = gh.cancel_goal_async()
        fut.add_done_callback(lambda f: done.set())
        done.wait(timeout)
        return True

    def cancel_all_actions(self):
        names = list(self._goals)
        for n in names:
            try:
                self.cancel_action(n, 2.0)
            except Exception as e:
                log("cancel", n, e)
        return names


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


# ======================================================================= runs
class Run:
    def __init__(self, run_id, name, pid, log_path, path, started_wall, motion, proc=None):
        self.run_id, self.name, self.pid, self.log, self.path = run_id, name, pid, log_path, path
        self.started_wall, self.motion, self.proc = started_wall, bool(motion), proc
        self.offset = 0
        self.pending = ""
        self.exit_sent = False
        self.code = None
        self.needle = os.path.basename(path)

    def info(self, alive):
        return {"run_id": self.run_id, "name": self.name, "pid": self.pid, "alive": alive,
                "started_wall": self.started_wall, "motion": self.motion, "log": self.log, "code": self.code}


FAKE_HOTSPOT = "netplan-wlan0-Turtlebot4"
# (ssid, security as nmcli prints it, signal %, channel)
FAKE_SCAN = [("HomeNet", "WPA2", 70, "6"), ("Students", "WPA2", 55, "11"), ("eduroam", "WPA2 802.1X", 48, "36"),
             ("CafeFree", "--", 40, "1"), ("FailNet", "WPA2", 30, "3"), ("PhoneHotspot", "WPA2 WPA3", 62, "9")]
try:
    FAKE_WIFI_SCALE = max(0.0, float(os.environ.get("STUDIO_FAKE_WIFI_SCALE", "1")))  # tests may speed the simulation up
except ValueError:
    FAKE_WIFI_SCALE = 1.0


def fake_wifi_state():
    """The fake robot is a client of HomeNet; Students is saved but out of reach; the hotspot profile exists."""
    return {"cur": "HomeNet", "ip": "192.168.50.12", "n": 0, "join": None,
            "saved": [{"name": "HomeNet", "ssid": "HomeNet", "mode": "infrastructure", "autoconnect": True, "priority": 10,
                       "powersave": "default"},
                      {"name": "Students", "ssid": "Students", "mode": "infrastructure", "autoconnect": True, "priority": 10,
                       "powersave": "disable"},
                      {"name": FAKE_HOTSPOT, "ssid": "Turtlebot4", "mode": "ap", "autoconnect": True, "priority": 0,
                       "powersave": "default"}]}


# ======================================================================= mapping: adapters and services (Studio 2.1)
START_TIMEOUT_S, SAVE_TIMEOUT_S, STOP_TIMEOUT_S = 120.0, 200.0, 90.0       # the delivery scripts, see DESIGN-MAPPING.md
MAP_SCRIPTS = ("start_stack.sh", "save_map.sh", "stop_stack.sh")


class ServiceError(Exception):
    """A refusal of a service (bad name, wrong state, ...). extra goes into the reply (for example exists=True)."""

    def __init__(self, msg, **extra):
        Exception.__init__(self, msg)
        self.extra = extra


class StackRunner:
    """Runs one of the delivery scripts and waits for it: run(script, args, timeout) -> (ok, output text)."""

    def scripts_ok(self):
        raise NotImplementedError

    def missing_scripts(self):
        return []

    def run(self, script, args, timeout):
        raise NotImplementedError


class RealStackRunner(StackRunner):
    """bash <delivery>/robot/<script> args, cwd = home, output captured. Delivery folder: ~/robot_code/delivery, or the
    environment variable STUDIO_DELIVERY_DIR."""

    def __init__(self, home):
        self.home = home
        self.delivery = os.environ.get("STUDIO_DELIVERY_DIR") or os.path.join(home, "robot_code", "delivery")

    def script_path(self, script):
        return os.path.join(self.delivery, "robot", script)

    def missing_scripts(self):
        return [s for s in MAP_SCRIPTS if not os.path.isfile(self.script_path(s))]

    def scripts_ok(self):
        return not self.missing_scripts()

    def run(self, script, args, timeout):
        argv = ["bash", self.script_path(script)] + [str(a) for a in args]
        kw = {"start_new_session": True} if os.name == "posix" else {}
        try:
            p = subprocess.Popen(argv, cwd=self.home, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, **kw)
        except OSError as e:
            return False, "cannot run %s: %s" % (script, e)
        try:
            out, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(p.pid, signal.SIGTERM)
                else:
                    p.kill()
            except OSError:
                pass
            try:
                out, _ = p.communicate(timeout=5)
            except Exception:
                out = b""
            return False, out.decode("utf-8", "replace") + "\n%s timed out after %d s" % (script, timeout)
        return p.returncode == 0, out.decode("utf-8", "replace")


class FakeStackRunner(StackRunner):
    """No processes: timers (starting 1.5 s, saving 1 s, stopping 1 s, times STUDIO_FAKE_MAP_SCALE) and a FakeMapGrid
    that saves real files."""

    def __init__(self, ros, scale=None):
        self.scale = fake_map_scale() if scale is None else scale
        self.ros = ros
        self.grid = getattr(ros, "map_grid", None) or FakeMapGrid(self.scale)
        self.slam_running = False

    def scripts_ok(self):
        return True

    def _pose(self):
        try:
            p = self.ros.pose_data()
            return p["x"], p["y"], p["yaw"]
        except Exception:
            return 0.0, 0.0, 0.0

    def run(self, script, args, timeout):
        args = [str(a) for a in args]
        if script == "start_stack.sh":
            time.sleep(1.5 * self.scale)
            if "map" not in args:
                return False, "ERROR: give a mode: map or nav"
            self.slam_running = True
            self.grid.begin(self._pose)
            return True, "fake: slam started"
        if script == "save_map.sh":
            time.sleep(1.0 * self.scale)
            if not self.slam_running:
                return False, "ERROR: the fake mapping is not running"
            prefix = next((a for a in args if not a.startswith("-")), "")
            if not prefix:
                return False, "ERROR: give the output path prefix"
            if os.path.exists(prefix + ".yaml") and "--force" not in args:
                return False, "ERROR: %s.yaml exists (use --force to overwrite)" % prefix
            self.grid.save(prefix)
            return True, "fake: saved %s" % prefix
        if script == "stop_stack.sh":
            time.sleep(1.0 * self.scale)
            was = self.slam_running
            self.slam_running = False
            self.grid.end()
            self.grid.reset()
            return True, "slam: sending SIGINT (fake)" if was else "slam: not running"
        return False, "unknown script %s" % script


class ProcessProbe:
    def running(self, pattern):
        raise NotImplementedError


class RealProcessProbe(ProcessProbe):
    def running(self, pattern):
        return bool((run_cmd(["pgrep", "-f", pattern], timeout=3.0) or "").split())


class FakeProcessProbe(ProcessProbe):
    def __init__(self, runner):
        self.runner = runner

    def running(self, pattern):
        return pattern == SLAM_PATTERN and bool(self.runner.slam_running)


class MappingService:
    """Mapping state machine (DESIGN-MAPPING.md section 4): idle, starting, mapping, saving, stopping, error.
    start, save and stop reply at once and finish in their own thread; a probe (every probe_period s) finds a SLAM that
    was started or stopped outside Studio. emit(dict) gets a `mapping` event on every change. Thread-safe."""

    def __init__(self, runner, probe, maps_dir, emit, disarm=None, probe_period=2.0, start_timeout=START_TIMEOUT_S,
                 save_timeout=SAVE_TIMEOUT_S, stop_timeout=STOP_TIMEOUT_S, seen_wait=15.0, gone_wait=10.0,
                 clock=time.time):
        self.runner, self.probe, self.maps_dir, self.emit, self.disarm = runner, probe, maps_dir, emit, disarm
        self.probe_period, self.clock = probe_period, clock
        self.start_timeout, self.save_timeout, self.stop_timeout = start_timeout, save_timeout, stop_timeout
        self.seen_wait, self.gone_wait = seen_wait, gone_wait
        self.lock = threading.Lock()
        self.state = "idle"
        self.since = clock()
        self.last_error = None
        self.last_saved = None
        self.unsaved = False
        self.other_stack = None
        self.saving_name = None
        self.gen = 0
        self._stop = threading.Event()
        self._probe_thread = None

    # ---- state
    def _info(self):
        return {"state": self.state, "since": round(self.since, 3), "last_error": self.last_error,
                "last_saved": self.last_saved, "unsaved": self.unsaved, "scripts_ok": bool(self.runner.scripts_ok()),
                "other_stack": self.other_stack, "maps_dir": self.maps_dir}

    def status(self):
        with self.lock:
            return self._info()

    def busy_name(self):
        """Name of the map that is being saved right now, or None."""
        with self.lock:
            return self.saving_name if self.state == "saving" else None

    def _emit(self, result=None):
        ev = dict(self._info(), ev="mapping")
        if result is not None:
            ev["result"] = result
        try:
            self.emit(ev)
        except Exception as e:
            log("mapping emit:", repr(e))

    def _go(self, state, result=None, **fields):
        """Enter a state (lock held), set fields, emit one event."""
        self.state = state
        self.since = self.clock()
        self.gen += 1
        for k, v in fields.items():
            setattr(self, k, v)
        self._emit(result)

    def _disarm(self, why):
        if self.disarm:
            try:
                self.disarm(why)
            except Exception as e:
                log("mapping disarm:", repr(e))

    def _script(self, script, args, timeout):
        try:
            return self.runner.run(script, args, timeout)
        except Exception as e:
            return False, "%s failed: %s: %s" % (script, type(e).__name__, e)

    def _wait_for(self, cond, secs):
        end = time.monotonic() + secs
        while True:
            if cond():
                return True
            if time.monotonic() >= end or self._stop.wait(min(0.2, max(0.01, secs / 5.0))):
                return bool(cond())

    # ---- probe
    def probe_once(self):
        """Look at the processes once: adopts a SLAM started outside Studio, reports one that vanished."""
        with self.lock:
            g = self.gen
        slam, other = detect_stack(self.probe.running)
        with self.lock:
            changed = other != self.other_stack
            self.other_stack = other
            if self.gen == g:
                if self.state == "idle" and slam:
                    self._go("mapping", unsaved=True, last_error=None)
                    return
                if self.state == "mapping" and not slam:
                    self._go("error", last_error="The mapping process is no longer running. It stopped or crashed; "
                                                 "the unsaved map is lost.")
                    return
            if changed:
                self._emit()

    def start_probe(self):
        self.probe_once()

        def loop():
            while not self._stop.wait(self.probe_period):
                try:
                    self.probe_once()
                except Exception as e:
                    log("mapping probe:", repr(e))
        self._probe_thread = threading.Thread(target=loop, name="mapprobe", daemon=True)
        self._probe_thread.start()

    def close(self):
        """Stop the probe thread. A running SLAM is left alone (mapping survives a Studio disconnect)."""
        self._stop.set()

    # ---- commands
    def start(self, keep_camera=False):
        self.probe_once()
        with self.lock:
            if self.state != "idle":
                raise ServiceError({"mapping": "Mapping is already running.", "error": "Mapping is in an error state. "
                                    "Reset it or stop it first."}.get(self.state, "Mapping is busy (%s). Wait until it "
                                                                                  "is done." % self.state))
            if self.other_stack:
                raise ServiceError("A navigation stack is running (%s). Stop it first." % self.other_stack,
                                   other_stack=self.other_stack)
            if not self.runner.scripts_ok():
                miss = ", ".join(self.runner.missing_scripts()) or "delivery scripts"
                raise ServiceError("The delivery scripts are missing on the robot (%s). Deploy them first." % miss,
                                   scripts_missing=True)
            self._go("starting", last_error=None)
            info = self._info()
        self._disarm("mapping is starting")
        threading.Thread(target=self._run_start, args=(bool(keep_camera),), name="mapstart", daemon=True).start()
        return info

    def _run_start(self, keep_camera):
        ok, out = self._script("start_stack.sh", ["map"] + (["--keep-camera"] if keep_camera else []), self.start_timeout)
        tail = tail_lines(out)
        err = None
        if ok:
            ok = self._wait_for(lambda: self.probe.running(SLAM_PATTERN), self.seen_wait)
            if not ok:
                err = "The start script finished but the SLAM process is not running."
        else:
            err = (tail[-1] if tail else "start_stack.sh failed")
        with self.lock:
            if ok:
                self._go("mapping", {"op": "start", "ok": True, "output_tail": tail}, unsaved=True, last_error=None)
            else:
                self._go("error", {"op": "start", "ok": False, "error": err, "output_tail": tail}, last_error=err)

    def save(self, name, overwrite=False):
        if not valid_map_name(name):
            raise ServiceError("Bad map name. Use 1 to 48 letters, digits, _ or -, starting with a letter or digit.")
        prefix = os.path.join(self.maps_dir, name)
        with self.lock:
            if self.state != "mapping":
                raise ServiceError("Saving needs a running mapping session (state: %s)." % self.state)
            if os.path.exists(prefix + ".yaml") and not overwrite:
                raise ServiceError("A map named %s already exists." % name, exists=True)
            self._go("saving", saving_name=name)
            info = self._info()
        self._disarm("mapping is saving")
        threading.Thread(target=self._run_save, args=(name, prefix, bool(overwrite)), name="mapsave", daemon=True).start()
        return info

    def _run_save(self, name, prefix, overwrite):
        ok, out = self._script("save_map.sh", [prefix] + (["--force"] if overwrite else []), self.save_timeout)
        tail = tail_lines(out)
        if ok and not os.path.isfile(prefix + ".yaml"):
            ok = False
            tail.append("the script finished but %s.yaml was not written" % name)
        with self.lock:
            if ok:
                self._go("mapping", {"op": "save", "ok": True, "name": name, "output_tail": tail},
                         last_saved={"name": name, "t": round(self.clock(), 3)}, unsaved=False, last_error=None,
                         saving_name=None)
            else:
                err = tail[-1] if tail else "save_map.sh failed"
                self._go("mapping", {"op": "save", "ok": False, "name": name, "error": err, "output_tail": tail},
                         last_error=err, saving_name=None)

    def stop(self):
        with self.lock:
            if self.state not in ("mapping", "error"):
                raise ServiceError("Mapping cannot be stopped now (state: %s)." % self.state)
            self._go("stopping")
            info = self._info()
        self._disarm("mapping is stopping")
        threading.Thread(target=self._run_stop, name="mapstop", daemon=True).start()
        return info

    def _run_stop(self):
        ok, out = self._script("stop_stack.sh", [], self.stop_timeout)
        tail = tail_lines(out)
        gone = self._wait_for(lambda: not self.probe.running(SLAM_PATTERN), self.gone_wait)
        with self.lock:
            if ok and gone:
                self._go("idle", {"op": "stop", "ok": True, "output_tail": tail}, unsaved=False, last_error=None)
            else:
                err = "The mapping process is still running after the stop script." if ok else \
                    (tail[-1] if tail else "stop_stack.sh failed")
                self._go("error", {"op": "stop", "ok": False, "error": err, "output_tail": tail}, last_error=err)

    def reset(self):
        """Leave the error state: idle or mapping again, from the processes."""
        slam = bool(self.probe.running(SLAM_PATTERN))
        with self.lock:
            if self.state == "error":
                self._go("mapping" if slam else "idle", last_error=None, unsaved=slam)
            return self._info()


class MapLibrary:
    """The maps folder: <name>.pgm, .yaml, .posegraph, .data. Every path is checked to stay inside the folder."""

    def __init__(self, maps_dir, busy=None):
        self.dir = maps_dir
        self.busy = busy or (lambda: None)

    def _path(self, name, ext=""):
        if not valid_map_name(name):
            raise ServiceError("Bad map name. Use 1 to 48 letters, digits, _ or -, starting with a letter or digit.")
        p = safe_join(self.dir, name + ext)
        if p is None or os.path.dirname(p) != os.path.realpath(self.dir):
            raise ServiceError("The path is outside the maps folder.")
        return p

    def names(self):
        try:
            files = os.listdir(self.dir)
        except OSError:
            return []
        return sorted(f[:-5] for f in files if f.endswith(".yaml") and valid_map_name(f[:-5]))

    def _image_path(self, name, meta):
        """The PGM of a map: the image: line of its YAML when that stays inside the folder, else <name>.pgm."""
        img = (meta or {}).get("image")
        if img and not os.path.isabs(img):
            p = safe_join(self.dir, img)
            if p and os.path.isfile(p):
                return p
        return self._path(name, ".pgm")

    def _meta(self, name):
        try:
            with open(self._path(name, ".yaml"), "r", encoding="utf-8", errors="replace") as f:
                return parse_map_yaml(f.read())
        except (OSError, ValueError):
            return None

    def entry(self, name):
        files, mtime, total = {}, 0.0, 0
        for ext in MAP_EXTS:
            try:
                st = os.stat(self._path(name, ext))
                files[ext[1:]] = st.st_size
                mtime, total = max(mtime, st.st_mtime), total + st.st_size
            except OSError:
                files[ext[1:]] = None
        meta = self._meta(name)
        w = h = None
        try:
            with open(self._image_path(name, meta), "rb") as f:
                _, w, h, _, _ = pgm_header(f.read(512))
        except (OSError, ValueError):
            pass
        return {"name": name, "width": w, "height": h, "resolution": meta["resolution"] if meta else None,
                "origin": meta["origin"] if meta else None, "mtime": round(mtime, 3), "bytes": total, "files": files}

    def list(self):
        out = [self.entry(n) for n in self.names()]
        out.sort(key=lambda e: (-e["mtime"], e["name"]))
        return out

    def preview(self, name, max_px=512):
        if not os.path.isfile(self._path(name, ".yaml")):
            raise ServiceError("There is no map named %s." % name)
        try:
            with open(self._image_path(name, self._meta(name)), "rb") as f:
                w, h, pix = read_pgm(f.read())
        except OSError:
            raise ServiceError("The map %s has no image file." % name)
        except ValueError as e:
            raise ServiceError("The map image cannot be read: %s" % e)
        stride = max(1, -(-max(w, h) // max(1, int(max_px))))
        sw, sh, raw = sample_grid(w, h, pix, stride)
        return {"width": sw, "height": sh, "stride": stride, "encoding": "gray", "data": pack_cells(raw)}

    def rename(self, name, new_name):
        src = self._path(name, ".yaml")
        if not os.path.isfile(src):
            raise ServiceError("There is no map named %s." % name)
        if not valid_map_name(new_name):
            raise ServiceError("Bad new map name. Use 1 to 48 letters, digits, _ or -, starting with a letter or digit.")
        if name == new_name:
            raise ServiceError("The new name is the same as the old one.")
        if self.busy() == name:
            raise ServiceError("The map %s is being saved right now." % name)
        if any(os.path.lexists(self._path(new_name, ext)) for ext in MAP_EXTS):
            raise ServiceError("A map named %s already exists." % new_name, exists=True)
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            raise ServiceError("Cannot read the map YAML: %s" % e)
        moved = []
        try:
            for ext in MAP_EXTS:
                a = self._path(name, ext)
                if os.path.isfile(a):
                    b = self._path(new_name, ext)
                    os.rename(a, b)
                    moved.append((a, b))
            ydst = self._path(new_name, ".yaml")
            tmp = ydst + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(rewrite_yaml_image(text, new_name + ".pgm"))
            os.replace(tmp, ydst)
        except OSError as e:
            for a, b in reversed(moved):
                try:
                    os.rename(b, a)
                except OSError:
                    pass
            raise ServiceError("Rename failed: %s" % e)
        return {"name": new_name}

    def delete(self, name, confirm=False):
        if confirm is not True:
            raise ServiceError("Deleting a map needs confirm: true.")
        if not os.path.isfile(self._path(name, ".yaml")):
            raise ServiceError("There is no map named %s." % name)
        if self.busy() == name:
            raise ServiceError("The map %s is being saved right now." % name)
        deleted = []
        for ext in MAP_EXTS:
            p = self._path(name, ext)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError as e:
                    raise ServiceError("Cannot delete %s%s: %s" % (name, ext, e), deleted=deleted)
                deleted.append(name + ext)
        return {"deleted": deleted}

    def seed_demo(self, name="demo_room"):
        """Fake robot: when the folder has no map, save a fully revealed fake room so the library is not empty."""
        if self.names():
            return False
        g = FakeMapGrid()
        g.reveal_all()
        g.save(os.path.join(self.dir, name))
        return True


class Bridge:
    def __init__(self, ros, writer, home, fake):
        self.ros, self.writer, self.home, self.fake = ros, writer, home, fake
        self.stop = threading.Event()
        self.runs = collections.OrderedDict()
        self.runs_lock = threading.Lock()
        self.run_counter = 0
        self.watches = {}
        self.watch_counter = 0
        self.watch_lock = threading.Lock()
        self.status_period = None
        self.status_wake = threading.Event()
        self.estop_on = None
        self.estop_app = False
        self.estop_t = 0.0
        self.slow = {"net": {}, "clock_synced": None, "ros_service": "unknown", "throttled": None}
        self.cpu_prev = None
        self.logdir = os.path.join(home, "robot_code", "logs")
        self.stop_file = os.path.join(home, "STOP")
        self.t0 = time.monotonic()
        self.secrets = WifiSecrets()
        self.fw_lock = threading.Lock()
        self.fw = fake_wifi_state()
        # Studio 2.0: manual driving + streams
        self.tele_lock = threading.Lock()
        self.tele = {"armed": False, "last_cmd": 0.0, "last_move": 0.0, "zeroed": True, "seq": -1,
                     "max_linear": TELEOP_MAX_LINEAR, "max_angular": TELEOP_MAX_ANGULAR, "armed_t": 0.0}
        self.status_estop = None            # estop.on of the newest status (None = unknown)
        self.streams = {"scan": None, "pose": None, "map": None}      # name -> {"period", "next", "max_points", "last_seq"} while on
        self.stream_lock = threading.Lock()
        self.map_seq = 0
        # Studio 2.1: mapping (the delivery scripts, or timers in fake mode) and the map library
        self.maps_dir = os.path.join(home, "robot_code", "maps")
        if fake:
            self.runner = FakeStackRunner(ros)
            self.probe = FakeProcessProbe(self.runner)
        else:
            self.runner = RealStackRunner(home)
            self.probe = RealProcessProbe()
        self.mapping = MappingService(self.runner, self.probe, self.maps_dir, self.emit,
                                      disarm=lambda why: self.teleop_disarm(why))
        self.maps = MapLibrary(self.maps_dir, self.mapping.busy_name)
        if fake:
            try:
                self.maps.seed_demo()
            except OSError as e:
                log("cannot seed the sample map:", e)

    # ---- infrastructure
    def emit(self, obj, droppable=False):
        self.writer.emit(obj, droppable)

    def start_threads(self):
        try:
            os.makedirs(self.logdir, exist_ok=True)
        except OSError as e:
            log("cannot create", self.logdir, e)
        self.rediscover()
        self.mapping.start_probe()
        for fn, name in ((self._status_loop, "status"), (self._slow_loop, "slow"), (self._run_monitor, "runmon"),
                         (self._teleop_loop, "teleop"), (self._stream_loop, "streams")):
            threading.Thread(target=fn, name=name, daemon=True).start()

    def reply(self, cid, ok, **kw):
        d = {"ev": "reply", "id": cid, "ok": bool(ok)}
        d.update(kw)
        self.emit(d)

    def handle(self, cmd):
        """Run one command (called in its own thread so a slow command never blocks e-stop)."""
        cid = cmd.get("id")
        name = str(cmd.get("cmd", ""))
        fn = getattr(self, "h_" + name, None) if re.fullmatch(r"[a-z_]+", name) else None
        if fn is None:
            self.reply(cid, False, error="unknown command: %s" % name[:40])
            return
        try:
            res = fn(cmd) or {}
            self.reply(cid, True, **res)
        except BridgeError as e:
            extra = dict(e.extra)
            self.reply(cid, False, error=str(e), **extra)
        except RosError as e:
            self.reply(cid, False, error=str(e))
        except Exception as e:
            log("command", name, "failed:", repr(e))
            self.reply(cid, False, error="internal error: %s: %s" % (type(e).__name__, e))

    def need_ros(self):
        if not self.ros.available:
            raise BridgeError("ROS not available: %s" % (self.ros.error or "not started"))

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

    # ---- v1.1: path safety, files, describe, wifi
    def resolve_dir(self, d):
        """Directory argument -> real absolute path inside the home directory (not in ~/.ssh), else BridgeError."""
        p = expand_home(d, self.home, "~/robot_code")
        if "\0" in p:
            raise BridgeError("bad directory")
        real = os.path.realpath(p)
        if not home_path_ok(real, self.home):
            raise BridgeError("directory must be inside your home directory (and not ~/.ssh)")
        return real

    def resolve_file(self, d, rel):
        """(dir, real file path) for a relative name; refuses bad names, '..', and symlinks leaving home."""
        base = self.resolve_dir(d)
        if not valid_rel(rel):
            raise BridgeError("bad file name (allowed: letters, digits, _ . - and / for subfolders, max 120 characters)")
        full = os.path.realpath(os.path.join(base, rel))
        if not inside_root(full, base) or not home_path_ok(full, self.home):
            raise BridgeError("path leaves the directory or the home directory")
        return base, full

    def h_describe(self, c):
        base = self.resolve_dir(c.get("dir"))
        out = []
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                if not name.lower().endswith((".py", ".sh")) or not valid_rel(name):
                    continue
                full = os.path.realpath(os.path.join(base, name))
                if not os.path.isfile(full) or not home_path_ok(full, self.home):
                    continue
                e = describe_file(full)
                if e:
                    e["name"] = name
                    out.append(e)
        return {"dir": base, "programs": out}

    def h_read_file(self, c):
        base, full = self.resolve_file(c.get("dir"), c.get("path"))
        if not os.path.isfile(full):
            raise BridgeError("no such file: %s" % c.get("path"))
        size = os.path.getsize(full)
        if size > MAX_TEXT_BYTES:
            raise BridgeError("file is larger than 512 KB")
        with open(full, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise BridgeError("not a UTF-8 text file")
        if "\0" in text:
            raise BridgeError("not a text file")
        return {"path": c.get("path"), "text": text, "size": size, "mtime": round(os.path.getmtime(full), 1),
                "sha1": hashlib.sha1(raw).hexdigest()}

    def h_write_file(self, c):
        base, full = self.resolve_file(c.get("dir"), c.get("path"))
        text = c.get("text")
        if not isinstance(text, str):
            raise BridgeError("text must be a string")
        raw = text.encode("utf-8")
        if len(raw) > MAX_TEXT_BYTES:
            raise BridgeError("text is larger than 512 KB")
        exists = os.path.lexists(full)
        if exists and os.path.isdir(full):
            raise BridgeError("a folder with that name exists")
        if exists and not c.get("overwrite"):
            raise BridgeError("file exists (set overwrite)")
        old = None
        if exists:
            with open(full, "rb") as f:
                old = f.read()
            exp = c.get("expect_sha1")
            if exp and hashlib.sha1(old).hexdigest() != exp:
                raise BridgeError("changed on the robot since you opened it")
        if old is not None and old == raw:  # same content: no rewrite and no .bak (it would replace the older backup)
            return {"path": c.get("path"), "size": len(raw), "sha1": hashlib.sha1(raw).hexdigest(), "backup": None,
                    "unchanged": True}
        parent = os.path.dirname(full)
        os.makedirs(parent, exist_ok=True)
        mode = 0o755 if full.lower().endswith((".py", ".sh")) else 0o644
        backup = None
        if old is not None:
            backup = full + ".bak"
            with open(backup, "wb") as f:
                f.write(old)
        fd, tmp = tempfile.mkstemp(prefix=".studio_", dir=parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, full)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise BridgeError("cannot write: %s" % e)
        return {"path": c.get("path"), "size": len(raw), "sha1": hashlib.sha1(raw).hexdigest(), "backup": backup}

    def h_wifi_info(self, c):
        if self.fake:
            return self.fake_wifi_info()
        return collect_wifi()

    def h_wifi_secret_put(self, c):
        """Studio hands over a Wi-Fi password once; the on-robot script fetches it from here (abstract unix socket)."""
        if not self.fake and not sys.platform.startswith("linux"):
            raise BridgeError("the Wi-Fi password handoff needs the Linux robot (abstract unix sockets)")
        try:
            ttl = self.secrets.put(c.get("nonce"), c.get("psk"), c.get("ttl", 180), serve=not self.fake)
        except ValueError as e:
            raise BridgeError(str(e))
        except OSError as e:
            raise BridgeError("cannot open the local socket (%s)" % type(e).__name__)
        except Exception as e:  # never let an exception text travel: it could quote the password
            raise BridgeError("internal error (%s)" % type(e).__name__)
        return {"state": "waiting", "ttl": ttl}

    def h_wifi_secret_drop(self, c):
        self.secrets.drop(c.get("nonce"))
        return {}

    def h_wifi_join_status(self, c):
        nonce = c.get("nonce")
        if nonce is not None and not (isinstance(nonce, str) and NONCE_RE.fullmatch(nonce)):
            raise BridgeError("bad nonce")
        with self.fw_lock:
            join = dict(self.fw["join"]) if self.fake and self.fw["join"] else None
        if not self.fake:
            join = read_join_status()
        return {"secret": self.secrets.state(nonce) if nonce else "none", "join": join}

    # ---- fake Wi-Fi (demo and tests): the robot sits on HomeNet; wifi_fake_add simulates fetch, save and join
    def fake_net(self):
        with self.fw_lock:
            ap = self.fw["cur"] == FAKE_HOTSPOT
            ps = next((x["powersave"] for x in self.fw["saved"] if x["name"] == self.fw["cur"]), "default")
            return {"wifi_mode": "ap" if ap else "client", "ssid": self.fw["cur"], "signal_dbm": None if ap else -55.0,
                    "link_quality": None if ap else 70,
                    "addresses": {"eth0": "192.168.185.3", "wlan0": self.fw["ip"], "usb0": "192.168.186.3"},
                    "wlan0_ip": self.fw["ip"], "powersave": ps, "powersave_students": ps}

    def fake_wifi_info(self):
        with self.fw_lock:
            cur, ip = self.fw["cur"], self.fw["ip"]
            saved = [dict(x, active=(x["name"] == cur)) for x in self.fw["saved"]]
            ap = cur == FAKE_HOTSPOT
            ps = next((x["powersave"] for x in saved if x["name"] == cur), "default")
            wlan = {"state": "connected", "connection": cur, "mode": "ap" if ap else "infrastructure", "ssid": cur, "ip": ip,
                    "signal_dbm": None if ap else -55.0, "powersave": ps}
        res = {"fake": True, "wlan0": wlan, "saved": saved, "scan": []}
        if ap:
            res["scan_note"] = "the robot cannot scan while it runs its hotspot"
        else:
            res["scan"] = [{"ssid": n, "signal": sig, "security": sec, "chan": ch} for n, sec, sig, ch in
                           sorted(FAKE_SCAN, key=lambda x: -x[2])]
        return res

    def h_fake_battery(self, c):
        """Fake robot only (tests): fix the battery percent, or null to go back to the slowly draining value."""
        if not self.fake:
            raise BridgeError("only available in fake mode")
        v = c.get("percent")
        if v is None:
            self.ros.battery_override = None
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
            raise BridgeError("percent must be 0 to 100 or null")
        else:
            self.ros.battery_override = float(v)
        return {"percent": self.ros.battery_override}

    def h_wifi_fake_add(self, c):
        if not self.fake:
            raise BridgeError("only available in fake mode")
        nonce, ssid = c.get("nonce"), c.get("ssid")
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise BridgeError("bad nonce")
        if not isinstance(ssid, str) or not ssid or len(ssid.encode("utf-8")) > 32:
            raise BridgeError("bad ssid")
        threading.Thread(target=self._fake_wifi_job, args=(nonce, ssid, bool(c.get("connect_now"))), name="fakewifi",
                         daemon=True).start()
        return {"simulated": True}

    def _fake_wifi_job(self, nonce, ssid, connect_now):
        scale = FAKE_WIFI_SCALE
        time.sleep(1.0 * scale)  # the "terminal" asks the bridge for the password
        psk = self.secrets.take(nonce)
        if psk is None:
            return
        with self.fw_lock:
            prev = self.fw["cur"]
            if not any(x["name"] == ssid for x in self.fw["saved"]):
                self.fw["saved"].append({"name": ssid, "ssid": ssid, "mode": "infrastructure", "autoconnect": True,
                                         "priority": 10, "powersave": "disable"})
            if connect_now:
                self.fw["join"] = {"state": "joining", "ssid": ssid, "prev": prev, "t": int(time.time())}
        if not connect_now:
            return
        time.sleep(2.0 * scale)
        with self.fw_lock:
            if ssid == "FailNet" or psk == "wrongpass1":
                self.fw["saved"] = [x for x in self.fw["saved"] if x["name"] != ssid]
                self.fw["join"] = {"state": "failed", "ssid": ssid, "reason": "could not join (wrong password or out of range)",
                                   "fallback": prev, "fallback_ok": True, "removed": True, "t": int(time.time())}
            else:
                self.fw["n"] += 1
                self.fw["cur"], self.fw["ip"] = ssid, "192.168.50.%d" % (20 + self.fw["n"])
                self.fw["join"] = {"state": "joined", "ssid": ssid, "ip": self.fw["ip"], "prev": prev, "t": int(time.time())}
        self.slow = dict(self.slow, net=self.fake_net())

    # ---- runs
    def _unique_log(self, name):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        base = "%s_%s" % (stamp, re.sub(r"[^A-Za-z0-9_.-]", "_", name))
        path, i = os.path.join(self.logdir, base + ".log"), 1
        while os.path.exists(path):
            i += 1
            path = os.path.join(self.logdir, "%s_%d.log" % (base, i))
        return path

    def h_run(self, c):
        rel = str(c.get("path", ""))
        args = c.get("args") or []
        if not isinstance(args, list) or any((not isinstance(a, str)) or "\0" in a for a in args):
            raise BridgeError("args must be a list of strings")
        motion = bool(c.get("motion"))
        if motion and not c.get("confirmed"):
            raise BridgeError("motion needs confirmation")
        if motion and os.path.exists(self.stop_file):
            raise BridgeError("e-stop/STOP file present: release first")
        d, full = self.resolve_file(c.get("dir"), rel)
        if not os.path.isfile(full):
            raise BridgeError("file not found in %s: %s" % (d, rel))
        ext = os.path.splitext(full)[1].lower()
        if ext == ".py":
            argv = [sys.executable or "python3", "-u", full]
        elif ext == ".sh":
            argv = [shutil.which("bash") or "bash", full]
        else:
            raise BridgeError("only .py and .sh files can be run")
        os.makedirs(self.logdir, exist_ok=True)
        name = os.path.basename(full)
        log_path = self._unique_log(name)
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        kw = {}
        if os.name == "posix":
            kw["start_new_session"] = True
        else:
            kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        with open(log_path, "ab") as lf:
            try:
                proc = subprocess.Popen(argv + args, cwd=os.path.dirname(full), env=env, stdin=subprocess.DEVNULL,
                                        stdout=lf, stderr=subprocess.STDOUT, **kw)
            except OSError as e:
                raise BridgeError("cannot start: %s" % e)
        run_id = os.path.basename(log_path)[:-4]
        run = Run(run_id, name, proc.pid, log_path, full, time.time(), motion, proc)
        try:
            with open(log_path + ".pid", "w") as f:
                json.dump({"run_id": run_id, "pid": proc.pid, "name": name, "path": full, "motion": motion,
                           "started_wall": run.started_wall, "args": args}, f)
        except OSError as e:
            log("pid file:", e)
        with self.runs_lock:
            self.runs[run_id] = run
        return {"run_id": run_id, "pid": proc.pid, "log": log_path}

    def rediscover(self):
        try:
            names = [n for n in os.listdir(self.logdir) if n.endswith(".log.pid")]
        except OSError:
            return
        names.sort(key=lambda n: os.path.getmtime(os.path.join(self.logdir, n)), reverse=True)
        for n in names[:20]:
            try:
                with open(os.path.join(self.logdir, n)) as f:
                    j = json.load(f)
                run_id = str(j["run_id"])
                if run_id in self.runs:
                    continue
                lp = os.path.join(self.logdir, n[:-4])
                r = Run(run_id, j.get("name", run_id), int(j["pid"]), lp, j.get("path", j.get("name", "")),
                        j.get("started_wall"), j.get("motion"))
                try:
                    r.offset = os.path.getsize(lp)
                except OSError:
                    pass
                r.exit_sent = True          # no history re-emit; set back below if still alive
                if self.run_alive(r):
                    r.exit_sent = False
                with self.runs_lock:
                    self.runs[run_id] = r
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def run_alive(self, r):
        if r.proc is not None:
            return r.proc.poll() is None
        return pid_alive(r.pid, r.needle)

    def h_runs(self, c):
        self.rediscover()
        with self.runs_lock:
            return {"runs": [r.info(self.run_alive(r)) for r in self.runs.values()]}

    def _signal_run(self, r, sig):
        try:
            if os.name == "posix":
                s = getattr(signal, sig)
                try:
                    pg = os.getpgid(r.pid)
                except OSError:
                    return
                if pg == r.pid:
                    os.killpg(pg, s)
                else:
                    os.kill(r.pid, s)
            elif r.proc is not None:
                if sig == "SIGINT":
                    r.proc.send_signal(signal.CTRL_BREAK_EVENT)
                elif sig == "SIGTERM":
                    r.proc.terminate()
                else:
                    r.proc.kill()
        except (OSError, ValueError) as e:
            log("signal", sig, r.run_id, e)

    def stop_run(self, r, waits=(3.0, 2.0, 2.0)):
        """SIGINT to the process group, wait 3 s, SIGTERM, wait 2 s, SIGKILL."""
        if not self.run_alive(r):
            return "already_exited"
        for sig, wait in zip(("SIGINT", "SIGTERM", "SIGKILL"), waits):
            self._signal_run(r, sig)
            end = time.monotonic() + wait
            while time.monotonic() < end:
                if not self.run_alive(r):
                    return sig
                time.sleep(0.05)
        return "SIGKILL" if not self.run_alive(r) else "SIGKILL_failed"

    def stop_many(self, runs):
        how, threads = {}, []
        for r in runs:
            t = threading.Thread(target=lambda r=r: how.__setitem__(r.run_id, self.stop_run(r)), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(8.0)
        return how

    def h_stop(self, c):
        rid = c.get("run_id")
        with self.runs_lock:
            if rid == "all":
                targets = [r for r in self.runs.values() if self.run_alive(r)]
            elif rid in self.runs:
                targets = [self.runs[rid]]
            else:
                raise BridgeError("no such run: %s" % rid)
        how = self.stop_many(targets)
        return {"stopped": list(how), "how": how}

    def _run_monitor(self):
        while not self.stop.is_set():
            with self.runs_lock:
                active = [r for r in self.runs.values() if not r.exit_sent]
            for r in active:
                try:
                    self._pump(r)
                except Exception as e:
                    log("run monitor:", repr(e))
            self.stop.wait(0.3 if active else 1.0)

    def _pump(self, r):
        alive = self.run_alive(r)
        data = b""
        try:
            with open(r.log, "rb") as f:
                f.seek(r.offset)
                data = f.read(256 * 1024)
                r.offset += len(data)
        except OSError:
            pass
        text = r.pending + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        r.pending = lines.pop()             # incomplete last line waits for its newline
        if not alive and not data:
            if r.pending:
                lines.append(r.pending)
                r.pending = ""
        for i in range(0, len(lines), 200):
            self.emit({"ev": "run_output", "run_id": r.run_id, "lines": [l.rstrip("\r") for l in lines[i:i + 200]]})
        if not alive and not data and not r.pending:
            r.code = r.proc.returncode if r.proc is not None else None
            r.exit_sent = True
            self.emit({"ev": "run_exit", "run_id": r.run_id, "code": r.code})

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
                                          md["cells"], v["max_cells"]))
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

    # ---- Studio 2.1: mapping and the map library (thin: check the arguments, call a service)
    @staticmethod
    def _svc(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except ServiceError as e:
            raise BridgeError(str(e), **e.extra)

    def h_mapping_status(self, c):
        return self.mapping.status()

    def h_mapping_start(self, c):
        kc = c.get("keep_camera", False)
        if not isinstance(kc, bool):
            raise BridgeError("keep_camera must be true or false")
        return self._svc(self.mapping.start, kc)

    def h_mapping_save(self, c):
        ow = c.get("overwrite", False)
        if not isinstance(ow, bool):
            raise BridgeError("overwrite must be true or false")
        return self._svc(self.mapping.save, c.get("name"), ow)

    def h_mapping_stop(self, c):
        return self._svc(self.mapping.stop)

    def h_mapping_reset(self, c):
        return self.mapping.reset()

    def h_maps_list(self, c):
        return {"maps": self.maps.list(), "dir": self.maps_dir}

    def h_map_preview(self, c):
        try:
            mp = clamp_int(c.get("max_px"), 64, 1024, 512)
        except ValueError:
            raise BridgeError("max_px must be a number")
        return self._svc(self.maps.preview, c.get("name"), mp)

    def h_map_rename(self, c):
        return self._svc(self.maps.rename, c.get("name"), c.get("new_name"))

    def h_map_delete(self, c):
        return self._svc(self.maps.delete, c.get("name"), c.get("confirm"))

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


class BridgeError(Exception):
    def __init__(self, msg, **extra):
        Exception.__init__(self, msg)
        self.extra = extra


MAPPING_BUSY_TEXT = {"starting": "Mapping is starting; driving is blocked until it is ready.",
                     "saving": "Mapping is saving the map; driving is blocked until it is done.",
                     "stopping": "Mapping is stopping; driving is blocked until it is done."}


# ======================================================================= main
def hello(ros, fake, home):
    return {"ev": "hello", "version": VERSION, "bridge": "robot_bridge", "hostname": "fake-turtlebot4" if fake else socket.gethostname(),
            "ros": bool(ros.available) and not fake, "ros_distro": os.environ.get("ROS_DISTRO"),
            "rmw": os.environ.get("RMW_IMPLEMENTATION"), "domain": os.environ.get("ROS_DOMAIN_ID", "0"),
            "python": sys.version.split()[0], "pid": os.getpid(), "fake": bool(fake), "home": home,
            "ros_error": ros.error}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TurtleBot Studio robot bridge")
    ap.add_argument("--fake", action="store_true", help="no ROS, simulated data")
    ns, _ = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
    fake = ns.fake or os.environ.get("STUDIO_BRIDGE_FAKE", "") not in ("", "0")
    home = os.environ.get("STUDIO_BRIDGE_HOME") or (tempfile.mkdtemp(prefix="studio_fake_") if fake else os.path.expanduser("~"))
    stdin = sys.stdin.buffer
    stop = threading.Event()
    writer = Writer(sys.stdout.buffer, on_broken=stop.set)
    ros = FakeRos() if fake else RosReal()
    bridge = Bridge(ros, writer, home, fake)
    bridge.stop = stop
    for s in ("SIGTERM", "SIGINT", "SIGHUP"):
        if hasattr(signal, s):
            try:
                signal.signal(getattr(signal, s), lambda *a: stop.set())
            except (ValueError, OSError):
                pass
    ros.start(writer.emit)
    writer.emit(hello(ros, fake, home))
    bridge.start_threads()

    def reader():
        try:
            while not stop.is_set():
                line = stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line.decode("utf-8", errors="replace"))
                    if not isinstance(cmd, dict):
                        raise ValueError("not an object")
                except ValueError as e:
                    log("bad command line:", e)
                    continue
                threading.Thread(target=bridge.handle, args=(cmd,), daemon=True, name="cmd").start()
        except Exception as e:
            log("reader stopped:", repr(e))
        stop.set()
    threading.Thread(target=reader, daemon=True, name="stdin").start()
    try:
        while not stop.wait(0.25):
            pass
    finally:
        # user programs started with "run" are detached and keep running; only our own threads stop
        bridge.status_period = None
        bridge.mapping.close()          # only the probe thread: a running SLAM keeps running (the next bridge finds it)
        try:
            bridge.teleop_disarm("bridge ended")
        except Exception:
            pass
        t = threading.Thread(target=ros.shutdown, daemon=True)
        t.start()
        t.join(1.0)
        writer.close(0.5)
        try:
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    main()
