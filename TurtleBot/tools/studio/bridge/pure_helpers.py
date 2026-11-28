"""Small pure functions: logging, JSON cleaning, battery flags, angle maths, the scan front-minimum.
No ROS, no files, no network. Tested offline."""
from .base import *  # bundle: skip


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
