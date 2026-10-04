"""Sensor health report: message rates and gaps of /odom, /scan, /imu, /battery_state, /dock_status.

Does NOT move the robot. Safe on the dock (the lidar is off there, so /scan shows as missing).

For --seconds s (default 20) it records, for each topic, when every message ARRIVED (Pi clock) and the time
in its header STAMP (the publisher's clock, the Create 3 for /odom, /imu, /battery_state, /dock_status).
Then it prints a table:
    msgs, rate (Hz), mean period, max ARRIVAL gap, max STAMP gap, number of gaps > GAP_FACTOR x the median
    period, and the median "age" (Pi clock now - header stamp; large or negative = clocks out of sync)
plus battery %, docked state, lidar valid-beam %, min/median range, and the lidar's yaw from TF.
If /odom has an arrival gap but no stamp gap, the base produced the data on time and it was delayed on the
way (Wi-Fi / DDS / Pi load); if both have the gap, the base itself paused. This is the odom-gap diagnostic.

Run it on the robot:
    python3 sensor_report.py                       # 20 s
    python3 sensor_report.py --seconds 60 --json ~/robot_code/sensors.json
Stop early with Ctrl+C (the report is still printed for the time measured so far).
Exit codes: 0 report printed, 2 no messages at all on any topic.
"""
import argparse
import json
import math
import signal
import statistics
import sys
import time

import rclpy
import tf2_ros
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import BatteryState, Imu, LaserScan

try:
    from irobot_create_msgs.msg import DockStatus
except ImportError:
    DockStatus = None

# ---------------------------------------------------------------- parameters
SECONDS = 20.0                # default measuring time
WARMUP = 15.0                 # s, wait at most this long for the first message before measuring
GAP_FACTOR = 2.5              # a gap longer than this x the median period counts as a gap
TOP_GAPS = 5                  # how many of the largest /odom and /scan gaps to list
EXPECTED_HZ = {'/odom': 20.0, '/scan': 7.7, '/imu': 100.0, '/battery_state': 1.0, '/dock_status': 1.0}
TOPICS = [('/odom', Odometry), ('/scan', LaserScan), ('/imu', Imu), ('/battery_state', BatteryState)]
if DockStatus is not None:
    TOPICS.append(('/dock_status', DockStatus))

stop_request = None


def stamp_seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


# ---------------------------------------------------------------- pure helpers (no ROS needed)
def gap_stats(times):
    """Stats of a list of increasing times: dict with count, rate, mean/median/max period, gaps list."""
    out = {'count': len(times), 'rate_hz': None, 'mean_period_s': None, 'median_period_s': None,
           'max_gap_s': None, 'max_gap_at_s': None, 'big_gaps': []}
    if len(times) < 2:
        return out
    gaps = [b - a for a, b in zip(times, times[1:])]
    span = times[-1] - times[0]
    med = statistics.median(gaps)
    i = max(range(len(gaps)), key=gaps.__getitem__)
    out.update(rate_hz=(len(times) - 1) / span if span > 0 else None, mean_period_s=span / len(gaps),
               median_period_s=med, max_gap_s=gaps[i], max_gap_at_s=times[i] - times[0],
               big_gaps=[(round(times[k] - times[0], 3), round(g, 3)) for k, g in enumerate(gaps)
                         if med > 0 and g > GAP_FACTOR * med])
    return out


def fmt(v, spec, missing='-'):
    return missing if v is None or (isinstance(v, float) and not math.isfinite(v)) else format(v, spec)


# ---------------------------------------------------------------- ROS node
class Recorder(Node):
    def __init__(self):
        super().__init__('sensor_report')
        self.arrivals = {t: [] for t, _ in TOPICS}
        self.stamps = {t: [] for t, _ in TOPICS}
        self.ages = {t: [] for t, _ in TOPICS}
        self.recording = False
        self.battery = None
        self.docked = None
        self.scan_valid = []          # fraction of valid beams per scan
        self.scan_min = []
        self.scan_median = []
        self.scan_frame = None
        self.scan_beams = None
        for topic, mtype in TOPICS:
            self.create_subscription(mtype, topic, self.make_callback(topic), qos_profile_sensor_data)
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

    def make_callback(self, topic):
        def callback(msg):
            now = time.monotonic()
            if topic == '/battery_state':
                self.battery = msg.percentage
            elif topic == '/dock_status':
                self.docked = msg.is_docked
            elif topic == '/scan':
                self.on_scan(msg)
            if not self.recording:
                self.arrivals[topic].append(None)   # marks "seen during warm-up"
                return
            self.arrivals[topic].append(now)
            header = getattr(msg, 'header', None)      # all five types have a header; be safe anyway
            if header is not None:
                st = stamp_seconds(header.stamp)
                self.stamps[topic].append(st)
                self.ages[topic].append(time.time() - st)
        return callback

    def on_scan(self, msg):
        valid = [r for r in msg.ranges if msg.range_min < r < msg.range_max]
        self.scan_frame = msg.header.frame_id
        self.scan_beams = len(msg.ranges)
        if not self.recording:
            return
        self.scan_valid.append(len(valid) / max(1, len(msg.ranges)))
        if valid:
            self.scan_min.append(min(valid))
            self.scan_median.append(statistics.median(valid))

    def lidar_yaw(self):
        if self.scan_frame is None:
            return None
        try:
            t = self.tf_buffer.lookup_transform('base_link', self.scan_frame, rclpy.time.Time())
        except tf2_ros.TransformException:
            return None
        q = t.transform.rotation
        return math.degrees(math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z)))


def on_signal(signum, frame):
    global stop_request
    stop_request = signal.Signals(signum).name


def build_report(node, measured):
    rep = {'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'measured_s': round(measured, 2), 'topics': {}}
    for topic, _ in TOPICS:
        arr = [t for t in node.arrivals[topic] if t is not None]
        a = gap_stats(arr)
        s = gap_stats(node.stamps[topic])
        rep['topics'][topic] = {
            'count': a['count'], 'rate_hz': a['rate_hz'], 'expected_hz': EXPECTED_HZ.get(topic),
            'mean_period_s': a['mean_period_s'], 'max_arrival_gap_s': a['max_gap_s'],
            'max_arrival_gap_at_s': a['max_gap_at_s'], 'arrival_gaps': a['big_gaps'],
            'max_stamp_gap_s': s['max_gap_s'], 'stamp_gaps': s['big_gaps'],
            'median_age_s': statistics.median(node.ages[topic]) if node.ages[topic] else None,
            'stamps_out_of_order': sum(1 for x, y in zip(node.stamps[topic], node.stamps[topic][1:]) if y < x),
        }
    rep['battery_percent'] = None if node.battery is None or not math.isfinite(node.battery) else \
        round(100.0 * node.battery, 1)
    rep['docked'] = node.docked
    rep['lidar'] = {
        'frame': node.scan_frame, 'beams': node.scan_beams,
        'valid_percent': round(100 * statistics.mean(node.scan_valid), 1) if node.scan_valid else None,
        'min_range_m': round(min(node.scan_min), 3) if node.scan_min else None,
        'median_range_m': round(statistics.median(node.scan_median), 3) if node.scan_median else None,
        'tf_yaw_deg': node.lidar_yaw(),
    }
    return rep


def print_report(rep):
    print(f'\nSensor report, {rep["measured_s"]:.1f} s measured at {rep["created"]}')
    print(f'{"topic":<15}{"msgs":>6}{"rate Hz":>9}{"expect":>8}{"period":>8}{"max arr gap":>13}'
          f'{"max stamp gap":>15}{"gaps>" + str(GAP_FACTOR) + "x":>11}{"age s":>8}')
    for topic, t in rep['topics'].items():
        print(f'{topic:<15}{t["count"]:>6}{fmt(t["rate_hz"], ".2f"):>9}{fmt(t["expected_hz"], ".1f"):>8}'
              f'{fmt(t["mean_period_s"], ".3f"):>8}{fmt(t["max_arrival_gap_s"], ".3f"):>13}'
              f'{fmt(t["max_stamp_gap_s"], ".3f"):>15}{len(t["arrival_gaps"]):>11}{fmt(t["median_age_s"], ".3f"):>8}')
    for topic in ('/odom', '/scan'):
        t = rep['topics'].get(topic)
        if t and t['arrival_gaps']:
            worst = sorted(t['arrival_gaps'], key=lambda g: -g[1])[:TOP_GAPS]
            print(f'  largest {topic} arrival gaps (at s: length s): '
                  + ', '.join(f'{at:.1f}: {g:.2f}' for at, g in worst))
        if t and t['stamp_gaps']:
            worst = sorted(t['stamp_gaps'], key=lambda g: -g[1])[:TOP_GAPS]
            print(f'  largest {topic} stamp gaps   (at s: length s): '
                  + ', '.join(f'{at:.1f}: {g:.2f}' for at, g in worst))
        if t and t['stamps_out_of_order']:
            print(f'  {topic}: {t["stamps_out_of_order"]} messages with a stamp older than the one before')
    lid = rep['lidar']
    print(f'battery: {fmt(rep["battery_percent"], ".1f", "unknown")} %   docked: '
          f'{"unknown" if rep["docked"] is None else rep["docked"]}')
    if lid['valid_percent'] is None:
        print('lidar: no scans (normal while docked: the lidar is switched off there)')
    else:
        print(f'lidar: {lid["beams"]} beams, {lid["valid_percent"]:.1f} % valid, min range {fmt(lid["min_range_m"], ".2f")} m, '
              f'median range {fmt(lid["median_range_m"], ".2f")} m, frame {lid["frame"]}, '
              f'TF yaw in base_link {fmt(lid["tf_yaw_deg"], ".0f", "unknown")} deg')
    print('age = Pi clock - header stamp. Arrival gap without stamp gap: delayed on the way; both: the source paused.')


def main():
    p = argparse.ArgumentParser(description='Measure sensor rates and gaps. Does not move the robot.')
    p.add_argument('--seconds', type=float, default=SECONDS, help=f'measuring time (default {SECONDS:.0f} s)')
    p.add_argument('--json', help='also write the report to this JSON file')
    args = p.parse_args()

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    node = Recorder()
    code = 0
    try:
        print(f'{time.strftime("%H:%M:%S")} waiting up to {WARMUP:.0f} s for the first messages '
              '(ROS starts slowly on the Pi)', flush=True)
        end = time.monotonic() + WARMUP
        while time.monotonic() < end and not stop_request and not node.arrivals['/odom']:
            rclpy.spin_once(node, timeout_sec=0.2)
        settle_end = time.monotonic() + 1.0      # one more second so the other topics are discovered too
        while time.monotonic() < settle_end and not stop_request:
            rclpy.spin_once(node, timeout_sec=0.1)
        node.recording = True
        print(f'{time.strftime("%H:%M:%S")} measuring for {args.seconds:.0f} s (Ctrl+C to stop early)', flush=True)
        start = time.monotonic()
        end = start + args.seconds
        while time.monotonic() < end and not stop_request:
            rclpy.spin_once(node, timeout_sec=0.05)
        measured = time.monotonic() - start
        node.recording = False
        rep = build_report(node, measured)
        print_report(rep)
        if args.json:
            with open(args.json, 'w') as f:
                json.dump(rep, f, indent=2)
            print(f'wrote {args.json}')
        if not any(t['count'] for t in rep['topics'].values()):
            print('NO MESSAGES on any topic. Is the robot on? See HOW-TO-CONNECT.md (restart the base application).')
            code = 2
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
