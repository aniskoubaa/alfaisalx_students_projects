"""Pure helpers for maps and routes: map names, the map yaml and pgm files, the cell encoding sent to
the desktop, pose maths, and reading and writing the current-route file. No ROS."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip


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


ROUTE_REQUIRED = ("route.yaml", "map.yaml", "keepout_mask.yaml", "speed_mask.yaml")
ROUTE_MENU_PATTERN, ROUTE_MISSION_PATTERN = "delivery_menu.py", "delivery_mission.py"
ROUTE_STACK_PATTERNS = ("delivery_stack.launch.py", "localization.launch.py", "nav2.launch.py")
ROUTE_FAKE_CURRENT = ".current_fake"      # fake robot only: the target of `current` where symbolic links are not possible


def route_missing(files):
    """The required route files (ROUTE_REQUIRED order) that are not in `files` (an iterable of file names)."""
    have = set(files or ())
    return [f for f in ROUTE_REQUIRED if f not in have]


def count_waypoints(text):
    """{outbound:int, inbound:int}: the list items ("- {...}") under the top-level keys outbound: and inbound: of a
    route.yaml, by a plain line scan (no YAML parser on the robot side)."""
    counts = {"outbound": 0, "inbound": 0}
    section = None
    for raw in str(text or "").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace() and not raw.startswith("-"):
            m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", raw)
            section = m.group(1) if m and m.group(1) in counts else None
            continue
        if section and raw.lstrip().startswith("- {"):
            counts[section] += 1
    return counts


def _is_real_dir(path):
    return os.path.isdir(path) and not os.path.islink(path)


def read_current(routes_dir):
    """(name or None, ok): where routes/current points. ok means the target is an existing route folder. On a robot
    `current` is a symbolic link; the fake robot may keep the name in routes/.current_fake instead."""
    cur = os.path.join(routes_dir, "current")
    name = None
    if os.path.islink(cur):
        try:
            name = os.path.basename(os.readlink(cur).rstrip("/\\"))
        except OSError:
            name = None
    elif not os.path.exists(cur):
        txt = read_text(os.path.join(routes_dir, ROUTE_FAKE_CURRENT), 200)
        name = (txt or "").strip() or None
    if not name:
        return None, False
    return name, valid_map_name(name) and _is_real_dir(os.path.join(routes_dir, name))


def write_current(routes_dir, name, fake=False):
    """Make routes/current point to `name` (a folder name inside routes_dir, relative link). Real robot: a new link is
    made beside the old one and renamed over it (os.replace, atomic, the same effect as `ln -sfn`). Refuses (ValueError)
    when `current` is a real directory: it is never deleted. Fake robot where links are not possible: the name goes
    into routes/.current_fake."""
    cur = os.path.join(routes_dir, "current")
    if _is_real_dir(cur):
        raise ValueError("routes/current is a real folder, not a link; it was left as it is")
    fake_file = os.path.join(routes_dir, ROUTE_FAKE_CURRENT)
    tmp = os.path.join(routes_dir, ".current.tmp-%d" % os.getpid())
    try:
        if os.path.lexists(tmp):
            os.remove(tmp)
        os.symlink(name, tmp)
    except (OSError, NotImplementedError, AttributeError):
        if not fake:
            raise
        if os.path.islink(cur):
            os.remove(cur)
        with open(fake_file + ".tmp", "w", encoding="utf-8") as f:
            f.write(name + "\n")
        os.replace(fake_file + ".tmp", fake_file)
        return
    try:
        os.replace(tmp, cur)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if fake and os.path.exists(fake_file):
        try:
            os.remove(fake_file)
        except OSError:
            pass


def tail_text_lines(path, n=40, max_bytes=65536):
    """The last n lines of a text file (empty lines left out), each cut at 300 characters; [] when it cannot be read."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
    except OSError:
        return []
    lines = [ln.rstrip()[:300] for ln in data.decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-n:] if n > 0 else []
