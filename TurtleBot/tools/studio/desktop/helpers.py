"""Small pure helpers: config folder, host checks, ssh/scp command lines, host keys, error texts.
No network or disk access beyond reading paths.
"""


from .config import *  # bundle: skip


def config_dir():
    env = os.environ.get('STUDIO_CONFIG_DIR')
    if env:
        return env
    if IS_WIN:
        return os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'TurtleBotStudio')
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support/TurtleBotStudio')
    return os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'turtlebot-studio')


def opt_path(p):
    """A path as ssh expects it inside -o Option=value: forward slashes, quoted if it has a space."""
    p = p.replace('\\', '/')
    return '"%s"' % p if ' ' in p else p


def strip_user(host):
    return host.split('@', 1)[1] if '@' in host else host


def valid_host(host):
    return isinstance(host, str) and bool(HOST_RE.match(strip_user(host.strip())))


def is_frozen():
    return bool(getattr(sys, 'frozen', False))


def self_argv(*args):
    """argv that runs Studio itself again (hidden helper modes): the frozen exe, or python + this file."""
    if is_frozen():
        return [sys.executable] + list(args)
    return [sys.executable, os.path.abspath(__file__)] + list(args)


def fake_bridge_argv(bridge_script):
    if is_frozen():
        return [sys.executable, '--_fake-bridge', '--fake']
    return [sys.executable, '-u', bridge_script, '--fake']


def key_fingerprint(line):
    """'SHA256:...' of an ssh public key line, same text as ssh-keygen -l; None if the line is not understood."""
    try:
        blob = base64.b64decode(line.split()[1], validate=True)
        return 'SHA256:' + base64.b64encode(hashlib.sha256(blob).digest()).decode('ascii').rstrip('=')
    except (IndexError, ValueError):
        return None


def parse_keyscan(text):
    """First 'type base64' key out of ssh-keyscan output (comment lines and the host column dropped), else None."""
    for ln in (text or '').splitlines():
        p = ln.split()
        if len(p) >= 3 and not ln.startswith('#') and KEY_LINE_RE.match(p[1] + ' ' + p[2]):
            return p[1] + ' ' + p[2]
    return None


def _fake_host_key():
    blob = b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20' + hashlib.sha256(b'turtlebot-studio fake robot').digest()
    return 'ssh-ed25519 ' + base64.b64encode(blob).decode('ascii')


FAKE_HOST_KEY = _fake_host_key()


def valid_psk(psk):
    """WPA2-personal passphrase: 8..63 printable ASCII characters, or exactly 64 hex digits."""
    if not isinstance(psk, str):
        return False
    if len(psk) == 64:
        return bool(re.match(r'^[0-9A-Fa-f]{64}$', psk))
    return 8 <= len(psk) <= 63 and all(' ' <= c <= '~' for c in psk)


def host_key_opts(known_hosts):
    return ['-o', 'HostKeyAlias=' + PIN_ALIAS, '-o', 'UserKnownHostsFile=' + opt_path(known_hosts),
            '-o', 'StrictHostKeyChecking=yes']


def build_bridge_ssh_argv(ssh_exe, host, key, known_hosts, user=ROBOT_USER):
    """The long-lived bridge process (spec section 1)."""
    return ([ssh_exe, '-T', '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3',
             '-o', 'ConnectTimeout=8'] + host_key_opts(known_hosts)
            + ['-i', key, '%s@%s' % (user, strip_user(host)), BOOT])


def build_ssh_argv(ssh_exe, host, key, known_hosts, remote_cmd=None, batch=True, tty=False, password_only=False,
                   connect_timeout=8, user=ROBOT_USER):
    """Generic ssh call (one-shot commands, terminals, setup_key)."""
    a = [ssh_exe]
    if tty:
        a.append('-t')
    elif remote_cmd is not None:
        a.append('-T')
    if batch:
        a += ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=%d' % connect_timeout, '-o', 'ServerAliveInterval=5',
              '-o', 'ServerAliveCountMax=3']
    a += host_key_opts(known_hosts)
    if password_only:
        a += ['-o', 'PubkeyAuthentication=no', '-o', 'PreferredAuthentications=password,keyboard-interactive']
    elif key:
        a += ['-i', key, '-o', 'IdentitiesOnly=yes']
    a.append('%s@%s' % (user, strip_user(host)))
    if remote_cmd is not None:
        a.append(remote_cmd)
    return a


def scp_target(host, user=ROBOT_USER):
    """scp/sftp need [addr] for IPv6 (incl. %scope); ssh does not."""
    host = strip_user(host)
    return '%s@[%s]:' % (user, host) if ':' in host else '%s@%s:' % (user, host)


def build_scp_argv(scp_exe, host, key, known_hosts, local, remote_path, upload=True, user=ROBOT_USER):
    a = [scp_exe, '-q', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8'] + host_key_opts(known_hosts)
    a += ['-i', key, '-o', 'IdentitiesOnly=yes']
    r = scp_target(host, user) + remote_path
    return a + ([local, r] if upload else [r, local])


def remote_path_expr(path):
    """Shell expression for a robot path: '~' and '~/x' stay expandable, the rest is quoted."""
    if path == '~':
        return '"$HOME"'
    if path.startswith('~/'):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


def map_ssh_error(text, code=None):
    """Map ssh stderr to (kind, short message). The UI offers 'Set up key login' for kind key_not_set_up."""
    t = text or ''
    low = t.lower()
    if 'permission denied (publickey' in low or 'permission denied, please try again' in low:
        return 'key_not_set_up', 'key not set up'
    if 'host key verification failed' in low or 'remote host identification has changed' in low:
        return 'host_key', 'robot key does not match the pinned key'
    if any(s in low for s in ('could not resolve', 'timed out', 'no route to host', 'network is unreachable',
                              'connection refused', 'connection closed by', 'connection reset', 'name or service not known',
                              'host is down', 'unreachable')):
        return 'unreachable', 'robot not reachable'
    if 'no such file or directory' in low and 'ssh' in low and 'identity' in low:
        return 'key_missing', 'key file not found'
    lines = [x.strip() for x in t.strip().splitlines() if x.strip()]
    return 'other', (lines[-1] if lines else 'connection ended (exit %s)' % code)
