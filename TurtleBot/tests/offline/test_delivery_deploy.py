"""Offline tests of TurtleBot/delivery/tools/deploy.py. No robot, no network.

A fake `ssh` and `scp` (small wrappers around fake_tool.py) are put first on PATH in a temporary folder. They log every
call and the script sent on stdin, copy the uploaded archive aside, and answer from environment variables
(FAKE_MISSION=1: a mission is running; FAKE_FAIL=<text>: the script containing <text> fails).
Covers: manifest content, excludes, file modes, byte-exact line endings, command order, checksum and syntax checks
before the symlink switch, refusal while a mission runs, rollback, status, dry run, IPv6 bracket form for scp, and
(when bash is found) the remote scripts themselves in a temporary HOME; the symlink steps run only where this
computer allows symlinks (Linux, macOS, Windows with developer mode).
Usage (from the repo root): python TurtleBot/tests/offline/test_delivery_deploy.py
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery', 'tools'))
DEPLOY = os.path.join(TOOLS, 'deploy.py')
sys.path.insert(0, TOOLS)
import deploy  # noqa: E402

TMP = tempfile.mkdtemp(prefix='tb4_deploy_tests_')
FAKEBIN = os.path.join(TMP, 'bin')
UPLOADS = os.path.join(TMP, 'uploads')
LOG = os.path.join(TMP, 'calls.jsonl')
KEY = os.path.join(TMP, 'key')
os.makedirs(FAKEBIN)
os.makedirs(UPLOADS)
with open(KEY, 'w') as _f:
    _f.write('not a real key\n')
fails = 0
HOST_V6 = 'ubuntu@fe80::da3a:ddff:fe41:d5df%8'

FAKE_TOOL = r'''
import json, os, shutil, sys
tool = sys.argv[1]
args = sys.argv[2:]
rec = {"tool": tool, "args": args, "cwd": os.getcwd()}
if tool == "ssh":
    rec["stdin"] = sys.stdin.buffer.read().decode("utf-8")
elif tool == "scp":
    src = args[-2]
    rec["exists_in_cwd"] = os.path.isfile(src)
    if os.path.isfile(src):
        shutil.copy(src, os.path.join(os.environ["FAKE_UPLOADS"], os.path.basename(src)))
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\n")
if tool == "ssh":
    s = rec["stdin"]
    fail = os.environ.get("FAKE_FAIL")
    if fail and fail in s:
        sys.stderr.write("fake failure\n")
        sys.exit(1)
    if "MISSION_RUNNING" in s:
        print("MISSION_RUNNING 4242" if os.environ.get("FAKE_MISSION") == "1" else "MISSION_IDLE")
        print("HOST_OK fakerobot")
    else:
        print("fake ok")
'''
with open(os.path.join(FAKEBIN, 'fake_tool.py'), 'w') as _f:
    _f.write(FAKE_TOOL)
for _tool in ('ssh', 'scp'):
    if os.name == 'nt':
        with open(os.path.join(FAKEBIN, _tool + '.cmd'), 'w', newline='\r\n') as _f:
            _f.write(f'@echo off\r\n"{sys.executable}" "%~dp0fake_tool.py" {_tool} %*\r\n')
    else:
        _p = os.path.join(FAKEBIN, _tool)
        with open(_p, 'w', newline='\n') as _f:
            _f.write(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake_tool.py" {_tool} "$@"\n')
        os.chmod(_p, 0o755)


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info and not cond else ''))
    if not cond:
        fails += 1


def run_deploy(args, **env):
    if os.path.exists(LOG):
        os.remove(LOG)
    for f in os.listdir(UPLOADS):
        os.remove(os.path.join(UPLOADS, f))
    e = dict(os.environ)
    e['PATH'] = FAKEBIN + os.pathsep + e.get('PATH', '')
    e.update({'FAKE_LOG': LOG, 'FAKE_UPLOADS': UPLOADS, 'PYTHONDONTWRITEBYTECODE': '1'})
    e.pop('FAKE_MISSION', None)
    e.pop('FAKE_FAIL', None)
    e.update(env)
    r = subprocess.run([sys.executable, DEPLOY, *args, '--key', KEY], capture_output=True, env=e, timeout=120)
    calls = []
    if os.path.exists(LOG):
        with open(LOG, encoding='utf-8') as f:
            calls = [json.loads(line) for line in f if line.strip()]
    return r.returncode, r.stdout.decode('utf-8', 'replace'), calls


def step_of(call):
    s = call.get('stdin', '')
    for key, name in (('MISSION_', 'preflight'), ('UNPACKED', 'unpack'), ('CHECKSUMS_OK', 'verify'),
                      ('PY_COMPILE_OK', 'syntax'), ('DISCARDED', 'discard'), ('SWITCHED', 'switch'),
                      ('PRUNED', 'prune'), ('ROLLED_BACK_TO', 'rollback'), ('MANIFEST_MATCH', 'status'),
                      ('MENU_', 'menu'), ('HOST_OK', 'prepare')):
        if key in s:
            return name
    return call['tool']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_archive(path):
    with tarfile.open(path) as tf:
        members = {m.name: m for m in tf.getmembers()}
        return members, {n: tf.extractfile(m).read() for n, m in members.items()}


# ---------------------------------------------------------------- host forms and name checks
check('split_host plain', deploy.split_host('ubuntu@fe80::1%8') == ('ubuntu', 'fe80::1%8'))
check('split_host brackets', deploy.split_host('ubuntu@[fe80::1%8]') == ('ubuntu', 'fe80::1%8'))
check('ssh target has no brackets', deploy.ssh_target('ubuntu@[fe80::1%8]') == 'ubuntu@fe80::1%8')
check('scp target gets brackets for IPv6',
      deploy.scp_target('ubuntu@fe80::1%8', '/tmp/x') == 'ubuntu@[fe80::1%8]:/tmp/x')
check('scp target keeps brackets once',
      deploy.scp_target('ubuntu@[fe80::1%8]', '/tmp/x') == 'ubuntu@[fe80::1%8]:/tmp/x')
check('scp target for an IPv4 address has no brackets',
      deploy.scp_target('ubuntu@192.168.100.31', '/tmp/x') == 'ubuntu@192.168.100.31:/tmp/x')
try:
    deploy.split_host('ubuntu@host; rm -rf ~')
    check('hostile --host is rejected', False)
except deploy.DeployError:
    check('hostile --host is rejected', True)
try:
    deploy.check_release_name('x; rm -rf ~')
    check('bad release name is rejected', False)
except deploy.DeployError:
    check('bad release name is rejected', True)

# ---------------------------------------------------------------- packing a synthetic tree
src = os.path.join(TMP, 'src')
d = os.path.join(src, 'delivery')
t = os.path.join(src, 'timing')
for sub in ('__pycache__', 'docs', os.path.join('config', 'upstream'), 'robot', 'tools', 'routes', 'logs'):
    os.makedirs(os.path.join(d, sub))
os.makedirs(t)
CRLF_PY = b'x = 1\r\ny = 2\r\n'
blobs = {
    'delivery_core.py': CRLF_PY, 'robot/start.sh': b'#!/bin/bash\necho hi\n', 'config/upstream/u.yaml': b'a: 1\n',
    'config/n.yaml': b'b: 2\n', 'tools/t.py': b'print(1)\n', '__pycache__/delivery_core.cpython-313.pyc': b'\0\0',
    'docs/guide.md': b'# docs\n', 'tools/old.pyc': b'\0', 'routes/r.yaml': b'r: 1\n', 'logs/l.txt': b'log\n',
    'VERSION': b'stale\n', 'MANIFEST.sha256': b'stale\n',
}
for rel, data in blobs.items():
    with open(os.path.join(d, *rel.split('/')), 'wb') as f:
        f.write(data)
for n in deploy.TIMING_FILES:
    with open(os.path.join(t, n), 'wb') as f:
        f.write(b'# ' + n.encode() + b'\n')
files = deploy.collect_files(d, t)
names = [a for a, _ in files]
check('collect: keeps code, config and config/upstream',
      {'delivery_core.py', 'robot/start.sh', 'config/upstream/u.yaml', 'config/n.yaml', 'tools/t.py'} <= set(names),
      names)
excluded = ('__pycache__', 'docs', 'routes', 'logs')
check('collect: no __pycache__, .pyc, docs, routes, logs, stale VERSION or MANIFEST',
      not any(x.startswith(excluded) or x.endswith('.pyc') or x in ('VERSION', 'MANIFEST.sha256') for x in names),
      names)
check('collect: timing tools go under robot_tools/',
      'robot_tools/record_timing.py' in names and 'robot_tools/analyze_timing.py' in names)
check('collect: forward slashes only', not any('\\' in x for x in names))
now = deploy.dt.datetime(2026, 11, 5, 10, 0, 0, tzinfo=deploy.dt.timezone.utc)
ver = deploy.version_text('REL', 'abc1234', True, now)
check('VERSION has sha, dirty flag and UTC time',
      'git_sha=abc1234' in ver and 'dirty=true' in ver and 'built_utc=2026-11-05T10:00:00Z' in ver, ver)
check('release name is UTC stamp-sha[-dirty]',
      deploy.release_name('abc1234', now, True) == '20261105T100000Z-abc1234-dirty'
      and deploy.release_name('abc1234', now) == '20261105T100000Z-abc1234')
arch = os.path.join(TMP, 'a.tar.gz')
manifest = deploy.build_archive(files, ver, arch, 0)
members, content = read_archive(arch)
check('archive holds exactly the files + VERSION + MANIFEST.sha256',
      set(content) == set(names) | {'VERSION', 'MANIFEST.sha256'}, sorted(content))
lines = [ln for ln in manifest.split('\n') if ln]
mp = {ln.split('  ', 1)[1]: ln.split('  ', 1)[0] for ln in lines}
check('manifest: every file except itself, right sha256, sha256sum -c format (hash, two spaces, name)',
      set(mp) == set(content) - {'MANIFEST.sha256'} and all(mp[n] == sha(content[n]) for n in mp)
      and all(len(ln.split('  ', 1)[0]) == 64 for ln in lines))
check('manifest file inside the archive equals the returned text', content['MANIFEST.sha256'].decode() == manifest)
check('.sh files are mode 755, others 644',
      members['robot/start.sh'].mode == 0o755 and members['config/n.yaml'].mode == 0o644
      and members['delivery_core.py'].mode == 0o644)
check('line endings are copied byte for byte (CRLF .py stays, nothing added)',
      content['delivery_core.py'] == CRLF_PY and content['robot/start.sh'] == blobs['robot/start.sh'])
check('owner is numeric 0 (nothing from the laptop user leaks)',
      all(m.uid == 0 and m.gid == 0 for m in members.values()))
bad = os.path.join(d, 'robot', 'crlf.sh')
with open(bad, 'wb') as f:
    f.write(b'#!/bin/bash\r\necho hi\r\n')
try:
    deploy.build_archive(deploy.collect_files(d, t), ver, os.path.join(TMP, 'b.tar.gz'), 0)
    check('a .sh file with CRLF is refused', False)
except deploy.DeployError:
    check('a .sh file with CRLF is refused', True)
os.remove(bad)

# ---------------------------------------------------------------- dry run
rc, out, calls = run_deploy(['deploy', '--dry-run'])
check('dry run: exit 0 and the fake ssh/scp are never called', rc == 0 and calls == [], f'rc={rc} calls={len(calls)}')
check('dry run: names the release', 'release ' in out)
markers = ('pgrep -f delivery_mission.py', 'scp delivery-', 'tar -xzf', 'sha256sum -c', 'bash -n', 'py_compile',
           'mv -T delivery.new delivery', 'head -n -5')
order = [out.find(k) for k in markers]
check('dry run: remote steps appear in order', all(x >= 0 for x in order) and order == sorted(order), order)
check('dry run: scp target uses the IPv6 bracket form',
      f'ubuntu@[{HOST_V6.split("@")[1]}]:/tmp/delivery-' in out)
check('dry run: no sudo anywhere', 'sudo' not in out)
check('dry run: never writes to routes or logs', 'robot_code/routes' not in out and 'robot_code/logs' not in out)
check('dry run: releases go to ~/robot_code/delivery-releases and the link is delivery',
      'robot_code/delivery-releases/' in out and 'readlink delivery' in out)
check('dry run: local scp uses a bare file name (no Windows drive letter)',
      ' scp delivery-' in out and 'scp C:' not in out)

# ---------------------------------------------------------------- real run with fake ssh and scp
rc, out, calls = run_deploy(['deploy'])
steps = [step_of(c) for c in calls]
check('deploy: exit 0', rc == 0, out[-300:])
check('deploy: command order', steps == ['preflight', 'scp', 'unpack', 'verify', 'syntax', 'switch', 'prune', 'menu'], steps)
check('deploy: checksum check and syntax checks come before the symlink switch',
      steps.index('verify') < steps.index('syntax') < steps.index('switch'))
ssh_calls = [c for c in calls if c['tool'] == 'ssh']
check('ssh: plain IPv6 form (no brackets), key, batch mode, script on stdin via bash -s',
      all(HOST_V6 in c['args'] and c['args'][-2:] == ['bash', '-s'] and '-i' in c['args']
          and 'BatchMode=yes' in c['args'] for c in ssh_calls)
      and not any('[' in a for c in ssh_calls for a in c['args']))
scp_call = [c for c in calls if c['tool'] == 'scp'][0]
check('scp: IPv6 bracket form for the target',
      scp_call['args'][-1].startswith('ubuntu@[fe80::da3a:ddff:fe41:d5df%8]:/tmp/delivery-'), scp_call['args'][-1])
check('scp: local file is a bare name found in the working directory',
      scp_call['exists_in_cwd'] and os.sep not in scp_call['args'][-2] and '/' not in scp_call['args'][-2])
stdin_all = [c.get('stdin', '') for c in calls]
check('no script uses sudo or touches routes/logs',
      all('sudo' not in s and 'robot_code/routes' not in s and 'robot_code/logs' not in s for s in stdin_all))
check('scripts sent to bash have LF line endings only (no CR)', all('\r' not in s for s in stdin_all))
up = os.listdir(UPLOADS)
check('exactly one archive was uploaded', len(up) == 1 and up[0].endswith('.tar.gz'), up)
if up:
    mem, data = read_archive(os.path.join(UPLOADS, up[0]))
    check('real archive: timing tools under robot_tools/',
          'robot_tools/record_timing.py' in data and 'robot_tools/analyze_timing.py' in data)
    check('real archive: no __pycache__, .pyc or docs',
          not any('__pycache__' in n or n.endswith('.pyc') or n.startswith('docs/') for n in data))
    check('real archive: keeps config/upstream', any(n.startswith('config/upstream/') for n in data))
    man = data['MANIFEST.sha256'].decode().split('\n')
    check('real archive: VERSION and MANIFEST.sha256 present, manifest matches the bytes',
          'VERSION' in data and all(sha(data[x.split('  ', 1)[1]]) == x.split('  ', 1)[0] for x in man if x))
    rel_in_version = [x for x in data['VERSION'].decode().split('\n') if x.startswith('release=')][0][len('release='):]
    check('real archive: the release named in VERSION is the one the unpack script creates and scp uploads',
          rel_in_version in calls[2]['stdin'] and rel_in_version in scp_call['args'][-1], rel_in_version)
    check('real archive: every .sh is executable', all(m.mode == 0o755 for n, m in mem.items() if n.endswith('.sh')))

# ---------------------------------------------------------------- refusal while a mission runs
rc, out, calls = run_deploy(['deploy'], FAKE_MISSION='1')
check('mission running: exit 2, REFUSED, only the pgrep call (no upload, no switch)',
      rc == 2 and 'REFUSED' in out and [step_of(c) for c in calls] == ['preflight'], f'rc={rc}')
rc, out, calls = run_deploy(['deploy', '--force'], FAKE_MISSION='1')
st = [step_of(c) for c in calls]
check('mission running + --force: deploys without asking pgrep',
      rc == 0 and 'switch' in st and 'preflight' not in st, st)

# ---------------------------------------------------------------- failures never switch
for label, needle in (('checksum check', 'CHECKSUMS_OK'), ('syntax check', 'PY_COMPILE_OK'), ('unpack', 'UNPACKED')):
    rc, out, calls = run_deploy(['deploy'], FAKE_FAIL=needle)
    st = [step_of(c) for c in calls]
    check(f'{label} fails: exit 1, no switch, the new release is discarded',
          rc == 1 and 'switch' not in st and 'prune' not in st and st[-1] == 'discard', f'rc={rc} {st}')
rc, out, calls = run_deploy(['deploy'], FAKE_FAIL='SWITCHED')
check('switch fails: exit 1', rc == 1)

# ---------------------------------------------------------------- rollback and status
rc, out, calls = run_deploy(['rollback'])
st = [step_of(c) for c in calls]
check('rollback: checks for a mission, then repoints, then restarts the menu if installed', rc == 0
      and st == ['preflight', 'rollback', 'menu'], st)
scr = calls[1]['stdin'] if len(calls) > 1 else ''
check('rollback script: previous release, checksum check before an atomic switch, no sudo',
      'grep -B1 -x' in scr and 'sudo' not in scr and 'ln -sfn' in scr
      and scr.index('sha256sum -c') < scr.index('mv -T delivery.new delivery'))
menu_scr = calls[-1]['stdin']
check('menu restart script: only when enabled, never while a mission runs, user service without sudo',
      'systemctl --user is-enabled delivery-menu' in menu_scr and 'systemctl --user restart delivery-menu' in menu_scr
      and 'pgrep' in menu_scr and menu_scr.index('is-enabled') < menu_scr.index('restart delivery-menu')
      and 'sudo' not in menu_scr)
rc, out, calls = run_deploy(['rollback'], FAKE_MISSION='1')
check('rollback refused while a mission runs', rc == 2 and [step_of(c) for c in calls] == ['preflight'])
rc, out, calls = run_deploy(['status'])
scr = calls[-1]['stdin'] if calls else ''
check('status: one ssh call, read only, shows version, releases and manifest check',
      rc == 0 and len(calls) == 1 and 'VERSION' in scr and 'MANIFEST_MATCH' in scr and 'delivery-releases' in scr
      and not any(w in scr for w in ('ln -', 'mv ', 'rm ', 'mkdir')), scr)
rc, out, calls = run_deploy(['deploy', '--dry-run', '--host', 'ubuntu@[fe80::1%8]'])
check('--host with brackets: scp keeps the bracket form', 'ubuntu@[fe80::1%8]:/tmp/delivery-' in out and rc == 0)
rc, out, calls = run_deploy(['status', '--host', 'ubuntu@[fe80::1%8]'])
check('--host with brackets: ssh gets the plain form', bool(calls) and 'ubuntu@fe80::1%8' in calls[0]['args'])
rc, out, calls = run_deploy(['status', '--host', 'bad host; id'])
check('--host with shell characters is refused before any call', rc == 1 and calls == [])


# ---------------------------------------------------------------- the remote scripts in a real bash (optional)
def find_bash():
    for p in (r'C:\Program Files\Git\bin\bash.exe', r'C:\Program Files\Git\usr\bin\bash.exe'):
        if os.path.isfile(p):
            return p
    b = shutil.which('bash')
    return b if b and 'system32' not in b.lower() else None


def real_bash_tests():
    bash = find_bash()
    if not bash:
        print('SKIP remote scripts in bash: bash not found')
        return
    home = os.path.join(TMP, 'home')
    rr = os.path.join(home, 'robot_code')
    relroot = os.path.join(rr, 'delivery-releases')
    for sub in ('routes', 'logs'):
        os.makedirs(os.path.join(rr, sub))
        with open(os.path.join(rr, sub, 'keep.txt'), 'w') as f:
            f.write('keep\n')
    env = dict(os.environ, HOME=home, MSYS='winsymlinks:nativestrict')

    def sh(script):
        r = subprocess.run([bash, '-s'], input=script.encode(), capture_output=True, env=env, timeout=60)
        return r.returncode, r.stdout.decode(errors='replace') + r.stderr.decode(errors='replace')

    def live():
        return sh('readlink "$HOME/robot_code/delivery"')[1].strip()

    rc, o = sh('cd "$HOME/robot_code" && ln -sfn nowhere probe.lnk && [ -L probe.lnk ] && echo LNK')
    links = rc == 0 and 'LNK' in o
    if links:
        os.remove(os.path.join(rr, 'probe.lnk'))
    else:
        print('SKIP bash: switch, status and rollback scripts need symlinks, which this computer does not allow')
    rels = [f'2026110{i}T100000Z-abc123{i}' for i in range(1, 8)]
    for i, rel in enumerate(rels):
        rd = os.path.join(relroot, rel)
        os.makedirs(rd)
        with tarfile.open(arch) as tf:
            if sys.version_info >= (3, 12):
                tf.extractall(rd, filter='data')
            else:
                tf.extractall(rd)
        if i == 3:                                    # one release is damaged: a file differs from its manifest
            with open(os.path.join(rd, 'config', 'n.yaml'), 'w') as f:
                f.write('tampered\n')
    rc, o = sh(deploy.script_verify(rels[0]))
    check('bash: checksum check passes for an intact release', rc == 0 and 'CHECKSUMS_OK' in o, o)
    check('bash: checksum check fails for a tampered release', sh(deploy.script_verify(rels[3]))[0] != 0)
    rc, o = sh(deploy.script_syntax(rels[0]))
    if sh('python3 -c 1')[0] == 0:
        check('bash: syntax script passes (bash -n and py_compile)', rc == 0 and 'PY_COMPILE_OK' in o, o[-200:])
    else:
        check('bash: bash -n part of the syntax script passes', 'BASH_N_OK' in o, o[-200:])
    check('bash: syntax script left no __pycache__ in the release',
          not any('__pycache__' in dp for dp, _, _ in os.walk(os.path.join(relroot, rels[0]))))
    if links:
        rc, o = sh(deploy.script_switch(rels[4]))
        check('bash: switch repoints the symlink to the new release',
              rc == 0 and live() == 'delivery-releases/' + rels[4], o)
        check('bash: no temporary delivery.new link is left behind',
              not os.path.lexists(os.path.join(rr, 'delivery.new')))
        rc, o = sh(deploy.script_status())
        check('bash: status marks the live release and reports a manifest match',
              '* delivery-releases/' + rels[4] in o and 'MANIFEST_MATCH' in o, o)
        rc, o = sh(deploy.script_rollback())
        check('bash: rollback refuses a damaged previous release and leaves the live link alone',
              rc != 0 and live() == 'delivery-releases/' + rels[4], o)
        sh(deploy.script_switch(rels[6]))
        rc, o = sh(deploy.script_rollback())
        check('bash: rollback repoints to the previous release',
              rc == 0 and live() == 'delivery-releases/' + rels[5], o)
        sh(deploy.script_switch(rels[2]))
        sh(deploy.script_prune(1))
        left = sorted(os.listdir(relroot))
        check('bash: prune never removes the live release', rels[2] in left and rels[6] in left, left)
    else:
        rc, o = sh(deploy.script_prune(5))
        left = sorted(os.listdir(relroot))
        check('bash: prune keeps the newest 5 releases', rc == 0 and left == rels[2:], left)
    sh(deploy.script_discard(rels[6]))
    check('bash: discard removes just that release', not os.path.exists(os.path.join(relroot, rels[6])))
    keep = []
    for sub in ('routes', 'logs'):
        with open(os.path.join(rr, sub, 'keep.txt')) as f:
            keep.append(f.read())
    check('bash: routes and logs are untouched by every script', keep == ['keep\n', 'keep\n'])


real_bash_tests()

shutil.rmtree(TMP, ignore_errors=True)
print('ALL PASSED' if fails == 0 else f'{fails} FAILED')
sys.exit(1 if fails else 0)
