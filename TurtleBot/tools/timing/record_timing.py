#!/usr/bin/env python3
"""Timing recorder for the TurtleBot 4: when do ROS messages stop, and what else happened at that moment?

Runs ON the robot (Ubuntu 24.04, ROS 2 Jazzy, Python 3.12) and is strictly read only: it only subscribes, never
publishes (so it cannot move the robot), changes no setting, writes only the output file, needs no root rights.

What it records, as JSON Lines (one record per line, field "kind"):
  header     versions, host, arguments, clock offsets (the robot's wall clock may be years wrong: all
             correlation uses the monotonic clock "t", in seconds)
  msg        one per received message: topic, t (monotonic receive time), wall, stamp (header stamp, if any);
             for /cmd_vel also vx and wz, so the start of a motion is visible
  sys        every --period s: loadavg, CPU % total and per core, CPU % of the ROS processes, network counters
             (errors, drops) and link state for eth0/usb0/wlan0, Wi-Fi link/level/noise, SoC temperature
  throttled  every 5 s: `vcgencmd get_throttled` (when vcgencmd exists)
  ping       every 1 s: round trip to the Create 3 base (and --ping-extra hosts); rtt is null on loss
  event      NetworkManager journal lines and Wi-Fi/USB/link kernel messages, when readable without root
  note       what could not be done (topic missing, journal not readable, ...)
  footer     end time, own CPU use

Usage on the robot (ROS environment must be set up):
    source /etc/turtlebot4/setup.bash
    python3 record_timing.py --duration 600 --out /tmp/timing.jsonl
    # or without copying the file:
    ssh <robot> 'source /etc/turtlebot4/setup.bash && python3 - --duration 600 --out /tmp/timing.jsonl' < record_timing.py
Stop early with Ctrl+C (or SIGTERM): the file is complete up to that moment; it is also flushed every second.
Then analyze it anywhere with analyze_timing.py. See README.md.
"""
import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

VERSION = 1
BASE_HOST = '192.168.186.2'                       # Create 3 base on the usb0 link
IFACES = ('eth0', 'usb0', 'wlan0')
CANDIDATE_TOPICS = ('/odom', '/imu', '/tf', '/scan', '/dock_status', '/battery_state',
                    '/wheel_vels', '/wheel_status', '/cmd_vel')
CMD_TOPIC = '/cmd_vel'
LIGHT_TOPICS = ('/odom', '/cmd_vel', '/dock_status')     # --light: the topics that matter for odometry stalls
FULL_DESERIALIZE = ('/cmd_vel', '/dock_status')          # low rate, and their fields are wanted
PROC_KEYWORDS = ('create3_republisher', 'turtlebot4', 'rplidar', 'diagnostic', 'joint_state_publisher',
                 'robot_state_publisher', 'rosbridge', 'discovery', 'ekf', 'ros2', 'micro_ros')
KERNEL_KEYWORDS = ('wlan', 'brcmfmac', 'wifi', 'wi-fi', 'link is', 'link up', 'link down', 'usb0', 'eth0',
                   'cdc_ether', 'disconnect', 'new usb device', 'voltage', 'throttl', 'thermal', 'oom',
                   'carrier', 'deauth', 'disassoc')
THERMAL_FILE = '/sys/class/thermal/thermal_zone0/temp'
RESCAN_PIDS_EVERY = 5.0     # s, look for new ROS processes this often (reading every cmdline each sample is dear)
THROTTLE_EVERY = 5.0        # s
DISCOVER_EVERY = 3.0        # s, look for topics that appeared later (e.g. /scan after undocking)


# ---------------------------------------------------------------- pure helpers (tested offline, no ROS)
def parse_proc_stat(text):
    """/proc/stat -> {'all': (total, idle), '0': (total, idle), ...} in jiffies."""
    out = {}
    for line in text.splitlines():
        if not line.startswith('cpu'):
            continue
        parts = line.split()
        name = parts[0][3:] or 'all'
        try:
            nums = [int(x) for x in parts[1:9]]
        except ValueError:
            continue
        nums += [0] * (8 - len(nums))
        out[name] = (sum(nums), nums[3] + nums[4])      # idle + iowait
    return out


def cpu_percent(prev, cur):
    """Busy percentage per CPU between two parse_proc_stat() results."""
    out = {}
    for name, (tot, idle) in cur.items():
        if name not in prev:
            continue
        dt = tot - prev[name][0]
        if dt > 0:
            out[name] = round(100.0 * (1.0 - (idle - prev[name][1]) / dt), 1)
    return out


def parse_net_dev(text):
    """/proc/net/dev -> {iface: {rx_bytes, rx_errs, rx_drop, tx_bytes, tx_errs, tx_drop}}."""
    out = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        name, rest = line.split(':', 1)
        f = rest.split()
        if len(f) < 12:
            continue
        try:
            v = [int(x) for x in f[:12]]
        except ValueError:
            continue
        out[name.strip()] = {'rx_bytes': v[0], 'rx_errs': v[2], 'rx_drop': v[3],
                             'tx_bytes': v[8], 'tx_errs': v[10], 'tx_drop': v[11]}
    return out


def parse_wireless(text):
    """/proc/net/wireless -> {iface: {link, level, noise}} (empty when no interface is associated)."""
    out = {}
    for line in text.splitlines()[2:]:
        if ':' not in line:
            continue
        name, rest = line.split(':', 1)
        f = rest.split()
        try:
            out[name.strip()] = {'link': float(f[1].rstrip('.')), 'level': float(f[2].rstrip('.')),
                                 'noise': float(f[3].rstrip('.'))}
        except (ValueError, IndexError):
            continue
    return out


def parse_ping(output):
    """Round trip time in ms from `ping -c1` output, or None when there was no reply."""
    m = re.search(r'time[=<]\s*([\d.]+)\s*ms', output or '')
    return float(m.group(1)) if m else None


def parse_pid_stat(text):
    """/proc/<pid>/stat -> (command name, utime + stime in jiffies)."""
    head, _, tail = text.rpartition(')')
    f = tail.split()
    return head.partition('(')[2], int(f[11]) + int(f[12])


def label_for_cmdline(cmdline, own_pid=None, pid=None):
    """Short name of a ROS-related process from its /proc/<pid>/cmdline text, or None if it is not one."""
    if own_pid is not None and pid == own_pid:
        return None
    args = [a for a in cmdline.split('\0') if a]
    if not args:
        return None
    joined = ' '.join(args).lower()
    if not ('--ros-args' in joined or '/opt/ros/' in joined or any(k in joined for k in PROC_KEYWORDS)):
        return None
    name = os.path.basename(args[0])
    if 'python' in name:
        script = [a for a in args[1:] if not a.startswith('-')]
        if script:
            name = os.path.basename(script[0])
    return name[:32] or None


def parse_throttled(text):
    m = re.search(r'throttled=(0x[0-9a-fA-F]+)', text or '')
    return int(m.group(1), 16) if m else None


def parse_journal_line(line):
    """One `journalctl -o json` line -> {'text', 'jt' (journal monotonic s, may be None), 'src'} or None."""
    try:
        d = json.loads(line)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    msg = d.get('MESSAGE', '')
    if isinstance(msg, list):                          # journald gives binary messages as a byte list
        msg = bytes(x & 255 for x in msg).decode('utf-8', 'replace')
    try:
        jt = int(d['__MONOTONIC_TIMESTAMP']) / 1e6
    except (KeyError, ValueError, TypeError):
        jt = None
    return {'text': str(msg), 'jt': jt, 'src': str(d.get('SYSLOG_IDENTIFIER', ''))}


def keep_event(source, text):
    """NetworkManager lines are all kept (few); kernel lines only when they mention network/USB/power."""
    if source != 'kernel':
        return True
    low = text.lower()
    return any(k in low for k in KERNEL_KEYWORDS)


def cdr_byte_order(data):
    """'<' or '>' from the 4-byte CDR encapsulation header (byte 1 = representation id low byte; odd = little endian)."""
    if len(data) < 4:
        return None
    return '<' if data[1] & 1 else '>'


def _stamp_at(data, off, order):
    if len(data) < off + 8:
        return None
    sec, nsec = struct.unpack_from(order + 'iI', data, off)
    return sec + nsec * 1e-9 if nsec < 1000000000 else None


def cdr_header_stamp(data):
    """Header stamp of a serialized message that starts with std_msgs/Header (int32 sec, uint32 nanosec right after
    the 4-byte encapsulation header). Bytes beyond that are never touched: no deserialisation."""
    order = cdr_byte_order(data)
    return None if order is None else _stamp_at(data, 4, order)


def cdr_tf_stamp(data):
    """tf2_msgs/TFMessage = sequence<TransformStamped>: uint32 length at stream offset 0, then the first
    TransformStamped whose first field is a Header. Offset 4 is 4-aligned and the stamp needs only 4-byte alignment,
    so no padding applies; the 4-byte encapsulation header shifts the raw offsets by 4."""
    order = cdr_byte_order(data)
    if order is None or len(data) < 8 or struct.unpack_from(order + 'I', data, 4)[0] == 0:
        return None
    return _stamp_at(data, 8, order)


def stamp_mode(cls):
    """How to read the stamp of a message class without deserialising: 'header', 'tf' or None."""
    try:
        fields = list(cls.get_fields_and_field_types().items())
    except Exception:
        return None
    if not fields:
        return None
    name, typ = fields[0]
    if name == 'header' and typ == 'std_msgs/Header':
        return 'header'
    if name == 'transforms' and 'TransformStamped' in typ:
        return 'tf'
    return None


def stamp_of(msg):
    """Header stamp of a message in seconds, or None. For /tf the first transform's stamp."""
    h = getattr(msg, 'header', None)
    if h is None:
        tr = getattr(msg, 'transforms', None)
        if tr:
            h = getattr(tr[0], 'header', None)
    if h is None or not hasattr(h, 'stamp'):
        return None
    return h.stamp.sec + h.stamp.nanosec * 1e-9


def cmd_of(msg):
    """(linear.x, angular.z) from a Twist or a TwistStamped."""
    tw = getattr(msg, 'twist', msg)
    return float(tw.linear.x), float(tw.angular.z)


def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except (OSError, ValueError):
        return None


def mono():
    return time.monotonic()


def r4(x):
    return round(x, 4)


# ---------------------------------------------------------------- output
class Writer:
    """Collects records from every thread and writes them out once a second (so a killed run keeps its data)."""

    def __init__(self, path):
        self.f = open(path, 'w', encoding='utf-8')
        self.lock = threading.Lock()
        self.buf = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def write(self, rec):
        line = json.dumps(rec, separators=(',', ':'))
        with self.lock:
            self.buf.append(line)

    def flush(self):
        with self.lock:
            lines, self.buf = self.buf, []
        if lines:
            self.f.write('\n'.join(lines) + '\n')
            self.f.flush()

    def _run(self):
        while not self.stop.wait(1.0):
            try:
                self.flush()
            except (OSError, ValueError):
                return

    def close(self):
        self.stop.set()
        self.thread.join(2.0)
        self.flush()
        self.f.close()


# ---------------------------------------------------------------- threads
def sampler(w, stop, period):
    """Side sampler: CPU, load, processes, network, Wi-Fi, temperature, throttling."""
    try:
        hz = os.sysconf('SC_CLK_TCK')
    except (ValueError, OSError, AttributeError):
        hz = 100
    prev_stat = parse_proc_stat(read_text('/proc/stat') or '')
    prev_ticks, labels = {}, {}
    last_scan = last_thr = -1e9
    vcg = shutil.which('vcgencmd')
    prev_t = mono()
    nxt = prev_t + period
    own = os.getpid()
    while not stop.wait(max(0.0, nxt - mono())):
        t = mono()
        nxt += period
        if nxt < t:
            nxt = t + period
        dt = max(t - prev_t, 1e-6)
        rec = {'kind': 'sys', 't': r4(t)}
        la = (read_text('/proc/loadavg') or '').split()
        if len(la) >= 3:
            rec['load'] = [float(x) for x in la[:3]]
        cur = parse_proc_stat(read_text('/proc/stat') or '')
        rec['cpu'] = cpu_percent(prev_stat, cur)
        prev_stat = cur
        if t - last_scan >= RESCAN_PIDS_EVERY:
            last_scan = t
            labels = {}
            try:
                names = os.listdir('/proc')
            except OSError:
                names = []
            for n in names:
                if n.isdigit():
                    txt = read_text('/proc/%s/cmdline' % n)
                    lab = label_for_cmdline(txt, own, int(n)) if txt else None
                    if lab:
                        labels[int(n)] = lab
        procs, ticks = {}, {}
        for pid, lab in labels.items():
            txt = read_text('/proc/%d/stat' % pid)
            if not txt:
                continue
            try:
                ticks[pid] = parse_pid_stat(txt)[1]
            except (ValueError, IndexError):
                continue
            if pid in prev_ticks:
                pct = 100.0 * (ticks[pid] - prev_ticks[pid]) / hz / dt
                if pct >= 1.0:
                    procs[lab] = round(procs.get(lab, 0.0) + pct, 1)
        prev_ticks = ticks
        rec['procs'] = procs
        net = parse_net_dev(read_text('/proc/net/dev') or '')
        rec['net'] = {i: net[i] for i in IFACES if i in net}
        link = {}
        for i in IFACES:
            op = read_text('/sys/class/net/%s/operstate' % i)
            if op is not None:
                ca = (read_text('/sys/class/net/%s/carrier' % i) or '').strip()
                link[i] = [op.strip(), ca]
        rec['link'] = link
        wl = parse_wireless(read_text('/proc/net/wireless') or '').get('wlan0')
        if wl:
            rec['wifi'] = wl
        tmp = read_text(THERMAL_FILE)
        if tmp and tmp.strip().lstrip('-').isdigit():
            rec['temp'] = round(int(tmp) / 1000.0, 1)
        w.write(rec)
        prev_t = t
        if vcg and t - last_thr >= THROTTLE_EVERY:
            last_thr = t
            try:
                p = subprocess.run([vcg, 'get_throttled'], capture_output=True, text=True, timeout=2)
                v = parse_throttled(p.stdout)
                if v is not None:
                    w.write({'kind': 'throttled', 't': r4(mono()), 'value': v})
                else:
                    vcg = None
                    w.write({'kind': 'note', 't': r4(mono()), 'text': 'vcgencmd gave no usable output'})
            except (OSError, subprocess.SubprocessError):
                vcg = None


def pinger(w, stop, host):
    """One ping per second; rtt is null on loss."""
    while not stop.is_set():
        t0 = mono()
        try:
            p = subprocess.run(['ping', '-c1', '-W1', host], capture_output=True, text=True, timeout=3)
            rtt = parse_ping(p.stdout)
        except subprocess.TimeoutExpired:
            rtt = None
        except OSError:
            w.write({'kind': 'note', 't': r4(t0), 'text': 'ping not available'})
            return
        w.write({'kind': 'ping', 't': r4(t0), 'host': host, 'rtt': rtt})
        stop.wait(max(0.0, 1.0 - (mono() - t0)))


def journal_follower(w, stop, cmd, source, procs):
    """Follow a journalctl command; silently give up if it cannot be started or read."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors='replace')
    except OSError:
        w.write({'kind': 'note', 't': r4(mono()), 'text': 'journalctl not available (%s)' % source})
        return
    procs.append(p)
    got = False
    for line in p.stdout:
        t = mono()
        got = True
        ev = parse_journal_line(line)
        if ev and keep_event(source, ev['text']):
            rec = {'kind': 'event', 't': r4(t), 'source': source, 'text': ev['text'][:300]}
            if ev['jt'] is not None:
                rec['jt'] = r4(ev['jt'])
            w.write(rec)
        if stop.is_set():
            break
    if not got and not stop.is_set():
        w.write({'kind': 'note', 't': r4(mono()), 'text': 'journal not readable without root (%s)' % source})


def ros_loop(w, stop, end_mono, extra_topics, light=False):
    """Subscribe to the topics and spin until stop/end. Imports ROS here so the helpers above need none."""
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from rosidl_runtime_py.utilities import get_message
    try:
        from rclpy.signals import SignalHandlerOptions
        rclpy.init(args=None, signal_handler_options=SignalHandlerOptions.NO)
    except ImportError:
        rclpy.init(args=None)
    node = rclpy.create_node('timing_recorder_%d' % os.getpid(), start_parameter_services=False,
                             enable_rosout=False)
    ex = rclpy.executors.SingleThreadedExecutor()
    ex.add_node(node)
    wanted = (list(LIGHT_TOPICS) if light else list(CANDIDATE_TOPICS)) + [t for t in extra_topics if t not in CANDIDATE_TOPICS]
    subs = {}

    def make_cb(topic, mode):
        """Callback factory. Raw subscriptions get the CDR bytes and only the stamp is read (cheap);
        /cmd_vel and /dock_status are deserialised (low rate, their fields are wanted)."""
        is_cmd = topic == CMD_TOPIC

        def cb_full(msg):
            t = mono()
            rec = {'kind': 'msg', 'topic': topic, 't': r4(t), 'wall': round(time.time(), 4)}
            s = stamp_of(msg)
            if s is not None:
                rec['stamp'] = round(s, 6)
            if is_cmd:
                rec['vx'], rec['wz'] = cmd_of(msg)
            if hasattr(msg, 'is_docked'):
                rec['docked'] = bool(msg.is_docked)
                rec['visible'] = bool(getattr(msg, 'dock_visible', False))
            w.write(rec)

        def cb_raw(data):
            t = mono()
            rec = {'kind': 'msg', 'topic': topic, 't': r4(t), 'wall': round(time.time(), 4)}
            s = cdr_header_stamp(data) if mode == 'header' else cdr_tf_stamp(data) if mode == 'tf' else None
            if s is not None:
                rec['stamp'] = round(s, 6)
            w.write(rec)
        return cb_full if mode == 'full' else cb_raw

    def discover():
        try:
            types = dict(node.get_topic_names_and_types())
        except Exception:
            return
        for topic in wanted:
            if topic in subs or topic not in types or not types[topic]:
                continue
            try:
                cls = get_message(types[topic][0])
                mode = 'full' if topic in FULL_DESERIALIZE else (stamp_mode(cls) or 'none')
                subs[topic] = node.create_subscription(cls, topic, make_cb(topic, mode), qos_profile_sensor_data,
                                                       raw=(mode != 'full'))
                w.write({'kind': 'subscribed', 't': r4(mono()), 'topic': topic, 'type': types[topic][0]})
            except Exception as e:
                w.write({'kind': 'note', 't': r4(mono()), 'text': 'cannot subscribe %s: %s' % (topic, e)})
                subs[topic] = None

    try:
        last = -1e9
        while not stop.is_set() and mono() < end_mono:
            if mono() - last >= DISCOVER_EVERY:
                last = mono()
                discover()
            ex.spin_once(timeout_sec=0.25)
        missing = [t for t in wanted if t not in subs]
        if missing:
            w.write({'kind': 'note', 't': r4(mono()), 'text': 'topics never seen: ' + ' '.join(missing)})
    finally:
        try:
            ex.shutdown()
            node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------- main
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='Read-only timing recorder (see the module docstring and README.md).')
    ap.add_argument('--duration', type=float, default=600.0, help='seconds to record, 0 = until Ctrl+C (default 600)')
    ap.add_argument('--out', default='/tmp/timing.jsonl', help='output JSON Lines file (default /tmp/timing.jsonl)')
    ap.add_argument('--overwrite', action='store_true', help='replace the output file if it exists')
    ap.add_argument('--period', type=float, default=None, help='system sampling period in s (default 0.2, 0.5 with --light)')
    ap.add_argument('--light', action='store_true', help='cheapest recording: only /odom, /cmd_vel, /dock_status plus system and ping')
    ap.add_argument('--ping-extra', action='append', default=[], metavar='HOST', help='also ping this host (repeatable)')
    ap.add_argument('--base-host', default=BASE_HOST, help='Create 3 base address (default %s)' % BASE_HOST)
    ap.add_argument('--no-ping', action='store_true', help='do not ping anything')
    ap.add_argument('--no-journal', action='store_true', help='do not follow the journal')
    ap.add_argument('--no-ros', action='store_true', help='system sampling only, no ROS topics')
    ap.add_argument('--topic', action='append', default=[], metavar='NAME', help='extra topic to record (repeatable)')
    a = ap.parse_args(argv)
    if a.period is None:
        a.period = 0.5 if a.light else 0.2
    if a.period < 0.05:
        ap.error('--period must be at least 0.05 s (the recorder must stay cheap)')
    return a


def run(a):
    if os.path.exists(a.out) and not a.overwrite:
        print('%s exists; use --overwrite or another --out' % a.out, file=sys.stderr)
        return 2
    stop = threading.Event()

    def on_signal(signum, frame):
        stop.set()
    for name in ('SIGINT', 'SIGTERM', 'SIGHUP'):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), on_signal)
            except (ValueError, OSError):
                pass
    try:
        import rclpy  # noqa: F401
        have_ros = not a.no_ros
    except ImportError:
        have_ros = False
        if not a.no_ros:
            print('rclpy not importable (source /etc/turtlebot4/setup.bash): recording system data only', file=sys.stderr)
    w = Writer(a.out)
    mono0, wall0 = mono(), time.time()
    w.write({'kind': 'header', 'version': VERSION, 'hostname': socket.gethostname(), 'args': vars(a),
             'mono0': r4(mono0), 'wall0': round(wall0, 3), 'wall_minus_mono': round(wall0 - mono0, 3),
             'python': platform.python_version(), 'platform': platform.platform(), 'cpus': os.cpu_count(),
             'ros_distro': os.environ.get('ROS_DISTRO'), 'rmw': os.environ.get('RMW_IMPLEMENTATION'),
             'domain': os.environ.get('ROS_DOMAIN_ID'), 'boot_id': (read_text('/proc/sys/kernel/random/boot_id') or '').strip(),
             'ros': have_ros})
    end = mono0 + a.duration if a.duration > 0 else float('inf')
    threads, procs = [], []

    def start(target, *args):
        th = threading.Thread(target=target, args=args, daemon=True)
        th.start()
        threads.append(th)
    start(sampler, w, stop, a.period)
    if not a.no_ping:
        hosts = ([a.base_host] if a.base_host else []) + list(a.ping_extra)
        for h in hosts:
            start(pinger, w, stop, h)
    if not a.no_journal:
        start(journal_follower, w, stop, ['journalctl', '-f', '-n', '0', '-o', 'json', '-u', 'NetworkManager'],
              'NetworkManager', procs)
        start(journal_follower, w, stop, ['journalctl', '-k', '-f', '-n', '0', '-o', 'json'], 'kernel', procs)
    print('recording to %s for %s (Ctrl+C to stop early)' % (a.out, '%g s' % a.duration if a.duration > 0 else 'ever'))
    try:
        if have_ros:
            ros_loop(w, stop, end, a.topic, a.light)
        else:
            while not stop.is_set() and mono() < end:
                stop.wait(min(0.25, max(0.0, end - mono())))
    finally:
        stop.set()
        for p in procs:
            try:
                p.terminate()
            except OSError:
                pass
        for th in threads:
            th.join(2.0)
        elapsed = max(mono() - mono0, 1e-6)
        ct = os.times()
        own = 100.0 * (ct[0] + ct[1] + ct[2] + ct[3]) / elapsed
        w.write({'kind': 'footer', 't': r4(mono()), 'elapsed': round(elapsed, 2), 'own_cpu_pct': round(own, 2)})
        w.close()
        print('done: %.1f s recorded, own CPU use %.2f %% of one core (children such as ping included)' % (elapsed, own))
    return 0


def main(argv=None):
    return run(parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
