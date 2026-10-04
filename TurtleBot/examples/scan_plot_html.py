"""Turn a lidar_snapshot.py JSON file into a standalone HTML page with a polar plot of the scan.

Runs on ANY computer with Python 3 (Windows, macOS, Linux, or the robot). No ROS, no extra packages.
The plot is an inline SVG: robot at the centre, straight ahead UP, left of the robot on the LEFT,
range rings every RING_STEP m, one dot per lidar return (several scans in different shades).

    # on the robot
    python3 lidar_snapshot.py --count 3 --out ~/robot_code/room.json
    # on your computer
    scp ubuntu@turtlebot4.local:robot_code/room.json .
    python3 scan_plot_html.py room.json                 # writes room.html next to it
    python3 scan_plot_html.py room.json --out plot.html --max-range 3
Open the HTML file in any browser. Exit codes: 0 written, 2 bad input file.
"""
import argparse
import html
import json
import math
import os
import sys

# ---------------------------------------------------------------- parameters
SIZE = 640                    # px, width and height of the plot
MARGIN = 40                   # px around the outer ring (room for labels)
RING_STEP = 0.5               # m between range rings (1.0 m when the plot covers more than 4 m)
ROBOT_RADIUS = 0.17           # m, the Create 3 is about 0.34 m across
MIN_PLOT_RANGE = 1.0          # m, smallest auto range
SPOKES = 30                   # deg between angle spokes


# ---------------------------------------------------------------- pure helpers
def load_scan(path):
    """Read the JSON file. Returns (angles_deg, list of range lists, meta dict). Raises ValueError if bad."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict) or not data.get('scans'):
        raise ValueError('no "scans" in the file (is it from lidar_snapshot.py?)')
    scans = [s['ranges'] for s in data['scans']]
    angles = data.get('angles_robot_deg')
    if not angles:   # rebuild from the laser angles and the lidar yaw
        yaw = float(data.get('lidar_yaw_deg', 90.0))
        n = len(scans[0])
        angles = [math.degrees(data['angle_min'] + i * data['angle_increment']) + yaw for i in range(n)]
    for r in scans:
        if len(r) != len(angles):
            raise ValueError(f'a scan has {len(r)} ranges but there are {len(angles)} angles')
    return angles, scans, data


def to_xy(angle_deg, r):
    """Robot frame point (x forward, y left)."""
    a = math.radians(angle_deg)
    return r * math.cos(a), r * math.sin(a)


def auto_range(scans):
    """Plot range: 95th percentile of the valid returns, rounded up to 0.5 m, at least MIN_PLOT_RANGE."""
    vals = sorted(r for s in scans for r in s if r is not None)
    if not vals:
        return MIN_PLOT_RANGE
    p95 = vals[min(len(vals) - 1, int(0.95 * len(vals)))]
    return max(MIN_PLOT_RANGE, math.ceil(p95 / 0.5) * 0.5)


def make_svg(angles, scans, max_range):
    """The SVG markup. Robot frame (x forward, y left) -> screen: up = forward, left = left."""
    c = SIZE / 2
    scale = (SIZE / 2 - MARGIN) / max_range

    def sx(x, y):
        return c - y * scale

    def sy(x, y):
        return c - x * scale

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" role="img" '
           f'aria-label="Lidar scan, robot at the centre facing up">']
    step = RING_STEP if max_range <= 4 else 1.0
    k = 1
    while k * step <= max_range + 1e-9:
        r = k * step
        out.append(f'<circle class="ring" cx="{c}" cy="{c}" r="{r * scale:.1f}"/>')
        out.append(f'<text class="lbl" x="{c + 3:.1f}" y="{c - r * scale - 3:.1f}">{r:g} m</text>')
        k += 1
    names = {0: 'front', 90: 'left', 180: 'back', 270: 'right'}
    for a in range(0, 360, SPOKES):
        x, y = to_xy(a, max_range)
        out.append(f'<line class="spoke" x1="{c}" y1="{c}" x2="{sx(x, y):.1f}" y2="{sy(x, y):.1f}"/>')
        lx, ly = to_xy(a, max_range + 14 / scale)
        label = names.get(a, f'{a if a <= 180 else a - 360:+d}°')
        out.append(f'<text class="lbl" text-anchor="middle" dominant-baseline="middle" '
                   f'x="{sx(lx, ly):.1f}" y="{sy(lx, ly):.1f}">{label}</text>')
    n = len(scans)
    for i, ranges in enumerate(scans):
        opacity = 0.35 + 0.65 * (i + 1) / n      # the newest scan is the darkest
        dots = []
        for a, r in zip(angles, ranges):
            if r is None or r > max_range:
                continue
            x, y = to_xy(a, r)
            dots.append(f'<circle cx="{sx(x, y):.1f}" cy="{sy(x, y):.1f}" r="2"/>')
        out.append(f'<g class="pts" fill-opacity="{opacity:.2f}">' + ''.join(dots) + '</g>')
    rr = ROBOT_RADIUS * scale
    out.append(f'<circle class="robot" cx="{c}" cy="{c}" r="{rr:.1f}"/>')
    out.append(f'<path class="arrow" d="M {c} {c - rr * 0.8:.1f} L {c - rr * 0.4:.1f} {c + rr * 0.3:.1f} '
               f'L {c + rr * 0.4:.1f} {c + rr * 0.3:.1f} Z"/>')
    out.append('</svg>')
    return '\n'.join(out)


def make_html(angles, scans, meta, max_range, source_name):
    valid = sum(r is not None for s in scans for r in s)
    total = sum(len(s) for s in scans)
    in_front = [r for s in scans for a, r in zip(angles, s) if r is not None and abs((a + 180) % 360 - 180) <= 30]
    nearest = min((r for s in scans for r in s if r is not None), default=None)
    rows = [('File', source_name), ('Saved', meta.get('created', '?')), ('Scans', len(scans)),
            ('Beams per scan', len(angles)), ('Valid returns', f'{100.0 * valid / max(1, total):.0f} %'),
            ('Nearest return', f'{nearest:.2f} m' if nearest is not None else 'none'),
            ('Nearest within ±30° ahead', f'{min(in_front):.2f} m' if in_front else 'none'),
            ('Lidar yaw in robot frame', f'{meta.get("lidar_yaw_deg", "?")}° ({meta.get("lidar_yaw_source", "?")})'),
            ('Plot range', f'{max_range:g} m')]
    table = '\n'.join(f'<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>' for k, v in rows)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lidar Scan Plot</title>
<style>
:root {{ --bg: #ffffff; --fg: #1d2330; --muted: #6b7280; --grid: #d5d9e0; --pts: #c2410c; --robot: #2563eb; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #14171c; --fg: #e5e7eb; --muted: #9ca3af; --grid: #353b45; --pts: #fb923c; --robot: #60a5fa; }}
}}
body {{ margin: 0; padding: 16px; background: var(--bg); color: var(--fg);
       font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 680px; margin: 0 auto; }}
h1 {{ font-size: 1.3rem; margin: 0 0 4px; }}
p {{ color: var(--muted); margin: 0 0 12px; }}
svg {{ width: 100%; height: auto; display: block; }}
.ring, .spoke {{ fill: none; stroke: var(--grid); stroke-width: 1; }}
.lbl {{ fill: var(--muted); font-size: 11px; }}
.pts {{ fill: var(--pts); }}
.robot {{ fill: none; stroke: var(--robot); stroke-width: 2; }}
.arrow {{ fill: var(--robot); }}
table {{ border-collapse: collapse; margin-top: 12px; width: 100%; }}
th, td {{ text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--grid); }}
th {{ color: var(--muted); font-weight: normal; width: 45%; }}
</style>
</head>
<body>
<main>
<h1>Lidar scan</h1>
<p>Robot at the centre (blue circle), straight ahead is up, the robot's left is on the left. One dot per lidar return.</p>
{make_svg(angles, scans, max_range)}
<table>
{table}
</table>
</main>
</body>
</html>
'''


def main():
    p = argparse.ArgumentParser(description='Plot a lidar_snapshot.py JSON file as a standalone HTML page.')
    p.add_argument('json_file')
    p.add_argument('--out', help='output HTML file (default: same name as the JSON with .html)')
    p.add_argument('--max-range', type=float, help='plot range in m (default: automatic)')
    args = p.parse_args()
    try:
        angles, scans, meta = load_scan(args.json_file)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f'cannot read {args.json_file}: {e}')
        return 2
    max_range = args.max_range if args.max_range and args.max_range > 0 else auto_range(scans)
    out = args.out or os.path.splitext(args.json_file)[0] + '.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(make_html(angles, scans, meta, max_range, os.path.basename(args.json_file)))
    print(f'wrote {out} ({len(scans)} scan(s), plot range {max_range:g} m)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
