#!/usr/bin/env python3
"""Judge one simulator run: reads the ground-truth log of fake_base.py and the mission's exit code, prints PASS or
FAIL per check and writes results.json. Standard library only; it only reads and writes files.

    python3 analyse_run.py --run-dir RUN_DIR [--expect-exit 0] [--exit-code N] [--allow-short]

RUN_DIR holds ground_truth.jsonl, sim_world.json (from sim_map.py), mission_exit.txt (written by run_e2e.sh),
optionally top.log (Pi CPU samples) and mission.out. Checks:
  1. mission exit code equals the expected one (--expect-exit; 0 delivered, 3 alarm, 4 no food)
  2. the true robot position never entered the glass room
  3. never closer than the clearance (0.20 m) to the nearest true obstacle while driving
  4. median wall distance on the straight stretches within 0.15 m of wall_offset_m (SKIP with --allow-short when
     fewer than 10 moving samples lie on a straight stretch, for example a run that jams early)
  5. maximum true speed under 0.21 m/s
  6. no BUMP (ground-truth collision)
Exit code 0 when everything passes (SKIP does not fail), 1 on any FAIL, 2 when the inputs are missing.
"""
import argparse
import json
import os
import re
import statistics
import sys

MEDIAN_TOLERANCE = 0.15      # m
MAX_SPEED = 0.21             # m/s
MOVING = 0.05                # m/s, a sample counts as moving above this
MIN_STRAIGHT_SAMPLES = 10


def load_log(path):
    """(samples, events) from ground_truth.jsonl; unreadable lines are skipped."""
    samples, events = [], []
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            (events if 'event' in rec else samples).append(rec)
    return samples, events


def parse_top(text):
    """Pi CPU summary from `top -b -n1` snapshots appended to one file: {'samples', 'cpu_mean', 'cpu_max', 'load1_max'}."""
    busy, loads = [], []
    for line in text.splitlines():
        if 'Cpu(s)' in line:
            m = re.search(r'([\d.,]+)\s*id', line)
            if m:
                busy.append(100.0 - float(m.group(1).replace(',', '.')))
        m = re.search(r'load average:\s*([\d.,]+)', line)
        if m:
            loads.append(float(m.group(1).rstrip('.,').replace(',', '.')))
    out = {'samples': len(busy)}
    if busy:
        out.update(cpu_mean=round(sum(busy) / len(busy), 1), cpu_max=round(max(busy), 1))
    if loads:
        out['load1_max'] = round(max(loads), 2)
    return out


def analyse(samples, events, world, exit_code, expect_exit=0, allow_short=False):
    """Pure judgement. Returns {'checks': [{'name','status','detail'}], 'passed': bool, 'summary': {...}}."""
    checks = []

    def add(name, status, detail):
        checks.append({'name': name, 'status': status, 'detail': detail})

    drive = [s for s in samples if s.get('mode') == 'nav' and not s.get('docked')]

    # 1. exit code
    if exit_code is None:
        add('mission exit code', 'FAIL', 'no mission exit code recorded')
    else:
        add('mission exit code', 'PASS' if exit_code == expect_exit else 'FAIL', f'got {exit_code}, expected {expect_exit}')

    # 2. glass room
    x0, y0, x1, y1 = world['glass_room']
    inside = [s for s in samples if x0 < s['x'] < x1 and y0 < s['y'] < y1]
    add('never entered the glass room', 'FAIL' if inside else 'PASS',
        f'{len(inside)} samples inside, first at t={inside[0]["t"]} ({inside[0]["x"]:.2f}, {inside[0]["y"]:.2f})'
        if inside else f'{len(samples)} samples checked')

    # 3. clearance
    clearance = float(world.get('clearance_m', 0.20))
    if drive:
        worst = min(drive, key=lambda s: s['wall'])
        add('clearance to the wall', 'PASS' if worst['wall'] >= clearance else 'FAIL',
            f'closest {worst["wall"]:.2f} m at t={worst["t"]} ({worst["x"]:.2f}, {worst["y"]:.2f}), limit {clearance:.2f} m')
    else:
        add('clearance to the wall', 'FAIL', 'the robot never drove (no samples)')

    # 4. median wall distance on straight stretches
    offset = float(world['wall_offset_m'])
    rngs = world.get('straight_ranges', [])
    on_wall = [s['wall'] for s in drive if s['speed'] > MOVING and any(a <= s['x'] <= b for a, b in rngs)]
    if len(on_wall) < MIN_STRAIGHT_SAMPLES:
        add('median wall distance', 'SKIP' if allow_short else 'FAIL',
            f'only {len(on_wall)} moving samples on straight stretches (need {MIN_STRAIGHT_SAMPLES})')
    else:
        med = statistics.median(on_wall)
        add('median wall distance', 'PASS' if abs(med - offset) <= MEDIAN_TOLERANCE else 'FAIL',
            f'median {med:.2f} m over {len(on_wall)} samples, wanted {offset:.2f} +- {MEDIAN_TOLERANCE:.2f} m')

    # 5. speed
    vmax = max((s['speed'] for s in samples), default=0.0)
    add('max speed', 'PASS' if vmax < MAX_SPEED else 'FAIL', f'{vmax:.3f} m/s, limit {MAX_SPEED} m/s')

    # 6. bump
    bumps = [e for e in events if e.get('event') == 'hazard' and e.get('type') == 'BUMP']
    add('no BUMP', 'FAIL' if bumps else 'PASS',
        f'{len(bumps)} BUMP, first at t={bumps[0]["t"]} ({bumps[0].get("x")}, {bumps[0].get("y")})' if bumps else 'none')

    ts = [s['t'] for s in samples]
    dist = 0.0
    for a, b in zip(samples, samples[1:]):
        dist += ((b['x'] - a['x']) ** 2 + (b['y'] - a['y']) ** 2) ** 0.5
    summary = {'duration_s': round(max(ts) - min(ts), 1) if ts else 0.0, 'distance_m': round(dist, 1),
               'samples': len(samples), 'events': sorted({e['event'] for e in events}),
               'stalls': sum(1 for e in events if e['event'] == 'stall_start')}
    # Not a check: how far AMCL's belief was from the truth, per axis (along the wall = x in the hall).
    est = [s for s in samples if 'est_err_x' in s and not s.get('docked')]
    if est:
        summary['amcl_error_m'] = {
            'max_x': round(max(abs(s['est_err_x']) for s in est), 2),
            'max_y': round(max(abs(s['est_err_y']) for s in est), 2),
            'median_x': round(statistics.median(abs(s['est_err_x']) for s in est), 2),
            'last_x': est[-1]['est_err_x'], 'last_y': est[-1]['est_err_y']}
    goals = [e for e in events if e.get('event') == 'dock_goal']
    if goals:
        summary['dock_goal_distance_m'] = [e.get('dist') for e in goals]
    return {'checks': checks, 'passed': all(c['status'] != 'FAIL' for c in checks), 'summary': summary}


def main(argv=None):
    ap = argparse.ArgumentParser(description='Judge one delivery simulator run.')
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--expect-exit', type=int, default=0, help='expected mission exit code (default 0)')
    ap.add_argument('--exit-code', type=int, help='mission exit code (default: read RUN_DIR/mission_exit.txt)')
    ap.add_argument('--allow-short', action='store_true', help='do not fail when too few samples lie on straight stretches')
    ap.add_argument('--scenario', default='', help='scenario name, only written to results.json')
    a = ap.parse_args(argv)
    run = a.run_dir
    gt, world_path = os.path.join(run, 'ground_truth.jsonl'), os.path.join(run, 'sim_world.json')
    for p in (gt, world_path):
        if not os.path.isfile(p):
            print(f'missing {p}', file=sys.stderr)
            return 2
    with open(world_path, 'r', encoding='utf-8') as fh:
        world = json.load(fh)
    code = a.exit_code
    exit_file = os.path.join(run, 'mission_exit.txt')
    if code is None and os.path.isfile(exit_file):
        try:
            with open(exit_file, 'r', encoding='utf-8') as fh:
                code = int(fh.read().strip())
        except ValueError:
            code = None
    samples, events = load_log(gt)
    res = analyse(samples, events, world, code, a.expect_exit, a.allow_short)
    top_path = os.path.join(run, 'top.log')
    if os.path.isfile(top_path):
        with open(top_path, 'r', encoding='utf-8', errors='replace') as fh:
            res['pi_cpu'] = parse_top(fh.read())
    res['scenario'] = a.scenario
    res['mission_exit_code'] = code
    res['expected_exit_code'] = a.expect_exit
    for c in res['checks']:
        print(f'{c["status"]:4s} {c["name"]}: {c["detail"]}')
    s = res['summary']
    print(f'time {s["duration_s"]} s, distance {s["distance_m"]} m, {s["samples"]} samples, stalls {s["stalls"]}')
    if 'amcl_error_m' in s:
        print(f'AMCL error (estimate minus truth, m): {s["amcl_error_m"]}; true distance at each /dock goal: '
              f'{s.get("dock_goal_distance_m")}')
    if 'pi_cpu' in res:
        cpu = res['pi_cpu']
        print('Pi CPU: ' + (f'mean {cpu["cpu_mean"]} %, max {cpu["cpu_max"]} % over {cpu["samples"]} samples'
                            if 'cpu_mean' in cpu else 'no usable top samples')
              + (f', load1 max {cpu["load1_max"]}' if 'load1_max' in cpu else ''))
    with open(os.path.join(run, 'results.json'), 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(res, fh, indent=1)
    print('RESULT: ' + ('PASS' if res['passed'] else 'FAIL'))
    return 0 if res['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
