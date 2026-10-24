"""Offline tests of TurtleBot Studio 1.3 upgrades U1-U4 in TurtleBot/tools/studio/studio.py and robot_bridge.py:
U1 search the whole network, U2 automatic reconnect, U3 copy diagnostics (redaction), U4 update notice and the
unchanged-file save fix.

No robot and no real network sweep: the parsers and target maths are pure; the sweep is run against a loopback
socket and with stubbed network/ssh-keyscan calls. The HTTP part starts the real studio.py --fake with the real
robot_bridge.py --fake and a local http.server standing in for GitHub.
Usage: python test_studio_upgrades.py     (prints PASS/FAIL/SKIP, exit code = number of failures)
"""
import http.client
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
sys.path.insert(0, STUDIO_DIR)
import studio as st  # noqa: E402

OUT = tempfile.mkdtemp(prefix='tb4_studio_upg_')
fails = 0


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode())
    if not cond:
        fails += 1


def skip(name, why):
    print(f'SKIP {name}  [{why}]')


def new_app(name, settings=None, extra=()):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    if settings is not None:
        with open(os.path.join(d, 'settings.json'), 'w', encoding='utf-8') as f:
            json.dump(settings, f)
    return st.Studio(st.parse_args(['--fake', '--config-dir', d, '--fake-home', os.path.join(d, 'home'), *extra])), d


def wait_for(fn, timeout, step=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


LAB = st.LAB_HOST_KEY
OTHER = st.FAKE_HOST_KEY

# ================================================================ version.json, packaging
with open(os.path.join(STUDIO_DIR, 'version.json'), encoding='utf-8') as f:
    vj = json.load(f)
check('VERSION is 1.3 and version.json carries the same version', st.VERSION == '1.3' and vj['version'] == st.VERSION, str(vj))
check('version.json: date, one plain sentence, page on the lab repo',
      set(vj) == {'version', 'date', 'notes', 'page'} and re.match(r'^\d{4}-\d\d-\d\d$', vj['date']) and vj['notes'].endswith('.')
      and '\n' not in vj['notes'] and vj['page'].startswith(st.UPDATE_PAGE_PREFIX), str(vj))
check('version.json is valid for the update parser', (st.parse_update_info(json.dumps(vj)) or {}).get('version') == st.VERSION)
with open(os.path.join(STUDIO_DIR, 'packaging', 'studio.spec'), encoding='utf-8') as f:
    check('packaging/studio.spec bundles version.json', "'version.json'" in f.read())
with open(os.path.join(STUDIO_DIR, 'version.json'), 'rb') as f:
    check('version.json has LF line endings', b'\r' not in f.read())

# ================================================================ U1 pure: interfaces, targets, neighbours
check('private_v4: 10/8, 172.16/12, 192.168/16 yes; loopback, link-local, public, 172.32 no',
      all(st.private_v4(x) for x in ('10.1.2.3', '172.16.0.1', '172.31.255.1', '192.168.1.1'))
      and not any(st.private_v4(x) for x in ('127.0.0.1', '169.254.3.4', '8.8.8.8', '172.32.0.1', '100.64.0.1', 'junk', '')))
win_if = json.dumps([{'IPAddress': '192.168.1.20', 'PrefixLength': 24, 'InterfaceAlias': 'Wi-Fi'},
                     {'IPAddress': '127.0.0.1', 'PrefixLength': 8, 'InterfaceAlias': 'Loopback'},
                     {'IPAddress': '169.254.9.9', 'PrefixLength': 16, 'InterfaceAlias': 'Ethernet'}])
check('parse_win_ipv4: list', [(i['ip'], i['prefix'], i['name']) for i in st.parse_win_ipv4(win_if)]
      == [('192.168.1.20', 24, 'Wi-Fi'), ('127.0.0.1', 8, 'Loopback'), ('169.254.9.9', 16, 'Ethernet')])
check('parse_win_ipv4: single object, junk and empty',
      st.parse_win_ipv4('{"IPAddress":"10.0.0.4","PrefixLength":22,"InterfaceAlias":"Eth"}') == [{'ip': '10.0.0.4', 'prefix': 22, 'name': 'Eth'}]
      and st.parse_win_ipv4('') == [] and st.parse_win_ipv4('nope') == [] and st.parse_win_ipv4('[{"IPAddress":"x"}]') == [])
lin_if = ('1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever\n'
          '2: eth0    inet 192.168.185.10/24 brd 192.168.185.255 scope global eth0\\       valid_lft forever\n'
          '3: wlan0    inet 10.20.30.40/26 brd 10.20.30.63 scope global dynamic wlan0\\       valid_lft 3000sec\n')
check('parse_ip4_addr: Linux ip -4 -o addr', [(i['ip'], i['prefix'], i['name']) for i in st.parse_ip4_addr(lin_if)]
      == [('127.0.0.1', 8, 'lo'), ('192.168.185.10', 24, 'eth0'), ('10.20.30.40', 26, 'wlan0')])
mac_if = ('lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384\n\tinet 127.0.0.1 netmask 0xff000000\n'
          'en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n\tether aa:bb:cc:dd:ee:ff\n'
          '\tinet 192.168.0.77 netmask 0xffffff00 broadcast 192.168.0.255\n\tinet6 fe80::1%en0 prefixlen 64\n'
          'en5: flags=8863<UP> mtu 1500\n\tinet 10.9.8.7 netmask 255.255.0.0 broadcast 10.9.255.255\n')
check('parse_ifconfig: macOS hex and dotted masks', [(i['ip'], i['prefix'], i['name']) for i in st.parse_ifconfig(mac_if)]
      == [('127.0.0.1', 8, 'lo0'), ('192.168.0.77', 24, 'en0'), ('10.9.8.7', 16, 'en5')])

t24 = st.sweep_targets([{'ip': '192.168.1.20', 'prefix': 24, 'name': 'a'}])
check('sweep_targets /24: .1-.254 without this computer', len(t24) == 253 and '192.168.1.20' not in t24 and t24[0] == '192.168.1.1'
      and t24[-1] == '192.168.1.254')
t16 = st.sweep_targets([{'ip': '10.5.77.9', 'prefix': 16, 'name': 'a'}])
check('sweep_targets /16: only the /24 around this computer', len(t16) == 253 and all(x.startswith('10.5.77.') for x in t16))
t26 = st.sweep_targets([{'ip': '10.20.30.40', 'prefix': 26, 'name': 'a'}])
check('sweep_targets /26: the real (smaller) subnet', len(t26) == 61 and t26[0] == '10.20.30.1' and t26[-1] == '10.20.30.62' and '10.20.30.40' not in t26, str(len(t26)))
check('sweep_targets skips loopback, link-local, public, /31, /32',
      st.sweep_targets([{'ip': '127.0.0.1', 'prefix': 8, 'name': 'lo'}, {'ip': '169.254.1.2', 'prefix': 16, 'name': 'x'},
                        {'ip': '8.8.8.8', 'prefix': 24, 'name': 'y'}, {'ip': '10.0.0.1', 'prefix': 31, 'name': 'p'},
                        {'ip': '10.0.0.2', 'prefix': 32, 'name': 'q'}]) == [])
two = st.sweep_targets([{'ip': '192.168.1.20', 'prefix': 24, 'name': 'a'}, {'ip': '192.168.1.99', 'prefix': 24, 'name': 'b'},
                        {'ip': '192.168.185.10', 'prefix': 24, 'name': 'c'}])
check('sweep_targets: two interfaces on one /24 are not probed twice; each own address left out',
      len(two) == len(set(two)) and '192.168.1.99' not in two and '192.168.1.20' not in two and len(two) == 252 + 253, str(len(two)))
check('sweep_targets: cap of 1024 targets in total', len(st.sweep_targets([{'ip': '10.%d.0.5' % i, 'prefix': 24, 'name': 'n'} for i in range(10)])) == 1024
      and len(st.sweep_targets([{'ip': '10.0.0.5', 'prefix': 24, 'name': 'a'}], cap=10)) == 10 and st.DEEP_MAX_TARGETS == 1024)

win_n = json.dumps([{'IPAddress': '192.168.1.1', 'LinkLayerAddress': 'AA-BB-CC-DD-EE-01'},
                    {'IPAddress': '192.168.1.55', 'LinkLayerAddress': 'D8-3A-DD-41-05-DF'},
                    {'IPAddress': '192.168.1.255', 'LinkLayerAddress': 'FF-FF-FF-FF-FF-FF'},
                    {'IPAddress': '224.0.0.22', 'LinkLayerAddress': '01-00-5E-00-00-16'},
                    {'IPAddress': '192.168.1.66', 'LinkLayerAddress': '00-00-00-00-00-00'}])
n = st.parse_win_neigh4(win_n)
check('parse_win_neigh4: Raspberry Pi MAC marked, broadcast/multicast/zero dropped', [(e['ip'], e['pi']) for e in n] == [('192.168.1.1', False), ('192.168.1.55', True)]
      and n[1]['mac'] == 'D8:3A:DD:41:05:DF', str(n))
n = st.parse_ip4_neigh('192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:01 REACHABLE\n192.168.1.55 dev eth0 lladdr dc:a6:32:01:02:03 STALE\n'
                       '192.168.1.77 dev eth0  FAILED\n192.168.1.78 dev eth0 lladdr b8:27:eb:00:00:01 FAILED\n169.254.1.1 dev eth0 lladdr d8:3a:dd:00:00:01 REACHABLE\n')
check('parse_ip4_neigh: Linux, FAILED and link-local dropped', [(e['ip'], e['pi']) for e in n] == [('192.168.1.1', False), ('192.168.1.55', True)], str(n))
n = st.parse_arp_an('? (192.168.1.1) at aa:bb:cc:dd:ee:1 on en0 ifscope [ethernet]\n? (192.168.1.55) at d8:3a:dd:41:5:df on en0 ifscope [ethernet]\n'
                    '? (192.168.1.9) at (incomplete) on en0 ifscope [ethernet]\n? (224.0.0.251) at 1:0:5e:0:0:fb on en0 ifscope permanent [ethernet]\n')
check('parse_arp_an: macOS short MACs, incomplete and multicast dropped', [(e['ip'], e['pi']) for e in n] == [('192.168.1.1', False), ('192.168.1.55', True)]
      and n[1]['mac'] == 'D8:3A:DD:41:05:DF', str(n))
check('neighbour parsers survive junk', st.parse_win_neigh4('x') == [] and st.parse_ip4_neigh('') == [] and st.parse_arp_an(None) == [])

cs = [{'host': '192.168.1.30', 'identity': 'unknown', 'pi': False}, {'host': '192.168.1.9', 'identity': 'unknown', 'pi': True},
      {'host': '192.168.1.100', 'identity': 'confirmed', 'pi': True}, {'host': '192.168.1.2', 'identity': 'unknown', 'pi': False},
      {'host': '192.168.1.10', 'identity': 'unknown', 'pi': True}]
check('order_deep: confirmed, then Pi, then others; numeric inside a group',
      [c['host'] for c in st.order_deep(cs)] == ['192.168.1.100', '192.168.1.9', '192.168.1.10', '192.168.1.2', '192.168.1.30'])

# ---- tcp_sweep against loopback sockets (real function, real sockets)
srv = socket.socket()
srv.bind(('127.0.0.1', 0))
srv.listen(8)
open_port = srv.getsockname()[1]
closed = socket.socket()
closed.bind(('127.0.0.1', 0))
closed_port = closed.getsockname()[1]
closed.close()
prog = []
res = st.tcp_sweep(['127.0.0.1'], lambda d, t: prog.append((d, t)), deadline=5, port=open_port)
check('tcp_sweep: finds an open port with its connect time and reports progress', list(res) == ['127.0.0.1'] and isinstance(res['127.0.0.1'], int)
      and prog and prog[-1] == (1, 1), str((res, prog)))
check('tcp_sweep: closed port is not reported', st.tcp_sweep(['127.0.0.1'], None, deadline=5, port=closed_port) == {})
t0 = time.time()
st.tcp_sweep(['127.0.0.1'] * 500, None, deadline=0.0, port=closed_port)
check('tcp_sweep: honours the overall deadline', time.time() - t0 < 3)
srv.close()

# ---- deep_scan with the network calls stubbed
LAB_LINE = 'ssh-ed25519 ' + LAB.split()[1]


class FakeRun:
    calls = []

    def __init__(self, argv, **kw):
        FakeRun.calls.append(argv)
        ip = argv[-1]
        self.returncode = 0
        self.stdout = '' if ip.endswith('.12') else '# %s:22 SSH-2.0\n%s %s\n' % (ip, ip, LAB if ip.endswith('.10') else OTHER)
        self.stderr = ''


saved = (st.local_ipv4_ifaces, st.neighbor_table_v4, st.tcp_sweep, st.find_exe, st.subprocess.run)
try:
    st.local_ipv4_ifaces = lambda: [{'ip': '192.168.7.200', 'prefix': 24, 'name': 'Wi-Fi'}]
    fakes = {'192.168.7.%d' % i: 5 + i for i in (10, 11, 12, 13, 14)}
    st.tcp_sweep = lambda targets, progress=None, **kw: ({progress(len(targets), len(targets)) if progress else None} and fakes)
    pi = {'192.168.7.10', '192.168.7.12'}
    calls_n = []

    def neigh():
        calls_n.append(1)
        return [{'ip': ip, 'mac': 'D8:3A:DD:00:00:01', 'pi': True} for ip in pi] if len(calls_n) > 1 else []
    st.neighbor_table_v4 = neigh
    st.find_exe = lambda name: 'ssh-keyscan-stub' if name == 'ssh-keyscan' else saved[3](name)
    st.subprocess.run = lambda argv, **kw: FakeRun(argv, **kw)
    pr = []
    cands, err = st.deep_scan([LAB], lambda d, t: pr.append((d, t)))
finally:
    st.local_ipv4_ifaces, st.neighbor_table_v4, st.tcp_sweep, st.find_exe, st.subprocess.run = saved
check('deep_scan: no error, neighbour table read before AND after the sweep', err is None and len(calls_n) == 2 and pr, str((err, calls_n, pr)))
check('deep_scan: confirmed robot first, then Pi + ssh, then other ssh devices',
      [(c['host'], c['identity'], c['pi']) for c in cands] == [('192.168.7.10', 'confirmed', True), ('192.168.7.12', 'unknown', True),
                                                                ('192.168.7.11', 'unknown', False), ('192.168.7.13', 'unknown', False),
                                                                ('192.168.7.14', 'unknown', False)], str(cands))
check('deep_scan: labels, via, reachable, ms', cands[0]['label'] == 'Your robot (identity confirmed)' and cands[1]['label'] == 'Raspberry Pi with ssh'
      and cands[2]['label'] == 'Other device with ssh' and all(c['via'] in ('wifi', 'cable') and c['reachable'] and isinstance(c['ms'], int) for c in cands))
check('deep_scan: ssh-keyscan -T 4 -t ed25519, Pi hosts asked first',
      all(c[:5] == ['ssh-keyscan-stub', '-T', '4', '-t', 'ed25519'] for c in FakeRun.calls) and {c[-1] for c in FakeRun.calls[:2]} == pi, str(FakeRun.calls[:3]))
# more than 24 open hosts: only 24 are asked
FakeRun.calls = []
try:
    st.local_ipv4_ifaces = lambda: [{'ip': '192.168.7.200', 'prefix': 24, 'name': 'Wi-Fi'}]
    many_open = {'192.168.7.%d' % i: 3 for i in range(1, 41)}
    st.tcp_sweep = lambda targets, progress=None, **kw: many_open
    st.neighbor_table_v4 = lambda: []
    st.find_exe = lambda name: 'ssh-keyscan-stub'
    st.subprocess.run = lambda argv, **kw: FakeRun(argv, **kw)
    cands2, err2 = st.deep_scan([LAB])
finally:
    st.local_ipv4_ifaces, st.neighbor_table_v4, st.tcp_sweep, st.find_exe, st.subprocess.run = saved
check('deep_scan: identity checked for at most 24 hosts, all 40 still listed', err2 is None and len(FakeRun.calls) == 24 and len(cands2) == 40, str((len(FakeRun.calls), len(cands2))))
try:
    st.local_ipv4_ifaces = lambda: [{'ip': '8.8.8.8', 'prefix': 24, 'name': 'x'}]
    c3, e3 = st.deep_scan([LAB])
finally:
    st.local_ipv4_ifaces = saved[0]
check('deep_scan: no private network gives a plain error', c3 == [] and e3 and 'private' in e3, str(e3))

# ================================================================ U2 pure: timing, text
check('reconnect_delay: 2, 4, 8, 15, 30, 30, ...', [st.reconnect_delay(n) for n in range(1, 9)] == [2, 4, 8, 15, 30, 30, 30, 30]
      and st.RECONNECT_GIVE_UP == 600)

# ================================================================ U3 pure: redact
sample = ('psk=SuperSecret99 and token=abcDEF123456 "password": "my wifi pass" passphrase: hunter2 hunter3\n'
          '-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----\n'
          'GET /?token=zzTOP9999&x=1 session SESSIONTOKEN77 ok')
r = st.redact(sample, secrets=('SESSIONTOKEN77',))
check('redact: psk, password, passphrase, token=, PEM private key, exact secret all gone',
      not any(x in r for x in ('SuperSecret99', 'abcDEF123456', 'my wifi pass', 'hunter2', 'hunter3', 'b3BlbnNzaC1rZXktdjEAAAAA', 'zzTOP9999', 'SESSIONTOKEN77')), r)
check('redact: keys and harmless text stay', 'psk=' in r and 'token=' in r and '&x=1' in r and ' ok' in r and 'private key' in r, r)
check('redact: public key lines and plain text are untouched', st.redact('ssh-ed25519 AAAAC3Nza fingerprint SHA256:abc') == 'ssh-ed25519 AAAAC3Nza fingerprint SHA256:abc'
      and st.redact(None) == '' and st.redact('hello world') == 'hello world')

# ================================================================ U4 pure: versions, version.json parsing
check('version_newer: numeric, not text', st.version_newer('1.10', '1.9') and st.version_newer('2', '1.9.9') and st.version_newer('1.3.1', '1.3')
      and not st.version_newer('1.3', '1.3') and not st.version_newer('1.3.0', '1.3') and not st.version_newer('1.2', '1.3')
      and not st.version_newer('abc', '1.3') and not st.version_newer('1.3', None) and not st.version_newer('1.3-beta', '1.0'))
PG = st.UPDATE_PAGE_PREFIX + 'blob/main/x.md'
ok = st.parse_update_info(json.dumps({'version': '1.4', 'page': PG, 'notes': 'New things.'}))
check('parse_update_info: valid file', ok == {'version': '1.4', 'page': PG, 'notes': 'New things.'}, str(ok))
check('parse_update_info: foreign or odd page falls back to the default page',
      all(st.parse_update_info(json.dumps({'version': '1.4', 'page': p}))['page'] == st.DEFAULT_UPDATE_PAGE
          for p in ('https://evil.example/x', 'http://github.com/aniskoubaa/alfaisalx_students_projects/x', 'javascript:alert(1)',
                    st.UPDATE_PAGE_PREFIX + 'a b', 'https://github.com/aniskoubaa/alfaisalx_students_projects-evil/x', None, 5)))
check('parse_update_info: notes cut to 300 plain characters', len(st.parse_update_info(json.dumps({'version': '1.4', 'notes': 'x' * 900}))['notes']) == 300
      and '\n' not in st.parse_update_info(json.dumps({'version': '1.4', 'notes': 'a\nb\tc'}))['notes'])
check('parse_update_info: bad version / bad JSON / not an object are rejected',
      all(st.parse_update_info(x) is None for x in (json.dumps({'version': '1.4; rm'}), json.dumps({'version': 1.4}), json.dumps({'nope': 1}), '[1]', '{bad', b'\xff\xfe', '')))

# ================================================================ U3: diagnostics (in-process, planted secrets)
SECRET_LOG, SECRET_SET, SECRET_TOK = 'PlantedLogPsk8841', 'PlantedSettingPsk7712', 'PlantedTokenXYZ99'
app, d = new_app('diag', {'last_host': '10.1.2.3 psk=%s' % SECRET_SET, 'last_via': 'wifi', 'wifi_password': 'Another' + SECRET_SET})
app.log('info', 'joining Wi-Fi psk=%s token=%s' % (SECRET_LOG, SECRET_TOK))
app.log('info', 'session token is ' + app.token)
for i in range(80):
    app.log('info', 'logline-%d' % i)
dg = app.diagnostics()
txt = dg['text']
check('diagnostics: ok and plain text with the main sections',
      dg['ok'] and all(x in txt for x in ('Version: ' + st.VERSION, 'Running as: source', 'Operating system:', 'Python:', 'ssh -V:', 'Config folder: ' + d,
                                           'robot_hostname: turtlebot4', 'ssh key file present:', 'Trusted robots: 1 (Built-in robot key)',
                                           'Built-in lab key: on', 'auto_reconnect: on', 'update_check: on', 'State: disconnected', '== Last robot search ==',
                                           '== Last 60 log lines ==')), txt[:600])
check('diagnostics: planted Wi-Fi password (log + settings), token= value and the session token are redacted',
      not any(x in txt for x in (SECRET_LOG, SECRET_SET, SECRET_TOK, app.token)) and '[redacted]' in txt, txt[-900:])
check('diagnostics: only the last 60 log lines', 'logline-79' in txt and 'logline-20' in txt and 'logline-19' not in txt)
app.connect()
time.sleep(0.5)
app.discover()
txt = app.diagnostics()['text']
check('diagnostics: connection, last search and robot status once connected', 'State: connected' in txt and 'Host: fake' in txt and 'fake  reachable=yes' in txt
      and 'Robot Wi-Fi mode:' in txt and 'Battery %:' in txt, txt[txt.find('== Connection'):][:700])
app.disconnect()
app.shutdown()

# ================================================================ U4 pure/in-process: update check against a local server
SERVED = {'body': json.dumps({'version': '9.9', 'date': '2030-01-01', 'notes': 'Big news. ' * 60, 'page': 'https://evil.example/pwn'}).encode(), 'code': 200}
REQS = []


class UpdH(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        REQS.append({'path': self.path, 'ua': self.headers.get('User-Agent'), 'headers': {k.lower() for k in self.headers.keys()}})
        self.send_response(SERVED['code'])
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(SERVED['body'])))
        self.end_headers()
        self.wfile.write(SERVED['body'])


usrv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), UpdH)
threading.Thread(target=usrv.serve_forever, daemon=True).start()
UURL = 'http://127.0.0.1:%d/version.json' % usrv.server_address[1]
os.environ['STUDIO_UPDATE_URL'] = UURL

app, d = new_app('upd')
q = app.bus.subscribe()
r = app.check_updates(force=True)
evs = []
while not q.empty():
    evs.append(q.get_nowait())
upd_evs = [e for e in evs if e.get('ev') == 'update']
check('check_updates: newer version found, validated page and trimmed notes', r['ok'] and r['result'] == 'newer' and r['newer'] and r['latest'] == '9.9' and r['current'] == st.VERSION
      and r['page'] == st.DEFAULT_UPDATE_PAGE and len(r['notes']) == 300, str(r)[:300])
check('check_updates: publishes {ev:update,current,latest,page,notes}', len(upd_evs) == 1 and set(upd_evs[0]) == {'ev', 'current', 'latest', 'page', 'notes'}
      and upd_evs[0]['latest'] == '9.9', str(upd_evs))
check('check_updates: User-Agent TurtleBotStudio/<version>, no cookie / auth / identifiers',
      len(REQS) == 1 and REQS[0]['ua'] == 'TurtleBotStudio/' + st.VERSION and not (REQS[0]['headers'] & {'cookie', 'authorization', 'x-studio-token', 'referer'})
      and REQS[0]['path'] == '/version.json', str(REQS))
check('update_last is stored in the settings', app.settings['update_last']['latest'] == '9.9' and abs(app.settings['update_last']['t'] - time.time()) < 30)
n0 = len(REQS)
app.check_updates()
check('automatic check is skipped when the last check is younger than 24 h', len(REQS) == n0)
app.settings['update_last'] = {'t': time.time() - 25 * 3600, 'latest': '9.9'}
app.check_updates()
check('automatic check runs when the last one is older than 24 h', len(REQS) == n0 + 1)
app.settings['update_last'] = {'t': 0, 'latest': '1.0'}
app.settings['update_check'] = False
app.check_updates()
check('update_check off: no automatic request (the button still works)', len(REQS) == n0 + 1 and app.check_updates(force=True)['result'] == 'newer' and len(REQS) == n0 + 2)
app.settings['update_check'] = True
SERVED['body'] = json.dumps({'version': st.VERSION}).encode()
r = app.check_updates(force=True)
check('same version: result latest, not newer, no update event', r['result'] == 'latest' and r['newer'] is False and r['ok'])
SERVED['code'], SERVED['body'] = 404, b'not found'
while not q.empty():
    q.get_nowait()
r1 = app.check_updates(force=True)
r2 = app.check_updates(force=True)
logs = [e for e in list(app.bus.logs) if 'update check skipped' in e['text']]
check('404 (file not pushed yet): silent failure, result failed, logged once', r1['ok'] and r1['result'] == 'failed' and r2['result'] == 'failed' and len(logs) == 1, str((r1, logs)))
SERVED['code'], SERVED['body'] = 200, b'{"version": "9.9", "pad": "' + b'x' * 100000 + b'"}'
check('a file larger than 64 KB is not accepted', app.check_updates(force=True)['result'] == 'failed')
SERVED['code'], SERVED['body'] = 200, b'garbage'
check('garbage is not accepted', app.check_updates(force=True)['result'] == 'failed')
os.environ['STUDIO_UPDATE_URL'] = 'http://127.0.0.1:1/none'
check('server not reachable: failed, no exception', app.check_updates(force=True)['result'] == 'failed')
os.environ['STUDIO_UPDATE_URL'] = 'file:///etc/passwd'
check('non-http(s) update address is refused', app.check_updates(force=True)['result'] == 'failed')
os.environ['STUDIO_UPDATE_URL'] = UURL
SERVED['code'], SERVED['body'] = 200, json.dumps({'version': '9.9'}).encode()
n0 = len(REQS)
app.update_delay = 0.2
os.environ.pop('STUDIO_UPDATE_URL')
app.start_update_check()
time.sleep(0.8)
check('--fake without STUDIO_UPDATE_URL: no startup check', len(REQS) == n0)
os.environ['STUDIO_UPDATE_URL'] = UURL
r = app.post_settings({'update_dismissed': '9.9'})
check('update_dismissed is remembered per version (settings)', r['ok'] and app.settings['update_dismissed'] == '9.9'
      and app.update_status()['dismissed'] == '9.9')
check('update_dismissed / update_check / auto_reconnect are validated', app.post_settings({'update_dismissed': '1.x'})['ok'] is False
      and app.post_settings({'update_check': 'yes'})['ok'] is False and app.post_settings({'auto_reconnect': 1})['ok'] is False
      and app.post_settings({'update_check': False, 'auto_reconnect': False})['ok'] and app.settings['update_check'] is False and app.settings['auto_reconnect'] is False)
app.post_settings({'update_check': True, 'auto_reconnect': True, 'update_dismissed': ''})
check('update_dismissed "" clears it', app.settings['update_dismissed'] is None)
with open(os.path.join(d, 'settings.json'), encoding='utf-8') as f:
    sj = json.load(f)
check('new settings are saved in settings.json', sj['auto_reconnect'] is True and sj['update_check'] is True and 'update_last' in sj and 'update_dismissed' in sj)
app2, _ = new_app('upd_bad', {'auto_reconnect': 'x', 'update_check': 0, 'update_last': {'t': 'x', 'latest': '1;2'}, 'update_dismissed': 'zz'})
check('bad stored values fall back to safe ones', app2.settings['auto_reconnect'] is True and app2.settings['update_check'] is False
      and app2.settings['update_last'] == {} and app2.settings['update_dismissed'] is None, str({k: app2.settings[k] for k in ('auto_reconnect', 'update_check', 'update_last', 'update_dismissed')}))
app.shutdown()

# ================================================================ U4: unchanged save in the robot bridge (fake bridge subprocess)
BH = os.path.join(OUT, 'bridgehome')
os.makedirs(BH)
benv = dict(os.environ, STUDIO_BRIDGE_HOME=BH, PYTHONDONTWRITEBYTECODE='1', HOME=BH, USERPROFILE=BH)
bp = subprocess.Popen([sys.executable, '-u', os.path.join(STUDIO_DIR, 'robot_bridge.py'), '--fake'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                      stderr=subprocess.DEVNULL, env=benv)
bq = []


def bread():
    for raw in bp.stdout:
        try:
            bq.append(json.loads(raw.decode('utf-8', 'replace')))
        except ValueError:
            pass


threading.Thread(target=bread, daemon=True).start()
bseq = [0]


def bsend(cmd, **kw):
    bseq[0] += 1
    i = bseq[0]
    bp.stdin.write((json.dumps(dict(cmd=cmd, id=i, **kw)) + '\n').encode())
    bp.stdin.flush()
    return wait_for(lambda: next((e for e in bq if e.get('ev') == 'reply' and e.get('id') == i), None), 15)


code = os.path.join(BH, 'robot_code')
r = bsend('write_file', path='same.py', text='print(1)\n')
r2 = bsend('write_file', path='same.py', text='print(1)\n', overwrite=True, expect_sha1=r['sha1'])
check('write_file: identical content is {ok, unchanged:true}, no .bak is created', r['ok'] and r2['ok'] and r2.get('unchanged') is True and r2['sha1'] == r['sha1']
      and r2['backup'] is None and not os.path.exists(os.path.join(code, 'same.py.bak')), str(r2))
r3 = bsend('write_file', path='same.py', text='print(2)\n', overwrite=True)
check('write_file: a real change still writes and keeps the .bak', r3['ok'] and 'unchanged' not in r3 and r3['backup'] and open(os.path.join(code, 'same.py.bak'), 'rb').read() == b'print(1)\n')
bak_before = open(os.path.join(code, 'same.py.bak'), 'rb').read()
mt = os.path.getmtime(os.path.join(code, 'same.py'))
time.sleep(0.05)
r4 = bsend('write_file', path='same.py', text='print(2)\n', overwrite=True)
check('write_file: saving the same text again does not touch the file or replace the older .bak',
      r4.get('unchanged') is True and os.path.getmtime(os.path.join(code, 'same.py')) == mt and open(os.path.join(code, 'same.py.bak'), 'rb').read() == bak_before)
r5 = bsend('write_file', path='same.py', text='print(2)\n', overwrite=True, expect_sha1='0' * 40)
check('write_file: the changed-on-robot check still comes first', r5['ok'] is False and 'changed on the robot' in r5['error'])
try:
    bp.stdin.close()
    bp.wait(5)
except Exception:
    bp.kill()

# ================================================================ U2: reconnect logic in-process (fast delays)
app, d = new_app('reconn')
app.reconnect_delays = (0.2, 0.2)
app.reconnect_give_up = 3.0
states = []
qq = app.bus.subscribe()
check('connect (fake) works', app.connect().get('ok'))
disc_calls = []
real_discover = app.discover


def spy_discover(extra=None):
    disc_calls.append(time.time())
    return real_discover(extra)


app.discover = spy_discover
app.bridge_script = os.path.join(d, 'no_such_bridge.py')   # every reconnect attempt now fails
check('fake_drop kills the fake bridge', app.fake_drop()['ok'])
gave = wait_for(lambda: app.bus.last_conn.get('state') == 'disconnected' and app.bus.last_conn.get('error'), 15)
evs = []
while not qq.empty():
    evs.append(qq.get_nowait())
conns = [e for e in evs if e.get('ev') == 'conn']
rec = [e for e in conns if e['state'] == 'reconnecting']
check('reconnecting events carry host, via, attempt, next_in, since', rec and rec[0]['host'] == 'fake' and rec[0]['via'] == 'custom' and rec[0]['attempt'] == 1
      and rec[0]['next_in'] == 0.2 and isinstance(rec[0]['since'], float) and [e['attempt'] for e in rec][:3] == [1, 2, 3], str(rec[:3]))
check('no error / connecting noise between reconnect attempts, then one final disconnected',
      [e['state'] for e in conns[conns.index(rec[0]):] if e['state'] != 'reconnecting'] == ['disconnected'], str([e['state'] for e in conns]))
check('gives up with a plain message and state disconnected', gave == 'gave up reconnecting after 3 seconds', str(gave))
check('after 2 failed attempts the quick discover runs', len(disc_calls) >= 1, str(disc_calls))
check('the default give-up text says 10 minutes', st.RECONNECT_GIVE_UP == 600 and st.gave_up_text(600) == 'gave up reconnecting after 10 minutes')
check('no reconnect state is left after giving up', app.reconn is None)
app.shutdown()

# ================================================================ HTTP in --fake (real studio.py + real robot_bridge.py)
HOME = os.path.join(OUT, 'fakehome')
os.makedirs(HOME)
CFG = os.path.join(OUT, 'httpcfg')
SERVED['code'], SERVED['body'] = 200, json.dumps({'version': '9.9', 'notes': 'Hello.', 'page': st.UPDATE_PAGE_PREFIX + 'blob/main/z.md'}).encode()
env = dict(os.environ, HOME=HOME, USERPROFILE=HOME, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', STUDIO_UPDATE_URL=UURL)
proc = subprocess.Popen([sys.executable, '-u', os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--port', '0', '--config-dir', CFG,
                         '--fake-home', os.path.join(CFG, 'home'), '--heartbeat', '1', '--update-delay', '0.5'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
url = {}
got_url = threading.Event()


def read_stdout():
    for raw in proc.stdout:
        m = re.search(r'http://127\.0\.0\.1:(\d+)/\?token=(\S+)', raw.decode('utf-8', 'replace'))
        if m:
            url['port'], url['token'] = int(m.group(1)), m.group(2)
            got_url.set()


threading.Thread(target=read_stdout, daemon=True).start()
try:
    check('studio.py --fake starts', got_url.wait(20))
    PORT, TOKEN = url['port'], url['token']

    def call_raw(method, path, body=None, timeout=60):
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=timeout)
        h = {'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        c.request(method, path, body=data, headers=h)
        resp = c.getresponse()
        txt = resp.read()
        c.close()
        return resp.status, txt

    def call(method, path, body=None, timeout=60):
        return json.loads(call_raw(method, path, body, timeout)[1].decode('utf-8'))

    sse = bytearray()

    def read_sse():
        try:
            c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=300)
            c.request('GET', '/api/events', headers={'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN})
            resp = c.getresponse()
            while True:
                x = resp.read1(4096)
                if not x:
                    break
                sse.extend(x)
        except (OSError, http.client.HTTPException):
            pass
    threading.Thread(target=read_sse, daemon=True).start()

    def events():
        out = []
        for ln in bytes(sse).decode('utf-8', 'replace').splitlines():
            if ln.startswith('data: '):
                try:
                    out.append(json.loads(ln[6:]))
                except ValueError:
                    pass
        return out

    def conn_states(since=0):
        return [(e['state'], e) for e in events()[since:] if e.get('ev') == 'conn']

    def connect_marked():
        """Connect, wait until the event stream shows it, and return the stream position to look at events from."""
        call('POST', '/api/connect', {})
        wait_for(lambda: conn_states() and conn_states()[-1][0] == 'connected', 5)
        time.sleep(0.2)
        return len(events())

    # ---- U4 over HTTP: the startup check (5 s in real life, 0.5 s here)
    up = wait_for(lambda: call('GET', '/api/update_status') if call('GET', '/api/update_status')['latest'] else None, 10)
    check('startup update check ran by itself: GET update_status says 9.9 is newer', up and up['newer'] is True and up['latest'] == '9.9' and up['current'] == st.VERSION
          and up['page'].startswith(st.UPDATE_PAGE_PREFIX) and up['notes'] == 'Hello.' and up['dismissed'] is None, str(up))
    check('the update event reached the event stream', any(e.get('ev') == 'update' and e.get('latest') == '9.9' for e in events()))
    j = call('POST', '/api/check_updates', {'force': True})
    check('POST check_updates {force:true}: result newer', j['ok'] and j['result'] == 'newer')
    SERVED['body'] = json.dumps({'version': st.VERSION}).encode()
    j = call('POST', '/api/check_updates', {'force': True})
    check('POST check_updates: "latest" when up to date', j['result'] == 'latest' and j['newer'] is False)
    SERVED['code'] = 500
    j = call('POST', '/api/check_updates', {'force': True})
    check('POST check_updates: "failed" when the server errors', j['ok'] and j['result'] == 'failed' and j['error'])
    SERVED['code'] = 200

    # ---- U3 over HTTP
    j = call('GET', '/api/diagnostics')
    check('GET diagnostics: ok, text, without the session token', j['ok'] and 'TurtleBot Studio diagnostics' in j['text'] and TOKEN not in j['text'] and 'Version: ' + st.VERSION in j['text'])
    call('POST', '/api/settings', {'last_host': 'fake'})

    # ---- U1 over HTTP (fake search)
    n_ev = len(events())
    box = {}

    def deep_call():
        box['r'] = call('POST', '/api/deep_discover', {})
    th = threading.Thread(target=deep_call)
    th.start()
    time.sleep(0.5)
    j2 = call('POST', '/api/deep_discover', {})
    th.join(20)
    r = box.get('r') or {}
    check('a second search while one runs is refused: already searching', j2 == {'ok': False, 'error': 'already searching'}, str(j2))
    c0 = (r.get('candidates') or [{}])[0]
    check('POST deep_discover (fake): one confirmed candidate "fake"', r.get('ok') and len(r['candidates']) == 1 and c0['host'] == 'fake' and c0['identity'] == 'confirmed'
          and c0['reachable'] is True and c0['pi'] is True and c0['via'] in ('wifi', 'cable', 'custom') and 'ms' in c0 and 'label' in c0, str(r))
    time.sleep(0.4)
    new = events()[n_ev:]
    prog = [e for e in new if e.get('ev') == 'deep_progress']
    disc = [e for e in new if e.get('ev') == 'discover' and e.get('deep')]
    check('deep_progress events (done/total, rising) then one discover event with deep:true',
          len(prog) >= 5 and all(0 <= e['done'] <= e['total'] for e in prog) and [e['done'] for e in prog] == sorted(e['done'] for e in prog)
          and len(disc) == 1 and disc[0]['candidates'][0]['host'] == 'fake', str((len(prog), disc)))
    j3 = call('POST', '/api/deep_discover', {})
    check('a new search is possible after the first finished', j3['ok'])

    # ---- U2 over HTTP
    check('fake_drop with nothing connected: clean error', call('POST', '/api/fake_drop', {}) == {'ok': False, 'error': 'not connected'})
    mark = connect_marked()
    check('connect (fake)', conn_states()[-1][0] == 'connected')
    check('fake_drop ends the bridge', call('POST', '/api/fake_drop', {})['ok'])
    rs = wait_for(lambda: [e for s, e in conn_states(mark) if s == 'reconnecting'], 6)
    check('drop -> state reconnecting with attempt 1, next_in 2, host, via, since', rs and rs[0]['attempt'] == 1 and rs[0]['next_in'] == 2 and rs[0]['host'] == 'fake'
          and rs[0]['via'] == 'custom' and abs(rs[0]['since'] - time.time()) < 30, str(rs[:1]))
    back = wait_for(lambda: [1 for s, e in conn_states(mark) if s == 'connected'], 12)
    check('...then connected again within about 10 s, with no error state in between',
          bool(back) and 'error' not in [s for s, e in conn_states(mark)], str([s for s, e in conn_states(mark)]))
    j = call('POST', '/api/bridge', {'cmd': 'ping'})
    check('after reconnect the bridge answers (status stream restarted by Studio)', j.get('ok'), str(j))
    time.sleep(1.5)
    st_ev = [e for e in events()[mark:] if e.get('ev') == 'status']
    check('status events keep flowing after reconnect', len(st_ev) >= 1)

    mark = len(events())
    call('POST', '/api/fake_drop', {})
    wait_for(lambda: [1 for s, e in conn_states(mark) if s == 'reconnecting'], 6)
    j = call('POST', '/api/reconnect_cancel', {})
    check('POST reconnect_cancel while reconnecting: ok', j['ok'] and j['was_reconnecting'] is True, str(j))
    after = wait_for(lambda: [s for s, e in conn_states(mark)][-1:] == ['disconnected'], 5)
    time.sleep(3)
    sts = [s for s, e in conn_states(mark)]
    check('cancel: state disconnected, and it never connects again by itself', after and sts[-1] == 'disconnected' and 'connected' not in sts, str(sts))
    check('reconnect_cancel when nothing runs is harmless', call('POST', '/api/reconnect_cancel', {}) == {'ok': True, 'was_reconnecting': False})

    mark = connect_marked()
    call('POST', '/api/fake_drop', {})
    wait_for(lambda: [1 for s, e in conn_states(mark) if s == 'reconnecting'], 6)
    call('POST', '/api/disconnect', {})
    time.sleep(4)
    sts = [s for s, e in conn_states(mark)]
    check('manual Disconnect during a reconnect stops it for good', sts[-1] == 'disconnected' and 'connected' not in sts, str(sts))

    mark = connect_marked()
    call('POST', '/api/disconnect', {})
    time.sleep(3)
    sts = [s for s, e in conn_states(mark)]
    check('manual Disconnect never reconnects', 'reconnecting' not in sts and sts[-1] == 'disconnected', str(sts))

    s = call('POST', '/api/settings', {'auto_reconnect': False})
    check('setting auto_reconnect can be switched off', s['ok'] and s['auto_reconnect'] is False)
    mark = connect_marked()
    call('POST', '/api/fake_drop', {})
    er = wait_for(lambda: [e for s2, e in conn_states(mark) if s2 == 'error'], 6)
    time.sleep(3)
    sts = [s2 for s2, e in conn_states(mark)]
    check('auto_reconnect off: a drop is reported as an error and nothing reconnects', er and 'reconnecting' not in sts and 'connected' not in sts, str(sts))
    call('POST', '/api/settings', {'auto_reconnect': True})
    call('POST', '/api/disconnect', {})

    # ---- U2/U3: the user takes over by pressing Connect while reconnecting
    mark = connect_marked()
    call('POST', '/api/fake_drop', {})
    wait_for(lambda: [1 for s2, e in conn_states(mark) if s2 == 'reconnecting'], 6)
    j = call('POST', '/api/connect', {})
    time.sleep(0.5)
    check('Connect during a reconnect takes over cleanly (connected, reconnect loop cancelled)', j['ok'] and conn_states()[-1][0] == 'connected')
    call('POST', '/api/disconnect', {})

    # ---- settings over HTTP
    s = call('GET', '/api/settings')
    check('GET settings has auto_reconnect, update_check, update_last, update_dismissed', s['auto_reconnect'] is True and s['update_check'] is True
          and set(s['update_last']) == {'t', 'latest'} and s['update_dismissed'] is None, str({k: s.get(k) for k in ('auto_reconnect', 'update_check', 'update_last')}))
    s = call('POST', '/api/settings', {'update_dismissed': '9.9'})
    check('POST settings update_dismissed', s['ok'] and s['update_dismissed'] == '9.9')

    # ---- no token / secrets in diagnostics even after all this
    j = call('GET', '/api/diagnostics')
    check('diagnostics after the run: lists the reconnect in the log lines and still has no token', 'reconnect' in j['text'] and TOKEN not in j['text'])
    leaks = []
    for root, _, files in os.walk(CFG):
        for fn in files:
            if fn == 'instance.json':   # v1.3: the running-instance record holds the token on purpose (user-only folder)
                continue
            if TOKEN.encode() in open(os.path.join(root, fn), 'rb').read():
                leaks.append(fn)
    check('the session token is in no file of the config folder (except instance.json)', not leaks, str(leaks))
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()

# ---- /api/fake_drop does not exist outside fake mode (in-process server, no robot, nothing is started)
real_app = st.Studio(st.parse_args(['--config-dir', os.path.join(OUT, 'realcfg'), '--no-browser']))
rsrv = st.serve(real_app, 0)
threading.Thread(target=rsrv.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True).start()
try:
    c = http.client.HTTPConnection('127.0.0.1', real_app.port, timeout=10)
    c.request('POST', '/api/fake_drop', body=b'{}', headers={'Host': '127.0.0.1:%d' % real_app.port, 'X-Studio-Token': real_app.token, 'Content-Type': 'application/json'})
    resp = c.getresponse()
    body = resp.read()
    check('POST /api/fake_drop is 404 when not in fake mode', resp.status == 404, str((resp.status, body)))
    c.request('POST', '/api/deep_discover', body=b'{}', headers={'Host': '127.0.0.1:%d' % real_app.port, 'X-Studio-Token': 'wrong', 'Content-Type': 'application/json'})
    resp = c.getresponse()
    resp.read()
    check('deep_discover needs the session token', resp.status == 403)
    c.close()
finally:
    rsrv.shutdown()
    rsrv.server_close()
    real_app.shutdown()
usrv.shutdown()

shutil.rmtree(OUT, ignore_errors=True) if fails == 0 else print('generated files are in', OUT)
print('\n%d failure(s)' % fails)
sys.exit(fails)
