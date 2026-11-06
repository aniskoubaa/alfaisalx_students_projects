"""Offline tests of the delivery route planner (TurtleBot/delivery/tools/plan_route.py).

No robot and no ROS needed. Synthetic maps are written to a temp folder: a 40 m x 12 m hall with outer walls and
a recessed 4 m x 4 m "glass room" opening off the bottom wall (a keepout line closes the opening). The dock is at
the left end and the pickup at the right end, both along the bottom wall. Usage: python test_plan_route.py
Exit code 0 when everything passes.
"""
import html.parser
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

import yaml

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery', 'tools'))
sys.path.insert(0, TOOL_DIR)
import plan_route as pr  # noqa: E402

TMP = tempfile.mkdtemp(prefix='tb4_plan_route_tests_')
fails = 0
LOG = []


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


def quiet(msg):
    LOG.append(msg)


# ---------------------------------------------------------------- synthetic maps
def make_hall(folder, res=0.1, length=40.0, width=12.0, room=True, name='hall'):
    """Write hall.pgm + hall.yaml. Origin (0, -4.4): bottom wall surface at y = 0.2, room below it at x 18..22."""
    oy = -4.4
    total_h = width + 4.4 + 0.4
    W, H = int(round(length / res)), int(round(total_h / res))
    rows = []
    for r in range(H):
        y = oy + (H - r - 0.5) * res
        row = bytearray([0]) * W
        for c in range(W):
            x = (c + 0.5) * res
            free = 0.2 <= x <= length - 0.2 and 0.2 <= y <= width - 0.2
            if room and 18.0 <= x <= 22.0 and -4.0 <= y <= 0.2:
                free = True
            if free:
                row[c] = 254
        rows.append(bytes(row))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + '.pgm'), 'wb') as fh:
        fh.write(f'P5\n# synthetic\n{W} {H}\n255\n'.encode())
        fh.write(b''.join(rows))
    with open(os.path.join(folder, name + '.yaml'), 'w') as fh:
        fh.write(f'image: {name}.pgm\nresolution: {res}\norigin: [0.0, {oy}, 0.0]\nnegate: 0\n'
                 'occupied_thresh: 0.65\nfree_thresh: 0.196\n')
    return os.path.join(folder, name + '.yaml')


def base_spec(length=40.0):
    return {
        'dock_pose': {'x': 1.0, 'y': 0.7, 'yaw': 180.0},
        'goal': {'x': length - 2.0, 'y': 0.7, 'yaw': 0.0},
        'wall_offset_m': 0.5, 'clearance_m': 0.30, 'lane_half_width_m': 0.25, 'waypoint_spacing_m': 2.0,
        'keepout_lines': [{'name': 'glass_room_opening', 'from': [18.0, 0.2], 'to': [22.0, 0.2], 'width_m': 0.10}],
        'keepout_polygons': [{'name': 'cables', 'points': [[30.0, 3.0], [32.0, 3.0], [32.0, 4.0], [30.0, 4.0]]}],
        'slow_zones': [{'name': 'dock', 'speed_percent': 50, 'center': [1.0, 0.7], 'radius_m': 1.5},
                       {'name': 'ramp', 'speed_percent': 40, 'points': [[25.0, 0.2], [28.0, 0.2], [28.0, 2.5], [25.0, 2.5]]}],
        'settings': {'pickup_timeout_s': 300},
    }


def write_spec(path, spec):
    with open(path, 'w') as fh:
        yaml.safe_dump(spec, fh)
    return path


# ---------------------------------------------------------------- mask decoding (Nav2 map_io scale mode)
def decode_new(pix, occ_t=0.99, free_t=0.01):
    occ = 1.0 - pix / 255.0
    if occ >= occ_t:
        return 100
    if occ <= free_t:
        return 0
    return int(round((occ - free_t) / (occ_t - free_t) * 100))


def decode_old(pix, occ_t=0.99, free_t=0.01):
    occ = 1.0 - pix / 255.0
    if occ >= occ_t:
        return 100
    if occ <= free_t:
        return 0
    return 1 + 98 * (occ - free_t) / (occ_t - free_t)


def mask_at(path, gm, x, y):
    w, h, vals = pr.read_pgm(path)
    c, r = gm.cell_of(x, y)
    return vals[r * w + c]


class Checker(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


# ---------------------------------------------------------------- pure helpers
check('pixel formula: 0 -> 255, 100 -> 0, 50 -> 128',
      (pr.value_to_pixel(0), pr.value_to_pixel(100), pr.value_to_pixel(50)) == (255, 0, 128))
check('pixel formula round trip within 1 for all values',
      all(abs(decode_new(pr.value_to_pixel(v)) - v) <= 1 for v in range(101)))
d2 = pr.edt_sq(5, 3, bytearray([1] + [0] * 14))
check('edt: exact squared distances', d2[0] == 0 and d2[4] == 16 and d2[5 + 2] == 5 and d2[14] == 16 + 4, str(d2))
check('wrap_deg', pr.wrap_deg(190) == -170 and pr.wrap_deg(-180) == 180 and pr.wrap_deg(360) == 0)

# ---------------------------------------------------------------- main scenario
t0 = time.time()
mapy = make_hall(os.path.join(TMP, 'm1'))
spec_path = write_spec(os.path.join(TMP, 'spec1.yaml'), base_spec())
out1 = os.path.join(TMP, 'out1')
res1 = pr.plan(mapy, spec_path, out1, log=quiet, command='plan_route.py --test')
gm = res1['map']
RES = gm.res
print(f'(main scenario took {time.time() - t0:.1f} s)')
with open(os.path.join(out1, 'route.yaml')) as fh:
    text = fh.read()
route = yaml.safe_load(text)
check('route.yaml: keys', set(route) == {'version', 'frame_id', 'map', 'dock_pose', 'outbound', 'inbound', 'settings'},
      str(list(route)))
check('route.yaml: version/frame/map', route['version'] == 1 and route['frame_id'] == 'map' and route['map'] == 'map.yaml')
with open(os.path.join(out1, 'map.yaml')) as fh:
    map_copy = yaml.safe_load(fh)
with open(os.path.join(TMP, 'm1', 'hall.pgm'), 'rb') as a, open(os.path.join(out1, 'map.pgm'), 'rb') as b:
    same_image = a.read() == b.read()
check('map copied into the route folder (map.yaml + map.pgm, for start_stack.sh nav)',
      map_copy['image'] == 'map.pgm' and map_copy['resolution'] == gm.res and same_image)
check('route.yaml: header comment with command and date', text.startswith('#') and '# Command:' in text and '# Date:' in text)


def pose_ok(p):
    return (set(p) == {'x', 'y', 'yaw'} and all(isinstance(p[k], (int, float)) for k in p) and -180 < p['yaw'] <= 180)


check('route.yaml: pose types', pose_ok(route['dock_pose']) and all(pose_ok(p) for p in route['outbound'] + route['inbound']))
check('route.yaml: last outbound = pickup',
      route['outbound'][-1] == {'x': 38.0, 'y': 0.7, 'yaw': 0.0}, str(route['outbound'][-1]))
last_in = route['inbound'][-1]
check('route.yaml: last inbound at start point facing the dock',
      abs(last_in['x'] - 1.7) < 0.01 and abs(last_in['y'] - 0.7) < 0.01 and abs(abs(last_in['yaw']) - 180) < 0.2, str(last_in))
check('route.yaml: settings default + override',
      route['settings']['pickup_timeout_s'] == 300 and route['settings']['button_placed'] == 3
      and set(route['settings']) >= {'max_speed', 'handoff_timeout_s', 'hands_clear_s', 'min_battery_start',
                                     'leg_timeout_s', 'button_received', 'min_battery_start'})
check('inbound yaw is outbound yaw + 180 (straight lane)',
      all(abs(abs(p['yaw']) - 180) < 15 for p in route['inbound'][:-1]))

poly = res1['poly']
dense = pr.resample_poly(poly, RES)
check('path stays out of the glass room (y >= 0.2 + clearance everywhere)', min(p[1] for p in dense) >= 0.2 + 0.30 - RES,
      f'min y {min(p[1] for p in dense):.2f}')
wall_d = [p[1] - 0.2 for p in dense]
check('median distance to the bottom wall within 0.15 of wall_offset',
      abs(statistics.median(wall_d) - 0.5) <= 0.15, f'median {statistics.median(wall_d):.3f}')
check('never closer than clearance (EDT distances)', res1['dist_min'] >= 0.30 - 1e-9, f'min {res1["dist_min"]:.3f}')
check('numbers reported', res1['dist_min'] <= res1['dist_median'] <= res1['dist_max'] and res1['length'] > 36,
      f'len {res1["length"]:.1f}')
pts = [(p['x'], p['y']) for p in route['outbound']]
gaps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
check('outbound waypoint spacing <= spacing + 1 cell', max(gaps) <= 2.0 + RES, f'max {max(gaps):.3f}')
pts = [(p['x'], p['y']) for p in route['inbound']]
gaps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
check('inbound waypoint spacing <= spacing + 1 cell', max(gaps) <= 2.0 + RES, f'max {max(gaps):.3f}')
check('all waypoints away from the glass room', all(p['y'] > 0.4 for p in route['outbound'] + route['inbound']))
check('no median warning on the good scenario', not any('median' in w for w in res1['warnings']), str(res1['warnings']))

# masks
kpath = os.path.join(out1, 'keepout_mask.pgm')
spath = os.path.join(out1, 'speed_mask.pgm')
with open(os.path.join(out1, 'keepout_mask.yaml')) as fh:
    ky = yaml.safe_load(fh)
check('mask yaml: scale mode and thresholds',
      ky['mode'] == 'scale' and ky['negate'] == 0 and ky['occupied_thresh'] == 0.99 and ky['free_thresh'] == 0.01
      and ky['image'] == 'keepout_mask.pgm' and ky['resolution'] == RES and ky['origin'][:2] == [0.0, -4.4], str(ky))
w, h, _ = pr.read_pgm(kpath)
check('mask size equals map size', (w, h) == (gm.W, gm.H))
lane_vals = [mask_at(kpath, gm, p['x'], p['y']) for p in route['outbound']]
check('keepout mask: 0 on the lane (both decoders)',
      all(decode_new(v) == 0 and decode_old(v) <= 2 for v in lane_vals), str(lane_vals[:3]))
far = mask_at(kpath, gm, 20.0, 6.0)
check('keepout mask: ~50 away from the lane (new and old decoder +-2)',
      abs(decode_new(far) - 50) <= 2 and abs(decode_old(far) - 50) <= 2, f'{decode_new(far)} {decode_old(far):.1f}')
mid = mask_at(kpath, gm, 20.0, 0.7 + 0.25 + 0.5)
check('keepout mask: rising ramp beside the lane', 10 < decode_new(mid) < 45, str(decode_new(mid)))
kl = mask_at(kpath, gm, 20.0, 0.2)
check('keepout mask: 100 on the keepout line', decode_new(kl) == 100 and decode_old(kl) >= 98, str(decode_new(kl)))
check('keepout mask: 100 inside the keepout polygon', decode_new(mask_at(kpath, gm, 31.0, 3.5)) == 100)
sv_dock = mask_at(spath, gm, 1.0, 0.7)
sv_ramp = mask_at(spath, gm, 26.0, 1.0)
sv_out = mask_at(spath, gm, 10.0, 1.0)
check('speed mask: 100 - speed_percent inside slow zones (circle 50, polygon 40)',
      abs(decode_new(sv_dock) - 50) <= 2 and abs(decode_new(sv_ramp) - 60) <= 2, f'{decode_new(sv_dock)} {decode_new(sv_ramp)}')
check('speed mask: 0 outside zones', decode_new(sv_out) == 0)

# preview
with open(os.path.join(out1, 'preview.html'), encoding='utf-8') as fh:
    page = fh.read()
chk = Checker()
chk.feed(page)
check('preview.html: valid structure, has svg and embedded png', 'svg' in chk.tags and 'image' in chk.tags
      and 'data:image/png;base64,' in page and page.count('<svg') == page.count('</svg>'))
check('preview.html: no external URLs', not re.search(r'https?:|//[a-z0-9.-]+\.[a-z]{2,}|src="[^d]', page))

# ---------------------------------------------------------------- px / py points
c_goal, r_goal = gm.cell_of(38.0, 0.7)
px_spec = base_spec()
px_spec['goal'] = {'px': c_goal, 'py': r_goal, 'yaw': 0.0}
px_spec['dock_pose'] = {'px': gm.cell_of(1.0, 0.7)[0], 'py': gm.cell_of(1.0, 0.7)[1], 'yaw': 180.0}
exp_x, exp_y = gm.px_to_world(c_goal, r_goal)
check('px/py: conversion formula', abs(exp_x - ((c_goal + 0.5) * RES)) < 1e-9
      and abs(exp_y - (-4.4 + (gm.H - r_goal - 0.5) * RES)) < 1e-9)
check('px/py: image rows go down, map y goes up', gm.px_to_world(0, 0)[1] > gm.px_to_world(0, gm.H - 1)[1])
out_px = os.path.join(TMP, 'out_px')
res_px = pr.plan(mapy, write_spec(os.path.join(TMP, 'spec_px.yaml'), px_spec), out_px, log=quiet)
lastp = res_px['outbound'][-1]
check('px/py: goal given in pixels ends the outbound route there',
      abs(lastp[0] - exp_x) < 1e-3 and abs(lastp[1] - exp_y) < 1e-3, str(lastp))
check('px/py: pixel centre within half a cell of the metre goal', abs(exp_x - 38.0) <= RES and abs(exp_y - 0.7) <= RES)

# default start = 0.7 m straight out from the dock (the docked robot faces the dock, yaw 180 here), and via points
v_spec = base_spec()
v_spec['via'] = [{'x': 10.0, 'y': 0.7}, [30.0, 0.7]]
res_v = pr.plan(mapy, write_spec(os.path.join(TMP, 'spec_via.yaml'), v_spec), os.path.join(TMP, 'out_via'), log=quiet)
check('via points: path passes close to each',
      all(min(math.hypot(p[0] - vx, p[1] - vy) for p in res_v['poly']) < 0.3 for vx, vy in ((10.0, 0.7), (30.0, 0.7))))
check('default start is 0.7 m out from the dock, opposite to the dock yaw', abs(res_v['outbound'][0][0] - 1.7) < 0.01 and abs(res_v['outbound'][0][1] - 0.7) < 0.01)

# ---------------------------------------------------------------- failures: exit codes and messages
nopath = base_spec()
nopath['keepout_lines'].append({'name': 'wall_of_keepout', 'from': [10.0, 0.0], 'to': [10.0, 12.0], 'width_m': 0.2})
sp_np = write_spec(os.path.join(TMP, 'spec_np.yaml'), nopath)
cmd = [sys.executable, '-B', os.path.join(TOOL_DIR, 'plan_route.py'), '--map', mapy, '--spec', sp_np,
       '--out', os.path.join(TMP, 'out_np')]
t0 = time.time()
cp = subprocess.run(cmd, capture_output=True, text=True)
check('no path: exit code non-zero (3)', cp.returncode == 3, f'rc {cp.returncode}')
check('no path: message names keepout / clearance as likely cause',
      'no path' in cp.stderr and 'keepout' in cp.stderr and 'clearance' in cp.stderr, cp.stderr.strip()[:120])
check('no path: no route.yaml left behind', not os.path.exists(os.path.join(TMP, 'out_np', 'route.yaml')))
print(f'(no-path run took {time.time() - t0:.1f} s)')

bad = base_spec()
bad['goal'] = {'x': 500.0, 'y': 0.7}
cp = subprocess.run([sys.executable, '-B', os.path.join(TOOL_DIR, 'plan_route.py'), '--map', mapy,
                     '--spec', write_spec(os.path.join(TMP, 'spec_bad.yaml'), bad), '--out', os.path.join(TMP, 'out_bad')],
                    capture_output=True, text=True)
check('goal outside the map: exit 2 with message', cp.returncode == 2 and 'outside the map' in cp.stderr, cp.stderr.strip()[:100])
bad = base_spec()
bad['slow_zones'][0]['speed_percent'] = 5
cp = subprocess.run([sys.executable, '-B', os.path.join(TOOL_DIR, 'plan_route.py'), '--map', mapy,
                     '--spec', write_spec(os.path.join(TMP, 'spec_bad2.yaml'), bad), '--out', os.path.join(TMP, 'out_bad2')],
                    capture_output=True, text=True)
check('slow zone speed_percent below 10: exit 2', cp.returncode == 2 and 'speed_percent' in cp.stderr)

# --info
cp = subprocess.run([sys.executable, '-B', os.path.join(TOOL_DIR, 'plan_route.py'), '--map', mapy, '--info'],
                    capture_output=True, text=True)
check('--info: size in pixels and metres, origin, resolution, conversion',
      cp.returncode == 0 and '400 x 168' in cp.stdout and '40.00 x 16.80 m' in cp.stdout and '-4.4' in cp.stdout
      and 'px + 0.5' in cp.stdout and '0.1 m/pixel' in cp.stdout, cp.stdout[:80])

# example spec parses
ex = os.path.join(TOOL_DIR, 'route_spec.example.yaml')
res_ex = pr.plan(mapy, ex, os.path.join(TMP, 'out_ex'), log=quiet)
check('route_spec.example.yaml plans on the synthetic hall', len(res_ex['outbound']) > 5)

# P2 (ascii) maps load the same way
p2 = os.path.join(TMP, 'm1', 'hall_p2.pgm')
w0, h0, vals0 = pr.read_pgm(os.path.join(TMP, 'm1', 'hall.pgm'))
with open(p2, 'w') as fh:
    fh.write(f'P2\n{w0} {h0}\n255\n' + ' '.join(str(v) for v in vals0) + '\n')
check('P2 pgm reads identical pixels', pr.read_pgm(p2)[2] == vals0)

# ---------------------------------------------------------------- largest map: 100 m x 30 m at 0.05 m (2000 x 680 cells)
t0 = time.time()
big = make_hall(os.path.join(TMP, 'big'), res=0.05, length=100.0, width=30.0, room=False, name='big')
bspec = {'dock_pose': {'x': 1.0, 'y': 0.7, 'yaw': 180.0}, 'goal': {'x': 98.0, 'y': 0.7, 'yaw': 0.0},
         'keepout_lines': [{'name': 'door', 'from': [50.0, 0.2], 'to': [53.0, 0.2]}]}
res_big = pr.plan(big, write_spec(os.path.join(TMP, 'spec_big.yaml'), bspec), os.path.join(TMP, 'out_big'), log=quiet)
el = time.time() - t0
print(f'(largest map: {res_big["map"].W} x {res_big["map"].H} cells, {el:.1f} s)')
check('largest map (2000 x 680 cells) plans in under 60 s', el < 60.0, f'{el:.1f} s')
check('largest map: path length about 97 m', 96 < res_big['length'] < 100, f'{res_big["length"]:.1f}')

shutil.rmtree(TMP, ignore_errors=True)
print('FAILED: %d' % fails if fails else 'ALL PASSED')
sys.exit(1 if fails else 0)
