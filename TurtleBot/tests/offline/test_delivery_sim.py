"""Offline tests of the delivery simulator (TurtleBot/delivery/sim). No ROS and no robot needed.

Checks: sim_map output plans with plan_route.py; the fake base's wall follower (pure part) and run_mapping.sh with its
embedded helper (bash -n, --dry-run guards, shift of the route spec into the SLAM frame, map sanity check); analyse_run gives PASS and FAIL on crafted logs; run_e2e.sh passes
`bash -n` and its --dry-run refuses domain 0 and a running mission; fake_base.py compiles, refuses to start without a
domain, and its pure kinematics, docking controller and ray cast work (numpy parts are skipped with a message when
numpy is missing); ci_check_params.py skips cleanly without ROS.
Usage (repo root): python TurtleBot/tests/offline/test_delivery_sim.py
"""
import json
import math
import os
import importlib.util
import py_compile
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
import yaml  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery'))
SIM = os.path.join(DELIVERY, 'sim')
sys.path.insert(0, SIM)
sys.path.insert(0, DELIVERY)
import analyse_run  # noqa: E402
import sim_map  # noqa: E402
import fake_base as fb  # noqa: E402
import delivery_core as core  # noqa: E402

TMP = tempfile.mkdtemp(prefix='tb4_delivery_sim_tests_')
fails = 0


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


def run(cmd, env=None, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, env=env, **kw)


# ---------------------------------------------------------------- sim_map + plan_route
src = os.path.join(TMP, 'src')
sim_map.write_all(src)
for name in ('route_map.yaml', 'route_map.pgm', 'route_spec.yaml', 'sim_world.json'):
    check(f'sim_map writes {name}', os.path.isfile(os.path.join(src, name)))
out = os.path.join(TMP, 'route')
r = run([sys.executable, os.path.join(DELIVERY, 'tools', 'plan_route.py'), '--map', os.path.join(src, 'route_map.yaml'),
         '--spec', os.path.join(src, 'route_spec.yaml'), '--out', out])
check('plan_route.py plans the synthetic hall', r.returncode == 0, (r.stdout + r.stderr)[-200:])
route = None
if r.returncode == 0:
    route = core.load_route(os.path.join(out, 'route.yaml'))
    check('route.yaml is accepted by delivery_core.load_route', len(route.outbound) > 10 and len(route.inbound) > 10)
    check('route settings carry the sim timeouts', route.settings.pickup_timeout_s == 600)
    check('route outbound stays near the wall', all(0.3 <= p.y <= 0.7 for p in route.outbound), str([p.y for p in route.outbound][:3]))
    check('masks were written', all(os.path.isfile(os.path.join(out, f)) for f in
                                    ('keepout_mask.yaml', 'keepout_mask.pgm', 'speed_mask.yaml', 'speed_mask.pgm', 'map.yaml')))
w, h, pix = fb.read_pgm(os.path.join(src, 'route_map.pgm'))
check('map image is 1400 x 240 (70 m x 12 m at 5 cm)', (w, h) == (1400, 240), f'{w}x{h}')
r2 = run([sys.executable, os.path.join(SIM, 'sim_map.py'), '--out', os.path.join(TMP, 'short'), '--goal-x', '20',
          '--pickup-timeout', '25', '--leg-timeout', '90'])
spec = yaml.safe_load(open(os.path.join(TMP, 'short', 'route_spec.yaml')))
check('sim_map options reach the spec', r2.returncode == 0 and spec['goal']['x'] == 20.0
      and spec['settings']['pickup_timeout_s'] == 25 and spec['settings']['leg_timeout_s'] == 90)
check('sim_map rejects a goal outside the hall', run([sys.executable, os.path.join(SIM, 'sim_map.py'), '--out', TMP, '--goal-x', '90']).returncode == 2)

# ---------------------------------------------------------------- analyse_run on crafted logs
world = json.load(open(os.path.join(src, 'sim_world.json')))


def good_samples():
    out, t, x = [], 0.0, 2.2
    while x < 59.0:
        out.append({'t': round(t, 2), 'x': round(x, 3), 'y': 0.5, 'yaw': 0.0, 'speed': 0.15, 'wall': 0.5 - 0.025 + 0.025,
                    'mode': 'nav', 'docked': False, 'stuck': False})
        x += 0.15 * 0.2
        t += 0.2
    return out


def verdict(samples=None, events=None, code=0, expect=0, allow_short=False):
    res = analyse_run.analyse(samples if samples is not None else good_samples(), events or [], world, code, expect, allow_short)
    return res, {c['name']: c['status'] for c in res['checks']}


res, st = verdict()
check('analyse: a good run passes', res['passed'] and set(st.values()) == {'PASS'}, str(st))
res, st = verdict(code=3)
check('analyse: wrong exit code fails', not res['passed'] and st['mission exit code'] == 'FAIL')
res, st = verdict(code=4, expect=4)
check('analyse: expected non-zero exit passes', res['passed'])
s = good_samples()
s[100]['x'], s[100]['y'] = 31.0, -1.0
res, st = verdict(s)
check('analyse: entering the glass room fails', st['never entered the glass room'] == 'FAIL')
s = good_samples()
s[200]['wall'] = 0.12
res, st = verdict(s)
check('analyse: a close approach fails the clearance check', st['clearance to the wall'] == 'FAIL')
s = good_samples()
for q in s:
    q['wall'] = 0.9
res, st = verdict(s)
check('analyse: wrong median wall distance fails', st['median wall distance'] == 'FAIL')
s = good_samples()
s[50]['speed'] = 0.25
res, st = verdict(s)
check('analyse: speeding fails', st['max speed'] == 'FAIL')
res, st = verdict(events=[{'event': 'hazard', 'type': 'BUMP', 't': 5.0, 'x': 3.0, 'y': 0.2}])
check('analyse: a BUMP fails', st['no BUMP'] == 'FAIL')
res, st = verdict(s[:8], allow_short=True)
check('analyse: a short run skips the median check only with --allow-short', st['median wall distance'] == 'SKIP')
res, st = verdict(s[:8])
check('analyse: a short run fails without --allow-short', st['median wall distance'] == 'FAIL')
top = 'top - 10:00:01 up 1 day, load average: 1.50, 1.00, 0.80\n%Cpu(s): 40.0 us, 10.0 sy,  0.0 ni, 50.0 id,  0.0 wa\n' \
      'top - 10:00:31 up 1 day, load average: 2.50, 1.00, 0.80\n%Cpu(s): 60.0 us, 10.0 sy,  0.0 ni, 30.0 id,  0.0 wa\n'
cpu = analyse_run.parse_top(top)
check('analyse: top parsing', cpu['samples'] == 2 and cpu['cpu_mean'] == 60.0 and cpu['cpu_max'] == 70.0 and cpu['load1_max'] == 2.5, str(cpu))

# command line: files in, results.json out, exit codes
for label, mutate, want in (('PASS', None, 0), ('FAIL', 'bump', 1)):
    d = os.path.join(TMP, 'run_' + label)
    os.makedirs(d)
    with open(os.path.join(d, 'ground_truth.jsonl'), 'w') as fh:
        fh.write(json.dumps({'event': 'start', 't': 0.0}) + '\n')
        for q in good_samples():
            fh.write(json.dumps(q) + '\n')
        if mutate == 'bump':
            fh.write(json.dumps({'event': 'hazard', 'type': 'BUMP', 't': 9.0, 'x': 5, 'y': 0.2}) + '\n')
        fh.write('not json\n')
    shutil.copy(os.path.join(src, 'sim_world.json'), os.path.join(d, 'sim_world.json'))
    open(os.path.join(d, 'mission_exit.txt'), 'w').write('0\n')
    open(os.path.join(d, 'top.log'), 'w').write(top)
    r = run([sys.executable, os.path.join(SIM, 'analyse_run.py'), '--run-dir', d])
    results = json.load(open(os.path.join(d, 'results.json'))) if os.path.isfile(os.path.join(d, 'results.json')) else {}
    check(f'analyse_run.py command line {label}', r.returncode == want and f'RESULT: {label}' in r.stdout
          and results.get('passed') == (want == 0) and results.get('pi_cpu', {}).get('cpu_max') == 70.0, r.stdout[-200:] + r.stderr[-200:])
check('analyse_run.py reports missing inputs', run([sys.executable, os.path.join(SIM, 'analyse_run.py'), '--run-dir', TMP]).returncode == 2)

# ---------------------------------------------------------------- fake_base: no ROS needed for import, domain guard
check('fake_base imports without rclpy', 'rclpy' not in sys.modules)
py_compile.compile(os.path.join(SIM, 'fake_base.py'), cfile=os.path.join(TMP, 'fb.pyc'), doraise=True)
check('fake_base.py compiles', True)
check('domain guard: unset refused', fb.domain_problem({}) is not None)
check('domain guard: 0 refused', fb.domain_problem({'ROS_DOMAIN_ID': '0'}) is not None)
check('domain guard: empty refused', fb.domain_problem({'ROS_DOMAIN_ID': ' '}) is not None)
check('domain guard: text refused', fb.domain_problem({'ROS_DOMAIN_ID': 'x'}) is not None)
check('domain guard: 77 accepted', fb.domain_problem({'ROS_DOMAIN_ID': '77'}) is None)
check('run dir guard', fb.run_dir_ok('/tmp/x', '/home/u') and fb.run_dir_ok('/home/u/robot_code/logs/delivery/sim_1', '/home/u')
      and not fb.run_dir_ok('/home/u/robot_code/logs', '/home/u') and not fb.run_dir_ok('/etc', '/home/u')
      and not fb.run_dir_ok('/home/u/robot_code/logs/delivery/../../../x', '/home/u'))
base_cmd = [sys.executable, os.path.join(SIM, 'fake_base.py'), '--map', os.path.join(src, 'route_map.yaml'), '--run-dir', TMP]
env = {k: v for k, v in os.environ.items() if k != 'ROS_DOMAIN_ID'}
r = run(base_cmd, env=env)
check('fake_base.py refuses to start without ROS_DOMAIN_ID', r.returncode == 2 and 'REFUSING' in r.stderr, r.stderr[-150:])
env['ROS_DOMAIN_ID'] = '0'
r = run(base_cmd, env=env)
check('fake_base.py refuses to start in domain 0', r.returncode == 2 and 'REFUSING' in r.stderr, r.stderr[-150:])
env['ROS_DOMAIN_ID'] = '77'
r = run(base_cmd[:-1] + ['/etc/not_allowed'], env=env)
check('fake_base.py refuses a run folder outside the safe roots', r.returncode == 2 and 'REFUSING' in r.stderr, r.stderr[-150:])
for bad in (['--press', 'pickup:9'], ['--stall', 'x'], ['--glass', '1,2,3']):
    r = run(base_cmd + bad, env=dict(env, FAKE_BASE_ANY_DIR='1'))
    check(f'fake_base.py rejects {bad}', r.returncode == 2 and 'bad argument' in r.stderr, r.stderr[-150:])

# ---------------------------------------------------------------- fake_base: pure functions
check('parse_press', fb.parse_press('pickup:3,handoff:4') == {'pickup': 3, 'handoff': 4} and fb.parse_press('') == {}
      and fb.parse_press('pickup:3') == {'pickup': 3})
try:
    fb.parse_press('lunch:3')
    check('parse_press rejects unknown names', False)
except ValueError:
    check('parse_press rejects unknown names', True)
check('parse_stall', fb.parse_stall('25,5') == (25.0, 5.0) and fb.parse_stall(None) is None)
check('parse_segments text', fb.parse_segments('1,2,3,4; 5,6,7,8') == [[1, 2, 3, 4], [5, 6, 7, 8]])
check('parse_segments file', len(fb.parse_segments('@' + os.path.join(src, 'sim_world.json'))) == 4)
check('match_prompt', fb.match_prompt('Food placed?\nPress button 3') == 'pickup'
      and fb.match_prompt('Your food is here\nTake it, press 4') == 'handoff' and fb.match_prompt('Paused') is None)
check('match_prompt: the menu-style prompts of the mission, as the robot receives them (display_wire)',
      fb.match_prompt(core.display_wire(core.PICKUP_TEXT)) == 'pickup'
      and fb.match_prompt(core.display_wire(core.HANDOFF_TEXT)) == 'handoff'
      and fb.match_prompt(core.display_wire('Going to the lab\n2 = Stop')) is None
      and fb.match_prompt(core.display_wire('Starting\nplease wait\n2 = Stop')) is None)
check('clamp_cmd limits', fb.clamp_cmd(1.0, -5.0) == (fb.MAX_LIN, -fb.MAX_ANG) and fb.clamp_cmd(0.1, 0.2) == (0.1, 0.2))
check('wrap', abs(fb.wrap(3 * math.pi / 2) + math.pi / 2) < 1e-9 and abs(fb.wrap(-math.pi / 2) + math.pi / 2) < 1e-9)
check('slew', fb.slew(0.0, 1.0, 0.1) == 0.1 and fb.slew(0.5, 0.45, 0.1) == 0.45)
x, y, yaw = 0.0, 0.0, 0.0
for _ in range(250):
    x, y, yaw = fb.step_pose(x, y, yaw, 0.2, 0.0, 0.02)
check('step_pose straight line (0.2 m/s for 5 s)', abs(x - 1.0) < 1e-9 and abs(y) < 1e-9)
x, y, yaw = 0.0, 0.0, 0.0
for _ in range(int(2 * math.pi / 0.5 / 0.02)):   # one full circle: v=0.25, w=0.5 -> radius 0.5
    x, y, yaw = fb.step_pose(x, y, yaw, 0.25, 0.5, 0.02)
check('step_pose circle closes', math.hypot(x, y) < 0.02, f'({x:.3f}, {y:.3f})')
x, y, yaw, phase, t = 2.2, 0.5, math.pi, 'turn', 0.0
while phase != 'done' and t < 200:
    v, w, phase = fb.goto_step(x, y, yaw, 1.5, 0.5, 0.0, phase)
    x, y, yaw = fb.step_pose(x, y, yaw, v, w, 0.02)
    t += 0.02
check('docking controller reaches the dock pose', phase == 'done' and math.hypot(x - 1.5, y - 0.5) < 0.03
      and abs(fb.wrap(yaw)) < 0.05, f'phase {phase} at ({x:.2f}, {y:.2f}, {yaw:.2f}) after {t:.0f} s')

# ---------------------------------------------------------------- fake_base: grid and ray cast (numpy)
if fb.np is None:
    print('SKIP grid and ray cast tests: numpy is not installed')
else:
    np = fb.np
    scan = fb.Grid.load(os.path.join(src, 'route_map.yaml'))
    truth = scan.copy_with_segments(world['glass_segments'])
    check('grid: south wall is occupied, hall is free', scan.occupied_at(10.0, -0.05) and not scan.occupied_at(10.0, 0.5)
          and scan.occupied_at(10.0, 6.55))
    check('grid: glass room is a free pocket in the map, closed by glass in the ground truth',
          not scan.occupied_at(29.0, 0.0) and truth.occupied_at(29.0, 0.0) and not truth.occupied_at(30.7, 0.0))
    check('grid: door recess pocket is free in the map and blocked by glass in the truth',
          not scan.occupied_at(44.7, -0.4) and truth.occupied_at(44.7, -0.4) and not scan.occupied_at(44.7, -1.0))
    d_wall = truth.nearest_obstacle(10.0, 0.5)
    check('nearest obstacle on the straight wall is about 0.5 m', 0.45 <= d_wall <= 0.55, f'{d_wall:.3f}')
    check('nearest obstacle along the glass front is the glass (about 0.45 m)', 0.40 <= truth.nearest_obstacle(29.0, 0.5) <= 0.5)
    check('the lidar does not see that glass', scan.nearest_obstacle(31.0, 0.5, 2.0) > 1.9)
    check('a point on the glass counts as a collision', truth.nearest_obstacle(29.0, 0.1, 0.5) < fb.ROBOT_RADIUS)
    rngs = fb.raycast(scan, 10.0, 0.5, 0.0)
    check('raycast: 360 beams', rngs.shape == (360,))
    check('raycast: beam 90 (-90 deg) hits the south wall at about 0.5 m, beam 270 the north wall at about 6 m',
          abs(rngs[90] - 0.5) < 0.06 and abs(rngs[270] - 6.0) < 0.06, f'{rngs[90]:.3f} {rngs[270]:.3f}')
    check('raycast: nothing beyond 12 m is returned', bool(np.isinf(fb.raycast(scan, 10.0, 0.5, 0.0)[180])) or rngs[180] <= 12.0)
    # lidar mounting: robot at (60, 0.5) facing +x. Laser -90 deg (beam 90) is straight ahead -> east wall at x = 66.
    robot_yaw = 0.0
    laser = fb.raycast(scan, 60.0, 0.5, robot_yaw + fb.LASER_YAW)
    check('raycast with the +90 deg lidar mount: straight ahead is laser -90 deg (beam 90)', abs(laser[90] - 6.0) < 0.1, f'{laser[90]:.3f}')
    check('raycast with the +90 deg lidar mount: laser 0 deg (beam 180) looks to the robot\'s left (north wall)',
          abs(laser[180] - 6.0) < 0.06, f'{laser[180]:.3f}')
    # glass room: a ray from the hall into the room opening sees the room's back wall (4.5 m), not the glass
    into = fb.raycast(scan, 29.0, 0.5, -math.pi / 2)   # beam 180 points along yaw0, here south
    check('raycast sees through the glass room front to the back wall', abs(into[180] - 4.5) < 0.1, f'{into[180]:.3f}')
    import time as _t
    t0 = _t.time()
    for _ in range(20):
        fb.raycast(scan, 29.0, 0.5, 0.3)
    check('raycast is cheap (under 30 ms each on this computer)', (_t.time() - t0) / 20 < 0.03, f'{(_t.time() - t0) / 20 * 1000:.1f} ms')

# ---------------------------------------------------------------- ci_check_params without ROS
r = run([sys.executable, os.path.join(SIM, 'ci_check_params.py')])
if shutil.which('ros2'):
    print('SKIP ci_check_params SKIP test: ros2 is installed here')
else:
    check('ci_check_params.py skips cleanly without ROS', r.returncode == 0 and 'SKIP' in r.stdout, r.stdout[-200:] + r.stderr[-200:])
py_compile.compile(os.path.join(SIM, 'ci_check_params.py'), cfile=os.path.join(TMP, 'ci.pyc'), doraise=True)
for f in ('analyse_run.py', 'sim_map.py'):
    py_compile.compile(os.path.join(SIM, f), cfile=os.path.join(TMP, f + 'c'), doraise=True)
check('all sim python files compile', True)

# ---------------------------------------------------------------- run_e2e.sh
SH = os.path.join(SIM, 'run_e2e.sh')
raw = open(SH, 'rb').read()
check('run_e2e.sh has LF line endings', b'\r' not in raw)


def find_bash():
    """Git Bash on Windows, not System32\\bash.exe: that is WSL, and it cannot read a C:\\ path given like this."""
    if os.name == 'nt':
        for p in (r'C:\Program Files\Git\bin\bash.exe', r'C:\Program Files\Git\usr\bin\bash.exe'):
            if os.path.isfile(p):
                return p
    b = shutil.which('bash')
    return None if (b and 'system32' in b.lower()) else b


bash = find_bash()
if not bash:
    print('SKIP run_e2e.sh tests: bash is not installed')
else:
    r = run([bash, '-n', SH])
    check('run_e2e.sh passes bash -n', r.returncode == 0, r.stderr[-200:])
    fakebin = os.path.join(TMP, 'bin')
    os.makedirs(fakebin)
    home = os.path.join(TMP, 'home')
    os.makedirs(home)

    def fake_pgrep(match):
        path = os.path.join(fakebin, 'pgrep')
        with open(path, 'w', newline='\n') as fh:
            fh.write('#!/bin/sh\n' + (f'case "$*" in *{match}*) exit 0;; esac\n' if match else '') + 'exit 1\n')
        os.chmod(path, 0o755)

    def sh(*args, pgrep=None, **envextra):
        fake_pgrep(pgrep)
        e = dict(os.environ, HOME=home, PATH=fakebin + os.pathsep + os.environ['PATH'])
        e.pop('ROS_DOMAIN_ID', None)
        e.update(envextra)
        return run([bash, SH, *args], env=e)

    r = sh('happy', '--dry-run')
    check('run_e2e.sh --dry-run prints the plan with domain 77', r.returncode == 0 and 'ROS_DOMAIN_ID=77' in r.stdout
          and 'fake_base.py' in r.stdout and 'delivery_stack.launch.py' in r.stdout and 'delivery_mission.py' in r.stdout,
          (r.stdout + r.stderr)[-300:])
    check('run_e2e.sh --dry-run starts nothing and writes nothing', not os.path.exists(os.path.join(home, 'robot_code')))
    for sc, want in (('pickup_timeout', 'expected mission exit code 4'), ('stall', '--stall 25,5'), ('nav_fail', '--fail-after-pose 3')):
        r = sh(sc, '--dry-run')
        check(f'run_e2e.sh --dry-run {sc}', r.returncode == 0 and want in r.stdout, (r.stdout + r.stderr)[-200:])
    r = sh('happy', '--dry-run', SIM_DOMAIN='0')
    check('run_e2e.sh refuses domain 0', r.returncode != 0 and 'REFUSING' in r.stderr and 'domain 0' in r.stderr, r.stderr[-200:])
    r = sh('happy', '--dry-run', SIM_DOMAIN='abc')
    check('run_e2e.sh refuses a non-numeric domain', r.returncode != 0 and 'REFUSING' in r.stderr, r.stderr[-200:])
    r = sh('happy', '--dry-run', SIM_DOMAIN='00')
    check('run_e2e.sh refuses domain 00', r.returncode != 0 and 'REFUSING' in r.stderr, r.stderr[-200:])
    r = sh('happy', '--dry-run', pgrep='delivery_mission.py')
    check('run_e2e.sh refuses while a mission runs', r.returncode != 0 and 'REFUSING' in r.stderr and 'delivery_mission.py' in r.stderr, r.stderr[-200:])
    r = sh('happy', '--dry-run', pgrep='nav2.launch.py')
    check('run_e2e.sh refuses while a navigation stack runs', r.returncode != 0 and 'REFUSING' in r.stderr, r.stderr[-200:])
    open(os.path.join(home, 'STOP'), 'w').close()
    r = sh('happy', '--dry-run')
    check('run_e2e.sh refuses while ~/STOP exists', r.returncode != 0 and 'STOP' in r.stderr, r.stderr[-200:])
    os.remove(os.path.join(home, 'STOP'))
    check('run_e2e.sh rejects an unknown scenario', sh('bogus', '--dry-run').returncode != 0)
    check('run_e2e.sh needs a scenario', sh('--dry-run').returncode != 0)
    text = raw.decode()
    check('run_e2e.sh uses the same three launch commands as start_stack.sh',
          all(c in text for c in ('ros2 launch "$STACK_LAUNCH" map:=', 'keepout_mask:=', 'localization_params:=', 'nav2_params:=')))
    check('run_e2e.sh checks the domain before every start and after sourcing ROS',
          text.count('guard') >= 5 and 'verify_domain' in text and 'unset ROS_DISCOVERY_SERVER' in text)

# ---------------------------------------------------------------- fake_base: the /wall_follow action (pure part)
if fb.np is None:
    print('SKIP wall follower tests: numpy is not installed')
else:
    fsrc = open(os.path.join(SIM, 'fake_base.py'), encoding='utf-8').read()
    check('fake_base.py serves the /wall_follow action', "WallFollow, 'wall_follow'" in fsrc and 'def exec_wall_follow' in fsrc
          and "self.mode in ('nav', 'wall')" in fsrc)
    r = fb.wall_follow_cmd({'front': 0.3, 'diag': 0.5, 'side': 0.3}, -1)
    check('wall follower: a wall ahead stops and turns away from the wall (right wall: turn left)', r[0] == 0.0 and r[1] > 0, str(r))
    r = fb.wall_follow_cmd({'front': 0.3, 'diag': 0.5, 'side': 0.3}, 1)
    check('wall follower: a wall ahead with the wall on the left: turn right', r[0] == 0.0 and r[1] < 0, str(r))
    r = fb.wall_follow_cmd({'front': math.inf, 'diag': math.inf, 'side': math.inf}, -1)
    check('wall follower: no wall at all arcs towards the wall side (right: w < 0)', 0 < r[0] <= 0.15 and r[1] < 0 and not r[2], str(r))
    r = fb.wall_follow_cmd({'front': math.inf, 'diag': 0.3 * 1.4142, 'side': 0.3}, -1)
    check('wall follower: parallel at the target distance goes straight at 0.2 m/s', abs(r[1]) < 0.02 and abs(r[0] - 0.2) < 0.01 and r[2], str(r))
    check('wall follower: speed never above the cruise speed', all(fb.wall_follow_cmd({'front': f, 'diag': d, 'side': s}, sd)[0] <= fb.WF_SPEED + 1e-9
          for f in (0.3, 0.7, 5.0, math.inf) for d in (0.2, 1.0, math.inf) for s in (0.2, 0.6, math.inf) for sd in (-1, 1)))
    check('cast_rays hits the south wall at about 0.5 m', abs(fb.cast_rays(scan, 10.0, 0.5, [-math.pi / 2])[0] - 0.5) < 0.06
          and bool(np.isinf(fb.cast_rays(scan, 10.0, 0.5, [0.0], rmax=3.0)[0])))
    tr = fb.simulate_wall_follow(truth, 2.2, 0.3, 0.0, -1, 140, stop_x=24.0)
    dists = [row[4] for row in tr]
    check('wall follower keeps about 0.30 m from a straight wall (right side, 2 to 24 m)', 0.27 <= statistics.median(dists) <= 0.33 and min(dists) >= 0.25
          and abs(tr[-1][1] - 24.0) < 0.3, f'median {statistics.median(dists):.3f}, min {min(dists):.3f}, end x {tr[-1][1]:.2f}')
    speeds = [math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0]) for a, b in zip(tr, tr[1:])]
    check('wall follower drives at about 0.2 m/s and never faster than 0.21', 0.17 <= statistics.median(speeds) <= 0.21 and max(speeds) < 0.21,
          f'median {statistics.median(speeds):.3f}, max {max(speeds):.3f}')
    tr = fb.simulate_wall_follow(truth, 2.2, 0.55, 0.0, -1, 140, stop_x=24.0)
    check('wall follower closes a 0.25 m offset within 30 s', all(abs(row[4] - 0.3) < 0.04 for row in tr if row[0] > 30), str([round(row[4], 2) for row in tr[::500]]))
    tr = fb.simulate_wall_follow(truth, 26.0, 0.3, math.pi, 1, 140, stop_x=3.0)
    dists = [row[4] for row in tr]
    check('wall follower with the wall on the left, driving -x: same distance', 0.27 <= statistics.median(dists) <= 0.33 and min(dists) >= 0.25
          and abs(tr[-1][1] - 3.0) < 0.3, f'median {statistics.median(dists):.3f}, min {min(dists):.3f}, end x {tr[-1][1]:.2f}')
    tr = fb.simulate_wall_follow(truth, 38.0, 0.3, 0.0, -1, 120, stop_x=58.0)
    check('wall follower crosses the glass door recesses (0.4 m deep) without entering them or touching anything',
          min(row[2] for row in tr) > -0.2 and min(row[4] for row in tr) >= 0.25 and abs(tr[-1][1] - 58.0) < 0.3,
          f'min y {min(row[2] for row in tr):.2f}, min dist {min(row[4] for row in tr):.2f}')
    tr = fb.simulate_wall_follow(truth, 2.2, 0.3, 0.0, -1, 420, stop_x=40.0)
    inside = [row for row in tr if 28.0 < row[1] < 34.0 and row[2] < -1.0]
    check('wall follower TURNS INTO the opening: it enters the glass room through the doorway',
          len(inside) > 100 and min(row[4] for row in tr) >= fb.ROBOT_RADIUS and abs(tr[-1][1] - 40.0) < 0.3,
          f'{len(inside)} samples inside, min dist {min(row[4] for row in tr):.2f}, end x {tr[-1][1]:.1f}')
    tr = fb.simulate_wall_follow(scan, 2.2, 0.3, 0.0, -1, 420, stop_x=40.0)
    check('on the lidar map alone (glass invisible) it also turns into the pocket', any(row[2] < -1.0 and 28.0 < row[1] < 34.0 for row in tr))
    tr = fb.simulate_wall_follow(truth, 58.0, 0.3, 0.0, -1, 120)
    check('wall follower turns away from a wall ahead (the east wall) and follows it north',
          tr[-1][2] > 3.0 and min(row[4] for row in tr) >= 0.25 and max(row[1] for row in tr) < 66.0 - 0.25,
          f'end ({tr[-1][1]:.1f}, {tr[-1][2]:.1f}), min dist {min(row[4] for row in tr):.2f}')

# ---------------------------------------------------------------- run_mapping.sh and its embedded helper
MAP_SH = os.path.join(SIM, 'run_mapping.sh')
mraw = open(MAP_SH, 'rb').read()
mtext = mraw.decode()
check('run_mapping.sh has LF line endings', b'\r' not in mraw)
mm = re.search(r"<<'MAPPING_TOOLS_PY'\n(.*?)\nMAPPING_TOOLS_PY\n", mtext, re.S)
check('run_mapping.sh embeds the python helper', mm is not None)
tools_path = os.path.join(TMP, 'mapping_tools.py')
if mm and fb.np is not None:
    with open(tools_path, 'w', newline='\n', encoding='utf-8') as fh:
        fh.write(mm.group(1) + '\n')
    py_compile.compile(tools_path, cfile=os.path.join(TMP, 'mt.pyc'), doraise=True)
    check('the embedded helper compiles', True)
    os.environ['SIM_DIR'] = SIM
    helper_env = dict(os.environ, SIM_DIR=SIM)
    spec_ = importlib.util.spec_from_file_location('mapping_tools', tools_path)
    mt = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mt)
    check('helper imports without ROS', 'rclpy' not in sys.modules)
    room = world['glass_room']
    check('next_action: far from the room, wall-follow up to 2 m before it', mt.next_action(2.0, 1, 40.0, room) == ('follow', 26.0))
    check('next_action: at the trigger, cross to 1.5 m past the far edge', mt.next_action(26.1, 1, 40.0, room) == ('cross', 35.5))
    check('next_action: past the room, follow to the target', mt.next_action(35.6, 1, 40.0, room) == ('follow', 40.0))
    check('next_action: a target before the room needs no crossing', mt.next_action(2.0, 1, 25.0, room) == ('follow', 25.0))
    check('next_action: reached', mt.next_action(25.0, 1, 25.0, room)[0] == 'done')
    check('next_action: coming back (-x) crosses from 2 m east of the room to 1.5 m west of it',
          mt.next_action(40.0, -1, 2.3, room) == ('follow', 36.0) and mt.next_action(35.9, -1, 2.3, room) == ('cross', 26.5)
          and mt.next_action(26.4, -1, 2.3, room) == ('follow', 2.3))
    check('goal_problem refuses a goal in the room, accepts 25 and 40', mt.goal_problem(30.0, room) and not mt.goal_problem(25.0, room)
          and not mt.goal_problem(40.0, room))
    hall_spec = yaml.safe_load(open(os.path.join(src, 'route_spec.yaml')))
    shifted = mt.shift_spec(hall_spec, 1.5, 0.5)
    check('shift_spec: the dock becomes (0, 0, 0), the start 0.7 m ahead, the goal shifted',
          shifted['dock_pose'] == {'x': 0.0, 'y': 0.0, 'yaw': 0.0} and shifted['start'] == {'x': 0.7, 'y': 0.0}
          and shifted['goal']['x'] == 58.5 and shifted['goal']['y'] == 0.0, str(shifted['dock_pose']))
    names = [ln['name'] for ln in shifted['keepout_lines']]
    check('shift_spec: keepout lines over the glass room opening and both glass doors are kept and shifted',
          names == ['glass_room_opening', 'glass_door_1', 'glass_door_2'] and shifted['keepout_lines'][0]['from'] == [26.5, -0.5]
          and shifted['keepout_lines'][0]['to'] == [32.5, -0.5] and shifted['keepout_lines'][1]['from'] == [42.5, -0.5])
    check('shift_spec: slow zone and settings', shifted['slow_zones'][0]['points'][0] == [36.5, -0.5] and shifted['settings'] == hall_spec['settings'])
    try:
        mt.shift_spec(dict(hall_spec, dock_pose={'x': 1.5, 'y': 0.5, 'yaw': 30.0}), 1.5, 0.5)
        check('shift_spec refuses a rotated dock', False)
    except ValueError:
        check('shift_spec refuses a rotated dock', True)

    def slam_like_map(folder, goal_x, shift=0.0):
        """What slam_toolbox would save after the wall-follow drive: rays of the fake scan marked free/occupied, the
        frame origin at the dock (map origin = hall origin minus the dock pose). shift moves the origin to fake a wrong frame."""
        os.makedirs(folder, exist_ok=True)
        Wc, Hc = scan.W, scan.H
        known = np.full((Hc, Wc), 205, dtype=np.uint8)
        trj = fb.simulate_wall_follow(truth, 1.2, 0.3, 0.0, -1, 200, stop_x=goal_x)
        for _t, x_, y_, yaw_, _d in trj[::25]:
            lx, ly = x_ + fb.LASER_X * math.cos(yaw_), y_ + fb.LASER_X * math.sin(yaw_)
            rr = fb.raycast(scan, lx, ly, yaw_ + fb.LASER_YAW)
            for i, rv in enumerate(rr):
                ang = yaw_ + fb.LASER_YAW - math.pi + i * 2 * math.pi / 360
                end = rv if math.isfinite(rv) else fb.SCAN_RANGE_MAX
                for k in range(int(end / 0.05)):
                    c, r_ = scan.cell(lx + math.cos(ang) * k * 0.05, ly + math.sin(ang) * k * 0.05)
                    if 0 <= c < Wc and 0 <= r_ < Hc and known[r_, c] != 0:
                        known[r_, c] = 254
                if math.isfinite(rv):
                    c, r_ = scan.cell(lx + math.cos(ang) * rv, ly + math.sin(ang) * rv)
                    if 0 <= c < Wc and 0 <= r_ < Hc:
                        known[r_, c] = 0
        with open(os.path.join(folder, 'map.pgm'), 'wb') as fh:
            fh.write(f'P5\n{Wc} {Hc}\n255\n'.encode() + known.tobytes())
        with open(os.path.join(folder, 'map.yaml'), 'w', newline='\n') as fh:
            fh.write(f'image: map.pgm\nmode: trinary\nresolution: 0.05\norigin: [{-2.0 - 1.5 + shift}, {-5.0 - 0.5}, 0]\n'
                     'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
        return os.path.join(folder, 'map.yaml')

    src25 = os.path.join(TMP, 'short')   # sim_map.py --goal-x 20 above; make a goal-25 hall for the SLAM test
    sim_map.write_all(src25, 25.0)
    slam_yaml = slam_like_map(os.path.join(TMP, 'slam_ok'), 25.0)
    Wc, Hc, pix_ = fb.read_pgm(os.path.join(TMP, 'slam_ok', 'map.pgm'))
    probs, num = mt.map_report(Wc, Hc, 0.05, -3.5, -5.5, pix_, world, 25.0)
    check('map_report: a SLAM-like map of the wall-follow drive is sane', not probs and num['wall_fraction'] > 0.9, f'{probs} {num}')
    probs, num = mt.map_report(Wc, Hc, 0.05, -3.5, -5.5 + 0.6, pix_, world, 25.0)
    check('map_report: the same map in a frame shifted by 0.6 m in y is caught (south wall not where the dock frame says)',
          bool(probs) and 'dock-origin' in probs[0], f'{probs} {num}')
    # A SLAM frame follows the robot's start heading, so a straight wall may be tilted a little (seen on the Pi: 1.6 degrees).
    def wall_map(slope, at_dock, bend=0.0):
        W_, H_, res_, ox_, oy_ = 700, 120, 0.1, -10.0, -5.0
        g = bytearray([254]) * (W_ * H_)
        for i_ in range(350):
            x_ = 1.0 + i_ * 0.1
            y_ = at_dock + slope * x_ + (bend if x_ > 15.0 else 0.0)
            g[(H_ - 1 - int((y_ - oy_) / res_)) * W_ + int((x_ - ox_) / res_)] = 0
        return W_, H_, res_, ox_, oy_, bytes(g)
    w25 = dict(world, dock_pose={'x': 1.5, 'y': 0.5, 'yaw': 0.0}, glass_room=[28.0, -4.0, 34.0, 0.0], glass_segments=[])
    def wall_only(*a_):
        return [p_ for p_ in mt.map_report(*a_, w25, 25.0)[0] if 'wall' in p_]
    check('map_report: a straight wall tilted 1.6 degrees is sane and the tilt is measured',
          not wall_only(*wall_map(0.028, -0.5)) and abs(mt.map_report(*wall_map(0.028, -0.5), w25, 25.0)[1]['wall_tilt_deg'] - 1.6) < 0.2)
    check('map_report: a wall 0.6 m from where the dock frame says fails', bool(wall_only(*wall_map(0.0, 0.1))))
    check('map_report: a bent wall fails', bool(wall_only(*wall_map(0.0, -0.5, 0.8))))
    check('map_report: a wall tilted more than the limit fails', bool(wall_only(*wall_map(0.15, -0.5))))
    sp_ = mt.shift_spec({'dock_pose': {'x': 1.5, 'y': 0.5, 'yaw': 0.0}, 'goal': {'x': 11.5, 'y': 0.5, 'yaw': 0.0},
                         'keepout_lines': [{'from': [1.5, 0.5], 'to': [11.5, 0.5]}]}, 1.5, 0.5, 90.0)
    check('shift_spec: rotates points and yaws by the tilt, about the dock', abs(sp_['goal']['y'] - 10.0) < 1e-6
          and abs(sp_['goal']['x']) < 1e-6 and sp_['goal']['yaw'] == 90.0 and sp_['dock_pose']['yaw'] == 90.0
          and abs(sp_['keepout_lines'][0]['to'][1] - 10.0) < 1e-6)
    # Distances ALONG the wall: a real SLAM run on the Pi shrank the hall by 30 % and the wall check above did not see it.
    def hand_map(end_walls, room_x=None):
        """A 60 m x 12 m map at 0.1 m, origin (-10, -5); end_walls and room_x are x positions in the SLAM frame."""
        W_, H_, res_, ox_, oy_ = 700, 120, 0.1, -10.0, -5.0
        g = bytearray([254]) * (W_ * H_)
        def put(x_, y_):
            c_, r2 = int((x_ - ox_) / res_), H_ - 1 - int((y_ - oy_) / res_)
            if 0 <= c_ < W_ and 0 <= r2 < H_:
                g[r2 * W_ + c_] = 0
        for i_ in range(600):
            put(-1.5 + i_ * 0.1, -0.5)       # the south wall, where the dock-origin frame says
        for ex in end_walls:
            for j_ in range(-45, 60):
                put(ex, j_ * 0.1)
        if room_x is not None:
            for j_ in range(-45, -5):
                put(room_x, j_ * 0.1)
                put(room_x + 6.0, j_ * 0.1)
        return W_, H_, res_, ox_, oy_, bytes(g)
    w40 = dict(world, dock_pose={'x': 1.5, 'y': 0.5, 'yaw': 0.0}, glass_room=[28.0, -4.0, 34.0, 0.0])
    probs, num = mt.along_wall_report(*hand_map([-1.5], 26.5), w40, 40.0)
    check('along_wall_report: end wall and room in the right place pass', not probs and abs(num['end_wall_x'] + 1.5) < 0.2
          and abs(num['room_x'] - 26.5) < 0.2, f'{probs} {num}')
    probs, num = mt.along_wall_report(*hand_map([-6.0], 13.7), w40, 40.0)
    check('along_wall_report: the shrunken map from the real run fails (end wall and room both wrong)',
          len(probs) == 2 and 'end wall' in probs[0] and 'room' in probs[1], f'{probs} {num}')
    probs, num = mt.along_wall_report(*hand_map([-1.5, -0.6], 26.5), w40, 40.0)
    check('along_wall_report: a second (ghost) end wall fails', len(probs) == 1 and 'second' in probs[0], f'{probs} {num}')
    probs, num = mt.along_wall_report(*hand_map([-1.5], None), w40, 25.0)
    check('along_wall_report: a goal short of the room does not need the room in the map', not probs, f'{probs} {num}')
    probs, num = mt.along_wall_report(*hand_map([], None), w40, 25.0)
    check('along_wall_report: no end wall at all fails', len(probs) == 1 and 'no end wall' in probs[0], f'{probs} {num}')
    probs, num = mt.map_report(100, 100, 0.05, -2.0, -2.0, bytes([205]) * 10000, world, 25.0)
    check('map_report: an empty map fails (too small, no walls)', len(probs) >= 3, str(probs))
    r = run([sys.executable, tools_path, 'check-map', '--map', slam_yaml, '--world', os.path.join(src, 'sim_world.json'), '--goal-x', '25'], env=helper_env)
    check('check-map command line passes on it', r.returncode == 0 and 'SLAM map check: PASS' in r.stdout, r.stdout[-300:] + r.stderr[-300:])
    r = run([sys.executable, tools_path, 'make-spec', '--src', os.path.join(src25, 'route_spec.yaml'), '--world', os.path.join(src25, 'sim_world.json'),
             '--out', os.path.join(TMP, 'slam_spec.yaml')], env=helper_env)
    check('make-spec command line writes the shifted spec', r.returncode == 0 and os.path.isfile(os.path.join(TMP, 'slam_spec.yaml')), r.stderr[-200:])
    r = run([sys.executable, os.path.join(DELIVERY, 'tools', 'plan_route.py'), '--map', slam_yaml, '--spec', os.path.join(TMP, 'slam_spec.yaml'),
             '--out', os.path.join(TMP, 'slam_route')])
    check('plan_route.py plans on the SLAM-like map with the shifted spec', r.returncode == 0, (r.stdout + r.stderr)[-300:])
    if r.returncode == 0:
        sroute = core.load_route(os.path.join(TMP, 'slam_route', 'route.yaml'))
        ys = [p.y for p in sroute.outbound]
        check('the SLAM route runs along the wall in the dock frame (dock (0,0), y about 0, last waypoint near x 23.5)',
              all(-0.3 <= y <= 0.3 for y in ys) and abs(sroute.outbound[-1].x - 23.5) < 0.6 and abs(sroute.dock_pose.x) < 1e-9,
              f'y range {min(ys):.2f}..{max(ys):.2f}, last x {sroute.outbound[-1].x:.2f}')
        check('preview.html was written by plan_route.py', os.path.isfile(os.path.join(TMP, 'slam_route', 'preview.html')))
    ts = [{'t': i * 0.2, 'x': 5.0, 'y': 0.3, 'speed': 0.2} for i in range(10)]
    check('gt_report: clean drive', mt.gt_report(ts, [{'event': 'wall_follow_goal', 'started': True}], world)[0] == [])
    check('gt_report: a BUMP and the glass room fail', len(mt.gt_report(ts + [{'t': 9, 'x': 30.0, 'y': -2.0, 'speed': 0.1}],
          [{'event': 'hazard', 'type': 'BUMP', 'x': 1, 'y': 2}], world)[0]) == 2)
    for tool_cmd in ('drive', 'check-map', 'make-spec', 'check-gt'):
        check(f'helper subcommand {tool_cmd} exists', f"'{tool_cmd}'" in mm.group(1))
    r = run([sys.executable, '-m', 'ruff', '--version'])
    if r.returncode == 0:
        r = run([sys.executable, '-m', 'ruff', 'check', '--no-cache', '--extend-ignore', 'E501', '--config', os.path.join(DELIVERY, 'ruff.toml'), tools_path])
        check('the embedded helper passes ruff', r.returncode == 0, (r.stdout + r.stderr)[-300:])
    else:
        print('SKIP ruff on the embedded helper: ruff is not installed')
    r = run([sys.executable, tools_path, 'drive', '--world', os.path.join(src, 'sim_world.json'), '--goal-x', '25', '--out', os.path.join(TMP, 'x.json')],
            env={k: v for k, v in helper_env.items() if k != 'ROS_DOMAIN_ID'})
    check('the helper refuses to drive without ROS_DOMAIN_ID', r.returncode == 2 and 'REFUSING' in r.stderr, r.stderr[-200:])

if not bash:
    print('SKIP run_mapping.sh shell tests: bash is not installed')
else:
    r = run([bash, '-n', MAP_SH])
    check('run_mapping.sh passes bash -n', r.returncode == 0, r.stderr[-200:])
    shellcheck = shutil.which('shellcheck')
    if shellcheck:
        r = run([shellcheck, MAP_SH])
        check('run_mapping.sh passes shellcheck', r.returncode == 0, r.stdout[-300:])
    else:
        print('SKIP shellcheck: not installed')

    def msh(*args, pgrep=None, **envextra):
        fake_pgrep(pgrep)
        e = dict(os.environ, HOME=home, PATH=fakebin + os.pathsep + os.environ['PATH'])
        e.pop('ROS_DOMAIN_ID', None)
        e.update(envextra)
        return run([bash, MAP_SH, *args], env=e)

    r = msh('--dry-run')
    check('run_mapping.sh --dry-run prints the whole plan with domain 77',
          r.returncode == 0 and 'ROS_DOMAIN_ID=77' in r.stdout and all(k in r.stdout for k in (
              'sim_map.py', 'fake_base.py', 'slam.launch.py sync:=false', 'save_map.sh', 'plan_route.py', 'make-spec', 'check-map',
              'delivery_stack.launch.py', 'delivery_mission.py', 'analyse_run.py', 'preview.html', 'E2E mapping')), (r.stdout + r.stderr)[-400:])
    check('run_mapping.sh --dry-run starts nothing and writes nothing', not os.path.exists(os.path.join(home, 'robot_code')))
    r = msh('--dry-run', SIM_GOAL_X='40')
    check('run_mapping.sh SIM_GOAL_X reaches the plan (default 25)', '--goal-x 40' in r.stdout and '--goal-x 25' in msh('--dry-run').stdout, r.stdout[-200:])
    for bad in ('0', 'abc', '00'):
        r = msh('--dry-run', SIM_DOMAIN=bad)
        check(f'run_mapping.sh refuses SIM_DOMAIN={bad}', r.returncode != 0 and 'REFUSING' in r.stderr, r.stderr[-200:])
    for pat in ('delivery_mission.py', 'slam.launch.py', 'nav2.launch.py', 'fake_base.py'):
        r = msh('--dry-run', pgrep=pat)
        check(f'run_mapping.sh refuses while {pat} runs', r.returncode != 0 and 'REFUSING' in r.stderr and pat in r.stderr, r.stderr[-200:])
    open(os.path.join(home, 'STOP'), 'w').close()
    r = msh('--dry-run')
    check('run_mapping.sh refuses while ~/STOP exists', r.returncode != 0 and 'STOP' in r.stderr, r.stderr[-200:])
    os.remove(os.path.join(home, 'STOP'))
    check('run_mapping.sh rejects an unknown argument', msh('bogus', '--dry-run').returncode != 0)
    check('run_mapping.sh checks the domain before every start and after sourcing ROS',
          mtext.count('guard') >= 6 and 'verify_domain' in mtext and 'unset ROS_DISCOVERY_SERVER' in mtext and 'setsid nohup' in mtext)
    check('run_mapping.sh starts slam exactly as start_stack.sh map and uses the real save_map.sh',
          'ros2 launch turtlebot4_navigation slam.launch.py sync:=false' in mtext and 'robot/save_map.sh' in mtext
          and 'ros2 launch turtlebot4_navigation slam.launch.py sync:=false' in open(os.path.join(DELIVERY, 'robot', 'start_stack.sh')).read())
    check('the mapping helper initialises rclpy before it creates its node',
          0 < mtext.find('rclpy.init()') < mtext.find('node = Driver()'))
    check('the crossing drives forward on both legs (on the way back the robot has turned round, a negative speed reverses)',
          'publish(CROSS_SPEED,' in mtext and 'publish(d * CROSS_SPEED' not in mtext)
    check('run_mapping.sh uses the stack launch like run_e2e.sh',
          all(c in mtext for c in ('ros2 launch "$STACK_LAUNCH" map:=', 'keepout_mask:=', 'localization_params:=', 'nav2_params:=')))
    check('run_mapping.sh stops on the ~/STOP file, Ctrl+C and SIGTERM, and prints a PASS or FAIL last line',
          '$HOME/STOP' in mtext and "trap 'echo \"interrupted\"" in mtext and 'E2E mapping: PASS' in mtext and 'E2E mapping: FAIL' in mtext)

shutil.rmtree(TMP, ignore_errors=True)
print('\nFAILED: %d' % fails if fails else '\nALL PASSED')
sys.exit(1 if fails else 0)
