"""Unit tests of the pure logic (stub ROS via sim.py imports)."""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim  # noqa: E402  (installs the ROS stubs)

OUT = tempfile.mkdtemp(prefix='tb4_tests_')   # generated files go here, not into the repo

import lidar_snapshot as ls  # noqa: E402
import lightring_status as lr  # noqa: E402
import more_shapes as mo  # noqa: E402
import motion_common as mc  # noqa: E402
import motion_shapes as ms  # noqa: E402
import scan_plot_html as sp  # noqa: E402
import sensor_report as sr  # noqa: E402
import wall_approach as wa  # noqa: E402
import keep_distance as kd  # noqa: E402
import health_check as hc  # noqa: E402

fails = 0


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


# ---- shape plans end where expected
def end(segs):
    return mo.simulate_plan(segs)


for n in range(3, 13):
    x, y, h, far = end(mo.plan_more('polygon', 0.2, n))
    R = 0.2 / (2 * math.sin(math.pi / n))
    expected_far = 2 * R if n % 2 == 0 else 2 * R * math.sin((n // 2) * math.pi / n)  # longest chord
    check(f'polygon {n} closed, heading 360, far={far:.3f}',
          abs(x) < 1e-9 and abs(y) < 1e-9 and abs(h - 2 * math.pi) < 1e-9 and abs(far - expected_far) < 1e-6,
          f'{expected_far:.3f}')
x, y, h, far = end(mo.plan_more('star', 0.4))
check('star closed, 720 deg, far == side', abs(x) < 1e-9 and abs(y) < 1e-9 and abs(h - 4 * math.pi) < 1e-9
      and abs(far - 0.4) < 1e-6, f'far {far:.4f}')
x, y, h, far = end(mo.plan_more('circle', radius=0.25))
check('circle closed, 360, far = 2r', abs(x) < 1e-9 and abs(y) < 1e-9 and abs(h - 2 * math.pi) < 1e-9
      and abs(far - 0.5) < 1e-3, f'far {far:.4f}')
segs = mo.plan_more('square_spiral', step=0.1, max_leg=0.5)
legs = [s['distance'] for s in segs if s['kind'] == 'straight']
x, y, h, far = end(segs)
check('square_spiral legs 0.1,0.1,...,0.5,0.5 and end (0.3, 0.3)',
      [round(l, 3) for l in legs] == [0.1, 0.1, 0.2, 0.2, 0.3, 0.3, 0.4, 0.4, 0.5, 0.5]
      and abs(x - 0.3) < 1e-9 and abs(y - 0.3) < 1e-9, f'{legs} end {x},{y} far {far:.3f}')
segs = mo.plan_more('square_spiral', step=0.1, max_leg=0.9)
check('square_spiral capped at 0.5 m', max(s['distance'] for s in segs if s['kind'] == 'straight') <= 0.5 + 1e-9)
for legs_n in range(1, 9):
    segs = mo.plan_more('zigzag', side=0.25, legs=legs_n)
    x, y, h, far = end(segs)
    inner = [s['angle'] for s in segs if s['kind'] == 'turn'][1:-1]
    check(f'zigzag {legs_n} legs: heading back to 0, on the centre line if even, +/-60 inner turns',
          abs(h) < 1e-9 and (abs(y) < 1e-9 if legs_n % 2 == 0 else abs(abs(y) - 0.125) < 1e-9) and abs(x - legs_n * 0.25 * math.cos(math.radians(30))) < 1e-9
          and all(abs(abs(a) - math.radians(60)) < 1e-9 for a in inner)
          and all(inner[i] * inner[i + 1] < 0 for i in range(len(inner) - 1)), f'x {x:.3f}')
for shape in ms.SHAPES:
    segs = mo.plan_more(shape, side=0.4)
    check(f'motion_shapes {shape} is closed (repeatable)', mo.is_closed(segs))
check('zigzag / spiral are not closed', not mo.is_closed(mo.plan_more('zigzag')) and
      not mo.is_closed(mo.plan_more('square_spiral')))
# simulate_plan agrees with motion_shapes.planned_end_pose for straight/turn plans
for shape in ('square', 'triangle', 'back_and_forth'):
    segs = ms.plan_segments(shape, 0.4, 0.2)
    a, b = mo.simulate_plan(segs)[:3], ms.planned_end_pose(segs)
    check(f'simulate_plan == planned_end_pose for {shape}', all(abs(p - q) < 1e-9 for p, q in zip(a, b)))
# right-hand arc
x, y, h, far = mo.simulate_plan([{'kind': 'arc', 'angle': -math.pi, 'radius': 0.2}])
check('half right circle ends 0.4 m to the right, heading -180', abs(x) < 1e-9 and abs(y + 0.4) < 1e-9
      and abs(h + math.pi) < 1e-9)
check('front_needed', mo.front_needed(mo.plan_more('star', 0.4)) == 0.4 + ms.OBSTACLE_STOP_DISTANCE
      and mo.front_needed(mo.plan_more('zigzag')) == 0.0)

# ---- motion_common helpers
off = math.pi / 2                     # lidar turned +90: robot forward = laser -90 deg
n = 720
amin, inc = -3.124, 0.0087
ranges = [5.0] * n
i_fwd = round((-math.pi / 2 - amin) / inc)
for k in range(i_fwd - 3, i_fwd + 4):
    ranges[k] = 0.8
ranges[i_fwd] = float('nan')
vals = mc.sector_ranges(ranges, amin, inc, 0.15, 12.0, off, math.radians(5))
check('sector_ranges picks robot-forward beams (laser -90 deg)', vals[0] == 0.8 and len([v for v in vals if v == 0.8]) == 6)
check('front_distance near = 3rd smallest', mc.front_distance([0.5, 0.6, 0.7, 0.9], 'near') == 0.7
      and mc.front_distance([0.5], 'near') == 0.5 and math.isinf(mc.front_distance([], 'near')))
check('front_distance median', mc.front_distance([1, 2, 3], 'median') == 2 and mc.front_distance([1, 2, 3, 4], 'median') == 2.5)
fx, fy = mc.to_start_frame(1.0, 1.0, math.pi / 2, 1.0, 2.0)
check('to_start_frame: 1 m along start heading = +x', abs(fx - 1) < 1e-9 and abs(fy) < 1e-9)

# ---- lidar_snapshot sector math
check('sector_of 0 -> 0, +10 -> 1, -10 -> 35, 180 -> 18, +4.9 -> 0, +5.1 -> 1',
      [ls.sector_of(a) for a in (0, 10, -10, 180, -180, 4.9, 5.1, 359)] == [0, 1, 35, 18, 18, 0, 1, 0])
angles = ls.robot_angles_deg(amin, inc, n, 90.0)
check('robot_angles_deg: beam at laser -90 deg is robot 0 deg', abs(angles[i_fwd]) < 0.3, f'{angles[i_fwd]}')
clean = ls.clean_ranges(ranges, 0.15, 12.0)
mins = ls.sector_minima(angles, [clean])
check('sector_minima: front sector 0.8, others 5.0', mins[0] == 0.8 and all(m == 5.0 for m in mins[1:]), str(mins[:3]))
check('summary has 36 lines, starts at front', len(ls.summary_lines(mins)) == 36 and 'front' in ls.summary_lines(mins)[0])
check('clean_ranges drops nan/inf/out of range', ls.clean_ranges([0.1, float('inf'), float('nan'), 1.23456, 12.5], 0.15, 12.0)
      == [None, None, None, 1.235, None])

# ---- wall_approach / keep_distance pure logic
check('plan_travel', wa.plan_travel(1.2, 0.5, 1.0) == 0.7 and wa.plan_travel(2.5, 0.5, 1.0) == 1.0
      and wa.plan_travel(0.4, 0.5, 1.0) == 0.0 and wa.plan_travel(float('inf'), 0.5, 1.0) == 0.0)
check('fit_slope', abs(wa.fit_slope([0, 1, 2, 3], [5, 4, 3, 2]) + 1) < 1e-12 and wa.fit_slope([1, 1], [1, 2]) is None)
check('keep: too far -> forward capped', kd.control(1.2, 0.6, 0.0, 0.1, True) == 0.1)
check('keep: too close -> reverse capped 0.05', kd.control(0.3, 0.6, 0.0, 0.1, True) == -0.05)
check('keep: deadband', kd.control(0.62, 0.6, 0.0, 0.1, True) == 0.0)
check('keep: no reverse beyond -0.2 m', kd.control(0.3, 0.6, -0.2, 0.1, True) == 0.0)
check('keep: no forward beyond +0.8 m', kd.control(1.2, 0.6, 0.8, 0.1, True) == 0.0)
check('keep: nothing / far object -> stand still', kd.control(float('inf'), 0.6, 0, 0.1, True) == 0.0
      and kd.control(2.0, 0.6, 0, 0.1, True) == 0.0)
check('keep: backup limit -> no reverse', kd.control(0.3, 0.6, 0.0, 0.1, False) == 0.0)
check('keep: small error -> min command', kd.control(0.635, 0.6, 0.0, 0.1, True) == kd.MIN_COMMAND)

# ---- lightring
check('lightring full battery: 6 green', lr.pattern(1.0, False, False, True) == [lr.GREEN] * 6)
check('lightring 42 %: 3 yellow', lr.pattern(0.42, False, False, True) == [lr.YELLOW] * 3 + [lr.OFF] * 3)
check('lightring 5 %: 1 red', lr.pattern(0.05, False, False, True) == [lr.RED] + [lr.OFF] * 5)
check('lightring lidar stale off dock: blink red', lr.pattern(0.9, True, False, True) == [lr.RED] * 6
      and lr.pattern(0.9, True, False, False) == [lr.OFF] * 6)
check('lightring lidar stale on dock: battery colours', lr.pattern(0.9, True, True, True) == [lr.GREEN] * 6)
check('lightring no battery: blink white', lr.pattern(None, False, False, True) == [lr.WHITE] * 6)

# ---- sensor_report gap stats
g = sr.gap_stats([0.0, 0.05, 0.10, 0.15, 0.95, 1.0])
check('gap_stats max gap 0.8 at 0.15, one big gap', abs(g['max_gap_s'] - 0.8) < 1e-9 and abs(g['max_gap_at_s'] - 0.15) < 1e-9
      and len(g['big_gaps']) == 1 and abs(g['rate_hz'] - 5.0) < 1e-9, str(g))
check('gap_stats with <2 samples', sr.gap_stats([1.0])['rate_hz'] is None)

# ---- scan_plot_html on a synthetic scan
synth = {'created': 'synthetic', 'frame_id': 'rplidar_link', 'lidar_yaw_deg': 90.0, 'lidar_yaw_source': 'tf',
         'range_min': 0.15, 'range_max': 12.0, 'angle_min': amin, 'angle_increment': inc,
         'angles_robot_deg': angles,
         'scans': [{'stamp': 0.0, 'ranges': [None if k % 4 == 0 else round(1.0 / max(0.3, abs(math.cos(math.radians(a)))), 3)
                                              if abs(a) < 70 else 2.0 for k, a in enumerate(angles)]},
                   {'stamp': 0.13, 'ranges': clean}]}
synth_path = os.path.join(OUT, 'synthetic_scan.json')
with open(synth_path, 'w') as f:
    json.dump(synth, f)
html_path = os.path.join(OUT, 'synthetic_scan.html')
r = subprocess.run([sys.executable, os.path.join(sim.EX, 'scan_plot_html.py'), synth_path, '--out', html_path],
                   capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
check('scan_plot_html exit 0', r.returncode == 0, r.stdout.strip() + r.stderr.strip())
doc = open(html_path, encoding='utf-8').read()


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in ('meta', 'circle', 'line', 'path', 'br'):
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in ('circle', 'line', 'path'):
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f'unexpected </{tag}> with stack {self.stack[-3:]}')
        else:
            self.stack.pop()


p = P()
p.feed(doc)
check('HTML tags balanced', not p.errors and p.stack == [], f'{p.errors[:2]} {p.stack}')
check('HTML has doctype, title, viewport, dark mode', doc.startswith('<!doctype html>') and '<title>' in doc
      and 'viewport' in doc and 'prefers-color-scheme: dark' in doc)
svg = doc[doc.index('<svg'):doc.index('</svg>') + 6]
root = ET.fromstring(svg)
dots = root.findall('.//{http://www.w3.org/2000/svg}g/{http://www.w3.org/2000/svg}circle')
check('SVG parses as XML and has dots', len(dots) > 500, f'{len(dots)} dots')
# forward points (robot angle ~0) must plot above the centre, left points left of the centre
c = sp.SIZE / 2
ax, ay = sp.to_xy(0, 1.0)
check('forward is up', abs(ax - 1) < 1e-9 and abs(ay) < 1e-9)
fwd_dot = None
scale = (sp.SIZE / 2 - sp.MARGIN) / sp.auto_range(synth and [s['ranges'] for s in synth['scans']])
check('auto range >= 1 m', sp.auto_range([s['ranges'] for s in synth['scans']]) >= 1.0)
check('left of the robot plots left', (lambda x, y: c - y * scale < c)(*sp.to_xy(90, 1.0)))
snap_json = os.path.join(OUT, 'snap.json')
r1 = subprocess.run([sys.executable, os.path.join(HERE, 'sim.py'), 'snapshot', '--count', '2', '--out', snap_json],
                    capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
check('lidar_snapshot (sim) writes JSON', r1.returncode == 0 and os.path.exists(snap_json),
      (r1.stdout + r1.stderr).strip()[-200:])
r2 = subprocess.run([sys.executable, os.path.join(sim.EX, 'scan_plot_html.py'), snap_json,
                     '--out', os.path.join(OUT, 'snap.html')], capture_output=True, text=True,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
check('scan_plot_html on lidar_snapshot (sim) output', r2.returncode == 0, r2.stdout.strip())
bad = os.path.join(OUT, 'bad.json')
open(bad, 'w').write('{"x": 1}')
r3 = subprocess.run([sys.executable, os.path.join(sim.EX, 'scan_plot_html.py'), bad], capture_output=True, text=True)
check('scan_plot_html rejects bad input with exit 2', r3.returncode == 2, r3.stdout.strip())

# ---- health_check: parsers and every threshold (status is element 0 of each (status, result, hint))
st = lambda row: row[0]  # noqa: E731
check('health exit code: PASS/INFO 0, WARN 1, FAIL 2',
      [hc.exit_code_for(x) for x in ([], ['PASS', 'INFO'], ['PASS', 'WARN', 'INFO'], ['WARN', 'FAIL'])] == [0, 0, 1, 2])
check('health nmcli parse (escaped colon, lo, empty)',
      hc.parse_nmcli_active('Students:wlan0\nlo:lo\nMy\\:Net:eth0\n') == {'wlan0': 'Students', 'lo': 'lo', 'eth0': 'My:Net'}
      and hc.parse_nmcli_active('') == {})
check('health ip -br parse', hc.parse_ip_brief('wlan0            UP             10.87.10.205/18 \n') == ['10.87.10.205/18']
      and hc.parse_ip_brief('wlan0            DOWN           \n') == []
      and hc.parse_ip_brief('Device "wlan0" does not exist.\n') == [])
check('health wifi: Students PASS, fallback profile or 10.42.0.x WARN, no address FAIL, no profile WARN',
      [st(hc.classify_wifi(*a)) for a in (('Students', ['10.87.10.205/18']),
                                          ('netplan-wlan0-Turtlebot4', ['10.42.0.1/24']),
                                          ('Other', ['10.42.0.1/24']), ('Students', []), (None, []),
                                          (None, ['10.87.10.205/18'], 'nmcli did not answer within 4 s'))]
      == ['PASS', 'WARN', 'WARN', 'FAIL', 'FAIL', 'WARN'])
check('health service: active PASS, activating WARN, inactive/failed/empty FAIL',
      [st(hc.classify_service(s)) for s in ('active\n', 'activating', 'inactive', 'failed', '')]
      == ['PASS', 'WARN', 'FAIL', 'FAIL', 'FAIL'])
check('health ROS env: domain 0 (or unset) and Fast DDS (or unset) PASS, others WARN',
      [st(hc.classify_ros_env(*a)) for a in (('0', 'rmw_fastrtps_cpp', 'jazzy'), (None, None, 'jazzy'),
                                             ('7', None, 'jazzy'), ('0', 'rmw_cyclonedds_cpp', 'jazzy'),
                                             ('0', None, None))] == ['PASS', 'PASS', 'WARN', 'WARN', 'WARN'])
wg = hc.window_gaps([0.05, 0.10, 0.15, 0.95, 1.0], 0.0, 1.0)
check('health window_gaps: gap 0.8 at 0.15, rate = count / window',
      abs(wg['max_gap_s'] - 0.8) < 1e-9 and abs(wg['max_gap_at_s'] - 0.15) < 1e-9 and abs(wg['rate_hz'] - 5.0) < 1e-9, str(wg))
wg = hc.window_gaps([0.05 * k for k in range(1, 61)], 0.0, 10.0)
check('health window_gaps: a topic that stops at 3 s shows the 7 s silence to the window end',
      abs(wg['max_gap_s'] - 7.0) < 1e-9 and abs(wg['max_gap_at_s'] - 3.0) < 1e-9, str(wg))
check('health window_gaps: no messages / empty window', hc.window_gaps([], 0.0, 5.0)['max_gap_s'] == 5.0
      and hc.window_gaps([1.0], 1.0, 1.0)['rate_hz'] is None)
check('health /odom rate: 0 msgs FAIL with the restart curl, 14.9 Hz WARN, 15.0 Hz PASS, 1 msg WARN',
      [st(hc.classify_odom_rate(*a)) for a in ((0, None, 10), (149, 14.9, 10), (150, 15.0, 10), (1, 0.1, 10),
                                               (200, 20.0, 10))] == ['FAIL', 'WARN', 'PASS', 'WARN', 'PASS']
      and hc.RESTART_BASE in hc.classify_odom_rate(0, None, 10)[2]
      and hc.RESTART_BASE == 'curl -X POST http://192.168.186.2/api/restart-app')
check('health /dock_status received PASS, missing FAIL with the restart curl',
      st(hc.classify_received('/dock_status', True, 'docked: no')) == 'PASS'
      and st(hc.classify_received('/dock_status', False)) == 'FAIL'
      and hc.RESTART_BASE in hc.classify_received('/dock_status', False)[2])
check('health battery: missing FAIL, 0.299 WARN, 0.30 PASS, nan WARN',
      [st(hc.classify_battery(*a)) for a in ((False, None), (True, 0.299), (True, 0.30), (True, float('nan')),
                                             (True, 0.42), (True, 0.05))] == ['FAIL', 'WARN', 'PASS', 'WARN', 'PASS', 'WARN'])
clock_rows = [hc.classify_clock(d) for d in (0.0, 4.99, -4.99, 5.0, -5.0, 30.0, -6.3e7)]
check('health clock: |diff| < 5 s PASS, otherwise FAIL; no base data INFO',
      [st(r) for r in clock_rows] == ['PASS', 'PASS', 'PASS', 'FAIL', 'FAIL', 'FAIL', 'FAIL']
      and st(hc.classify_clock(None)) == 'INFO')
check('health clock FAIL hint points at MAINTENANCE.md and does not suggest setting the clock',
      all('MAINTENANCE.md' in r[2] and not any(w in r[2] for w in ('date -s', 'timedatectl', 'chrony', 'ntpdate', 'hwclock'))
          for r in clock_rows if r[0] == 'FAIL'), clock_rows[3][2])
check('health lidar USB: CP210x + /dev/RPLIDAR PASS; either missing FAIL with the reseat hint; no lsusb uses the link',
      [st(hc.classify_lidar_usb(*a)) for a in (('ID 10c4:ea60 Silicon Labs CP210x UART Bridge', True, '/dev/ttyUSB0'),
                                               ('ID 1d6b:0002 Linux Foundation 2.0 root hub', True, '/dev/ttyUSB0'),
                                               ('ID 10C4:EA60 Silicon Labs', False), (None, True, '/dev/ttyUSB0'),
                                               (None, False))] == ['PASS', 'FAIL', 'FAIL', 'PASS', 'FAIL']
      and 'reseat' in hc.classify_lidar_usb('', False)[2] and 'MAINTENANCE.md' in hc.classify_lidar_usb('', False)[2])
check('health scan on the dock: INFO "scan not checked", never FAIL',
      hc.classify_scan(True, 0, None, None)[:2] == ('INFO', 'scan not checked: the lidar is switched off on the dock')
      and st(hc.classify_scan(True, 0, None, None, publishers=0)) == 'INFO')
check('health scan off the dock: none FAIL, 4.99 Hz WARN, 5.0 Hz PASS, 39.9 % WARN, 40 % PASS, dock unknown WARN',
      [st(hc.classify_scan(*a)) for a in ((False, 0, None, None), (False, 38, 4.99, 72.0, 720), (False, 39, 5.0, 72.0, 720),
                                          (False, 77, 7.7, 39.9, 720), (False, 77, 7.7, 40.0, 720),
                                          (None, 0, None, None), (None, 77, 7.7, 72.0, 720))]
      == ['FAIL', 'WARN', 'PASS', 'WARN', 'PASS', 'WARN', 'PASS'])
check('health odom gap: 0.3 PASS, 0.31 WARN, 2.0 WARN, 2.01 FAIL, < 2 msgs INFO; notes motion',
      [st(hc.classify_odom_gap(g, 1.0, 200)) for g in (0.05, 0.3, 0.31, 2.0, 2.01)] == ['PASS', 'PASS', 'WARN', 'WARN', 'FAIL']
      and st(hc.classify_odom_gap(None, None, 0)) == 'INFO' and st(hc.classify_odom_gap(9.0, 0.0, 1)) == 'INFO'
      and 'during motion' in hc.classify_odom_gap(0.05, 0.0, 200)[1] and 'during motion' in hc.classify_odom_gap(0.5, 1, 200)[2])
fix_files = hc.CLOCK_FIX_FILES
check('health clock fix: always INFO, installed / partly / not installed, hint names TB-17',
      [hc.classify_clock_fix(dict(zip(fix_files, v)))[1].split(':')[0] for v in ((True, True), (True, False), (False, False))]
      == ['installed', 'partly installed', 'not installed']
      and all(st(hc.classify_clock_fix(dict(zip(fix_files, v)))) == 'INFO' for v in ((True, True), (False, False)))
      and 'TB-17' in hc.classify_clock_fix(dict(zip(fix_files, (True, True))))[2])
check('health CPU temperature: parse millidegrees; 75.0 PASS, 75.1 WARN, 82.0 WARN, 82.1 FAIL, missing INFO',
      hc.parse_thermal('48312\n') == 48.312
      and [st(hc.classify_cpu_temp(c)) for c in (48.3, 75.0, 75.1, 82.0, 82.1, None)] == ['PASS', 'PASS', 'WARN', 'WARN', 'FAIL', 'INFO'])
check('health throttled: parse; 0 PASS, non-zero WARN with decoded flags, missing vcgencmd INFO',
      hc.parse_throttled('throttled=0x0\n') == 0 and hc.parse_throttled('throttled=0x50005') == 0x50005
      and hc.parse_throttled('VCHI initialization failed') is None
      and st(hc.classify_throttled(0)) == 'PASS' and st(hc.classify_throttled(0x50005)) == 'WARN'
      and 'under-voltage now' in hc.classify_throttled(0x50005)[1] and 'throttled since boot' in hc.classify_throttled(0x50005)[1]
      and st(hc.classify_throttled(None, 'vcgencmd not installed')) == 'INFO' and st(hc.classify_throttled(None)) == 'INFO')
check('health load: parse, always INFO, hint only when load >= CPUs',
      hc.parse_loadavg('1.52 1.31 1.20 3/512 12345\n') == (1.52, 1.31, 1.2)
      and hc.classify_load((1.5, 1.3, 1.2), 4)[0::2] == ('INFO', '') and hc.classify_load((4.2, 3.0, 2.0), 4)[2] != '')
check('health disk: 2.0 GB PASS, 1.99 GB WARN', st(hc.classify_disk(2e9, 59e9)) == 'PASS' and st(hc.classify_disk(1.99e9, 59e9)) == 'WARN')
mi = hc.parse_meminfo('MemTotal:        3881468 kB\nMemFree:          912344 kB\nMemAvailable:    2310452 kB\n')
check('health memory: parse /proc/meminfo, INFO in MB', mi == {'MemTotal': 3881468, 'MemFree': 912344, 'MemAvailable': 2310452}
      and hc.classify_memory(mi) == ('INFO', '2366 MB available of 3975 MB', '') and st(hc.classify_memory({})) == 'INFO')
check('health uptime: parse and format', hc.parse_uptime('5123.45 17800.10\n') == 5123.45
      and [hc.format_duration(s) for s in (59, 5123.45, 90061)] == ['0 min', '1 h 25 min', '1 d 1 h 1 min']
      and st(hc.classify_uptime(10)) == 'INFO')
check('health STOP file: present WARN with "rm ~/STOP", absent PASS',
      hc.classify_stop_file(True)[0::2] == ('WARN', 'rm ~/STOP') and st(hc.classify_stop_file(False)) == 'PASS')
pat = hc.motion_pattern()
check('health pgrep pattern: matches every motion program but not its own text (bracket trick)',
      all(re.search(pat, f'python3 /home/ubuntu/robot_code/{p} --yes') for p in hc.MOTION_PROGRAMS)
      and re.search(pat, f'sh -c pgrep -af "{pat}"') is None and re.search(pat, 'python3 health_check.py') is None
      and re.search(pat, 'python3 motion_shapesXpy') is None, pat)
check('health pgrep parse drops own pid; motion programs INFO either way',
      hc.parse_pgrep('2345 python3 motion_shapes.py square --yes\n999 python3 x\n', 999) == [(2345, 'python3 motion_shapes.py square --yes')]
      and hc.classify_motion_programs([])[:2] == ('INFO', 'none running')
      and st(hc.classify_motion_programs([(2345, 'python3 motion_shapes.py square')])) == 'INFO')
check('health isolated(): an exception or a hang gives a WARN row, a normal check its own row',
      st(hc.isolated(lambda: 1 / 0)) == 'WARN' and 'ZeroDivisionError' in hc.isolated(lambda: 1 / 0)[1]
      and st(hc.isolated(lambda: threading.Event().wait(2) or ('PASS', 'x', ''), timeout=0.2)) == 'WARN'
      and hc.isolated(lambda: ('PASS', 'ok', '')) == ('PASS', 'ok', ''))
check('health ROS unavailable: every ROS row FAIL with the setup hint',
      all(r[0] == 'FAIL' and 'setup.bash' in r[2] for r in hc.ros_rows({'error': 'no rclpy'})[0].values())
      and set(hc.ros_rows({'error': 'x'})[0]) == set(hc.ROS_ROWS))
health_json = os.path.join(OUT, 'health.json')
r4 = subprocess.run([sys.executable, os.path.join(HERE, 'sim.py'), 'health', '--seconds', '3', '--json', health_json],
                    capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'SIM_HEALTH': 'ap'})
try:
    with open(health_json) as f:
        hj = json.load(f)
except (OSError, ValueError) as e:
    hj = {'error': str(e)}
check('health_check (sim) --json: valid file, every row has status/result/hint, exit code matches',
      'SIM exit=1' in r4.stdout and hj.get('exit_code') == 1 and len(hj.get('checks', [])) == len(hc.ROWS)
      and all(c['status'] in hc.STATUSES and {'id', 'check', 'result', 'hint'} <= set(c) for c in hj['checks'])
      and {c['id']: c['status'] for c in hj['checks']}['wifi'] == 'WARN'
      and sum(hj['counts'].values()) == len(hc.ROWS) and hj['measurements']['odom_rate_hz'] > 15,
      (r4.stdout + r4.stderr).strip()[-300:])

print(f'\n{fails} failure(s); generated files are in {OUT}')
sys.exit(1 if fails else 0)
