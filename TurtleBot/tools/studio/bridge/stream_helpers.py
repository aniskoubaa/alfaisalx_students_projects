"""Pure helpers for the scan and pose streams, manual driving limits, the robot log (journal), the
parsers for /proc, nmcli and ip output, and the collectors that call them.
It does not talk to ROS or to the Bridge."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip


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
