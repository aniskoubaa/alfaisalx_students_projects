"""Read-only health checklist for the TurtleBot 4: one PASS / WARN / FAIL / INFO row per item, with a fix hint.

Does NOT move the robot and changes nothing: it publishes nothing, calls no service and needs no sudo.
Safe on the dock. It runs the MAINTENANCE.md verification checklist in one go (ROADMAP TB-19):
    Wi-Fi profile and address, turtlebot4.service, ROS environment, base data (/odom rate, /dock_status,
    /battery_state and battery %), Pi vs base clock, lidar USB device and (off the dock) /scan rate and
    valid beams, the largest /odom gap, the clock-fix files (TB-17), CPU temperature, throttling, load,
    free disk, free memory, uptime, the ~/STOP file and running motion programs.
System checks use commands (nmcli, ip, systemctl, lsusb, vcgencmd, pgrep) and files in /proc and /sys.
ROS checks wait up to FIRST_MESSAGE_WAIT s for the first /odom, /dock_status and /battery_state, then
listen for --seconds (default 10). Every check is isolated: one that fails, hangs or crashes gets its own
row and the others still run. Takes about 15 to 25 s, and about 45 s when the base is silent.

Run it on the robot, in a login shell (so ROS is set up):
    python3 health_check.py
    python3 health_check.py --seconds 20 --json ~/robot_code/health.json
    python3 health_check.py > health.txt        # progress goes to the terminal, the report into the file
Exit codes: 0 every row PASS or INFO, 1 at least one WARN, 2 at least one FAIL.
See README.md in this folder.
"""
import argparse
import json
import math
import os
import re
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------- parameters
SECONDS = 10.0                # default ROS measuring window
MAX_SECONDS = 120.0
FIRST_MESSAGE_WAIT = 30.0     # s, wait at most this long for the first /odom, /dock_status and /battery_state
COMMAND_TIMEOUT = 4.0         # s, limit for each system command
CHECK_TIMEOUT = 10.0          # s, limit for each system check (the Wi-Fi check runs two commands)
ODOM_EXPECTED_HZ = 20.0
ODOM_RATE_WARN = 15.0         # Hz, WARN below this
SCAN_RATE_WARN = 5.0          # Hz, WARN below this (7.7 Hz is normal)
SCAN_VALID_WARN = 40.0        # %, WARN below this share of valid beams (72 % in the lab on 2026-10-04)
BATTERY_WARN = 0.30           # fraction, WARN below this
CLOCK_LIMIT = 5.0             # s, Pi clock minus base header stamp must be within +/- this
ODOM_GAP_WARN = 0.3           # s, WARN above this (motion programs hold still above 0.3 s)
ODOM_GAP_FAIL = 2.0           # s, FAIL above this (motion programs abort above 2.0 s)
CPU_TEMP_WARN = 75.0          # C, WARN above this
CPU_TEMP_FAIL = 82.0          # C, FAIL above this (the Pi 4 starts throttling at about 80 C)
DISK_WARN = 2e9               # bytes free on /, WARN below this
WIFI_DEVICE = 'wlan0'
FALLBACK_PROFILE = 'netplan-wlan0-Turtlebot4'   # the robot's own access point
FALLBACK_PREFIX = '10.42.0.'
LIDAR_USB_ID = '10c4:ea60'    # Silicon Labs CP210x USB bridge inside the RPLIDAR
RPLIDAR_DEV = '/dev/RPLIDAR'
STOP_FILE = os.path.expanduser('~/STOP')
CLOCK_FIX_FILES = ('/etc/systemd/system/tb4-https-time.timer',
                   '/etc/systemd/system/turtlebot4.service.d/10-wait-for-clock.conf')
THERMAL_FILE = '/sys/class/thermal/thermal_zone0/temp'
MEMINFO_FILE = '/proc/meminfo'
LOADAVG_FILE = '/proc/loadavg'
UPTIME_FILE = '/proc/uptime'
MOTION_PROGRAMS = ('motion_shapes.py', 'more_shapes.py', 'wall_approach.py', 'keep_distance.py', 'campaign.sh')
RESTART_BASE = 'curl -X POST http://192.168.186.2/api/restart-app'
BASE_HINT = f'restart the Create 3 base app: `{RESTART_BASE}`, wait for the chime, run again'

STATUSES = ('PASS', 'INFO', 'WARN', 'FAIL')
# Report rows in print order: (id, name). The id is the key in the JSON file.
ROWS = [
    ('wifi', 'Wi-Fi'),
    ('ros_service', 'turtlebot4.service'),
    ('ros_env', 'ROS environment'),
    ('odom_rate', 'Base /odom'),
    ('dock_status', 'Base /dock_status'),
    ('battery', 'Base /battery_state'),
    ('clock', 'Clock Pi vs base'),
    ('lidar_usb', 'Lidar USB'),
    ('lidar_scan', 'Lidar /scan'),
    ('odom_gaps', 'Odometry gaps'),
    ('clock_fix', 'Clock fix (TB-17)'),
    ('cpu_temp', 'CPU temperature'),
    ('throttled', 'Throttling'),
    ('load', 'Load average'),
    ('disk', 'Disk free on /'),
    ('memory', 'Memory'),
    ('uptime', 'Uptime'),
    ('stop_file', 'STOP file'),
    ('motion_programs', 'Motion programs'),
]
ROS_ROWS = ('odom_rate', 'dock_status', 'battery', 'clock', 'lidar_scan', 'odom_gaps')
THROTTLE_BITS = {0: 'under-voltage now', 1: 'frequency capped now', 2: 'throttled now',
                 3: 'soft temperature limit now', 16: 'under-voltage since boot',
                 17: 'frequency capped since boot', 18: 'throttled since boot',
                 19: 'soft temperature limit since boot'}

stop_request = None


def log(text):
    """Progress line on stderr, so `> file` keeps only the report."""
    print(f'{time.strftime("%H:%M:%S")} {text}', file=sys.stderr, flush=True)


# ---------------------------------------------------------------- pure helpers (no ROS, no system access)
# Each classify_* function returns (status, result, hint); hint is '' when there is nothing to do.
def exit_code_for(statuses):
    """0 if every status is PASS or INFO, 1 if any WARN, 2 if any FAIL."""
    statuses = list(statuses)
    if 'FAIL' in statuses:
        return 2
    if 'WARN' in statuses:
        return 1
    return 0


def first_line(text):
    for line in (text or '').splitlines():
        if line.strip():
            return line.strip()
    return ''


def split_terse(line):
    """Split one line of `nmcli -t` output on ':' (nmcli writes ':' inside a value as '\\:')."""
    fields, cur, i = [], '', 0
    while i < len(line):
        c = line[i]
        if c == '\\' and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ':':
            fields.append(cur)
            cur = ''
        else:
            cur += c
        i += 1
    fields.append(cur)
    return fields


def parse_nmcli_active(text):
    """`nmcli -t -f NAME,DEVICE connection show --active` -> {device: connection name}."""
    out = {}
    for line in (text or '').splitlines():
        f = split_terse(line.strip())
        if len(f) == 2 and f[1]:
            out[f[1]] = f[0]
    return out


def parse_ip_brief(text):
    """`ip -4 -br addr show wlan0` ('wlan0   UP   10.87.10.205/18') -> ['10.87.10.205/18']."""
    addrs = []
    for line in (text or '').splitlines():
        addrs += [p for p in line.split()[2:] if re.fullmatch(r'\d+\.\d+\.\d+\.\d+(/\d+)?', p)]
    return addrs


def classify_wifi(profile, addresses, nmcli_error=None):
    name = profile or (f'unknown ({nmcli_error})' if nmcli_error else 'none')
    if not addresses:
        return ('FAIL', f'no IPv4 address on {WIFI_DEVICE} (connection: {name})',
                'check `nmcli device status`; it should be on Students or its own Turtlebot4 network '
                '(HOW-TO-CONNECT.md)')
    addr = ', '.join(addresses)
    if profile == FALLBACK_PROFILE or any(a.startswith(FALLBACK_PREFIX) for a in addresses):
        return ('WARN', f'{name} on {WIFI_DEVICE}, {addr}: the fallback access point, not Students',
                'Students is out of range or failed; laptops reach the robot on the Turtlebot4 network '
                '(HOW-TO-CONNECT.md)')
    if profile is None:
        return ('WARN', f'{addr} on {WIFI_DEVICE}, but connection {name}',
                'run `nmcli -t -f NAME,DEVICE connection show --active` (expected Students:wlan0)')
    return 'PASS', f'{profile} on {WIFI_DEVICE}, {addr}', ''


def classify_service(state):
    state = (state or '').strip() or 'unknown'
    if state == 'active':
        return 'PASS', 'active', ''
    if state in ('activating', 'reloading'):
        return 'WARN', f'{state} (still starting)', 'wait 2 minutes after power-on, then run this again'
    return ('FAIL', state, 'ROS is not running: see `systemctl status turtlebot4`, `journalctl -u turtlebot4 -b`; '
            'a restart needs an admin')


def classify_ros_env(domain_id, rmw, distro):
    text = (f'ROS_DISTRO {distro or "unset"}, ROS_DOMAIN_ID {domain_id or "unset (0)"}, '
            f'RMW_IMPLEMENTATION {rmw or "unset (Fast DDS)"}')
    ok = bool(distro) and (domain_id or '0').strip() == '0' and (rmw or 'rmw_fastrtps_cpp') == 'rmw_fastrtps_cpp'
    if ok:
        return 'PASS', text, ''
    return ('WARN', text,
            'use a login shell, or first `source /etc/turtlebot4/setup.bash` (MAINTENANCE.md checklist step 4)')



def window_gaps(times, start, end):
    """Arrival times inside the window [start, end] -> count, rate (count / window length), largest gap.

    Same idea as gap_stats() in sensor_report.py, but the window edges count as boundaries, so a topic that
    stops halfway shows the silence up to the end of the window instead of looking healthy.
    """
    out = {'count': len(times), 'rate_hz': None, 'max_gap_s': None, 'max_gap_at_s': None}
    span = end - start
    if span <= 0:
        return out
    points = [start] + sorted(times) + [end]
    gaps = [b - a for a, b in zip(points, points[1:])]
    i = max(range(len(gaps)), key=gaps.__getitem__)
    out.update(rate_hz=len(times) / span, max_gap_s=gaps[i], max_gap_at_s=points[i] - start)
    return out


def classify_odom_rate(count, rate_hz, seconds):
    if not count:
        return 'FAIL', f'no /odom in {seconds:.0f} s (the base is silent)', BASE_HINT
    rate_hz = rate_hz or 0.0
    text = f'{rate_hz:.1f} Hz, {count} messages (expected about {ODOM_EXPECTED_HZ:.0f} Hz)'
    if rate_hz < ODOM_RATE_WARN:
        return ('WARN', text + f', below {ODOM_RATE_WARN:g} Hz',
                f'run `python3 sensor_report.py --seconds 60`; if it stays low: `{RESTART_BASE}`')
    return 'PASS', text, ''


def classify_received(topic, seen, detail=''):
    if seen:
        return 'PASS', 'received' + (f', {detail}' if detail else ''), ''
    return 'FAIL', f'no {topic} message', BASE_HINT


def classify_battery(seen, fraction):
    if not seen:
        return classify_received('/battery_state', False)
    if fraction is None or not math.isfinite(fraction):
        return 'WARN', 'received, but without a battery percentage', 'look at `ros2 topic echo --once /battery_state`'
    text = f'battery {round(100 * fraction, 1):g} %'
    if fraction < BATTERY_WARN:
        return ('WARN', text + f' (WARN below {100 * BATTERY_WARN:.0f} %)',
                'charge it on the dock (README.md, Undock and dock)')
    return 'PASS', text, ''


def classify_clock(diff_s, pi_time=''):
    """diff_s = Pi clock minus base header stamp (median), None if no base message arrived."""
    pi = f'; Pi clock {pi_time}' if pi_time else ''
    if diff_s is None:
        return ('INFO', 'not measured: no message from the base' + pi,
                'a Pi/base clock mismatch can silence the base: MAINTENANCE.md, incident '
                '"Create 3 base stopped responding"')
    side = 'ahead of' if diff_s >= 0 else 'behind'
    text = f'Pi {abs(diff_s):.2f} s {side} the base stamps (limit {CLOCK_LIMIT:g} s){pi}'
    if abs(diff_s) < CLOCK_LIMIT:
        return 'PASS', text, ''
    return ('FAIL', text, 'the base may go silent: MAINTENANCE.md, incident "Create 3 base stopped responding"; '
            'do not change the clock while ROS runs')


def classify_lidar_usb(lsusb_text, dev_exists, dev_target=None):
    """lsusb_text None means lsusb was not available; the device link is then the only evidence."""
    usb = None if lsusb_text is None else LIDAR_USB_ID in lsusb_text.lower()
    parts = ['lsusb not available' if usb is None else
             f'CP210x ({LIDAR_USB_ID}) in lsusb' if usb else f'no CP210x ({LIDAR_USB_ID}) in lsusb',
             f'{RPLIDAR_DEV} -> {dev_target}' if dev_exists else f'no {RPLIDAR_DEV}']
    if usb is False or not dev_exists:
        return ('FAIL', ', '.join(parts),
                'power off, reseat the lidar USB cable at both ends, boot '
                '(MAINTENANCE.md, incident "lidar not detected")')
    return 'PASS', ', '.join(parts), ''


def classify_scan(docked, count, rate_hz, valid_pct, beams=None, publishers=None):
    pub = '' if publishers is None else f' (/scan publishers: {publishers})'
    if docked:
        return ('INFO', 'scan not checked: the lidar is switched off on the dock' + pub,
                'undock and run again to check it')
    if not count:
        if docked is None:
            return ('WARN', 'no /scan, and the dock state is unknown' + pub,
                    'see the Base /dock_status and Lidar USB rows; on the dock no /scan is normal')
        return ('FAIL', 'no /scan off the dock' + pub,
                'see the Lidar USB row; just undocked? wait 10 s for the lidar to spin up, run again')
    rate_hz = rate_hz or 0.0
    text = (f'{rate_hz:.2f} Hz, {beams if beams is not None else "?"} beams, '
            f'{"?" if valid_pct is None else format(valid_pct, ".1f")} % valid')
    problems = []
    if rate_hz < SCAN_RATE_WARN:
        problems.append(f'rate below {SCAN_RATE_WARN:g} Hz')
    if valid_pct is None or valid_pct < SCAN_VALID_WARN:
        problems.append(f'valid beams below {SCAN_VALID_WARN:g} %')
    if problems:
        return ('WARN', f'{text} ({", ".join(problems)})',
                'normal: 7.7 Hz, 70 % valid in a room. Lidar blocked or dirty, Pi overloaded? '
                'Try `python3 lidar_snapshot.py`')
    return 'PASS', text + ' (expected about 7.7 Hz)', ''


def classify_odom_gap(max_gap, at_s, count):
    """Largest /odom arrival gap in the window; None if fewer than 2 messages arrived."""
    if max_gap is None or count < 2:
        return 'INFO', f'not measured ({count} /odom messages in the window)', ''
    limits = f'(WARN > {ODOM_GAP_WARN:g} s, FAIL > {ODOM_GAP_FAIL:g} s)'
    if max_gap > ODOM_GAP_FAIL:
        return ('FAIL', f'largest arrival gap {max_gap:.2f} s, {at_s:.1f} s into the window {limits}',
                'motion programs abort on gaps over 2 s; robot still? run `python3 sensor_report.py --seconds 60`')
    if max_gap > ODOM_GAP_WARN:
        return ('WARN', f'largest arrival gap {max_gap:.2f} s, {at_s:.1f} s into the window {limits}',
                'gaps mostly show up during motion (TB-15); robot still? check the load, run sensor_report.py')
    return 'PASS', f'largest arrival gap {max_gap:.2f} s {limits}; gaps mostly show up during motion', ''


def classify_clock_fix(present):
    """present: {path: True/False} for the clock-fix files."""
    names = [p.rsplit('/', 1)[-1] for p, ok in present.items() if ok]
    if names and len(names) == len(present):
        text = 'installed: ' + ', '.join(names)
    elif names:
        text = 'partly installed: only ' + ', '.join(names)
    else:
        text = 'not installed: ' + ', '.join(p.rsplit('/', 1)[-1] for p in present) + ' absent'
    return 'INFO', text, 'keep or remove is an open decision (ROADMAP.md TB-17); never change the clock while ROS runs'


def parse_thermal(text):
    """thermal_zone0/temp holds millidegrees C, for example '48312'."""
    return int(text.strip()) / 1000.0


def classify_cpu_temp(celsius):
    if celsius is None:
        return 'INFO', f'not available (no {THERMAL_FILE})', ''
    text = f'{celsius:.1f} C (WARN > {CPU_TEMP_WARN:g}, FAIL > {CPU_TEMP_FAIL:g})'
    if celsius > CPU_TEMP_FAIL:
        return 'FAIL', text, 'too hot, the Pi throttles: stop heavy programs, check the airflow, let it cool'
    if celsius > CPU_TEMP_WARN:
        return 'WARN', text, 'running hot: check the airflow around the Pi; see the Throttling row'
    return 'PASS', text, ''


def parse_throttled(text):
    """'throttled=0x50005' -> 0x50005, None if there is no such value."""
    m = re.search(r'throttled=(0x[0-9a-fA-F]+)', text or '')
    return int(m.group(1), 16) if m else None


def classify_throttled(value, error=None):
    if error:
        return 'INFO', error, 'optional check; the CPU temperature row still works'
    if value is None:
        return 'INFO', 'vcgencmd gave no throttled= value', 'optional check; the CPU temperature row still works'
    if value == 0:
        return 'PASS', 'throttled=0x0 (no under-voltage or throttling since boot)', ''
    flags = [name for bit, name in sorted(THROTTLE_BITS.items()) if value >> bit & 1] or ['unknown flags']
    return ('WARN', f'throttled={value:#x}: {", ".join(flags)}',
            'under-voltage: charge the battery on the dock; heat: see CPU temperature')


def parse_loadavg(text):
    """'/proc/loadavg' '1.52 1.31 1.20 3/512 12345' -> (1.52, 1.31, 1.2)."""
    return tuple(float(x) for x in text.split()[:3])


def classify_load(loads, cpus):
    l1, l5, l15 = loads
    text = f'{l1:.2f} {l5:.2f} {l15:.2f} (1, 5, 15 min; {cpus} CPUs)'
    hint = 'high load can delay /odom and /scan (load 3.4 came with a 1.0 s /odom gap)' if l1 >= cpus else ''
    return 'INFO', text, hint


def classify_disk(free_bytes, total_bytes):
    text = f'{free_bytes / 1e9:.2f} GB free of {total_bytes / 1e9:.1f} GB'
    if free_bytes < DISK_WARN:
        return ('WARN', text + f' (WARN below {DISK_WARN / 1e9:g} GB)',
                'delete old logs in ~/robot_code/logs; ~/.vscode-server (600 MB) is safe to delete (MAINTENANCE.md R9)')
    return 'PASS', text, ''


def parse_meminfo(text):
    """/proc/meminfo -> {name: kB}."""
    out = {}
    for line in text.splitlines():
        name, _, rest = line.partition(':')
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[name.strip()] = int(parts[0])
    return out


def classify_memory(info):
    avail = info.get('MemAvailable', info.get('MemFree'))
    total = info.get('MemTotal')
    if avail is None or total is None:
        return 'INFO', 'not available (no MemAvailable / MemTotal)', ''
    return 'INFO', f'{avail * 1024 / 1e6:.0f} MB available of {total * 1024 / 1e6:.0f} MB', ''


def parse_uptime(text):
    """/proc/uptime '5123.45 17800.10' -> 5123.45 s."""
    return float(text.split()[0])


def format_duration(seconds):
    m = int(seconds // 60)
    d, h, m = m // 1440, m // 60 % 24, m % 60
    return (f'{d} d ' if d else '') + (f'{h} h ' if d or h else '') + f'{m} min'


def classify_uptime(seconds):
    return 'INFO', f'up {format_duration(seconds)}', ''


def classify_stop_file(exists):
    if exists:
        return 'WARN', '~/STOP exists: motion programs refuse to start', 'rm ~/STOP'
    return 'PASS', '~/STOP not present', ''


def motion_pattern():
    """pgrep -f pattern. '[m]otion_shapes' matches 'motion_shapes' but not the pattern text itself."""
    return '|'.join('[' + p[0] + ']' + re.escape(p[1:]) for p in MOTION_PROGRAMS)


def parse_pgrep(text, own_pid):
    """`pgrep -af` lines 'PID command line' -> [(pid, command)], without our own process."""
    procs = []
    for line in (text or '').splitlines():
        pid, _, cmd = line.strip().partition(' ')
        if pid.isdigit() and int(pid) != own_pid:
            procs.append((int(pid), cmd.strip()))
    return procs


def classify_motion_programs(procs):
    if not procs:
        return 'INFO', 'none running', ''
    shown = '; '.join(f'{pid} {cmd[:70]}' for pid, cmd in procs)
    return ('INFO', f'running: {shown}',
            'a program may be driving the robot: watch it; to stop it: touch ~/STOP')


def describe_error(e):
    if isinstance(e, subprocess.TimeoutExpired):
        cmd = e.cmd if isinstance(e.cmd, str) else e.cmd[0]
        return f'{cmd} did not answer within {e.timeout:g} s'
    if isinstance(e, FileNotFoundError) and e.filename:
        return f'{e.filename}: not found'
    return f'{type(e).__name__}: {e}'


def check_error_row(error):
    return ('WARN', f'check failed: {error}',
            'run this item by hand (MAINTENANCE.md, Verification checklist) and report the output')


# ---------------------------------------------------------------- system checks (commands and files, read only)
def run_cmd(args):
    """Run a command without a shell; returns (exit code, stdout, stderr). Raises on a missing command or timeout."""
    r = subprocess.run(args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
                       env=dict(os.environ, LC_ALL='C'))
    return r.returncode, r.stdout, r.stderr


def read_text(path):
    with open(path) as f:
        return f.read()


def check_wifi():
    profile, error = None, None
    try:
        rc, out, err = run_cmd(['nmcli', '-t', '-f', 'NAME,DEVICE', 'connection', 'show', '--active'])
        profile = parse_nmcli_active(out).get(WIFI_DEVICE)
        if rc != 0:
            error = 'nmcli: ' + (first_line(err) or f'exit code {rc}')
    except (OSError, subprocess.SubprocessError) as e:
        error = describe_error(e)
    rc, out, err = run_cmd(['ip', '-4', '-br', 'addr', 'show', WIFI_DEVICE])
    return classify_wifi(profile, parse_ip_brief(out), error)


def check_service():
    rc, out, err = run_cmd(['systemctl', 'is-active', 'turtlebot4'])   # exit code 3 = inactive; the state is on stdout
    return classify_service(first_line(out) or first_line(err))


def check_ros_env():
    return classify_ros_env(os.environ.get('ROS_DOMAIN_ID'), os.environ.get('RMW_IMPLEMENTATION'),
                            os.environ.get('ROS_DISTRO'))


def check_lidar_usb():
    try:
        rc, out, err = run_cmd(['lsusb'])
        text = out if rc == 0 else None
    except FileNotFoundError:
        text = None
    exists = os.path.exists(RPLIDAR_DEV)
    return classify_lidar_usb(text, exists, os.path.realpath(RPLIDAR_DEV) if exists else None)


def check_clock_fix():
    return classify_clock_fix({p: os.path.exists(p) for p in CLOCK_FIX_FILES})


def check_cpu_temp():
    try:
        text = read_text(THERMAL_FILE)
    except FileNotFoundError:
        return classify_cpu_temp(None)
    return classify_cpu_temp(parse_thermal(text))


def check_throttled():
    try:
        rc, out, err = run_cmd(['vcgencmd', 'get_throttled'])
    except FileNotFoundError:
        return classify_throttled(None, 'vcgencmd not installed')
    if rc != 0:
        return classify_throttled(None, f'vcgencmd failed: {first_line(err) or first_line(out) or f"exit code {rc}"}')
    return classify_throttled(parse_throttled(out))


def check_load():
    return classify_load(parse_loadavg(read_text(LOADAVG_FILE)), os.cpu_count() or 1)


def check_disk():
    usage = shutil.disk_usage('/')
    return classify_disk(usage.free, usage.total)


def check_memory():
    return classify_memory(parse_meminfo(read_text(MEMINFO_FILE)))


def check_uptime():
    return classify_uptime(parse_uptime(read_text(UPTIME_FILE)))


def check_stop_file():
    return classify_stop_file(os.path.exists(STOP_FILE))


def check_motion_programs():
    rc, out, err = run_cmd(['pgrep', '-af', motion_pattern()])   # exit code 1 = no match
    if rc not in (0, 1):
        raise RuntimeError(f'pgrep exit code {rc}: {first_line(err)}')
    return classify_motion_programs(parse_pgrep(out, os.getpid()))


SYSTEM_CHECKS = {'wifi': check_wifi, 'ros_service': check_service, 'ros_env': check_ros_env,
                 'lidar_usb': check_lidar_usb, 'clock_fix': check_clock_fix, 'cpu_temp': check_cpu_temp,
                 'throttled': check_throttled, 'load': check_load, 'disk': check_disk, 'memory': check_memory,
                 'uptime': check_uptime, 'stop_file': check_stop_file, 'motion_programs': check_motion_programs}


def isolated(check, timeout=CHECK_TIMEOUT):
    """Run one check in a helper thread. A check that raises or hangs gives a WARN row; the others go on."""
    box = {}

    def target():
        try:
            box['row'] = check()
        except Exception as e:      # any failure of one check must not stop the others
            box['error'] = describe_error(e)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return check_error_row(f'no answer within {timeout:g} s')
    if 'error' in box:
        return check_error_row(box['error'])
    return box['row']


def guarded(make_row):
    try:
        return make_row()
    except Exception as e:          # same isolation for the ROS rows
        return check_error_row(describe_error(e))


# ---------------------------------------------------------------- ROS checks (listen only)
def stamp_seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


def measure_ros(seconds, stopped):
    """Listen to /odom, /dock_status, /battery_state and /scan. Returns raw measurements; 'error' is set if ROS
    could not be used. Publishes nothing."""
    m = {'error': None, 'window': (0.0, 0.0), 'odom': [], 'scan': [], 'scan_valid': [], 'scan_beams': None,
         'odom_clock': [], 'base_clock': [], 'odom_seen': False, 'dock_seen': False, 'docked': None,
         'battery_seen': False, 'battery': None, 'scan_publishers': None, 'dock_type': True}
    try:   # imported here, so the system checks still run when ROS is not set up in this shell
        import rclpy
        from nav_msgs.msg import Odometry
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from rclpy.signals import SignalHandlerOptions
        from sensor_msgs.msg import BatteryState, LaserScan
    except ImportError as e:
        m['error'] = f'ROS 2 Python packages not found ({e})'
        return m
    try:
        from irobot_create_msgs.msg import DockStatus
    except ImportError:
        DockStatus = None
        m['dock_type'] = False
    recording = [False]

    def on_odom(msg):
        m['odom_seen'] = True
        m['odom_clock'].append(time.time() - stamp_seconds(msg.header.stamp))
        if recording[0]:
            m['odom'].append(time.monotonic())

    def on_dock(msg):
        m['dock_seen'], m['docked'] = True, msg.is_docked
        m['base_clock'].append(time.time() - stamp_seconds(msg.header.stamp))

    def on_battery(msg):
        m['battery_seen'], m['battery'] = True, msg.percentage
        m['base_clock'].append(time.time() - stamp_seconds(msg.header.stamp))

    def on_scan(msg):
        if recording[0]:
            m['scan'].append(time.monotonic())
            m['scan_beams'] = len(msg.ranges)
            valid = sum(1 for r in msg.ranges if msg.range_min < r < msg.range_max)
            m['scan_valid'].append(valid / max(1, len(msg.ranges)))

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # Ctrl+C is handled by on_signal
    node = None
    try:
        node = Node('health_check')
        node.create_subscription(Odometry, '/odom', on_odom, qos_profile_sensor_data)
        node.create_subscription(BatteryState, '/battery_state', on_battery, qos_profile_sensor_data)
        node.create_subscription(LaserScan, '/scan', on_scan, qos_profile_sensor_data)
        if DockStatus is not None:
            node.create_subscription(DockStatus, '/dock_status', on_dock, qos_profile_sensor_data)
        log(f'waiting up to {FIRST_MESSAGE_WAIT:.0f} s for /odom, /dock_status and /battery_state '
            '(ROS starts slowly on the Pi)')
        end = time.monotonic() + FIRST_MESSAGE_WAIT
        while not stopped() and time.monotonic() < end and not (
                m['odom_seen'] and m['battery_seen'] and (m['dock_seen'] or DockStatus is None)):
            rclpy.spin_once(node, timeout_sec=0.1)
        log(f'measuring for {seconds:g} s (Ctrl+C to stop early)')
        recording[0] = True
        start = time.monotonic()
        while not stopped() and time.monotonic() < start + seconds:
            rclpy.spin_once(node, timeout_sec=0.05)
        recording[0] = False
        m['window'] = (start, time.monotonic())
        try:
            m['scan_publishers'] = node.count_publishers('/scan')
        except Exception:
            pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
    return m


def ros_rows(m):
    """Turn the raw ROS measurements into (report rows, measurements); each row is isolated."""
    if m.get('error'):
        row = ('FAIL', f'not checked: {m["error"]}',
               'run it in a login shell on the robot, or first: source /etc/turtlebot4/setup.bash')
        return {k: row for k in ROS_ROWS}, {'window_s': 0.0}
    start, end = m['window']
    odom = window_gaps(m['odom'], start, end)
    scan = window_gaps(m['scan'], start, end)
    diffs = m['odom_clock'] or m['base_clock']
    clock = statistics.median(diffs) if diffs else None
    valid = 100 * statistics.mean(m['scan_valid']) if m['scan_valid'] else None
    docked = 'unknown' if m['docked'] is None else 'yes' if m['docked'] else 'no'
    rows = {
        'odom_rate': guarded(lambda: classify_odom_rate(odom['count'], odom['rate_hz'], end - start)),
        'dock_status': guarded(lambda: classify_received('/dock_status', m['dock_seen'], f'docked: {docked}')
                               if m['dock_type'] else ('WARN', 'not checked: irobot_create_msgs not found',
                                                       'first: source /etc/turtlebot4/setup.bash')),
        'battery': guarded(lambda: classify_battery(m['battery_seen'], m['battery'])),
        'clock': guarded(lambda: classify_clock(clock, time.strftime('%Y-%m-%d %H:%M:%S'))),
        'lidar_scan': guarded(lambda: classify_scan(m['docked'], scan['count'], scan['rate_hz'], valid,
                                                    m['scan_beams'], m['scan_publishers'])),
        'odom_gaps': guarded(lambda: classify_odom_gap(odom['max_gap_s'], odom['max_gap_at_s'], odom['count'])),
    }
    measurements = {
        'window_s': round(end - start, 2), 'odom_count': odom['count'],
        'odom_rate_hz': None if odom['rate_hz'] is None else round(odom['rate_hz'], 2),
        'odom_max_gap_s': None if odom['count'] < 2 else round(odom['max_gap_s'], 3),
        'clock_pi_minus_base_s': None if clock is None else round(clock, 3),
        'docked': m['docked'],
        'battery_percent': None if m['battery'] is None or not math.isfinite(m['battery'])
        else round(100 * m['battery'], 1),
        'scan_count': scan['count'], 'scan_rate_hz': None if not scan['count'] else round(scan['rate_hz'], 2),
        'scan_beams': m['scan_beams'], 'scan_valid_percent': None if valid is None else round(valid, 1),
        'scan_publishers': m['scan_publishers'],
    }
    return rows, measurements


# ---------------------------------------------------------------- report
def build_report(rows, measurements, window_s, host):
    checks = [{'id': key, 'check': name, 'status': rows[key][0], 'result': rows[key][1], 'hint': rows[key][2]}
              for key, name in ROWS]
    counts = {s: sum(1 for c in checks if c['status'] == s) for s in STATUSES}
    return {'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'host': host, 'program': 'health_check.py',
            'window_s': round(window_s, 1), 'stopped_early': stop_request, 'counts': counts,
            'exit_code': exit_code_for(c['status'] for c in checks), 'checks': checks,
            'measurements': measurements}


def format_report(rep):
    w1, w2 = 7, 21
    lines = [f'TurtleBot 4 health check, {rep["created"]} on {rep["host"]}, ROS window {rep["window_s"]:g} s'
             + (f' (stopped early by {rep["stopped_early"]})' if rep['stopped_early'] else ''),
             'Read only: nothing was moved or changed.',
             '',
             f'{"STATUS":<{w1}}{"CHECK":<{w2}}RESULT',
             f'{"------":<{w1}}{"-----":<{w2}}------']
    for c in rep['checks']:
        lines.append(f'{c["status"]:<{w1}}{c["check"]:<{w2}}{c["result"]}')
        if c['hint'] and c['status'] != 'PASS':
            lines.append(' ' * (w1 + w2) + ('note: ' if c['status'] == 'INFO' else 'fix: ') + c['hint'])
    n = rep['counts']
    lines += ['', f'{n["PASS"]} PASS, {n["WARN"]} WARN, {n["FAIL"]} FAIL, {n["INFO"]} INFO. '
              f'Exit code {rep["exit_code"]} (0 all PASS or INFO, 1 a WARN, 2 a FAIL).']
    return '\n'.join(lines)


def on_signal(signum, frame):
    global stop_request
    stop_request = signal.Signals(signum).name


def main():
    p = argparse.ArgumentParser(description='Read-only robot health checklist. Does not move the robot.')
    p.add_argument('--seconds', type=float, default=SECONDS,
                   help=f'ROS measuring window (default {SECONDS:g} s, max {MAX_SECONDS:g})')
    p.add_argument('--json', help='also write the report to this JSON file')
    args = p.parse_args()
    seconds = max(1.0, min(MAX_SECONDS, args.seconds))
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    if seconds != args.seconds:
        log(f'note: --seconds {args.seconds:g} is out of range, using {seconds:g}')

    log('health check: system checks (read only, nothing moves)')
    rows = {key: isolated(check) for key, check in SYSTEM_CHECKS.items()}
    try:
        m = measure_ros(seconds, lambda: stop_request is not None)
    except Exception as e:          # ROS failed to start: the system rows are still reported
        m = {'error': describe_error(e)}
    ros, measurements = ros_rows(m)
    rows.update(ros)
    try:
        host = socket.gethostname()
    except OSError:
        host = 'unknown'
    rep = build_report(rows, measurements, measurements['window_s'], host)
    print('\n' + format_report(rep), flush=True)
    if args.json:
        try:
            with open(args.json, 'w') as f:
                json.dump(rep, f, indent=2)
            log(f'wrote {args.json}')
        except OSError as e:
            log(f'ERROR: could not write {args.json}: {e}')
    return rep['exit_code']


if __name__ == '__main__':
    sys.exit(main())
