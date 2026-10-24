"""Offline tests of the timing tools (TurtleBot/tools/timing): the recorder's pure parsers and the analyzer.

No robot and no ROS needed: the recorder imports rclpy only inside its ROS loop. Synthetic recordings contain
known /odom gaps (at a motion start, at a CPU spike with delayed delivery, at base ping loss, one without any
cause) and a clean run. Usage: python test_timing.py
"""
import gzip
import json
import os
import signal
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as NS

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'timing'))
sys.path.insert(0, TOOLS)
import analyze_timing as at  # noqa: E402
import record_timing as rt  # noqa: E402

OUT = tempfile.mkdtemp(prefix='tb4_timing_tests_')
fails = 0


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


# ---------------------------------------------------------------- recorder: pure parsers
STAT_A = 'cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 50 0 50 350 50 0 0 0 0 0\ncpu1 50 0 50 350 50 0 0 0 0 0\nintr 1\n'
STAT_B = 'cpu  200 0 200 750 150 0 0 0 0 0\ncpu0 100 0 100 375 75 0 0 0 0 0\ncpu1 100 0 100 375 75 0 0 0 0 0\n'
pa, pb = rt.parse_proc_stat(STAT_A), rt.parse_proc_stat(STAT_B)
cp = rt.cpu_percent(pa, pb)
check('proc/stat: totals and idle (idle+iowait)', pa['all'] == (1000, 800) and pa['0'] == (500, 400), str(pa))
check('proc/stat: cpu percent total and per core (busy 200 of 300 -> 66.7 %)',
      cp == {'all': 66.7, '0': 66.7, '1': 66.7}, str(cp))
check('proc/stat: no change or garbage gives no value', rt.cpu_percent(pa, pa) == {} and rt.parse_proc_stat('cpu x y\n') == {})

NETDEV = ('Inter-|   Receive                                                |  Transmit\n'
          ' face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n'
          '    lo: 1000      10    0    0    0     0          0         0     1000      10    0    0    0     0       0          0\n'
          '  usb0: 123456   200    3    4    0     0          0         0     654321   300    5    6    0     0       0          0\n'
          ' wlan0:99 1 0 0 0 0 0 0 88 2 1 2 0 0 0 0\n')
nd = rt.parse_net_dev(NETDEV)
check('net/dev: usb0 bytes, errors, drops', nd['usb0'] == {'rx_bytes': 123456, 'rx_errs': 3, 'rx_drop': 4,
                                                          'tx_bytes': 654321, 'tx_errs': 5, 'tx_drop': 6}, str(nd.get('usb0')))
check('net/dev: name glued to the number still parses', nd['wlan0']['rx_bytes'] == 99 and nd['wlan0']['tx_drop'] == 2)

WIRELESS = ('Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE\n'
            ' face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22\n'
            ' wlan0: 0000   58.  -52.  -256        0      0      0      0      0        0\n')
wl = rt.parse_wireless(WIRELESS)
check('net/wireless: link, level, noise', wl == {'wlan0': {'link': 58.0, 'level': -52.0, 'noise': -256.0}}, str(wl))
check('net/wireless: header only (access point mode) gives nothing', rt.parse_wireless(WIRELESS.splitlines()[0] + '\n' + WIRELESS.splitlines()[1] + '\n') == {})

PING_OK = 'PING 192.168.186.2 (192.168.186.2) 56(84) bytes of data.\n64 bytes from 192.168.186.2: icmp_seq=1 ttl=64 time=0.523 ms\n'
PING_LOSS = 'PING 192.168.186.2 (192.168.186.2) 56(84) bytes of data.\n\n--- 192.168.186.2 ping statistics ---\n1 packets transmitted, 0 received, 100% packet loss\n'
check('ping: rtt parsed, loss gives None, <1 ms form', rt.parse_ping(PING_OK) == 0.523 and rt.parse_ping(PING_LOSS) is None
      and rt.parse_ping('64 bytes: time<1 ms') == 1.0 and rt.parse_ping(None) is None)

check('pid stat: comm with spaces and parentheses, utime+stime',
      rt.parse_pid_stat('1234 (my (odd) proc) S 1 2 3 4 5 6 7 8 9 10 111 222 0 0 20 0 1 0 5 100 50') == ('my (odd) proc', 333))
check('process labels: ROS node, python script, unrelated, own pid',
      rt.label_for_cmdline('/opt/ros/jazzy/lib/create3_republisher/create3_republisher\0--ros-args\0') == 'create3_republisher'
      and rt.label_for_cmdline('python3\0/home/ubuntu/rplidar_thing.py\0-x\0') == 'rplidar_thing.py'
      and rt.label_for_cmdline('/usr/sbin/sshd\0-D\0') is None and rt.label_for_cmdline('') is None
      and rt.label_for_cmdline('python3\0-\0--duration\0600\0', 5, 5) is None)
check('vcgencmd throttled parse', rt.parse_throttled('throttled=0x50005\n') == 0x50005 and rt.parse_throttled('error') is None)

jl = rt.parse_journal_line(json.dumps({'MESSAGE': 'wlan0: link disconnected', '__MONOTONIC_TIMESTAMP': '12345678',
                                       'SYSLOG_IDENTIFIER': 'NetworkManager'}))
check('journal line: text, monotonic seconds, source', jl == {'text': 'wlan0: link disconnected', 'jt': 12.345678, 'src': 'NetworkManager'}, str(jl))
check('journal line: byte-list message, bad json', rt.parse_journal_line(json.dumps({'MESSAGE': [104, 105]}))['text'] == 'hi'
      and rt.parse_journal_line('{oops') is None)
check('event filter: NM all kept, kernel only network/usb/power',
      rt.keep_event('NetworkManager', 'anything') and rt.keep_event('kernel', 'brcmfmac: deauth') and rt.keep_event('kernel', 'Under-voltage detected')
      and not rt.keep_event('kernel', 'audit: type=1400'))
stamp = NS(sec=10, nanosec=500000000)
check('message helpers: header stamp, tf stamp, no header, Twist and TwistStamped',
      rt.stamp_of(NS(header=NS(stamp=stamp))) == 10.5 and rt.stamp_of(NS(transforms=[NS(header=NS(stamp=stamp))])) == 10.5
      and rt.stamp_of(NS(data=1)) is None
      and rt.cmd_of(NS(twist=NS(linear=NS(x=0.1), angular=NS(z=0.5)))) == (0.1, 0.5)
      and rt.cmd_of(NS(linear=NS(x=0.1), angular=NS(z=-0.5))) == (0.1, -0.5))

src = open(os.path.join(TOOLS, 'record_timing.py'), 'rb').read()
text = src.decode()
check('recorder is read only (no publisher, client, service, sudo, shell=True), LF endings, ROS imported only inside functions',
      all(w not in text for w in ('create_publisher', 'create_client', 'sudo', 'shell=True', 'create_service'))
      and bytes([13]) not in src and not any(l.startswith(('import rclpy', 'from rclpy', 'from rosidl')) for l in text.splitlines()))


# ---------------------------------------------------------------- synthetic recordings
T0 = 1000.0       # monotonic start of the synthetic robot
STAMP0 = 5000.0   # header stamps live in another time base, as on the real robot


def build(path, dur=60, odom_gap=None, delayed=False, motion_at=None, cpu_spike=None, ping_loss=None, event_at=None,
          truncate=False, imu_too=False, undock_at=None):
    """Write a synthetic recording; odom_gap=(start, end) in seconds since the start."""
    recs = [{'kind': 'header', 'version': 1, 'hostname': 'tb4-test', 'mono0': T0, 'wall0': 1730000000.0, 'wall_minus_mono': 1.0}]
    n = int(dur * 20)
    for k in range(n + 1):
        orig = k * 0.05
        recv = orig
        if not (imu_too and odom_gap and odom_gap[0] < orig < odom_gap[1] - 1e-9):
            recs.append({'kind': 'msg', 'topic': '/imu', 't': T0 + orig + (0.02 if imu_too else 0.001), 'wall': 0, 'stamp': STAMP0 + orig})
        if odom_gap and odom_gap[0] < orig < odom_gap[1] - 1e-9:
            if not delayed:
                continue
            recv = odom_gap[1] - 0.001 + (orig - odom_gap[0]) * 1e-5   # queued messages arrive in a burst just before the gap ends
        recs.append({'kind': 'msg', 'topic': '/odom', 't': T0 + recv, 'wall': 0, 'stamp': STAMP0 + orig})
    recs.append({'kind': 'msg', 'topic': '/cmd_vel', 't': T0 + 1.0, 'wall': 0, 'stamp': STAMP0, 'vx': 0.0, 'wz': 0.0})
    if motion_at is not None:
        recs.append({'kind': 'msg', 'topic': '/cmd_vel', 't': T0 + motion_at, 'wall': 0, 'stamp': STAMP0 + motion_at, 'vx': 0.15, 'wz': 0.0})
        recs.append({'kind': 'msg', 'topic': '/cmd_vel', 't': T0 + motion_at + 5, 'wall': 0, 'stamp': STAMP0, 'vx': 0.0, 'wz': 0.0})
    if undock_at is not None:
        for k in range(int(dur)):
            recs.append({'kind': 'msg', 'topic': '/dock_status', 't': T0 + k + 0.3, 'wall': 0, 'stamp': STAMP0 + k,
                         'docked': k < undock_at, 'visible': k < undock_at})
    for k in range(int(dur / 0.2)):
        t = k * 0.2
        busy = 95.0 if cpu_spike and cpu_spike[0] <= t <= cpu_spike[1] else 20.0
        recs.append({'kind': 'sys', 't': T0 + t, 'load': [0.9, 0.9, 0.6], 'cpu': {'all': busy, '0': busy, '1': 10.0, '2': 10.0, '3': 10.0},
                     'procs': {'create3_republisher': 17.0, 'turtlebot4_node': 8.0},
                     'net': {'usb0': {'rx_bytes': k * 100, 'rx_errs': 0, 'rx_drop': 0, 'tx_bytes': k * 100, 'tx_errs': 0, 'tx_drop': 0}},
                     'link': {'usb0': ['up', '1']}, 'temp': 51.0})
    for k in range(int(dur)):
        lost = ping_loss and ping_loss[0] <= k <= ping_loss[1]
        recs.append({'kind': 'ping', 't': T0 + k + 0.5, 'host': '192.168.186.2', 'rtt': None if lost else 0.6})
    if event_at is not None:
        recs.append({'kind': 'event', 't': T0 + event_at, 'jt': T0 + event_at, 'source': 'NetworkManager', 'text': 'wlan0: link disconnected'})
    recs.append({'kind': 'footer', 't': T0 + dur, 'elapsed': dur, 'own_cpu_pct': 1.2})
    with open(path, 'w') as f:
        for r in recs:
            f.write(json.dumps(r) + '\n')
        if truncate:
            f.write('{"kind":"msg","topic":"/od')
    return path


def analyze_file(path, **kw):
    header, recs, bad = at.load(path)
    return at.analyze(header, recs, **kw), header, bad


def gaps_of(res, topic='/odom'):
    return [g for g in res['gaps'] if g['topic'] == topic]


# A: 1.0 s /odom gap at motion start, publisher stopped
pa_ = build(os.path.join(OUT, 'a_motion.jsonl'), odom_gap=(10.0, 11.0), motion_at=9.95)
res, hdr, bad = analyze_file(pa_)
g = gaps_of(res)
check('A motion start: exactly one /odom gap, 1.0 s long at 10.0 s, none on /imu',
      len(g) == 1 and abs(g[0]['length'] - 1.0) < 1e-6 and abs(g[0]['start'] - 10.0) < 1e-6 and not gaps_of(res, '/imu'),
      str([(x['start'], x['length']) for x in g]))
check('A motion start: stamp gap equals receive gap -> publisher stopped', g[0]['cls'] == 'publisher stopped', g[0]['why'])
check('A motion start: verdict says motion start and nothing about CPU or ping',
      any('motion start' in v for v in g[0]['verdicts']) and not any(('CPU' in v or 'ping' in v) for v in g[0]['verdicts']), str(g[0]['verdicts']))
check('A motion start: median 50 ms, threshold 250 ms, rate 20 Hz',
      abs(res['topics']['/odom']['median'] - 0.05) < 1e-6 and abs(res['topics']['/odom']['threshold'] - 0.25) < 1e-6
      and abs(res['topics']['/odom']['rate'] - 20.0) < 0.5)

# B: gap at a CPU spike, messages delayed (stamps continuous)
pb_ = build(os.path.join(OUT, 'b_cpu.jsonl'), odom_gap=(30.0, 31.0), delayed=True, motion_at=5.0, cpu_spike=(29.5, 31.5))
res, _, _ = analyze_file(pb_)
g = gaps_of(res)
check('B CPU spike: one gap of 1.0 s classified as delayed delivery (stamp gap 0.05 s)',
      len(g) == 1 and g[0]['cls'] == 'delivery delayed' and abs(g[0]['stamp_gap'] - 0.05) < 1e-6, str(g and (g[0]['cls'], g[0]['stamp_gap'])))
check('B CPU spike: verdict CPU > 90 %, not motion start, not ping',
      any('CPU > 90' in v for v in g[0]['verdicts']) and not any('motion start' in v for v in g[0]['verdicts'])
      and not any('ping' in v for v in g[0]['verdicts']), str(g[0]['verdicts']))
check('B CPU spike: context has max total 95 %, busiest core 0, top process create3_republisher',
      g[0]['ctx']['cpu_max_total'] == 95.0 and g[0]['ctx']['cpu_max_core'] == ('0', 95.0)
      and g[0]['ctx']['top_process'][0] == 'create3_republisher')
res_hi, _, _ = analyze_file(pb_, cpu_thr=99.0)
check('B CPU spike: --cpu-threshold 99 removes the CPU verdict (core 0 still flagged saturated)',
      not any('CPU > 99' in v for v in gaps_of(res_hi)[0]['verdicts']) and any('core' in v for v in gaps_of(res_hi)[0]['verdicts']))

# C: ping loss and a NetworkManager event
pc_ = build(os.path.join(OUT, 'c_ping.jsonl'), odom_gap=(45.0, 46.0), ping_loss=(44, 46), event_at=45.2)
res, _, _ = analyze_file(pc_)
g = gaps_of(res)
vs = g[0]['verdicts'] if g else []
check('C ping loss: verdicts name base ping loss and the network event',
      len(g) == 1 and any('base ping loss' in v and '192.168.186.2' in v for v in vs) and any('network/kernel event' in v and 'link disconnected' in v for v in vs), str(vs))
check('C ping loss: loss count in the window is 3 pings', g[0]['ctx']['pings']['192.168.186.2']['lost'] == 3, str(g[0]['ctx']['pings']))

# D: clean run
pd_ = build(os.path.join(OUT, 'd_clean.jsonl'), motion_at=10.0)
res, _, _ = analyze_file(pd_)
check('D clean run: no gaps at all, /odom and /imu at 20 Hz', not res['gaps'] and abs(res['topics']['/imu']['rate'] - 20.0) < 0.5)
txt = at.report(res, {'hostname': 'x'}, 'd.jsonl')
check('D clean run: report says so', 'No gaps found.' in txt and '/odom' in txt)

# E: gap with no cause; short gaps below the threshold are ignored
pe_ = build(os.path.join(OUT, 'e_idle.jsonl'), odom_gap=(20.0, 20.6), motion_at=40.0)
res, _, _ = analyze_file(pe_)
g = gaps_of(res)
check('E idle gap 0.6 s: verdict "no correlate found"', len(g) == 1 and g[0]['verdicts'] == ['no correlate found'], str(g and g[0]['verdicts']))
res2, _, _ = analyze_file(build(os.path.join(OUT, 'e2.jsonl'), odom_gap=(20.0, 20.2)))
check('gap of 0.2 s is below max(3 x median, 0.25 s) and is not reported; --min-gap 0.1 would', not res2['gaps']
      and at.find_gaps([0, .05, .1, .3, .35, .4], 0.1)[2] != [])

# F: truncated last line (killed run) and no footer
pf_ = build(os.path.join(OUT, 'f_cut.jsonl'), odom_gap=(10.0, 11.0), truncate=True)
res, hdr, bad = analyze_file(pf_)
check('F truncated file: bad line counted, gap still found', bad == 1 and len(gaps_of(res)) == 1)

# G0: grouping, undock as motion start, motion window, gzip input
pg_ = build(os.path.join(OUT, 'g_group.jsonl'), odom_gap=(30.0, 31.5), imu_too=True, motion_at=27.5)
res, _, _ = analyze_file(pg_)
ev = res['events']
check('group: odom and imu stall starting 20 ms apart are ONE event "base stall: /imu /odom"',
      len(res['gaps']) == 2 and len(ev) == 1 and ev[0]['name'] == 'base stall' and ev[0]['topics'] == ['/imu', '/odom'], str([(e['name'], e['topics']) for e in ev]))
check('motion window: start 2.5 s before the stall found by default (3 s), not with --motion-window 1',
      any('motion start' in v and '2.5' in v for v in ev[0]['verdicts'])
      and not any('motion start' in v for v in analyze_file(pg_, motion_window=1.0)[0]['events'][0]['verdicts']))
check('motion window: "robot commanded to move at gap start" is its own verdict, also with the short window',
      any('commanded to move' in v for v in analyze_file(pg_, motion_window=1.0)[0]['events'][0]['verdicts']))
txt = at.report(res, {'hostname': 'x'}, 'g.jsonl')
check('report: grouped event line and per-topic lines', 'Event 1: base stall: /imu /odom' in txt and '1 events' in txt.replace('into 1 events', '1 events'))
pu_ = build(os.path.join(OUT, 'u_undock.jsonl'), odom_gap=(12.0, 13.0), undock_at=10)
res, _, _ = analyze_file(pu_)
g = gaps_of(res)
check('undock: /dock_status is_docked true -> false at 10 s counts as motion start for a stall at 12 s (no /cmd_vel at all)',
      len(g) == 1 and g[0]['ctx']['motion_start'] is not None and abs(g[0]['ctx']['motion_start'] - 9.3) < 1.0 and 'undock' in g[0]['ctx']['motion_label']
      and any('motion start' in v and 'undock' in v for v in g[0]['verdicts']), str(g and g[0]['verdicts']))
gz = os.path.join(OUT, 'a_motion.jsonl.gz')
with open(pa_, 'rb') as fi, gzip.open(gz, 'wb') as fo:
    fo.write(fi.read())
rg, _, _ = analyze_file(gz)
check('gzip input is read transparently and gives the same gaps', [(x['topic'], round(x['start'], 3)) for x in rg['gaps']] == [(x['topic'], round(x['start'], 3)) for x in analyze_file(pa_)[0]['gaps']] and rg['gaps'])

# CDR: hand-built serialized messages (4-byte encapsulation header, then little or big endian fields)
def cdr(order, body):
    return (b'\x00\x01\x00\x00' if order == '<' else b'\x00\x00\x00\x00') + body


for o, name in (('<', 'little'), ('>', 'big')):
    hdr_msg = cdr(o, struct.pack(o + 'iI', 1730142335, 250000000) + struct.pack(o + 'I', 3) + b'odom\x00\x00\x00\x00' + b'x' * 40)
    check('CDR %s endian: header stamp read from the first 8 bytes after the encapsulation header' % name,
          rt.cdr_byte_order(hdr_msg) == o and abs(rt.cdr_header_stamp(hdr_msg) - 1730142335.25) < 1e-6, str(rt.cdr_header_stamp(hdr_msg)))
    tf_msg = cdr(o, struct.pack(o + 'I', 2) + struct.pack(o + 'iI', 42, 500000000) + struct.pack(o + 'I', 6) + b'odom\x00\x00' + b'\x00' * 60)
    check('CDR %s endian: TFMessage stamp read after the sequence length' % name, abs(rt.cdr_tf_stamp(tf_msg) - 42.5) < 1e-9)
    check('CDR %s endian: empty TF sequence gives None' % name, rt.cdr_tf_stamp(cdr(o, struct.pack(o + 'I', 0))) is None)
check('CDR: short or garbage data gives None, nanosec >= 1e9 rejected',
      rt.cdr_header_stamp(b'') is None and rt.cdr_header_stamp(b'\x00\x01\x00\x00\x01\x00') is None and rt.cdr_tf_stamp(b'\x00\x01\x00') is None
      and rt.cdr_header_stamp(cdr('<', struct.pack('<iI', 1, 2000000000))) is None)
check('stamp_mode: header-first class, TFMessage, other',
      rt.stamp_mode(NS(get_fields_and_field_types=lambda: {'header': 'std_msgs/Header', 'x': 'double'})) == 'header'
      and rt.stamp_mode(NS(get_fields_and_field_types=lambda: {'transforms': 'sequence<geometry_msgs/TransformStamped>'})) == 'tf'
      and rt.stamp_mode(NS(get_fields_and_field_types=lambda: {'data': 'int32'})) is None and rt.stamp_mode(object()) is None)
check('recorder args: --light lowers the system rate to 0.5 s and keeps only /odom /cmd_vel /dock_status; explicit --period wins',
      rt.parse_args(['--light']).period == 0.5 and rt.parse_args([]).period == 0.2 and rt.parse_args(['--light', '--period', '0.3']).period == 0.3
      and set(rt.LIGHT_TOPICS) == {'/odom', '/cmd_vel', '/dock_status'})

# G: unit checks of the classification and the motion detector
check('classify_stamp: stopped / delayed / unclear / no stamp',
      at.classify_stamp(1.0, 0.98)[0] == 'publisher stopped' and at.classify_stamp(1.0, 0.05)[0] == 'delivery delayed'
      and at.classify_stamp(1.0, 0.55)[0] == 'unclear' and at.classify_stamp(1.0, None)[0] == 'no stamp')
check('motion_starts: zero -> non-zero only, spin counts, a repeated non-zero does not',
      at.motion_starts([{'t': 1, 'vx': 0, 'wz': 0}, {'t': 2, 'vx': .1, 'wz': 0}, {'t': 3, 'vx': .1, 'wz': 0}, {'t': 4, 'vx': 0, 'wz': 0},
                        {'t': 5, 'vx': 0, 'wz': .5}]) == [2, 5])

# H: output files
csv_path, html_path = os.path.join(OUT, 'gaps.csv'), os.path.join(OUT, 'timeline.html')
r = subprocess.run([sys.executable, os.path.join(TOOLS, 'analyze_timing.py'), pc_, '--csv', csv_path, '--html', html_path],
                   capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
csv_text = open(csv_path, encoding='utf-8').read() if os.path.exists(csv_path) else ''
html_text = open(html_path, encoding='utf-8').read() if os.path.exists(html_path) else ''
check('CLI: exit 0, report on stdout, CSV has header and one gap row',
      r.returncode == 0 and 'Event 1: gap: /odom' in r.stdout and csv_text.startswith('event,topic,start_s') and len(csv_text.strip().splitlines()) == 2, r.stderr[-200:])
check('HTML: self-contained (inline svg, no scripts, no src/href, no external links), shows the gap and loss',
      '<svg' in html_text and '<script' not in html_text and ' src=' not in html_text and 'href=' not in html_text
      and 'https://' not in html_text and 'class="gap"' in html_text and 'class="loss"' in html_text)
r = subprocess.run([sys.executable, os.path.join(TOOLS, 'analyze_timing.py'), os.path.join(OUT, 'missing.jsonl')], capture_output=True, text=True)
check('CLI: missing file exits 2 with a message', r.returncode == 2 and 'cannot read' in r.stderr)

# I: the recorder itself, system sampling only (works anywhere; /proc files are simply absent off Linux)
rec_path = os.path.join(OUT, 'rec.jsonl')
env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
r = subprocess.run([sys.executable, os.path.join(TOOLS, 'record_timing.py'), '--no-ros', '--no-ping', '--no-journal', '--duration', '1.2',
                    '--period', '0.1', '--out', rec_path], capture_output=True, text=True, env=env, timeout=30)
hdr, recs, bad = at.load(rec_path) if os.path.exists(rec_path) else ({}, [], 0)
kinds = {x['kind'] for x in recs}
check('recorder run (--no-ros): exit 0, header, sys samples, footer with own CPU, prints own CPU use',
      r.returncode == 0 and hdr.get('kind') == 'header' and abs(hdr['wall_minus_mono'] - (hdr['wall0'] - hdr['mono0'])) < 0.01
      and 'sys' in kinds and 'footer' in kinds and 'own CPU use' in r.stdout and bad == 0, (r.stdout + r.stderr)[-300:])
r = subprocess.run([sys.executable, os.path.join(TOOLS, 'record_timing.py'), '--no-ros', '--no-ping', '--no-journal', '--duration', '1', '--out', rec_path],
                   capture_output=True, text=True, env=env, timeout=30)
check('recorder refuses to overwrite an existing file', r.returncode == 2 and 'exists' in r.stderr)
if os.name == 'posix':
    p = subprocess.Popen([sys.executable, os.path.join(TOOLS, 'record_timing.py'), '--no-ros', '--no-ping', '--no-journal', '--duration', '0',
                          '--out', os.path.join(OUT, 'term.jsonl')], stdout=subprocess.PIPE, text=True, env=env)
    time.sleep(1.5)
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=15)
    hdr2, recs2, _ = at.load(os.path.join(OUT, 'term.jsonl'))
    check('recorder: SIGTERM ends cleanly with a footer', p.returncode == 0 and any(x['kind'] == 'footer' for x in recs2), out[-200:])
    if os.path.exists('/proc/stat'):
        check('recorder on Linux: sys samples carry cpu, load and net data', any(x.get('cpu') and x.get('load') for x in recs2 if x['kind'] == 'sys'))

print(f'\n{fails} failure(s); generated files are in {OUT}')
sys.exit(1 if fails else 0)
