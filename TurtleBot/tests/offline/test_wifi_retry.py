"""Offline test of TurtleBot/setup/wifi-retry/tb4-wifi-retry (the real bash script).

No robot, no network. Stub nmcli, ip, logger and flock executables are put first on PATH in a temp dir, so the
script's decisions can be checked: which profiles it tries, in which order, and what it restores.
Skips cleanly when bash is missing.

Usage: python test_wifi_retry.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, '..', '..', 'setup', 'wifi-retry', 'tb4-wifi-retry'))
OUT = tempfile.mkdtemp(prefix='tb4_wifi_retry_')
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


BASH = shutil.which('bash')
if BASH:
    try:
        ok = subprocess.run([BASH, '-c', 'echo ok'], capture_output=True, text=True, timeout=20).stdout.strip() == 'ok'
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    BASH = BASH if ok else None

# State files in $STATE: active (name of the wlan0 connection), profiles (uuid|name|mode|autoconnect|priority),
# succeed (profile names whose "up" works), neigh (output of ip neigh), nmcli.log (UP lines), logger.log.
NMCLI = r'''#!/bin/bash
S="$STATE"
prop() {  # prop PROPERTY FIELD-VALUE-LOOKUP-KEY LOOKUP-COLUMN
  case "$1" in
    connection.id) c=2 ;; 802-11-wireless.mode) c=3 ;; connection.autoconnect) c=4 ;;
    connection.autoconnect-priority) c=5 ;; *) exit 1 ;;
  esac
  awk -F'|' -v k="$2" -v kc="$3" -v c="$c" '$kc == k { print $c; f = 1 } END { exit f ? 0 : 1 }' "$S/profiles"
}
if [ "$1" = "--wait" ]; then
  shift 2
  if [ "$1 $2" = "connection up" ] && [ "$3" = "id" ] && [ "$5" = "ifname" ] && [ "$6" = "wlan0" ]; then
    echo "UP $4" >> "$S/nmcli.log"
    grep -qxF -- "$4" "$S/succeed" && exit 0
    exit 4
  fi
  echo "BAD $*" >> "$S/nmcli.log"; exit 2
fi
if [ "$1 $2 $3 $4 $5" = "-g GENERAL.CONNECTION device show wlan0" ]; then cat "$S/active"; exit 0; fi
if [ "$1 $2 $3 $4 $5" = "-t -f UUID,TYPE connection show" ]; then
  awk -F'|' '{ print $1 ":802-11-wireless" }' "$S/profiles"; exit 0
fi
if [ "$1" = "-g" ] && [ "$3 $4" = "connection show" ]; then
  if [ "$5" = "uuid" ]; then prop "$2" "$6" 1; exit $?; fi
  if [ "$5" = "id" ]; then prop "$2" "$6" 2; exit $?; fi
fi
echo "BAD $*" >> "$S/nmcli.log"; exit 2
'''
IP = '#!/bin/bash\n[ "$1 $2 $3 $4" = "neigh show dev wlan0" ] && cat "$STATE/neigh"\nexit 0\n'
LOGGER = '#!/bin/bash\n[ "$1 $2" = "-t tb4-wifi-retry" ] || exit 2\nshift 2\n[ "$1" = "--" ] && shift\necho "$*" >> "$STATE/logger.log"\n'
FLOCK = '#!/bin/bash\nexit 0\n'

STUBS = os.path.join(OUT, 'stubs')
os.makedirs(STUBS)
for nm, body in (('nmcli', NMCLI), ('ip', IP), ('logger', LOGGER), ('flock', FLOCK)):
    p = os.path.join(STUBS, nm)
    with open(p, 'w', newline='\n') as f:
        f.write(body)
    os.chmod(p, 0o755)

PROFILES_STD = [
    ('u1', 'Students', 'infrastructure', 'yes', '10'),
    ('u2', 'TP-LINK_Extender_5GHz', 'infrastructure', 'yes', '20'),
    ('u3', 'Old Net', 'infrastructure', 'yes', '5'),
    ('u4', 'Manual Net', 'infrastructure', 'no', '30'),
    ('u5', 'netplan-wlan0-Turtlebot4', 'ap', 'yes', '0'),
]


def run(name, active, profiles=PROFILES_STD, succeed=(), neigh='', leases=None, synced='yes'):
    st = os.path.join(OUT, name)
    os.makedirs(st)

    def w(fn, txt):
        with open(os.path.join(st, fn), 'w', newline='\n') as f:
            f.write(txt)
    w('active', active + '\n')
    w('profiles', ''.join('|'.join(p) + '\n' for p in profiles))
    w('succeed', ''.join(s + '\n' for s in succeed))
    w('neigh', neigh)
    w('nmcli.log', '')
    w('logger.log', '')
    env = dict(os.environ, STATE=fwd(st), PATH=fwd(STUBS) + os.pathsep + os.environ['PATH'],
               TB4_WIFI_LOCK=fwd(os.path.join(st, 'lock')), TB4_WIFI_LEASES=fwd(os.path.join(st, 'leases')),
               TB4_WIFI_CLOCK_SYNCED=synced)
    if leases is not None:
        w('leases', leases)
    r = subprocess.run([BASH, fwd(SCRIPT)], capture_output=True, text=True, env=env, timeout=60)
    ups = [ln[3:] for ln in open(os.path.join(st, 'nmcli.log'), encoding='utf-8').read().splitlines() if ln.startswith('UP ')]
    bad = [ln for ln in open(os.path.join(st, 'nmcli.log'), encoding='utf-8').read().splitlines() if ln.startswith('BAD ')]
    logs = open(os.path.join(st, 'logger.log'), encoding='utf-8').read()
    return r.returncode, ups, logs, bad, r


if not BASH:
    skip('tb4-wifi-retry scenarios', 'bash not found')
else:
    r = subprocess.run([BASH, '-n', fwd(SCRIPT)], capture_output=True, text=True)
    check('bash -n on tb4-wifi-retry', r.returncode == 0, r.stderr[-200:])
    check('script has LF line endings', b'\r' not in open(SCRIPT, 'rb').read())

    rc, ups, logs, bad, _ = run('client_mode', 'Students', succeed=['Students'])
    check('client mode: exit 0, no connection change', rc == 0 and ups == [] and not bad, f'rc={rc} ups={ups} bad={bad}')
    check('client mode: logged why', 'not the hotspot' in logs, logs)

    rc, ups, logs, bad, _ = run('no_active', '--')
    check('no active connection: exit 0, no change', rc == 0 and ups == [], f'rc={rc} ups={ups}')

    for state in ('REACHABLE', 'STALE', 'DELAY', 'PROBE'):
        rc, ups, logs, bad, _ = run('client_' + state, 'netplan-wlan0-Turtlebot4',
                                    neigh=f'10.42.0.23 lladdr aa:bb:cc:dd:ee:ff {state}\n')
        check(f'AP with a {state} client: skipped, exit 0, nothing brought up', rc == 0 and ups == [] and 'has clients' in logs,
              f'rc={rc} ups={ups}')

    rc, ups, logs, bad, _ = run('dead_neigh', 'netplan-wlan0-Turtlebot4', succeed=['TP-LINK_Extender_5GHz'],
                                neigh='10.42.0.23 FAILED\n10.42.0.24 dev wlan0 INCOMPLETE\n192.168.1.5 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n')
    check('FAILED/INCOMPLETE entries and other subnets are not clients', ups == ['TP-LINK_Extender_5GHz'], f'ups={ups}')

    future = int(time.time()) + 3600
    rc, ups, logs, bad, _ = run('lease_live', 'netplan-wlan0-Turtlebot4', leases=f'{future} aa:bb:cc:dd:ee:ff 10.42.0.50 phone *\n')
    check('AP with an unexpired lease: skipped', rc == 0 and ups == [] and 'has clients' in logs, f'rc={rc} ups={ups}')
    rc, ups, logs, bad, _ = run('lease_old', 'netplan-wlan0-Turtlebot4', succeed=['TP-LINK_Extender_5GHz'],
                                leases='1000000 aa:bb:cc:dd:ee:ff 10.42.0.50 phone *\n')
    check('AP with an expired lease: retries', ups == ['TP-LINK_Extender_5GHz'], f'ups={ups}')
    rc, ups, logs, bad, _ = run('lease_unsynced', 'netplan-wlan0-Turtlebot4', succeed=['TP-LINK_Extender_5GHz'],
                                leases=f'{future} aa:bb:cc:dd:ee:ff 10.42.0.50 phone *\n', synced='no')
    check('clock not synced: an "unexpired" lease is ignored and it retries', ups == ['TP-LINK_Extender_5GHz'], f'ups={ups}')

    rc, ups, logs, bad, _ = run('first_success', 'netplan-wlan0-Turtlebot4', succeed=['Students'])
    check('AP, no clients: tries by priority (20 then 10) and stops at the first success',
          rc == 0 and ups == ['TP-LINK_Extender_5GHz', 'Students'], f'rc={rc} ups={ups}')
    check('first_success: autoconnect-no and AP profiles not tried, hotspot not restored',
          'Manual Net' not in ups and 'netplan-wlan0-Turtlebot4' not in ups and 'Old Net' not in ups)
    check('first_success: log says what happened', "joined 'Students'" in logs, logs)

    rc, ups, logs, bad, _ = run('top_success', 'netplan-wlan0-Turtlebot4', succeed=['TP-LINK_Extender_5GHz', 'Students'])
    check('highest priority succeeds: only one attempt', rc == 0 and ups == ['TP-LINK_Extender_5GHz'], f'ups={ups}')

    rc, ups, logs, bad, _ = run('all_fail', 'netplan-wlan0-Turtlebot4', succeed=['netplan-wlan0-Turtlebot4'])
    check('all fail: every client profile tried in priority order, then the hotspot restored, exit 10',
          rc == 10 and ups == ['TP-LINK_Extender_5GHz', 'Students', 'Old Net', 'netplan-wlan0-Turtlebot4'], f'rc={rc} ups={ups}')
    check('all fail: no unexpected nmcli calls', not bad, str(bad))
    check('all fail: log says the hotspot is back', 'hotspot' in logs and 'is back' in logs, logs)

    rc, ups, logs, bad, _ = run('restore_fail', 'netplan-wlan0-Turtlebot4')
    check('all fail and hotspot restore fails: exit 11 with an ERROR line', rc == 11 and 'ERROR' in logs, f'rc={rc}')

    prof = [p for p in PROFILES_STD if p[2] != 'ap'] + [('u9', 'Lab Hotspot 2', 'ap', 'yes', '0')]
    rc, ups, logs, bad, _ = run('ap_dynamic', 'Lab Hotspot 2', profiles=prof, succeed=['Lab Hotspot 2'])
    check('hotspot profile found by mode, not by name', rc == 10 and ups[-1] == 'Lab Hotspot 2', f'ups={ups}')

    prof = [('u1', 'Lab Wi-Fi 5G', 'infrastructure', 'yes', '40'), ('u2', 'Students', 'infrastructure', 'yes', '10'),
            ('u5', 'My Hotspot Profile', 'ap', 'yes', '0')]
    rc, ups, logs, bad, _ = run('space', 'My Hotspot Profile', profiles=prof, succeed=['Lab Wi-Fi 5G'])
    check('profile name with spaces is passed as one argument', rc == 0 and ups == ['Lab Wi-Fi 5G'] and not bad, f'ups={ups} bad={bad}')
    rc, ups, logs, bad, _ = run('space_fail', 'My Hotspot Profile', profiles=prof)
    check('hotspot name with spaces is restored intact', ups == ['Lab Wi-Fi 5G', 'Students', 'My Hotspot Profile'], f'ups={ups}')

print(f'\n{fails} failure(s); generated files are in {OUT}')
sys.exit(1 if fails else 0)
