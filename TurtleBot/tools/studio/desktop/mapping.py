"""Map storage and decoding: map names, route upload checks, PNG preview, MapStore.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip
from .wifi_scripts import *  # bundle: skip
from .laptop_network import *  # bundle: skip
from .programs import *  # bundle: skip
from .events import *  # bundle: skip
from .alerts import *  # bundle: skip


MAP_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$')
MAP_MAX_SIDE = 8192
MAP_MAX_CELLS = 16_000_000
MAP_META_KEYS = ('seq', 't', 'width', 'height', 'resolution', 'origin', 'stride')
MAP_FILE_EXTS = (('pgm', '.pgm'), ('yaml', '.yaml'), ('posegraph', '.posegraph'), ('data', '.data'))
MAP_REMOTE_DIR = '~/robot_code/maps'
MAP_UNKNOWN_GRAY = 205


def valid_map_name(name):
    """True for a map name the bridge accepts (same rule as robot_bridge.py)."""
    return isinstance(name, str) and bool(MAP_NAME_RE.fullmatch(name))  # fullmatch: '$' would accept a trailing newline


ROUTE_UPLOAD_MAX = 32 * 1024 * 1024
ROUTE_REQUIRED = ('route.yaml', 'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml')


def validate_route_upload(name, files):
    """(True, [(rel, bytes), ...]) for a route folder upload the robot may receive, else (False, error text)."""
    if not valid_map_name(name):
        return False, 'bad route name (letters, digits, - and _, at most 48 characters)'
    if name == 'current':
        return False, 'current is a reserved name'
    if not isinstance(files, list) or not files:
        return False, 'no files to upload'
    if len(files) > 64:
        return False, 'too many files (at most 64)'
    out, seen, total = [], set(), 0
    for f in files:
        if not isinstance(f, dict) or not isinstance(f.get('path'), str) or not isinstance(f.get('data_b64'), str):
            return False, 'each file needs a path and data_b64'
        rel = f['path']
        if (not rel or len(rel) > 100 or '/' in rel or '\\' in rel or '..' in rel or rel.startswith('.')
                or not rel.isprintable()):
            return False, 'bad file name: %r' % rel[:60]
        if rel in seen:
            return False, 'duplicate file: ' + rel
        seen.add(rel)
        try:
            data = base64.b64decode(f['data_b64'], validate=True)
        except (ValueError, TypeError):
            return False, 'bad base64 in ' + rel
        total += len(data)
        if total > ROUTE_UPLOAD_MAX:
            return False, 'upload too large (at most %d MB)' % (ROUTE_UPLOAD_MAX // (1024 * 1024))
        out.append((rel, data))
    missing = [r for r in ROUTE_REQUIRED if r not in seen]
    if missing:
        return False, 'missing: ' + ', '.join(missing)
    return True, out


def png_gray(width, height, pixels):
    """8-bit greyscale PNG (colour type 0, filter 0 on every row) of width x height pixel bytes, row 0 = top."""
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        raise ValueError('bad image size')
    if len(pixels) != width * height:
        raise ValueError('pixel count does not match the size')

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)

    raw = b''.join(b'\x00' + bytes(pixels[y * width:(y + 1) * width]) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def _gray_table():
    t = bytearray([MAP_UNKNOWN_GRAY]) * 256
    for v in range(101):
        t[v] = int(254 - v * 254 / 100 + 0.5)
    return bytes(t)


_GRAY_TABLE = _gray_table()


def cells_to_gray(data):
    """Occupancy bytes (0..100, 255 unknown) to grey: 0 -> 254, 100 -> 0, in between scaled, unknown (and 101..254) -> 205."""
    return bytes(data).translate(_GRAY_TABLE)


def flip_rows(width, height, data):
    """Reverse the row order (ROS row 0 = bottom of the map, image row 0 = top)."""
    if len(data) != width * height:
        raise ValueError('cell count does not match the size')
    return b''.join(bytes(data[y * width:(y + 1) * width]) for y in range(height - 1, -1, -1))


def decode_map_payload(ev):
    """(meta, grey bytes with the top row first) from a bridge `map` event ('cells') or a map_preview reply ('gray').

    Raises ValueError for a payload that is not what the contract says."""
    if not isinstance(ev, dict):
        raise ValueError('map payload is not an object')
    w, h = ev.get('width'), ev.get('height')
    if not (isinstance(w, int) and isinstance(h, int)) or isinstance(w, bool) or isinstance(h, bool):
        raise ValueError('map size is not a whole number')
    if not (0 < w <= MAP_MAX_SIDE and 0 < h <= MAP_MAX_SIDE and w * h <= MAP_MAX_CELLS):
        raise ValueError('map size out of range')
    enc = ev.get('encoding')
    if enc not in ('cells', 'gray'):
        raise ValueError('unknown map encoding: %r' % (enc,))
    try:
        comp = base64.b64decode(ev.get('data') or '', validate=True)
        d = zlib.decompressobj()
        raw = d.decompress(comp, w * h + 1)
    except (ValueError, TypeError, zlib.error):
        raise ValueError('map data is not zlib + base64')
    if len(raw) != w * h or d.unconsumed_tail:
        raise ValueError('map data length %d does not match %dx%d' % (len(raw), w, h))
    meta = {k: ev[k] for k in MAP_META_KEYS if k in ev}
    if enc == 'cells':
        return meta, cells_to_gray(flip_rows(w, h, raw))
    return meta, raw


class MapStore:
    """Thread-safe: the newest live map as a PNG with its metadata, and the last MappingInfo seen."""

    def __init__(self):
        self.lock = threading.Lock()
        self.png = None
        self.meta = None
        self.info = None

    def set_map(self, meta, png):
        with self.lock:
            self.png, self.meta = png, dict(meta)

    def get_map(self):
        """(png, meta) or None."""
        with self.lock:
            return None if self.png is None else (self.png, dict(self.meta))

    def set_info(self, info):
        """Remember a MappingInfo (a `mapping` event or the reply of a mapping_* command); only a dict with a state counts."""
        if not isinstance(info, dict) or not isinstance(info.get('state'), str):
            return
        clean = {k: v for k, v in info.items() if k not in ('ev', 'id', 'ok', 'result', 'error')}
        with self.lock:
            self.info = clean

    def get_info(self):
        with self.lock:
            return None if self.info is None else dict(self.info)

    def clear(self):
        with self.lock:
            self.png = self.meta = self.info = None
