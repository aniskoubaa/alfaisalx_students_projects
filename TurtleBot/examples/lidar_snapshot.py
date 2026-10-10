"""Save one or more lidar scans to a file (JSON or CSV) and print a 36-sector summary around the robot.

Does NOT move the robot. Needs the robot off the dock (the lidar is switched off while docked).

Angles are saved in the ROBOT frame: 0 deg = straight ahead, +90 deg = left, -90 deg = right
(the lidar on this robot is mounted turned +90 deg; the program reads that from TF, fallback +90 deg).
JSON layout (what scan_plot_html.py reads):
    {"created", "frame_id", "lidar_yaw_deg", "lidar_yaw_source", "range_min", "range_max",
     "angle_min", "angle_increment",               <- laser frame, as in the LaserScan message
     "angles_robot_deg": [...one per beam...],
     "scans": [{"stamp": seconds, "ranges": [metres or null for no return, ...]}, ...]}
CSV layout: scan,beam,angle_robot_deg,range_m,x_m,y_m  (x forward, y left; empty range = no return).

Run it on the robot:
    python3 lidar_snapshot.py                                  # 1 scan -> ~/robot_code/scan_<time>.json
    python3 lidar_snapshot.py --count 5 --out ~/robot_code/room.json
    python3 lidar_snapshot.py --out ~/robot_code/room.csv      # CSV because of the extension
Then copy the JSON to your computer and run scan_plot_html.py on it to see a picture.
Stop early with Ctrl+C. Exit codes: 0 saved, 2 no scan (docked? lidar off?).
"""
import argparse
import json
import math
import os
import sys
import time

import rclpy
import tf2_ros
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

# ---------------------------------------------------------------- parameters
COUNT = 1                     # scans to save by default
WAIT = 30.0                   # s, wait this long for scans (ROS starts slowly on the Pi)
TF_WAIT = 5.0                 # s, wait this long for the lidar's TF before using the fallback
LIDAR_YAW_FALLBACK = 90.0     # deg, measured on this robot (base_link -> rplidar_link)
SECTORS = 36                  # 10 deg sectors in the printed summary
BAR_RANGE = 4.0               # m, a full-length bar in the summary
BAR_WIDTH = 40                # characters
DEFAULT_DIR = os.path.expanduser('~/robot_code')


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def wrap_deg(a):
    """Wrap an angle in degrees to [-180, 180)."""
    return (a + 180.0) % 360.0 - 180.0


def robot_angles_deg(angle_min, angle_increment, n, lidar_yaw_deg):
    """Robot-frame angle (deg) of each of n beams."""
    return [round(wrap_deg(math.degrees(angle_min + i * angle_increment) + lidar_yaw_deg), 3) for i in range(n)]


def clean_ranges(ranges, range_min, range_max):
    """Ranges with invalid returns (out of limits, inf, nan) replaced by None, rounded to mm."""
    return [round(r, 3) if range_min < r < range_max else None for r in ranges]


def sector_of(angle_deg, sectors=SECTORS):
    """Sector index for a robot-frame angle. Sector 0 is centred on straight ahead, indexes increase to the left."""
    width = 360.0 / sectors
    return int(math.floor(wrap_deg(angle_deg) / width + 0.5)) % sectors


def sector_minima(angles_deg, scans, sectors=SECTORS):
    """Nearest valid range per sector over all scans (None if the sector has no return)."""
    best = [None] * sectors
    for ranges in scans:
        for a, r in zip(angles_deg, ranges):
            if r is None:
                continue
            k = sector_of(a, sectors)
            if best[k] is None or r < best[k]:
                best[k] = r
    return best


def sector_label(k, sectors=SECTORS):
    """Centre angle of sector k in degrees, in [-180, 180)."""
    return wrap_deg(k * 360.0 / sectors)


def summary_lines(minima, sectors=SECTORS):
    """Printable lines, from straight ahead going left round to the right."""
    lines = []
    names = {0: 'front', 90: 'left', -180: 'back', -90: 'right'}
    for k in range(sectors):
        a = sector_label(k, sectors)
        r = minima[k]
        name = names.get(int(round(a)), '')
        if r is None:
            lines.append(f'{a:+5.0f} deg {name:<5}   none')
        else:
            bar = '#' * max(1, int(round(min(r, BAR_RANGE) / BAR_RANGE * BAR_WIDTH)))
            lines.append(f'{a:+5.0f} deg {name:<5} {r:5.2f} m {bar}')
    return lines


def write_csv(path, angles_deg, scans):
    with open(path, 'w') as f:
        f.write('scan,beam,angle_robot_deg,range_m,x_m,y_m\n')
        for s, ranges in enumerate(scans):
            for i, (a, r) in enumerate(zip(angles_deg, ranges)):
                if r is None:
                    f.write(f'{s},{i},{a:.3f},,,\n')
                else:
                    x, y = r * math.cos(math.radians(a)), r * math.sin(math.radians(a))
                    f.write(f'{s},{i},{a:.3f},{r:.3f},{x:.3f},{y:.3f}\n')


# ---------------------------------------------------------------- ROS node
class Snapshot(Node):
    def __init__(self):
        super().__init__('lidar_snapshot')
        self.scans = []
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.create_subscription(LaserScan, '/scan', self.scans.append, qos_profile_sensor_data)

    def lidar_yaw_deg(self, frame):
        try:
            t = self.tf_buffer.lookup_transform('base_link', frame, rclpy.time.Time())
        except tf2_ros.TransformException:
            return None
        q = t.transform.rotation
        return math.degrees(math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z)))


def main():
    p = argparse.ArgumentParser(description='Save lidar scans to JSON/CSV. Does not move the robot.')
    p.add_argument('--count', type=int, default=COUNT, help=f'number of scans to save (default {COUNT})')
    p.add_argument('--out', help='output file, .json or .csv (default ~/robot_code/scan_<time>.json)')
    args = p.parse_args()
    count = max(1, min(100, args.count))
    out = args.out or os.path.join(DEFAULT_DIR if os.path.isdir(DEFAULT_DIR) else '.',
                                   time.strftime('scan_%Y%m%d_%H%M%S.json'))

    rclpy.init()
    node = Snapshot()
    code = 0
    try:
        print(f'{time.strftime("%H:%M:%S")} waiting up to {WAIT:.0f} s for {count} scan(s)', flush=True)
        end = time.monotonic() + WAIT
        yaw, source = None, 'tf'
        tf_end = None
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.2)
            if node.scans and yaw is None:
                tf_end = tf_end or time.monotonic() + TF_WAIT
                yaw = node.lidar_yaw_deg(node.scans[0].header.frame_id)
                if yaw is None and time.monotonic() > tf_end:
                    yaw, source = LIDAR_YAW_FALLBACK, 'fallback'
                    print(f'warning: no TF for the lidar, assuming it is turned {yaw:.0f} deg')
            if len(node.scans) >= count and yaw is not None:
                break
        if not node.scans:
            print('NO SCAN: the lidar is not publishing. Is the robot on the dock? (the lidar is off there)')
            return 2
        if yaw is None:
            yaw, source = LIDAR_YAW_FALLBACK, 'fallback'
        msgs = node.scans[-count:] if len(node.scans) >= count else node.scans
        if len(msgs) < count:
            print(f'warning: only {len(msgs)} of {count} scans arrived')
        first = msgs[0]
        angles = robot_angles_deg(first.angle_min, first.angle_increment, len(first.ranges), yaw)
        scans = [clean_ranges(m.ranges, m.range_min, m.range_max)[:len(angles)] for m in msgs]
        if out.lower().endswith('.csv'):
            write_csv(out, angles, scans)
        else:
            data = {'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'frame_id': first.header.frame_id,
                    'lidar_yaw_deg': round(yaw, 2), 'lidar_yaw_source': source,
                    'range_min': first.range_min, 'range_max': first.range_max,
                    'angle_min': first.angle_min, 'angle_increment': first.angle_increment,
                    'angles_robot_deg': angles,
                    'scans': [{'stamp': m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, 'ranges': r}
                              for m, r in zip(msgs, scans)]}
            with open(out, 'w') as f:
                json.dump(data, f, separators=(',', ':'))
        valid = sum(r is not None for s in scans for r in s)
        total = sum(len(s) for s in scans)
        print(f'saved {len(scans)} scan(s), {len(angles)} beams each, {100.0 * valid / max(1, total):.0f} % valid, '
              f'lidar yaw {yaw:.0f} deg ({source}) -> {out}')
        print(f'nearest return per {360 // SECTORS} deg sector (robot frame: 0 = front, +90 = left):')
        for line in summary_lines(sector_minima(angles, scans)):
            print('  ' + line)
    except (KeyboardInterrupt, ExternalShutdownException):
        print('stopped')
        code = 130
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
