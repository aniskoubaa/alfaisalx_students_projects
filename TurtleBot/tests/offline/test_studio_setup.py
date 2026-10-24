"""Offline tests of TurtleBot Studio 1.2: settings, first-run wizard backend, join-any-Wi-Fi (S-b, S-c, S-d) and the
frozen-exe hooks (S-a) in TurtleBot/tools/studio/studio.py and robot_bridge.py.

No robot, no network. The HTTP part starts the real studio.py --fake with the real robot_bridge.py --fake. bash tests
(script syntax, the root join job with stub nmcli/ip) skip cleanly when bash is missing; the unix-socket handoff test
runs only on Linux (a loopback stand-in for the socket runs everywhere).
Usage: python test_studio_setup.py
"""
import base64
import http.client
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
import robot_bridge as rb  # noqa: E402
import studio as st  # noqa: E402

OUT = tempfile.mkdtemp(prefix='tb4_studio_setup_')
fails = 0


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode())
    if not cond:
        fails += 1


def skip(name, why):
    print(f'SKIP {name}  [{why}]')


def fwd(p):
    return p.replace('\\', '/')


def new_app(name, settings=None, extra=()):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    if settings is not None:
        with open(os.path.join(d, 'settings.json'), 'w', encoding='utf-8') as f:
            json.dump(settings, f)
    return st.Studio(st.parse_args(['--fake', '--config-dir', d, '--fake-home', os.path.join(d, 'home'), *extra])), d


LAB = st.LAB_HOST_KEY
OTHER = st.FAKE_HOST_KEY

# ---------------------------------------------------------------- S-d: settings
app, d1 = new_app('fresh')
S = app.settings
check('defaults: lab values and wizard still to do', S['robot_hostname'] == 'turtlebot4' and S['robot_user'] == 'ubuntu'
      and S['hotspot_ssid'] == 'Turtlebot4' and S['hotspot_addr'] == '10.42.0.1' and S['cable_addr'] == '192.168.185.3'
      and S['builtin_host_key'] is True and S['trusted_host_keys'] == [] and S['setup_done'] is False)
check('PINNED_HOST_KEY still importable and equal to LAB_HOST_KEY', st.PINNED_HOST_KEY == st.LAB_HOST_KEY and st.PINNED_HOST_KEY.startswith('ssh-ed25519 '))
with open(app.known_hosts, encoding='utf-8') as f:
    check('fresh known_hosts: the built-in key only, under the unchanged alias', f.read() == 'turtlebot4-lab %s\n' % LAB)
gs = app.get_settings()
check('GET settings: defaults, lab_host_key, trusted list with fingerprints', gs['defaults'] == st.DEFAULT_SETTINGS and gs['lab_host_key'] == LAB
      and gs['pinned_host_key'] == LAB and gs['trusted'][0]['builtin'] is True and gs['trusted'][0]['enabled'] is True
      and gs['trusted'][0]['fingerprint'].startswith('SHA256:') and gs['version'] == st.VERSION, str(gs['trusted']))

app2, d2 = new_app('existing', {'last_host': '10.1.2.3', 'last_via': 'wifi', 'trust_host_key': OTHER})
check('existing user (last_host set): wizard skipped', app2.settings['setup_done'] is True)
check('old trust_host_key migrated into trusted_host_keys, one-slot cleared',
      app2.settings['trust_host_key'] is None and [e['key'] for e in app2.settings['trusted_host_keys']] == [OTHER], str(app2.settings['trusted_host_keys']))
with open(app2.known_hosts, encoding='utf-8') as f:
    kh = f.read().splitlines()
check('known_hosts: built-in + migrated key, one line each, same alias', kh == ['turtlebot4-lab ' + LAB, 'turtlebot4-lab ' + OTHER], str(kh))
app3, d3 = new_app('explicit_done', {'last_host': '10.1.2.3', 'setup_done': False})
check('explicit setup_done in the file wins over the last_host rule', app3.settings['setup_done'] is False)

r = app2.post_settings({'builtin_host_key': False})
with open(app2.known_hosts, encoding='utf-8') as f:
    kh = f.read().splitlines()
check('built-in key switched off: only the trusted key stays in known_hosts', r['ok'] and kh == ['turtlebot4-lab ' + OTHER], str(kh))
r = app2.post_settings({'builtin_host_key': True, 'trust_host_key': ''})
check('legacy POST trust_host_key "" removes the imported key', r['ok'] and app2.settings['trusted_host_keys'] == [])
r = app2.post_settings({'trust_host_key': OTHER})
check('legacy POST trust_host_key still accepted (becomes a list entry)', r['ok'] and app2.settings['trusted_host_keys'][0]['key'] == OTHER
      and app2.settings['trust_host_key'] is None)
bad = [{'robot_hostname': 'a b'}, {'robot_hostname': '-x'}, {'robot_hostname': 'x' * 64}, {'robot_hostname': 'é'}, {'robot_user': 'Root'},
       {'robot_user': '1abc'}, {'robot_user': 'a b'}, {'hotspot_ssid': 'x' * 33}, {'hotspot_ssid': 'a\nb'}, {'hotspot_addr': '-oProxyCommand=x'},
       {'hotspot_addr': 'a b'}, {'cable_addr': 'u@host'}, {'cable_addr': 5}, {'builtin_host_key': 'yes'}, {'setup_done': 1}, {'trust_host_key': 'junk'}]
check('settings validation rejects bad values', all(app2.post_settings(b).get('ok') is False for b in bad),
      str([b for b in bad if app2.post_settings(b).get('ok') is not False]))
good = {'robot_hostname': 'tb4-lab-2', 'robot_user': 'pi', 'hotspot_ssid': 'RobotNet', 'hotspot_addr': '192.168.77.1',
        'cable_addr': 'fe80::1%eth0', 'setup_done': True}
r = app2.post_settings(good)
check('settings accept valid values and persist them', r['ok'] and all(r[k] == v for k, v in good.items()))
with open(os.path.join(d2, 'settings.json'), encoding='utf-8') as f:
    saved = json.load(f)
check('settings.json holds the new keys', all(saved[k] == v for k, v in good.items()) and 'trusted_host_keys' in saved)
r = app2.post_settings({'robot_hostname': ''})
check('empty value resets to the default', r['ok'] and r['robot_hostname'] == 'turtlebot4')
app4, _ = new_app('badfile', {'robot_user': 'Bad User', 'hotspot_addr': 'x y', 'robot_hostname': '-', 'trusted_host_keys': ['x', {'key': 'bad'}]})
check('invalid values in settings.json fall back to defaults', app4.settings['robot_user'] == 'ubuntu' and app4.settings['hotspot_addr'] == '10.42.0.1'
      and app4.settings['robot_hostname'] == 'turtlebot4' and app4.settings['trusted_host_keys'] == [])

orig_cable = st.has_cable_v4
st.has_cable_v4 = lambda: True
app2.post_settings({'hotspot_addr': '192.168.77.1', 'cable_addr': '192.168.99.5', 'robot_hostname': 'bot7', 'hotspot_ssid': 'RobotNet'})
cl = app2.candidate_list()
hosts = [c['host'] for c in cl]
check('candidate_list uses hotspot_addr, cable_addr and robot_hostname from settings',
      '192.168.77.1' in hosts and '192.168.99.5' in hosts and 'bot7.local' in hosts and '10.42.0.1' not in hosts
      and 'turtlebot4.local' not in hosts and '192.168.185.3' not in hosts, str(hosts))
check('candidate labels carry the configured hotspot name', any(c['label'] == 'Robot hotspot (RobotNet Wi-Fi)' for c in cl))
st.has_cable_v4 = orig_cable
cl = app.candidate_list()
check('candidate_list defaults unchanged', [c['host'] for c in cl][:1] == ['10.42.0.1'] and 'turtlebot4.local' in [c['host'] for c in cl])

# ---------------------------------------------------------------- user= in the argv builders
KH = '/k/kh'
check('build_*_argv: default user stays ubuntu, positional signatures unchanged',
      st.build_bridge_ssh_argv('ssh', 'h', 'K', KH)[-2] == 'ubuntu@h' and st.build_ssh_argv('ssh', 'h', 'K', KH, 'x')[-2] == 'ubuntu@h'
      and st.build_scp_argv('scp', 'h', 'K', KH, 'a', '~/b')[-1] == 'ubuntu@h:~/b')
check('build_*_argv: user keyword', st.build_bridge_ssh_argv('ssh', 'h', 'K', KH, user='pi')[-2] == 'pi@h'
      and st.build_ssh_argv('ssh', 'h', 'K', KH, 'x', user='pi')[-2] == 'pi@h' and st.build_ssh_argv('ssh', 'h', 'K', KH, user='pi')[-1] == 'pi@h'
      and st.build_scp_argv('scp', 'fe80::1%8', 'K', KH, 'a', '~/b', user='pi')[-1] == 'pi@[fe80::1%8]:~/b'
      and '    User pi' in st.ssh_config_block('h', 'K', KH, user='pi').splitlines())

# ---------------------------------------------------------------- fingerprints / keyscan
fp = st.key_fingerprint(LAB)
check('fingerprint format', fp.startswith('SHA256:') and '=' not in fp and len(fp) == 7 + 43, fp)
check('fingerprint of junk is None', st.key_fingerprint('ssh-ed25519') is None and st.key_fingerprint('ssh-ed25519 !!!') is None)
KS = '# 10.0.0.5:22 SSH-2.0-OpenSSH_9.6\n10.0.0.5 ssh-ed25519 %s\n' % LAB.split()[1]
check('keyscan parser: host column and comments dropped', st.parse_keyscan(KS) == LAB and st.parse_keyscan('# only comments\n') is None
      and st.parse_keyscan('') is None and st.parse_keyscan(None) is None)
KG = st.find_exe('ssh-keygen')
if KG:
    kd = os.path.join(OUT, 'kg')
    os.makedirs(kd)
    subprocess.run([KG, '-q', '-t', 'ed25519', '-N', '', '-f', os.path.join(kd, 'k')], check=True, capture_output=True)
    pub = open(os.path.join(kd, 'k.pub'), encoding='utf-8').read().strip()
    out = subprocess.run([KG, '-lf', os.path.join(kd, 'k.pub')], capture_output=True, text=True).stdout.split()
    check('fingerprint equals ssh-keygen -lf', out[1] == st.key_fingerprint(pub), '%s vs %s' % (out[1], st.key_fingerprint(pub)))
else:
    skip('fingerprint equals ssh-keygen -lf', 'ssh-keygen not found')

# ---------------------------------------------------------------- S-a: frozen helpers
had = hasattr(sys, 'frozen')
old_frozen = getattr(sys, 'frozen', None)
try:
    sys.frozen = True
    check('frozen: self_argv is the exe itself', st.self_argv('--_fake-tar', 'x') == [sys.executable, '--_fake-tar', 'x'])
    check('frozen: fake bridge argv uses --_fake-bridge', st.fake_bridge_argv('whatever.py') == [sys.executable, '--_fake-bridge', '--fake'])
    app.bridge_script = os.path.join(OUT, 'nowhere.py')
    check('frozen: fake connect does not need robot_bridge.py on disk', st.is_frozen() and not os.path.isfile(app.bridge_script))
    check('frozen: _remote_exec_argv in fake mode goes through the exe', app._remote_exec_argv('x', ['extract', 'd'])[:2] == [sys.executable, '--_fake-tar'])
    sys.frozen = False
    sa = st.self_argv('--_fake-tar', 'x')
    check('not frozen: self_argv is python + studio.py', sa[0] == sys.executable and sa[1].endswith('studio.py') and sa[2:] == ['--_fake-tar', 'x'])
    check('not frozen: fake bridge argv runs the script', st.fake_bridge_argv('rb.py') == [sys.executable, '-u', 'rb.py', '--fake'])
finally:
    if had:
        sys.frozen = old_frozen
    else:
        del sys.frozen
check('HERE and WEB_DIR derive from the module location when not frozen', st.HERE == STUDIO_DIR and st.WEB_DIR == os.path.join(STUDIO_DIR, 'web'))
r = subprocess.run([sys.executable, os.path.join(STUDIO_DIR, 'studio.py'), '--version'], capture_output=True, text=True, timeout=30)
check('--version prints the version and exits 0', r.returncode == 0 and r.stdout.strip() == 'TurtleBot Studio ' + st.VERSION, r.stdout + r.stderr)

# ---------------------------------------------------------------- scripts under bash
BASH = shutil.which('bash')
if BASH:
    try:
        ok = subprocess.run([BASH, '-c', 'echo ok'], capture_output=True, text=True, timeout=20).stdout.strip() == 'ok'
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    BASH = BASH if ok else None
add_script = st.wifi_add_script()
check('add script: all three heredocs embedded, no placeholder left', '@@' not in add_script and add_script.count('STUDIO_PY_EOF') == 2
      and add_script.count('STUDIO_FETCH_EOF') == 2 and add_script.count('STUDIO_JOIN_EOF') == 2)
check('add script: password still piped from a builtin to the writer, never echoed', "printf '%s' \"$pw\" | sudo python3 -c \"$WRITER\"" in add_script
      and not any('$pw' in ln for ln in add_script.splitlines() if ln.lstrip().startswith('echo')) and 'set -x' not in add_script)
check('fetch program compiles and talks to the abstract socket', compile(st.WIFI_FETCH, 'fetch', 'exec') and 'turtlebot-studio-wifi-' in st.WIFI_FETCH
      and 'SO_PEERCRED' in st.WIFI_FETCH)
check('add script argument limits: nonce and timeout pass build_robot_script_cmd',
      st.build_robot_script_cmd(add_script, st.b64s('Net'), 'studio-Net', '1', 'a' * 32, '45').count(' ') >= 5)
join_path = os.path.join(OUT, 'join.sh')
add_path = os.path.join(OUT, 'add.sh')
for pth, txt in ((join_path, st.WIFI_JOIN_SCRIPT), (add_path, add_script)):
    with open(pth, 'w', newline='\n') as f:
        f.write(txt)
if BASH:
    for nm, pth in (('join', join_path), ('add', add_path)):
        r = subprocess.run([BASH, '-n', pth], capture_output=True, text=True)
        check(f'bash -n on the {nm} script', r.returncode == 0, r.stderr[-200:])

    stubs = os.path.join(OUT, 'stubs')
    os.makedirs(stubs)
    pyexe = fwd(sys.executable)
    stub_src = {
        'nmcli': '#!/bin/bash\necho "$*" >> "$LOGDIR/nmcli.log"\n'
                 'case "$*" in *GENERAL.CONNECTION*) echo "$PREV_CONN"; exit 0;; esac\n'
                 'if [ "$1" = "--wait" ]; then shift 2; fi\n'
                 'if [ "$1 $2" = "connection up" ]; then case ",$FAIL_UP," in *",$4,"*) exit 4;; esac; fi\nexit 0\n',
        'ip': '#!/bin/bash\nif [ -n "$NOIP" ]; then exit 0; fi\n'
              'echo "3: wlan0    inet 192.168.50.23/24 brd 192.168.50.255 scope global dynamic wlan0"\n',
        'sleep': '#!/bin/bash\nexit 0\n',
        'setsid': '#!/bin/bash\nprintf \'%s\\0\' "$@" >> "$LOGDIR/setsid.args"\nprintf \'SETSID-CALL\\0\' >> "$LOGDIR/setsid.args"\nexit 0\n',
        'sudo': '#!/bin/bash\nprintf \'%s\\0\' "$@" >> "$LOGDIR/sudo.args"\nprintf \'SUDO-CALL\\0\' >> "$LOGDIR/sudo.args"\n'
                '[ "$1" = "-v" ] && exit 0\nargs=()\nfor a in "$@"; do case "$a" in /etc/NetworkManager/system-connections/*) a="$FAKEDIR/${a##*/}";; '
                '/run/*) a="$FAKEDIR/${a##*/}";; esac; args+=("$a"); done\nexec "${args[@]}"\n',
        'python3': '#!/bin/bash\ncase "$2" in *turtlebot-studio-wifi-*) [ -n "$FETCH_FAIL" ] && exit 1; printf \'%%s\' "$FETCH_PSK"; exit 0;; esac\n'
                   'exec "%s" "$@"\n' % pyexe,
    }
    for nm, src in stub_src.items():
        with open(os.path.join(stubs, nm), 'w', newline='\n') as f:
            f.write(src)
        try:
            os.chmod(os.path.join(stubs, nm), 0o755)
        except OSError:
            pass

    def run_join(tag, ssid, prev='HomeNet', fail_up=(), noip=False, wait='7'):
        logd = os.path.join(OUT, 'join_' + tag)
        os.makedirs(logd)
        status = os.path.join(logd, 'status.json')
        env = dict(os.environ, PATH=stubs + os.pathsep + os.environ.get('PATH', ''), LOGDIR=fwd(logd), PREV_CONN=prev,
                   FAIL_UP=','.join(fail_up), LC_ALL='C.UTF-8')
        if noip:
            env['NOIP'] = '1'
        r = subprocess.run([BASH, join_path, ssid, wait, fwd(status)], capture_output=True, env=env, timeout=60)  # file: no -c, so $1 is the SSID too
        try:
            with open(status, encoding='utf-8') as f:
                js = json.load(f)
        except (OSError, ValueError) as e:
            js = {'_err': str(e)}
        try:
            with open(os.path.join(logd, 'nmcli.log'), encoding='utf-8') as f:
                lg = f.read().splitlines()
        except OSError:
            lg = []
        leftovers = [x for x in os.listdir(logd) if '.tmp.' in x]
        return r, js, lg, leftovers

    NASTYS = ['Home Net', 'it\'s "quoted" back\\slash', 'café ☃', 'tab\there', '$HOME `id` $(whoami)', 'a;b|c&d']
    ok_all, why = True, ''
    for i, ssid in enumerate(NASTYS):
        r, js, lg, left = run_join('ok%d' % i, ssid)
        want_ssid = ssid
        if not (r.returncode == 0 and js.get('state') == 'joined' and js.get('ssid') == want_ssid and js.get('ip') == '192.168.50.23'
                and js.get('prev') == 'HomeNet' and isinstance(js.get('t'), int) and not left
                and ('--wait 7 connection up id ' + ssid) in lg and not any('delete' in x for x in lg)):
            ok_all, why = False, 'ssid %r: rc=%s js=%s log=%s out=%s' % (ssid, r.returncode, js, lg, r.stderr[-200:])
            break
    check('join job: success writes joined + ip, valid JSON for nasty SSIDs, nothing deleted, no temp files left', ok_all, why)
    st_mode = None
    try:
        st_mode = os.stat(os.path.join(OUT, 'join_ok0', 'status.json')).st_mode & 0o777
    except OSError:
        pass
    check('join job: status file readable by everyone (not secret)', st_mode is None or os.name == 'nt' or st_mode == 0o644, oct(st_mode or 0))

    r, js, lg, left = run_join('fail', 'WrongPw Net', fail_up=['WrongPw Net'])
    check('join job: failure removes the new profile, brings back the previous network, reports it',
          r.returncode == 1 and js.get('state') == 'failed' and js.get('ssid') == 'WrongPw Net' and js.get('fallback') == 'HomeNet'
          and js.get('fallback_ok') is True and js.get('removed') is True and 'wrong password' in js.get('reason', '')
          and 'connection down id WrongPw Net' in lg and 'connection delete id WrongPw Net' in lg
          and '--wait 30 connection up id HomeNet' in lg and lg.index('connection delete id WrongPw Net') < lg.index('--wait 30 connection up id HomeNet'),
          str((js, lg)))
    r, js, lg, left = run_join('fail2', 'WrongPw Net', fail_up=['WrongPw Net', 'HomeNet'])
    check('join job: failed fallback is reported as fallback_ok false', js.get('state') == 'failed' and js.get('fallback') == 'HomeNet'
          and js.get('fallback_ok') is False and js.get('removed') is True, str(js))
    r, js, lg, left = run_join('fail3', 'WrongPw Net', prev='--', fail_up=['WrongPw Net'])
    check('join job: no previous network means no fallback attempt', js.get('state') == 'failed' and js.get('fallback') == ''
          and js.get('fallback_ok') is False and not any(x.startswith('--wait 30') for x in lg), str((js, lg)))
    r, js, lg, left = run_join('noip', 'No Ip Net', noip=True)
    check('join job: joined but no address counts as a failure with its own reason', js.get('state') == 'failed' and 'no IP' in js.get('reason', '')
          and js.get('removed') is True, str(js))
    r, js, lg, left = run_join('same', 'HomeNet', prev='HomeNet', fail_up=['HomeNet'])
    check('join job: never "falls back" to the network it just failed on', js.get('state') == 'failed' and js.get('fallback_ok') is False
          and not any(x.startswith('--wait 30') for x in lg), str((js, lg)))
    r, js, lg, left = run_join('prot', 'netplan-wlan0-Turtlebot4', fail_up=['netplan-wlan0-Turtlebot4'])
    check('join job: a netplan-* profile is never deleted', js.get('state') == 'failed' and js.get('removed') is False
          and not any('delete' in x for x in lg), str((js, lg)))
    r = subprocess.run([BASH, join_path, 'X', '5', fwd(os.path.join(OUT, 'no_such_dir', 's.json'))],
                       capture_output=True, env=dict(os.environ, PATH=stubs + os.pathsep + os.environ.get('PATH', ''), LOGDIR=fwd(OUT),
                                                    PREV_CONN='HomeNet'), timeout=60)
    check('join job: unwritable status path does not hang or crash', r.returncode in (0, 1))

    # ---- the terminal script with a nonce (stub sudo/nmcli/python3/setsid)
    PSK1 = 'p@ss w0rd`id`"q\'\\9'
    ok_all, why = True, ''
    for i, (ssid, cn) in enumerate([('Cafe Wi-Fi', '1'), ('$(x) it\'s', '0')]):
        logd = os.path.join(OUT, 'add%d_log' % i)
        fake = os.path.join(OUT, 'add%d_etc' % i)
        os.makedirs(logd)
        os.makedirs(fake)
        env = dict(os.environ, PATH=stubs + os.pathsep + os.environ.get('PATH', ''), LOGDIR=fwd(logd), FAKEDIR=fwd(fake), FETCH_PSK=PSK1,
                   LC_ALL='C.UTF-8', PREV_CONN='HomeNet')
        nonce = 'ab' * 16
        argv = [BASH, add_path, st.b64s(ssid), st.safe_conn_filename(ssid), cn, nonce, '45']
        r = subprocess.run(argv, input=b'\n', capture_output=True, env=env, timeout=60)
        out = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
        kf = os.path.join(fake, st.safe_conn_filename(ssid) + '.nmconnection')
        if r.returncode != 0 or not os.path.isfile(kf):
            ok_all, why = False, 'rc=%s %s' % (r.returncode, out[-300:])
            break
        txt = open(kf, encoding='utf-8').read()
        blob = b''
        for fn in ('sudo.args', 'nmcli.log', 'setsid.args'):
            if os.path.exists(os.path.join(logd, fn)):
                blob += open(os.path.join(logd, fn), 'rb').read()
        if PSK1.encode() in blob or PSK1 in out or 'powersave=2' not in txt or 'psk=' not in txt:
            ok_all, why = False, 'leak or bad keyfile for %r' % ssid
            break
        if 'Wi-Fi password for' in out:
            ok_all, why = False, 'script asked for the Wi-Fi password in the terminal'
            break
        calls = [c for c in blob.split(b'\0') if c]
        joined = (b'setsid' in calls and b'-f' in calls)
        if cn == '1':
            jtxt = st.WIFI_JOIN_SCRIPT.rstrip('\n').encode()
            if not (joined and jtxt in calls and ssid.encode() in calls and b'45' in calls and b'-v' in calls
                    and any(c.endswith(b'turtlebot-studio-wifi.json') for c in calls) and b'rm' in calls):
                ok_all, why = False, 'join job not started as expected: %r' % [c[:40] for c in calls]
                break
            if calls.index(b'rm') > calls.index(b'setsid'):
                ok_all, why = False, 'old status file not removed before the job starts'
                break
        elif joined or b'rm' in calls:
            ok_all, why = False, 'join job started although connect_now=0'
            break
    check('add script with nonce: password fetched not typed, stored intact, never in argv/output; join job only with connect-now',
          ok_all, why)
    logd = os.path.join(OUT, 'add_fail_log')
    os.makedirs(logd)
    env = dict(os.environ, PATH=stubs + os.pathsep + os.environ.get('PATH', ''), LOGDIR=fwd(logd), FAKEDIR=fwd(logd), FETCH_FAIL='1')
    r = subprocess.run([BASH, add_path, st.b64s('Net'), 'studio-Net', '1', 'cd' * 16, '45'], input=b'\n', capture_output=True, env=env, timeout=60)
    sa = open(os.path.join(logd, 'sudo.args'), 'rb').read().split(b'\0') if os.path.exists(os.path.join(logd, 'sudo.args')) else []
    check('add script with nonce: a failed fetch stops before the writer and the join job', b'Could not get the Wi-Fi password' in r.stdout
          and b'python3' not in sa and b'setsid' not in sa and r.returncode == 1, r.stdout[-200:].decode('utf-8', 'replace'))
    env['FETCH_PSK'] = 'short'
    env.pop('FETCH_FAIL')
    r = subprocess.run([BASH, add_path, st.b64s('Net'), 'studio-Net', '0', 'cd' * 16, '45'], input=b'\n', capture_output=True, env=env, timeout=60)
    check('add script with nonce: a too short fetched password is refused before the writer', b'8 to 63' in r.stdout and r.returncode == 1)
else:
    skip('bash tests (script syntax, join job, add script with nonce)', 'bash not found')

# ---------------------------------------------------------------- bridge: pure parts and the secret store
jd = os.path.join(OUT, 'jstat')
os.makedirs(jd)
jp = os.path.join(jd, 's.json')
with open(jp, 'w', encoding='utf-8') as f:
    json.dump({'state': 'joined', 'ssid': 'Net', 'ip': '1.2.3.4', 'prev': 'HomeNet', 't': 5, 'extra': 'dropped', 'removed': 'notbool'}, f)
check('read_join_status keeps known keys with the right types only', rb.read_join_status(jp) == {'state': 'joined', 'ssid': 'Net', 'ip': '1.2.3.4',
      'prev': 'HomeNet', 't': 5})
for bad_text in ('', 'not json', '[1]', '{"state":"weird"}', '{"state":"failed","fallback_ok":1}'):
    with open(jp, 'w', encoding='utf-8') as f:
        f.write(bad_text)
    r = rb.read_join_status(jp)
    check('read_join_status tolerates %r' % bad_text[:20], r is None or r == {'state': 'failed'}, str(r))
check('read_join_status: missing file is None', rb.read_join_status(os.path.join(jd, 'nope.json')) is None)


def net_run(args, timeout=3.0):
    a = ' '.join(args)
    if a.startswith('ip '):
        return '4: wlan0    inet 192.168.50.9/24 brd 192.168.50.255 scope global wlan0\n'
    if 'DEVICE,TYPE,STATE,CONNECTION' in a:
        return 'wlan0:wifi:connected:MyHome\n'
    if '802-11-wireless.mode' in a:
        return 'infrastructure\nMyHome\n'
    if a.endswith('connection show MyHome') and 'powersave' in a:
        return 'disable (2)\n'
    if 'powersave' in a:
        return 'default (0)\n'   # would be the answer for any other connection, e.g. a hard-coded "Students"
    return None


net = rb.collect_net(net_run, lambda p: None)
check('collect_net: power save of the ACTIVE wlan0 connection, old key kept', net['powersave'] == 'disable' and net['powersave_students'] == 'disable'
      and net['ssid'] == 'MyHome' and net['wifi_mode'] == 'client', str(net))
check('collect_net: wifi down leaves power save empty', rb.collect_net(lambda a, timeout=3: 'wlan0:wifi:disconnected:--\n' if 'DEVICE,TYPE' in ' '.join(a) else None,
                                                                       lambda p: None)['powersave'] is None)

# secret store with a loopback socket standing in for the abstract unix socket (works on every OS)
ports = {}
now = [1000.0]


def tcp_listen(nonce):
    ls = socket.socket()
    ls.bind(('127.0.0.1', 0))
    ls.listen(1)
    ports[nonce] = ls.getsockname()[1]
    return ls


def fetch_tcp(nonce, timeout=3):
    c = socket.create_connection(('127.0.0.1', ports[nonce]), timeout=timeout)
    data = b''
    try:
        while True:
            x = c.recv(256)
            if not x:
                break
            data += x
    finally:
        c.close()
    return data


peer_ok = [True]
ws = rb.WifiSecrets(listen=tcp_listen, peer_ok=lambda c: peer_ok[0], clock=lambda: now[0])
N1, N2, N3 = '1' * 32, '2' * 32, '3' * 32
SECRET = 'tcp-secret-pass-77'
bad_ok = True
for args in ((N1, 'short', 60), ('zz', SECRET, 60), (N1, SECRET, 'x'), (N1, 5, 60)):
    try:
        ws.put(*args)
        bad_ok = False
    except ValueError as e:
        if SECRET in str(e):
            bad_ok = False
check('secret store: bad nonce / password / ttl refused, error text never quotes the password', bad_ok)
ws.put(N1, SECRET, 60)
check('secret store: waiting after put', ws.state(N1) == 'waiting' and ws.state(N2) == 'none' and ws.state(None) == 'none')
peer_ok[0] = False
try:
    got = fetch_tcp(N1)
except OSError:
    got = b''
check('secret store: a reader of another user gets nothing and the secret keeps waiting', got == b'' and ws.state(N1) == 'waiting')
peer_ok[0] = True
got = fetch_tcp(N1)
time.sleep(0.2)
check('secret store: the right reader gets the password once, then state fetched and password dropped', got == SECRET.encode()
      and ws.state(N1) == 'fetched' and ws.items[N1]['psk'] is None)
try:
    fetch_tcp(N1, 1)
    again = True
except OSError:
    again = False
check('secret store: a second fetch is impossible (listener closed)', again is False)
ws.put(N2, SECRET + 'x', 60)
now[0] += 61
for _ in range(30):
    if ws.state(N2) == 'expired' and ws.items[N2]['sock'].fileno() == -1:
        break
    time.sleep(0.1)
check('secret store: expires after the ttl, password dropped, socket closed', ws.state(N2) == 'expired' and ws.items[N2]['psk'] is None
      and ws.items[N2]['sock'].fileno() == -1)
ws.put(N3, SECRET, 60)
ws.drop(N3)
time.sleep(0.8)
check('secret store: drop forgets the password', ws.state(N3) == 'expired' and ws.items[N3]['psk'] is None)
ws2 = rb.WifiSecrets(listen=tcp_listen, peer_ok=lambda c: True, clock=lambda: now[0])
ws2.put(N1, SECRET, 60, serve=False)
ws2.put(N2, SECRET, 60, serve=False)
check('secret store: a new password supersedes a waiting one', ws2.state(N1) == 'expired' and ws2.state(N2) == 'waiting')
check('secret store (no socket): take hands over once', ws2.take(N2) == SECRET and ws2.take(N2) is None and ws2.state(N2) == 'fetched')

if sys.platform.startswith('linux'):
    ru = rb.WifiSecrets()
    nn = 'ef' * 16
    ru.put(nn, 'linux-secret-pass', 60)
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.settimeout(3)
    c.connect('\0turtlebot-studio-wifi-' + nn)
    data = b''
    while True:
        x = c.recv(64)
        if not x:
            break
        data += x
    c.close()
    time.sleep(0.2)
    c2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c2.connect('\0turtlebot-studio-wifi-' + nn)
        second = True
    except OSError:
        second = False
    c2.close()
    check('linux: abstract unix socket hands the password to the same user once', data == b'linux-secret-pass' and ru.state(nn) == 'fetched' and second is False)
    ru.put('01' * 16, 'linux-secret-pass', 5)
    time.sleep(6.2)
    check('linux: abstract socket secret expires', ru.state('01' * 16) == 'expired')
    # the on-robot fetch program itself
    ru.put('02' * 16, 'fetched-by-script', 60)
    r = subprocess.run([sys.executable, '-c', st.WIFI_FETCH, '02' * 16], capture_output=True, timeout=20)
    check('linux: WIFI_FETCH prints exactly the password', r.stdout == b'fetched-by-script' and r.returncode == 0, str(r))
else:
    skip('abstract unix socket handoff, expiry, WIFI_FETCH', 'Linux only')

# ---------------------------------------------------------------- bridge process: commands in fake mode
BRIDGE = os.path.join(STUDIO_DIR, 'robot_bridge.py')


class Proc:
    def __init__(self, env_extra=None):
        self.home = tempfile.mkdtemp(prefix='studio_home_')
        env = dict(os.environ, STUDIO_BRIDGE_HOME=self.home, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        env.pop('STUDIO_BRIDGE_FAKE', None)
        env.update(env_extra or {})
        self.p = subprocess.Popen([sys.executable, '-u', BRIDGE, '--fake'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env)
        self.events, self.err, self.n = [], [], 0
        threading.Thread(target=self._rd, daemon=True).start()
        threading.Thread(target=lambda: [self.err.append(x) for x in self.p.stderr], daemon=True).start()

    def _rd(self):
        for line in self.p.stdout:
            try:
                self.events.append(json.loads(line.decode('utf-8')))
            except ValueError:
                self.events.append({'ev': 'BADLINE'})

    def send(self, cmd, timeout=10.0, **kw):
        self.n += 1
        i = self.n
        self.p.stdin.write((json.dumps(dict(kw, id=i, cmd=cmd)) + '\n').encode())
        self.p.stdin.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for ev in self.events[:]:
                if ev.get('ev') == 'reply' and ev.get('id') == i:
                    return ev
            time.sleep(0.02)
        return None

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(3)
        except (OSError, subprocess.TimeoutExpired):
            self.p.kill()


b = Proc({'STUDIO_FAKE_WIFI_SCALE': '0.1'})
SEC = 'bridge-secret-pw-42'
nonce = 'a1' * 16
r = b.send('wifi_secret_put', nonce=nonce, psk=SEC, ttl=60)
check('bridge wifi_secret_put (fake): waiting, no password in the reply', r and r['ok'] and r['state'] == 'waiting' and SEC not in json.dumps(r), str(r))
r = b.send('wifi_join_status', nonce=nonce)
check('bridge wifi_join_status: secret state, no join yet', r and r['ok'] and r['secret'] == 'waiting' and r['join'] is None, str(r))
for bad_args in ({'nonce': 'xyz', 'psk': SEC}, {'nonce': 'b2' * 16, 'psk': 'short12'}, {'nonce': 'b2' * 16, 'psk': 12345678}, {'nonce': 'b2' * 16, 'psk': SEC, 'ttl': 'abc'}):
    r = b.send('wifi_secret_put', **bad_args)
    check('bridge wifi_secret_put refuses %s' % sorted(bad_args), r and r['ok'] is False and SEC not in json.dumps(r) and 'short12' not in json.dumps(r), str(r))
r = b.send('wifi_join_status', nonce='nonsense')
check('bridge wifi_join_status refuses a bad nonce', r and r['ok'] is False)
r = b.send('wifi_secret_drop', nonce=nonce)
r2 = b.send('wifi_join_status', nonce=nonce)
check('bridge wifi_secret_drop expires the secret', r and r['ok'] and r2['secret'] == 'expired')
r = b.send('wifi_fake_add', nonce='nope', ssid='Net', connect_now=True)
check('bridge wifi_fake_add validates', r and r['ok'] is False)
nonce2 = 'c3' * 16
b.send('wifi_secret_put', nonce=nonce2, psk='wrongpass1', ttl=60)
r = b.send('wifi_fake_add', nonce=nonce2, ssid='OtherNet', connect_now=True)
seen_states = []
for _ in range(100):
    js = b.send('wifi_join_status', nonce=nonce2)
    seen_states.append((js['secret'], (js['join'] or {}).get('state')))
    if (js['join'] or {}).get('state') == 'failed':
        break
    time.sleep(0.05)
j = js['join']
check('bridge fake join: wrongpass1 fails, falls back to HomeNet, profile removed', j and j['state'] == 'failed' and j['fallback'] == 'HomeNet'
      and j['fallback_ok'] is True and j['removed'] is True and js['secret'] == 'fetched', str(seen_states[-3:]))
wi = b.send('wifi_info')
check('bridge fake: failed join leaves HomeNet active and no OtherNet profile', wi['wlan0']['ssid'] == 'HomeNet' and all(x['name'] != 'OtherNet' for x in wi['saved']))
nonce3 = 'd4' * 16
b.send('wifi_secret_put', nonce=nonce3, psk='goodpassword1', ttl=60)
b.send('wifi_fake_add', nonce=nonce3, ssid='NewNet', connect_now=True)
for _ in range(100):
    js = b.send('wifi_join_status', nonce=nonce3)
    if (js['join'] or {}).get('state') == 'joined' and js['join'].get('ssid') == 'NewNet':
        break
    time.sleep(0.05)
check('bridge fake join: success gives an address 192.168.50.2x', js['join'].get('state') == 'joined' and js['join']['ip'] == '192.168.50.21', str(js))
wi = b.send('wifi_info')
check('bridge fake: after joining NewNet it is saved, active, and the robot address changed',
      wi['wlan0']['ssid'] == 'NewNet' and wi['wlan0']['ip'] == '192.168.50.21' and any(x['name'] == 'NewNet' and x['active'] for x in wi['saved'])
      and {x['ssid'] for x in wi['scan']} == {'HomeNet', 'Students', 'eduroam', 'CafeFree', 'FailNet', 'PhoneHotspot'}
      and [x for x in wi['scan'] if x['ssid'] == 'eduroam'][0]['security'] == 'WPA2 802.1X'
      and [x for x in wi['scan'] if x['ssid'] == 'CafeFree'][0]['security'] == '--', str(wi)[:300])
time.sleep(0.3)
b.close()
errtxt = b''.join(b.err).decode('utf-8', 'replace')
check('bridge stderr never contains a password', SEC not in errtxt and 'wrongpass1' not in errtxt and 'goodpassword1' not in errtxt, errtxt[-300:])

# ---------------------------------------------------------------- HTTP in --fake (real studio.py + real robot_bridge.py)
HOME = os.path.join(OUT, 'fakehome')
os.makedirs(HOME)
CFG = os.path.join(OUT, 'httpcfg')
env = dict(os.environ, HOME=HOME, USERPROFILE=HOME, PYTHONDONTWRITEBYTECODE='1', STUDIO_FAKE_WIFI_SCALE='0.15', PYTHONIOENCODING='utf-8')
proc = subprocess.Popen([sys.executable, '-u', os.path.join(STUDIO_DIR, 'studio.py'), '--fake', '--no-browser', '--port', '0', '--config-dir', CFG,
                         '--fake-home', os.path.join(CFG, 'home'), '--heartbeat', '1'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
stdout_lines = []
url = {}
got_url = threading.Event()


def read_stdout():
    for raw in proc.stdout:
        line = raw.decode('utf-8', 'replace').rstrip()
        stdout_lines.append(line)
        m = re.search(r'http://127\.0\.0\.1:(\d+)/\?token=(\S+)', line)
        if m:
            url['port'], url['token'] = int(m.group(1)), m.group(2)
            got_url.set()


threading.Thread(target=read_stdout, daemon=True).start()
try:
    check('studio.py --port 0 picks a free port and prints the URL', got_url.wait(20) and url.get('port', 0) > 0, str(stdout_lines[-3:]))
    PORT, TOKEN = url['port'], url['token']

    def call(method, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=60)
        h = {'Host': '127.0.0.1:%d' % PORT, 'X-Studio-Token': TOKEN}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        c.request(method, path, body=data, headers=h)
        resp = c.getresponse()
        txt = resp.read()
        c.close()
        return json.loads(txt.decode('utf-8'))

    sse = bytearray()

    def read_sse():
        try:
            c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=120)
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

    j = call('GET', '/api/setup_status')
    check('GET setup_status: fields', j['ok'] and set(j) >= {'ssh', 'keygen', 'keyscan', 'key', 'host', 'setup_done', 'fake', 'os'}
          and j['fake'] is True and j['setup_done'] is False and j['host'] is None and j['os'] in ('windows', 'macos', 'linux')
          and set(j['ssh']) == {'found', 'path', 'version'} and j['key']['exists'] is False and j['key']['fingerprint'] is None, str(j))
    j2 = call('GET', '/api/setup_status')
    check('setup_status ssh version is cached per process and sane', j2['ssh'] == j['ssh'] and (not j['ssh']['found'] or (j['ssh']['version'] or '').lower().find('ssh') >= 0), str(j['ssh']))
    s0 = call('GET', '/api/settings')
    check('GET settings over HTTP has the new fields', s0['defaults']['robot_hostname'] == 'turtlebot4' and s0['setup_done'] is False and s0['trusted'][0]['builtin'])

    if st.find_exe('ssh-keygen'):
        j = call('POST', '/api/create_key', {})
        check('POST create_key: creates the per-user key', j['ok'] and j['created'] is True and j['fingerprint'].startswith('SHA256:') and os.path.isfile(j['path'])
              and os.path.abspath(j['path']).startswith(os.path.abspath(CFG)) or os.path.abspath(j['path']).startswith(os.path.abspath(HOME)), str(j))
        j3 = call('POST', '/api/create_key', {})
        check('create_key again: not created twice, same fingerprint', j3['ok'] and j3['created'] is False and j3['fingerprint'] == j['fingerprint'])
        j4 = call('GET', '/api/setup_status')
        check('setup_status shows the key afterwards', j4['key']['exists'] and j4['key']['fingerprint'] == j['fingerprint'])
    else:
        skip('create_key', 'ssh-keygen not found')

    j = call('POST', '/api/scan_host_key', {'host': 'fake'})
    check('POST scan_host_key (fake): fixed key, fingerprint, not trusted yet', j['ok'] and j['key'] == OTHER and j['fingerprint'] == st.key_fingerprint(OTHER)
          and j['trusted'] is False and j['label'] is None, str(j))
    check('scan_host_key refuses bad hosts', call('POST', '/api/scan_host_key', {'host': '-oProxyCommand=x'})['ok'] is False
          and call('POST', '/api/scan_host_key', {'host': 'a b'})['ok'] is False)
    check('trust_host_key needs confirm:true and a valid key', call('POST', '/api/trust_host_key', {'key': OTHER, 'label': 'x'})['ok'] is False
          and call('POST', '/api/trust_host_key', {'key': 'junk', 'confirm': True})['ok'] is False)
    j = call('POST', '/api/trust_host_key', {'key': OTHER, 'label': 'Bench robot', 'confirm': True})
    kh = open(os.path.join(CFG, 'known_hosts'), encoding='utf-8').read().splitlines()
    check('POST trust_host_key: listed with fingerprint, known_hosts has both keys', j['ok'] and j['label'] == 'Bench robot'
          and [t['label'] for t in j['trusted']] == ['Built-in robot key', 'Bench robot'] and kh == ['turtlebot4-lab ' + LAB, 'turtlebot4-lab ' + OTHER], str((j, kh)))
    j = call('POST', '/api/trust_host_key', {'key': OTHER, 'label': 'Renamed', 'confirm': True})
    check('trusting the same key again renames it (no duplicate)', j['ok'] and len(j['trusted']) == 2 and j['trusted'][1]['label'] == 'Renamed')
    j = call('POST', '/api/scan_host_key', {'host': 'fake'})
    check('scan_host_key now reports the label', j['trusted'] is True and j['label'] == 'Renamed')
    j = call('POST', '/api/untrust_host_key', {'key': OTHER})
    check('untrust_host_key needs confirm', j['ok'] is False)
    j = call('POST', '/api/untrust_host_key', {'key': OTHER, 'confirm': True})
    kh = open(os.path.join(CFG, 'known_hosts'), encoding='utf-8').read().splitlines()
    check('POST untrust_host_key removes it', j['ok'] and len(j['trusted']) == 1 and kh == ['turtlebot4-lab ' + LAB])
    check('untrust of an unknown key fails', call('POST', '/api/untrust_host_key', {'key': OTHER, 'confirm': True})['ok'] is False)
    j = call('POST', '/api/untrust_host_key', {'key': LAB, 'confirm': True})
    kh = open(os.path.join(CFG, 'known_hosts'), encoding='utf-8').read()
    check('untrust of the built-in key switches it off (not deleted from the list)', j['ok'] and j['trusted'][0]['enabled'] is False and kh == '')
    j = call('POST', '/api/scan_host_key', {'host': 'fake'})
    j = call('POST', '/api/trust_host_key', {'key': LAB, 'label': 'ignored', 'confirm': True})
    kh = open(os.path.join(CFG, 'known_hosts'), encoding='utf-8').read().splitlines()
    check('trusting the built-in key again switches it back on', j['ok'] and j['trusted'][0]['enabled'] is True and len(j['trusted']) == 1 and kh == ['turtlebot4-lab ' + LAB])

    j = call('POST', '/api/test_login', {'host': 'fake'})
    check('POST test_login (fake)', j['ok'] and j['hostname'] == 'fake-turtlebot4', str(j))
    j = call('POST', '/api/setup_key', {})
    check('POST setup_key in fake mode opens no terminal', j == {'ok': True, 'fake': True, 'note': 'fake mode: no terminal'}, str(j))
    j = call('POST', '/api/settings', {'setup_done': True})
    check('POST settings setup_done', j['ok'] and j['setup_done'] is True)
    j = call('POST', '/api/settings', {'robot_user': 'Bad User'})
    check('POST settings rejects a bad robot_user over HTTP', j['ok'] is False)

    # --- S-c over HTTP
    j = call('POST', '/api/connect', {})
    check('fake connect works', j['ok'] is True, str(j))
    PSK_OK, PSK_BAD, PSK_BAD2 = 'goodpass-9QXZ', 'nope-FAILPW-77', 'wrongpass1'
    for body, why in (({'ssid': 'Net', 'psk': PSK_OK}, 'confirm'), ({'ssid': 'Net', 'psk': 'short', 'confirm': True}, 'password'),
                      ({'ssid': 'Net', 'psk': 'x' * 64, 'confirm': True}, 'password'), ({'ssid': 'Net', 'psk': 'é' * 9, 'confirm': True}, 'password'),
                      ({'ssid': 'Net', 'psk': 12345678, 'confirm': True}, 'password'), ({'ssid': 'Net', 'confirm': True}, 'password'),
                      ({'ssid': 'a\nb', 'psk': PSK_OK, 'confirm': True}, 'network name'), ({'ssid': 'x' * 33, 'psk': PSK_OK, 'confirm': True}, 'network name'),
                      ({'ssid': 'Turtlebot4', 'psk': PSK_OK, 'confirm': True}, 'hotspot'), ({'ssid': 'netplan-eth0', 'psk': PSK_OK, 'confirm': True}, 'hotspot'),
                      ({'ssid': 'Students', 'psk': PSK_OK, 'confirm': True}, 'already saved'), ({'ssid': 'HomeNet', 'psk': PSK_OK, 'confirm': True}, 'already saved')):
        j = call('POST', '/api/robot_wifi_add', body)
        check('robot_wifi_add refused (%s): %s' % (why, str({k: v for k, v in body.items() if k != 'psk'})[:50]),
              j['ok'] is False and why in j['error'] and PSK_OK not in json.dumps(j), str(j))
    j = call('POST', '/api/robot_wifi_status', {'nonce': 'bad'})
    check('robot_wifi_status refuses a bad nonce', j['ok'] is False)

    def wait_status(nonce, want, timeout=20):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            last = call('POST', '/api/robot_wifi_status', {'nonce': nonce})
            if last.get('ok') and (last['join'] or {}).get('state') in want:
                return last
            time.sleep(0.1)
        return last

    j = call('POST', '/api/robot_wifi_add', {'ssid': 'NewNet', 'psk': PSK_OK, 'connect_now': True, 'confirm': True})
    check('robot_wifi_add (fake) succeeds: nonce, ttl, timeout, no terminal, no password echoed', j['ok'] and re.match(r'^[0-9a-f]{32}$', j['nonce'])
          and j['ttl'] == 180 and j['timeout'] == 45 and j['fake'] is True and j['ssid'] == 'NewNet' and j['connect_now'] is True and PSK_OK not in json.dumps(j), str(j))
    s1 = wait_status(j['nonce'], ('joined', 'failed'))
    check('robot_wifi_status: joined with a new IP, secret fetched, address stored', s1['ok'] and s1['join']['state'] == 'joined' and s1['join']['ssid'] == 'NewNet'
          and s1['join']['ip'].startswith('192.168.50.') and s1['secret'] == 'fetched' and s1['stored'] is True and s1['join']['prev'] == 'HomeNet', str(s1))
    sj = call('GET', '/api/settings')
    check('known_addresses has the new network', sj['known_addresses'].get('NewNet', {}).get('ip') == s1['join']['ip'])
    s2 = call('POST', '/api/robot_wifi_status', {})
    check('robot_wifi_status without a nonce still reads the join result', s2['ok'] and s2['join']['state'] == 'joined' and s2['secret'] == 'none')
    wi = call('POST', '/api/bridge', {'cmd': 'wifi_info'})
    check('wifi_info after the join: robot is on NewNet', wi['ok'] and wi['wlan0']['ssid'] == 'NewNet' and any(x['name'] == 'NewNet' for x in wi['saved']))
    j = call('POST', '/api/robot_wifi_add', {'ssid': 'NewNet', 'psk': PSK_OK, 'confirm': True})
    check('adding the same network again is refused (already saved)', j['ok'] is False and 'already saved' in j['error'])

    j = call('POST', '/api/robot_wifi_add', {'ssid': 'FailNet', 'psk': PSK_BAD, 'connect_now': True, 'confirm': True})
    s3 = wait_status(j['nonce'], ('joined', 'failed'))
    check('FailNet: join fails, robot back on NewNet, profile removed', s3['join']['state'] == 'failed' and s3['join']['fallback'] == 'NewNet'
          and s3['join']['fallback_ok'] is True and s3['join']['removed'] is True and s3['stored'] is False and 'wrong password' in s3['join']['reason'], str(s3))
    j = call('POST', '/api/robot_wifi_add', {'ssid': 'PhoneHotspot', 'psk': PSK_BAD2, 'connect_now': True, 'confirm': True})
    s4 = wait_status(j['nonce'], ('joined', 'failed'))
    check('the password wrongpass1 fails on any network', s4['join']['state'] == 'failed' and s4['join']['ssid'] == 'PhoneHotspot')
    j = call('POST', '/api/robot_wifi_add', {'ssid': 'SaveOnly', 'psk': PSK_OK, 'connect_now': False, 'confirm': True})
    time.sleep(0.6)
    s5 = call('POST', '/api/robot_wifi_status', {'nonce': j['nonce']})
    wi = call('POST', '/api/bridge', {'cmd': 'wifi_info'})
    check('save without connecting: secret fetched, no join, network saved, robot stays', s5['secret'] == 'fetched' and s5['join'] is None
          and any(x['name'] == 'SaveOnly' for x in wi['saved']) and wi['wlan0']['ssid'] == 'NewNet', str((s5, wi['wlan0'])))
    # a stale result of another network is not shown for this nonce
    s6 = call('POST', '/api/robot_wifi_status', {'nonce': j['nonce']})
    check('status for a nonce hides another network\'s result', s6['join'] is None)
    j = call('POST', '/api/disconnect', {})
    j = call('POST', '/api/robot_wifi_status', {'nonce': 'e5' * 16})
    check('robot_wifi_status while disconnected is a clean error', j['ok'] is False and j.get('kind') == 'not_connected')
    j = call('POST', '/api/robot_wifi_add', {'ssid': 'Another', 'psk': PSK_OK, 'confirm': True})
    check('robot_wifi_add while disconnected is a clean error', j['ok'] is False and 'connect' in j['error'] and PSK_OK not in json.dumps(j))
    time.sleep(0.5)

    # --- no password anywhere
    secrets_all = [PSK_OK, PSK_BAD, PSK_BAD2]
    leaks = []
    for root, _, files in os.walk(CFG):
        for fn in files:
            data = open(os.path.join(root, fn), 'rb').read()
            for sct in secrets_all:
                if sct.encode() in data:
                    leaks.append((fn, sct))
    check('no Wi-Fi password in any file under the config dir (settings.json, studio.log, known_hosts, fake home)', not leaks, str(leaks))
    log_txt = open(os.path.join(CFG, 'studio.log'), encoding='utf-8').read()
    check('studio.log mentions the request but not the password', 'Wi-Fi add requested for NewNet' in log_txt and not any(x in log_txt for x in secrets_all))
    time.sleep(0.5)
    check('no Wi-Fi password in the SSE event stream', len(sse) > 100 and not any(x.encode() in bytes(sse) for x in secrets_all), 'sse bytes %d' % len(sse))
    check('no Wi-Fi password on studio stdout', not any(x in '\n'.join(stdout_lines) for x in secrets_all))
finally:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()

shutil.rmtree(OUT, ignore_errors=True) if fails == 0 else print('generated files are in', OUT)
print('\n%d failure(s)' % fails)
sys.exit(1 if fails else 0)
