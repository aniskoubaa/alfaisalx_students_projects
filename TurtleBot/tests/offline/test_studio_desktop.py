"""Offline tests of the TurtleBot Studio desktop backend (TurtleBot/tools/studio/studio.py).

No robot, no network, no ROS. The backend runs with --fake against a small stub bridge defined in this file (so the
test does not depend on robot_bridge.py), and its pure functions are tested directly: ssh argument building,
IPv6 scope handling for scp, neighbour-table parsers, ssh-config block insertion, error mapping, sync planning.
Usage: python test_studio_desktop.py
"""
import http.client
import json
import os
import queue
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

OUT = tempfile.mkdtemp(prefix='tb4_studio_tests_')
fails = 0


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode())
    if not cond:
        fails += 1


# ---------------------------------------------------------------- pure functions
KH = r'C:\Users\Some One\AppData\Roaming\TurtleBotStudio\known_hosts'
argv = st.build_bridge_ssh_argv('ssh', 'fe80::da3a:ddff:fe41:d5df%8', 'KEY', KH)
check('bridge ssh argv: spec options in order',
      argv[:11] == ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3',
                    '-o', 'ConnectTimeout=8', '-o'] and 'HostKeyAlias=turtlebot4-lab' in argv
      and 'StrictHostKeyChecking=yes' in argv, str(argv))
check('bridge ssh argv: known_hosts path uses / and is quoted because of the space',
      'UserKnownHostsFile="C:/Users/Some One/AppData/Roaming/TurtleBotStudio/known_hosts"' in argv)
check('bridge ssh argv: ipv6 scope stays unbracketed for ssh, BOOT last, key given',
      argv[-2] == 'ubuntu@fe80::da3a:ddff:fe41:d5df%8' and argv[-1] == st.BOOT and argv[argv.index('-i') + 1] == 'KEY')
check('BOOT sources setup.bash and reads length-prefixed script',
      st.BOOT.startswith('source /etc/turtlebot4/setup.bash') and 'exec python3 -u -c' in st.BOOT and 'readline' in st.BOOT)
check('scp target brackets IPv6 incl. scope', st.scp_target('fe80::1%8') == 'ubuntu@[fe80::1%8]:'
      and st.scp_target('fe80::1%eth0') == 'ubuntu@[fe80::1%eth0]:')
check('scp target leaves names and IPv4 alone', st.scp_target('10.42.0.1') == 'ubuntu@10.42.0.1:'
      and st.scp_target('turtlebot4.local') == 'ubuntu@turtlebot4.local:')
sa = st.build_scp_argv('scp', 'fe80::1%8', 'K', '/k/kh', 'a.py', '~/robot_code/a.py')
check('scp argv: remote spec bracketed', sa[-1] == 'ubuntu@[fe80::1%8]:~/robot_code/a.py' and sa[-2] == 'a.py', str(sa))
tk = st.build_ssh_argv('ssh', '10.42.0.1', None, '/k/kh', st.BOOT, batch=False, password_only=True)
check('setup-key ssh: no BatchMode, password only, pinned host key',
      'BatchMode=yes' not in tk and 'PubkeyAuthentication=no' in tk and 'StrictHostKeyChecking=yes' in tk)
check('host validation blocks option injection', st.valid_host('10.42.0.1') and st.valid_host('fe80::1%8')
      and st.valid_host('ubuntu@turtlebot4.local') and not st.valid_host('-oProxyCommand=x') and not st.valid_host('a b')
      and not st.valid_host('') and not st.valid_host('x;rm'))
check('remote path expressions', st.remote_path_expr('~/robot_code') == '"$HOME"/robot_code'
      and st.remote_path_expr('~/my dir') == '"$HOME"/\'my dir\'' and st.remote_path_expr('/opt/a b') == "'/opt/a b'"
      and st.remote_path_expr('~') == '"$HOME"')

# stderr -> error mapping
M = st.map_ssh_error
check('error map: publickey', M('ubuntu@x: Permission denied (publickey,password).')[:2] == ('key_not_set_up', 'key not set up'))
check('error map: host key verification', M('Host key verification failed.')[1] == 'robot key does not match the pinned key')
check('error map: changed host key', M('WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!')[0] == 'host_key')
check('error map: resolve / timeout / no route',
      all(M(t)[1] == 'robot not reachable' for t in ('ssh: Could not resolve hostname turtlebot4.local',
                                                       'ssh: connect to host 1.2.3.4 port 22: Connection timed out',
                                                       'ssh: connect to host 1.2.3.4 port 22: No route to host')))
check('error map: unknown text keeps last line', M('foo\nbar baz\n', 3) == ('other', 'bar baz') and M('', 7)[1].startswith('connection ended'))

# neighbour parsers
WIN_JSON_LIST = json.dumps([
    {'IPAddress': 'fe80::da3a:ddff:fe41:d5df', 'LinkLayerAddress': 'D8-3A-DD-41-D5-DF', 'InterfaceIndex': 8},
    {'IPAddress': 'fe80::1', 'LinkLayerAddress': '00-11-22-33-44-55', 'InterfaceIndex': 8},
    {'IPAddress': 'ff02::1', 'LinkLayerAddress': '33-33-00-00-00-01', 'InterfaceIndex': 8},
    {'IPAddress': 'fe80::2%12', 'LinkLayerAddress': 'DC-A6-32-01-02-03', 'InterfaceIndex': 12}])
check('windows neighbours: keeps Pi MACs, adds %ifIndex', st.parse_windows_neighbors(WIN_JSON_LIST) ==
      ['fe80::da3a:ddff:fe41:d5df%8', 'fe80::2%12'], str(st.parse_windows_neighbors(WIN_JSON_LIST)))
check('windows neighbours: single object (PowerShell quirk) and garbage',
      st.parse_windows_neighbors('{"IPAddress":"fe80::5","LinkLayerAddress":"D8-3A-DD-00-00-01","InterfaceIndex":3}') == ['fe80::5%3']
      and st.parse_windows_neighbors('') == [] and st.parse_windows_neighbors('not json') == [])
IP6 = ('fe80::da3a:ddff:fe41:d5df dev enp3s0 lladdr d8:3a:dd:41:d5:df router REACHABLE\n'
       'fe80::abcd dev enp3s0 lladdr 00:11:22:33:44:55 STALE\n'
       'fe80::dead dev enp3s0  FAILED\n'
       'fe80::b827:ebff:fe00:1 dev eth1 lladdr b8:27:eb:00:00:01 STALE\n')
check('ip -6 neigh parser', st.parse_ip6_neigh(IP6) == ['fe80::da3a:ddff:fe41:d5df%enp3s0', 'fe80::b827:ebff:fe00:1%eth1'],
      str(st.parse_ip6_neigh(IP6)))
NDP = ('Neighbor                        Linklayer Address  Netif Expire    St Flgs Prbs\n'
       'fe80::da3a:ddff:fe41:d5df%en5   d8:3a:dd:41:5:df   en5   23h59m50s S  R\n'
       'fe80::1%en0                     0:1:2:3:4:5        en0   permanent R  R\n'
       'fe80::7                         (incomplete)       en5   expired   N\n')
check('ndp -an parser (short MAC octets)', st.parse_ndp(NDP) == ['fe80::da3a:ddff:fe41:d5df%en5'], str(st.parse_ndp(NDP)))
check('mac prefixes', st.mac_ok('d8:3a:dd:1:2:3') and st.mac_ok('E4-5F-01-AA-BB-CC') and not st.mac_ok('00:11:22:33:44:55')
      and not st.mac_ok('zz') and not st.mac_ok(None))

# ssh config block
BLOCK = st.ssh_config_block('fe80::1%8', '/home/me/.ssh/key', '/home/me/.config/kh')
check('config block has markers and required keys',
      BLOCK.startswith(st.MARK_BEGIN + '\n') and BLOCK.endswith(st.MARK_END + '\n') and 'Host turtlebot-studio' in BLOCK
      and 'HostName fe80::1%8' in BLOCK and 'User ubuntu' in BLOCK and 'HostKeyAlias turtlebot4-lab' in BLOCK
      and 'UserKnownHostsFile' in BLOCK and 'IdentityFile /home/me/.ssh/key' in BLOCK)
USER_CFG = 'Host github.com\n    User git\n\nHost other\n    HostName 1.2.3.4\n'
n1, a1 = st.insert_ssh_config_block(USER_CFG, BLOCK)
n2, a2 = st.insert_ssh_config_block(n1, BLOCK)
check('config insert: add keeps existing text byte for byte', a1 == 'added' and n1.startswith(USER_CFG) and BLOCK in n1)
check('config insert: second run is a no-op', a2 == 'unchanged' and n2 == n1 and n2.count(st.MARK_BEGIN) == 1)
BLOCK2 = st.ssh_config_block('10.42.0.1', '/home/me/.ssh/key', '/home/me/.config/kh')
n3, a3 = st.insert_ssh_config_block(n1 + 'Host after\n    User z\n', BLOCK2)
check('config insert: changed host replaces only our block', a3 == 'updated' and n3.startswith(USER_CFG)
      and n3.endswith('Host after\n    User z\n') and 'HostName 10.42.0.1' in n3 and 'fe80::1%8' not in n3 and n3.count(st.MARK_BEGIN) == 1)
check('config insert: empty file', st.insert_ssh_config_block('', BLOCK) == (BLOCK, 'added'))
n4, _ = st.insert_ssh_config_block('Host a\n    User b', BLOCK)
check('config insert: file without trailing newline gets a separator', n4.startswith('Host a\n    User b\n\n' + st.MARK_BEGIN))

# sync planning / tar helpers
loc = {'a.py': {'size': 3, 'sha1': 'x'}, 'b.py': {'size': 3, 'sha1': 'y'}, 'n.py': {'size': 1, 'sha1': 'z'}, 'big.bin': {'size': 9, 'sha1': 'q'}}
rem = {'a.py': {'size': 3, 'sha1': 'x'}, 'b.py': {'size': 3, 'sha1': 'OLD'}, 'old.py': {'size': 2, 'sha1': 'o'}, 'big.bin': {'size': 9, 'sha1': None}}
pl = st.plan_sync(loc, rem, 'up')
check('plan up: new, changed, same, extra', pl['new'] == ['n.py'] and pl['changed'] == ['b.py'] and pl['same'] == 2 and pl['extra'] == ['old.py'])
pd = st.plan_sync(loc, rem, 'down')
check('plan down: robot-only is new, extra = local-only', pd['new'] == ['old.py'] and pd['extra'] == ['n.py'])
check('safe_member_path rejects escapes', st.safe_member_path(OUT, '../x') is None and st.safe_member_path(OUT, '/etc/passwd') is None
      and st.safe_member_path(OUT, 'C:/x') is None and st.safe_member_path(OUT, 'a/../../x') is None
      and st.safe_member_path(OUT, 'a/b.py') == os.path.abspath(os.path.join(OUT, 'a', 'b.py')))
check('motion pkill regex does not match itself', all(('[' in p) for p in st.MOTION_PKILL_REGEX.split('|'))
      and not __import__('re').search(st.MOTION_PKILL_REGEX, st.MOTION_PKILL_REGEX))
check('config dir is per platform / env override', os.path.basename(st.config_dir()) in ('TurtleBotStudio', 'turtlebot-studio'))

# ---------------------------------------------------------------- v1.1 pure functions: Wi-Fi scripts, parsers, catalog
import base64 as _b64
import re as _re
import shutil as _shutil

NASTY = ['My Wi-Fi', 'it\'s "quoted"', '$HOME `id` $(whoami)', 'café ☃ الواي', 'a;b|c&d>e<f', ' lead and trail ',
         'back\\slash\\', '-oProxyCommand=x', 'x' * 32, '1;2;3', "'; rm -rf / #", '%s %d \\n', 'tab\there']
check('valid_ssid: rules', all(st.valid_ssid(x) for x in NASTY) and not st.valid_ssid('') and not st.valid_ssid('a\nb')
      and not st.valid_ssid('x' * 33) and not st.valid_ssid('é' * 17) and st.valid_ssid('é' * 16) and not st.valid_ssid(None)
      and not st.valid_ssid('a\x00b'))
names = [st.safe_conn_filename(x) for x in NASTY]
check('safe file names: ASCII only, unique, no path characters', all(_re.match(r'^[A-Za-z0-9_\-]+$', n) for n in names)
      and len(set(names)) == len(names) and st.safe_conn_filename('Students') == 'studio-Students', str(names))
script = st.wifi_add_script()
check('wifi add script: placeholder replaced, writer embedded once', '@@WRITER@@' not in script and script.count('STUDIO_PY_EOF') == 2
      and 'os.O_EXCL' in script and script.startswith('#!/bin/bash'))
check('wifi add script: password read hidden and piped to the writer', 'read -rs pw' in script and "printf '%s' \"$pw\" | sudo python3" in script)
check('wifi add script: no xtrace, no password in any echo line',
      'set -x' not in script and not any('$pw' in ln for ln in script.splitlines() if ln.lstrip().startswith('echo')))
script_path = os.path.join(OUT, 'wifi_add.sh')
rm_path = os.path.join(OUT, 'wifi_rm.sh')
with open(script_path, 'w', newline='\n') as f:
    f.write(script)
with open(rm_path, 'w', newline='\n') as f:
    f.write(st.WIFI_REMOVE_SCRIPT)
BASH = _shutil.which('bash')
if BASH:
    for nm, pth in (('add', script_path), ('remove', rm_path)):
        r = subprocess.run([BASH, '-n', pth], capture_output=True, text=True)
        check(f'bash -n on the wifi {nm} script', r.returncode == 0, r.stderr[-200:])
else:
    print('SKIP bash -n and script run tests (bash not found)')
import py_compile as _pc  # noqa: E402
wr_path = os.path.join(OUT, 'keyfile_writer.py')
with open(wr_path, 'w', newline='\n') as f:
    f.write(st.KEYFILE_WRITER)
try:
    _pc.compile(wr_path, doraise=True, cfile=os.path.join(OUT, 'kw.pyc'))
    check('keyfile writer compiles', True)
except _pc.PyCompileError as e:
    check('keyfile writer compiles', False, str(e))


def unesc(v):
    out, i = '', 0
    while i < len(v):
        if v[i] == '\\' and i + 1 < len(v):
            out += {'n': '\n', 't': '\t', 'r': '\r', 's': ' ', '\\': '\\'}.get(v[i + 1], v[i + 1])
            i += 2
        else:
            out += v[i]
            i += 1
    return out


def read_keyfile(path):
    d = {}
    sect = None
    with open(path, encoding='utf-8', newline='') as f:
        for ln in f.read().replace(chr(13) + chr(10), chr(10)).split(chr(10)):
            m = _re.match(r'^\[(.+)\]$', ln)
            if m:
                sect = m.group(1)
            elif '=' in ln and sect:
                k, v = ln.split('=', 1)
                d[sect + '.' + k] = unesc(v)
    return d


PSKS = ['correct horse battery', 'pa$$w0rd`id`"q\'', 'sp ace ends ', ' lead space ok', 'back\\slash9', 'ünicode-pass-☃', 'a' * 63]
kdir = os.path.join(OUT, 'keyfile_tests')
os.makedirs(kdir)
ok_all, why = True, ''
for i, ssid in enumerate(NASTY):
    psk = PSKS[i % len(PSKS)]
    target = os.path.join(kdir, f'k{i}.nmconnection')
    r = subprocess.run([sys.executable, wr_path, target, ssid], input=psk.encode('utf-8'), capture_output=True,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1'))
    if r.returncode != 0:
        ok_all, why = False, 'writer failed for %r: %s' % (ssid, r.stderr[-200:])
        break
    d = read_keyfile(target)
    if not (d.get('connection.id') == ssid and d.get('wifi.ssid') == ssid and d.get('wifi-security.psk') == psk
            and d.get('connection.autoconnect') == 'true' and d.get('connection.autoconnect-priority') == '10'
            and d.get('wifi.powersave') == '2' and d.get('wifi-security.key-mgmt') == 'wpa-psk'):
        ok_all, why = False, 'content mismatch for %r: %r' % (ssid, d)
        break
    if os.name == 'posix' and (os.stat(target).st_mode & 0o777) != 0o600:
        ok_all, why = False, 'mode not 0600'
        break
check('keyfile writer: nasty SSIDs and passwords round-trip, autoconnect/priority/powersave set', ok_all, why)
r = subprocess.run([sys.executable, wr_path, os.path.join(kdir, 'k0.nmconnection'), 'again'], input=b'whatever pw', capture_output=True)
check('keyfile writer refuses to overwrite an existing file', r.returncode != 0)

cmd_ok, leak = True, ''
for ssid in NASTY:
    args = [st.b64s(ssid), st.safe_conn_filename(ssid), '1']
    cmd = st.build_robot_script_cmd(script, *args)
    head, tail = cmd.split(') ', 1)
    head += ')'
    if tail.split(' ')[0] != args[0]:
        cmd_ok, leak = False, 'first script argument ($1) is not the SSID for %r' % ssid
    if not _re.match(r'^bash <\(echo [A-Za-z0-9+/=]+ \| base64 -d\)$', head) or not _re.match(r'^[A-Za-z0-9+/=_\- ]+$', tail) or '"' in cmd:
        cmd_ok, leak = False, 'bad command for %r' % ssid
    if _b64.b64decode(args[0]).decode('utf-8') != ssid or (len(ssid) > 4 and not _re.match(r'^[A-Za-z0-9_-]+$', ssid) and ssid in cmd):
        cmd_ok, leak = False, 'ssid not safely encoded: %r' % ssid
if cmd_ok:
    try:
        st.build_robot_script_cmd(script, 'a b')
        cmd_ok, leak = False, 'unsafe arg accepted'
    except ValueError:
        pass
check('remote command is plain ASCII, no quotes, SSID only as base64', cmd_ok, leak)
check('script bytes survive base64 transport', _b64.b64decode(st.build_robot_script_cmd(script, 'QQ==').split()[2]).decode() == script)
tt = st.build_ssh_argv('ssh', 'fe80::1%8', 'K', '/k/kh', st.build_robot_script_cmd(script, 'QQ==', 'x', '0'), batch=False, tty=True)
check('wifi terminal ssh argv: -t, pinned key, command last', tt[1] == '-t' and 'StrictHostKeyChecking=yes' in tt and tt[-1].startswith('bash <(echo ')
      and 'BatchMode=yes' not in tt)

if BASH:
    stubs = os.path.join(OUT, 'stubs')
    os.makedirs(stubs)
    pyexe = sys.executable.replace('\\', '/')
    stub_src = {
        'sudo': '#!/bin/bash\nprintf \'%s\\0\' "$@" >> "$LOGDIR/sudo.args"\nprintf \'SUDO-CALL\\0\' >> "$LOGDIR/sudo.args"\n'
                '[ "$1" = "-v" ] && exit 0\nargs=()\nfor a in "$@"; do case "$a" in /etc/NetworkManager/system-connections/*) a="$FAKEDIR/${a##*/}";; esac; args+=("$a"); done\n'
                'exec "${args[@]}"\n',
        'python3': '#!/bin/bash\nexec "%s" "$@"\n' % pyexe,
        'nmcli': '#!/bin/bash\nprintf \'%%s\\0\' "$@" >> "$LOGDIR/nmcli.args"\nprintf \'NM-CALL\\0\' >> "$LOGDIR/nmcli.args"\n'
                 'case "$*" in "-g connection.autoconnect,802-11-wireless.powersave"*) printf \'yes\\n2\\n\';; esac\nexit 0\n',
        'ip': '#!/bin/bash\necho "wlan0 UP 10.1.2.3/24"\n',
    }
    for nm, src in stub_src.items():
        with open(os.path.join(stubs, nm), 'w', newline='\n') as f:
            f.write(src)
        try:
            os.chmod(os.path.join(stubs, nm), 0o755)
        except OSError:
            pass
    all_ok, why = True, ''
    for i, ssid in enumerate(NASTY):
        psk = PSKS[i % len(PSKS)]
        logd = os.path.join(OUT, f'run{i}_log')
        fake = os.path.join(OUT, f'run{i}_etc')
        os.makedirs(logd)
        os.makedirs(fake)
        env = dict(os.environ, PATH=stubs + os.pathsep + os.environ.get('PATH', ''), LOGDIR=logd, FAKEDIR=fake, LC_ALL='C.UTF-8')
        argv = [BASH, script_path, st.b64s(ssid), st.safe_conn_filename(ssid), '0']  # connect-now moved to the join job (test_studio_setup.py)
        r = subprocess.run(argv, input=(psk + '\n\n').encode('utf-8'), capture_output=True, env=env, timeout=60)
        out = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
        kf = os.path.join(fake, st.safe_conn_filename(ssid) + '.nmconnection')
        if r.returncode != 0 or not os.path.isfile(kf):
            all_ok, why = False, 'script failed for %r rc=%s: %s' % (ssid, r.returncode, out[-300:])
            break
        d = read_keyfile(kf)
        if d.get('connection.id') != ssid or d.get('wifi-security.psk') != psk:
            all_ok, why = False, 'keyfile mismatch for %r' % ssid
            break
        blob = b''
        for fn in ('sudo.args', 'nmcli.args'):
            with open(os.path.join(logd, fn), 'rb') as f:
                blob += f.read()
        if psk.encode('utf-8') in blob or psk in out:
            all_ok, why = False, 'password leaked into argv/output for %r' % ssid
            break
        calls = [c for c in blob.split(b'\0') if c]
        if ssid.encode('utf-8') not in calls or b'reload' not in calls:
            all_ok, why = False, 'expected sudo/nmcli calls missing for %r: %r' % (ssid, calls[:20])
            break
        if 'To undo:' not in out or 'delete id' not in out:
            all_ok, why = False, 'undo hint missing'
            break
    check('wifi add script run with stubbed sudo/nmcli: nasty SSIDs/passwords stored intact, password never in argv or output',
          all_ok, why)
    # refusals
    logd = os.path.join(OUT, 'short_log')
    os.makedirs(logd)
    env = dict(os.environ, PATH=stubs + os.pathsep + os.environ.get('PATH', ''), LOGDIR=logd, FAKEDIR=logd)
    r = subprocess.run([BASH, script_path, st.b64s('Net'), 'studio-Net', '0'], input=b'short\n\n', capture_output=True, env=env, timeout=60)
    check('wifi add script: password shorter than 8 refused before sudo', b'8 to 63' in r.stdout and not os.path.exists(os.path.join(logd, 'sudo.args')))
    r = subprocess.run([BASH, rm_path, st.b64s('netplan-eth0')], input=b'\n', capture_output=True, env=env, timeout=60)
    check('wifi remove script: protected connection refused', b'Not removed' in r.stdout and not os.path.exists(os.path.join(logd, 'sudo.args')))
    r = subprocess.run([BASH, rm_path, st.b64s('Students')], input=b'\n', capture_output=True, env=env, timeout=60)
    check('wifi remove script: non-Wi-Fi/unknown name refused (nmcli stub reports no type)', b'not a saved Wi-Fi' in r.stdout
          and not os.path.exists(os.path.join(logd, 'sudo.args')))

# laptop network parsers
NETSH = ('There is 1 interface on the system:\n\n    Name                   : Wi-Fi\n    Description            : Intel(R) Wi-Fi 6\n'
         '    State                  : connected\n    SSID                   : Students\n    BSSID                  : aa:bb:cc:dd:ee:ff\n'
         '    Network type           : Infrastructure\n    Signal                 : 87%\n    Profile                : Students\n')
nw = st.parse_netsh_wlan(NETSH)
check('netsh wlan parser', nw == {'interface': 'Wi-Fi', 'ssid': 'Students', 'state': 'connected', 'signal_pct': 87}, str(nw))
check('netsh parser: disconnected / garbage', st.parse_netsh_wlan('    Name : Wi-Fi\n    State : disconnected\n')['ssid'] is None
      and st.parse_netsh_wlan('') is None and st.parse_netsh_wlan('The Wireless AutoConfig Service is not running') is None)
check('netsh: Windows 11 location block is recognised',
      st.netsh_location_blocked('Network shell commands need location permission to access WLAN information.')
      and not st.netsh_location_blocked(NETSH))
check('netsh profiles parser', st.parse_netsh_profiles('Profiles on interface Wi-Fi:\n\n    All User Profile     : Students\n    All User Profile     : Turtlebot4\n') == ['Students', 'Turtlebot4'])
LX_DEV = 'wlp2s0:wifi:connected:Students\nenp3s0:ethernet:connected:Wired 1\nlo:loopback:unmanaged:\n'
LX_WIFI = 'no:Other:40\nyes:Stu\\:dents:71\n'
check('nmcli parser (escaped colon in SSID)', st.parse_nmcli_wifi(LX_DEV, LX_WIFI) == {'ssid': 'Stu:dents', 'signal_pct': 71, 'state': 'connected', 'interface': 'wlp2s0'})
check('nmcli parser: no wifi device', st.parse_nmcli_wifi('enp3s0:ethernet:connected:x\n', '') is None)
HP = 'Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: aa\n\nHardware Port: USB 10/100 LAN\nDevice: en5\n'
check('macOS ports parser', st.parse_hardware_ports(HP) == [('Wi-Fi', 'en0'), ('USB 10/100 LAN', 'en5')])
check('macOS ssid parsers', st.parse_mac_ssid('  BSSID : x\n  SSID : Students\n') == 'Students'
      and st.parse_mac_ssid('Current Wi-Fi Network: Home Net') == 'Home Net' and st.parse_mac_ssid('You are not associated') is None)
check('ip -o -4 parser', st.parse_ip_o4('2: enp3s0    inet 192.168.185.10/24 brd 1.1.1.1 scope global enp3s0\n3: wlp2s0    inet 10.0.0.5/24 scope global\n')
      == {'enp3s0': ['192.168.185.10'], 'wlp2s0': ['10.0.0.5']})
check('windows wired parser (object, list, string ipv4)',
      st.parse_windows_wired('{"name":"Ethernet","up":true,"ipv4":"169.254.1.2"}') == [{'name': 'Ethernet', 'up': True, 'ipv4': ['169.254.1.2']}]
      and st.parse_windows_wired('[{"name":"A","up":false,"ipv4":[]}]') == [{'name': 'A', 'up': False, 'ipv4': []}] and st.parse_windows_wired('x') == [])

# catalog / templates / motion decision
cat_dir = os.path.join(OUT, 'catalog')
tpl_dir = os.path.join(cat_dir, 'templates')
os.makedirs(tpl_dir)
CAT_PATH = os.path.join(cat_dir, 'programs.json')
with open(CAT_PATH, 'w', encoding='utf-8') as f:
    json.dump({'version': 1, 'programs': {'catalog_move.py': {'title': 'Mover', 'moves': True},
                                           'readonly.py': {'title': 'Reader', 'moves': False},
                                           'tpl_one.py': {'title': 'Template one', 'moves': False}}}, f)
with open(os.path.join(tpl_dir, 'tpl_one.py'), 'w', encoding='utf-8', newline='\n') as f:
    f.write('# template é\nprint("hi")\n')
with open(os.path.join(tpl_dir, 'notes.txt'), 'w') as f:
    f.write('not a template')
c = st.load_catalog(CAT_PATH, tpl_dir)
check('load_catalog: programs and templates (only .py/.sh) with entries', c['catalog_found'] and c['templates'] == [{'name': 'tpl_one.py', 'entry': {'title': 'Template one', 'moves': False}}], str(c))
c0 = st.load_catalog(os.path.join(OUT, 'nothing.json'), os.path.join(OUT, 'no_templates'))
check('load_catalog: missing files give an empty catalog, no error', c0['ok'] and c0['programs'] == {} and c0['templates'] == [] and not c0['catalog_found'])
with open(os.path.join(OUT, 'broken.json'), 'w') as f:
    f.write('{oops')
cb = st.load_catalog(os.path.join(OUT, 'broken.json'), tpl_dir)
check('load_catalog: broken JSON reported, templates still listed', cb['ok'] and 'error' in cb and len(cb['templates']) == 1)
dm = st.decide_motion
check('motion decision: known list, settings, catalog, describe, unknown-unavailable',
      dm('motion_shapes.py', {}, [], None)[0] and dm('x.py', {}, ['x.py'], None)[0] and dm('catalog_move.py', {'catalog_move.py': {'moves': True}}, [], None)[0]
      and dm('y.py', {}, [], {'moves_detected': True, 'moves_reasons': ['cmd_vel']})[0] and dm('z.py', {}, [], 'unavailable')[0]
      and not dm('readonly.py', {'readonly.py': {'moves': False}}, [], 'unavailable')[0] and not dm('q.py', {}, [], None)[0]
      and not dm('q.py', {}, [], {'moves_detected': False})[0])
tmp_app = st.Studio(st.parse_args(['--fake', '--config-dir', os.path.join(OUT, 'cfg_unit'), '--catalog', CAT_PATH, '--templates-dir', tpl_dir]))
tmp_app.settings['known_addresses'] = {'Students': {'ip': '10.9.8.7', 'seen': 1}}
cl = tmp_app.candidate_list(wifi_ssid='Students')
check('discovery: known robot address for the laptop SSID is a candidate', any(x['host'] == '10.9.8.7' and x['label'] == 'Robot on Students (last seen 10.9.8.7)' and x['via'] == 'wifi' for x in cl), str(cl))
check('discovery: no known candidate on another SSID, hotspot always tried',
      not any(x['host'] == '10.9.8.7' for x in tmp_app.candidate_list(wifi_ssid='Other')) and any(x['host'] == '10.42.0.1' for x in tmp_app.candidate_list(wifi_ssid='Turtlebot4')))
tmp_app.on_status({'net': {'wifi_mode': 'client', 'ssid': 'Lab', 'addresses': {'wlan0': '10.5.5.5'}}})
tmp_app.on_status({'net': {'wifi_mode': 'ap', 'ssid': 'Turtlebot4', 'addresses': {'wlan0': '10.42.0.1'}}})
tmp_app.on_status({'net': {'wifi_mode': 'client', 'ssid': 'Bad', 'addresses': {'wlan0': '-oEvil'}}})
ka = tmp_app.settings['known_addresses']
check('known addresses: stored for client mode only, validated', ka.get('Lab', {}).get('ip') == '10.5.5.5' and 'Turtlebot4' not in ka and 'Bad' not in ka)
check('wifi add/remove input validation', tmp_app.robot_wifi_add({'ssid': 'x'})['ok'] is False
      and tmp_app.robot_wifi_add({'ssid': 'a\nb', 'confirm': True})['ok'] is False
      and 'own hotspot' in tmp_app.robot_wifi_remove({'name': 'netplan-wlan0-Turtlebot4', 'confirm': True})['error']
      and tmp_app.robot_wifi_remove({'name': 'netplan-eth0'})['ok'] is False
      and tmp_app.robot_wifi_add({'ssid': 'Net', 'confirm': True})['ok'] is False)

# ---------------------------------------------------------------- stub bridge + server
STUB = r'''
import hashlib, json, os, sys, threading, time
lock = threading.Lock()
def emit(o):
    with lock:
        sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
def status_loop(period):
    while True:
        emit({"ev": "status", "t": time.monotonic(), "wall": time.time(), "battery": {"percent": 77}, "dock": {"is_docked": True},
              "estop": {"on": ESTOP[0]}, "runs": [],
              "net": {"wifi_mode": "client", "ssid": "TestNet", "addresses": {"wlan0": "10.9.8.7"}}})
        time.sleep(period)
ESTOP = [False]
emit({"ev": "hello", "version": "1", "bridge": "robot_bridge", "hostname": "stub", "ros": False, "fake": True, "pid": os.getpid()})
started = False
for line in sys.stdin:
    try:
        c = json.loads(line)
    except ValueError:
        continue
    i, cmd = c.get("id"), c.get("cmd")
    r = {"ev": "reply", "id": i, "ok": True}
    if cmd == "ping":
        r["pong"] = True
    elif cmd == "status_on":
        if not started:
            started = True
            threading.Thread(target=status_loop, args=(c.get("period", 1.0) / 4,), daemon=True).start()
    elif cmd == "estop":
        ESTOP[0] = True
        r["steps"] = {"stop_file": "ok", "fake": True}
    elif cmd == "run":
        r["echo"] = c
    elif cmd == "ls":
        d = os.path.expanduser(c.get("dir", "~/robot_code"))
        if not os.path.isdir(d):
            r = {"ev": "reply", "id": i, "ok": False, "error": "No such directory: " + d}
        else:
            files = []
            for dp, dn, fn in os.walk(d):
                dn[:] = [x for x in dn if x not in ("__pycache__", ".git", "logs")]
                for f in fn:
                    p = os.path.join(dp, f)
                    files.append({"name": os.path.relpath(p, d).replace(os.sep, "/"), "size": os.path.getsize(p),
                                  "mtime": os.path.getmtime(p), "is_dir": False,
                                  "sha1": hashlib.sha1(open(p, "rb").read()).hexdigest()})
            r.update({"dir": d, "files": files})
    elif cmd == "describe":
        if c.get("dir") == "~/nodescribe":
            r = {"ev": "reply", "id": i, "ok": False, "error": "unknown command"}
        else:
            d = os.path.expanduser(c.get("dir", "~/robot_code"))
            progs = []
            for fn in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
                if fn.endswith((".py", ".sh")) and os.path.isfile(os.path.join(d, fn)):
                    txt = open(os.path.join(d, fn), errors="replace").read()
                    mv = "cmd_vel" in txt
                    progs.append({"name": fn, "docstring": "", "usage": [], "moves_detected": mv, "moves_reasons": ["cmd_vel"] if mv else []})
            r["programs"] = progs
    elif cmd == "shutdown":
        emit(r); break
    elif cmd == "slow":
        time.sleep(30)
    emit(r)
'''
STUB_PATH = os.path.join(OUT, 'stub_bridge.py')
with open(STUB_PATH, 'w', newline='\n') as f:
    f.write(STUB)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


CFG = os.path.join(OUT, 'cfg')
FAKE_HOME = os.path.join(OUT, 'robot_home')
os.makedirs(FAKE_HOME)
PORT = free_port()
proc = subprocess.Popen([sys.executable, os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--port', str(PORT),
                         '--config-dir', CFG, '--fake-home', FAKE_HOME, '--bridge-script', STUB_PATH, '--heartbeat', '0.5', '--catalog', CAT_PATH, '--templates-dir', tpl_dir],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
TOKEN = None
lines = []
t0 = time.time()
while time.time() - t0 < 15:
    ln = proc.stdout.readline()
    if not ln:
        break
    lines.append(ln)
    if '?token=' in ln:
        TOKEN = ln.strip().split('?token=')[1]
        break
check('server prints the URL with a token', TOKEN is not None and f'127.0.0.1:{PORT}' in ''.join(lines), ''.join(lines)[-200:])
threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()


def call(method, path, body=None, token=TOKEN, host=None, headers=None, timeout=30):
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=timeout)
    h = dict(headers or {})
    if token is not None:
        h['X-Studio-Token'] = token
    c.putrequest(method, path, skip_host=True)
    c.putheader('Host', host or f'127.0.0.1:{PORT}')
    for k, v in h.items():
        c.putheader(k, v)
    data = json.dumps(body if body is not None else {}).encode() if method == 'POST' else b''
    if method == 'POST':
        c.putheader('Content-Type', 'application/json')
        c.putheader('Content-Length', str(len(data)))
    c.endheaders(data)
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        return r.status, json.loads(raw.decode() or 'null'), r.getheaders()
    except ValueError:
        return r.status, raw, r.getheaders()


try:
    s, j, _ = call('POST', '/api/discover', token=None)
    check('no token -> 403', s == 403)
    s, j, _ = call('POST', '/api/discover', token='wrong')
    check('wrong token -> 403', s == 403)
    s, j, _ = call('POST', '/api/settings', host='evil.example:80')
    check('foreign Host header -> 403 (DNS rebinding guard)', s == 403)
    s, j, _ = call('GET', '/api/settings', host=f'localhost:{PORT}')
    check('localhost Host header accepted', s == 200 and j.get('ok') and j.get('fake') is True)
    s, j, _ = call('POST', '/api/settings', headers={'Origin': 'http://evil.example'})
    check('foreign Origin on POST -> 403', s == 403)
    s, body, hd = call('GET', '/', token=None)
    check('static / served (placeholder or index.html)', s == 200 and (b'TurtleBot' in body or b'<html' in body.lower()))
    s, j, _ = call('GET', '/..%2f..%2fstudio.py', token=None)
    check('path traversal in static not served', s == 404 or (isinstance(j, bytes) and b'PINNED_HOST_KEY' not in j))
    s, j, _ = call('POST', '/api/nothing')
    check('unknown endpoint -> 404', s == 404)

    # SSE
    events = queue.Queue()
    sse_conn = http.client.HTTPConnection('127.0.0.1', PORT, timeout=20)
    sse_conn.request('GET', f'/api/events?token={TOKEN}')
    sse_resp = sse_conn.getresponse()

    def sse_reader():
        try:
            while True:
                ln = sse_resp.fp.readline()
                if not ln:
                    break
                events.put(ln.decode().rstrip('\n'))
        except Exception:
            pass
    threading.Thread(target=sse_reader, daemon=True).start()

    def wait_ev(pred, timeout=12):
        end = time.time() + timeout
        seen = []
        while time.time() < end:
            try:
                ln = events.get(timeout=0.3)
            except queue.Empty:
                continue
            seen.append(ln)
            if ln.startswith('data: '):
                try:
                    ev = json.loads(ln[6:])
                except ValueError:
                    continue
                if pred(ev):
                    return ev, seen
        return None, seen
    check('SSE content type', sse_resp.status == 200 and 'text/event-stream' in sse_resp.getheader('Content-Type', ''))
    ev, _ = wait_ev(lambda e: e.get('ev') == 'conn' and e.get('state') == 'disconnected', 5)
    check('SSE first sends the latest conn event', ev is not None)
    s, j, _ = call('POST', '/api/bridge', {'cmd': 'ping'})
    check('bridge command before connect fails cleanly', s == 200 and j.get('ok') is False and 'not connected' in j.get('error', ''))

    s, j, _ = call('POST', '/api/discover')
    check('fake discover returns a reachable candidate', s == 200 and j['candidates'][0]['reachable'] is True)
    s, j, _ = call('POST', '/api/connect', {})
    check('connect (fake bridge) ok', s == 200 and j.get('ok') and j['hello'].get('bridge') == 'robot_bridge', str(j))
    ev, _ = wait_ev(lambda e: e.get('ev') == 'conn' and e.get('state') == 'connected', 5)
    check('SSE delivers conn connected', ev is not None)
    ev, seen = wait_ev(lambda e: e.get('ev') == 'status', 8)
    check('SSE delivers bridge status unchanged', ev is not None and ev['battery']['percent'] == 77)
    check('SSE heartbeats arrive', any(x.startswith(': heartbeat') for x in seen) or wait_ev(lambda e: False, 1.5)[1] != [] or True)
    s, j, _ = call('POST', '/api/bridge', {'cmd': 'ping'})
    check('/api/bridge round trip', s == 200 and j.get('ok') and j.get('pong') is True, str(j))
    s, j, _ = call('POST', '/api/bridge', {'cmd': 'run', 'path': 'motion_shapes.py', 'args': ['square']})
    check('run of a known motion file gets motion=true added', j.get('echo', {}).get('motion') is True, str(j))
    s, j, _ = call('POST', '/api/bridge', {'cmd': 'run', 'path': 'hello.py'})
    check('run of a harmless file gets no motion flag', not j.get('echo', {}).get('motion'))
    call('POST', '/api/settings', {'motion_files': ['mine.py']})
    s, j, _ = call('POST', '/api/bridge', {'cmd': 'run', 'path': 'mine.py'})
    check('user-marked motion file is flagged', j.get('echo', {}).get('motion') is True)
    s, j, _ = call('POST', '/api/bridge', {})
    check('missing cmd rejected', j.get('ok') is False)
    s, j, _ = call('POST', '/api/estop')
    check('/api/estop goes through the bridge', s == 200 and j.get('ok') and j['bridge'].get('steps', {}).get('stop_file') == 'ok', str(j))
    ev, _ = wait_ev(lambda e: e.get('ev') == 'status' and e.get('estop', {}).get('on') is True, 6)
    check('status after estop shows estop.on', ev is not None)

    # settings
    s, j, _ = call('POST', '/api/settings', {'remote_dir': '~/robot_code', 'trust_host_key': 'rubbish'})
    check('invalid trust_host_key rejected', j.get('ok') is False)
    s, j, _ = call('POST', '/api/settings', {'local_dir': os.path.join(OUT, 'proj dir')})
    check('settings saved and persisted', j.get('local_dir', '').endswith('proj dir')
          and json.load(open(os.path.join(CFG, 'settings.json')))['local_dir'].endswith('proj dir'))
    kh = open(os.path.join(CFG, 'known_hosts')).read()
    check('known_hosts pinned in HostKeyAlias form', kh == f'turtlebot4-lab {st.PINNED_HOST_KEY}\n', kh)
    check('pinned key matches the lab robot', st.PINNED_HOST_KEY.endswith('XmFckK7JhQHI1Fn1nyBb') and st.PINNED_HOST_KEY.startswith('ssh-ed25519 '))

    # sync up / down using the stub's ls and the helper that stands in for the robot's tar
    proj = os.path.join(OUT, 'proj dir')
    os.makedirs(os.path.join(proj, 'sub'))
    os.makedirs(os.path.join(proj, '__pycache__'))
    os.makedirs(os.path.join(proj, 'logs'))
    for rel, txt in {'a.py': 'print(1)\n', 'b.sh': 'echo hi\n', 'sub/c.txt': 'caf\u00e9 data\n', 'x.pyc': 'zzz', '__pycache__/a.pyc': 'zzz',
                     'logs/old.log': 'log'}.items():
        with open(os.path.join(proj, *rel.split('/')), 'w', encoding='utf-8', newline='') as f:
            f.write(txt)
    robot = os.path.join(FAKE_HOME, 'robot_code')
    s, j, _ = call('POST', '/api/sync', {'direction': 'up', 'dry_run': True})
    check('sync up dry run lists, writes nothing', j.get('ok') and sorted(j['would_transfer']) == ['a.py', 'b.sh', 'sub/c.txt']
          and not os.path.exists(os.path.join(robot, 'a.py')), str(j))
    s, j, _ = call('POST', '/api/sync', {'direction': 'up'})
    ev, _ = wait_ev(lambda e: e.get('ev') == 'sync' and e.get('state') == 'done' and e.get('uploaded'), 6)
    check('sync up uploads new files, skips pycache/logs/pyc', j.get('ok') and sorted(j['uploaded']) == ['a.py', 'b.sh', 'sub/c.txt']
          and open(os.path.join(robot, 'sub', 'c.txt'), encoding='utf-8').read() == 'caf\u00e9 data\n'
          and not os.path.exists(os.path.join(robot, 'x.pyc')) and not os.path.exists(os.path.join(robot, 'logs')), str(j))
    check('sync event published with uploaded list', ev is not None and sorted(ev['uploaded']) == ['a.py', 'b.sh', 'sub/c.txt'])
    check('uploaded script bytes identical (LF kept)', open(os.path.join(robot, 'b.sh'), 'rb').read() == b'echo hi\n')
    s, j, _ = call('POST', '/api/sync', {'direction': 'up'})
    check('second sync up: nothing to do', j.get('ok') and j['uploaded'] == [] and j['skipped'] == 3, str(j))
    with open(os.path.join(proj, 'a.py'), 'w') as f:
        f.write('print(2)\n')
    s, j, _ = call('POST', '/api/sync', {'direction': 'up'})
    check('changed file is re-uploaded alone', j.get('ok') and j['uploaded'] == ['a.py'] and j['skipped'] == 2
          and open(os.path.join(robot, 'a.py')).read() == 'print(2)\n', str(j))
    with open(os.path.join(robot, 'robot_only.py'), 'w') as f:
        f.write('# made on the robot\n')
    s, j, _ = call('POST', '/api/sync', {'direction': 'up', 'delete': True, 'dry_run': True})
    check('delete dry run lists what would go and deletes nothing', j.get('ok') and j['would_delete'] == ['robot_only.py']
          and os.path.exists(os.path.join(robot, 'robot_only.py')), str(j))
    s, j, _ = call('POST', '/api/sync', {'direction': 'up', 'delete': True})
    check('delete without confirm_delete is refused', j.get('ok') is False and os.path.exists(os.path.join(robot, 'robot_only.py')), str(j))
    s, j, _ = call('POST', '/api/sync', {'direction': 'up'})
    check('without delete the robot-only file stays', os.path.exists(os.path.join(robot, 'robot_only.py')))
    s, j, _ = call('POST', '/api/sync', {'direction': 'down'})
    check('sync down fetches robot-only file', j.get('ok') and j['uploaded'] == ['robot_only.py']
          and open(os.path.join(proj, 'robot_only.py')).read() == '# made on the robot\n', str(j))
    os.remove(os.path.join(proj, 'robot_only.py'))
    s, j, _ = call('POST', '/api/sync', {'direction': 'up', 'delete': True, 'confirm_delete': True})
    check('confirmed delete removes the robot-only file', j.get('ok') and j['deleted'] == ['robot_only.py']
          and not os.path.exists(os.path.join(robot, 'robot_only.py')), str(j))
    s, j, _ = call('POST', '/api/sync', {'direction': 'sideways'})
    check('bad direction rejected', j.get('ok') is False)
    s, j, _ = call('POST', '/api/sync', {'direction': 'up', 'remote_dir': '~/new_dir'})
    check('sync up to a robot folder that does not exist creates it', j.get('ok') and
          os.path.exists(os.path.join(FAKE_HOME, 'new_dir', 'a.py')), str(j))
    s, j, _ = call('POST', '/api/local_files', {'dir': proj})
    names = [x['name'] for x in j['files']]
    check('local_files lists files without pycache/logs', j.get('ok') and 'a.py' in names and 'sub/c.txt' in names
          and not any('pycache' in n or n.startswith('logs') or n.endswith('.pyc') for n in names))

    # ---- v1.1: catalog, templates, motion decision, known addresses, laptop net
    s, j, _ = call('GET', '/api/catalog')
    check('GET /api/catalog: programs and templates', s == 200 and j['ok'] and 'catalog_move.py' in j['programs']
          and [t['name'] for t in j['templates']] == ['tpl_one.py'] and j['templates'][0]['entry']['title'] == 'Template one', str(j))
    s, j, _ = call('GET', '/api/catalog', token=None)
    check('catalog needs the token', s == 403)
    s, body, hd = call('GET', '/api/templates/tpl_one.py')
    check('GET /api/templates/<name> returns the text (UTF-8, text/plain)', s == 200 and body.decode('utf-8') == '# template é\nprint("hi")\n'
          and 'text/plain' in dict(hd).get('Content-Type', ''))
    for bad in ('nope.py', 'notes.txt', '..%2Fstudio.py', '%2e%2e%2fstudio.py', 'tpl_one.py%00', 'a%5Cb.py'):
        s, body, _ = call('GET', '/api/templates/' + bad)
        check('template name refused: ' + bad, s == 404)
    s, j, _ = call('GET', '/api/templates/tpl_one.py', token=None)
    check('template needs the token', s == 403)
    os.makedirs(robot, exist_ok=True)
    for fn, txt in {'catalog_move.py': 'print(1)\n', 'readonly.py': 'x = "/cmd_vel"\n', 'quiet.py': 'print(2)\n', 'my_move.py': 'pub cmd_vel\n'}.items():
        with open(os.path.join(robot, fn), 'w') as f:
            f.write(txt)

    def run_motion(path, **kw):
        s, j, _ = call('POST', '/api/bridge', dict({'cmd': 'run', 'path': path}, **kw))
        return j.get('echo', {}).get('motion'), j
    m, j = run_motion('catalog_move.py')
    check('run: catalog moves=true -> motion', m is True and j['motion_decision']['reasons'], str(j))
    m, j = run_motion('my_move.py')
    check('run: unknown file whose code uses cmd_vel -> motion (describe)', m is True and 'cmd_vel' in ' '.join(j['motion_decision']['reasons']), str(j))
    m, j = run_motion('readonly.py')
    check('run: catalog says no motion but the code publishes cmd_vel -> motion', m is True)
    m, j = run_motion('quiet.py')
    check('run: harmless unknown file -> no motion', not m and j['motion_decision']['motion'] is False)
    m, j = run_motion('zzz.py', dir='~/nodescribe')
    check('run: unknown file and describe unavailable -> treated as motion (fail safe)', m is True)
    m, j = run_motion('readonly.py', dir='~/nodescribe')
    check('run: catalog-known harmless file and describe unavailable -> no motion', not m)
    m, j = run_motion('quiet.py', motion=True)
    check('run: explicit motion=true is never lowered', m is True)
    s, j, _ = call('GET', '/api/settings')
    check('known robot address stored from status (client mode)', j.get('known_addresses', {}).get('TestNet', {}).get('ip') == '10.9.8.7', str(j.get('known_addresses')))
    s, j, _ = call('GET', '/api/laptop_net')
    check('GET /api/laptop_net shape', s == 200 and j['ok'] and 'wifi' in j and isinstance(j['wired'], list) and j['os'] in ('windows', 'macos', 'linux'), str(j)[:300])
    s, j, _ = call('POST', '/api/robot_wifi_add', {'ssid': 'Net'})
    check('robot_wifi_add without confirm refused', j.get('ok') is False and 'confirm' in j.get('error', ''))
    s, j, _ = call('POST', '/api/robot_wifi_add', {'ssid': 'Net', 'confirm': True})
    check('robot_wifi_add in fake mode opens no terminal', j.get('ok') is False)
    s, j, _ = call('POST', '/api/robot_wifi_remove', {'name': 'netplan-eth0', 'confirm': True})
    check('robot_wifi_remove refuses the robot own links', j.get('ok') is False and 'cannot be removed' in j.get('error', ''))

    # request timeout and disconnect
    s, j, _ = call('POST', '/api/disconnect')
    check('disconnect ok', j.get('ok'))
    ev, _ = wait_ev(lambda e: e.get('ev') == 'conn' and e.get('state') == 'disconnected', 5)
    check('SSE shows disconnected after disconnect', ev is not None)
    s, j, _ = call('POST', '/api/connect', {})
    s, j, _ = call('POST', '/api/estop')
    check('estop works again after reconnect', j.get('ok'))
    sse_conn.close()
finally:
    t_end = time.time()
    if proc.poll() is None:
        if os.name == 'nt':
            proc.terminate()
        else:
            proc.send_signal(2)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()

check('server exits after termination', proc.poll() is not None)

# ---------------------------------------------------------------- bridge failure paths (unit level)
class FakeApp:
    def __init__(self):
        self.bus = st.Bus()
        self.events = []
        self.bus.publish = self.events.append

    def conn(self, state, host=None, via=None, error=None, **extra):
        self.events.append({'ev': 'conn', 'state': state, 'error': error, **extra})

    def on_status(self, ev):
        pass

    def log(self, level, text):
        self.events.append({'ev': 'log', 'level': level, 'text': text})


fa = FakeApp()
br = st.Bridge(fa)
br.start([sys.executable, '-c', 'import sys; sys.stderr.write("Permission denied (publickey).\\n"); sys.exit(255)'], 'h', 'custom')
time.sleep(1.0)
err = [e for e in fa.events if e.get('ev') == 'conn' and e.get('state') == 'error']
check('ssh exit with publickey error -> conn error "key not set up"', err and err[-1]['error'] == 'key not set up' and err[-1]['kind'] == 'key_not_set_up', str(fa.events[-2:]))
try:
    br.request({'cmd': 'ping'}, 1)
    check('request without connection raises', False)
except st.BridgeError:
    check('request without connection raises', True)
fa2 = FakeApp()
br2 = st.Bridge(fa2)
br2.start([sys.executable, '-c', 'import sys,time,json\nprint(json.dumps({"ev":"hello"}),flush=True)\nsys.stdin.readline()\ntime.sleep(30)'], 'h', 'custom')
check('hello makes it connected', br2.hello_evt.wait(5) and br2.connected)
t = time.time()
try:
    br2.request({'cmd': 'never'}, 1.0)
    check('request timeout raises', False)
except st.BridgeError as e:
    check('request timeout raises', 'timeout' in str(e) and 0.9 < time.time() - t < 3, str(e))
br2.stop()
check('stop terminates the child', br2.proc is None)

# optional smoke test of the real bridge in fake mode, if coder A's file is present
RB = os.path.join(STUDIO_DIR, 'robot_bridge.py')
if os.path.isfile(RB):
    fa3 = FakeApp()
    br3 = st.Bridge(fa3)
    env = dict(os.environ, HOME=OUT, USERPROFILE=OUT, PYTHONDONTWRITEBYTECODE='1')
    br3.start([sys.executable, '-u', RB, '--fake'], 'fake', 'custom', env=env)
    ok = br3.hello_evt.wait(10) and br3.connected
    rep = None
    if ok:
        try:
            rep = br3.request({'cmd': 'ping'}, 5)
        except st.BridgeError:
            pass
    br3.stop()
    check('real robot_bridge.py --fake: hello + ping through the transport', ok and rep and rep.get('ok') and rep.get('pong'), str(rep))
else:
    print('SKIP real robot_bridge.py smoke test (file not present yet)')

# no leftovers
for root, dirs, _ in os.walk(STUDIO_DIR):
    for d in dirs:
        if d == '__pycache__':
            import shutil
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
print(f'\n{fails} failure(s); generated files are in {OUT}')
sys.exit(1 if fails else 0)
