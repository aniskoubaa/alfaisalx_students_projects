"""Path safety for the file browser, the program describer (first paragraph, docstring, usage) and the
Wi-Fi information collector. It never changes a file; it only reads and checks."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


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


RUN_COMMAND_RE = re.compile(r"^(?:python3?|bash)\s+\S+\.(?:py|sh)\b\s*(.*)$")


def extract_run_example(text, ext):
    """The arguments of the first command under "Run it on the robot:" in the docstring (or the leading # block), or ''.

    The templates write it as 'Run it on the robot:   python3 name.py --radius 0.3 --dry-run   (checks only)'. The
    command may also be on the next line. Any program name counts, because a copy keeps the template's name in its
    text. A note in brackets or after # is left out. Studio shows the result as the hint in the arguments box."""
    doc = None
    if ext == ".py":
        try:
            import ast
            doc = ast.get_docstring(ast.parse(text))
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            doc = None
    if not doc:
        doc = "\n".join(s.strip().lstrip("#").strip() for s in text.splitlines()[:60]
                        if s.strip().startswith("#") and not s.strip().startswith("#!"))
    lines = doc.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"run it on the robot\s*:(.*)$", line, re.I)
        if not m:
            continue
        for candidate in [m.group(1)] + lines[i + 1:i + 3]:
            command = re.sub(r"\s*\(.*\)\s*$", "", candidate.split("#")[0]).strip()
            if not command:
                continue
            found = RUN_COMMAND_RE.match(command)
            return found.group(1).strip() if found else ""
        return ""
    return ""


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
            "example": extract_run_example(text, ext),
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
