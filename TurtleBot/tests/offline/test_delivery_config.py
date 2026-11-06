"""Offline tests of the delivery configuration and robot shell scripts (TurtleBot/delivery).

No robot and no ROS needed. Checks:
  - config/nav2_delivery.yaml parses and differs from the upstream copy only in the intended keys;
  - costmap filter lists, speed caps, inflation values;
  - launch/delivery_stack.launch.py compiles and contains the expected node names and parameters (text checks);
  - every .sh under delivery/ passes `bash -n`, has LF line endings, and runs with --dry-run in a temporary HOME with
    fake ros2/pgrep/... on the PATH; a few real runs with fakes (save_map, start_stack, refusals).
Needs PyYAML and bash (Git Bash on Windows, bash on Linux); the shell part is skipped with a message if bash is missing.
Usage (from the repo root): python TurtleBot/tests/offline/test_delivery_config.py
"""
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
import yaml  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery'))
NAV2 = os.path.join(DELIVERY, 'config', 'nav2_delivery.yaml')
UPSTREAM = os.path.join(DELIVERY, 'config', 'upstream', 'turtlebot4_nav2_jazzy.yaml')
LAUNCH = os.path.join(DELIVERY, 'launch', 'delivery_stack.launch.py')
TMP = tempfile.mkdtemp(prefix='tb4_delivery_tests_')
fails = 0


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


def posix(p):
    return p.replace('\\', '/')


# ---------------------------------------------------------------- yaml
def load(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def diff_paths(a, b, prefix=''):
    """Key paths where a and b differ. A key present on one side only is reported at its own level."""
    out = set()
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            p = prefix + '.' + str(k) if prefix else str(k)
            if k not in a or k not in b:
                out.add(p)
            else:
                out |= diff_paths(a[k], b[k], p)
    elif a != b:
        out.add(prefix)
    return out


up, dl = load(UPSTREAM), load(NAV2)
GC = 'global_costmap.global_costmap.ros__parameters.'
LC = 'local_costmap.local_costmap.ros__parameters.'
CS = 'controller_server.ros__parameters.'
VS = 'velocity_smoother.ros__parameters.'
EXPECTED = {
    GC + 'filters', GC + 'keepout_filter', GC + 'speed_filter',
    GC + 'inflation_layer.cost_scaling_factor', GC + 'inflation_layer.inflation_radius',
    LC + 'filters', LC + 'keepout_filter',
    LC + 'inflation_layer.cost_scaling_factor', LC + 'inflation_layer.inflation_radius',
    'bt_navigator.ros__parameters.bt_loop_duration', 'bt_navigator.ros__parameters.default_server_timeout',
    CS + 'speed_limit_topic', CS + 'FollowPath', CS + 'controller_frequency',
    'collision_monitor.ros__parameters.transform_tolerance', 'collision_monitor.ros__parameters.source_timeout',
    GC + 'obstacle_layer.scan.topic', LC + 'voxel_layer.scan.topic',
    VS + 'max_velocity', VS + 'min_velocity', VS + 'max_accel', VS + 'max_decel',
}
got = {('controller_server.ros__parameters.FollowPath' if x.startswith(CS + 'FollowPath') else x) for x in diff_paths(up, dl)}
check('nav2_delivery.yaml differs from upstream only in the intended keys', got == EXPECTED,
      'extra=%s missing=%s' % (sorted(got - EXPECTED), sorted(EXPECTED - got)))

with open(UPSTREAM, encoding='utf-8') as f:
    head = ''.join([next(f) for _ in range(5)])
check('upstream copy header has source URL and date',
      'https://raw.githubusercontent.com/turtlebot/turtlebot4/jazzy/turtlebot4_navigation/config/nav2.yaml' in head
      and '2026-11-03' in head)
check('upstream copy has the known upstream values',
      up['controller_server']['ros__parameters']['FollowPath']['vx_max'] == 0.5
      and up[ 'velocity_smoother']['ros__parameters']['max_velocity'] == [0.26, 0.0, 1.0])

g = dl['global_costmap']['global_costmap']['ros__parameters']
lc = dl['local_costmap']['local_costmap']['ros__parameters']
check('global plugins unchanged', g['plugins'] == ['static_layer', 'obstacle_layer', 'inflation_layer'])
check('local plugins unchanged', lc['plugins'] == ['static_layer', 'voxel_layer', 'inflation_layer'])
check('global filters keepout then speed', g['filters'] == ['keepout_filter', 'speed_filter'])
check('local filters keepout only', lc['filters'] == ['keepout_filter'])
check('filters are not inside the plugins lists', 'keepout_filter' not in g['plugins'] + lc['plugins'])
for nm, c in (('global', g), ('local', lc)):
    k = c['keepout_filter']
    check(f'{nm} keepout filter params', k == {'plugin': 'nav2_costmap_2d::KeepoutFilter', 'enabled': True,
                                               'filter_info_topic': '/keepout_filter_info'}, str(k))
s = g['speed_filter']
check('global speed filter params', s['plugin'] == 'nav2_costmap_2d::SpeedFilter' and s['enabled'] is True
      and s['filter_info_topic'] == '/speed_filter_info' and s['speed_limit_topic'] == '/speed_limit', str(s))
check('controller speed_limit_topic', dl['controller_server']['ros__parameters']['speed_limit_topic'] == '/speed_limit')
for nm, c in (('global', g), ('local', lc)):
    il = c['inflation_layer']
    check(f'{nm} inflation 0.35 / 6.0', il['inflation_radius'] == 0.35 and il['cost_scaling_factor'] == 6.0)

fp = dl['controller_server']['ros__parameters']['FollowPath']
check('Regulated Pure Pursuit at the speed cap, no reversing', 'RegulatedPurePursuit' in fp['plugin'] and fp['desired_linear_vel'] == 0.20 and fp['allow_reversing'] is False)
vs = dl['velocity_smoother']['ros__parameters']
check('smoother max_velocity', vs['max_velocity'] == [0.20, 0.0, 0.8])
check('smoother min_velocity', vs['min_velocity'] == [-0.10, 0.0, -0.8])
check('smoother max_accel', vs['max_accel'] == [0.3, 0.0, 1.0])
check('smoother max_decel', vs['max_decel'] == [-0.5, 0.0, -1.5])
check('all speed caps within 0.15..0.20 m/s and 1.0 rad/s rules',
      max(fp['desired_linear_vel'], vs['max_velocity'][0]) <= 0.20 and max(fp['rotate_to_heading_angular_vel'], vs['max_velocity'][2]) <= 1.0)
with open(NAV2, encoding='utf-8') as f:
    ntext = f.read()
check('every change is marked with a "# delivery:" comment (at least 17 lines)', ntext.count('# delivery:') >= 17)
check('NOT VERIFIED note present for the speed filter parameter', 'NOT VERIFIED' in ntext)

# ---------------------------------------------------------------- launch file
try:
    py_compile.compile(LAUNCH, cfile=os.path.join(TMP, 'l.pyc'), doraise=True)
    check('delivery_stack.launch.py compiles', True)
except py_compile.PyCompileError as e:
    check('delivery_stack.launch.py compiles', False, str(e))
with open(LAUNCH, encoding='utf-8') as f:
    ltext = f.read()
for token in ['keepout_filter_mask_server', 'speed_filter_mask_server', 'keepout_costmap_filter_info_server',
              'speed_costmap_filter_info_server', 'lifecycle_manager_navigation', "'autostart': True",
              'component_container_isolated', 'bond_timeout', 'BOND_TIMEOUT = 0.0', 'nav2_amcl::AmclNode',
              '/keepout_filter_mask', '/speed_filter_mask', '/keepout_filter_info', '/speed_filter_info',
              'KEEPOUT_TYPE, KEEPOUT_BASE, KEEPOUT_MULTIPLIER = 0, 0.0, 1.0',
              'SPEED_TYPE, SPEED_BASE, SPEED_MULTIPLIER = 1, 100.0, -1.0',
              "'keepout_mask'", "'speed_mask'", "'use_sim_time'", 'CostmapFilterInfoServer', 'nav2_lifecycle_manager']:
    check('launch file contains ' + token, token in ltext)
check('launch filter-info topics match the yaml',
      g['keepout_filter']['filter_info_topic'] in ltext and s['filter_info_topic'] in ltext)

# ---------------------------------------------------------------- shell scripts
def find_bash():
    cands = []
    if os.name == 'nt':
        cands += [r'C:\Program Files\Git\bin\bash.exe', r'C:\Program Files (x86)\Git\bin\bash.exe']
    else:
        cands.append(shutil.which('bash') or '')
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


# ---------------------------------------------------------------- AMCL initial pose from the route
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('make_localization_params', os.path.join(DELIVERY, 'tools', 'make_localization_params.py'))
_mlp = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mlp)
_base = load(os.path.join(DELIVERY, 'config', 'localization_delivery.yaml'))
check('no use_sim_time true in our localization settings',
      all(v['ros__parameters'].get('use_sim_time') is False for v in _base.values()))
_p = _mlp.localization_params(_base, {'x': 1.5, 'y': 0.5, 'yaw': 90.0})['amcl']['ros__parameters']
check('dock pose becomes the AMCL initial pose',
      _p['set_initial_pose'] is True and _p['initial_pose']['x'] == 1.5 and _p['initial_pose']['y'] == 0.5
      and abs(_p['initial_pose']['yaw'] - 1.5707963) < 1e-6)

# The installed yaml files set use_sim_time true, which would make Nav2 wait for a /clock that does not exist.
for _name in sorted(os.listdir(os.path.join(DELIVERY, 'config'))):
    if _name.endswith('.yaml'):
        with open(os.path.join(DELIVERY, 'config', _name), encoding='utf-8') as _f:
            check('no simulated time in config/' + _name, 'use_sim_time: true' not in _f.read().lower())

BASH = find_bash()
scripts = []
for root, _dirs, files in os.walk(DELIVERY):
    for fn in files:
        if fn.endswith('.sh'):
            scripts.append(os.path.join(root, fn))
scripts.sort()
names = {os.path.basename(s) for s in scripts}
check('found the delivery shell scripts', {'p0_checks.sh', 'p0_soak.sh', 'save_map.sh', 'start_stack.sh', 'stop_stack.sh'} <= names, str(sorted(names)))
for sc in scripts:
    with open(sc, 'rb') as f:
        data = f.read()
    check('LF line endings: ' + os.path.basename(sc), b'\r' not in data and data.startswith(b'#!/bin/bash'))

if not BASH:
    print('SKIP shell tests: bash not available')
else:
    FAKE = os.path.join(TMP, 'fakebin')
    os.makedirs(FAKE)
    FAKES = {
        # pgrep: nothing running unless FAKE_PGREP_FOUND is set
        'pgrep': '#!/bin/bash\nif [ -n "$FAKE_PGREP_FOUND" ]; then echo 4242; exit 0; fi\nexit 1\n',
        'setsid': '#!/bin/bash\necho "$@" >> "$HOME/fake_setsid.log"\nexit 0\n',
        'ros2': r'''#!/bin/bash
echo "$@" >> "$HOME/fake_ros2.log"
case "$*" in
  *"--field header.stamp"*) echo "sec: $(date +%s)"; echo "nanosec: 0"; echo "---" ;;
  *"echo --once /dock_status"*) echo "is_docked: ${FAKE_DOCKED:-true}" ;;
  *"/battery_state"*) echo "percentage: 0.8"; echo "current: 1.2" ;;
  *"topic hz"*) echo "average rate: 7.50" ;;
  *"save_map"*|*"serialize_map"*)
     p="$(echo "$*" | sed -n "s/.*'\(.*\)'.*/\1/p")"
     case "$*" in *save_map*) touch "$p.pgm" "$p.yaml" ;; *) touch "$p.posegraph" "$p.data" ;; esac
     echo "response: Response(result=0)" ;;
esac
exit 0
''',
        'curl': '#!/bin/bash\necho 200\n',
    }
    for n, body in FAKES.items():
        p = os.path.join(FAKE, n)
        with open(p, 'w', newline='\n') as f:
            f.write(body)
        os.chmod(p, 0o755)

    def run_sh(script, args, env_extra=None, fresh_home=True, timeout=120):
        home = tempfile.mkdtemp(prefix='home_', dir=TMP)
        env = dict(os.environ)
        env['HOME'] = posix(home)
        env['PATH'] = posix(FAKE) + os.pathsep + env.get('PATH', '')
        env['DELIVERY_PAUSE'] = '0'
        env.pop('FAKE_PGREP_FOUND', None)
        env.update(env_extra or {})
        r = subprocess.run([BASH, posix(script)] + args, env=env, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        return r, home

    def S(name):
        return [s for s in scripts if s.endswith(name)][0]

    for sc in scripts:
        r = subprocess.run([BASH, '-n', posix(sc)], capture_output=True, text=True)
        check('bash -n ' + os.path.basename(sc), r.returncode == 0, r.stderr.strip())

    route = os.path.join(TMP, 'route')
    os.makedirs(route)
    for fn in ('map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml', 'route.yaml'):
        open(os.path.join(route, fn), 'w').close()

    # --- dry runs (must start nothing and create no files under HOME)
    r, home = run_sh(S('start_stack.sh'), ['nav', '--route-dir', posix(route), '--dry-run'], {'DELIVERY_PAUSE': '20'})
    o = r.stdout
    check('start_stack nav --dry-run rc 0', r.returncode == 0, r.stderr[-200:] + o[-200:])
    check('start_stack nav starts the one-process stack with AMCL settings from the route',
          'delivery_stack.launch.py' in o and 'make_localization_params.py' in o and 'localization_params:=' in o
          and 'nav2.launch.py' not in o)
    check('start_stack nav uses script-relative nav2_delivery.yaml and masks',
          'nav2_params:=' in o and 'config/nav2_delivery.yaml' in o and 'keepout_mask.yaml' in o
          and 'speed_mask.yaml' in o and 'map:=' in o)
    check('start_stack nav uses setsid nohup', 'setsid nohup' in o)
    check('start_stack prints TB-25 reminder', 'TB-25' in o)
    check('dry run created nothing under HOME', os.listdir(home) == [], str(os.listdir(home)))
    r, _ = run_sh(S('start_stack.sh'), ['map', '--dry-run'])
    check('start_stack map --dry-run: slam sync:=false, no nav2',
          r.returncode == 0 and 'slam.launch.py sync:=false' in r.stdout and 'nav2.launch.py' not in r.stdout)
    r, _ = run_sh(S('start_stack.sh'), ['map', '--with-nav2', '--dry-run'])
    check('start_stack map --with-nav2 starts nav2 with upstream params',
          'nav2.launch.py' in r.stdout and 'nav2_delivery.yaml' not in r.stdout)
    r, _ = run_sh(S('start_stack.sh'), ['nav', '--dry-run'])
    check('start_stack nav without --route-dir fails', r.returncode != 0)
    r, _ = run_sh(S('start_stack.sh'), ['nav', '--route-dir', posix(route), '--dry-run'], {'FAKE_PGREP_FOUND': '1'})
    check('start_stack refuses when a launch is running', r.returncode != 0 and 'already running' in r.stderr)

    r, home = run_sh(S('stop_stack.sh'), ['--dry-run'])
    check('stop_stack --dry-run rc 0 and lists leftovers check', r.returncode == 0 and 'Leftovers' in r.stdout)
    r, home = run_sh(S('stop_stack.sh'), ['--dry-run'], {'FAKE_PGREP_FOUND': '1'})
    o = r.stdout
    check('stop_stack order delivery stack, nav2, localization/slam',
          0 <= o.find('(delivery stack)') < o.find('(nav2)') < o.find('(localization/slam)') and 'kill -INT' in o, o[:300])

    pre = posix(os.path.join(TMP, 'maps', 'm1'))
    r, home = run_sh(S('save_map.sh'), [pre, '--dry-run'])
    o = r.stdout
    check('save_map --dry-run shows save_map, fallback and serialize_map',
          r.returncode == 0 and '/slam_toolbox/save_map slam_toolbox/srv/SaveMap' in o and 'map_saver_cli' in o
          and '/slam_toolbox/serialize_map' in o and os.listdir(home) == [])
    r, home = run_sh(S('save_map.sh'), [pre])
    check('save_map real run with fake ros2 writes map and pose graph',
          r.returncode == 0 and os.path.exists(pre + '.yaml') and os.path.exists(pre + '.posegraph'),
          r.stdout[-300:] + r.stderr[-200:])
    r, home = run_sh(S('save_map.sh'), [pre])
    check('save_map refuses to overwrite', r.returncode != 0 and 'exists' in r.stderr)
    r, home = run_sh(S('save_map.sh'), [])
    check('save_map without prefix fails', r.returncode != 0)

    r, home = run_sh(S('p0_checks.sh'), ['--interactive', '--dry-run'])
    o = r.stdout
    check('p0_checks --dry-run lists the A1..A9 commands',
          r.returncode == 0 and all(t in o for t in ['/dock_status', '/battery_state', 'logs-raw', 'timedatectl',
                                                     'nmcli', '802-11-wireless.powersave', 'vcgencmd', 'topic hz /scan', 'dpkg -l',
                                                     'ros2 bag', 'turtlebot4.yaml', '/hmi/buttons', '/hmi/display',
                                                     'bluetoothctl', '/joy', 'api.telegram.org'])
          and os.listdir(home) == [], r.stderr[-200:])
    r, home = run_sh(S('p0_checks.sh'), [])
    rep = [x for x in os.walk(home) for x in [os.path.join(x[0], f) for f in x[2]] if 'p0_checks_' in x]
    check('p0_checks real run with fakes writes a report and a summary',
          len(rep) == 1 and 'SUMMARY' in r.stdout and 'A1a PASS' in r.stdout and 'A1b PASS' in r.stdout
          and 'A7  SKIP' in r.stdout and 'A8a CHECK' in r.stdout, r.stdout[-400:] + r.stderr[-200:])

    r, home = run_sh(S('p0_soak.sh'), ['--baseline', '1', '--soak', '25', '--dry-run'])
    o = r.stdout
    check('p0_soak --dry-run prints the whole timeline',
          r.returncode == 0 and 'record_timing.py --light --duration 1860' in o
          and 0 <= o.find('start recorder') < o.find('start the navigation stack') < o.find('stop the navigation stack')
          and 'snapshot: 20 min' in o and 'T+00:01:00 start recorder' in o and 'wait 60 s' in o
          and os.listdir(home) == [], o[-300:] + r.stderr[-200:])
    rec = os.path.join(TMP, 'record_timing.py')
    open(rec, 'w').write('print("fake recorder")\n')
    r, home = run_sh(S('p0_soak.sh'), ['--recorder', posix(rec)], {'FAKE_DOCKED': 'false'})
    check('p0_soak refuses when not docked', r.returncode != 0 and 'Refusing' in r.stderr, r.stderr[-200:])
    r, home = run_sh(S('p0_soak.sh'), ['--recorder', posix(os.path.join(TMP, 'nope.py'))])
    check('p0_soak refuses without the recorder', r.returncode != 0 and 'recorder not found' in r.stderr)
    r, home = run_sh(S('p0_soak.sh'), ['--recorder', posix(rec), '--soak', 'x'])
    check('p0_soak rejects a bad --soak', r.returncode != 0)

shutil.rmtree(TMP, ignore_errors=True)
print()
print('FAILED: %d' % fails if fails else 'ALL PASSED')
sys.exit(1 if fails else 0)
