#!/usr/bin/env python3
"""Plan a wall-hugging delivery route on a saved map (laptop tool, no robot and no ROS needed).

Standard library plus PyYAML only (Python 3.10+, Windows, macOS or Linux).

    python plan_route.py --map my_map.yaml --spec route_spec.yaml --out route_out/
    python plan_route.py --map my_map.yaml --info          # map size, origin, pixel -> metre conversion

Input
  --map   Nav2 / slam_toolbox map yaml (image, resolution, origin, negate, occupied_thresh, free_thresh,
          optional mode). The image must be a PGM (P5 or P2) next to the yaml. Unknown cells count as obstacles.
  --spec  Route spec yaml (see route_spec.example.yaml). Fields:
            dock_pose {x, y, yaw}            robot pose on the dock (yaw in degrees). On the dock the robot FACES the
                                             dock (real robot, 2026-11-06), so yaw points at the dock, not into the room
            start {x, y}                     where the lane begins (default: 0.7 m from the dock, straight out into
                                             the room, that is, opposite to the dock yaw)
            goal {x, y, yaw?}                pickup spot; yaw optional (default: direction of travel)
            via: [{x, y}, ...]               optional points the path must pass through, in order
            wall_offset_m      (0.5)         wanted distance from robot centre to the nearest obstacle
            clearance_m        (0.30)        hard minimum distance to obstacles
            lane_half_width_m  (0.25)        half width of the lane in keepout_mask (value 0)
            waypoint_spacing_m (2.0)         distance between route waypoints
            keepout_lines: [{name, from [x,y], to [x,y], width_m (0.10)}]   lethal lines (glass doors, ...)
            keepout_polygons: [{name, points [[x,y], ...]}]                 lethal areas
            slow_zones: [{name, speed_percent 10..100, points [[x,y],...] or center [x,y] + radius_m}]
            settings: {...}                  overrides copied into route.yaml "settings"
          Every point may instead be {px: column, py: row} in image pixels (counted from the top-left of
          the map image, pixel centres): x = origin_x + (px + 0.5) * resolution,
          y = origin_y + (image_height - py - 0.5) * resolution.
  --out   Output folder (created).

Method: obstacle distance map (exact Euclidean distance transform), cells closer than clearance_m are blocked,
8-connected A* with a step cost that grows with the squared difference between the distance to the nearest
obstacle and wall_offset_m (so the path keeps about wall_offset_m from the wall but can still cross open
areas), light smoothing, resampling to waypoints. Inbound = the outbound lane reversed.

Output files in --out
  route.yaml                      the route (format: delivery/route.example.yaml)
  map.yaml + map.pgm              a copy of the input map, so the folder is complete for robot/start_stack.sh nav
  keepout_mask.pgm / .yaml        0 on the lane, rising to 50 over 1 m, 50 elsewhere, 100 on keepouts
  speed_mask.pgm / .yaml          100 - speed_percent inside slow zones, 0 elsewhere
  preview.html                    self-contained picture of the plan and the numbers (no internet needed)
Mask pixel formula (Nav2 map_io, mode scale, negate 0, occupied_thresh 0.99, free_thresh 0.01):
  occ = 0.01 + 0.98 * value / 100;  pixel = round(255 * (1 - occ));  value 0 -> 255, value 100 -> 0.

Exit code 0 on success, 2 for bad input, 3 when no path exists (the message names the likely cause).
This tool only writes files. It never moves a robot.
"""
import argparse
import base64
import bisect
import datetime
import heapq
import html
import json
import math
import os
import shutil
import statistics
import struct
import sys
import zlib

import yaml

# ---------------------------------------------------------------- constants
DEFAULT_WALL_OFFSET = 0.5      # m, wanted distance from robot centre to the nearest obstacle
DEFAULT_CLEARANCE = 0.30       # m, hard minimum distance to obstacles
DEFAULT_LANE_HALF = 0.25       # m, half width of the lane in the keepout mask
DEFAULT_SPACING = 2.0          # m, waypoint spacing
DEFAULT_START_AHEAD = 0.7      # m, default start point, straight out from the dock (opposite to the dock yaw)
DEFAULT_LINE_WIDTH = 0.10      # m, keepout line width
PEN_WEIGHT = 4.0               # A* wall-offset penalty weight
PEN_CAP = 20.0                 # A* penalty cap (so open areas can still be crossed)
SNAP_RADIUS = 0.4              # m, a start/goal/via point inside the blocked zone is moved at most this far
LANE_SOFT_RANGE = 1.0          # m, mask rises from 0 to 50 over this distance outside the lane
SOFT_VALUE = 50                # mask value (cost 127) away from the lane
LETHAL_VALUE = 100
MEDIAN_TOLERANCE = 0.15        # m, warn when the median wall distance is further than this from wall_offset
KEEPOUT_WARN = 0.10            # m, warn when the path passes closer than this to a keepout
SMOOTH_PASSES = 3
SMOOTH_HALF_WINDOW_M = 0.20    # m
INF = 1e20
SQ2 = math.sqrt(2.0)
NEIGHBOURS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
              (-1, -1, SQ2), (-1, 1, SQ2), (1, -1, SQ2), (1, 1, SQ2)]
DEFAULT_SETTINGS = {
    'max_speed': 0.20, 'pickup_timeout_s': 600, 'handoff_timeout_s': 900, 'hands_clear_s': 5,
    'min_battery_start': 0.40, 'leg_timeout_s': 600, 'button_placed': 3, 'button_received': 4,
}
SPEC_KEYS = {'dock_pose', 'start', 'goal', 'via', 'wall_offset_m', 'clearance_m', 'lane_half_width_m',
             'waypoint_spacing_m', 'keepout_lines', 'keepout_polygons', 'slow_zones', 'settings'}


class PlanError(Exception):
    """A problem the user can fix; code 2 = bad input, 3 = no path."""

    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------- map loading
class GridMap:
    """The map: size, resolution, origin and a per-cell class (0 free, 1 occupied, 2 unknown), image row 0 on top."""

    def __init__(self, width, height, res, ox, oy, cls, yaml_path):
        self.W, self.H, self.res, self.ox, self.oy = width, height, res, ox, oy
        self.cls = cls
        self.yaml_path = yaml_path

    def world_to_uv(self, x, y):
        """Map metres -> continuous image coordinates (column, row); cell (c, r) has its centre at (c+.5, r+.5)."""
        return (x - self.ox) / self.res, self.H - (y - self.oy) / self.res

    def uv_to_world(self, u, v):
        return self.ox + u * self.res, self.oy + (self.H - v) * self.res

    def px_to_world(self, px, py):
        """Pixel (column, row from the top-left) -> map metres, using the pixel centre."""
        return self.uv_to_world(px + 0.5, py + 0.5)

    def cell_of(self, x, y):
        u, v = self.world_to_uv(x, y)
        return int(math.floor(u)), int(math.floor(v))

    def inside(self, c, r):
        return 0 <= c < self.W and 0 <= r < self.H


def read_pgm(path):
    """Return (width, height, bytes of 8-bit values) from a P5 or P2 file."""
    with open(path, 'rb') as fh:
        data = fh.read()
    magic = data[:2]
    if magic not in (b'P5', b'P2'):
        raise PlanError(f'{path}: not a PGM image (P5/P2). Convert the map image to PGM first.')
    pos = [2]

    def token():
        while True:
            while pos[0] < len(data) and data[pos[0]:pos[0] + 1].isspace():
                pos[0] += 1
            if data[pos[0]:pos[0] + 1] == b'#':
                while pos[0] < len(data) and data[pos[0]] not in (10, 13):
                    pos[0] += 1
            else:
                break
        start = pos[0]
        while pos[0] < len(data) and not data[pos[0]:pos[0] + 1].isspace():
            pos[0] += 1
        return data[start:pos[0]]

    try:
        width, height, maxval = int(token()), int(token()), int(token())
    except ValueError:
        raise PlanError(f'{path}: unreadable PGM header') from None
    if width <= 0 or height <= 0 or not 0 < maxval < 65536:
        raise PlanError(f'{path}: bad PGM header')
    n = width * height
    if magic == b'P5':
        pos[0] += 1
        if maxval < 256:
            raw = data[pos[0]:pos[0] + n]
            vals = raw if maxval == 255 else bytes(v * 255 // maxval for v in raw)
        else:
            raw = data[pos[0]:pos[0] + 2 * n]
            if len(raw) < 2 * n:
                raise PlanError(f'{path}: PGM data is too short')
            vals = bytes(((raw[2 * i] << 8) | raw[2 * i + 1]) * 255 // maxval for i in range(n))
    else:
        rest = data[pos[0]:].split()
        vals = bytes(int(v) * 255 // maxval for v in rest[:n])
    if len(vals) < n:
        raise PlanError(f'{path}: PGM data is too short ({len(vals)} of {n} pixels)')
    return width, height, vals


def load_map(yaml_path):
    try:
        with open(yaml_path, 'r', encoding='utf-8') as fh:
            info = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as e:
        raise PlanError(f'cannot read map yaml {yaml_path}: {e}') from None
    if not isinstance(info, dict):
        raise PlanError(f'{yaml_path}: not a map yaml')
    try:
        image = str(info['image'])
        res = float(info['resolution'])
        origin = [float(v) for v in info['origin']]
    except (KeyError, TypeError, ValueError):
        raise PlanError(f'{yaml_path}: needs image, resolution and origin [x, y, yaw]') from None
    if res <= 0 or len(origin) < 2:
        raise PlanError(f'{yaml_path}: bad resolution or origin')
    if len(origin) > 2 and abs(origin[2]) > 1e-6:
        raise PlanError(f'{yaml_path}: a map origin yaw of {origin[2]} is not supported (use 0)')
    negate = int(info.get('negate', 0))
    occ_t = float(info.get('occupied_thresh', 0.65))
    free_t = float(info.get('free_thresh', 0.25))
    img_path = image if os.path.isabs(image) else os.path.join(os.path.dirname(os.path.abspath(yaml_path)), image)
    width, height, vals = read_pgm(img_path)
    table = bytearray(256)
    for v in range(256):
        p = v / 255.0
        occ = p if negate else 1.0 - p
        table[v] = 1 if occ >= occ_t else (0 if occ <= free_t else 2)
    cls = bytearray(vals.translate(bytes(table)))
    return GridMap(width, height, res, origin[0], origin[1], cls, yaml_path)


def info_text(gm):
    w_m, h_m = gm.W * gm.res, gm.H * gm.res
    return '\n'.join([
        f'map yaml:   {gm.yaml_path}',
        f'size:       {gm.W} x {gm.H} pixels = {w_m:.2f} x {h_m:.2f} m',
        f'resolution: {gm.res} m/pixel',
        f'origin:     x={gm.ox}, y={gm.oy} (map position of the bottom-left corner of the image)',
        f'x range:    {gm.ox:.2f} to {gm.ox + w_m:.2f} m;  y range: {gm.oy:.2f} to {gm.oy + h_m:.2f} m',
        'pixel (px = column, py = row from the TOP-LEFT of the image) -> map metres:',
        f'  x = {gm.ox} + (px + 0.5) * {gm.res}',
        f'  y = {gm.oy} + ({gm.H} - py - 0.5) * {gm.res}',
        'In a spec any point can be written {px: 123, py: 45} instead of {x: .., y: ..}.',
    ])


# ---------------------------------------------------------------- distance transform
def _dt1d(f, n):
    """Felzenszwalb exact 1-D squared distance transform of the list f (length n)."""
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    z[0] = -INF
    z[1] = INF
    for q in range(1, n):
        fq = f[q] + q * q
        while True:
            p = v[k]
            s = (fq - (f[p] + p * p)) / (2.0 * (q - p))
            if s <= z[k]:
                k -= 1
            else:
                break
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = INF
    d = [0.0] * n
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        dq = q - v[k]
        d[q] = dq * dq + f[v[k]]
    return d


def edt_sq(width, height, obst):
    """Exact squared distance (in cells^2) from every cell to the nearest obstacle cell (obst[i] truthy)."""
    g = [0.0 if obst[i] else INF for i in range(width * height)]
    for c in range(width):
        col = g[c::width]
        if 0.0 in col:
            g[c::width] = _dt1d(col, height)
    for r in range(height):
        base = r * width
        g[base:base + width] = _dt1d(g[base:base + width], width)
    return g


def surface_distances(gm, obst):
    """Distance in metres from each cell centre to the surface of the nearest obstacle (about half a cell less
    than the centre to centre distance)."""
    d2 = edt_sq(gm.W, gm.H, obst)
    res = gm.res
    return [max(0.0, math.sqrt(d) - 0.5) * res if d < INF else 1e6 for d in d2]


# ---------------------------------------------------------------- rasterizing shapes (cell units)
def line_cells(gm, a, b, half_m):
    """Cells whose centre is within half_m of the segment a-b (map metres)."""
    ua, va = gm.world_to_uv(*a)
    ub, vb = gm.world_to_uv(*b)
    h = half_m / gm.res
    c0 = max(0, int(math.floor(min(ua, ub) - h - 1)))
    c1 = min(gm.W - 1, int(math.ceil(max(ua, ub) + h + 1)))
    r0 = max(0, int(math.floor(min(va, vb) - h - 1)))
    r1 = min(gm.H - 1, int(math.ceil(max(va, vb) + h + 1)))
    dx, dy = ub - ua, vb - va
    ll = dx * dx + dy * dy
    out = []
    for r in range(r0, r1 + 1):
        py = r + 0.5
        for c in range(c0, c1 + 1):
            px = c + 0.5
            t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ua) * dx + (py - va) * dy) / ll))
            ex, ey = px - (ua + t * dx), py - (va + t * dy)
            if ex * ex + ey * ey <= h * h:
                out.append(r * gm.W + c)
    return out


def polygon_cells(gm, pts):
    """Cells whose centre lies inside the polygon (map metres), even-odd scanline fill."""
    uv = [gm.world_to_uv(*p) for p in pts]
    n = len(uv)
    r0 = max(0, int(math.floor(min(v for _, v in uv))))
    r1 = min(gm.H - 1, int(math.ceil(max(v for _, v in uv))))
    out = []
    for r in range(r0, r1 + 1):
        y = r + 0.5
        xs = []
        for i in range(n):
            (x1, y1), (x2, y2) = uv[i], uv[(i + 1) % n]
            if (y1 <= y < y2) or (y2 <= y < y1):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            c_a = max(0, int(math.ceil(xs[k] - 0.5)))
            c_b = min(gm.W - 1, int(math.floor(xs[k + 1] - 0.5)))
            out.extend(range(r * gm.W + c_a, r * gm.W + c_b + 1))
    return out


def circle_cells(gm, center, radius):
    u, v = gm.world_to_uv(*center)
    rc = radius / gm.res
    out = []
    for r in range(max(0, int(v - rc - 1)), min(gm.H - 1, int(v + rc + 1)) + 1):
        for c in range(max(0, int(u - rc - 1)), min(gm.W - 1, int(u + rc + 1)) + 1):
            if (c + 0.5 - u) ** 2 + (r + 0.5 - v) ** 2 <= rc * rc:
                out.append(r * gm.W + c)
    return out


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def point_in_poly(p, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def keepout_distance(p, shape):
    """Distance from point p to the keepout shape's surface (0 inside)."""
    if shape['kind'] == 'line':
        return max(0.0, seg_dist(p, shape['pts'][0], shape['pts'][1]) - shape['width'] / 2.0)
    pts = shape['pts']
    if point_in_poly(p, pts):
        return 0.0
    return min(seg_dist(p, pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


# ---------------------------------------------------------------- spec parsing
def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise PlanError(f'spec: {what} must be a number, got {v!r}')
    return float(v)


def parse_point(gm, v, what):
    """{x, y} or {px, py} or [x, y] -> (x, y) in map metres."""
    if isinstance(v, dict):
        if 'px' in v and 'py' in v:
            return gm.px_to_world(_num(v['px'], what + '.px'), _num(v['py'], what + '.py'))
        if 'x' in v and 'y' in v:
            return _num(v['x'], what + '.x'), _num(v['y'], what + '.y')
    elif isinstance(v, (list, tuple)) and len(v) == 2:
        return _num(v[0], what), _num(v[1], what)
    raise PlanError(f'spec: {what} must be {{x, y}}, {{px, py}} or [x, y], got {v!r}')


def parse_points(gm, v, what, minimum):
    if not isinstance(v, list) or len(v) < minimum:
        raise PlanError(f'spec: {what} needs a list of at least {minimum} points')
    return [parse_point(gm, p, f'{what}[{i}]') for i, p in enumerate(v)]


def wrap_deg(a):
    a = (a + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def parse_spec(gm, spec, log=print):
    if not isinstance(spec, dict):
        raise PlanError('spec: not a yaml mapping')
    for k in spec:
        if k not in SPEC_KEYS:
            log(f'WARNING: unknown spec key "{k}" is ignored')
    s = {}
    if 'dock_pose' not in spec:
        raise PlanError('spec: dock_pose {x, y, yaw} is required')
    dock = spec['dock_pose']
    s['dock'] = parse_point(gm, dock, 'dock_pose')
    s['dock_yaw'] = _num(dock.get('yaw', 0.0), 'dock_pose.yaw') if isinstance(dock, dict) else 0.0
    if 'goal' not in spec:
        raise PlanError('spec: goal {x, y, yaw?} is required')
    goal = spec['goal']
    s['goal'] = parse_point(gm, goal, 'goal')
    s['goal_yaw'] = _num(goal['yaw'], 'goal.yaw') if isinstance(goal, dict) and 'yaw' in goal else None
    if spec.get('start') is not None:
        s['start'] = parse_point(gm, spec['start'], 'start')
    else:
        a = math.radians(s['dock_yaw'] + 180.0)   # the docked robot faces the dock: the room is behind it
        s['start'] = (s['dock'][0] + DEFAULT_START_AHEAD * math.cos(a),
                      s['dock'][1] + DEFAULT_START_AHEAD * math.sin(a))
    s['via'] = [parse_point(gm, p, f'via[{i}]') for i, p in enumerate(spec.get('via') or [])]
    s['wall_offset'] = _num(spec.get('wall_offset_m', DEFAULT_WALL_OFFSET), 'wall_offset_m')
    s['clearance'] = _num(spec.get('clearance_m', DEFAULT_CLEARANCE), 'clearance_m')
    s['lane_half'] = _num(spec.get('lane_half_width_m', DEFAULT_LANE_HALF), 'lane_half_width_m')
    s['spacing'] = _num(spec.get('waypoint_spacing_m', DEFAULT_SPACING), 'waypoint_spacing_m')
    if s['wall_offset'] <= 0 or s['clearance'] < 0 or s['lane_half'] <= 0 or s['spacing'] <= 0:
        raise PlanError('spec: wall_offset_m, lane_half_width_m and waypoint_spacing_m must be > 0, clearance_m >= 0')
    keepouts = []
    for i, ln in enumerate(spec.get('keepout_lines') or []):
        if not isinstance(ln, dict) or 'from' not in ln or 'to' not in ln:
            raise PlanError(f'spec: keepout_lines[{i}] needs from and to')
        keepouts.append({'name': str(ln.get('name', f'line{i}')), 'kind': 'line',
                         'pts': [parse_point(gm, ln['from'], f'keepout_lines[{i}].from'),
                                 parse_point(gm, ln['to'], f'keepout_lines[{i}].to')],
                         'width': _num(ln.get('width_m', DEFAULT_LINE_WIDTH), 'width_m')})
    for i, pg in enumerate(spec.get('keepout_polygons') or []):
        if not isinstance(pg, dict) or 'points' not in pg:
            raise PlanError(f'spec: keepout_polygons[{i}] needs points')
        keepouts.append({'name': str(pg.get('name', f'polygon{i}')), 'kind': 'poly', 'width': 0.0,
                         'pts': parse_points(gm, pg['points'], f'keepout_polygons[{i}].points', 3)})
    s['keepouts'] = keepouts
    zones = []
    for i, z in enumerate(spec.get('slow_zones') or []):
        if not isinstance(z, dict):
            raise PlanError(f'spec: slow_zones[{i}] must be a mapping')
        pct = _num(z.get('speed_percent', -1), f'slow_zones[{i}].speed_percent')
        if not 10 <= pct <= 100:
            raise PlanError(f'spec: slow_zones[{i}].speed_percent must be 10..100, got {pct}')
        zone = {'name': str(z.get('name', f'zone{i}')), 'pct': int(round(pct))}
        if 'points' in z:
            zone['pts'] = parse_points(gm, z['points'], f'slow_zones[{i}].points', 3)
        elif 'center' in z and 'radius_m' in z:
            zone['center'] = parse_point(gm, z['center'], f'slow_zones[{i}].center')
            zone['radius'] = _num(z['radius_m'], f'slow_zones[{i}].radius_m')
        else:
            raise PlanError(f'spec: slow_zones[{i}] needs points, or center and radius_m')
        zones.append(zone)
    s['zones'] = zones
    st = spec.get('settings') or {}
    if not isinstance(st, dict):
        raise PlanError('spec: settings must be a mapping')
    s['settings'] = st
    return s


# ---------------------------------------------------------------- planning
def snap_cell(gm, blocked, cell, max_cells):
    """Return the nearest unblocked cell (c, r) within max_cells of cell, or None."""
    c0, r0 = cell
    best, bd = None, None
    for r in range(r0 - max_cells, r0 + max_cells + 1):
        for c in range(c0 - max_cells, c0 + max_cells + 1):
            if gm.inside(c, r) and not blocked[r * gm.W + c]:
                d = (c - c0) ** 2 + (r - r0) ** 2
                if d <= max_cells * max_cells and (bd is None or d < bd):
                    best, bd = (c, r), d
    return best


def astar(gm, blocked, mult, start, goal):
    """8-connected A*. start/goal are (c, r). Returns a list of (c, r) or None."""
    W, H, res = gm.W, gm.H, gm.res
    n = W * H
    g = [1e30] * n
    par = [-1] * n
    closed = bytearray(n)
    s, t = start[1] * W + start[0], goal[1] * W + goal[0]
    gc, gr = goal
    g[s] = 0.0
    heap = [(0.0, s)]
    push, pop = heapq.heappush, heapq.heappop
    found = False
    while heap:
        _, i = pop(heap)
        if closed[i]:
            continue
        closed[i] = 1
        if i == t:
            found = True
            break
        r, c = divmod(i, W)
        gi = g[i]
        for dr, dc, dl in NEIGHBOURS:
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= H or nc < 0 or nc >= W:
                continue
            j = nr * W + nc
            if blocked[j] or closed[j]:
                continue
            if dr and dc and (blocked[r * W + nc] or blocked[nr * W + c]):
                continue
            ng = gi + dl * res * mult[j]
            if ng < g[j]:
                g[j] = ng
                par[j] = i
                dx, dy = abs(nc - gc), abs(nr - gr)
                push(heap, (ng + (dx + dy + (SQ2 - 2.0) * min(dx, dy)) * res, j))
    if not found:
        return None
    out = []
    i = t
    while i != -1:
        out.append((i % W, i // W))
        i = par[i]
    out.reverse()
    return out


def polyline_length(poly):
    return sum(math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1]) for i in range(len(poly) - 1))


def smooth(gm, poly_uv, dist, clearance):
    """Light moving-average smoothing in image coordinates; a point is only moved if it stays clear of obstacles."""
    half = max(1, int(round(SMOOTH_HALF_WINDOW_M / gm.res)))
    pts = list(poly_uv)
    n = len(pts)
    if n < 2 * half + 2:
        return pts
    for _ in range(SMOOTH_PASSES):
        new = list(pts)
        for i in range(1, n - 1):
            lo, hi = max(0, i - half), min(n - 1, i + half)
            k = min(i - lo, hi - i)
            lo, hi = i - k, i + k
            u = sum(p[0] for p in pts[lo:hi + 1]) / (hi - lo + 1)
            v = sum(p[1] for p in pts[lo:hi + 1]) / (hi - lo + 1)
            c, r = int(u), int(v)
            if gm.inside(c, r) and dist[r * gm.W + c] >= clearance:
                new[i] = (u, v)
        pts = new
    return pts


def resample_poly(poly, step):
    """Points every `step` metres along the polyline (including both ends)."""
    cum = [0.0]
    for i in range(1, len(poly)):
        cum.append(cum[-1] + math.hypot(poly[i][0] - poly[i - 1][0], poly[i][1] - poly[i - 1][1]))
    total = cum[-1]
    out = []
    n = max(1, int(math.ceil(total / step - 1e-9)))
    for k in range(n + 1):
        out.append(point_at(poly, cum, total * k / n))
    return out


def point_at(poly, cum, s):
    s = max(0.0, min(cum[-1], s))
    i = min(len(poly) - 2, max(0, bisect.bisect_right(cum, s) - 1))
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg <= 0 else (s - cum[i]) / seg
    return (poly[i][0] + t * (poly[i + 1][0] - poly[i][0]), poly[i][1] + t * (poly[i + 1][1] - poly[i][1]))


def waypoints_along(poly, spacing, look=0.5):
    """Evenly spaced waypoints (x, y, yaw_deg) along poly, first at s=0, last at the end, spacing <= spacing."""
    cum = [0.0]
    for i in range(1, len(poly)):
        cum.append(cum[-1] + math.hypot(poly[i][0] - poly[i - 1][0], poly[i][1] - poly[i - 1][1]))
    total = cum[-1]
    n = max(1, int(math.ceil(total / spacing - 1e-9)))
    out = []
    d = min(look, max(spacing / 2.0, 0.05))
    for k in range(n + 1):
        s = total * k / n
        a = point_at(poly, cum, s - d)
        b = point_at(poly, cum, s + d)
        p = point_at(poly, cum, s)
        yaw = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        out.append((p[0], p[1], wrap_deg(yaw)))
    return out


def plan(map_path, spec_path, out_dir, log=print, command=None):
    """Run the whole planner. Returns a dict with the route, numbers and file names; raises PlanError."""
    gm = load_map(map_path)
    try:
        with open(spec_path, 'r', encoding='utf-8') as fh:
            raw_spec = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as e:
        raise PlanError(f'cannot read spec {spec_path}: {e}') from None
    sp = parse_spec(gm, raw_spec, log)
    W, H, res = gm.W, gm.H, gm.res
    warnings = []

    # obstacles: occupied + unknown cells + burned-in keepouts
    obst = bytearray(1 if v else 0 for v in gm.cls)
    keep_cells = bytearray(W * H)
    for sh in sp['keepouts']:
        if sh['kind'] == 'line':
            cells = line_cells(gm, sh['pts'][0], sh['pts'][1], max(sh['width'] / 2.0, res * 0.75))
        else:
            cells = polygon_cells(gm, sh['pts'])
        for i in cells:
            keep_cells[i] = 1
            obst[i] = 1
    dist = surface_distances(gm, obst)
    clearance, wo = sp['clearance'], sp['wall_offset']
    blocked = bytearray(1 if d < clearance else 0 for d in dist)
    mult = [1.0 + min(PEN_CAP, PEN_WEIGHT * ((d - wo) / wo) ** 2) for d in dist]

    # key cells: start, via..., goal
    names = ['start'] + [f'via[{i}]' for i in range(len(sp['via']))] + ['goal']
    keys_xy = [sp['start']] + sp['via'] + [sp['goal']]
    keys = []
    for nm, (x, y) in zip(names, keys_xy):
        c, r = gm.cell_of(x, y)
        if not gm.inside(c, r):
            raise PlanError(f'{nm} ({x:.2f}, {y:.2f}) is outside the map. Check the coordinates (use --info).')
        if blocked[r * W + c]:
            alt = snap_cell(gm, blocked, (c, r), int(math.ceil(SNAP_RADIUS / res)))
            if alt is None:
                raise PlanError(
                    f'{nm} ({x:.2f}, {y:.2f}) is only {dist[r * W + c]:.2f} m from an obstacle, closer than '
                    f'clearance_m={clearance}, and no free cell is within {SNAP_RADIUS} m. Move the point '
                    'away from the wall or keepout, or lower clearance_m.')
            xn, yn = gm.uv_to_world(alt[0] + 0.5, alt[1] + 0.5)
            warnings.append(f'{nm} ({x:.2f}, {y:.2f}) was too close to an obstacle; moved to ({xn:.2f}, {yn:.2f})')
            c, r = alt
            keys_xy[names.index(nm)] = (xn, yn)
        keys.append((c, r))
    sp['start'], sp['goal'] = keys_xy[0], keys_xy[-1]

    cells = [keys[0]]
    for a, b in zip(keys[:-1], keys[1:]):
        seg = astar(gm, blocked, mult, a, b) if a != b else [a]
        if seg is None:
            fx, fy = gm.uv_to_world(a[0] + 0.5, a[1] + 0.5)
            tx, ty = gm.uv_to_world(b[0] + 0.5, b[1] + 0.5)
            raise PlanError(
                f'no path from ({fx:.2f}, {fy:.2f}) to ({tx:.2f}, {ty:.2f}). Likely cause: a keepout line or polygon '
                f'closes the corridor, or clearance_m={clearance} is too large for a narrow passage, or the map has '
                'unknown cells (grey) across the way. Check preview of the map and the keepouts, then try a '
                'smaller clearance_m.', code=3)
        cells.extend(seg[1:])
    poly_uv = [(c + 0.5, r + 0.5) for c, r in cells]
    poly_uv = smooth(gm, poly_uv, dist, clearance)
    poly = [gm.uv_to_world(u, v) for u, v in poly_uv]
    poly[0] = sp['start']
    poly[-1] = sp['goal']
    # drop zero-length steps
    clean = [poly[0]]
    for p in poly[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-9:
            clean.append(p)
    poly = clean if len(clean) > 1 else poly

    # waypoints
    out_wp = waypoints_along(poly, sp['spacing'])
    gy = sp['goal_yaw']
    out_wp[-1] = (sp['goal'][0], sp['goal'][1], wrap_deg(gy) if gy is not None else out_wp[-1][2])
    rev = list(reversed(poly))
    in_all = waypoints_along(rev, sp['spacing'])
    in_wp = in_all[1:]
    dx, dy = sp['dock'][0] - sp['start'][0], sp['dock'][1] - sp['start'][1]
    face = math.degrees(math.atan2(dy, dx)) if math.hypot(dx, dy) > 0.05 else sp['dock_yaw'] + 180.0
    if in_wp:
        in_wp[-1] = (sp['start'][0], sp['start'][1], wrap_deg(face))
    else:
        in_wp = [(sp['start'][0], sp['start'][1], wrap_deg(face))]

    # numbers
    dense = resample_poly(poly, res)
    ds = []
    for x, y in dense:
        c, r = gm.cell_of(x, y)
        ds.append(dist[r * W + c] if gm.inside(c, r) else 0.0)
    length = polyline_length(poly)
    dmin, dmed, dmax = min(ds), statistics.median(ds), max(ds)
    kmin = None
    if sp['keepouts']:
        kmin = min(keepout_distance(p, sh) for p in dense for sh in sp['keepouts'])
    if abs(dmed - wo) > MEDIAN_TOLERANCE:
        warnings.append(f'median distance to obstacles {dmed:.2f} m is more than {MEDIAN_TOLERANCE} m from '
                        f'wall_offset_m={wo}; the route may not follow a wall '
                        '(open space, or wall_offset_m too small/large)')
    if kmin is not None and kmin < KEEPOUT_WARN:
        warnings.append(f'the path passes {kmin:.2f} m from a keepout (less than {KEEPOUT_WARN} m)')
    report = [
        f'path length:        {length:.1f} m  ({len(out_wp)} outbound and {len(in_wp)} inbound waypoints)',
        f'distance to obstacles along the path: min {dmin:.2f} m, median {dmed:.2f} m, max {dmax:.2f} m'
        f' (wall_offset_m {wo}, clearance_m {clearance})',
    ]
    if kmin is not None:
        report.append(f'closest approach to a keepout: {kmin:.2f} m')
    report += [f'WARNING: {w}' for w in warnings]

    # outputs
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    cmd = command or ' '.join([os.path.basename(sys.argv[0])] + sys.argv[1:])
    settings = dict(DEFAULT_SETTINGS)
    settings.update(sp['settings'])
    copy_map(map_path, out_dir)
    write_route(os.path.join(out_dir, 'route.yaml'), cmd, stamp, 'map.yaml', sp, out_wp, in_wp, settings)

    key_mask, speed_mask = build_masks(gm, sp, poly, keep_cells)
    for name, data in (('keepout_mask', key_mask), ('speed_mask', speed_mask)):
        write_pgm(os.path.join(out_dir, name + '.pgm'), W, H, bytes(value_to_pixel(v) for v in data))
        write_mask_yaml(os.path.join(out_dir, name + '.yaml'), name + '.pgm', gm)
    write_preview(os.path.join(out_dir, 'preview.html'), gm, sp, poly, out_wp, in_wp, report, cmd, stamp)
    for line in report:
        log(line)
    log(f'wrote route.yaml, keepout_mask, speed_mask and preview.html in {out_dir}')
    return {'outbound': out_wp, 'inbound': in_wp, 'poly': poly, 'length': length, 'dist_min': dmin,
            'dist_median': dmed, 'dist_max': dmax, 'keepout_min': kmin, 'warnings': warnings, 'map': gm}


# ---------------------------------------------------------------- masks and files
def value_to_pixel(v):
    """Mask value 0..100 -> PGM pixel for Nav2 map_io scale mode (negate 0, thresholds 0.99 / 0.01)."""
    if v <= 0:
        return 255
    if v >= 100:
        return 0
    return int(round(255 * (1.0 - (0.01 + 0.98 * v / 100.0))))


def build_masks(gm, sp, poly, keep_cells):
    W, H, res = gm.W, gm.H, gm.res
    key = bytearray([SOFT_VALUE]) * (W * H)
    margin = int(math.ceil((sp['lane_half'] + LANE_SOFT_RANGE) / res)) + 2
    path_pts = resample_poly(poly, res / 2.0)
    cells = set()
    for x, y in path_pts:
        c, r = gm.cell_of(x, y)
        if gm.inside(c, r):
            cells.add((c, r))
    c0 = max(0, min(c for c, _ in cells) - margin)
    c1 = min(W - 1, max(c for c, _ in cells) + margin)
    r0 = max(0, min(r for _, r in cells) - margin)
    r1 = min(H - 1, max(r for _, r in cells) + margin)
    sw, sh = c1 - c0 + 1, r1 - r0 + 1
    sub = bytearray(sw * sh)
    for c, r in cells:
        sub[(r - r0) * sw + (c - c0)] = 1
    d2 = edt_sq(sw, sh, sub)
    hw = sp['lane_half']
    for r in range(sh):
        for c in range(sw):
            d = math.sqrt(d2[r * sw + c]) * res
            if d <= hw:
                v = 0
            elif d < hw + LANE_SOFT_RANGE:
                v = int(round(SOFT_VALUE * (d - hw) / LANE_SOFT_RANGE))
            else:
                continue
            key[(r + r0) * W + (c + c0)] = v
    for i in range(W * H):
        if keep_cells[i]:
            key[i] = LETHAL_VALUE
    speed = bytearray(W * H)
    for z in sp['zones']:
        cl = polygon_cells(gm, z['pts']) if 'pts' in z else circle_cells(gm, z['center'], z['radius'])
        val = 100 - z['pct']
        for i in cl:
            if speed[i] < val:
                speed[i] = val
    return key, speed


def write_pgm(path, w, h, data):
    with open(path, 'wb') as fh:
        fh.write(f'P5\n{w} {h}\n255\n'.encode('ascii'))
        fh.write(data)


def write_mask_yaml(path, image, gm):
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('# Costmap filter mask written by plan_route.py. Value convention: see plan_route.py docstring.\n')
        fh.write(f'image: {image}\nmode: scale\nresolution: {gm.res}\n')
        fh.write(f'origin: [{gm.ox}, {gm.oy}, 0.0]\nnegate: 0\noccupied_thresh: 0.99\nfree_thresh: 0.01\n')


def _pose(w):
    return '{x: %.3f, y: %.3f, yaw: %.1f}' % (w[0], w[1], w[2])


def copy_map(map_path, out_dir):
    """Copy the map into out_dir as map.yaml + map.<ext>, so the route folder is complete on its own:
    robot/start_stack.sh nav --route-dir DIR loads DIR/map.yaml next to the masks and route.yaml."""
    with open(map_path, 'r', encoding='utf-8') as fh:
        meta = yaml.safe_load(fh)
    image = str(meta['image'])
    src = image if os.path.isabs(image) else os.path.join(os.path.dirname(os.path.abspath(map_path)), image)
    dst_name = 'map' + (os.path.splitext(image)[1] or '.pgm')
    dst = os.path.join(out_dir, dst_name)
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    meta['image'] = dst_name
    dst_yaml = os.path.join(out_dir, 'map.yaml')
    if os.path.abspath(map_path) != os.path.abspath(dst_yaml):
        with open(dst_yaml, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(f'# copy of {os.path.basename(map_path)} made by plan_route.py\n')
            yaml.safe_dump(meta, fh, default_flow_style=None, sort_keys=False)


def write_route(path, cmd, stamp, map_name, sp, out_wp, in_wp, settings):
    lines = [
        '# Delivery route for delivery_mission.py, written by tools/plan_route.py. Map frame, metres, yaw in degrees.',
        f'# Command: {cmd}',
        f'# Date: {stamp}',
        'version: 1',
        'frame_id: map',
        f'map: {json.dumps(map_name)}',
        f"dock_pose: {_pose((sp['dock'][0], sp['dock'][1], sp['dock_yaw']))}",
        'outbound:                      # the LAST pose is the pickup pose',
    ]
    lines += [f'  - {_pose(w)}' for w in out_wp]
    lines.append('inbound:                       # the LAST pose is the handoff pose in front of the dock, facing it')
    lines += [f'  - {_pose(w)}' for w in in_wp]
    lines.append('settings:')
    lines += [f'  {k}: {json.dumps(v)}' for k, v in settings.items()]
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')


def png_bytes(w, h, rows):
    """8-bit grayscale PNG from a list of row bytes."""
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    raw = b''.join(b'\x00' + r for r in rows)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def write_preview(path, gm, sp, poly, out_wp, in_wp, report, cmd, stamp):
    W, H, res = gm.W, gm.H, gm.res
    table = bytearray(256)
    table[0], table[1], table[2] = 245, 25, 185
    img = bytes(gm.cls).translate(bytes(table))
    png = png_bytes(W, H, [img[r * W:(r + 1) * W] for r in range(H)])
    b64 = base64.b64encode(png).decode('ascii')

    def uv(p):
        u, v = gm.world_to_uv(*p)
        return f'{u:.2f},{v:.2f}'
    s = []
    s.append(f'<image href="data:image/png;base64,{b64}" width="{W}" height="{H}" style="image-rendering:pixelated"/>')
    for z in sp['zones']:
        if 'pts' in z:
            s.append(f'<polygon points="{" ".join(uv(p) for p in z["pts"])}" fill="orange" fill-opacity="0.35" '
                     f'stroke="orange" stroke-width="1"><title>{html.escape(z["name"])} {z["pct"]}%</title></polygon>')
        else:
            u, v = gm.world_to_uv(*z['center'])
            s.append(f'<circle cx="{u:.2f}" cy="{v:.2f}" r="{z["radius"] / res:.2f}" fill="orange" fill-opacity="0.35" '
                     f'stroke="orange" stroke-width="1"><title>{html.escape(z["name"])} {z["pct"]}%</title></circle>')
    s.append(f'<polyline points="{" ".join(uv(p) for p in poly)}" fill="none" stroke="gold" stroke-opacity="0.45" '
             f'stroke-width="{2 * sp["lane_half"] / res:.2f}" stroke-linejoin="round" stroke-linecap="round"/>')
    for k in sp['keepouts']:
        if k['kind'] == 'line':
            s.append(f'<polyline points="{uv(k["pts"][0])} {uv(k["pts"][1])}" fill="none" stroke="red" '
                     f'stroke-width="{max(k["width"] / res, 2):.2f}">'
                     f'<title>{html.escape(k["name"])}</title></polyline>')
        else:
            s.append(f'<polygon points="{" ".join(uv(p) for p in k["pts"])}" fill="red" fill-opacity="0.4" '
                     f'stroke="red" stroke-width="1"><title>{html.escape(k["name"])}</title></polygon>')
    L = 0.6 / res

    def arrow(w, colour):
        u, v = gm.world_to_uv(w[0], w[1])
        return (f'<g transform="translate({u:.2f},{v:.2f}) rotate({-w[2]:.1f})"><polygon '
                f'points="{L:.1f},0 {-L * 0.5:.1f},{-L * 0.45:.1f} {-L * 0.5:.1f},{L * 0.45:.1f}" fill="{colour}" '
                f'stroke="white" stroke-width="{max(0.3, L / 20):.2f}"/></g>')
    for w in out_wp:
        s.append(arrow(w, 'royalblue'))
    for w in in_wp:
        s.append(arrow(w, 'seagreen'))
    du, dv = gm.world_to_uv(*sp['dock'])
    gu, gv = gm.world_to_uv(*sp['goal'])
    s.append(f'<rect x="{du - L / 2:.1f}" y="{dv - L / 2:.1f}" width="{L:.1f}" height="{L:.1f}" '
             'fill="black" stroke="white"/>')
    s.append(f'<circle cx="{gu:.1f}" cy="{gv:.1f}" r="{L / 2:.1f}" fill="magenta" stroke="white"/>')
    legend = [('royalblue', 'outbound waypoint (arrow = heading)'), ('seagreen', 'inbound waypoint'),
              ('gold', 'lane band (keepout_mask value 0)'), ('red', 'keepout (lethal)'),
              ('orange', 'slow zone'), ('black', 'dock'), ('magenta', 'pickup')]
    leg = ''.join(f'<span class="k"><i style="background:{c}"></i>{html.escape(t)}</span>' for c, t in legend)
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Route preview</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}}
.k{{display:inline-block;margin-right:14px}}
.k i{{display:inline-block;width:12px;height:12px;margin-right:4px;border:1px solid #888}}
#box{{overflow:auto;border:1px solid #999;background:#fff;max-height:75vh}} svg{{display:block}}
pre{{background:#fff;border:1px solid #ccc;padding:8px;overflow:auto}}
</style></head><body>
<h1>Route preview</h1>
<p>Map: {html.escape(os.path.basename(gm.yaml_path))}, {W} x {H} cells, {res} m/cell. Planned {stamp}.
Zoom: <select id="z"><option value="1">1x</option><option value="2">2x</option>
<option value="4">4x</option><option value="8">8x</option></select></p>
<p>{leg}</p>
<div id="box"><svg id="s" viewBox="0 0 {W} {H}" style="width:100%">{''.join(s)}</svg></div>
<h2>Numbers</h2>
<pre>{html.escape(chr(10).join(report))}</pre>
<p><small>Command: {html.escape(cmd)}</small></p>
<script>
document.getElementById('z').onchange=function(){{document.getElementById('s').style.width=(100*this.value)+'%';}};
</script>
</body></html>
"""
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(body)


# ---------------------------------------------------------------- command line
def main(argv=None):
    ap = argparse.ArgumentParser(description='Plan a wall-hugging delivery route on a saved map (laptop tool).')
    ap.add_argument('--map', required=True, help='map yaml (Nav2 / slam_toolbox)')
    ap.add_argument('--spec', help='route spec yaml (see route_spec.example.yaml)')
    ap.add_argument('--out', help='output folder')
    ap.add_argument('--info', action='store_true', help='print map size, origin, resolution and pixel conversion, '
                    'then exit')
    a = ap.parse_args(argv)
    try:
        if a.info:
            print(info_text(load_map(a.map)))
            return 0
        if not a.spec or not a.out:
            ap.error('--spec and --out are required (or use --info)')
        plan(a.map, a.spec, a.out)
        return 0
    except PlanError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return e.code


if __name__ == '__main__':
    sys.exit(main())
