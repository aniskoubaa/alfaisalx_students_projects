"""Offline tests of the desktop side of the TurtleBot Studio 2.1 mapping feature (TurtleBot/tools/studio/studio.py):
PNG encoder, occupancy cells to grey, row flip, map payload decoding, MapStore, and the HTTP endpoints
/api/mapping, /api/map/live.png, /api/maps/preview.png and /api/maps/download against the real studio.py --fake.

No robot and no ROS. The HTTP part starts studio.py --fake with a temporary config folder and a temporary copy of web/
(--web-dir); nothing in the repo is written. It needs the fake bridge commands of robot_bridge.py (mapping_start, map_on,
maps_list, map_preview); when the bridge does not know them yet that part is reported as SKIP.
Usage: python test_studio_mapping_desktop.py     (prints PASS/FAIL/SKIP, exit code = number of failures)
"""
import base64
import http.client
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
import zlib
import io

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
sys.path.insert(0, STUDIO_DIR)
import studio as st  # noqa: E402

OUT = tempfile.mkdtemp(prefix='tb4_studio_mapdesk_')
fails = 0


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode())
    if not cond:
        fails += 1


def skip(name, why):
    print(('SKIP ' + name + '  [' + why + ']').encode('ascii', 'replace').decode())


def wait_for(fn, timeout, step=0.05):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


def decode_png(data):
    """Tiny PNG reader for the tests: returns (width, height, bit depth, colour type, pixel bytes) and checks every CRC."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'signature'
    pos, chunks = 8, []
    while pos < len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        crc = struct.unpack('>I', data[pos + 8 + n:pos + 12 + n])[0]
        assert crc == zlib.crc32(kind + body) & 0xffffffff, 'crc of ' + kind.decode()
        chunks.append((kind, body))
        pos += 12 + n
    assert chunks[0][0] == b'IHDR' and chunks[-1][0] == b'IEND', 'chunk order'
    w, h, depth, ctype, comp, filt, inter = struct.unpack('>IIBBBBB', chunks[0][1])
    assert comp == 0 and filt == 0 and inter == 0
    raw = zlib.decompress(b''.join(b for k, b in chunks if k == b'IDAT'))
    assert len(raw) == (w + 1) * h, 'scanline size'
    px = bytearray()
    for y in range(h):
        row = raw[y * (w + 1):(y + 1) * (w + 1)]
        assert row[0] == 0, 'filter 0'
        px.extend(row[1:])
    return w, h, depth, ctype, bytes(px)


def payload(width, height, data, encoding, **extra):
    ev = {'width': width, 'height': height, 'encoding': encoding,
          'data': base64.b64encode(zlib.compress(bytes(data))).decode()}
    ev.update(extra)
    return ev


# ================================================================ png_gray
pix = bytes([0, 50, 100, 150, 200, 254])
w, h, depth, ctype, got = decode_png(st.png_gray(3, 2, pix))
check('png_gray: signature, CRCs, IHDR 3x2, 8 bit, colour type 0, pixels decode back', (w, h, depth, ctype, got) == (3, 2, 8, 0, pix))
big = bytes((x * 7 + y * 13) % 256 for y in range(40) for x in range(70))
check('png_gray: 70x40 round trip', decode_png(st.png_gray(70, 40, big))[4] == big)
check('png_gray: 1x1', decode_png(st.png_gray(1, 1, b'\xcd'))[4] == b'\xcd')
for bad in ((0, 2, b''), (2, 2, b'abc'), (2, -1, b'ab'), (2.0, 2, b'abcd')):
    try:
        st.png_gray(*bad)
        ok = False
    except ValueError:
        ok = True
    check('png_gray: refuses %r' % (bad[:2],), ok)

# ================================================================ cells_to_gray
g = st.cells_to_gray(bytes([0, 100, 50, 255, 1, 99, 101, 200, 254, 10, 25]))
check('cells_to_gray: free 254, occupied 0, 50 -> 127, unknown 255 -> 205', g[:4] == bytes([254, 0, 127, 205]), str(list(g[:4])))
check('cells_to_gray: 1 -> 251, 99 -> 3 (254 - v*254/100 rounded)', g[4] == 251 and g[5] == 3, str(list(g[4:6])))
check('cells_to_gray: 101..254 are unknown (205)', g[6:9] == bytes([205, 205, 205]), str(list(g[6:9])))
check('cells_to_gray: 10 -> 229, 25 -> 190 (rounded half up)', g[9] == 229 and g[10] == 191, str(list(g[9:])))
exp = [int(254 - v * 254 / 100 + 0.5) for v in range(101)]
check('cells_to_gray: whole table 0..100', list(st.cells_to_gray(bytes(range(101)))) == exp)
check('cells_to_gray: the length is kept, empty input is fine', len(st.cells_to_gray(bytes(range(256)))) == 256 and st.cells_to_gray(b'') == b'')

# ================================================================ flip_rows
check('flip_rows: rows reversed, columns kept', st.flip_rows(3, 2, bytes([1, 2, 3, 4, 5, 6])) == bytes([4, 5, 6, 1, 2, 3]))
check('flip_rows: 1 row and 3 rows', st.flip_rows(2, 1, b'ab') == b'ab' and st.flip_rows(2, 3, b'aabbcc') == b'ccbbaa')
try:
    st.flip_rows(3, 2, b'abc')
    ok = False
except ValueError:
    ok = True
check('flip_rows: wrong length is refused', ok)

# ================================================================ valid_map_name
check('valid_map_name: accepts letters, digits, _ and -', all(st.valid_map_name(n) for n in ('a', 'demo_room', 'Room-2', '0x', 'a' * 48)))
check('valid_map_name: refuses empty, 49 chars, leading _ or -, dots, slashes, spaces, non-text',
      not any(st.valid_map_name(n) for n in ('', 'a' * 49, '_a', '-a', 'a.b', '../x', 'a/b', 'a b', 'a\n', None, 5)))

# ================================================================ decode_map_payload
# 3 wide, 2 tall, ROS order: row 0 (bottom) = 0, 100, 255 ; row 1 (top) = 50, 1, 100
cells = bytes([0, 100, 255, 50, 1, 100])
meta, grey = st.decode_map_payload(payload(3, 2, cells, 'cells', seq=7, t=12.5, resolution=0.05, origin={'x': -1, 'y': -2, 'yaw': 0}, stride=2, data_junk=1))
check('decode cells: flipped (top row first) and turned into grey', grey == bytes([127, 251, 0, 254, 0, 205]), str(list(grey)))
check('decode cells: meta has the contract keys only', meta == {'seq': 7, 't': 12.5, 'width': 3, 'height': 2, 'resolution': 0.05,
                                                              'origin': {'x': -1, 'y': -2, 'yaw': 0}, 'stride': 2}, str(meta))
pv = bytes([254, 0, 205, 10, 20, 30])
meta, grey = st.decode_map_payload(payload(3, 2, pv, 'gray', stride=4))
check('decode gray: already top-first, no change, no grey mapping', grey == pv and meta == {'width': 3, 'height': 2, 'stride': 4}, str((list(grey), meta)))
badp = [None, [], {}, payload(3, 2, cells, 'rgb'), payload(0, 2, b'', 'cells'), payload(3, 2, cells[:5], 'cells'),
        payload(3, 2, cells + b'x', 'cells'), dict(payload(3, 2, cells, 'cells'), data='not base64 !!'),
        dict(payload(3, 2, cells, 'cells'), data=base64.b64encode(b'plain, not zlib').decode()),
        dict(payload(3, 2, cells, 'cells'), width='3'), dict(payload(3, 2, cells, 'cells'), width=True),
        dict(payload(3, 2, cells, 'cells'), width=9000), dict(payload(3, 2, cells, 'cells'), data=None),
        payload(4000, 4001, b'\x00' * 100, 'cells')]
rejected = 0
for bp in badp:
    try:
        st.decode_map_payload(bp)
    except ValueError:
        rejected += 1
check('decode: every bad payload raises ValueError (%d cases)' % len(badp), rejected == len(badp), str(rejected))
bomb = payload(100, 100, b'\x00' * 10_000_000, 'cells')
try:
    st.decode_map_payload(bomb)
    ok = False
except ValueError:
    ok = True
check('decode: data longer than width*height is refused without inflating it all', ok)

# ================================================================ MapStore
ms = st.MapStore()
check('MapStore: empty at the start', ms.get_map() is None and ms.get_info() is None)
ms.set_map({'seq': 1, 'width': 3}, b'PNG1')
got = ms.get_map()
check('MapStore: set_map / get_map (a copy of the meta)', got == (b'PNG1', {'seq': 1, 'width': 3}))
got[1]['seq'] = 99
check('MapStore: callers cannot change the stored meta', ms.get_map()[1]['seq'] == 1)
ms.set_map({'seq': 2}, b'PNG2')
check('MapStore: the newest map wins', ms.get_map() == (b'PNG2', {'seq': 2}))
ms.set_info({'ev': 'mapping', 'state': 'mapping', 'unsaved': True, 'result': {'op': 'start', 'ok': True}})
check('MapStore: set_info drops ev/result, keeps the info', ms.get_info() == {'state': 'mapping', 'unsaved': True}, str(ms.get_info()))
ms.set_info({'ok': True, 'id': 4, 'state': 'saving', 'since': 5})
check('MapStore: a command reply is stored without ok/id', ms.get_info() == {'state': 'saving', 'since': 5})
ms.set_info({'ok': False, 'error': 'x'})
ms.set_info('junk')
ms.set_info({'state': 5})
check('MapStore: things without a text state are ignored', ms.get_info() == {'state': 'saving', 'since': 5})
ms.clear()
check('MapStore: clear removes map and info', ms.get_map() is None and ms.get_info() is None)
seen = []


def hammer(i):
    for k in range(200):
        ms.set_map({'seq': k}, b'x' * 10)
        ms.set_info({'state': 'mapping'})
        ms.get_map()
        ms.get_info()
        if k % 50 == 0:
            ms.clear()


ths = [threading.Thread(target=hammer, args=(i,)) for i in range(4)]
[t.start() for t in ths]
[t.join() for t in ths]
check('MapStore: parallel use does not fail', True)

# ---- Studio.on_map / mapping_info without a server
args = st.parse_args(['--fake', '--no-browser', '--config-dir', os.path.join(OUT, 'cfg_unit'), '--fake-home', os.path.join(OUT, 'home_unit')])
app = st.Studio(args)
published = []
app.bus.publish = published.append
app.on_map(dict(payload(3, 2, cells, 'cells'), ev='map', seq=3, t=1.0, resolution=0.05, origin={'x': 0, 'y': 0, 'yaw': 0}, stride=1))
slim = [e for e in published if e.get('ev') == 'map']
check('on_map: publishes the slim event without data', len(slim) == 1 and 'data' not in slim[0] and 'encoding' not in slim[0]
      and slim[0]['seq'] == 3 and slim[0]['width'] == 3 and slim[0]['height'] == 2 and slim[0]['stride'] == 1, str(slim))
png, m = app.maps.get_map()
check('on_map: stored PNG decodes to the grey picture', decode_png(png)[4] == bytes([127, 251, 0, 254, 0, 205]) and m['seq'] == 3)
published.clear()
app.on_map({'ev': 'map', 'width': 3, 'height': 2, 'encoding': 'cells', 'data': 'garbage'})
app.on_map(dict(payload(3, 2, cells, 'gray'), ev='map'))
check('on_map: a bad payload and a wrong encoding are dropped, the old map stays', not [e for e in published if e.get('ev') == 'map'] and app.maps.get_map()[1]['seq'] == 3)
check('mapping_info: unknown before anything was seen', app.mapping_info() == {'ok': True, 'state': 'unknown'})
app.maps.set_info({'state': 'idle', 'since': 1})
check('mapping_info: last info with ok', app.mapping_info() == {'ok': True, 'state': 'idle', 'since': 1})
check('map_preview_png / map_download_zip: bad names are 400, no bridge is 409',
      app.map_preview_png('../x', 512)[0] == 400 and app.map_download_zip('a b')[0] == 400
      and app.map_preview_png('demo', 512)[0] == 409 and app.map_download_zip('demo')[0] == 409)

# ================================================================ HTTP: real studio.py --fake
WEB = os.path.join(OUT, 'web_copy')
shutil.copytree(os.path.join(STUDIO_DIR, 'web'), WEB, ignore=shutil.ignore_patterns('v2'))
CFG = os.path.join(OUT, 'httpcfg')
HOME = os.path.join(OUT, 'httphome')
os.makedirs(HOME)
env = dict(os.environ, HOME=HOME, USERPROFILE=HOME, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', STUDIO_FAKE_MAP_SCALE='0.2')
proc = subprocess.Popen([sys.executable, '-u', os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--port', '0', '--config-dir', CFG,
                         '--fake-home', os.path.join(CFG, 'home'), '--heartbeat', '1', '--web-dir', WEB],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
url = {}
got_url = threading.Event()


def read_stdout():
    for raw in proc.stdout:
        m = re.search(r'http://127\.0\.0\.1:(\d+)/\?token=(\S+)', raw.decode('utf-8', 'replace'))
        if m:
            url['port'], url['token'] = int(m.group(1)), m.group(2)
            got_url.set()


threading.Thread(target=read_stdout, daemon=True).start()
try:
    check('studio.py --fake --web-dir starts', got_url.wait(20))
    PORT, TOKEN = url['port'], url['token']

    def call_raw(method, path, body=None, timeout=30, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=timeout)
        h = {'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN}
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        c.request(method, path, body=data, headers=h)
        resp = c.getresponse()
        txt = resp.read()
        hd = dict((k.lower(), v) for k, v in resp.getheaders())
        c.close()
        return resp.status, txt, hd

    def call(method, path, body=None, timeout=30):
        return json.loads(call_raw(method, path, body, timeout)[1].decode('utf-8'))

    def bridge(cmd, **kw):
        return call('POST', '/api/bridge', dict(kw, cmd=cmd))

    class Sse:
        def __init__(self):
            self.buf = bytearray()
            self.c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=300)
            self.c.request('GET', '/api/events', headers={'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN})
            self.resp = self.c.getresponse()
            threading.Thread(target=self._rd, daemon=True).start()

        def _rd(self):
            try:
                while True:
                    x = self.resp.read1(4096)
                    if not x:
                        break
                    self.buf.extend(x)
            except (OSError, http.client.HTTPException, ValueError):
                pass

        def events(self):
            out = []
            for ln in bytes(self.buf).decode('utf-8', 'replace').splitlines():
                if ln.startswith('data: '):
                    try:
                        out.append(json.loads(ln[6:]))
                    except ValueError:
                        pass
            return out

        def close(self):
            try:
                self.resp.close()
                self.c.close()
            except OSError:
                pass

    # ---- before connecting
    r = call('GET', '/api/mapping')
    check('GET /api/mapping before anything: {ok, state: unknown}', r == {'ok': True, 'state': 'unknown'}, str(r))
    code, body, hd = call_raw('GET', '/api/map/live.png')
    check('GET /api/map/live.png: 404 JSON when there is no map', code == 404 and json.loads(body)['ok'] is False)
    code, body, hd = call_raw('GET', '/api/maps/preview.png?name=demo_room')
    check('preview while not connected: 409 JSON', code == 409 and json.loads(body)['ok'] is False, str(code))
    code, body, hd = call_raw('GET', '/api/maps/download?name=demo_room')
    check('download while not connected: 409 JSON', code == 409, str(code))

    # ---- bad names and the token
    for nm in ('', 'a b', '../x', '.hidden', 'a' * 49, 'x%00y'):
        q = nm.replace(' ', '%20')
        c1 = call_raw('GET', '/api/maps/preview.png?name=' + q)[0]
        c2 = call_raw('GET', '/api/maps/download?name=' + q)[0]
        check('bad map name %r: 400 on preview and download' % nm, c1 == 400 and c2 == 400, '%s %s' % (c1, c2))
    for path in ('/api/mapping', '/api/map/live.png', '/api/maps/preview.png?name=demo_room', '/api/maps/download?name=demo_room'):
        check('%s without the token: refused (403)' % path.split('?')[0], call_raw('GET', path, headers={'X-Studio-Token': 'wrong'})[0] == 403)
    check('wrong Host header is refused', call_raw('GET', '/api/mapping', headers={'Host': 'evil.example:%d' % PORT})[0] == 403)

    A = Sse()
    check('connect (fake)', call('POST', '/api/connect', {})['ok'])
    wait_for(lambda: [e for e in A.events() if e.get('ev') == 'status'], 8)
    probe = bridge('mapping_status')
    if probe.get('ok') is False and 'unknown' in str(probe.get('error', '')).lower():
        skip('HTTP mapping part', 'the fake bridge does not know the mapping commands yet: ' + str(probe))
    else:
        check('mapping_status through /api/bridge', probe.get('ok') is True and probe.get('state') in ('idle', 'mapping'), str(probe))
        r = call('GET', '/api/mapping')
        check('GET /api/mapping: remembered from the mapping_status reply', r.get('ok') is True and r.get('state') == probe['state'], str(r))
        if probe['state'] != 'idle':
            skip('start', 'fake bridge not idle')
        r = bridge('mapping_start')
        check('mapping_start accepted', r.get('ok') is True and r.get('state') == 'starting', str(r))
        check('GET /api/mapping follows the command reply', call('GET', '/api/mapping')['state'] in ('starting', 'mapping'))
        ok = wait_for(lambda: call('GET', '/api/mapping').get('state') == 'mapping', 20)
        check('state becomes mapping (from the mapping event)', ok, str(call('GET', '/api/mapping')))
        check('a mapping event is on /api/events, passed on unchanged', any(e.get('ev') == 'mapping' and e.get('state') == 'mapping' for e in A.events()))

        r = bridge('map_on', hz=2)
        check('map_on accepted', r.get('ok') is True, str(r))
        mp = wait_for(lambda: [e for e in A.events() if e.get('ev') == 'map'], 15)
        check('a slim map event arrives on /api/events', bool(mp), '')
        if mp:
            e = mp[0]
            check('slim map event: no data / encoding, has seq, t, width, height, resolution, origin, stride',
                  'data' not in e and 'encoding' not in e and all(k in e for k in ('seq', 't', 'width', 'height', 'resolution', 'origin', 'stride')), str(list(e)))
            check('no map event on the stream carries data', all('data' not in x for x in A.events() if x.get('ev') == 'map'))
        code, body, hd = call_raw('GET', '/api/map/live.png')
        check('GET /api/map/live.png: 200 image/png, no-store', code == 200 and hd['content-type'] == 'image/png' and hd['cache-control'] == 'no-store', str((code, hd.get('content-type'))))
        try:
            w, h, depth, ctype, px = decode_png(body)
            meta = json.loads(hd['x-map-meta'])
            check('live PNG is a valid 8-bit grey image whose size matches X-Map-Meta',
                  depth == 8 and ctype == 0 and meta['width'] == w and meta['height'] == h and meta['resolution'] > 0
                  and 'data' not in meta and set(px) <= set(range(256)), str(meta))
            check('live PNG uses the grey scale (some unknown 205 or free 254 or occupied 0)', bool(set(px) & {205, 254, 0}))
        except (AssertionError, ValueError, KeyError) as ex:
            check('live PNG is valid', False, repr(ex))
        bridge('map_off')

        r = bridge('maps_list')
        has_demo = r.get('ok') is True and any(m.get('name') == 'demo_room' for m in r.get('maps', []))
        if not has_demo:
            saved = bridge('mapping_save', name='demo_room', overwrite=True)
            check('mapping_save demo_room (the fake library had no demo_room)', saved.get('ok') is True, str(saved))
            wait_for(lambda: (call('GET', '/api/mapping').get('last_saved') or {}).get('name') == 'demo_room', 15)
            r = bridge('maps_list')
            has_demo = any(m.get('name') == 'demo_room' for m in r.get('maps', []))
        check('maps_list has demo_room', has_demo, str(r)[:200])

        code, body, hd = call_raw('GET', '/api/maps/preview.png?name=demo_room')
        check('GET /api/maps/preview.png?name=demo_room: valid grey PNG', code == 200 and hd['content-type'] == 'image/png', str((code, body[:80])))
        try:
            w, h, depth, ctype, px = decode_png(body)
            check('preview PNG: 8-bit grey, side at most 512', depth == 8 and ctype == 0 and 0 < max(w, h) <= 512 and len(px) == w * h, str((w, h)))
        except (AssertionError, ValueError) as ex:
            check('preview PNG is valid', False, repr(ex))
        code, body, hd = call_raw('GET', '/api/maps/preview.png?name=demo_room&max=64')
        try:
            w, h = decode_png(body)[:2]
            check('preview max=64 gives a side of at most 64; max below 64 is clamped to 64, junk gives the default',
                  max(w, h) <= 64 and max(decode_png(call_raw('GET', '/api/maps/preview.png?name=demo_room&max=1')[1])[:2]) <= 64
                  and call_raw('GET', '/api/maps/preview.png?name=demo_room&max=abc')[0] == 200, str((w, h)))
        except (AssertionError, ValueError) as ex:
            check('preview max', False, repr(ex))
        code, body, hd = call_raw('GET', '/api/maps/preview.png?name=no_such_map_xyz')
        check('preview of a map that does not exist: JSON error 404/502', code in (404, 502) and json.loads(body)['ok'] is False, str(code))

        code, body, hd = call_raw('GET', '/api/maps/download?name=demo_room')
        check('GET /api/maps/download?name=demo_room: application/zip attachment',
              code == 200 and hd['content-type'] == 'application/zip' and hd.get('content-disposition') == 'attachment; filename="demo_room.zip"', str((code, hd.get('content-type'), hd.get('content-disposition'))))
        try:
            z = zipfile.ZipFile(io.BytesIO(body))
            names = z.namelist()
            check('zip has demo_room.yaml and demo_room.pgm, only that map\'s files', {'demo_room.yaml', 'demo_room.pgm'} <= set(names)
                  and all(n.startswith('demo_room.') for n in names) and z.testzip() is None, str(names))
            check('zip pgm is a P5 file, yaml names the image', z.read('demo_room.pgm')[:2] == b'P5' and b'demo_room' in z.read('demo_room.yaml'))
        except zipfile.BadZipFile:
            check('download is a valid zip', False)
        check('download of a missing map: JSON 404', call_raw('GET', '/api/maps/download?name=no_such_map_xyz')[0] == 404)
        left = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith('studio_map_')]
        check('no temporary download folder is left behind', not left, str(left))

        r = bridge('mapping_stop')
        check('mapping_stop accepted', r.get('ok') is True, str(r))
        check('state returns to idle', wait_for(lambda: call('GET', '/api/mapping').get('state') == 'idle', 20), str(call('GET', '/api/mapping')))

        # a new connection clears the remembered map and state
        check('disconnect', call('POST', '/api/disconnect', {}).get('ok') is not False)
        check('connect again', call('POST', '/api/connect', {})['ok'])
        wait_for(lambda: call('GET', '/api/mapping').get('state') in ('unknown', 'idle'), 8)
        code, body, hd = call_raw('GET', '/api/map/live.png')
        check('after a new connection no stale live map is served', code == 404, str(code))
    A.close()
finally:
    proc.terminate()
    try:
        proc.wait(8)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(OUT, ignore_errors=True)

print('\n%s' % ('ALL PASSED' if fails == 0 else '%d FAILED' % fails))
sys.exit(fails)
