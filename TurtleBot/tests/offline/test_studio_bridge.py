"""Offline tests of the TurtleBot Studio robot bridge (TurtleBot/tools/studio/robot_bridge.py).

No robot and no ROS: the bridge is driven as a subprocess in --fake mode through stdin/stdout, plus unit tests of its
pure helpers. Also tests the BOOT path (the one-liner that streams the file over ssh) with STUDIO_BRIDGE_FAKE=1.
Usage: python test_studio_bridge.py     (prints PASS/FAIL/SKIP, exit code 1 on any failure)
"""
import importlib.util
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio', 'robot_bridge.py'))
POSIX = os.name == 'posix'
fails = 0


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


def skip(name, why):
    print(f'SKIP {name}  [{why}]')


spec = importlib.util.spec_from_file_location('robot_bridge_mod', BRIDGE)
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)

# ---------------------------------------------------------------- pure helpers
# lidar mounted at +90 deg yaw: straight ahead is laser -90 deg
N = 720
INC = 2 * math.pi / N
AMIN = -math.pi


def idx(laser_deg):
    return int(round((math.radians(laser_deg) - AMIN) / INC)) % N


rng = [3.0] * N
rng[idx(-90)] = 0.8               # straight ahead
rng[idx(90)] = 0.5                # behind: nearest overall but not in front
rng[idx(-90 + 10)] = 0.05         # inside the robot body: ignored
rng[idx(0)] = float('inf')
rng[idx(10)] = float('nan')
front, low = rb.scan_front_min(rng, AMIN, INC)
check('scan: front uses laser -90 deg (mount +90), min is the rear obstacle', front == 0.8 and low == 0.5, f'{front} {low}')
rng2 = [3.0] * N
rng2[idx(-90 + 14)] = 1.1
rng2[idx(-90 + 20)] = 0.4
f2, l2 = rb.scan_front_min(rng2, AMIN, INC)
check('scan: +-15 deg window (14 deg in, 20 deg out)', f2 == 1.1 and l2 == 0.4, f'{f2} {l2}')
check('scan: no valid beam gives None', rb.scan_front_min([float('inf'), float('nan'), 0.01], AMIN, INC) == (None, None))
f3, _ = rb.scan_front_min(rng, AMIN, INC, yaw_off=0.0)
check('scan: with yaw 0 the front would be laser 0 deg (inf ignored -> 3.0)', f3 == 3.0, str(f3))

check('yaw from quaternion', abs(rb.yaw_deg_from_quat(0, 0, math.sin(math.pi / 4), math.cos(math.pi / 4)) - 90.0) < 1e-6)

big = {'ranges': [float(i) for i in range(720)], 'name': 'x', 'inf': float('inf'), 'nested': {'a': list(range(5))}}
sh = rb.shrink_msg(big)
check('truncate: arrays > 32 keep 32 + "…(+N)" marker', len(sh['ranges']) == 33 and sh['ranges'][-1] == '…(+688)', str(sh['ranges'][-2:]))
check('truncate: short arrays and non-finite floats', sh['nested']['a'] == [0, 1, 2, 3, 4] and sh['inf'] is None)
huge = {'a%d' % i: list(range(32)) for i in range(60)}
sh2 = rb.shrink_msg(huge)
check('truncate: total JSON <= 16 KB', len(json.dumps(sh2)) <= 16 * 1024, str(len(json.dumps(sh2))))
check('truncate: bytes and tuples are cleaned', rb.clean_json({'b': b'\x01\x02', 't': (1, 2)}) == {'b': [1, 2], 't': [1, 2]})

STAT_A = 'cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 50 0 50 350 50 0 0 0 0 0\n'
STAT_B = 'cpu  200 0 200 750 150 0 0 0 0 0\n'
pa, pb = rb.parse_proc_stat(STAT_A), rb.parse_proc_stat(STAT_B)
check('proc/stat parse and cpu percent (busy 200 of 300 = 66.7)', pa == (1000, 800) and rb.cpu_pct(pa, pb) == 66.7 and rb.cpu_pct(pa, pa) is None)
check('proc/stat garbage', rb.parse_proc_stat('cpu x y\n') is None and rb.parse_proc_stat('') is None)
check('meminfo used/total MB', rb.parse_meminfo('MemTotal: 3874816 kB\nMemFree: 1 kB\nMemAvailable: 3118080 kB\n') == (739, 3784))
check('loadavg and uptime', rb.parse_loadavg('0.90 0.93 0.64 1/400 1234\n') == 0.9 and rb.parse_uptime('783.45 2000.1\n') == 783.5
      and rb.parse_loadavg('') is None)
check('vcgencmd throttled', rb.parse_throttled('throttled=0x50005\n') == '0x50005' and rb.parse_throttled('x') is None)
WIRELESS = ('Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE\n'
            ' face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22\n'
            ' wlan0: 0000   58.  -52.  -256        0      0      0      0      0        0\n')
check('net/wireless parse; header only gives {}', rb.parse_wireless(WIRELESS) == {'wlan0': {'link': 58.0, 'level': -52.0}}
      and rb.parse_wireless('\n'.join(WIRELESS.splitlines()[:2])) == {})
check('nmcli split with escaped colon', rb.split_nmcli(r'wlan0:wifi:connected:My\:Net') == ['wlan0', 'wifi', 'connected', 'My:Net'])
devs = rb.parse_nmcli_devices('wlan0:wifi:connected:netplan-wlan0-Turtlebot4\neth0:ethernet:connected:netplan-eth0\nlo:loopback:unmanaged:--\n')
check('nmcli devices', devs[0] == {'device': 'wlan0', 'type': 'wifi', 'state': 'connected', 'connection': 'netplan-wlan0-Turtlebot4'}
      and devs[2]['connection'] == '')
IPOUT = ('1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever\n'
         '2: eth0    inet 192.168.185.3/24 brd 192.168.185.255 scope global eth0\n'
         '4: wlan0    inet 10.42.0.1/24 brd 10.42.0.255 scope global wlan0\n')
check('ip addr parse (lo skipped)', rb.parse_ip_addr(IPOUT) == {'eth0': '192.168.185.3', 'wlan0': '10.42.0.1'})


def fake_run(args, timeout=3.0):
    a = ' '.join(args)
    if a.startswith('ip '):
        return IPOUT
    if 'DEVICE,TYPE,STATE,CONNECTION' in a:
        return 'wlan0:wifi:connected:netplan-wlan0-Turtlebot4\n'
    if '802-11-wireless.mode' in a:
        return 'ap\nTurtlebot4\n'
    if 'powersave' in a:
        return 'disable\n'
    return None


net = rb.collect_net(fake_run, lambda p: WIRELESS)
check('collect_net: AP mode, ssid, powersave, addresses', net['wifi_mode'] == 'ap' and net['ssid'] == 'Turtlebot4'
      and net['powersave_students'] == 'disable' and net['addresses']['eth0'] == '192.168.185.3', str(net))
check('collect_net: nothing available gives empty facts', rb.collect_net(lambda a, timeout=3: None, lambda p: None)['wifi_mode'] is None)

check('cmdline match guards against pid reuse', rb.cmdline_matches('python3\0-u\0/home/ubuntu/robot_code/drive_test.py\0', 'drive_test.py')
      and not rb.cmdline_matches('/usr/sbin/sshd\0-D\0', 'drive_test.py') and not rb.cmdline_matches('', 'x'))
check('pid_alive uses the command line', rb.pid_alive(5, 'a.py', lambda p: 'python3\0a.py\0', linux=True)
      and not rb.pid_alive(5, 'a.py', lambda p: 'bash\0', linux=True) and not rb.pid_alive(5, 'a.py', lambda p: None, linux=True)
      and not rb.pid_alive(0, 'a.py', lambda p: 'a.py', linux=True))
tmp = tempfile.mkdtemp(prefix='studio_t_')
check('safe_join stays inside the base', rb.safe_join(tmp, 'a/b.py') == os.path.realpath(os.path.join(tmp, 'a', 'b.py'))
      and rb.safe_join(tmp, '../x.py') is None and rb.safe_join(tmp, '') is None)
check('expand_home', rb.expand_home('~/robot_code', '/h') == os.path.join('/h', 'robot_code') and rb.expand_home(None, '/h', '~') == '/h')
check('hazard names', rb.hazard_name(1) == 'bump' and rb.hazard_name(2) == 'cliff' and rb.hazard_name(99) == 'type99')

# list_dir: skips __pycache__, .git, logs when recursive
os.makedirs(os.path.join(tmp, 'sub'))
os.makedirs(os.path.join(tmp, '__pycache__'))
os.makedirs(os.path.join(tmp, 'logs'))
with open(os.path.join(tmp, 'a.py'), 'w', newline='\n') as f:
    f.write('print(1)\n')
with open(os.path.join(tmp, 'sub', 'b.sh'), 'w') as f:
    f.write('echo\n')
with open(os.path.join(tmp, '__pycache__', 'c.pyc'), 'w') as f:
    f.write('x')
names = [e['name'] for e in rb.list_dir(tmp, recursive=True)]
check('ls recursive: relative names, no __pycache__/logs', sorted(names) == ['a.py', 'sub', 'sub/b.sh'], str(names))
a = [e for e in rb.list_dir(tmp) if e['name'] == 'a.py'][0]
import hashlib
check('ls: sha1 and size of a file', a['size'] == 9 and a['sha1'] == hashlib.sha1(b'print(1)' + bytes([10])).hexdigest())

# ---- v1.1 pure helpers: path rules, describe, wifi_info
check('valid_rel: allowed and refused names', rb.valid_rel('a.py') and rb.valid_rel('sub/my-prog_1.py') and not rb.valid_rel('../x.py')
      and not rb.valid_rel('/etc/passwd') and not rb.valid_rel('a b.py') and not rb.valid_rel('a/../b.py') and not rb.valid_rel('')
      and not rb.valid_rel('a' * 121) and not rb.valid_rel('a//b') and not rb.valid_rel('x\\y.py') and not rb.valid_rel(None))
check('home_path_ok: inside home yes, ~/.ssh and outside no', rb.home_path_ok(os.path.join(tmp, 'robot_code', 'a.py'), tmp)
      and not rb.home_path_ok(os.path.join(tmp, '.ssh', 'id'), tmp) and not rb.home_path_ok(os.path.dirname(tmp), tmp)
      and not rb.home_path_ok(tmp + '_other', tmp))
check('detect_moves: keywords, /dock_status alone is not motion',
      rb.detect_moves('pub = create_publisher(TwistStamped, "/cmd_vel")') == ['cmd_vel', 'TwistStamped']
      and rb.detect_moves('sub("/dock_status")') == [] and rb.detect_moves('ActionClient(node, Dock, "/dock")') == ['/dock']
      and rb.detect_moves('import motion_shapes') == ['motion_shapes'] and rb.detect_moves('print(1)') == [])
PYSRC = ('"""Spin the robot.\n\nSecond paragraph is not included.\n"""\nimport argparse\nap = argparse.ArgumentParser()\n'
         'ap.add_argument("--turns", type=float, default=1.0, help="how many turns")\nap.add_argument(\n    "shape", help="square or circle")\n'
         'ap.add_argument("-s", "--speed", type=float)\n')
check('describe: docstring is the first paragraph only', rb.extract_docstring(PYSRC, '.py') == 'Spin the robot.')
check('describe: usage lines with option strings and help', rb.extract_usage(PYSRC) == ['--turns: how many turns', 'shape: square or circle', '-s, --speed'], str(rb.extract_usage(PYSRC)))
check('describe: usage capped at 12', len(rb.extract_usage('ap.add_argument("--a")\n' * 30)) == 12)
check('describe: leading # block for scripts without docstring', rb.extract_docstring('#!/bin/bash\n# Run the thing.\n# More text.\n\necho hi\n', '.sh') == 'Run the thing.\nMore text.')
check('describe: docstring limited to 600 chars', len(rb.extract_docstring('"""' + 'x' * 2000 + '"""\n', '.py')) == 600)


def wifi_run(args, timeout=3.0):
    a = ' '.join(args)
    if 'DEVICE,TYPE,STATE,CONNECTION' in a:
        return 'wlan0:wifi:connected:Students\n'
    if a.startswith('ip '):
        return '4: wlan0    inet 10.1.2.3/24 brd 10.1.2.255 scope global wlan0\n'
    if 'NAME,TYPE,AUTOCONNECT' in a:
        return 'Students:802-11-wireless:yes:10:yes\nnetplan-wlan0-Turtlebot4:802-11-wireless:yes:0:no\nnetplan-eth0:802-3-ethernet:yes:0:no\n'
    if '802-11-wireless.ssid' in a:
        return ('Students\ninfrastructure\ndisable\n' if a.endswith('Students') else 'Turtlebot4\nap\ndefault (0)\n')
    if 'SSID,SIGNAL' in a:
        return 'Students:70:WPA2:6\nStudents:50:WPA2:11\nCafe:40:WPA1 WPA2:1\n:30::3\n'
    return None


wi = rb.collect_wifi(wifi_run, lambda p: WIRELESS)
check('wifi_info: wlan0 client with ip, signal, power save', wi['wlan0'] == {'state': 'connected', 'connection': 'Students', 'mode': 'infrastructure',
      'ssid': 'Students', 'ip': '10.1.2.3', 'signal_dbm': -52.0, 'powersave': 'disable'}, str(wi['wlan0']))
check('wifi_info: saved wifi connections only, priority, active', [(x['name'], x['priority'], x['active'], x['mode']) for x in wi['saved']]
      == [('Students', 10, True, 'infrastructure'), ('netplan-wlan0-Turtlebot4', 0, False, 'ap')] and wi['saved'][0]['autoconnect'] is True
      and wi['saved'][1]['powersave'] == 'default', str(wi['saved']))
check('wifi_info: scan deduped, strongest first, hidden skipped', [(x['ssid'], x['signal']) for x in wi['scan']] == [('Students', 70), ('Cafe', 40)]
      and 'scan_note' not in wi)


def ap_run(args, timeout=3.0):
    a = ' '.join(args)
    if 'DEVICE,TYPE,STATE,CONNECTION' in a:
        return 'wlan0:wifi:connected:netplan-wlan0-Turtlebot4\n'
    if '802-11-wireless.ssid' in a:
        return 'Turtlebot4\nap\ndefault\n'
    return None


wa = rb.collect_wifi(ap_run, lambda p: WIRELESS)
check('wifi_info: AP mode gives an empty scan with the note and no signal', wa['wlan0']['mode'] == 'ap' and wa['scan'] == [] and wa['wlan0']['signal_dbm'] is None
      and 'hotspot' in wa['scan_note'])
check('wifi_info: no nmcli at all does not crash', rb.collect_wifi(lambda a, timeout=3: None, lambda p: None)['saved'] == [])
check('collect_net has wlan0_ip', rb.collect_net(fake_run, lambda p: WIRELESS)['wlan0_ip'] == '10.42.0.1')

bf = rb.battery_flags
check('battery: status 1 charging, 2/3 not charging whatever the current', bf(1, -1.0, 50, False) == (True, False)
      and bf(2, 0.5, 50, True) == (False, False) and bf(3, 0.5, 50, True) == (False, False))
check('battery: UNKNOWN status uses the current sign (Create 3: always 0)', bf(0, 0.503, 97, True) == (True, False)
      and bf(0, -0.8, 80, False) == (False, False) and bf(0, 0.01, 80, True) == (None, False) and bf(0, None, 80, True) == (None, False)
      and bf(None, 0.5, 80, True) == (True, False))
check('battery: full = status 4, or docked at >= 99 % with ~0 A', bf(4, 0.0, 50, False)[1] is True and bf(0, 0.0, 99.5, True) == (None, True)
      and bf(0, 0.0, 99.5, False)[1] is False and bf(0, 0.5, 99.5, True)[1] is False and bf(0, 0.0, 98, True)[1] is False)

# estop status logic (wheel_status is the truth, "app" only when the bridge set it)
br = rb.Bridge(rb.FakeRos(), None, tmp, True)
check('estop status: wheels disabled, not ours -> on, source robot', br.estop_status(False) == {'on': True, 'source': 'robot', 'stop_file': False})
br.estop_app, br.estop_t = True, time.monotonic()
check('estop status: ours -> source app', br.estop_status(False)['source'] == 'app')
check('estop status: wheels enabled right after our estop is not cleared yet', br.estop_status(True)['on'] is False and br.estop_app is True)
br.estop_t -= 10
br.estop_status(True)
check('estop status: wheels enabled later clears the app flag', br.estop_app is False and br.estop_status(True)['source'] is None)
br.estop_on = True
check('estop status: unknown wheels falls back to bridge knowledge', br.estop_status(None)['on'] is True)

# ---------------------------------------------------------------- subprocess driver


class Proc:
    def __init__(self, extra_args=('--fake',), home=None, env_extra=None, boot=False):
        self.home = home or tempfile.mkdtemp(prefix='studio_home_')
        env = dict(os.environ, STUDIO_BRIDGE_HOME=self.home, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        env.pop('STUDIO_BRIDGE_FAKE', None)
        env.update(env_extra or {})
        if boot:
            src = "import sys;b=sys.stdin.buffer;n=int(b.readline());exec(compile(b.read(n).decode(),'robot_bridge','exec'))"
            cmd = [sys.executable, '-u', '-c', src]
        else:
            cmd = [sys.executable, '-u', BRIDGE] + list(extra_args)
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.events = []
        self.err = []
        self.next_id = 0
        threading.Thread(target=self._rd, daemon=True).start()
        threading.Thread(target=lambda: [self.err.append(l) for l in self.p.stderr], daemon=True).start()
        if boot:
            data = open(BRIDGE, 'rb').read()
            self.p.stdin.write(b'%d\n' % len(data) + data)
            self.p.stdin.flush()

    def _rd(self):
        for line in self.p.stdout:
            try:
                ev = json.loads(line.decode('utf-8'))
            except ValueError:
                ev = {'ev': 'BADLINE', 'raw': line[:200].decode('utf-8', 'replace')}
            self.events.append(ev)

    def wait_ev(self, pred, timeout=5.0):
        end = time.monotonic() + timeout
        while True:
            for ev in self.events[:]:
                if pred(ev):
                    try:
                        self.events.remove(ev)
                    except ValueError:
                        continue
                    return ev
            if time.monotonic() >= end:
                return None
            time.sleep(0.02)

    def send(self, cmd, timeout=15.0, **kw):
        self.next_id += 1
        i = self.next_id
        d = dict(kw, id=i, cmd=cmd)
        self.p.stdin.write((json.dumps(d) + '\n').encode())
        self.p.stdin.flush()
        return self.wait_ev(lambda e: e.get('ev') == 'reply' and e.get('id') == i, timeout)

    def raw(self, text):
        self.p.stdin.write(text.encode())
        self.p.stdin.flush()

    def close(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(3)
        except subprocess.TimeoutExpired:
            self.p.kill()


b = Proc()
hello = b.wait_ev(lambda e: e.get('ev') == 'hello')
check('hello: fields, fake', hello is not None and hello['fake'] is True and hello['version'] == '1' and hello['bridge'] == 'robot_bridge'
      and hello['pid'] == b.p.pid and 'hostname' in hello and hello['ros'] is False, str(hello))
r = b.send('ping')
check('ping', r and r['ok'] and r['pong'] is True)
r = b.send('definitely_not_a_command')
check('unknown command: ok false, bridge keeps running', r and r['ok'] is False and 'unknown' in r['error'] and b.p.poll() is None)
b.raw('this is not json\n{"id":99,"cmd":"ping"}\n[1,2]\n')
r = b.wait_ev(lambda e: e.get('id') == 99)
check('garbage lines are ignored, next command still answered', r and r['ok'])
r = b.send('run', path='../../etc/passwd')
check('run: path outside dir refused', r and r['ok'] is False)

b.send('status_on', period=0.2)
s1 = b.wait_ev(lambda e: e.get('ev') == 'status')
s2 = b.wait_ev(lambda e: e.get('ev') == 'status')
keys = {'battery', 'dock', 'odom', 'scan', 'hazards', 'estop', 'system', 'net', 'clock', 'ros_service', 'runs', 't', 'wall'}
check('status_on: status events with every spec key', s1 and s2 and keys <= set(s1), str(sorted(keys - set(s1 or {}))))
check('status: fake values (docked, battery, scan 7.7 Hz, estop off)', s1['dock']['is_docked'] is True and s1['battery']['percent'] is not None
      and s1['scan']['rate_hz'] == 7.7 and s1['estop']['on'] is False and s2['t'] > s1['t'])
time.sleep(1.2)
b.events[:] = [e for e in b.events if e.get('ev') != 'status']
b.send('status_off')
time.sleep(0.6)
b.events[:] = [e for e in b.events if e.get('ev') != 'status']
time.sleep(0.8)
check('status_off: no more status events', not any(e.get('ev') == 'status' for e in b.events))

r = b.send('topics')
check('topics: list with /odom and /scan', r and r['ok'] and {'/odom', '/scan', '/cmd_vel'} <= {t['name'] for t in r['topics']}
      and all({'name', 'types', 'publishers', 'subscribers'} <= set(t) for t in r['topics']))
r = b.send('watch', topic='/odom', max_hz=10)
wid = r and r.get('watch_id')
m1 = b.wait_ev(lambda e: e.get('ev') == 'msg' and e.get('watch_id') == wid)
check('watch /odom: reply with watch_id, then msg events', r and r['ok'] and m1 and m1['topic'] == '/odom' and 'data' in m1 and 'rate_hz' in m1)
r = b.send('unwatch', watch_id=wid)
time.sleep(0.4)
b.events[:] = [e for e in b.events if e.get('ev') != 'msg']
time.sleep(0.5)
check('unwatch: stops msg events', r and r['ok'] and not any(e.get('ev') == 'msg' for e in b.events))
ids = [b.send('watch', topic='/t%d' % i, max_hz=1) for i in range(5)]
check('watch: at most 4 at once', [x['ok'] for x in ids] == [True] * 4 + [False], str([x['ok'] for x in ids]))
for x in ids[:4]:
    b.send('unwatch', watch_id=x['watch_id'])

# programs in the fake home
code = os.path.join(b.home, 'robot_code')
os.makedirs(code, exist_ok=True)
with open(os.path.join(code, 'hello.py'), 'w') as f:
    f.write('import sys\nprint("hello from run", sys.argv[1:], flush=True)\n')
with open(os.path.join(code, 'sleeper.py'), 'w') as f:
    f.write('import time\nprint("sleeping", flush=True)\ntime.sleep(60)\n')
with open(os.path.join(code, 'drive_test.py'), 'w') as f:
    f.write('print("would drive")\n')
with open(os.path.join(code, 'notes.txt'), 'w') as f:
    f.write('x')
r = b.send('ls', dir='~/robot_code')
check('ls: files with sha1 under the fake home', r and r['ok'] and {'hello.py', 'sleeper.py'} <= {e['name'] for e in r['files']}
      and r['dir'] == code and all(len(e['sha1']) == 40 for e in r['files'] if not e['is_dir']), str(r)[:200])
r = b.send('run', path='hello.py', args=['a', 'b'])
rid = r and r.get('run_id')
out = b.wait_ev(lambda e: e.get('ev') == 'run_output' and e.get('run_id') == rid and any('hello from run' in l for l in e['lines']))
ex = b.wait_ev(lambda e: e.get('ev') == 'run_exit' and e.get('run_id') == rid)
check('run: reply, run_output with the program text, run_exit code 0', r and r['ok'] and out and ex and ex['code'] == 0
      and os.path.isfile(r['log']) and os.path.isfile(r['log'] + '.pid'), str(r))
check('run: log lives in ~/robot_code/logs', r and os.path.dirname(r['log']) == os.path.join(code, 'logs'))
r = b.send('run', path='notes.txt')
check('run: only .py and .sh', r and r['ok'] is False)
r = b.send('run', path='drive_test.py', motion=True)
check('motion run without confirmed is refused', r and r['ok'] is False and r['error'] == 'motion needs confirmation', str(r))
r = b.send('run', path='drive_test.py', motion=True, confirmed=True)
b.wait_ev(lambda e: e.get('ev') == 'run_exit' and e.get('run_id') == (r or {}).get('run_id'))
check('motion run with confirmed starts', r and r['ok'])
r = b.send('runs')
check('runs: lists earlier runs with alive flag', r and r['ok'] and len(r['runs']) >= 2 and all('alive' in x for x in r['runs']))

r = b.send('run', path='sleeper.py')
sid = r['run_id']
b.wait_ev(lambda e: e.get('ev') == 'run_output' and e.get('run_id') == sid and any('sleeping' in l for l in e['lines']))
t0 = time.monotonic()
st = b.send('stop', run_id=sid)
ex = b.wait_ev(lambda e: e.get('ev') == 'run_exit' and e.get('run_id') == sid, 8)
check('stop: stopped list and run_exit', st and st['ok'] and sid in st['stopped'] and ex is not None, str(st))
if POSIX:
    check('stop: SIGINT is enough for a sleeping python script, quickly', st['how'][sid] == 'SIGINT' and time.monotonic() - t0 < 3.0, str(st['how']))
else:
    skip('stop: SIGINT escalation details', 'posix only (Windows uses CTRL_BREAK / terminate)')
r = b.send('stop', run_id='nope')
check('stop: unknown run id -> ok false', r and r['ok'] is False)

# estop
r = b.send('run', path='sleeper.py')
eid = r['run_id']
b.wait_ev(lambda e: e.get('ev') == 'run_output' and e.get('run_id') == eid)
t0 = time.monotonic()
r = b.send('estop', timeout=10)
dt = time.monotonic() - t0
steps = (r or {}).get('steps', {})
check('estop: reply has every step key, fake:true', r and r['ok'] and r['fake'] is True
      and {'zero_cmd_vel', 'stop_file', 'programs', 'e_stop_service', 'cancel_goals'} <= set(steps), str(r)[:300])
check('estop: STOP file written, e_stop service success, finished in < 8 s', os.path.exists(os.path.join(b.home, 'STOP'))
      and steps['e_stop_service']['success'] is True and dt < 8.0, '%.1f s' % dt)
check('estop: running app program was stopped', eid in steps['programs']['app_runs'], str(steps['programs']))
ex = b.wait_ev(lambda e: e.get('ev') == 'run_exit' and e.get('run_id') == eid, 5)
check('estop: run_exit for that program', ex is not None)
b.send('status_on', period=0.2)
b.events[:] = [e for e in b.events if e.get('ev') != 'status']
s = b.wait_ev(lambda e: e.get('ev') == 'status' and e['estop']['on'] is True)
check('estop: status shows estop.on with source app', s and s['estop']['source'] == 'app' and s['estop']['stop_file'] is True)
r = b.send('run', path='drive_test.py', motion=True, confirmed=True)
check('STOP file blocks a confirmed motion run', r and r['ok'] is False and 'STOP file' in r['error'], str(r))
r = b.send('run', path='hello.py')
b.wait_ev(lambda e: e.get('ev') == 'run_exit' and e.get('run_id') == (r or {}).get('run_id'))
check('STOP file does not block non-motion runs', r and r['ok'])
r = b.send('undock', confirmed=True)
check('STOP file blocks undock', r and r['ok'] is False)
r = b.send('estop_release')
check('estop_release: STOP removed, estop off', r and r['ok'] and not os.path.exists(os.path.join(b.home, 'STOP'))
      and r['steps']['e_stop_service']['success'] is True, str(r)[:200])
b.events[:] = [e for e in b.events if e.get('ev') != 'status']
s = b.wait_ev(lambda e: e.get('ev') == 'status' and e['estop']['on'] is False)
check('estop_release: status estop.on false', s is not None)

# actions / lidar / health
r = b.send('undock')
check('undock without confirmed is refused', r and r['ok'] is False)
r = b.send('undock', confirmed=True)
ev = b.wait_ev(lambda e: e.get('ev') == 'action' and e.get('state') == 'succeeded', 6)
check('undock confirmed: accepted, action events, succeeded', r and r['ok'] and r['fake'] is True and ev and ev['name'] == 'undock')
s = None
for _ in range(10):
    s = b.wait_ev(lambda e: e.get('ev') == 'status', 2)
    if s and s['dock']['is_docked'] is False:
        break
check('fake undock changes the dock status', s and s['dock']['is_docked'] is False)
r = b.send('lidar', on=False)
check('lidar off', r and r['ok'] and r['on'] is False and r['fake'] is True)
r = b.send('health')
check('health: checks list with name/ok/detail', r and r['ok'] and len(r['checks']) >= 6 and all({'name', 'ok', 'detail'} <= set(c) for c in r['checks']))

# ---- v1.1 commands: describe, read_file, write_file, path safety, wifi_info
r = b.send('describe', dir='~/robot_code')
progs = {p['name']: p for p in (r or {}).get('programs', [])}
check('describe: *.py/*.sh only, docstring, moves flag', r and r['ok'] and 'notes.txt' not in progs and 'hello.py' in progs
      and progs['hello.py']['moves_detected'] is False and progs['hello.py']['docstring'] == '' and progs['sleeper.py']['size'] > 0, str(r)[:300])
with open(os.path.join(code, 'mover.py'), 'w', newline='\n') as f:
    f.write('"""Drive a bit.\n\nmore"""\nimport argparse\nap = argparse.ArgumentParser()\nap.add_argument("--d", help="distance")\npub = x.create_publisher(TwistStamped, "/cmd_vel", 10)\n')
r = b.send('describe')
m = [p for p in r['programs'] if p['name'] == 'mover.py'][0]
check('describe: motion detected with reasons, docstring and usage', m['moves_detected'] and m['moves_reasons'] == ['cmd_vel', 'TwistStamped']
      and m['docstring'] == 'Drive a bit.' and m['usage'] == ['--d: distance'], str(m))
r = b.send('describe', dir='/')
check('describe/ls/run: directory outside home refused', r and r['ok'] is False and b.send('ls', dir='/')['ok'] is False
      and b.send('ls', dir='~/..')['ok'] is False and b.send('run', dir='/', path='etc.py')['ok'] is False)
check('ls/describe: ~/.ssh refused', b.send('ls', dir='~/.ssh')['ok'] is False and b.send('describe', dir='~/.ssh')['ok'] is False)

r = b.send('write_file', path='new_prog.py', text='print("hi")\n')
check('write_file: creates, reply path/size/sha1, no backup', r and r['ok'] and r['size'] == 12 and len(r['sha1']) == 40 and r['backup'] is None, str(r))
p_new = os.path.join(code, 'new_prog.py')
check('write_file: file content and (posix) mode 0755', open(p_new, 'rb').read() == b'print("hi")\n'
      and (not POSIX or (os.stat(p_new).st_mode & 0o777) == 0o755))
sha_old = r['sha1']
r = b.send('write_file', path='new_prog.py', text='print("x")\n')
check('write_file: refuses to replace without overwrite', r and r['ok'] is False and 'exists' in r['error'])
r = b.send('write_file', path='new_prog.py', text='print("v2")\n', overwrite=True, expect_sha1='0' * 40)
check('write_file: wrong expect_sha1 refused', r and r['ok'] is False and r['error'] == 'changed on the robot since you opened it', str(r))
r = b.send('write_file', path='new_prog.py', text='print("v2")\n', overwrite=True, expect_sha1=sha_old)
check('write_file: overwrite with matching sha1 keeps ONE .bak with the old text', r and r['ok'] and r['backup'] == p_new + '.bak'
      and open(p_new + '.bak', 'rb').read() == b'print("hi")\n' and open(p_new, 'rb').read() == b'print("v2")\n', str(r))
r = b.send('write_file', path='new_prog.py', text='print("v3")\n', overwrite=True)
check('write_file: second overwrite replaces the .bak (still one)', r and r['ok'] and open(p_new + '.bak', 'rb').read() == b'print("v2")\n'
      and not [n for n in os.listdir(code) if n.startswith('new_prog.py') and n not in ('new_prog.py', 'new_prog.py.bak')])
r = b.send('write_file', path='notes2.txt', text='plain')
check('write_file: other extensions are written (mode 0644 on posix)', r and r['ok'] and (not POSIX or (os.stat(os.path.join(code, 'notes2.txt')).st_mode & 0o777) == 0o644))
r = b.send('write_file', path='sub/dir/deep.py', text='x = 1\n')
check('write_file: subfolders are created', r and r['ok'] and os.path.isfile(os.path.join(code, 'sub', 'dir', 'deep.py')))
bad = [b.send('write_file', path=p, text='x') for p in ('../evil.py', '/tmp/evil.py', 'a b.py', '..', '.ssh/../../x.py', 'x' * 130)]
check('write_file: bad names refused', all(x and x['ok'] is False for x in bad), str([x['error'] for x in bad]))
check('write_file: dir outside home or ~/.ssh refused', b.send('write_file', dir='~/.ssh', path='authorized_keys', text='x')['ok'] is False
      and b.send('write_file', dir='/', path='x.py', text='x')['ok'] is False and not os.path.exists(os.path.join(b.home, '.ssh')))
check('write_file: non-string text refused', b.send('write_file', path='n.py', text=5)['ok'] is False)
r = b.send('read_file', path='new_prog.py')
check('read_file: text, size, mtime, sha1', r and r['ok'] and r['text'] == 'print("v3")\n' and r['size'] == 12 and len(r['sha1']) == 40 and 'mtime' in r, str(r))
with open(os.path.join(code, 'bin.dat'), 'wb') as f:
    f.write(bytes([0xff, 0xfe, 0x00, 0x80]))
with open(os.path.join(code, 'big.txt'), 'wb') as f:
    f.write(b'a' * (512 * 1024 + 1))
check('read_file: binary, too big, missing and escaping names refused', b.send('read_file', path='bin.dat')['ok'] is False
      and b.send('read_file', path='big.txt')['ok'] is False and b.send('read_file', path='nope.py')['ok'] is False
      and b.send('read_file', path='../../etc/passwd')['ok'] is False and b.send('read_file', dir='~/.ssh', path='id_ed25519')['ok'] is False)
if POSIX:
    os.makedirs(os.path.join(b.home, '.ssh'), exist_ok=True)
    with open(os.path.join(b.home, '.ssh', 'authorized_keys'), 'w') as f:
        f.write('secret')
    os.symlink(os.path.join(b.home, '.ssh', 'authorized_keys'), os.path.join(code, 'link.txt'))
    os.symlink('/etc/hostname', os.path.join(code, 'link2.txt'))
    check('read_file: symlinks into ~/.ssh or outside home refused', b.send('read_file', path='link.txt')['ok'] is False
          and b.send('read_file', path='link2.txt')['ok'] is False and b.send('run', path='link.txt')['ok'] is False)
else:
    skip('symlink escape checks', 'posix only (symlinks need privileges on Windows)')
r = b.send('run', path='new_prog.py')
ex = b.wait_ev(lambda e: e.get('ev') == 'run_exit' and e.get('run_id') == (r or {}).get('run_id'))
check('a file written with write_file can be run', r and r['ok'] and ex and ex['code'] == 0)

r = b.send('wifi_info')
check('wifi_info (fake): client of HomeNet, saved Students prio 10 powersave disable + hotspot, scan list',
      r and r['ok'] and r['fake'] is True and r['wlan0']['mode'] == 'infrastructure' and r['wlan0']['ssid'] == 'HomeNet'
      and r['wlan0']['ip'] == '192.168.50.12' and len(r['scan']) == 6 and 'scan_note' not in r
      and {x['name'] for x in r['saved']} == {'HomeNet', 'Students', 'netplan-wlan0-Turtlebot4'}
      and [x for x in r['saved'] if x['name'] == 'Students'][0]['priority'] == 10
      and [x for x in r['saved'] if x['name'] == 'Students'][0]['powersave'] == 'disable', str(r)[:300])
s = b.wait_ev(lambda e: e.get('ev') == 'status', 3)
check('status net has wlan0_ip in fake mode', s and s['net'].get('wlan0_ip') == '192.168.50.12' and s['net'].get('powersave') == 'default', str(s and s['net']))

s = b.wait_ev(lambda e: e.get('ev') == 'status', 3)
check('fake battery: charging follows docked, with current_a and full flag', s and s['battery']['charging'] is s['dock']['is_docked'] and s['battery']['current_a'] == (0.5 if s['dock']['is_docked'] else -0.8)
      and s['battery']['full'] is False, str(s and s['battery']))

# EOF: exits within 2 s; detached runs are not stopped
r = b.send('run', path='sleeper.py')
lid = r['run_id']
lpid = r['pid']
b.wait_ev(lambda e: e.get('ev') == 'run_output' and e.get('run_id') == lid)
t0 = time.monotonic()
b.p.stdin.close()
try:
    b.p.wait(2.5)
    took = time.monotonic() - t0
except subprocess.TimeoutExpired:
    took = 99
check('EOF on stdin: bridge exits within 2 s', took < 2.0, '%.2f s' % took)
if POSIX:
    alive = True
    try:
        os.kill(lpid, 0)
    except OSError:
        alive = False
    check('detached run survives the bridge', alive)
    # a new bridge on the same home rediscovers it from logs/*.pid and can stop it
    b2 = Proc(home=b.home)
    b2.wait_ev(lambda e: e.get('ev') == 'hello')
    r = b2.send('runs')
    mine = [x for x in r['runs'] if x['run_id'] == lid]
    check('rediscover: run found again from its .pid file, alive', bool(mine) and mine[0]['alive'] is True, str(mine))
    st = b2.send('stop', run_id=lid)
    check('rediscover: stop works on a run of an earlier session', st and st['ok'] and lid in st['stopped'], str(st))
    b2.close()
else:
    skip('detached run survives the bridge / rediscover', 'posix only')
    try:
        os.kill(lpid, 15)
    except OSError:
        pass
b.close()
check('no unexpected stderr traceback', not any(b'Traceback' in l for l in b.err), b''.join(b.err)[-300:].decode('utf-8', 'replace'))

# ---------------------------------------------------------------- separate invocations
bs = Proc(extra_args=(), env_extra={'STUDIO_BRIDGE_FAKE': '1'})
h = bs.wait_ev(lambda e: e.get('ev') == 'hello')
check('STUDIO_BRIDGE_FAKE=1 forces fake mode without --fake', h and h['fake'] is True)
bs.close()

bb = Proc(boot=True, env_extra={'STUDIO_BRIDGE_FAKE': '1'})
h = bb.wait_ev(lambda e: e.get('ev') == 'hello', 10)
r = bb.send('ping') if h else None
check('BOOT path: streamed via exec(compile(...)) from "python -c", hello and ping work', h and h['fake'] is True and r and r['pong'] is True, str(bb.err[-3:]))
t0 = time.monotonic()
bb.p.stdin.close()
try:
    bb.p.wait(2.5)
    took = time.monotonic() - t0
except subprocess.TimeoutExpired:
    took = 99
check('BOOT path: exits within 2 s on EOF', took < 2.0, '%.2f s' % took)
bb.close()

# the file must keep LF endings (it runs on the robot)
with open(BRIDGE, 'rb') as f:
    check('robot_bridge.py has LF line endings only', b'\r\n' not in f.read())

for d in (os.path.join(os.path.dirname(BRIDGE), '__pycache__'),):
    if os.path.isdir(d):
        import shutil
        shutil.rmtree(d, ignore_errors=True)

print('\n%s' % ('ALL PASS' if not fails else '%d FAILED' % fails))
sys.exit(1 if fails else 0)
