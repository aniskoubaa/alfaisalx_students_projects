#!/usr/bin/env python3
"""Deploy TurtleBot/delivery to the robot as a numbered release, with checks before anything goes live.

Runs on the laptop (Windows, macOS or Linux). Python standard library only; it uses the system `ssh` and `scp`.
It never uses sudo and never touches ~/robot_code/routes or ~/robot_code/logs on the robot.

    python TurtleBot/delivery/tools/deploy.py deploy --dry-run     # show every step and remote command, change nothing
    python TurtleBot/delivery/tools/deploy.py deploy               # really deploy
    python TurtleBot/delivery/tools/deploy.py status               # what is live, and does it match its manifest
    python TurtleBot/delivery/tools/deploy.py rollback             # go back to the previous release

What `deploy` does, in this order (any failure stops it; the live version is only switched at the very end):
  1. pack TurtleBot/delivery (without __pycache__, *.pyc and docs; config/upstream is kept) plus
     TurtleBot/tools/timing/record_timing.py and analyze_timing.py (as robot_tools/) into a .tar.gz, with
     MANIFEST.sha256 (sha256 of every file) and VERSION (git sha, dirty flag, UTC time); .sh files get mode 755;
     line endings are kept exactly as they are in the working tree (no CRLF conversion, LF is enforced by
     TurtleBot/.gitattributes);
  2. refuse while a mission runs on the robot (pgrep -f delivery_mission.py), unless --force;
  3. upload to /tmp and unpack to ~/robot_code/delivery-releases/<UTC stamp>-<git sha>;
  4. check every file against MANIFEST.sha256 on the robot (sha256sum -c);
  5. `bash -n` on every .sh and `python3 -m py_compile` on every .py, on the robot;
  6. only then repoint the symlink ~/robot_code/delivery to the new release (ln -sfn + mv -T: atomic);
  7. keep the newest 5 releases (the live one is never removed);
  8. restart the front-panel menu service (robot/install_menu.sh) so it runs the new code, only when it is installed
     (systemctl --user is-enabled delivery-menu) and no mission runs. A running mission and the stack are not touched
     (KillMode=process); nothing happens when the service is not installed.
If step 3, 4 or 5 fails, the new release directory is removed and the live version is untouched.

Exit codes: 0 ok, 1 failure, 2 refused (mission running, docked-state checks are not part of this tool).
Host: ubuntu@fe80::da3a:ddff:fe41:d5df%8 (Ethernet link-local) by default. Write it with or without [brackets];
ssh gets the plain form and scp gets the bracket form `user@[addr]:path`, which it needs for IPv6.
"""
import argparse
import datetime as dt
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.dirname(HERE)                                   # TurtleBot/delivery
TURTLEBOT = os.path.dirname(DELIVERY)                              # TurtleBot
TIMING = os.path.join(TURTLEBOT, 'tools', 'timing')
TIMING_FILES = ('record_timing.py', 'analyze_timing.py')           # packed as robot_tools/<name>

DEFAULT_HOST = 'ubuntu@fe80::da3a:ddff:fe41:d5df%8'
DEFAULT_KEY = os.path.join('~', '.ssh', 'turtlebot4_ed25519')
KEEP_RELEASES = 5
EXCLUDE_DIRS = {'__pycache__', 'docs', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.git', 'routes', 'logs'}
EXCLUDE_SUFFIXES = ('.pyc', '.pyo', '.swp', '.tmp')
EXCLUDE_NAMES = {'.DS_Store', 'Thumbs.db', 'MANIFEST.sha256', 'VERSION'}
RELEASE_RE = re.compile(r'^\d{8}T\d{6}Z-[0-9a-z]+(-dirty)?$')
ROBOT_ROOT = '$HOME/robot_code'                                    # as written inside remote scripts
LOCAL_TIMEOUT = 20
EXIT_OK, EXIT_FAIL, EXIT_REFUSED = 0, 1, 2


class DeployError(Exception):
    pass


# ------------------------------------------------------------------ host handling
def split_host(host):
    """'user@addr%8', 'user@[addr%8]' or 'addr' -> (user or '', addr without brackets)."""
    user, _, addr = host.rpartition('@')
    addr = addr.strip()
    if addr.startswith('[') and addr.endswith(']'):
        addr = addr[1:-1]
    if not addr or any(c in addr for c in ' \t\'"`;&|<>$()'):
        raise DeployError(f'cannot understand --host {host!r}')
    return user, addr


def ssh_target(host):
    user, addr = split_host(host)
    return f'{user}@{addr}' if user else addr


def scp_target(host, remote_path):
    """scp needs [addr] around an IPv6 address, otherwise the colons are read as the end of the host name."""
    user, addr = split_host(host)
    shown = f'[{addr}]' if ':' in addr else addr
    return (f'{user}@' if user else '') + f'{shown}:{remote_path}'


# ------------------------------------------------------------------ packing
def collect_files(delivery_dir=DELIVERY, timing_dir=TIMING):
    """[(archive name, absolute path)] sorted by archive name. Excludes caches, docs, bytecode and the VERSION and
    MANIFEST files (those are generated)."""
    out = []
    for d, dirs, files in os.walk(delivery_dir):
        dirs[:] = sorted(x for x in dirs if x not in EXCLUDE_DIRS)
        for f in sorted(files):
            if f in EXCLUDE_NAMES or f.endswith(EXCLUDE_SUFFIXES):
                continue
            p = os.path.join(d, f)
            out.append((os.path.relpath(p, delivery_dir).replace(os.sep, '/'), p))
    for name in TIMING_FILES:
        p = os.path.join(timing_dir, name)
        if not os.path.isfile(p):
            raise DeployError(f'missing {p} (it is packed as robot_tools/{name})')
        out.append((f'robot_tools/{name}', p))
    out.sort()
    return out


def git_info(repo_dir=TURTLEBOT):
    """(short sha or 'nogit', dirty flag). Dirty = uncommitted or untracked changes under delivery/ or tools/timing."""
    def git(*a):
        r = subprocess.run(['git', '-C', repo_dir, *a], capture_output=True, text=True, timeout=LOCAL_TIMEOUT)
        if r.returncode != 0:
            raise OSError(r.stderr.strip())
        return r.stdout.strip()
    try:
        sha = git('rev-parse', '--short=7', 'HEAD').lower()
        dirty = bool(git('status', '--porcelain', '--', 'delivery', 'tools/timing'))
    except (OSError, subprocess.SubprocessError):
        return 'nogit', True
    return sha, dirty


def release_name(sha, utc_now, dirty=False):
    return utc_now.strftime('%Y%m%dT%H%M%SZ') + '-' + sha + ('-dirty' if dirty else '')


def version_text(release, sha, dirty, utc_now):
    return (f'release={release}\ngit_sha={sha}\ndirty={"true" if dirty else "false"}\n'
            f'built_utc={utc_now.strftime("%Y-%m-%dT%H:%M:%SZ")}\n')


def file_mode(arcname):
    return 0o755 if arcname.endswith('.sh') else 0o644


def build_archive(files, version, out_path, mtime):
    """Write out_path (.tar.gz) holding files + VERSION + MANIFEST.sha256. Bytes are copied as they are (no newline
    translation). Returns the manifest text. Raises DeployError if a .sh file has CRLF line endings."""
    entries = []
    for arc, path in files:
        with open(path, 'rb') as f:
            data = f.read()
        if arc.endswith('.sh') and b'\r\n' in data:
            raise DeployError(f'{arc} has CRLF line endings and would not run on the robot '
                              '(see TurtleBot/.gitattributes)')
        entries.append((arc, data))
    entries.append(('VERSION', version.encode('utf-8')))
    entries.sort()
    manifest = ''.join(f'{hashlib.sha256(d).hexdigest()}  {a}\n' for a, d in entries)
    entries.append(('MANIFEST.sha256', manifest.encode('utf-8')))
    with tarfile.open(out_path, 'w:gz', format=tarfile.GNU_FORMAT) as tf:
        for arc, data in entries:
            ti = tarfile.TarInfo(arc)
            ti.size, ti.mtime, ti.mode = len(data), mtime, file_mode(arc)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ''
            tf.addfile(ti, io.BytesIO(data))
    return manifest


# ------------------------------------------------------------------ remote scripts (sent to `bash -s` on stdin)
def check_release_name(rel):
    if not RELEASE_RE.match(rel):
        raise DeployError(f'bad release name {rel!r}')
    return rel


def script_preflight():
    return (
        'if pgrep -f delivery_mission.py >/dev/null 2>&1; then\n'
        '  echo "MISSION_RUNNING $(pgrep -f delivery_mission.py | tr \'\\n\' \' \')"\n'
        'else\n'
        '  echo MISSION_IDLE\n'
        'fi\n'
        f'mkdir -p "{ROBOT_ROOT}/delivery-releases"\n'
        'echo "HOST_OK $(hostname)"\n')


def script_unpack(rel):
    check_release_name(rel)
    return (
        'set -eu\n'
        f'R="{ROBOT_ROOT}/delivery-releases/{rel}"\n'
        '[ ! -e "$R" ] || { echo "release $R already exists"; exit 1; }\n'
        'mkdir -p "$R"\n'
        f'tar -xzf /tmp/delivery-{rel}.tar.gz -C "$R"\n'
        f'rm -f /tmp/delivery-{rel}.tar.gz\n'
        'echo UNPACKED\n')


def script_verify(rel):
    check_release_name(rel)
    return (
        'set -eu\n'
        f'cd "{ROBOT_ROOT}/delivery-releases/{rel}"\n'
        'sha256sum -c --quiet MANIFEST.sha256\n'
        'echo CHECKSUMS_OK\n')


def script_syntax(rel):
    check_release_name(rel)
    return (
        'set -eu\n'
        f'cd "{ROBOT_ROOT}/delivery-releases/{rel}"\n'
        "find . -name '*.sh' -print0 | xargs -0 -n1 bash -n\n"
        'echo BASH_N_OK\n'
        'PYTHONPYCACHEPREFIX="$(mktemp -d)"\n'
        'export PYTHONPYCACHEPREFIX\n'
        "find . -name '*.py' -print0 | xargs -0 python3 -m py_compile\n"
        'rm -rf "$PYTHONPYCACHEPREFIX"\n'
        'echo PY_COMPILE_OK\n')


def script_discard(rel):
    """Remove a half-installed release and its upload (only paths built from the validated release name)."""
    check_release_name(rel)
    return (f'rm -rf "{ROBOT_ROOT}/delivery-releases/{rel}"\n'
            f'rm -f /tmp/delivery-{rel}.tar.gz\n'
            'echo DISCARDED\n')


def script_switch(rel):
    check_release_name(rel)
    return (
        'set -eu\n'
        f'cd "{ROBOT_ROOT}"\n'
        'if [ -e delivery ] && [ ! -L delivery ]; then\n'
        f'  mv delivery "delivery.pre-deploy-{rel}"\n'
        '  echo "an existing plain directory delivery/ was moved aside"\n'
        'fi\n'
        f'ln -sfn "delivery-releases/{rel}" delivery.new\n'
        'mv -T delivery.new delivery\n'
        'echo "SWITCHED $(readlink delivery)"\n')


def script_prune(keep=KEEP_RELEASES):
    return (
        'set -u\n'
        f'cd "{ROBOT_ROOT}/delivery-releases"\n'
        'cur="$(basename "$(readlink ../delivery 2>/dev/null)" 2>/dev/null)"\n'
        f"ls -1d [0-9]*Z-* 2>/dev/null | sort | head -n -{keep} | while read -r r; do\n"
        '  if [ "$r" != "$cur" ]; then rm -rf -- "$r"; echo "removed old release $r"; fi\n'
        'done\n'
        'echo PRUNED\n')


def script_restart_menu():
    """Restart the delivery-menu user service after the symlink changed: only if it is enabled and no mission runs.
    Its own pgrep check also covers --force; the bracket in the pattern keeps it from matching its own shell."""
    return (
        'export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"\n'
        'if ! systemctl --user is-enabled delivery-menu >/dev/null 2>&1; then\n'
        '  echo "MENU_NOT_INSTALLED (nothing to restart)"\n'
        'elif pgrep -f "[d]elivery_mission.py" >/dev/null 2>&1; then\n'
        '  echo "MENU_KEPT a mission is running; restart the menu later: systemctl --user restart delivery-menu"\n'
        'elif systemctl --user restart delivery-menu; then\n'
        '  echo "MENU_RESTARTED"\n'
        'else\n'
        '  echo "MENU_RESTART_FAILED see: systemctl --user status delivery-menu"\n'
        'fi\n')


def script_rollback():
    return (
        'set -eu\n'
        f'cd "{ROBOT_ROOT}"\n'
        '[ -L delivery ] || { echo "ROLLBACK_IMPOSSIBLE delivery is not a symlink"; exit 1; }\n'
        'cur="$(basename "$(readlink delivery)")"\n'
        'prev="$(ls -1d delivery-releases/[0-9]*Z-* | sed \'s#.*/##\' | sort | grep -B1 -x -- "$cur" | head -n1)"\n'
        'if [ -z "$prev" ] || [ "$prev" = "$cur" ]; then\n'
        '  echo "ROLLBACK_IMPOSSIBLE no earlier release than $cur"; exit 1\n'
        'fi\n'
        '(cd "delivery-releases/$prev" && sha256sum -c --quiet MANIFEST.sha256)\n'
        'ln -sfn "delivery-releases/$prev" delivery.new\n'
        'mv -T delivery.new delivery\n'
        'echo "ROLLED_BACK_TO $prev (was $cur)"\n')


def script_status():
    return (
        f'cd "{ROBOT_ROOT}" || exit 1\n'
        'if [ -L delivery ]; then echo "current: $(readlink delivery)"; else echo "current: (no symlink)"; fi\n'
        'echo "--- VERSION"\n'
        'cat delivery/VERSION 2>/dev/null || echo "(no VERSION file)"\n'
        'echo "--- releases (* = live)"\n'
        'live="$(readlink delivery 2>/dev/null)"\n'
        'for r in $(ls -1d delivery-releases/[0-9]*Z-* 2>/dev/null | sort); do\n'
        '  if [ "$r" = "$live" ]; then echo "* $r"; else echo "  $r"; fi\n'
        'done\n'
        'echo "--- integrity"\n'
        'if (cd delivery 2>/dev/null && sha256sum -c --quiet MANIFEST.sha256 >/dev/null 2>&1); then\n'
        '  echo "MANIFEST_MATCH: every file equals the manifest"\n'
        'else\n'
        '  echo "MANIFEST_MISMATCH: a file differs, is missing, or there is no manifest"\n'
        'fi\n'
        'if pgrep -f delivery_mission.py >/dev/null 2>&1; then echo "mission: RUNNING"\n'
        'else echo "mission: not running"; fi\n')


# ------------------------------------------------------------------ running ssh and scp
class Remote:
    def __init__(self, host, key, dry_run, log=print):
        self.host, self.key, self.dry_run, self.log = host, os.path.expanduser(key), dry_run, log
        self.ssh_path = shutil.which('ssh')
        self.scp_path = shutil.which('scp')

    def _opts(self):
        o = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15']
        if self.key:
            o = ['-i', self.key, *o]
        return o

    def check_tools(self):
        if self.dry_run:
            return
        for name, path in (('ssh', self.ssh_path), ('scp', self.scp_path)):
            if not path:
                raise DeployError(f'`{name}` not found on this computer (install the OpenSSH client)')
        if self.key and not os.path.isfile(self.key):
            raise DeployError(f'ssh key {self.key} not found (use --key)')

    def run(self, title, script, timeout=120, check=True):
        """Send `script` to `bash -s` on the robot. Returns (returncode, stdout). Prints the script in a dry run."""
        self.log(f'--- remote: {title}')
        for line in script.rstrip('\n').split('\n'):
            self.log('    | ' + line)
        if self.dry_run:
            return 0, ''
        cmd = [self.ssh_path, *self._opts(), ssh_target(self.host), 'bash', '-s']
        try:
            r = subprocess.run(cmd, input=script.encode('utf-8'), capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise DeployError(f'{title}: timed out after {timeout} s') from None
        out = r.stdout.decode('utf-8', 'replace')
        err = r.stderr.decode('utf-8', 'replace')
        for line in out.rstrip('\n').split('\n') if out.strip() else []:
            self.log('    > ' + line)
        if r.returncode != 0:
            for line in err.rstrip('\n').split('\n') if err.strip() else []:
                self.log('    ! ' + line)
            if check:
                raise DeployError(f'{title} failed (exit {r.returncode})')
        return r.returncode, out

    def upload(self, local_path, remote_path, timeout=300):
        # run scp from the file's folder with a bare file name: a Windows path such as C:\x would read as host "C"
        folder, name = os.path.split(os.path.abspath(local_path))
        target = scp_target(self.host, remote_path)
        self.log(f'--- local: scp {name} -> {target}')
        if self.dry_run:
            return
        cmd = [self.scp_path, *self._opts(), name, target]
        try:
            r = subprocess.run(cmd, cwd=folder, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise DeployError(f'upload timed out after {timeout} s') from None
        if r.returncode != 0:
            raise DeployError('upload failed: ' + r.stderr.decode('utf-8', 'replace').strip())


# ------------------------------------------------------------------ commands
def mission_running(remote):
    _, out = remote.run('is a mission running?', script_preflight())
    return 'MISSION_RUNNING' in out


def cmd_deploy(a, remote, log=print):
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    sha, dirty = git_info()
    if dirty:
        if not a.allow_dirty:
            raise DeployError('the working tree has uncommitted changes under delivery/ and --no-allow-dirty was given')
        log('WARNING: deploying uncommitted changes (dirty working tree); the release name ends in -dirty')
    rel = release_name(sha, now, dirty)
    files = collect_files()
    log(f'release {rel}: {len(files)} files')
    keep_dir = a.keep
    tmp = tempfile.mkdtemp(prefix='tb4_deploy_')
    try:
        archive = os.path.join(keep_dir or tmp, f'delivery-{rel}.tar.gz')
        if keep_dir:
            os.makedirs(keep_dir, exist_ok=True)
        manifest = build_archive(files, version_text(rel, sha, dirty, now), archive, int(now.timestamp()))
        log(f'packed {archive} ({os.path.getsize(archive)} bytes), manifest has {manifest.count(chr(10))} lines')
        if a.dry_run:
            log('DRY RUN: nothing is sent; these are the remote commands that a real run would issue')
        remote.check_tools()
        if a.force:
            log('--force: not checking for a running mission')
            remote.run('prepare', 'mkdir -p "$HOME/robot_code/delivery-releases"\necho HOST_OK\n')
        elif mission_running(remote):
            log('REFUSED: delivery_mission.py is running on the robot. Stop it first, or use --force if you are sure.')
            return EXIT_REFUSED
        remote.upload(archive, f'/tmp/delivery-{rel}.tar.gz')
        try:
            remote.run('unpack', script_unpack(rel))
            remote.run('verify checksums', script_verify(rel))
            remote.run('syntax checks (bash -n, py_compile)', script_syntax(rel), timeout=180)
        except DeployError:
            log('the new release failed its checks; removing it. The live version was not changed.')
            try:
                remote.run('discard failed release', script_discard(rel), check=False)
            except DeployError:
                pass
            raise
        remote.run('switch the live symlink', script_switch(rel))
        remote.run(f'keep the newest {KEEP_RELEASES} releases', script_prune(KEEP_RELEASES), check=False)
        remote.run('restart the front-panel menu if it is installed', script_restart_menu(), check=False)
        log(f'DONE: ~/robot_code/delivery -> delivery-releases/{rel}' + ('  (dry run)' if a.dry_run else ''))
        return EXIT_OK
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_rollback(a, remote, log=print):
    remote.check_tools()
    if a.force:
        log('--force: not checking for a running mission')
    elif mission_running(remote):
        log('REFUSED: delivery_mission.py is running on the robot. Stop it first, or use --force if you are sure.')
        return EXIT_REFUSED
    remote.run('rollback to the previous release', script_rollback())
    remote.run('restart the front-panel menu if it is installed', script_restart_menu(), check=False)
    return EXIT_OK


def cmd_status(a, remote, log=print):
    remote.check_tools()
    remote.run('status', script_status(), check=False)
    return EXIT_OK


def make_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--host', default=DEFAULT_HOST,
                        help='[user@]address, with or without [brackets] around IPv6 (default %(default)s)')
    common.add_argument('--key', default=DEFAULT_KEY, help='ssh private key (default %(default)s)')
    common.add_argument('--dry-run', action='store_true', help='print every remote command, run none')
    common.add_argument('--force', action='store_true', help='do not refuse while a mission is running')
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0], epilog='See the top of this file for the steps.')
    sub = p.add_subparsers(dest='command', required=True)
    d = sub.add_parser('deploy', parents=[common], help='pack, upload, check and switch to a new release')
    d.add_argument('--allow-dirty', action=argparse.BooleanOptionalAction, default=True,
                   help='deploy uncommitted changes, with a warning (default on; --no-allow-dirty refuses)')
    d.add_argument('--keep', metavar='DIR', help='also keep the .tar.gz in DIR (default: temporary, deleted)')
    sub.add_parser('rollback', parents=[common], help='repoint ~/robot_code/delivery to the previous release')
    sub.add_parser('status', parents=[common], help='show the live version, the releases, and manifest match')
    return p


def main(argv=None):
    a = make_parser().parse_args(argv)
    try:
        split_host(a.host)
        remote = Remote(a.host, a.key, a.dry_run)
        return {'deploy': cmd_deploy, 'rollback': cmd_rollback, 'status': cmd_status}[a.command](a, remote)
    except DeployError as e:
        print(f'ERROR: {e}')
        return EXIT_FAIL
    except KeyboardInterrupt:
        print('interrupted; the live version is only changed by the last step, so it is unchanged unless that ran')
        return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
