#!/usr/bin/env python3
"""Check on the REAL Nav2 that (1) the keepout and speed masks written by tools/plan_route.py are read back by the real
map_server with the intended values, and (2) every server in config/nav2_delivery.yaml accepts its parameters
(each is started alone, given the params file and configured; that declares the parameters and loads the plugins).
Used by the `ros:jazzy` CI job and runnable on the robot. It moves nothing and publishes no velocity.

    python3 ci_check_params.py [--only masks|params] [--keep]

SAFETY: it starts ROS nodes, so it refuses to run when ROS_DOMAIN_ID is unset or 0 (the real robot's domain), and it
forces local-only discovery. On the robot run it under the simulator domain, for example
    source /etc/turtlebot4/setup.bash; export ROS_DOMAIN_ID=77
It writes only into a temporary folder (removed unless --keep).
If ROS 2 is not installed it prints SKIP and exits 0. Exit codes: 0 all fine or skipped, 1 a check failed, 2 refused.
"""
import argparse
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.normpath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
NAV2_PARAMS = os.path.join(DELIVERY, 'config', 'nav2_delivery.yaml')
TOLERANCE = 2            # mask values may differ by this much from the formula (older map_server rounding)
NODE_TIMEOUT = 40.0      # s per node to appear and configure
MASK_TIMEOUT = 20.0

# Nav2 server -> (package, executable). Costmaps run inside controller_server / planner_server.
LAUNCHERS = {
    'bt_navigator': ('nav2_bt_navigator', 'bt_navigator'),
    'controller_server': ('nav2_controller', 'controller_server'),
    'planner_server': ('nav2_planner', 'planner_server'),
    'smoother_server': ('nav2_smoother', 'smoother_server'),
    'behavior_server': ('nav2_behaviors', 'behavior_server'),
    'waypoint_follower': ('nav2_waypoint_follower', 'waypoint_follower'),
    'velocity_smoother': ('nav2_velocity_smoother', 'velocity_smoother'),
    'collision_monitor': ('nav2_collision_monitor', 'collision_monitor'),
    'docking_server': ('opennav_docking', 'opennav_docking'),
}
INSIDE_OTHERS = {'local_costmap', 'global_costmap'}

problems = []


def fail(msg):
    problems.append(msg)
    print('FAIL ' + msg, flush=True)


def ok(msg):
    print('PASS ' + msg, flush=True)


def domain_problem():
    raw = os.environ.get('ROS_DOMAIN_ID', '').strip()
    if not raw:
        return 'ROS_DOMAIN_ID is not set'
    try:
        value = int(raw)
    except ValueError:
        return f'ROS_DOMAIN_ID={raw!r} is not a number'
    return 'ROS_DOMAIN_ID is 0 (the real robot\'s domain)' if value == 0 else None


def mask_value(pixel, free_t=0.01, occ_t=0.99):
    """The value Nav2 map_io gives a mask pixel (scale mode, negate 0)."""
    occ = 1.0 - pixel / 255.0
    if occ >= occ_t:
        return 100
    if occ <= free_t:
        return 0
    return int(round((occ - free_t) / (occ_t - free_t) * 100.0))


def read_pgm(path):
    from fake_base import read_pgm as rp
    return rp(path)


def expected_cells(mask_yaml):
    """Expected OccupancyGrid data (row 0 at the bottom, as map_server publishes) from the mask PGM."""
    import yaml
    with open(mask_yaml, 'r', encoding='utf-8') as fh:
        info = yaml.safe_load(fh)
    img = os.path.join(os.path.dirname(mask_yaml), info['image'])
    w, h, pix = read_pgm(img)
    data = []
    for row in range(h - 1, -1, -1):
        data.extend(mask_value(p) for p in pix[row * w:(row + 1) * w])
    return w, h, float(info['resolution']), float(info['origin'][0]), float(info['origin'][1]), data


def cell_value(grid, x, y):
    """Value of the OccupancyGrid message `grid` at map position (x, y)."""
    res = grid.info.resolution
    c = int(math.floor((x - grid.info.origin.position.x) / res))
    r = int(math.floor((y - grid.info.origin.position.y) / res))
    return grid.data[r * grid.info.width + c]


class Procs:
    """Child processes in their own process groups; always stopped at the end."""

    def __init__(self):
        self.list = []

    def start(self, cmd, log_path):
        # the same guard as everywhere: a child must not start in domain 0
        if domain_problem():
            raise RuntimeError('domain guard: ' + domain_problem())
        fh = open(log_path, 'w')
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self.list.append((p, fh))
        return p

    def stop(self, p):
        for sig, wait in ((signal.SIGINT, 8), (signal.SIGTERM, 4), (signal.SIGKILL, 2)):
            if p.poll() is not None:
                return
            try:
                os.killpg(p.pid, sig)
            except ProcessLookupError:
                return
            end = time.time() + wait
            while p.poll() is None and time.time() < end:
                time.sleep(0.1)

    def stop_all(self):
        for p, fh in self.list:
            self.stop(p)
            fh.close()
        self.list = []


def lifecycle(node, name, transition, timeout=NODE_TIMEOUT):
    """Call ChangeState on /name/change_state. Returns True when the transition succeeded."""
    import rclpy
    from lifecycle_msgs.msg import Transition
    from lifecycle_msgs.srv import ChangeState
    cli = node.create_client(ChangeState, f'/{name}/change_state')
    if not cli.wait_for_service(timeout_sec=timeout):
        node.destroy_client(cli)
        return False
    req = ChangeState.Request()
    req.transition = Transition(id=transition)
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
    node.destroy_client(cli)
    return bool(fut.done() and fut.result() and fut.result().success)


def check_masks(node, procs, work):
    import rclpy
    from nav_msgs.msg import OccupancyGrid
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    import sim_map
    import yaml

    src = os.path.join(work, 'src')
    out = os.path.join(work, 'route')
    sim_map.write_all(src)
    r = subprocess.run([sys.executable, os.path.join(DELIVERY, 'tools', 'plan_route.py'), '--map',
                        os.path.join(src, 'route_map.yaml'), '--spec', os.path.join(src, 'route_spec.yaml'), '--out', out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail('plan_route.py failed on the synthetic hall: ' + (r.stdout + r.stderr)[-300:])
        return
    with open(os.path.join(out, 'route.yaml'), 'r', encoding='utf-8') as fh:
        route = yaml.safe_load(fh)
    lane = route['outbound'][len(route['outbound']) // 2]
    # (mask name, [(x, y, wanted value, what)])
    samples = {
        'keepout_mask': [(lane['x'], lane['y'], 0, 'on the preferred lane'), (31.0, 0.0, 100, 'glass room opening'),
                         (44.7, 0.0, 100, 'glass door 1'), (31.0, 5.5, 50, 'far from the lane')],
        'speed_mask': [(39.0, 0.7, 50, 'inside the 50 percent slow zone'), (15.0, 0.5, 0, 'full speed')],
    }
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    for i, (name, points) in enumerate(samples.items()):
        yaml_path = os.path.join(out, name + '.yaml')
        node_name = f'ci_mask_server_{i}'
        topic = f'/ci_{name}'
        procs.start(['ros2', 'run', 'nav2_map_server', 'map_server', '--ros-args', '-r', f'__node:={node_name}',
                     '-p', f'yaml_filename:={yaml_path}', '-p', f'topic_name:={topic}', '-p', 'frame_id:=map'],
                    os.path.join(work, node_name + '.log'))
        got = []
        sub = node.create_subscription(OccupancyGrid, topic, got.append, qos)
        if not lifecycle(node, node_name, 1):
            fail(f'{name}: map_server did not configure (see {work}/{node_name}.log)')
            node.destroy_subscription(sub)
            continue
        if not lifecycle(node, node_name, 3):
            fail(f'{name}: map_server did not activate')
            node.destroy_subscription(sub)
            continue
        end = time.time() + MASK_TIMEOUT
        while not got and time.time() < end:
            rclpy.spin_once(node, timeout_sec=0.2)
        node.destroy_subscription(sub)
        if not got:
            fail(f'{name}: no OccupancyGrid on {topic} within {MASK_TIMEOUT:.0f} s')
            continue
        grid = got[0]
        w, h, res, ox, oy, data = expected_cells(yaml_path)
        if (grid.info.width, grid.info.height) != (w, h) or abs(grid.info.resolution - res) > 1e-6:
            fail(f'{name}: size/resolution {grid.info.width}x{grid.info.height} @ {grid.info.resolution} differs from the '
                 f'mask file {w}x{h} @ {res}')
            continue
        if abs(grid.info.origin.position.x - ox) > 1e-6 or abs(grid.info.origin.position.y - oy) > 1e-6:
            fail(f'{name}: origin differs from the mask yaml')
        bad = [(k, a, b) for k, (a, b) in enumerate(zip(data, grid.data)) if abs(a - b) > TOLERANCE]
        if bad:
            k, a, b = bad[0]
            fail(f'{name}: {len(bad)} of {len(data)} cells differ from the encoding formula by more than {TOLERANCE}; '
                 f'first at index {k}: expected {a}, map_server gave {b}')
        else:
            ok(f'{name}: all {len(data)} cells match the encoding formula (+-{TOLERANCE})')
        for x, y, want, what in points:
            v = cell_value(grid, x, y)
            (ok if abs(v - want) <= TOLERANCE else fail)(f'{name} at ({x}, {y}) {what}: value {v}, wanted {want}')


def check_params(node, procs, work):
    import yaml
    with open(NAV2_PARAMS, 'r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh)
    for name, (pkg, exe) in LAUNCHERS.items():
        if name not in data:
            continue
        if subprocess.run(['ros2', 'pkg', 'prefix', pkg], capture_output=True).returncode != 0:
            print(f'note: package {pkg} is not installed here, {name} not checked')
            continue
        log = os.path.join(work, name + '.log')
        p = procs.start(['ros2', 'run', pkg, exe, '--ros-args', '-r', f'__node:={name}', '--params-file', NAV2_PARAMS,
                         '-p', 'use_sim_time:=false'], log)
        configured = lifecycle(node, name, 1)
        if p.poll() is not None and not configured:
            fail(f'{name}: the node exited ({pkg}/{exe}); last log lines: {tail(log)}')
        elif not configured:
            fail(f'{name}: configure failed or timed out; last log lines: {tail(log)}')
        else:
            text = open(log, 'r', errors='replace').read()
            errs = [ln for ln in text.splitlines() if '[ERROR]' in ln or 'ParameterNotDeclared' in ln or 'not declared' in ln]
            if errs:
                fail(f'{name}: configured, but the log has errors: {errs[0][:200]}')
            else:
                ok(f'{name}: parameters declared and configure succeeded')
        procs.stop(p)
    unknown = [k for k, v in data.items() if isinstance(v, dict) and k not in LAUNCHERS and k not in INSIDE_OTHERS]
    if unknown:
        print('note: no launcher known for ' + ', '.join(unknown) + ' (not checked)')


def tail(path, n=3):
    try:
        lines = open(path, 'r', errors='replace').read().splitlines()
    except OSError:
        return '(no log)'
    return ' | '.join(ln.strip()[:160] for ln in lines[-n:])


def sim_time_check():
    """No ROS needed: nothing in our params may switch on simulated time."""
    import yaml

    def walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == 'use_sim_time' and v is True:
                    fail(f'{path}.use_sim_time is true (on the robot there is no /clock)')
                walk(v, f'{path}.{k}')
    with open(NAV2_PARAMS, 'r', encoding='utf-8') as fh:
        walk(yaml.safe_load(fh), 'nav2_delivery')
    if not any('use_sim_time' in p for p in problems):
        ok('no use_sim_time: true in config/nav2_delivery.yaml')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Check the delivery masks and Nav2 parameters on the real Nav2.')
    ap.add_argument('--only', choices=['masks', 'params'], help='run only one part')
    ap.add_argument('--keep', action='store_true', help='keep the temporary folder')
    a = ap.parse_args(argv)

    sim_time_check()
    import importlib.util
    have_ros = shutil.which('ros2') is not None and importlib.util.find_spec('rclpy') is not None
    if not have_ros:
        print('SKIP: ROS 2 is not available here (no rclpy or ros2); only the file checks ran')
        return 1 if problems else 0
    problem = domain_problem()
    if problem:
        print(f'REFUSING to start ROS nodes: {problem}. Set ROS_DOMAIN_ID to another number, for example 77.', file=sys.stderr)
        return 2
    os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    os.environ['ROS_LOCALHOST_ONLY'] = '1'
    os.environ.pop('ROS_DISCOVERY_SERVER', None)
    os.environ.pop('ROS_SUPER_CLIENT', None)
    os.environ.pop('FASTRTPS_DEFAULT_PROFILES_FILE', None)

    import rclpy
    work = tempfile.mkdtemp(prefix='tb4_ci_params_')
    os.environ['ROS_LOG_DIR'] = os.path.join(work, 'roslog')
    procs = Procs()
    rclpy.init()
    node = rclpy.create_node('ci_check_params')
    try:
        if a.only in (None, 'masks'):
            check_masks(node, procs, work)
            procs.stop_all()
        if a.only in (None, 'params'):
            check_params(node, procs, work)
    except Exception as e:   # noqa: BLE001
        fail(f'unexpected error: {type(e).__name__}: {e}')
    finally:
        procs.stop_all()
        node.destroy_node()
        rclpy.try_shutdown()
        if a.keep:
            print(f'kept {work}')
        else:
            shutil.rmtree(work, ignore_errors=True)
    print('RESULT: ' + ('FAIL (%d problems)' % len(problems) if problems else 'PASS'))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
