#!/usr/bin/env python3
"""Short supervised motion steps on the real robot, one program for one batch (TB-25: one new ROS participant).

THIS MOVES THE ROBOT. A person stays next to it with the controller (button B = emergency stop). Run it on the robot:

    source /etc/turtlebot4/setup.bash
    python3 motion_probe.py status undock status scan drive:0.25 status dock status

Steps, run in the order given; the first failed step stops the batch and no later step runs:
    status        odometry position, distance from where the program started, dock_visible, is_docked, battery
    scan          nearest lidar return in each of 8 sectors around the robot (needs the lidar spinning: undocked)
    undock        built-in Undock action
    dock          built-in Dock action
    drive:M       built-in DriveDistance action, M metres (negative = backwards), 0.15 m/s. Refused when a lidar return
                  lies in the robot's path (0.22 m each side, up to M + 0.30 m ahead); needs /scan
    turn:DEG      built-in RotateAngle action, degrees, positive = left
    wall:SIDE:S   built-in WallFollow action, SIDE = left or right, S seconds; logs the distance from the lidar centre
                  to the nearest return on that side during the run (minimum, mean, maximum)
    wait:S        wait S seconds
    face:dock     turn on the spot to face the point where the program started (use only when it started on the dock)

Every line is also written to the log file given with --log. It sends no /cmd_vel: the Create 3 actions keep their own
bump and cliff stops. Exit code 0 = every step succeeded, 1 = a step failed, 2 = setup failure.
"""
import argparse
import math
import sys
import time


def sector_name(angle):
    names = ['front', 'front-left', 'left', 'back-left', 'back', 'back-right', 'right', 'front-right']
    return names[int(((angle + math.pi / 8) % (2 * math.pi)) // (math.pi / 4))]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Short supervised motion steps (moves the robot).')
    parser.add_argument('steps', nargs='+')
    parser.add_argument('--log', default=None)
    args = parser.parse_args(argv)

    import rclpy
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from builtin_interfaces.msg import Duration
    from irobot_create_msgs.action import DriveDistance, Dock, RotateAngle, Undock, WallFollow
    from irobot_create_msgs.msg import DockStatus
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import BatteryState, LaserScan

    logfile = open(args.log, 'a') if args.log else None

    def say(text):
        line = f'{time.strftime("%H:%M:%S")} {text}'
        print(line, flush=True)
        if logfile:
            logfile.write(line + '\n')
            logfile.flush()

    rclpy.init()
    node = Node('motion_probe')
    state = {'odom': None, 'odom_t': None, 'start': None, 'gap': 0.0, 'dock': None, 'battery': None, 'scan': None}

    def on_odom(msg):
        now = time.monotonic()
        if state['odom_t'] is not None:
            state['gap'] = max(state['gap'], now - state['odom_t'])
        state['odom_t'] = now
        state['odom'] = msg.pose.pose
        if state['start'] is None:
            state['start'] = msg.pose.pose

    node.create_subscription(Odometry, '/odom', on_odom, qos_profile_sensor_data)
    node.create_subscription(DockStatus, '/dock_status', lambda m: state.__setitem__('dock', m),
                             qos_profile_sensor_data)
    node.create_subscription(BatteryState, '/battery_state', lambda m: state.__setitem__('battery', m.percentage),
                             qos_profile_sensor_data)
    wall = {'side': None, 'samples': []}

    def on_scan(msg):
        state['scan'] = (time.monotonic(), msg)
        if wall['side'] is not None:
            names = (('left', 'front-left', 'back-left') if wall['side'] == 'left'
                     else ('right', 'front-right', 'back-right'))
            best = nearest_by_sector(msg)
            values = [best[n] for n in names if n in best]
            if values:
                wall['samples'].append(min(values))

    node.create_subscription(LaserScan, '/scan', on_scan, qos_profile_sensor_data)
    clients = {'undock': ActionClient(node, Undock, '/undock'), 'dock': ActionClient(node, Dock, '/dock'),
               'drive': ActionClient(node, DriveDistance, '/drive_distance'),
               'turn': ActionClient(node, RotateAngle, '/rotate_angle'),
               'wall': ActionClient(node, WallFollow, '/wall_follow')}

    def spin_for(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)

    def yaw_of(q):
        return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))

    def from_start():
        return math.hypot(state['odom'].position.x - state['start'].position.x,
                          state['odom'].position.y - state['start'].position.y)

    def status():
        d = state['dock']
        spin_for(0.3)
        p = state['odom'].position
        say(f'status x={p.x:.3f} y={p.y:.3f} yaw={math.degrees(yaw_of(state["odom"].orientation)):.1f} deg '
            f'from_start={from_start():.3f} m docked={d.is_docked if d else "?"} '
            f'dock_visible={d.dock_visible if d else "?"} battery={(state["battery"] or 0) * 100:.0f} % '
            f'longest_odom_gap={state["gap"]:.3f} s')
        return True

    def fresh_scan(max_wait=20.0):
        end = time.monotonic() + max_wait
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
            if state['scan'] and time.monotonic() - state['scan'][0] < 0.5:
                return state['scan'][1]
        return None

    def nearest_by_sector(scan):
        # the RPLIDAR on this robot is mounted turned by 90 degrees: base_link angle = scan angle + 90 degrees is read
        # from the tf at run time by the stack; here the fixed mount of the TurtleBot 4 Standard is assumed
        best = {}
        for i, r in enumerate(scan.ranges):
            if not (scan.range_min < r < scan.range_max) or math.isinf(r) or math.isnan(r):
                continue
            name = sector_name(scan.angle_min + i * scan.angle_increment + math.pi / 2)
            best[name] = min(best.get(name, 99.0), r)
        return best

    def free_path(scan, sign):
        """Distance to the nearest lidar return inside the robot's path, ahead (sign 1) or behind (sign -1)."""
        free = 99.0
        for i, r in enumerate(scan.ranges):
            if not (scan.range_min < r < scan.range_max) or math.isinf(r) or math.isnan(r):
                continue
            a = scan.angle_min + i * scan.angle_increment + math.pi / 2
            x, y = r * math.cos(a) * sign, r * math.sin(a)
            if x > 0.05 and abs(y) < 0.22:   # a return beside or behind the centre is not in the way of this move
                free = min(free, x)
        return free

    def scan_step():
        scan = fresh_scan()
        if scan is None:
            say('scan: no fresh /scan (lidar off while docked?)')
            return False
        best = nearest_by_sector(scan)
        say('scan nearest: ' + ' '.join(f'{k}={v:.2f}' for k, v in sorted(best.items())) +
            f' free_ahead={free_path(scan, 1):.2f} free_behind={free_path(scan, -1):.2f}')
        return True

    def run_action(name, goal, timeout):
        client = clients[name]
        if not client.wait_for_server(timeout_sec=30.0):
            say(f'{name}: no action server after 30 s')
            return False
        before = time.monotonic()
        future = client.send_goal_async(goal)
        rclpy.spin_until_future_complete(node, future, timeout_sec=20.0)
        handle = future.result()
        if handle is None or not handle.accepted:
            say(f'{name}: goal refused or no answer')
            return False
        result = handle.get_result_async()
        rclpy.spin_until_future_complete(node, result, timeout_sec=timeout)
        took = time.monotonic() - before
        if not result.done():
            handle.cancel_goal_async()
            spin_for(1.0)
            say(f'{name}: no result after {timeout} s, cancelled')
            return False
        say(f'{name}: status {result.result().status} (4 = succeeded) in {took:.1f} s')
        ok = result.result().status == 4
        if name in ('dock', 'undock'):
            value = getattr(result.result().result, 'is_docked', None)
            say(f'{name}: is_docked in the result = {value}')
            ok = ok and value is (name == 'dock')
        return ok

    def drive_step(metres):
        scan = fresh_scan()
        if scan is None:
            say('drive: no /scan, refusing')
            return False
        free = free_path(scan, 1 if metres > 0 else -1)
        if free < abs(metres) + 0.30:
            say(f'drive: the path is free for {free:.2f} m only, refusing {metres} m')
            return False
        goal = DriveDistance.Goal(distance=metres, max_translation_speed=0.15)
        return run_action('drive', goal, abs(metres) / 0.15 + 30)

    def turn_step(deg):
        return run_action('turn', RotateAngle.Goal(angle=math.radians(deg), max_rotation_speed=0.6), abs(deg) / 30 + 30)

    def wall_step(side, seconds):
        goal = WallFollow.Goal(follow_side=1 if side == 'left' else -1, max_runtime=Duration(sec=int(seconds)))
        wall['side'], wall['samples'] = side, []
        ok = run_action('wall', goal, seconds + 20)
        wall['side'] = None
        v = sorted(wall['samples'])
        if v:
            say(f'wall {side}: nearest return min {v[0]:.2f} mean {sum(v) / len(v):.2f} max {v[-1]:.2f} m, '
                f'{len(v)} scans')
        return ok

    def face_start():
        p, s = state['odom'].position, state['start'].position
        target = math.atan2(s.y - p.y, s.x - p.x)
        delta = (target - yaw_of(state['odom'].orientation) + math.pi) % (2 * math.pi) - math.pi
        say(f'face:dock turning {math.degrees(delta):.1f} deg')
        return turn_step(math.degrees(delta))

    code = 1
    try:
        end = time.monotonic() + 60
        while time.monotonic() < end and (state['odom'] is None or state['dock'] is None or state['battery'] is None):
            rclpy.spin_once(node, timeout_sec=0.1)
        if state['odom'] is None or state['dock'] is None:
            say('SETUP FAILED: no /odom or /dock_status after 60 s')
            return 2
        # TB-25: this program is a new participant, wait until /odom is steady before moving
        steady_from = time.monotonic()
        limit = time.monotonic() + 60
        state['gap'] = 0.0
        while time.monotonic() - steady_from < 5.0 and time.monotonic() < limit:
            rclpy.spin_once(node, timeout_sec=0.05)
            if state['gap'] > 0.3:
                say(f'odometry gap {state["gap"]:.2f} s, waiting for 5 s steady')
                state['gap'] = 0.0
                steady_from = time.monotonic()
        if time.monotonic() >= limit:
            say('REFUSING: /odom not steady for 5 s within 60 s')
            return 2
        for step in args.steps:
            say(f'-- {step}')
            state['gap'] = 0.0
            name, _, value = step.partition(':')
            if name == 'status':
                ok = status()
            elif name == 'scan':
                ok = scan_step()
            elif name == 'undock':
                ok = run_action('undock', Undock.Goal(), 90)
            elif name == 'dock':
                ok = run_action('dock', Dock.Goal(), 120)
            elif name == 'drive':
                ok = drive_step(float(value))
            elif name == 'turn':
                ok = turn_step(float(value))
            elif name == 'wall':
                side, _, seconds = value.partition(':')
                ok = wall_step(side, float(seconds))
            elif name == 'wait':
                spin_for(float(value))
                ok = True
            elif name == 'face':
                ok = face_start()
            else:
                say(f'unknown step {step}')
                ok = False
            if not ok:
                say(f'step {step} failed, stopping the batch')
                status()
                return 1
        code = 0
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
        if logfile:
            logfile.close()
    return code


if __name__ == '__main__':
    sys.exit(main())
