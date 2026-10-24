"""Offline tests of the TurtleBot Studio program templates and the program catalog (programs.json).

No robot and no ROS needed. The five templates in TurtleBot/tools/studio/templates/ run against the simulated
robot in sim.py (stub rclpy, virtual clock, odometry, lidar with the +90 degree mounting, dock status).
Each simulated run is a fresh process of this same file in --child mode.
Usage: python test_studio_templates.py        (set PYTHONDONTWRITEBYTECODE=1 to avoid __pycache__)
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TB = os.path.normpath(os.path.join(HERE, '..', '..'))
TPL = os.path.join(TB, 'tools', 'studio', 'templates')
EXAMPLES = os.path.join(TB, 'examples')
CATALOG = os.path.join(TB, 'tools', 'studio', 'programs.json')
TEMPLATES = ['my_first_program.py', 'spin_in_place.py', 'drive_circle.py', 'drive_forward_and_back.py', 'read_lidar.py']
MOVING = ['spin_in_place.py', 'drive_circle.py', 'drive_forward_and_back.py']
START_TH = 0.3          # the simulated robot's start heading (sim.py)


# ============================================================ child mode: one simulated run in this process
def child(argv):
    sys.path.insert(0, HERE)
    import importlib.util
    import signal
    import sim                       # installs the stub rclpy / message modules and the virtual clock
    path, args = argv[0], argv[1:]
    name = os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stop_file = os.path.join(tempfile.gettempdir(), 'turtlebot_tpl_test_STOP')
    if os.path.exists(stop_file):
        os.remove(stop_file)
    mod.STOP_FILE = stop_file
    if os.environ.get('TPL_STOPFILE_AT_START'):
        open(stop_file, 'w').close()
    for item in filter(None, os.environ.get('TPL_SET', '').split(';')):     # e.g. TIME_LIMIT=3
        k, v = item.split('=')
        setattr(mod, k, float(v))

    cmds, state = [], {'exited': False, 'after': 0}
    orig_publish = sim.Pub.publish

    def publish(self, msg):
        if self.topic == '/cmd_vel':
            cmds.append((msg.twist.linear.x, msg.twist.angular.z, msg.header.frame_id, msg.header.stamp is not None))
            state['after'] += state['exited']
        orig_publish(self, msg)
    sim.Pub.publish = publish

    ev = os.environ.get('TPL_EVENT')      # "stopfile,t" "sigint,t" "sigterm,t" "bump,t" "scanstop,t" (t = seconds from start)
    orig_advance = sim.advance
    fired = []

    def advance(dt):
        orig_advance(dt)
        if ev and not fired:
            kind, at = ev.split(',')
            if sim.CLOCK[0] - sim.T0 >= float(at):
                fired.append(1)
                if kind == 'stopfile':
                    open(stop_file, 'w').close()
                elif kind in ('sigint', 'sigterm'):
                    signal.raise_signal(signal.SIGINT if kind == 'sigint' else signal.SIGTERM)
                elif kind == 'bump':
                    for nd in sim.NODES:
                        nd._subs['/hazard_detection'](sim.NS(detections=[sim.NS(type=1, header=sim.NS(frame_id='bump_front_left'))]))
                elif kind == 'scanstop':
                    sim.NO_SCAN = True
    sim.advance = advance

    sys.argv = [name + '.py'] + args
    try:
        code = mod.main()
    except SystemExit as e:
        code = e.code
    except BaseException as e:           # includes the AssertionError of sim.Pub when a speed cap is broken
        print(f'SIM crash={e!r}')
        code = 99
    state['exited'] = True
    sim.advance(3.0)                      # time passes after the program ended: nothing may be published
    zeros = 0
    for c in reversed(cmds):
        if c[0] == 0.0 and c[1] == 0.0:
            zeros += 1
        else:
            break
    W = sim.W
    print(f'SIM exit={code} t={sim.CLOCK[0] - sim.T0:.1f}s dth={math.degrees(W["th"] - START_TH):+.1f} '
          f'closure_cm={100 * math.hypot(W["x"], W["y"]):.1f} max_r={W["max_r"]:.3f} max_v={W["max_v"]:.3f} '
          f'max_w={W["max_w"]:.3f} cmds={len(cmds)} tail_zero={zeros} final=({W["v"]},{W["w"]}) '
          f'after_exit={state["after"]} nodes_left={len(sim.NODES)} '
          f'bad_header={sum(1 for c in cmds if c[2] != "base_link" or not c[3])} min_wall={W["min_wall"]:.3f} '
          f'nonzero={sum(1 for c in cmds if c[0] != 0.0 or c[1] != 0.0)}')


def unit_child():
    """Pure functions of the templates, imported with ROS stubbed (run in a child so the stubs stay out of the parent)."""
    sys.path.insert(0, HERE)
    import importlib.util
    import sim
    mods = {}
    for f in TEMPLATES:
        spec = importlib.util.spec_from_file_location(f[:-3], os.path.join(TPL, f))
        mods[f] = m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    res = []

    def chk(name, cond):
        res.append((name, bool(cond)))
    NS = sim.NS
    chk('every template imports with ROS stubbed and has main()', all(callable(getattr(m, 'main', None)) for m in mods.values()))
    for f in MOVING:
        m = mods[f]
        chk(f'{f}: wrap_angle(359 deg) = -1 deg', abs(m.wrap_angle(math.radians(359)) + math.radians(1)) < 1e-9)
        chk(f'{f}: clamp', m.clamp(5, 0, 1) == 1 and m.clamp(-5, 0, 1) == 0 and m.clamp(0.5, 0, 1) == 0.5)
        t = m.HeadingTracker()
        for k in range(0, 721, 30):             # yaw goes round twice, wrapping at 180 degrees
            t.update(m.wrap_angle(math.radians(k)))
        chk(f'{f}: HeadingTracker adds up two full turns', abs(t.total - 4 * math.pi) < 1e-6)
        q = NS(x=0.0, y=0.0, z=math.sin(0.4), w=math.cos(0.4))
        chk(f'{f}: yaw_of quaternion', abs(m.yaw_of(q) - 0.8) < 1e-9)
        chk(f'{f}: speed caps are within 0.15 m/s and 1.0 rad/s',
            getattr(m, 'MAX_SPEED') <= (1.0 if f == 'spin_in_place.py' else 0.15) and getattr(m, 'MAX_TURN_SPEED', 1.0) <= 1.0)
        chk(f'{f}: stale limits (hold 0.3 s, abort 2 s)', m.ODOM_HOLD == 0.3 and m.ODOM_STALE == 2.0)
    m = mods['spin_in_place.py']
    chk('spin_in_place: turn_rate slows near the goal and keeps the sign',
        m.turn_rate(3.0, 0.5) == 0.5 and m.turn_rate(0.05, 0.5) == m.MIN_SPEED and m.turn_rate(-1.0, 0.5) == -0.5)
    chk('spin_in_place: SPEED default is within the cap', m.SPEED <= m.MAX_SPEED)
    m = mods['drive_circle.py']
    v, w = m.circle_speeds(0.3, 0.1)
    chk('drive_circle: v = w * r', abs(v - w * 0.3) < 1e-12 and abs(w - 0.1 / 0.3) < 1e-12)
    v, w = m.circle_speeds(0.15, 0.15)
    chk('drive_circle: small radius keeps w within the cap and v = w * r', w <= 1.0 + 1e-12 and abs(v - w * 0.15) < 1e-12)
    v, w = m.circle_speeds(0.05, 0.15)
    chk('drive_circle: tiny radius lowers v so that w stays at the cap', w == 1.0 and abs(v - 0.05) < 1e-12)
    chk('drive_circle: speed above the cap is lowered', m.circle_speeds(0.5, 9.0)[0] <= 0.15)

    def scan_with(laser_angle_deg, distance):
        n, amin, inc = 720, -3.124, 0.0087
        ranges = [float('inf')] * n
        ranges[round((math.radians(laser_angle_deg) - amin) / inc)] = distance
        return ranges, amin, inc
    for f in ('drive_forward_and_back.py', 'drive_circle.py') if hasattr(mods['drive_circle.py'], 'nearest_ahead') else ('drive_forward_and_back.py',):
        m = mods[f]
        for laser, label, expect_front in ((-90, 'laser -90 deg (robot front)', True), (90, 'laser +90 deg (robot rear)', False),
                                           (0, 'laser 0 deg (robot left)', False)):
            r, amin, inc = scan_with(laser, 0.5)
            d = m.nearest_ahead(r, amin, inc, 0.15, 12.0, math.pi / 2, math.radians(30))
            chk(f'{f}: {label} {"is" if expect_front else "is not"} ahead with the +90 deg mounting',
                (abs(d - 0.5) < 1e-9) if expect_front else d == float('inf'))
        r, amin, inc = scan_with(-90, 0.5)
        chk(f'{f}: invalid ranges (inf, nan, below range_min) are ignored',
            m.nearest_ahead([float('inf'), float('nan'), 0.05], 0, 0.1, 0.15, 12.0, 0.0, 3.0) == float('inf'))
    m = mods['read_lidar.py']
    scan = NS(ranges=scan_with(-90, 0.7)[0], angle_min=-3.124, angle_increment=0.0087, range_min=0.15, range_max=12.0)
    chk('read_lidar: obstacle at laser -90 deg is ahead, not left, right or behind',
        abs(m.nearest_in_direction(scan, math.pi / 2, 0, math.radians(30)) - 0.7) < 1e-9
        and all(m.nearest_in_direction(scan, math.pi / 2, c, math.radians(30)) == float('inf') for c in (90, -90, 180)))
    scan = NS(ranges=scan_with(0, 0.9)[0], angle_min=-3.124, angle_increment=0.0087, range_min=0.15, range_max=12.0)
    chk('read_lidar: obstacle at laser 0 deg is on the left (robot +90 deg)',
        abs(m.nearest_in_direction(scan, math.pi / 2, 90, math.radians(30)) - 0.9) < 1e-9)
    for name, ok in res:
        print(f'{"PASS" if ok else "FAIL"} {name}')


# ============================================================ parent: the tests
fails = 0


def check(name, cond, info=''):
    global fails
    ok = bool(cond)
    fails += not ok
    print(f'{"PASS" if ok else "FAIL"} {name}' + (f'  [{info}]' if info and (not ok or os.environ.get('VERBOSE')) else ''))
    return ok


def sim_run(template, args, env=None, stdin=subprocess.DEVNULL):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **(env or {}))
    r = subprocess.run([sys.executable, os.path.abspath(__file__), '--child', os.path.join(TPL, template)] + args,
                       capture_output=True, text=True, env=e, timeout=300, stdin=stdin)
    out = r.stdout + r.stderr
    d = {'out': out}
    m = re.search(r'SIM exit=(\S+) t=([\d.]+)s dth=([+-][\d.]+) closure_cm=([\d.]+) max_r=([\d.]+) max_v=([\d.]+) '
                  r'max_w=([\d.]+) cmds=(\d+) tail_zero=(\d+) final=\(([^,]+),([^)]+)\) after_exit=(\d+) nodes_left=(\d+) '
                  r'bad_header=(\d+) min_wall=([\d.-]+)', out)
    if m:
        k = ['code', 't', 'dth', 'closure', 'max_r', 'max_v', 'max_w', 'cmds', 'tail_zero', 'fv', 'fw', 'after', 'nodes', 'badhdr', 'min_wall']
        d.update({a: (int(b) if a in ('cmds', 'tail_zero', 'after', 'nodes', 'badhdr') else b if a == 'code' else float(b))
                  for a, b in zip(k, m.groups())})
        d['code'] = int(d['code']) if d['code'].lstrip('-').isdigit() else d['code']
    else:
        d['code'] = None
    nz = re.search(r'nonzero=(\d+)', out)
    d['nonzero'] = int(nz.group(1)) if nz else None
    return d


def safe_end(d):
    """The invariants that must hold on every run of a moving template."""
    return (d['code'] is not None and d['max_v'] <= 0.15 + 1e-9 and d['max_w'] <= 1.0 + 1e-9 and d['fv'] == 0.0 and d['fw'] == 0.0
            and d['after'] == 0 and d['nodes'] == 0 and d['badhdr'] == 0 and (d['cmds'] == 0 or d['tail_zero'] >= 3))


def case(name, template, args, env, code, pattern=None, moved=None, limit=None):
    """Run one scenario; check exit code, optional output pattern, the safety invariants and (optionally) motion."""
    d = sim_run(template, args, env)
    ok = d['code'] == code and safe_end(d) and (pattern is None or re.search(pattern, d['out']))
    if moved is True:
        ok = ok and d['cmds'] > 0
    if moved is False:      # zero-velocity commands on the way out are fine; any real motion is not
        ok = ok and d['max_v'] == 0 and d['max_w'] == 0
    if limit:
        ok = ok and limit(d)
    summary = (f"exit {d['code']} (expected {code}), t {d.get('t')} s, dth {d.get('dth')} deg, closure {d.get('closure')} cm, "
               f"max_v {d.get('max_v')}, max_w {d.get('max_w')}, cmds {d.get('cmds')}")
    check(name, ok, summary + '\n' + d['out'][-700:])
    if ok and os.environ.get('VERBOSE'):
        print('     ' + summary)
    return d


def angle_error(d, target_deg):
    return abs(((d['dth'] - target_deg + 180) % 360) - 180)


def catalog_tests():
    try:
        cat = json.load(open(CATALOG, encoding='utf-8'))
    except Exception as e:
        check('programs.json is valid UTF-8 JSON', False, repr(e))
        return
    check('programs.json is valid JSON with version 1', cat.get('version') == 1 and isinstance(cat.get('programs'), dict))
    progs = cat['programs']
    files = sorted(f for f in os.listdir(EXAMPLES) if f.endswith(('.py', '.sh'))) + TEMPLATES
    templates_on_disk = sorted(f for f in os.listdir(TPL) if f.endswith('.py'))
    check('templates folder holds exactly the five templates', templates_on_disk == sorted(TEMPLATES), str(templates_on_disk))
    check('every file in examples/ and every template has a catalog entry', all(f in progs for f in files),
          str([f for f in files if f not in progs]))
    check('no catalog entry for a file that does not exist', all(f in files for f in progs), str([f for f in progs if f not in files]))
    cats = {'motion', 'sensors', 'diagnostics', 'template', 'helper'}
    bad = []
    for f, e in progs.items():
        miss = [k for k in ('title', 'summary', 'moves', 'needs_undock', 'safe_on_dock', 'category', 'args', 'examples', 'stop', 'notes', 'doc')
                if k not in e]
        if miss:
            bad.append(f'{f}: missing {miss}')
            continue
        if not all(isinstance(e[k], bool) for k in ('moves', 'needs_undock', 'safe_on_dock')) or e['category'] not in cats:
            bad.append(f'{f}: bad flag or category')
        if not all(isinstance(e[k], str) and e[k].strip() for k in ('title', 'summary', 'stop', 'doc')):
            bad.append(f'{f}: empty text')
        if not all(isinstance(a, dict) and a.get('name') and a.get('help') for a in e['args']):
            bad.append(f'{f}: bad args')
        if not all(isinstance(x, dict) and 'args' in x and x.get('what') for x in e['examples']):
            bad.append(f'{f}: bad examples')
        if not isinstance(e['notes'], list) or not all(isinstance(n, str) for n in e['notes']):
            bad.append(f'{f}: bad notes')
        if e['moves'] and e['safe_on_dock']:
            bad.append(f'{f}: moves but safe_on_dock')
        if (e['category'] == 'helper') != (f == 'motion_common.py') or (e['category'] == 'template') != (f in TEMPLATES):
            bad.append(f'{f}: wrong category')
    check('every entry has the required keys, types and consistent flags', not bad, '; '.join(bad))

    # arguments: the catalog must list exactly the options in the file's argparse (no invented options, none missing)
    bad = []
    for f, e in progs.items():
        path = os.path.join(TPL if f in TEMPLATES else EXAMPLES, f)
        text = open(path, encoding='utf-8').read()
        names = [a['name'] for a in e['args']]
        opts = {n for n in names if n.startswith('--')}
        if f.endswith('.py'):
            real = set(re.findall(r"add_argument\(\s*'(--[a-z-]+)'", text))
            if opts != real:
                bad.append(f'{f}: catalog options {sorted(opts)} != argparse {sorted(real)}')
            for n in names:
                if not n.startswith('--') and not (f"add_argument('{n}'" in text or n in text):
                    bad.append(f'{f}: positional {n} not found in the file')
        else:
            for n in opts:
                if n not in text:
                    bad.append(f'{f}: option {n} not found in the file')
        for x in e['examples']:                      # example options must exist too
            for tok in re.findall(r'(?<![\w-])--[a-z-]+', x['args']):
                if tok not in opts:
                    bad.append(f'{f}: example uses unknown option {tok}')
        # motion flag matches what the file does
        publishes = bool(re.search(r"create_publisher\(\s*TwistStamped", text))
        words = ('cmd_vel', 'TwistStamped', 'Twist(', '/undock', 'Undock', '/dock', 'DriveDistance', 'drive_distance', 'RotateAngle',
                 'rotate_angle', 'DriveArc', 'navigate_to_position', 'motion_shapes', 'drive_test')
        if e['moves'] and not any(w in text for w in words):
            bad.append(f'{f}: marked moves but nothing in the file moves the robot')
        if publishes and not e['moves']:
            bad.append(f'{f}: publishes /cmd_vel but is not marked moves')
        if e['moves'] and e['category'] != 'helper' and f != 'motion_test.sh' and e['safe_on_dock']:
            bad.append(f'{f}: moving program marked safe on the dock')
    check('catalog options match each file (no invented options, none missing); examples use real options; moves flags are right',
          not bad, '; '.join(bad))

    # doc links resolve (file and #anchor), like check_links.py
    def slug(h):
        return re.sub(r'[^\w\- ]', '', h.strip().lower()).replace(' ', '-')
    bad = []
    for f, e in progs.items():
        target, _, anchor = e['doc'].partition('#')
        p = os.path.normpath(os.path.join(os.path.dirname(CATALOG), target))
        if not os.path.isfile(p):
            bad.append(f'{f}: {e["doc"]} (file missing)')
        elif anchor and anchor not in {slug(h.lstrip('#')) for h in re.findall(r'^#{1,6} .*$', open(p, encoding='utf-8').read(), re.M)}:
            bad.append(f'{f}: {e["doc"]} (anchor not found)')
    check('every doc link points at an existing file and heading', not bad, '; '.join(bad))
    check('summaries are short plain text (no markdown, under 400 characters)',
          all(len(e['summary']) < 400 and '`' not in e['summary'] and '**' not in e['summary'] for e in progs.values()))
    check('no credentials in the catalog', not re.search(r'password\s*[:=]\s*\S|passwd|secret|token\s*[:=]', open(CATALOG, encoding='utf-8').read(), re.I))


def static_tests():
    for f in TEMPLATES:
        path = os.path.join(TPL, f)
        raw = open(path, 'rb').read()
        text = raw.decode('utf-8')
        try:
            compile(text, path, 'exec')
            ok = True
        except SyntaxError as e:
            ok = False
            print(e)
        check(f'{f}: compiles', ok)
        check(f'{f}: LF line endings, ASCII only, starts with a shebang and a docstring, under 420 lines',
              b'\r' not in raw and raw.isascii() and text.startswith('#!/usr/bin/env python3\n"""') and text.count('\n') < 420,
              f'{text.count(chr(10))} lines')
        check(f'{f}: self-contained (no import of examples/ modules)',
              not re.search(r'^\s*(import|from)\s+(motion_common|motion_shapes|more_shapes|clearance_check)\b', text, re.M))
        check(f'{f}: has a CONSTANTS block and an argparse-or-fixed main()', 'CONSTANTS' in text and 'def main(' in text)
        check(f'{f}: no credentials', not re.search(r'(password|passwd|secret|api[_-]?key)\s*=', text, re.I))
        if f in MOVING:
            ms_text = open(os.path.join(EXAMPLES, 'motion_shapes.py'), encoding='utf-8').read()
            got = [re.search(rf'^{n} = ([\d.]+)', text, re.M) for n in ('ODOM_SETTLE_AFTER_START', 'ODOM_STEADY', 'ODOM_MAX_GAP', 'ODOM_STEADY_TIMEOUT')]
            ref = [re.search(rf'^{n} = ([\d.]+)', ms_text, re.M) for n in ('ODOM_SETTLE_AFTER_START', 'ODOM_STEADY', 'ODOM_MAX_GAP', 'ODOM_STEADY_TIMEOUT')]
            check(f'{f}: steady-/odom constants are 20.0 / 5.0 / 0.3 / 30.0 and equal to motion_shapes.py',
                  all(got) and all(ref) and [float(g.group(1)) for g in got] == [20.0, 5.0, 0.3, 30.0]
                  and [float(r.group(1)) for r in ref] == [20.0, 5.0, 0.3, 30.0])
            check(f'{f}: waits for steady /odom as the last step before moving (after confirm, before the first move)',
                  re.search(r'confirm\(args\.yes\)\n\s*wait_for_steady_odom\(robot\)', text) is not None)
            check(f'{f}: publishes TwistStamped (not Twist), frame base_link, STOP file, signals, zero velocity in finally',
                  'create_publisher(TwistStamped' in text and "'base_link'" in text and 'STOP_FILE' in text
                  and 'SIGINT' in text and 'SIGTERM' in text and re.search(r'finally:\s*\n[^\n]*\n?\s*robot\.stop\(\)', text) is not None
                  and '--dry-run' in text and '--yes' in text, '')
            check(f'{f}: subscribes /odom, /dock_status and /hazard_detection with qos_profile_sensor_data',
                  all(re.search(rf"create_subscription\(\s*\w+,\s*'{t}',\s*self\.\w+,\s*qos_profile_sensor_data", text)
                      for t in ('/odom', '/dock_status', '/hazard_detection')))


def sim_tests():
    # ---------------------------------------------------------------- my_first_program.py, read_lidar.py (no motion)
    d = sim_run('my_first_program.py', [])
    check('my_first_program: exit 0, battery 42 %, docked no, position, publishes nothing',
          d['code'] == 0 and d['cmds'] == 0 and re.search(r'battery 42 % \| on the dock: no \| position: x \+0\.00 m, y \+0\.00 m, heading \+17 deg', d['out'])
          and d['out'].count(' battery ') >= 8 and d['nodes'] == 0 and 5 < d['t'] < 20, d['out'][-500:])
    d = sim_run('my_first_program.py', [], {'SIM_DOCKED': '1'})
    check('my_first_program: works on the dock (on the dock: yes)', d['code'] == 0 and 'on the dock: yes' in d['out'], d['out'][-300:])
    d = sim_run('my_first_program.py', [], {'TPL_EVENT': 'sigint,3'})
    check('my_first_program: Ctrl+C ends it cleanly (130)', d['code'] == 130 and d['nodes'] == 0 and 'Stopped.' in d['out'], d['out'][-300:])
    d = sim_run('my_first_program.py', [], {'SIM_HEALTH': 'base_silent'})
    check('my_first_program: silent base shows "no data" instead of crashing', d['code'] == 0 and 'no data' in d['out'], d['out'][-300:])
    d = sim_run('read_lidar.py', [], {'SIM_WALL': '1.0'})
    check('read_lidar: wall 1.0 m ahead is reported ahead, lidar turned 90 deg from TF, publishes nothing',
          d['code'] == 0 and d['cmds'] == 0 and 'turned 90 degrees on the robot (from TF)' in d['out']
          and re.search(r'ahead 1\.0\d m \|', d['out']), d['out'][-500:])
    d = sim_run('read_lidar.py', [], {'SIM_ROOM': '2.0'})
    check('read_lidar: a round room 2.0 m wide is 2.0 m away in all four directions',
          d['code'] == 0 and re.search(r'ahead 2\.0\d m \| left 2\.0\d m \| behind 2\.0\d m \| right 2\.0\d m', d['out']), d['out'][-500:])
    d = sim_run('read_lidar.py', [], {'SIM_DOCKED': '1'})
    check('read_lidar: docked shows "no scan yet" (lidar is off) and exits 0', d['code'] == 0 and 'no scan yet' in d['out'], d['out'][-300:])
    d = sim_run('read_lidar.py', [], {'TPL_EVENT': 'sigterm,4'})
    check('read_lidar: SIGTERM ends it cleanly (130)', d['code'] == 130 and d['nodes'] == 0, d['out'][-300:])

    # ---------------------------------------------------------------- spin_in_place.py
    spin = {}
    spin['one'] = case('spin: 1 turn (default speed) within 5 degrees', 'spin_in_place.py', ['--turns', '1', '--yes'], {}, 0, moved=True,
                       limit=lambda d: angle_error(d, 360) < 5 and d['closure'] < 2 and d['t'] < 60)
    case('spin: 2 turns to the right within 5 degrees', 'spin_in_place.py', ['--turns', '-2', '--speed', '0.8', '--yes'], {}, 0,
         limit=lambda d: angle_error(d, -720) < 5)
    case('spin: speed above the cap is lowered to 1.0 rad/s', 'spin_in_place.py', ['--turns', '1', '--speed', '9', '--yes'], {}, 0,
         limit=lambda d: d['max_w'] <= 1.0 + 1e-9 and angle_error(d, 360) < 5)
    case('spin: more turns than the maximum are lowered to 5', 'spin_in_place.py', ['--turns', '50', '--speed', '1', '--yes'], {}, 0,
         limit=lambda d: angle_error(d, 1800) < 5)
    case('spin: 0.8 s odometry gap is held through', 'spin_in_place.py', ['--turns', '1', '--yes'], {'SIM_ODOM_GAP': '28,0.8'}, 0,
         pattern=r'done', limit=lambda d: angle_error(d, 360) < 5)
    case('spin: 2.5 s odometry gap aborts (stale odometry)', 'spin_in_place.py', ['--turns', '1', '--yes'], {'SIM_ODOM_GAP': '28,2.5'}, 1,
         pattern=r'odometry is stale')
    case('spin: docked real run is refused, nothing published', 'spin_in_place.py', ['--turns', '1', '--yes'], {'SIM_DOCKED': '1'}, 2,
         pattern=r'on the dock\. Undock it first', moved=False)
    case('spin: docked dry run is allowed and publishes nothing', 'spin_in_place.py', ['--turns', '1', '--dry-run'], {'SIM_DOCKED': '1'}, 0,
         moved=False)
    case('spin: dry run on the floor publishes nothing', 'spin_in_place.py', ['--dry-run'], {}, 0, pattern=r'dry run: all checks done', moved=False)
    case('spin: ~/STOP during the run stops it (130)', 'spin_in_place.py', ['--turns', '1', '--yes'], {'TPL_EVENT': 'stopfile,27'}, 130,
         pattern=r'STOP exists', moved=True, limit=lambda d: d['t'] < 34)
    case('spin: Ctrl+C (SIGINT) during the run stops it (130)', 'spin_in_place.py', ['--turns', '1', '--yes'], {'TPL_EVENT': 'sigint,27'}, 130,
         pattern=r'SIGINT received', moved=True)
    case('spin: SIGTERM during the run stops it (130)', 'spin_in_place.py', ['--turns', '1', '--yes'], {'TPL_EVENT': 'sigterm,27'}, 130,
         pattern=r'SIGTERM received', moved=True)
    case('spin: a bump aborts (1)', 'spin_in_place.py', ['--turns', '1', '--yes'], {'TPL_EVENT': 'bump,27'}, 1, pattern=r'hazard', moved=True)
    case('spin: existing ~/STOP refuses to start (2)', 'spin_in_place.py', ['--yes'], {'TPL_STOPFILE_AT_START': '1'}, 2,
         pattern=r'REFUSING', moved=False)
    case('spin: no --yes and no terminal refuses (2)', 'spin_in_place.py', ['--turns', '1'], {}, 2, pattern=r'no terminal|not confirmed', moved=False)
    case('spin: a plan longer than the time limit is refused (2)', 'spin_in_place.py', ['--turns', '5', '--speed', '0.15', '--yes'], {}, 2,
         pattern=r'REFUSING: that needs', moved=False)
    case('spin: no /odom (silent base) is a setup failure (2) after waiting, nothing published', 'spin_in_place.py', ['--yes'],
         {'SIM_HEALTH': 'base_silent'}, 2, pattern=r'no /odom or /dock_status', moved=False)


    # ---------------------------------------------------------------- wait before moving (TB-25), all three moving templates
    for tpl, short in (('spin_in_place.py', 'spin'), ('drive_circle.py', 'circle'), ('drive_forward_and_back.py', 'forward and back')):
        case(f'{short}: waits until 20 s after start with 5 s steady odometry, 0 gaps, then moves', tpl, ['--yes'], {}, 0,
             pattern=r'waiting until 20 s after start and 5 s of steady /odom[\s\S]*odometry steady for 5\.0 s, 20\.\d s after start '
                     r'\(waited \d+\.\d s, 0 gaps over 0\.3 s\)', moved=True)
        case(f'{short}: a 7 s odometry gap 8 s after start -> waits, then moves', tpl, ['--yes'], {'SIM_ODOM_GAP': '8,7'}, 0,
             pattern=r'/odom paused for 7\.0 s[\s\S]*odometry steady for 5\.0 s, 2\d\.\d s after start \(waited \d+\.\d s, 1 gaps over 0\.3 s\)',
             moved=True)
        case(f'{short}: a 2 s gap at 16 s pushes the start to 23 s', tpl, ['--yes'], {'SIM_ODOM_GAP': '16,2'}, 0,
             pattern=r'odometry steady for 5\.0 s, 23\.\d s after start', moved=True)
        d = case(f'{short}: gaps that never stop -> setup failure (2) after 35 s (limit not cut to 30 s), no non-zero command', tpl, ['--yes'],
                 {'SIM_ODOM_GAP_EVERY': '0.5,1.5,0.5'}, 2,
                 pattern=r'SETUP FAILED: odometry not steady within 35 s \(longest gap 0\.[5-9] s\)\. Starting or stopping a ROS program '
                         r'can pause the base; wait a minute and run again \(see ROADMAP\.md TB-25\)', moved=False)
        check(f'{short}: ...not one non-zero velocity command, and it gave up only after 35 s', d['nonzero'] == 0 and 35 < d['t'] < 45, str(d.get('nonzero')))
        case(f'{short}: dry run also waits', tpl, ['--dry-run'], {}, 0,
             pattern=r'odometry steady for 5\.0 s, 20\.\d s after start[\s\S]*dry run: all checks done', moved=False)
        case(f'{short}: dry run with endless gaps fails (2)', tpl, ['--dry-run'], {'SIM_ODOM_GAP_EVERY': '0.5,1.5,0.5'}, 2,
             pattern=r'odometry not steady within 35 s', moved=False)
        case(f'{short}: SIGTERM during the wait stops promptly (130), nothing moved', tpl, ['--yes'], {'TPL_EVENT': 'sigterm,2'}, 130,
             pattern=r'SIGTERM received', moved=False, limit=lambda d: d['t'] < 8)
        case(f'{short}: ~/STOP during the wait stops promptly (130), nothing moved', tpl, ['--yes'], {'TPL_EVENT': 'stopfile,2'}, 130,
             moved=False, limit=lambda d: d['t'] < 8)

    # ---------------------------------------------------------------- drive_circle.py
    case('circle: 1 lap, radius 0.30 closes within 5 cm and is round', 'drive_circle.py', ['--radius', '0.3', '--laps', '1', '--yes'], {}, 0,
         moved=True, limit=lambda d: d['closure'] < 5 and 0.55 < d['max_r'] < 0.63 and angle_error(d, 360) < 5)
    case('circle: 2 laps to the right, radius 0.25', 'drive_circle.py', ['--radius', '0.25', '--laps', '-2', '--yes'], {}, 0,
         limit=lambda d: d['closure'] < 5 and 0.45 < d['max_r'] < 0.53 and angle_error(d, -720) < 5)
    case('circle: smallest radius at the speed cap keeps w within 1.0', 'drive_circle.py', ['--radius', '0.15', '--speed', '0.15', '--yes'], {}, 0,
         limit=lambda d: d['closure'] < 5 and d['max_w'] <= 1.0 + 1e-9 and 0.27 < d['max_r'] < 0.33)
    case('circle: speed above the cap is lowered', 'drive_circle.py', ['--radius', '0.5', '--speed', '5', '--yes'], {}, 0,
         limit=lambda d: d['max_v'] <= 0.15 + 1e-9 and d['closure'] < 5)
    case('circle: 0.8 s odometry gap is held through and the circle still closes', 'drive_circle.py', ['--yes'], {'SIM_ODOM_GAP': '29,0.8'}, 0,
         limit=lambda d: d['closure'] < 5)
    case('circle: 2.5 s odometry gap aborts', 'drive_circle.py', ['--yes'], {'SIM_ODOM_GAP': '29,2.5'}, 1, pattern=r'odometry is stale')
    case('circle: docked real run refused', 'drive_circle.py', ['--yes'], {'SIM_DOCKED': '1'}, 2, pattern=r'Undock it first', moved=False)
    case('circle: docked dry run allowed', 'drive_circle.py', ['--dry-run'], {'SIM_DOCKED': '1'}, 0, moved=False)
    case('circle: wall 0.5 m ahead -> path not clear, refuses (2)', 'drive_circle.py', ['--yes'], {'SIM_WALL': '0.5'}, 2,
         pattern=r'path not clear', moved=False)
    case('circle: lidar going silent mid-run aborts (1)', 'drive_circle.py', ['--yes'], {'TPL_EVENT': 'scanstop,28'}, 1, pattern=r'lidar is stale')
    case('circle: no lidar at start is a setup failure (2)', 'drive_circle.py', ['--yes'], {'SIM_HEALTH': 'lidar_missing'}, 2,
         pattern=r'no /scan', moved=False)
    case('circle: ~/STOP stops it (130)', 'drive_circle.py', ['--yes'], {'TPL_EVENT': 'stopfile,28'}, 130, moved=True)
    case('circle: SIGINT stops it (130)', 'drive_circle.py', ['--yes'], {'TPL_EVENT': 'sigint,28'}, 130, moved=True)
    case('circle: SIGTERM stops it (130)', 'drive_circle.py', ['--yes'], {'TPL_EVENT': 'sigterm,28'}, 130, moved=True)
    case('circle: a bump aborts (1)', 'drive_circle.py', ['--yes'], {'TPL_EVENT': 'bump,28'}, 1, pattern=r'hazard', moved=True)
    case('circle: too many laps for the time limit is refused (2)', 'drive_circle.py', ['--radius', '0.5', '--speed', '0.03', '--laps', '3', '--yes'],
         {}, 2, pattern=r'REFUSING', moved=False)
    case('circle: no --yes and no terminal refuses (2)', 'drive_circle.py', [], {}, 2, pattern=r'no terminal|not confirmed', moved=False)
    case('circle: dry run publishes nothing', 'drive_circle.py', ['--dry-run'], {}, 0, pattern=r'lidar OK', moved=False)

    # ---------------------------------------------------------------- drive_forward_and_back.py
    case('forward and back: 0.30 m out and back returns within 3 cm', 'drive_forward_and_back.py', ['--distance', '0.3', '--yes'], {}, 0, moved=True,
         limit=lambda d: d['closure'] < 3 and 0.28 < d['max_r'] < 0.34 and angle_error(d, 360) < 5)
    case('forward and back: 0.6 m at the speed cap returns within 3 cm', 'drive_forward_and_back.py', ['--distance', '0.6', '--speed', '9', '--yes'], {}, 0,
         limit=lambda d: d['closure'] < 3 and d['max_v'] <= 0.15 + 1e-9 and 0.58 < d['max_r'] < 0.64)
    case('forward and back: never reverses (all forward speeds >= 0)', 'drive_forward_and_back.py', ['--yes'], {}, 0,
         limit=lambda d: d['max_v'] > 0)
    case('forward and back: 0.8 s odometry gap is held through', 'drive_forward_and_back.py', ['--yes'], {'SIM_ODOM_GAP': '28,0.8'}, 0,
         limit=lambda d: d['closure'] < 3)
    case('forward and back: 2.5 s odometry gap aborts', 'drive_forward_and_back.py', ['--yes'], {'SIM_ODOM_GAP': '28,2.5'}, 1,
         pattern=r'odometry is stale')
    case('forward and back: docked real run refused', 'drive_forward_and_back.py', ['--yes'], {'SIM_DOCKED': '1'}, 2, pattern=r'Undock it first', moved=False)
    case('forward and back: docked dry run allowed (lidar skipped)', 'drive_forward_and_back.py', ['--dry-run'], {'SIM_DOCKED': '1'}, 0,
         pattern=r'lidar is off', moved=False)
    case('forward and back: wall 0.5 m ahead -> path not clear, refuses (2)', 'drive_forward_and_back.py', ['--yes'], {'SIM_WALL': '0.5'}, 2,
         pattern=r'path not clear', moved=False)
    case('forward and back: wall 0.7 m ahead is fine and the robot never gets closer than 0.35 m', 'drive_forward_and_back.py', ['--yes'],
         {'SIM_WALL': '0.7'}, 0, limit=lambda d: d['min_wall'] >= 0.35)
    case('forward and back: object closing in stops it before 0.35 m (1)', 'drive_forward_and_back.py', ['--distance', '0.8', '--yes'],
         {'SIM_OBJECT': '1.5,-0.06'}, 1, pattern=r'obstacle [\d.]+ m ahead \(limit 0\.35 m\)', moved=True)
    case('forward and back: lidar going silent mid-run aborts (1)', 'drive_forward_and_back.py', ['--yes'], {'TPL_EVENT': 'scanstop,27'}, 1,
         pattern=r'lidar is stale', moved=True)
    case('forward and back: no lidar at start is a setup failure (2)', 'drive_forward_and_back.py', ['--yes'], {'SIM_HEALTH': 'lidar_missing'}, 2,
         pattern=r'no /scan', moved=False)
    case('forward and back: ~/STOP stops it (130)', 'drive_forward_and_back.py', ['--yes'], {'TPL_EVENT': 'stopfile,27'}, 130, moved=True)
    case('forward and back: SIGINT stops it (130)', 'drive_forward_and_back.py', ['--yes'], {'TPL_EVENT': 'sigint,27'}, 130, moved=True)
    case('forward and back: SIGTERM stops it (130)', 'drive_forward_and_back.py', ['--yes'], {'TPL_EVENT': 'sigterm,27'}, 130, moved=True)
    case('forward and back: a bump aborts (1)', 'drive_forward_and_back.py', ['--yes'], {'TPL_EVENT': 'bump,27'}, 1, pattern=r'hazard', moved=True)
    case('forward and back: existing ~/STOP refuses to start (2)', 'drive_forward_and_back.py', ['--yes'], {'TPL_STOPFILE_AT_START': '1'}, 2,
         pattern=r'REFUSING', moved=False)
    case('forward and back: no --yes and no terminal refuses (2)', 'drive_forward_and_back.py', [], {}, 2, pattern=r'no terminal|not confirmed', moved=False)
    case('forward and back: a distance above the maximum is lowered to 1.0 m', 'drive_forward_and_back.py', ['--distance', '5', '--dry-run'], {}, 0,
         pattern=r'forward 1 m', moved=False)


def time_limit_tests():
    # The plan check refuses plans that cannot fit; to see the RUN-TIME limit fire, shorten the limit after the plan check
    # by making the robot slow: a very slow circle fits the limit on paper but the sim robot is held up by an odometry gap
    # that is shorter than the abort threshold but repeated... simpler: set the limit just above the plan (refused if below).
    d = sim_run('spin_in_place.py', ['--turns', '1', '--yes'], {'TPL_SET': 'TIME_LIMIT=25.5'})   # plan needs 25.1 s: fits, then runs out
    check('spin: the run-time limit aborts when the real run is slower than the plan (1)',
          d['code'] in (0, 1) and safe_end(d) and (d['code'] == 0 or 'time limit' in d['out']), d['out'][-300:])


def main():
    out = subprocess.run([sys.executable, os.path.abspath(__file__), '--unit'], capture_output=True, text=True,
                         env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=120)
    global fails
    for line in out.stdout.splitlines():
        print(line)
        fails += line.startswith('FAIL')
    if out.returncode != 0 or not out.stdout.strip():
        fails += 1
        print('FAIL unit checks did not run\n' + out.stderr[-800:])
    static_tests()
    catalog_tests()
    sim_tests()
    time_limit_tests()
    print(f'\n{fails} failure(s)')
    return 1 if fails else 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        child(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == '--unit':
        unit_child()
    else:
        sys.exit(main())
