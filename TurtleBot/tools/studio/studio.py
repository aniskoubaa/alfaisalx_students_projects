#!/usr/bin/env python3
"""TurtleBot Studio - desktop backend (ROADMAP TB-27).

Starts a small web server on 127.0.0.1 (random per-launch token), opens the browser UI in web/, and talks to
the lab TurtleBot 4 through ONE long-lived ssh process that streams robot_bridge.py to the robot at connect
time (nothing is installed on the robot). Python >= 3.10, standard library only, Windows / macOS / Linux.

Usage:
    python studio.py [--port 8765] [--no-browser] [--host-override ADDR] [--fake]

The app never stores, asks for, logs or sends a password. Password login happens only in a system terminal
that ssh itself opened (setup_key). Every ssh call checks the robot against a pinned host key.
See README.md for the architecture and the security model.
"""
import argparse
import base64
import collections
import concurrent.futures
import hashlib
import hmac
import http.server
import io
import ipaddress
import json
import os
import platform
import queue
import re
import secrets
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import zlib
import http.client

sys.dont_write_bytecode = True
VERSION = '2.1'
FROZEN = bool(getattr(sys, 'frozen', False))  # PyInstaller one-file build
HERE = getattr(sys, '_MEIPASS', None) if FROZEN else None
HERE = HERE or os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, 'web')

PIN_ALIAS = 'turtlebot4-lab'
LAB_HOST_KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINezwwah6HhR6o0ONkI77+B+XmFckK7JhQHI1Fn1nyBb'
PINNED_HOST_KEY = LAB_HOST_KEY  # old name, kept for importers
ROBOT_USER = 'ubuntu'
DEFAULT_SETTINGS = {'robot_hostname': 'turtlebot4', 'robot_user': ROBOT_USER, 'hotspot_ssid': 'Turtlebot4',
                    'hotspot_addr': '10.42.0.1', 'cable_addr': '192.168.185.3'}
LEGACY_TRUST_LABEL = 'Imported from settings'
WIFI_SECRET_TTL = 180   # s the bridge keeps a Wi-Fi password in memory
WIFI_JOIN_TIMEOUT = 45  # s nmcli may take to join
DNS_LABEL_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')
USER_RE = re.compile(r'^[a-z_][a-z0-9_-]{0,31}$')
NONCE_RE = re.compile(r'^[0-9a-f]{32}$')
DEFAULT_REMOTE_DIR = '~/robot_code'
BOOT = ("source /etc/turtlebot4/setup.bash >/dev/null 2>&1; exec python3 -u -c "
        "\"import sys;b=sys.stdin.buffer;n=int(b.readline());exec(compile(b.read(n).decode(),'robot_bridge','exec'))\"")
MOTION_FILES = ['drive_test.py', 'motion_shapes.py', 'motion_test.sh', 'more_shapes.py', 'wall_approach.py',
                'keep_distance.py', 'campaign.sh']
# '[m]' trick: pkill -f must not match the shell that carries this very command line.
MOTION_PKILL_REGEX = '|'.join('[%s]%s' % (n[0], re.escape(n[1:])) for n in MOTION_FILES)
PI_MAC_PREFIXES = ('D8:3A:DD', 'DC:A6:32', 'E4:5F:01', '28:CD:C1', 'B8:27:EB')
SYNC_SKIP_DIRS = ('__pycache__', '.git', 'logs')
SYNC_MAX_BYTES = 20 * 1024 * 1024
MARK_BEGIN = '# >>> TurtleBot Studio >>>'
MARK_END = '# <<< TurtleBot Studio <<<'
HOST_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:%\-]{0,200}$')
KEY_LINE_RE = re.compile(r'^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/=]{20,}$')
PUB_LINE_RE = re.compile(r'^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/=]{20,}( [A-Za-z0-9._@\-]+)?$')
IS_WIN = os.name == 'nt'
VERSION_RE = re.compile(r'^\d+(\.\d+){0,3}$')
UPDATE_PAGE_PREFIX = 'https://github.com/aniskoubaa/alfaisalx_students_projects/'
DEFAULT_UPDATE_PAGE = UPDATE_PAGE_PREFIX + 'blob/main/TurtleBot/tools/studio/INSTALL.md'
DEFAULT_UPDATE_URL = ('https://raw.githubusercontent.com/aniskoubaa/alfaisalx_students_projects/main/'
                      'TurtleBot/tools/studio/version.json')
UPDATE_EVERY = 24 * 3600        # s between automatic update checks
RECONNECT_DELAYS = (2, 4, 8, 15, 30)   # s before attempt 1, 2, ...; the last one repeats
RECONNECT_GIVE_UP = 600                # s after which automatic reconnecting stops
DEEP_MAX_TARGETS = 1024         # addresses the "Search the whole network" sweep may probe
DEEP_DEADLINE = 12.0            # s for the whole port-22 sweep
DEEP_CONNECT_TIMEOUT = 0.4      # s per TCP connect
DEEP_WORKERS = 64
DEEP_KEYSCAN_MAX = 24           # hosts whose identity is checked with ssh-keyscan
DEEP_KEYSCAN_PARALLEL = 8
CLOSE_GRACE = 45.0              # s without any open Studio page before the built app stops itself
WINDOW_MODES = ('app', 'browser')
DEFAULT_WINDOW_MODE = 'app'
UI_CHOICES = ('v2', 'classic')  # 2.0: which interface GET / serves; 'classic' is the 1.3 page (always also at /classic/)
TELEOP_MAX_LINEAR = 0.30        # m/s, same hard caps as robot_bridge.py (the bridge enforces them; Studio mirrors them)
TELEOP_MAX_ANGULAR = 1.20       # rad/s
TELEOP_MIN_LINEAR = 0.02
TELEOP_MIN_ANGULAR = 0.10
TELEOP_DEFAULT_LINEAR = 0.15
TELEOP_DEFAULT_ANGULAR = 0.60
HISTORY_KEEP_S = 1800           # s of 1 Hz metrics kept in memory
HISTORY_SERIES = ('battery_pct', 'voltage', 'current_a', 'speed', 'odom_hz', 'scan_hz', 'cpu_pct', 'temp_c', 'wifi_dbm')
ALERT_DEDUP_S = 60.0            # the same alert code is raised at most once per this many seconds
ALERT_EDGE_DEDUP_S = 2.0        # state changes (e-stop, dock, connection, programs, driving) only drop exact repeats
ALERT_EDGE_CODES = frozenset({'estop_on', 'estop_off', 'docked', 'undocked', 'teleop_armed', 'teleop_disarmed',
                              'conn_connected', 'conn_lost', 'conn_restored', 'conn_disconnected', 'program_started',
                              'program_exited', 'program_failed'})
ALERT_SEVERITIES = ('info', 'warn', 'critical')
EVENTS_MAX_BYTES = 1_000_000    # events.jsonl rotates to events.jsonl.old at this size

# ============================================================================ pure helpers


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


def norm_mac(mac):
    parts = re.split(r'[:\-]', (mac or '').strip())
    if len(parts) != 6:
        return None
    try:
        return ':'.join('%02X' % int(p, 16) for p in parts)
    except ValueError:
        return None


def mac_ok(mac):
    m = norm_mac(mac)
    return bool(m) and m[:8] in PI_MAC_PREFIXES


def parse_windows_neighbors(text):
    """Get-NetNeighbor ... | ConvertTo-Json (one object or a list). Returns link-local hosts of Raspberry Pi MACs."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for n in data if isinstance(data, list) else []:
        if not isinstance(n, dict):
            continue
        addr = str(n.get('IPAddress') or '')
        if not addr.lower().startswith('fe80') or not mac_ok(n.get('LinkLayerAddress')):
            continue
        if '%' not in addr and n.get('InterfaceIndex') is not None:
            addr += '%%%s' % n['InterfaceIndex']
        if addr not in out:
            out.append(addr)
    return out


def parse_ip6_neigh(text):
    """Linux `ip -6 neigh`: 'fe80::1 dev eth0 lladdr d8:3a:dd:.. REACHABLE'."""
    out = []
    for line in (text or '').splitlines():
        p = line.split()
        if len(p) < 5 or not p[0].lower().startswith('fe80') or 'lladdr' not in p or 'dev' not in p:
            continue
        mac = p[p.index('lladdr') + 1] if p.index('lladdr') + 1 < len(p) else ''
        if p[-1] in ('FAILED', 'INCOMPLETE') or not mac_ok(mac):
            continue
        h = '%s%%%s' % (p[0].split('%')[0], p[p.index('dev') + 1])
        if h not in out:
            out.append(h)
    return out


def parse_ndp(text):
    """macOS `ndp -an`: 'fe80::1%en5 d8:3a:dd:41:5:df en5 23h S R'."""
    out = []
    for line in (text or '').splitlines():
        p = line.split()
        if len(p) < 3 or not p[0].lower().startswith('fe80') or not mac_ok(p[1]):
            continue
        addr = p[0] if '%' in p[0] else '%s%%%s' % (p[0], p[2])
        if addr not in out:
            out.append(addr)
    return out


# ---- v1.3: "Search the whole network" (pure parts; the I/O is in deep_* below) ----
PRIVATE_V4 = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]


def private_v4(ip):
    """True for 10/8, 172.16/12 and 192.168/16 (loopback 127/8 and link-local 169.254/16 are not)."""
    try:
        a = ipaddress.IPv4Address(str(ip).strip())
    except ValueError:
        return False
    return any(a in n for n in PRIVATE_V4)


def _prefix_from_mask(mask):
    """'255.255.255.0' or '0xffffff00' -> 24, else None."""
    try:
        n = int(mask, 16) if mask.lower().startswith('0x') else int(ipaddress.IPv4Address(mask))
    except ValueError:
        return None
    bits = bin(n).count('1')
    return bits if n == (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF else None


def parse_win_ipv4(text):
    """Get-NetIPAddress -AddressFamily IPv4 | Select IPAddress,PrefixLength,InterfaceAlias | ConvertTo-Json."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for n in data if isinstance(data, list) else []:
        if not isinstance(n, dict):
            continue
        ip, pre = str(n.get('IPAddress') or ''), n.get('PrefixLength')
        if isinstance(pre, int) and 0 < pre <= 32 and re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
            out.append({'ip': ip, 'prefix': pre, 'name': str(n.get('InterfaceAlias') or '')})
    return out


def parse_ip4_addr(text):
    """Linux `ip -4 -o addr`: '2: eth0    inet 192.168.1.5/24 brd 192.168.1.255 scope global eth0'."""
    out = []
    for line in (text or '').splitlines():
        m = re.match(r'^\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)', line.strip())
        if m and 0 < int(m.group(3)) <= 32:
            out.append({'ip': m.group(2), 'prefix': int(m.group(3)), 'name': m.group(1)})
    return out


def parse_ifconfig(text):
    """macOS `ifconfig`: 'en0: flags=...' then '\tinet 192.168.1.5 netmask 0xffffff00 broadcast ...'."""
    out, dev = [], ''
    for line in (text or '').splitlines():
        m = re.match(r'^([A-Za-z0-9_.-]+):\s+flags=', line)
        if m:
            dev = m.group(1)
            continue
        m = re.match(r'^\s+inet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(\S+)', line)
        if m:
            pre = _prefix_from_mask(m.group(2))
            if pre:
                out.append({'ip': m.group(1), 'prefix': pre, 'name': dev})
    return out


def sweep_targets(ifaces, cap=DEEP_MAX_TARGETS):
    """Addresses to probe: per private interface the /24 around this computer's address (the real subnet when its
    prefix is longer than /24), minus this computer's own addresses, at most `cap` in total."""
    own = {i['ip'] for i in ifaces}
    out, seen = [], set()
    for i in ifaces:
        if not private_v4(i['ip']) or not 0 < i['prefix'] < 31:
            continue
        net = ipaddress.ip_network((i['ip'], max(i['prefix'], 24)), strict=False)
        for h in net.hosts():
            s = str(h)
            if s in own or s in seen:
                continue
            seen.add(s)
            out.append(s)
            if len(out) >= cap:
                return out
    return out


def _neigh_entry(ip, mac):
    m = norm_mac(mac)
    if not m or m in ('00:00:00:00:00:00', 'FF:FF:FF:FF:FF:FF') or int(m[:2], 16) & 1 or not private_v4(ip):
        return None
    return {'ip': ip, 'mac': m, 'pi': mac_ok(m)}


def parse_win_neigh4(text):
    """Get-NetNeighbor -AddressFamily IPv4 | Select IPAddress,LinkLayerAddress | ConvertTo-Json."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for n in data if isinstance(data, list) else []:
        e = _neigh_entry(str(n.get('IPAddress') or ''), n.get('LinkLayerAddress')) if isinstance(n, dict) else None
        if e and all(x['ip'] != e['ip'] for x in out):
            out.append(e)
    return out


def parse_ip4_neigh(text):
    """Linux `ip -4 neigh`: '192.168.1.1 dev eth0 lladdr d8:3a:dd:41:05:df REACHABLE'."""
    out = []
    for line in (text or '').splitlines():
        p = line.split()
        if len(p) < 5 or 'lladdr' not in p or p[-1] in ('FAILED', 'INCOMPLETE') or p.index('lladdr') + 1 >= len(p):
            continue
        e = _neigh_entry(p[0], p[p.index('lladdr') + 1])
        if e and all(x['ip'] != e['ip'] for x in out):
            out.append(e)
    return out


def parse_arp_an(text):
    """macOS `arp -an`: '? (192.168.1.1) at d8:3a:dd:41:5:df on en0 ifscope [ethernet]'."""
    out = []
    for line in (text or '').splitlines():
        m = re.search(r'\((\d+\.\d+\.\d+\.\d+)\) at ([0-9A-Fa-f:]+) ', line + ' ')
        e = _neigh_entry(m.group(1), m.group(2)) if m else None
        if e and all(x['ip'] != e['ip'] for x in out):
            out.append(e)
    return out


def order_deep(cands):
    """Confirmed robots first, then Raspberry Pi devices with ssh, then other ssh devices; inside a group by address."""
    def key(c):
        try:
            n = int(ipaddress.IPv4Address(c['host']))
        except ValueError:
            n = 0
        return (0 if c.get('identity') == 'confirmed' else 1 if c.get('pi') else 2, n)
    return sorted(cands, key=key)


ROUTE_WORDS = {'cable': 'Ethernet cable', 'wifi': 'Wi-Fi', 'hotspot': 'robot hotspot', 'custom': 'typed address'}


def route_words(via):
    """How the robot is reached, in words for people (the internal names are cable, wifi, hotspot, custom)."""
    return ROUTE_WORDS.get(via, via) if via else via


# ---- v1.3: update notice, reconnect timing, diagnostics redaction ----
def version_tuple(v):
    """'1.3' -> (1, 3); None when it is not a plain dotted number."""
    v = str(v or '').strip()
    return tuple(int(x) for x in v.split('.')) if VERSION_RE.match(v) else None


def version_newer(latest, current):
    """Numeric compare (1.10 > 1.9, 1.3 == 1.3.0). False when either side is not understood."""
    a, b = version_tuple(latest), version_tuple(current)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def parse_update_info(raw):
    """version.json text/bytes -> {'version','page','notes'} or None. The page must be on the lab's GitHub repo,
    else the default page is used; notes are cut to 300 plain characters."""
    try:
        d = json.loads(raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw)
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get('version'), str) or not VERSION_RE.match(d['version'].strip()):
        return None
    page = d.get('page')
    if not (isinstance(page, str) and page.startswith(UPDATE_PAGE_PREFIX) and page.isprintable() and ' ' not in page):
        page = DEFAULT_UPDATE_PAGE
    notes = d.get('notes')
    notes = ''.join(c if c.isprintable() else ' ' for c in notes).strip()[:300] if isinstance(notes, str) else ''
    return {'version': d['version'].strip(), 'page': page, 'notes': notes}


def reconnect_delay(attempt, delays=RECONNECT_DELAYS):
    """Seconds to wait before attempt number `attempt` (1, 2, 3, ...): 2, 4, 8, 15, 30, 30, ..."""
    return delays[min(max(attempt, 1) - 1, len(delays) - 1)]


def gave_up_text(seconds):
    if seconds >= 60 and seconds % 60 == 0:
        return 'gave up reconnecting after %d minutes' % (seconds // 60)
    return 'gave up reconnecting after %g seconds' % seconds


REDACTED = '[redacted]'
_SECRET_WORDS = r'(?:psk|passwords?|passwd|passphrase|wifi[_ -]?pass(?:word)?|secret)'
_RE_PEM = re.compile(r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)', re.S)
_RE_JSON_SECRET = re.compile(r'("?' + _SECRET_WORDS + r'"?\s*[:=]\s*)"(?:[^"\x5c]|\x5c.)*"', re.I)
_RE_SECRET = re.compile(r'(\b' + _SECRET_WORDS + r'\b"?\s*[:=])(?!\s*"?\[redacted)(\s*)[^\r\n]+', re.I)
_RE_TOKEN = re.compile(r'(\btoken\b"?\s*[:=]\s*)"?[^\s"&,;]+"?', re.I)


def redact(text, secrets=()):
    """Remove what must never leave this computer in a diagnostics text: the session token (also as token=...),
    psk/password/passphrase values and PEM private key blocks. `secrets` are exact strings to blank out too."""
    t = text or ''
    for s in secrets:
        if s and len(s) >= 4:
            t = t.replace(s, REDACTED)
    t = _RE_PEM.sub('[redacted private key]', t)
    t = _RE_JSON_SECRET.sub(lambda m: m.group(1) + '"' + REDACTED + '"', t)
    t = _RE_SECRET.sub(lambda m: m.group(1) + m.group(2) + REDACTED, t)
    t = _RE_TOKEN.sub(lambda m: m.group(1) + REDACTED, t)
    return t


def ssh_config_block(host, key, known_hosts, alias='turtlebot-studio', user=ROBOT_USER):
    lines = [MARK_BEGIN, 'Host ' + alias, '    HostName ' + strip_user(host), '    User ' + user,
             '    IdentityFile ' + opt_path(key), '    IdentitiesOnly yes', '    HostKeyAlias ' + PIN_ALIAS,
             '    UserKnownHostsFile ' + opt_path(known_hosts), '    StrictHostKeyChecking yes', MARK_END]
    return '\n'.join(lines) + '\n'


def insert_ssh_config_block(existing, block):
    """Add-only: append the marked block, or (only if it exists) replace our own marked block. Everything
    outside the markers is returned byte-identical. Returns (new_text, action) with action in
    'added' | 'unchanged' | 'updated'."""
    b = existing.find(MARK_BEGIN)
    e = existing.find(MARK_END, b + 1) if b >= 0 else -1
    if b >= 0 and e >= 0:
        e_end = e + len(MARK_END)
        if existing[e_end:e_end + 1] == '\n':
            e_end += 1
        if existing[b:e_end] == block:
            return existing, 'unchanged'
        return existing[:b] + block + existing[e_end:], 'updated'
    sep = '' if (not existing or existing.endswith('\n\n')) else ('\n' if existing.endswith('\n') else '\n\n')
    return existing + sep + block, 'added'


def should_skip_local(rel_parts, name):
    return any(p in SYNC_SKIP_DIRS for p in rel_parts[:-1]) or name.endswith('.pyc')


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def scan_local(root, with_sha=True):
    """{'rel/posix/path': {'size','mtime','sha1'}} - skips __pycache__, .git, logs/, *.pyc, files > 20 MB."""
    out = {}
    root = os.path.abspath(root)
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SYNC_SKIP_DIRS]
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            if fn.endswith('.pyc'):
                continue
            try:
                st = os.stat(full)
                if st.st_size > SYNC_MAX_BYTES or not os.path.isfile(full):
                    continue
                out[rel] = {'size': st.st_size, 'mtime': st.st_mtime, 'sha1': sha1_file(full) if with_sha else None}
            except OSError:
                continue
    return out


def plan_sync(local, remote, direction):
    """local/remote: {rel: {'size','sha1'}} (remote sha1 may be None for big files). Returns a plan dict.
    'transfer' = files to send in the given direction (new or changed); 'extra' = files only on the receiving side."""
    def same(a, b):
        if a.get('sha1') and b.get('sha1'):
            return a['sha1'] == b['sha1']
        return a.get('size') == b.get('size')
    src, dst = (local, remote) if direction == 'up' else (remote, local)
    new, changed, same_n = [], [], 0
    for rel in sorted(src):
        if rel not in dst:
            new.append(rel)
        elif same(src[rel], dst[rel]):
            same_n += 1
        else:
            changed.append(rel)
    extra = sorted(r for r in dst if r not in src)
    return {'new': new, 'changed': changed, 'same': same_n, 'transfer': new + changed, 'extra': extra}


def tar_mode(rel):
    return 0o755 if rel.endswith(('.py', '.sh')) else 0o644


def safe_member_path(dest, name):
    """Destination path for a tar member, or None if it would escape dest."""
    if not name or name.startswith('/') or '\\' in name or re.match(r'^[A-Za-z]:', name):
        return None
    parts = name.split('/')
    if any(p in ('..', '') for p in parts if p != '.'):
        return None
    parts = [p for p in parts if p != '.']
    if not parts:
        return None
    full = os.path.abspath(os.path.join(dest, *parts))
    root = os.path.abspath(dest)
    return full if full.startswith(root + os.sep) else None


def extract_tar_stream(fileobj, dest):
    """Extract regular files from a tar stream into dest (no links, no devices, no escapes). Returns names."""
    got = []
    with tarfile.open(fileobj=fileobj, mode='r|') as tf:
        for m in tf:
            if not m.isreg():
                continue
            target = safe_member_path(dest, m.name)
            if target is None:
                raise ValueError('unsafe path in archive: %r' % m.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            src = tf.extractfile(m)
            with open(target, 'wb') as f:
                shutil.copyfileobj(src, f)
            got.append(m.name.lstrip('./'))
    return got


def write_tar_stream(fileobj, root, rels):
    with tarfile.open(fileobj=fileobj, mode='w|', format=tarfile.GNU_FORMAT) as tf:
        for rel in rels:
            def flt(ti, rel=rel):
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = ''
                ti.mode = tar_mode(rel)
                return ti
            tf.add(os.path.join(root, *rel.split('/')), arcname=rel, recursive=False, filter=flt)


def expand_remote(path, home):
    if path == '~':
        return home
    if path.startswith('~/'):
        return os.path.join(home, *path[2:].split('/'))
    return path


def find_exe(name):
    if IS_WIN:
        p = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'OpenSSH', name + '.exe')
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def hide_flags():
    if IS_WIN:
        return {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


# ============================================================================ v1.3 helpers: own window, single instance, exit when closed
def say(*parts):
    """print() that never fails: the windowed (no console) build has sys.stdout = None or a closed pipe."""
    try:
        if sys.stdout is not None:
            print(*parts, flush=True)
    except (OSError, ValueError, AttributeError):
        pass


def browser_candidates(system, env, home=''):
    """Edge/Chrome/Chromium programs to try, best first. system: 'win32' | 'darwin' | 'linux'. Pure."""
    if system == 'win32':
        out = []
        for var, rel in (('ProgramFiles(x86)', 'Microsoft\\Edge\\Application\\msedge.exe'),
                         ('ProgramFiles', 'Microsoft\\Edge\\Application\\msedge.exe'),
                         ('ProgramFiles', 'Google\\Chrome\\Application\\chrome.exe'),
                         ('ProgramFiles(x86)', 'Google\\Chrome\\Application\\chrome.exe'),
                         ('LOCALAPPDATA', 'Google\\Chrome\\Application\\chrome.exe'),
                         ('LOCALAPPDATA', 'Microsoft\\Edge\\Application\\msedge.exe')):
            base = env.get(var)
            if base:
                out.append(base.rstrip('\\/') + '\\' + rel)
        return out
    if system == 'darwin':
        apps = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                '/Applications/Chromium.app/Contents/MacOS/Chromium']
        if home:
            apps += [home.rstrip('/') + a for a in apps[:2]]
        return apps
    return ['microsoft-edge', 'microsoft-edge-stable', 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']


def app_window_argv(browser_exe, url, profile_dir):
    """argv that opens url as a bare app window (no tabs or address bar) with its own browser profile. Pure."""
    return [browser_exe, '--app=' + url, '--user-data-dir=' + profile_dir, '--no-first-run', '--no-default-browser-check']


def find_app_browser(system, env, exists=os.path.isfile, which=shutil.which, home=''):
    """First installed Edge/Chrome/Chromium, or None. exists/which are injectable for tests."""
    for c in browser_candidates(system, env, home):
        if system == 'linux':
            found = which(c)
            if found:
                return found
        elif exists(c):
            return c
    return None


def window_command(system, mode, url, profile_dir, env=None, exists=os.path.isfile, which=shutil.which, home=''):
    """argv of the app window to open, or None when the normal browser should be used instead. Pure."""
    if mode != 'app':
        return None
    exe = find_app_browser(system, os.environ if env is None else env, exists, which, home)
    return app_window_argv(exe, url, profile_dir) if exe else None


def open_window(url, mode, cfg_dir):
    """Open Studio in its own window (Edge/Chrome --app) or, failing that, the default browser. Returns 'app' | 'browser' | None."""
    system = 'win32' if IS_WIN else ('darwin' if sys.platform == 'darwin' else 'linux')
    argv = window_command(system, mode, url, os.path.join(cfg_dir, 'window'), home=os.path.expanduser('~'))
    if argv:
        try:
            kw = {'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {'start_new_session': True}
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
            return 'app'
        except OSError:
            pass
    try:
        return 'browser' if webbrowser.open(url) else None
    except Exception:
        return None


def instance_path(cfg_dir):
    return os.path.join(cfg_dir, 'instance.json')


def write_instance(cfg_dir, port, token):
    """Record this running Studio so a second start can reuse its window. The config folder is private to the user."""
    info = {'pid': os.getpid(), 'port': port, 'token': token, 'version': VERSION, 'started': int(time.time())}
    tmp = instance_path(cfg_dir) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(info, f)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, instance_path(cfg_dir))


def read_instance(cfg_dir):
    try:
        with open(instance_path(cfg_dir), encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get('port'), int) and isinstance(d.get('token'), str):
            return d
    except (OSError, ValueError):
        pass
    return None


def remove_instance(cfg_dir, pid=None):
    """Delete instance.json (only if it is ours when pid is given)."""
    d = read_instance(cfg_dir)
    if pid is not None and d is not None and d.get('pid') != pid:
        return
    try:
        os.remove(instance_path(cfg_dir))
    except OSError:
        pass


def instance_alive(info, timeout=2.0):
    """True when the recorded Studio still answers with its token. A stale file (dead process, port reused) gives False."""
    if not info:
        return False
    try:
        c = http.client.HTTPConnection('127.0.0.1', info['port'], timeout=timeout)
        try:
            c.request('GET', '/api/settings', headers={'X-Studio-Token': info['token']})
            r = c.getresponse()
            body = r.read(200000)
        finally:
            c.close()
        return r.status == 200 and bool(json.loads(body.decode('utf-8')).get('version'))
    except (OSError, ValueError, http.client.HTTPException):
        return False


def stored_window_mode(cfg_dir):
    try:
        with open(os.path.join(cfg_dir, 'settings.json'), encoding='utf-8') as f:
            m = json.load(f).get('window_mode')
        return m if m in WINDOW_MODES else DEFAULT_WINDOW_MODE
    except (OSError, ValueError, AttributeError):
        return DEFAULT_WINDOW_MODE


def resolve_exit_when_closed(exit_flag, stay_flag, frozen, fake):
    """--stay-open wins, then --exit-when-closed; otherwise on only in the built app (and not in --fake demos). Pure."""
    if stay_flag:
        return False
    if exit_flag:
        return True
    return bool(frozen and not fake)


class CloseWatcher:
    """Decides when to stop because every Studio page was closed: after at least one page was seen, `grace`
    seconds with none connected. tick() is called about twice a second with the number of open event streams."""

    def __init__(self, grace=CLOSE_GRACE):
        self.grace = grace
        self.seen = False
        self.empty_since = None

    def tick(self, clients, now):
        if clients > 0:
            self.seen = True
            self.empty_since = None
            return False
        if not self.seen:
            return False
        if self.empty_since is None:
            self.empty_since = now
        return now - self.empty_since >= self.grace


# ============================================================================ v1.1 helpers: catalog, laptop network, Wi-Fi scripts

PROTECTED_CONNECTIONS = ('netplan-wlan0-Turtlebot4', 'netplan-eth0', 'netplan-usb0')
TEMPLATE_NAME_RE = re.compile(r'^[A-Za-z0-9_\-]{1,80}\.(py|sh)$')

# Runs as root on the robot (via sudo python3 -c). Port of TurtleBot/setup/write_keyfile.py; the password arrives on
# stdin only. O_EXCL: never overwrites an existing profile.
KEYFILE_WRITER = r'''import os
import sys

path, ssid = sys.argv[1], sys.argv[2]
psk = sys.stdin.buffer.read().decode('utf-8')
BS = chr(92)


def esc(v):
    v = v.replace(BS, BS + BS).replace(chr(10), BS + 'n').replace(chr(9), BS + 't').replace(chr(13), BS + 'r')
    if v.startswith(' '):
        v = BS + 's' + v[1:]
    if v.endswith(' '):
        v = v[:-1] + BS + 's'
    return v


content = (
    "[connection]\n"
    "id=" + esc(ssid) + "\n"
    "type=wifi\n"
    "interface-name=wlan0\n"
    "autoconnect=true\n"
    "autoconnect-priority=10\n"
    "\n"
    "[wifi]\n"
    "mode=infrastructure\n"
    "ssid=" + esc(ssid) + "\n"
    "powersave=2\n"
    "\n"
    "[wifi-security]\n"
    "key-mgmt=wpa-psk\n"
    "psk=" + esc(psk) + "\n"
    "\n"
    "[ipv4]\n"
    "method=auto\n"
    "\n"
    "[ipv6]\n"
    "method=auto\n"
)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8', newline=chr(10)) as f:
    f.write(content)
os.chmod(path, 0o600)
'''

# Runs as the normal robot user: asks the Studio bridge (abstract unix socket, same machine) for the Wi-Fi password that
# Studio sent it a moment ago and writes it to stdout. argv[1] = nonce. The bridge only answers its own user (SO_PEERCRED);
# this side checks the same, so another local user cannot pose as the bridge and feed in a password.
WIFI_FETCH = r'''import os
import socket
import struct
import sys

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect('\0turtlebot-studio-wifi-' + sys.argv[1])
if struct.unpack('3I', s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3I')))[1] != os.getuid():
    sys.exit(3)
data = b''
while True:
    c = s.recv(256)
    if not c:
        break
    data += c
sys.stdout.buffer.write(data)
'''

# Runs as root, detached (setsid), started by the Wi-Fi add script. $1 = SSID (= connection id), $2 = nmcli wait seconds,
# $3 = status file (JSON, no secrets). Never touches eth0. On failure the profile it was asked to bring up is deleted
# (so the user can retry with the right password) and the network that was active before is brought back.
WIFI_JOIN_SCRIPT = r'''ssid=$1
wait=${2:-45}
status=${3:-/run/turtlebot-studio-wifi.json}
jesc() { printf '%s' "$1" | LC_ALL=C sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/\\t/g' | LC_ALL=C tr -d '\000-\037'; }
js() { printf '"%s"' "$(jesc "$1")"; }
put() {
    tmp="$status.tmp.$$"
    printf '{%s}\n' "$1" > "$tmp" && chmod 644 "$tmp" && mv -f "$tmp" "$status"
}
now() { date +%s; }
prev=$(nmcli -g GENERAL.CONNECTION device show wlan0 2>/dev/null | head -n 1)
if [ "$prev" = "--" ]; then prev=""; fi
put "\"state\":\"joining\",\"ssid\":$(js "$ssid"),\"prev\":$(js "$prev"),\"t\":$(now)"
reason="could not join (wrong password or out of range)"
if nmcli --wait "$wait" connection up id "$ssid" >/dev/null 2>&1; then
    addr=""
    n=0
    while [ "$n" -lt 20 ]; do
        addr=$(ip -4 -o addr show dev wlan0 2>/dev/null | awk '{print $4}' | head -n 1 | cut -d/ -f1)
        if [ -n "$addr" ]; then break; fi
        sleep 1
        n=$((n + 1))
    done
    if [ -n "$addr" ]; then
        put "\"state\":\"joined\",\"ssid\":$(js "$ssid"),\"ip\":$(js "$addr"),\"prev\":$(js "$prev"),\"t\":$(now)"
        exit 0
    fi
    reason="joined but got no IP address"
fi
nmcli connection down id "$ssid" >/dev/null 2>&1
removed=false
if [ "${ssid#netplan-}" = "$ssid" ] && nmcli connection delete id "$ssid" >/dev/null 2>&1; then removed=true; fi
fb=false
if [ -n "$prev" ] && [ "$prev" != "$ssid" ]; then
    if nmcli --wait 30 connection up id "$prev" >/dev/null 2>&1; then fb=true; fi
fi
put "\"state\":\"failed\",\"ssid\":$(js "$ssid"),\"reason\":$(js "$reason"),\"fallback\":$(js "$prev"),\"fallback_ok\":$fb,\"removed\":$removed,\"t\":$(now)"
exit 1
'''

# Robot-side script (bash). Arguments: $1 = base64(ssid UTF-8), $2 = safe file name, $3 = 1|0 connect now,
# $4 = nonce (optional), $5 = join timeout in seconds (optional, default 45).
# With a nonce the Wi-Fi password comes from Studio's bridge (memory to memory on this robot, see WIFI_FETCH) and the
# only thing typed here is the robot (sudo) password. Without a nonce the Wi-Fi password is read with read -rs. Either way
# it reaches the keyfile writer through a pipe from a shell builtin (never argv, environment or a file).
WIFI_ADD_SCRIPT = r'''#!/bin/bash
# TurtleBot Studio: save a Wi-Fi network on this robot (run in a terminal on the robot).
ssid=$(printf '%s' "$1" | base64 -d) || { echo "bad arguments"; exit 2; }
fname=$2
connect_now=$3
nonce=$4
join_wait=${5:-45}
file="/etc/NetworkManager/system-connections/$fname.nmconnection"
status_file=/run/turtlebot-studio-wifi.json
WRITER=$(cat <<'STUDIO_PY_EOF'
@@WRITER@@
STUDIO_PY_EOF
)
FETCH=$(cat <<'STUDIO_FETCH_EOF'
@@FETCH@@
STUDIO_FETCH_EOF
)
JOIN=$(cat <<'STUDIO_JOIN_EOF'
@@JOIN@@
STUDIO_JOIN_EOF
)
wait_enter() { echo; echo "Press Enter to close."; read -r _ignored || true; }
echo "== TurtleBot Studio: add a Wi-Fi network to this robot =="
echo "Network name (SSID): $ssid"
echo "This will, as the administrator (sudo):"
echo "  1. write the saved network to $file (readable by root only)"
echo "  2. set autoconnect on, priority 10, Wi-Fi power save off"
echo "  3. reload NetworkManager's connection files"
if [ "$connect_now" = "1" ]; then
    echo "  4. switch the robot to it and test it (if that fails the profile is removed again and the"
    echo "     robot goes back to the network it is on now)"
fi
echo "Nothing else is changed. The cable connection is never touched."
echo
if nmcli -g NAME connection show 2>/dev/null | grep -qxF -- "$ssid"; then
    echo "A saved network called this already exists on the robot. Nothing was changed."
    echo "To replace it, remove it first (Studio, Wi-Fi tab, Remove)."
    wait_enter; exit 1
fi
if [ -n "$nonce" ]; then
    echo "The Wi-Fi password was typed in Studio. Now sudo asks for the ROBOT password (the ubuntu user's), hidden."
    sudo -v || { echo "sudo failed. Nothing was changed."; wait_enter; exit 1; }
    pw=$(python3 -c "$FETCH" "$nonce") || { echo "Could not get the Wi-Fi password from Studio (it is kept for 3 minutes only,"; echo "and Studio must stay connected). Nothing was changed."; unset pw; wait_enter; exit 1; }
else
    printf 'Wi-Fi password for %s (typing is hidden): ' "$ssid"
    IFS= read -rs pw
    echo
fi
n=$(printf '%s' "$pw" | LC_ALL=C wc -c | tr -d ' ')
if [ "$n" -eq 64 ] && printf '%s' "$pw" | grep -qE '^[0-9A-Fa-f]{64}$'; then :
elif [ "$n" -lt 8 ] || [ "$n" -gt 63 ]; then
    echo "A WPA password has 8 to 63 characters. Nothing was changed."
    unset pw; wait_enter; exit 1
fi
if [ -z "$nonce" ]; then
    echo "Now sudo asks for the ROBOT password (the ubuntu user's), also hidden."
    sudo -v || { echo "sudo failed. Nothing was changed."; unset pw; wait_enter; exit 1; }
fi
if ! printf '%s' "$pw" | sudo python3 -c "$WRITER" "$file" "$ssid"; then
    echo "Writing the network failed. Nothing was changed (an existing file is never overwritten)."
    unset pw; wait_enter; exit 1
fi
unset pw
sudo nmcli connection reload || echo "reload failed"
echo
echo "Saved. NetworkManager reports (autoconnect, power save):"
nmcli -g connection.autoconnect,802-11-wireless.powersave connection show id "$ssid"
echo
echo "To undo:   sudo nmcli connection delete id $(printf '%q' "$ssid")"
if [ "$connect_now" = "1" ]; then
    echo
    sudo rm -f -- "$status_file"
    sudo setsid -f bash -c "$JOIN" studio-join "$ssid" "$join_wait" "$status_file" </dev/null >/dev/null 2>&1
    echo "The robot is switching to '$ssid' now (up to $join_wait s). This connection may drop: that is expected"
    echo "if you are on the robot's own hotspot. If the join fails the profile is removed and the robot returns"
    echo "to its previous network within about 1.5 minutes. Studio shows the result."
fi
wait_enter
'''

WIFI_REMOVE_SCRIPT = r'''#!/bin/bash
# TurtleBot Studio: remove a saved Wi-Fi network from this robot. $1 = base64(connection name).
name=$(printf '%s' "$1" | base64 -d) || { echo "bad arguments"; exit 2; }
wait_enter() { echo; echo "Press Enter to close."; read -r _ignored || true; }
case "$name" in
    netplan-wlan0-Turtlebot4|netplan-eth0|netplan-usb0)
        echo "'$name' is the robot's own hotspot / cable link. Not removed."; wait_enter; exit 1;;
esac
t=$(nmcli -g connection.type connection show id "$name" 2>/dev/null)
if [ "$t" != "802-11-wireless" ]; then
    echo "'$name' is not a saved Wi-Fi network on this robot. Nothing was changed."; wait_enter; exit 1
fi
echo "== TurtleBot Studio: remove the saved Wi-Fi network '$name' from this robot =="
if nmcli -g GENERAL.STATE connection show id "$name" 2>/dev/null | grep -q activated; then
    echo "WARNING: this network is in use now. Removing it can drop your connection."
fi
echo "Command: sudo nmcli connection delete id $(printf '%q' "$name")"
sudo nmcli connection delete id "$name"
echo "exit code: $?"
wait_enter
'''


def b64s(s):
    return base64.b64encode(s.encode('utf-8')).decode('ascii')


def valid_ssid(ssid):
    if not isinstance(ssid, str) or not ssid or '\n' in ssid or '\r' in ssid or '\x00' in ssid:
        return False
    return len(ssid.encode('utf-8')) <= 32


def safe_conn_filename(ssid):
    """ASCII file stem for /etc/NetworkManager/system-connections/<stem>.nmconnection (a hash is added if changed)."""
    stem = re.sub(r'[^A-Za-z0-9_\-]', '_', ssid)[:40] or 'wifi'
    if stem != ssid:
        stem += '-' + hashlib.sha1(ssid.encode('utf-8')).hexdigest()[:6]
    return 'studio-' + stem


def build_robot_script_cmd(script, *args):
    """Remote command: bash <(echo SCRIPT_B64 | base64 -d) <args>. Only [A-Za-z0-9+/=_-] occur in the
    variable parts, so no quoting is needed on any OS; bash reads the script from a file so stdin stays the terminal.
    With a script file bash sets $0 to the file, so the first argument here is $1 (unlike `bash -c`, which takes a
    $0 placeholder; an extra placeholder broke Add and Remove on the robot, 2026-10-24)."""
    for a in args:
        if not re.match(r'^[A-Za-z0-9+/=_\-]+$', a):
            raise ValueError('unsafe script argument')
    return 'bash <(echo %s | base64 -d) %s' % (b64s(script), ' '.join(args))


def wifi_add_script():
    return (WIFI_ADD_SCRIPT.replace('@@WRITER@@', KEYFILE_WRITER.rstrip('\n')).replace('@@FETCH@@', WIFI_FETCH.rstrip('\n'))
            .replace('@@JOIN@@', WIFI_JOIN_SCRIPT.rstrip('\n')))


def split_nmcli(line):
    """Split an `nmcli -t` line on unescaped ':' and unescape backslash sequences."""
    out, cur, i = [], '', 0
    while i < len(line):
        c = line[i]
        if c == '\\' and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if c == ':':
            out.append(cur)
            cur = ''
        else:
            cur += c
        i += 1
    out.append(cur)
    return out


def parse_netsh_wlan(text):
    """`netsh wlan show interfaces` (English). Returns {'ssid','signal_pct','state','interface'} or None."""
    ifs, cur = [], None
    for line in (text or '').splitlines():
        m = re.match(r'^\s*([^:]+?)\s*:\s*(.*?)\s*$', line)
        if not m:
            continue
        k, v = m.group(1).lower(), m.group(2)
        if k == 'name':
            cur = {'interface': v, 'ssid': None, 'state': None, 'signal_pct': None}
            ifs.append(cur)
        elif cur is None:
            continue
        elif k == 'ssid':
            cur['ssid'] = v or None
        elif k == 'state':
            cur['state'] = v
        elif k == 'signal' and v.rstrip('%').isdigit():
            cur['signal_pct'] = int(v.rstrip('%'))
    if not ifs:
        return None
    return next((i for i in ifs if (i['state'] or '').lower() == 'connected'), ifs[0])


def parse_netsh_profiles(text):
    return [m.group(1).strip() for m in re.finditer(r'^\s*All User Profile\s*:\s*(.+?)\s*$', text or '', re.M)]


def parse_nmcli_wifi(dev_text, wifi_text):
    """Linux: `nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev` + `nmcli -t -f ACTIVE,SSID,SIGNAL dev wifi`."""
    iface, state = None, None
    for line in (dev_text or '').splitlines():
        p = split_nmcli(line)
        if len(p) >= 3 and p[1] == 'wifi':
            iface, state = p[0], p[2]
            if state == 'connected':
                break
    if iface is None:
        return None
    ssid, sig = None, None
    for line in (wifi_text or '').splitlines():
        p = split_nmcli(line)
        if len(p) >= 3 and p[0] == 'yes':
            ssid = p[1] or None
            sig = int(p[2]) if p[2].isdigit() else None
            break
    return {'ssid': ssid, 'signal_pct': sig, 'state': state, 'interface': iface}


def parse_hardware_ports(text):
    """macOS `networksetup -listallhardwareports` -> [(port name, device)]."""
    out, name = [], None
    for line in (text or '').splitlines():
        if line.startswith('Hardware Port:'):
            name = line.split(':', 1)[1].strip()
        elif line.startswith('Device:') and name:
            out.append((name, line.split(':', 1)[1].strip()))
            name = None
    return out


def parse_mac_ssid(text):
    m = re.search(r'^\s*SSID\s*:\s*(.+?)\s*$', text or '', re.M)
    if m:
        return m.group(1)
    m = re.search(r'Current Wi-Fi Network:\s*(.+?)\s*$', text or '', re.M)
    return m.group(1) if m else None


def parse_ip_o4(text):
    """`ip -o -4 addr show` -> {dev: [ipv4]}."""
    out = {}
    for line in (text or '').splitlines():
        p = line.split()
        if len(p) >= 4 and p[2] == 'inet':
            out.setdefault(p[1], []).append(p[3].split('/')[0])
    return out


def parse_windows_wired(text):
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for n in data if isinstance(data, list) else []:
        if isinstance(n, dict) and n.get('name'):
            ip = n.get('ipv4') or []
            ip = [ip] if isinstance(ip, str) else [x for x in ip if isinstance(x, str)]
            out.append({'name': str(n['name']), 'up': bool(n.get('up')), 'ipv4': ip})
    return out


WIN_WIRED_PS = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "[System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | "
    "Where-Object { $_.NetworkInterfaceType -eq 'Ethernet' } | ForEach-Object { [pscustomobject]@{ name = $_.Name; "
    "up = ($_.OperationalStatus -eq 'Up'); ipv4 = @($_.GetIPProperties().UnicastAddresses | "
    "Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' } | ForEach-Object { $_.Address.IPAddressToString }) } } | "
    "ConvertTo-Json -Compress")


# Windows 11 hides the SSID from `netsh wlan` unless Location is on. The network profile name of the Wi-Fi
# adapter is usually the SSID (it can differ, for example "Name 2"), so it is offered as a guess to check.
WIN_WIFI_PROFILE_PS = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "$a = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.NdisPhysicalMedium -eq 9 } | Select-Object -First 1; "
    "if ($a) { $a.Name; (Get-NetConnectionProfile -InterfaceIndex $a.ifIndex).Name }")


def netsh_location_blocked(text):
    return 'location permission' in (text or '').lower()


def laptop_wifi():
    """Current Wi-Fi of this computer: {'ssid','signal_pct','state','interface'} or None. Never raises."""
    try:
        if IS_WIN:
            text = _run_quiet(['netsh', 'wlan', 'show', 'interfaces'], 3)
            if not netsh_location_blocked(text):
                return parse_netsh_wlan(text)
            ps = shutil.which('powershell') or 'powershell'
            lines = [x.strip() for x in _run_quiet([ps, '-NoProfile', '-NonInteractive', '-Command', WIN_WIFI_PROFILE_PS], 6).splitlines() if x.strip()]
            return {'ssid': lines[1] if len(lines) > 1 else None, 'signal_pct': None,
                    'state': 'connected' if len(lines) > 1 else 'unknown', 'interface': lines[0] if lines else None,
                    'ssid_guess': True,
                    'note': 'Windows hides the Wi-Fi name unless Location is on (Settings, Privacy & security, Location). '
                            'The name shown is the Windows network name; check it before adding it to the robot.'}
        if sys.platform == 'darwin':
            ports = parse_hardware_ports(_run_quiet(['networksetup', '-listallhardwareports'], 3))
            dev = next((d for n, d in ports if n in ('Wi-Fi', 'AirPort')), None)
            if not dev:
                return None
            ssid = parse_mac_ssid(_run_quiet(['ipconfig', 'getsummary', dev], 3)) or \
                parse_mac_ssid(_run_quiet(['networksetup', '-getairportnetwork', dev], 3))
            return {'ssid': ssid, 'signal_pct': None, 'state': 'connected' if ssid else 'disconnected', 'interface': dev}
        if shutil.which('nmcli'):
            return parse_nmcli_wifi(_run_quiet(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'dev'], 3),
                                    _run_quiet(['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL', 'dev', 'wifi'], 4))
    except Exception:
        pass
    return None


def laptop_wired():
    try:
        if IS_WIN:
            ps = shutil.which('powershell') or 'powershell'
            return parse_windows_wired(_run_quiet([ps, '-NoProfile', '-NonInteractive', '-Command', WIN_WIRED_PS], 6))
        if sys.platform == 'darwin':
            out = []
            for n, d in parse_hardware_ports(_run_quiet(['networksetup', '-listallhardwareports'], 3)):
                if re.search(r'wi-?fi|airport|bluetooth|bridge|iphone|ipad|vpn', n, re.I):
                    continue
                ip = _run_quiet(['ipconfig', 'getifaddr', d], 2).strip()
                out.append({'name': n, 'up': bool(ip), 'ipv4': [ip] if ip else []})
            return out
        ips = parse_ip_o4(_run_quiet(['ip', '-o', '-4', 'addr', 'show'], 3))
        out = []
        for d in sorted(os.listdir('/sys/class/net')):
            base = '/sys/class/net/' + d
            if d == 'lo' or os.path.isdir(base + '/wireless') or not os.path.exists(base + '/device'):
                continue
            try:
                with open(base + '/operstate') as f:
                    up = f.read().strip() == 'up'
            except OSError:
                up = False
            out.append({'name': d, 'up': up, 'ipv4': ips.get(d, [])})
        return out
    except Exception:
        return []


def list_templates(templates_dir):
    try:
        return sorted(n for n in os.listdir(templates_dir)
                      if TEMPLATE_NAME_RE.match(n) and os.path.isfile(os.path.join(templates_dir, n)))
    except OSError:
        return []


def load_catalog(path, templates_dir):
    """programs.json + templates/ -> dict for GET /api/catalog. Missing or broken files give an empty catalog."""
    out = {'ok': True, 'version': 1, 'programs': {}, 'templates': [], 'catalog_found': False}
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get('programs'), dict):
            out['programs'] = d['programs']
            out['version'] = d.get('version', 1)
            out['catalog_found'] = True
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        out['error'] = 'programs.json could not be read: %s' % e
    for n in list_templates(templates_dir):
        out['templates'].append({'name': n, 'entry': out['programs'].get(n)})
    return out


def decide_motion(base, catalog_programs, user_files, described):
    """Motion decision for `run`. described: the bridge `describe` entry for the file, 'unavailable' if describe
    failed, or None if the file was not listed. Returns (motion, reasons)."""
    reasons = []
    if base in MOTION_FILES:
        reasons.append('known motion program')
    if base in (user_files or []):
        reasons.append('marked as moving in settings')
    ent = catalog_programs.get(base) if isinstance(catalog_programs, dict) else None
    if isinstance(ent, dict) and ent.get('moves'):
        reasons.append('catalog says it moves the robot')
    if isinstance(described, dict) and described.get('moves_detected'):
        reasons.append('code uses motion topics/actions: %s' % ', '.join(map(str, described.get('moves_reasons') or [])))
    if described == 'unavailable' and not isinstance(ent, dict) and not reasons:
        reasons.append('unknown file and the robot could not check it (treated as moving)')
    return bool(reasons), reasons


# ============================================================================ event bus


class Bus:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = set()
        self.last_conn = {'ev': 'conn', 'state': 'disconnected', 'host': None, 'via': None, 'error': None}
        self.last_status = None
        self.last_hello = None  # a page opened later still learns the robot's name and ROS version
        self.logs = collections.deque(maxlen=200)
        self.tap = None         # 2.0: optional callable(ev) that sees every published event (alerts); must not raise

    def publish(self, ev):
        self._publish(ev)
        tap = self.tap
        if tap is not None:
            try:
                tap(ev)
            except Exception:
                pass

    def _publish(self, ev):
        with self.lock:
            if ev.get('ev') == 'conn':
                self.last_conn = ev
                if ev.get('state') in ('disconnected', 'error', 'connecting', 'discovering'):
                    self.last_hello = None
            elif ev.get('ev') == 'hello':
                self.last_hello = ev
            elif ev.get('ev') == 'status':
                self.last_status = ev
            elif ev.get('ev') == 'log':
                self.logs.append(ev)
            for q in list(self.clients):
                try:
                    q.put_nowait(ev)
                except queue.Full:
                    self.clients.discard(q)

    def subscribe(self):
        q = queue.Queue(maxsize=2000)
        with self.lock:
            pre = [self.last_conn] + ([self.last_hello] if self.last_hello else []) +                   ([self.last_status] if self.last_status else []) + list(self.logs)
            for ev in pre:
                q.put_nowait(ev)
            self.clients.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients.discard(q)

    def count(self):
        with self.lock:
            return len(self.clients)

    def close_all(self):
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass


# ============================================================================ 2.0: history and alerts


def finite_num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float('inf') else None


def history_sample(ev):
    """One status event -> the plotted numbers (None where the robot did not report one)."""
    g = lambda k: ev.get(k) if isinstance(ev.get(k), dict) else {}
    b, o, sc, sy, net = g('battery'), g('odom'), g('scan'), g('system'), g('net')
    vx = finite_num(o.get('vx'))
    return {'battery_pct': finite_num(b.get('percent')), 'voltage': finite_num(b.get('voltage')),
            'current_a': finite_num(b.get('current_a')), 'speed': None if vx is None else round(abs(vx), 3),
            'odom_hz': finite_num(o.get('rate_hz')), 'scan_hz': finite_num(sc.get('rate_hz')),
            'cpu_pct': finite_num(sy.get('cpu_pct')), 'temp_c': finite_num(sy.get('temp_c')),
            'wifi_dbm': finite_num(net.get('signal_dbm'))}


def clamp_minutes(v, default=15.0):
    m = finite_num(v)
    return default if m is None else min(HISTORY_KEEP_S / 60.0, max(1.0, m))


class History:
    """Metrics from the robot's status events, at most one sample per second, the newest HISTORY_KEEP_S seconds."""

    def __init__(self, keep=HISTORY_KEEP_S):
        self.rows = collections.deque(maxlen=int(keep))
        self.lock = threading.Lock()

    def add(self, ev, now=None):
        now = time.time() if now is None else now
        with self.lock:
            if self.rows and now - self.rows[-1][0] < 0.9:
                return False
            self.rows.append((now, history_sample(ev)))
            return True

    def query(self, minutes=15, now=None):
        now = time.time() if now is None else now
        cut = now - clamp_minutes(minutes) * 60.0
        with self.lock:
            rows = [r for r in self.rows if r[0] >= cut]
        return {'t': [round(t, 1) for t, _ in rows], 'series': {k: [smp.get(k) for _, smp in rows] for k in HISTORY_SERIES}}


class AlertCenter:
    """Alerts with severity, de-duplicated per code, kept in memory and in <config>/events.jsonl (rotated at max_bytes,
    one old file kept). Conditions are edge-triggered: an alert is raised when a condition starts and an info alert when it
    ends. publish(ev) is called with {'ev': 'alert', ...} for every alert that is kept."""

    def __init__(self, path, publish, clock=time.time, max_bytes=EVENTS_MAX_BYTES, keep=500):
        self.path, self.publish, self.clock, self.max_bytes = path, publish, clock, max_bytes
        self.lock = threading.RLock()
        self.items = collections.deque(maxlen=keep)
        self.last_t = {}
        self.next_id = 1
        self.active = {}
        self.batt_level = 0
        self.prev_docked = None
        self.prev_estop = None
        self.lidar_bad_since = None
        self._load()

    def _load(self):
        for fn in (self.path + '.old', self.path):
            try:
                with open(fn, encoding='utf-8') as f:
                    for line in f:
                        try:
                            a = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(a, dict) and isinstance(a.get('id'), int) and a.get('severity') in ALERT_SEVERITIES:
                            self.items.append({k: a.get(k) for k in ('id', 't', 'severity', 'code', 'text')})
                            self.next_id = max(self.next_id, a['id'] + 1)
            except OSError:
                pass

    def raise_alert(self, code, severity, text):
        """Returns the alert dict, or None when the same code was already raised recently."""
        now = self.clock()
        window = ALERT_EDGE_DEDUP_S if code in ALERT_EDGE_CODES else ALERT_DEDUP_S
        with self.lock:
            last = self.last_t.get(code)
            if last is not None and 0 <= now - last < window:
                return None
            self.last_t[code] = now
            a = {'id': self.next_id, 't': round(now, 3), 'severity': severity if severity in ALERT_SEVERITIES else 'info',
                 'code': str(code), 'text': str(text)[:300]}
            self.next_id += 1
            self.items.append(a)
            self._persist(a)
        try:
            self.publish(dict(a, ev='alert'))
        except Exception:
            pass
        return a

    def _persist(self, a):
        try:
            try:
                if os.path.getsize(self.path) >= self.max_bytes:
                    os.replace(self.path, self.path + '.old')
            except OSError:
                pass
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(a) + '\n')
        except OSError:
            pass

    def since(self, since_id=0, limit=500):
        with self.lock:
            out = [dict(a) for a in self.items if a['id'] > since_id]
            last = self.next_id - 1
        return out[-limit:], last

    def _cond(self, code, active, severity, text, clear_text):
        was = self.active.get(code, False)
        if active and not was:
            self.active[code] = True
            self.raise_alert(code, severity, text)
        elif not active and was:
            self.active[code] = False
            self.raise_alert(code + '_cleared', 'info', clear_text)

    def check_status(self, ev, moving=False):
        """Evaluate one status event. moving = a motion program runs or manual driving is armed."""
        g = lambda k: ev.get(k) if isinstance(ev.get(k), dict) else {}
        b, d, o, sc, es, sy, net, ck = g('battery'), g('dock'), g('odom'), g('scan'), g('estop'), g('system'), g('net'), g('clock')
        now = self.clock()
        # battery (a robot that is charging is not "low")
        pct = finite_num(b.get('percent'))
        if pct is not None:
            if b.get('charging') is True:
                lvl = 0
            else:
                prev = self.batt_level
                lvl = 2 if (pct < 10 or (prev == 2 and pct < 12)) else 1 if (pct < 20 or (prev >= 1 and pct < 22)) else 0
            if lvl != self.batt_level:
                old, self.batt_level = self.batt_level, lvl
                if lvl == 2:
                    self.raise_alert('battery_critical', 'critical', 'Battery is critically low (%d %%). Dock the robot now.' % pct)
                elif lvl == 1 and old == 0:
                    self.raise_alert('battery_low', 'warn', 'Battery is low (%d %%). Dock the robot soon.' % pct)
                else:
                    self.raise_alert('battery_cleared', 'info', 'Battery is %d %%.' % pct)
        # dock
        dk = d.get('is_docked')
        if isinstance(dk, bool):
            if self.prev_docked is not None and dk != self.prev_docked:
                self.raise_alert('docked' if dk else 'undocked', 'info', 'The robot is docked.' if dk else 'The robot left the dock.')
            self.prev_docked = dk
        # e-stop
        on = es.get('on')
        if isinstance(on, bool):
            if on and self.prev_estop is not True:
                self.raise_alert('estop_on', 'critical', 'E-stop is on (%s).' % (es.get('source') or 'unknown source'))
            elif not on and self.prev_estop is True:
                self.raise_alert('estop_off', 'info', 'E-stop released.')
            self.prev_estop = on
        # lidar silent while undocked for 10 s (it is off while docked)
        silent = dk is False and (sc.get('age_s') is None or finite_num(sc.get('age_s')) is None or sc['age_s'] > 3.0)
        if silent:
            self.lidar_bad_since = self.lidar_bad_since or now
        else:
            self.lidar_bad_since = None
        self._cond('lidar_silent', silent and now - self.lidar_bad_since >= 10.0, 'warn',
                   'The lidar is not sending scans although the robot is undocked.', 'The lidar is sending scans again.')
        # odometry stall while moving (TB-25)
        age = finite_num(o.get('age_s'))
        vx, wz = finite_num(o.get('vx')) or 0.0, finite_num(o.get('wz')) or 0.0
        stalled = age is not None and age > 0.5 and (moving or abs(vx) > 0.02 or abs(wz) > 0.02)
        self._cond('odom_stall', stalled, 'warn', 'Odometry paused for %.1f s while the robot was moving (TB-25).' % (age or 0.0),
                   'Odometry is flowing again.')
        # Wi-Fi, temperature, clock
        dbm = finite_num(net.get('signal_dbm'))
        if dbm is not None:
            weak = dbm < -75 or (self.active.get('wifi_weak', False) and dbm < -72)
            self._cond('wifi_weak', weak, 'warn', 'Wi-Fi signal is weak (%d dBm).' % dbm, 'Wi-Fi signal is fine again (%d dBm).' % dbm)
        temp = finite_num(sy.get('temp_c'))
        if temp is not None:
            hot = temp > 75 or (self.active.get('temp_high', False) and temp > 72)
            self._cond('temp_high', hot, 'warn', 'The robot computer is hot (%d C).' % temp, 'The robot computer cooled down (%d C).' % temp)
        wall = finite_num(ev.get('wall'))
        if wall is None and finite_num(ck.get('year')) is not None:
            wrong = abs(ck['year'] - time.gmtime(now).tm_year) >= 1
        else:
            wrong = wall is not None and abs(wall - now) > 86400
        self._cond('clock_wrong', wrong, 'warn', 'The robot clock is wrong. Log timestamps will be off.', 'The robot clock is correct again.')


def is_status_moving(ev, tele_armed=False):
    runs = ev.get('runs') if isinstance(ev.get('runs'), list) else []
    return bool(tele_armed) or any(isinstance(r, dict) and r.get('motion') and r.get('alive') for r in runs)


def limit_value(v, default, lo, hi):
    n = finite_num(v)
    return default if n is None or n <= 0 else min(hi, max(lo, n))


# ============================================================================ mapping (Studio 2.1)

MAP_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$')
MAP_MAX_SIDE = 8192
MAP_MAX_CELLS = 16_000_000
MAP_META_KEYS = ('seq', 't', 'width', 'height', 'resolution', 'origin', 'stride')
MAP_FILE_EXTS = (('pgm', '.pgm'), ('yaml', '.yaml'), ('posegraph', '.posegraph'), ('data', '.data'))
MAP_REMOTE_DIR = '~/robot_code/maps'
MAP_UNKNOWN_GRAY = 205


def valid_map_name(name):
    """True for a map name the bridge accepts (same rule as robot_bridge.py)."""
    return isinstance(name, str) and bool(MAP_NAME_RE.fullmatch(name))  # fullmatch: '$' would accept a trailing newline


ROUTE_UPLOAD_MAX = 32 * 1024 * 1024
ROUTE_REQUIRED = ('route.yaml', 'map.yaml', 'keepout_mask.yaml', 'speed_mask.yaml')


def validate_route_upload(name, files):
    """(True, [(rel, bytes), ...]) for a route folder upload the robot may receive, else (False, error text)."""
    if not valid_map_name(name):
        return False, 'bad route name (letters, digits, - and _, at most 48 characters)'
    if not isinstance(files, list) or not files:
        return False, 'no files to upload'
    if len(files) > 64:
        return False, 'too many files (at most 64)'
    out, seen, total = [], set(), 0
    for f in files:
        if not isinstance(f, dict) or not isinstance(f.get('path'), str) or not isinstance(f.get('data_b64'), str):
            return False, 'each file needs a path and data_b64'
        rel = f['path']
        if (not rel or len(rel) > 100 or '/' in rel or '\\' in rel or '..' in rel or rel.startswith('.')
                or not rel.isprintable()):
            return False, 'bad file name: %r' % rel[:60]
        if rel in seen:
            return False, 'duplicate file: ' + rel
        seen.add(rel)
        try:
            data = base64.b64decode(f['data_b64'], validate=True)
        except (ValueError, TypeError):
            return False, 'bad base64 in ' + rel
        total += len(data)
        if total > ROUTE_UPLOAD_MAX:
            return False, 'upload too large (at most %d MB)' % (ROUTE_UPLOAD_MAX // (1024 * 1024))
        out.append((rel, data))
    missing = [r for r in ROUTE_REQUIRED if r not in seen]
    if missing:
        return False, 'missing: ' + ', '.join(missing)
    return True, out


def png_gray(width, height, pixels):
    """8-bit greyscale PNG (colour type 0, filter 0 on every row) of width x height pixel bytes, row 0 = top."""
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        raise ValueError('bad image size')
    if len(pixels) != width * height:
        raise ValueError('pixel count does not match the size')

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)

    raw = b''.join(b'\x00' + bytes(pixels[y * width:(y + 1) * width]) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def _gray_table():
    t = bytearray([MAP_UNKNOWN_GRAY]) * 256
    for v in range(101):
        t[v] = int(254 - v * 254 / 100 + 0.5)
    return bytes(t)


_GRAY_TABLE = _gray_table()


def cells_to_gray(data):
    """Occupancy bytes (0..100, 255 unknown) to grey: 0 -> 254, 100 -> 0, in between scaled, unknown (and 101..254) -> 205."""
    return bytes(data).translate(_GRAY_TABLE)


def flip_rows(width, height, data):
    """Reverse the row order (ROS row 0 = bottom of the map, image row 0 = top)."""
    if len(data) != width * height:
        raise ValueError('cell count does not match the size')
    return b''.join(bytes(data[y * width:(y + 1) * width]) for y in range(height - 1, -1, -1))


def decode_map_payload(ev):
    """(meta, grey bytes with the top row first) from a bridge `map` event ('cells') or a map_preview reply ('gray').

    Raises ValueError for a payload that is not what the contract says."""
    if not isinstance(ev, dict):
        raise ValueError('map payload is not an object')
    w, h = ev.get('width'), ev.get('height')
    if not (isinstance(w, int) and isinstance(h, int)) or isinstance(w, bool) or isinstance(h, bool):
        raise ValueError('map size is not a whole number')
    if not (0 < w <= MAP_MAX_SIDE and 0 < h <= MAP_MAX_SIDE and w * h <= MAP_MAX_CELLS):
        raise ValueError('map size out of range')
    enc = ev.get('encoding')
    if enc not in ('cells', 'gray'):
        raise ValueError('unknown map encoding: %r' % (enc,))
    try:
        comp = base64.b64decode(ev.get('data') or '', validate=True)
        d = zlib.decompressobj()
        raw = d.decompress(comp, w * h + 1)
    except (ValueError, TypeError, zlib.error):
        raise ValueError('map data is not zlib + base64')
    if len(raw) != w * h or d.unconsumed_tail:
        raise ValueError('map data length %d does not match %dx%d' % (len(raw), w, h))
    meta = {k: ev[k] for k in MAP_META_KEYS if k in ev}
    if enc == 'cells':
        return meta, cells_to_gray(flip_rows(w, h, raw))
    return meta, raw


class MapStore:
    """Thread-safe: the newest live map as a PNG with its metadata, and the last MappingInfo seen."""

    def __init__(self):
        self.lock = threading.Lock()
        self.png = None
        self.meta = None
        self.info = None

    def set_map(self, meta, png):
        with self.lock:
            self.png, self.meta = png, dict(meta)

    def get_map(self):
        """(png, meta) or None."""
        with self.lock:
            return None if self.png is None else (self.png, dict(self.meta))

    def set_info(self, info):
        """Remember a MappingInfo (a `mapping` event or the reply of a mapping_* command); only a dict with a state counts."""
        if not isinstance(info, dict) or not isinstance(info.get('state'), str):
            return
        clean = {k: v for k, v in info.items() if k not in ('ev', 'id', 'ok', 'result', 'error')}
        with self.lock:
            self.info = clean

    def get_info(self):
        with self.lock:
            return None if self.info is None else dict(self.info)

    def clear(self):
        with self.lock:
            self.png = self.meta = self.info = None


# ============================================================================ bridge process


class BridgeError(Exception):
    pass


class Bridge:
    """One long-lived bridge process (ssh, or `python robot_bridge.py --fake`), JSON lines both ways."""

    def __init__(self, app):
        self.app = app
        self.proc = None
        self.lock = threading.Lock()
        self.pending = {}
        self.next_id = 1
        self.stderr_tail = collections.deque(maxlen=30)
        self.connected = False
        self.hello = None
        self.hello_evt = threading.Event()
        self.user_stop = False
        self.host = None
        self.via = None
        self.gen = 0

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, argv, host, via, payload=None, env=None):
        self.stop(quiet=True)
        self.gen += 1
        gen = self.gen
        self.user_stop = False
        self.connected = False
        self.hello = None
        self.hello_evt.clear()
        self.stderr_tail.clear()
        maps = getattr(self.app, 'maps', None)     # test doubles of the app have none
        if maps is not None:
            maps.clear()    # no map or mapping state from another robot or bridge process
        self.host, self.via = host, via
        self.app.conn('connecting', host, via)
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         env=env, **hide_flags())
        except OSError as e:
            self.app.conn('error', host, via, 'cannot start: %s' % e, kind='other')
            return False
        proc = self.proc
        threading.Thread(target=self._read_out, args=(proc, gen), daemon=True).start()
        threading.Thread(target=self._read_err, args=(proc,), daemon=True).start()
        threading.Thread(target=self._wait, args=(proc, gen), daemon=True).start()
        if payload is not None:
            try:
                proc.stdin.write(b'%d\n' % len(payload) + payload)
                proc.stdin.flush()
            except OSError:
                pass  # the exit handler reports the real reason
        return True

    def _read_out(self, proc, gen):
        try:
            for raw in proc.stdout:
                line = raw.decode('utf-8', 'replace').strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if not isinstance(ev, dict):
                        raise ValueError
                except ValueError:
                    self.app.log('warn', 'bridge output: ' + line[:200])
                    continue
                if gen != self.gen:
                    continue
                if ev.get('ev') == 'reply':
                    with self.lock:
                        slot = self.pending.pop(ev.get('id'), None)
                    if slot:
                        slot[1].append(ev)
                        slot[0].set()
                    continue
                if ev.get('ev') == 'hello' and not self.connected:
                    self.hello = ev
                    self.connected = True
                    self.hello_evt.set()
                    self.app.bus.publish(ev)
                    self.app.conn('connected', self.host, self.via)
                    self._send({'id': 0, 'cmd': 'status_on', 'period': 1.0})
                    continue
                if ev.get('ev') == 'status':
                    self.app.on_status(ev)
                if ev.get('ev') == 'map':
                    self.app.on_map(ev)     # decoded into the MapStore; the page gets the slim event
                    continue
                if ev.get('ev') == 'mapping':
                    self.app.maps.set_info(ev)
                self.app.bus.publish(ev)
        except (OSError, ValueError):
            pass

    def _read_err(self, proc):
        try:
            for raw in proc.stderr:
                line = raw.decode('utf-8', 'replace').rstrip()
                if line:
                    self.stderr_tail.append(line)
        except (OSError, ValueError):
            pass

    def _wait(self, proc, gen):
        code = proc.wait()
        time.sleep(0.2)  # let the stderr reader finish
        if gen != self.gen:
            return
        with self.lock:
            pend, self.pending = self.pending, {}
        for ident, slot in pend.items():
            slot[1].append({'ev': 'reply', 'id': ident, 'ok': False, 'error': 'bridge connection closed'})
            slot[0].set()
        was = self.connected
        self.connected = False
        self.hello_evt.set()
        if self.user_stop:
            self.app.conn('disconnected', self.host, self.via)
            return
        kind, msg = map_ssh_error('\n'.join(self.stderr_tail), code)
        if was and kind == 'other':
            msg = 'connection lost (%s)' % msg
        self.app.log('error', 'bridge ended (exit %s): %s' % (code, msg))
        if was and self.app.bridge_lost(self.host, self.via, msg, kind):
            return  # v1.3: the app reconnects by itself and shows the 'reconnecting' state instead of an error
        self.app.conn('error', self.host, self.via, msg, kind=kind, detail=list(self.stderr_tail)[-5:])

    def _send(self, obj):
        data = (json.dumps(obj) + '\n').encode()
        with self.lock:
            p = self.proc
            if p is None or p.poll() is not None:
                raise BridgeError('not connected')
            try:
                p.stdin.write(data)
                p.stdin.flush()
            except (OSError, ValueError):
                raise BridgeError('not connected')

    def request(self, cmd, timeout=15.0):
        """cmd: dict with 'cmd' and args. Returns the reply event (dict). Raises BridgeError on no connection / timeout."""
        if not self.connected:
            raise BridgeError('not connected')
        with self.lock:
            ident = self.next_id
            self.next_id += 1
            slot = (threading.Event(), [])
            self.pending[ident] = slot
        msg = dict(cmd)
        msg['id'] = ident
        try:
            self._send(msg)
        except BridgeError:
            with self.lock:
                self.pending.pop(ident, None)
            raise
        if not slot[0].wait(timeout):
            with self.lock:
                self.pending.pop(ident, None)
            raise BridgeError('timeout after %.0f s waiting for the robot' % timeout)
        return slot[1][0]

    def stop(self, quiet=False):
        p = self.proc
        if p is None:
            return
        self.user_stop = True
        if p.poll() is None:
            try:
                if self.connected:
                    self._send({'id': -1, 'cmd': 'shutdown'})
                    p.stdin.close()
            except Exception:
                pass
            try:
                p.wait(2.5)
            except subprocess.TimeoutExpired:
                p.terminate()
                try:
                    p.wait(2)
                except subprocess.TimeoutExpired:
                    p.kill()
        self.connected = False
        self.proc = None


# ============================================================================ app


class Studio:
    def __init__(self, args):
        self.args = args
        self.fake = bool(args.fake)
        self.cfg = args.config_dir or config_dir()
        os.makedirs(self.cfg, exist_ok=True)
        self.token = secrets.token_urlsafe(24)
        self.heartbeat = getattr(args, 'heartbeat', 15.0)
        self.port = None
        self.bus = Bus()
        self.maps = MapStore()
        self.bridge = Bridge(self)
        self.set_lock = threading.Lock()
        self.settings = self._load_settings()
        self.known_hosts = os.path.join(self.cfg, 'known_hosts')
        # the fake robot's home: --fake-home, else STUDIO_BRIDGE_HOME (tests), else in the config folder. The fake bridge and
        # the fake tar helper must use the same folder.
        self.fake_home = args.fake_home or os.environ.get('STUDIO_BRIDGE_HOME') or os.path.join(self.cfg, 'fake_home')
        self.bridge_script = args.bridge_script or os.path.join(HERE, 'robot_bridge.py')
        self.catalog_path = getattr(args, 'catalog', None) or os.path.join(HERE, 'programs.json')
        self.templates_dir = getattr(args, 'templates_dir', None) or os.path.join(HERE, 'templates')
        self.log_path = os.path.join(self.cfg, 'studio.log')
        try:
            if os.path.getsize(self.log_path) > 1_000_000:
                os.replace(self.log_path, self.log_path + '.old')
        except OSError:
            pass
        self.write_known_hosts()
        self.sync_lock = threading.Lock()
        self._ssh_ver = None
        self.wifi_jobs = collections.OrderedDict()  # nonce -> ssid of the Wi-Fi joins started from this process
        self.closing = False
        self.stop_cb = None             # v1.3: set by main(); stops the server (Quit Studio, exit when closed)
        self.reconn = None              # v1.3: state of a running automatic reconnect, else None
        self.reconn_lock = threading.Lock()
        self.reconnect_delays = RECONNECT_DELAYS
        self.reconnect_give_up = RECONNECT_GIVE_UP
        self.last_cands = []            # newest discover result (diagnostics)
        self.deep_lock = threading.Lock()
        self.update_delay = getattr(args, 'update_delay', 5.0)
        self.update = {'checked': None, 'latest': None, 'page': None, 'notes': '', 'error': None}
        self.update_lock = threading.Lock()
        self._update_logged = False
        # 2.0
        self.web_dir = getattr(args, 'web_dir', None) or WEB_DIR
        self.history = History()
        self.alerts = AlertCenter(os.path.join(self.cfg, 'events.jsonl'), self.bus.publish)
        self.tele_armed = False         # what Studio believes (from the bridge's teleop events and replies)
        self.tele_gen = None            # bridge generation the arm belongs to: motion is never sent to another process
        self.conn_lost = False
        self.run_names = {}
        self.run_stopped = set()       # run ids the user stopped (a stopped program ends with a non-zero code: not an error)
        self.estop_until = 0.0         # runs that end shortly after an e-stop or Stop all were stopped by it
        self.bus.tap = self._tap

    # ---------------------------------------------------------------- settings / logging
    def _load_settings(self):
        s = {'last_host': None, 'last_via': None, 'key_path': None, 'local_dir': None,
             'remote_dir': DEFAULT_REMOTE_DIR, 'motion_files': [], 'trust_host_key': None, 'known_addresses': {},
             'builtin_host_key': True, 'trusted_host_keys': [], 'setup_done': False,
             'auto_reconnect': True, 'update_check': True, 'update_last': {}, 'update_dismissed': None,
             'window_mode': DEFAULT_WINDOW_MODE, 'ui': 'v2', 'teleop_linear': TELEOP_DEFAULT_LINEAR,
             'teleop_angular': TELEOP_DEFAULT_ANGULAR}
        s.update(DEFAULT_SETTINGS)
        d = {}
        try:
            with open(os.path.join(self.cfg, 'settings.json'), encoding='utf-8') as f:
                d = json.load(f)
            if not isinstance(d, dict):
                d = {}
            for k in s:
                if k in d:
                    s[k] = d[k]
        except (OSError, ValueError):
            d = {}
        # keep the file's values only when they pass the same checks as POST /api/settings, else the default
        if not (isinstance(s['robot_hostname'], str) and DNS_LABEL_RE.match(s['robot_hostname'])):
            s['robot_hostname'] = DEFAULT_SETTINGS['robot_hostname']
        if not (isinstance(s['robot_user'], str) and USER_RE.match(s['robot_user'])):
            s['robot_user'] = DEFAULT_SETTINGS['robot_user']
        if not valid_ssid(s['hotspot_ssid']):
            s['hotspot_ssid'] = DEFAULT_SETTINGS['hotspot_ssid']
        for k in ('hotspot_addr', 'cable_addr'):
            if not (isinstance(s[k], str) and valid_host(s[k]) and '@' not in s[k]):
                s[k] = DEFAULT_SETTINGS[k]
        s['builtin_host_key'] = bool(s['builtin_host_key'])
        s['auto_reconnect'] = bool(s['auto_reconnect'])
        s['update_check'] = bool(s['update_check'])
        s['window_mode'] = s['window_mode'] if s['window_mode'] in WINDOW_MODES else DEFAULT_WINDOW_MODE
        s['ui'] = s['ui'] if s['ui'] in UI_CHOICES else 'v2'
        s['teleop_linear'] = limit_value(s['teleop_linear'], TELEOP_DEFAULT_LINEAR, TELEOP_MIN_LINEAR, TELEOP_MAX_LINEAR)
        s['teleop_angular'] = limit_value(s['teleop_angular'], TELEOP_DEFAULT_ANGULAR, TELEOP_MIN_ANGULAR, TELEOP_MAX_ANGULAR)
        ul = s['update_last'] if isinstance(s['update_last'], dict) else {}
        s['update_last'] = ({'t': float(ul['t']), 'latest': ul['latest']} if isinstance(ul.get('t'), (int, float))
                            and isinstance(ul.get('latest'), str) and VERSION_RE.match(ul['latest']) else {})
        ud = s['update_dismissed']
        s['update_dismissed'] = ud if isinstance(ud, str) and VERSION_RE.match(ud) else None
        tk = []
        for e in (s['trusted_host_keys'] if isinstance(s['trusted_host_keys'], list) else []):
            if isinstance(e, dict) and isinstance(e.get('key'), str) and KEY_LINE_RE.match(e['key']) \
                    and e['key'] not in [x['key'] for x in tk]:
                tk.append({'key': e['key'], 'label': str(e.get('label') or 'Robot')[:60], 'added': e.get('added')})
        old = s.get('trust_host_key')  # one-slot setting of v1.0/1.1: migrate into the list
        if isinstance(old, str) and KEY_LINE_RE.match(old.strip()):
            old = ' '.join(old.split()[:2])
            if old != LAB_HOST_KEY and old not in [x['key'] for x in tk]:
                tk.append({'key': old, 'label': LEGACY_TRUST_LABEL, 'added': int(time.time())})
        s['trust_host_key'] = None
        s['trusted_host_keys'] = tk
        # a config that already knows a robot has been set up before: no wizard for existing users
        s['setup_done'] = bool(d['setup_done']) if 'setup_done' in d else bool(d.get('last_host'))
        return s

    def save_settings(self):
        tmp = os.path.join(self.cfg, 'settings.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=2)
        os.replace(tmp, os.path.join(self.cfg, 'settings.json'))

    def user(self):
        return self.settings.get('robot_user') or ROBOT_USER

    def trusted_keys(self):
        """Every key ssh may accept for the robot alias: the built-in one (unless switched off) + the user's own list."""
        keys = [LAB_HOST_KEY] if self.settings.get('builtin_host_key', True) else []
        for e in self.settings.get('trusted_host_keys') or []:
            if e['key'] not in keys:
                keys.append(e['key'])
        return keys

    def write_known_hosts(self):
        want = ''.join('%s %s\n' % (PIN_ALIAS, k) for k in self.trusted_keys())
        try:
            with open(self.known_hosts, encoding='utf-8') as f:
                if f.read() == want:
                    return
        except OSError:
            pass
        with open(self.known_hosts, 'w', encoding='utf-8', newline='\n') as f:
            f.write(want)

    def log(self, level, text):
        self.bus.publish({'ev': 'log', 'level': level, 'text': text, 't': time.time()})
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write('%s %s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), level, text))
        except OSError:
            pass

    def conn(self, state, host=None, via=None, error=None, **extra):
        if self.reconn is not None and state in ('connecting', 'error', 'disconnected'):
            return  # an automatic reconnect is running: the banner shows it, not every failed try
        ev = {'ev': 'conn', 'state': state, 'host': host, 'via': via, 'error': error}
        ev.update(extra)
        self.bus.publish(ev)

    # ---------------------------------------------------------------- keys / executables
    def default_key(self):
        std = os.path.expanduser('~/.ssh/turtlebot4_ed25519')
        return std if os.path.isfile(std) else os.path.join(self.cfg, 'id_ed25519')

    def key_path(self, create=True):
        k = self.settings.get('key_path') or self.default_key()
        k = os.path.expanduser(k)
        if create and not os.path.isfile(k):
            if k != os.path.join(self.cfg, 'id_ed25519') and self.settings.get('key_path'):
                raise BridgeError('key file not found: ' + k)
            kg = find_exe('ssh-keygen')
            if not kg:
                raise BridgeError('ssh-keygen not found (install the OpenSSH client)')
            r = subprocess.run([kg, '-t', 'ed25519', '-N', '', '-f', k, '-C', 'turtlebot-studio'],
                               capture_output=True, text=True, timeout=30, **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
            if r.returncode != 0:
                raise BridgeError('ssh-keygen failed: ' + (r.stderr or r.stdout).strip()[-200:])
            self.log('info', 'created a new ssh key for this app: ' + k)
        return k

    def public_key_line(self):
        k = self.key_path()
        try:
            with open(k + '.pub', encoding='utf-8') as f:
                line = f.read().strip()
        except OSError:
            kg = find_exe('ssh-keygen')
            r = subprocess.run([kg, '-y', '-f', k], capture_output=True, text=True, timeout=15, **hide_flags()) if kg else None
            line = (r.stdout.strip() if r and r.returncode == 0 else '')
        if not PUB_LINE_RE.match(line):
            raise BridgeError('public key file missing or not understood: ' + k + '.pub')
        return line

    # ---------------------------------------------------------------- connect
    def connect(self, host=None, auto=False):
        if not auto:
            self.reconnect_cancel(quiet=True)  # the user takes over
        self.teleop_off('reconnecting' if auto else 'connecting')  # a new bridge process always starts disarmed
        host = (host or self.args.host_override or '').strip()
        if self.fake:
            return self._connect_fake()
        ssh = find_exe('ssh')
        if not ssh:
            self.conn('error', None, None, 'ssh not found: install the OpenSSH client', kind='no_ssh')
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        via = 'custom' if host else None
        if not host:
            cands = self.discover()
            best = next((c for c in cands if c['reachable']), None)
            if not best:
                self.conn('error', None, None, 'robot not reachable', kind='unreachable')
                return {'ok': False, 'error': 'robot not reachable', 'candidates': cands}
            host, via = best['host'], best['via']
        elif host == self.settings.get('last_host') and self.settings.get('last_via'):
            via = self.settings['last_via']
        if not valid_host(host):
            return {'ok': False, 'error': 'invalid host name or address'}
        try:
            key = self.key_path()
            payload = self._bridge_bytes()
        except (BridgeError, OSError) as e:
            self.conn('error', host, via, str(e), kind='other')
            return {'ok': False, 'error': str(e)}
        self.write_known_hosts()
        argv = build_bridge_ssh_argv(ssh, host, key, self.known_hosts, user=self.user())
        self.bridge.start(argv, host, via, payload=payload)
        return self._await_hello(host, via)

    def _connect_fake(self):
        try:
            os.makedirs(self.fake_home, exist_ok=True)
            if not is_frozen() and not os.path.isfile(self.bridge_script):
                raise BridgeError('robot_bridge.py not found next to studio.py')
        except (OSError, BridgeError) as e:
            self.conn('error', 'fake', 'custom', str(e), kind='other')
            return {'ok': False, 'error': str(e)}
        # STUDIO_BRIDGE_HOME: the fake robot keeps maps, routes and logs in the fake home, where the fake tar helper looks
        env = dict(os.environ, HOME=self.fake_home, USERPROFILE=self.fake_home, STUDIO_BRIDGE_HOME=self.fake_home,
                   PYTHONDONTWRITEBYTECODE='1')
        checker = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'delivery',
                                                'menu_config.py'))
        if 'STUDIO_MENU_CHECKER' not in env and os.path.isfile(checker):
            env['STUDIO_MENU_CHECKER'] = checker
        self.bridge.start(fake_bridge_argv(self.bridge_script), 'fake', 'custom', env=env)
        return self._await_hello('fake', 'custom')

    def _bridge_bytes(self):
        try:
            with open(self.bridge_script, 'rb') as f:
                return f.read()
        except OSError:
            raise BridgeError('robot_bridge.py not found next to studio.py')

    def _await_hello(self, host, via):
        ok = self.bridge.hello_evt.wait(25) and self.bridge.connected
        if ok:
            if not self.fake:
                self.settings['last_host'], self.settings['last_via'] = host, via
                self.save_settings()
            return {'ok': True, 'host': host, 'via': via, 'hello': self.bridge.hello}
        if self.bridge.alive():  # no hello and no exit: give up
            self.bridge.stop()
            self.conn('error', host, via, 'robot did not answer', kind='unreachable')
            return {'ok': False, 'error': 'robot did not answer'}
        time.sleep(0.3)
        c = self.bus.last_conn
        return {'ok': False, 'error': c.get('error') or 'connection failed', 'kind': c.get('kind')}

    def disconnect(self):
        self.teleop_off('Disconnected.')
        self.reconnect_cancel(quiet=True)
        self.bridge.stop()
        self.conn('disconnected', self.bridge.host, self.bridge.via)
        return {'ok': True}

    # ---------------------------------------------------------------- discovery
    def candidate_list(self, extra=None, v6=(), wifi_ssid=None):
        cands = []

        def add(host, label, via):
            if host and valid_host(host) and all(c['host'] != host for c in cands):
                cands.append({'host': host, 'label': label, 'via': via})
        last = self.settings.get('last_host')
        if extra:
            add(extra, 'Typed address', 'custom')
        if self.args.host_override:
            add(self.args.host_override, 'Host override', 'custom')
        add(last, 'Last used', self.settings.get('last_via') or 'custom')
        add(self.settings['hotspot_addr'], 'Robot hotspot (%s Wi-Fi)' % self.settings['hotspot_ssid'], 'hotspot')
        for h in v6:
            add(h, 'Cable (IPv6)', 'cable')
        if has_cable_v4():
            add(self.settings['cable_addr'], 'Cable (%s)' % self.settings['cable_addr'], 'cable')
        known = (self.settings.get('known_addresses') or {}).get(wifi_ssid) if wifi_ssid else None
        if isinstance(known, dict) and known.get('ip'):
            add(known['ip'], 'Robot on %s (last seen %s)' % (wifi_ssid, known['ip']), 'wifi')
        mdns = self.settings['robot_hostname'] + '.local'
        add(mdns, 'Robot name on the Wi-Fi (%s)' % mdns, 'wifi')
        return cands

    def discover(self, extra=None):
        if self.fake:
            c = [{'host': 'fake', 'label': 'Fake robot (local)', 'via': 'custom', 'reachable': True, 'ms': 0}]
            self.last_cands = c
            self.bus.publish({'ev': 'discover', 'candidates': c})
            return c
        prev = self.bus.last_conn
        if prev.get('state') not in ('connected', 'connecting', 'reconnecting'):
            self.conn('discovering', prev.get('host'), prev.get('via'))
        t0 = time.time()
        deadline = t0 + 4.0
        res = {}
        threads = []

        def probe(c):
            t = time.time()
            try:
                s = socket.create_connection((c['host'], 22), timeout=1.5)
                s.close()
                res[c['host']] = (True, int((time.time() - t) * 1000))
            except OSError:
                res[c['host']] = (False, int((time.time() - t) * 1000))

        def start_probes(cs):
            for c in cs:
                th = threading.Thread(target=probe, args=(c,), daemon=True)
                th.start()
                threads.append(th)
        v6box = []
        nb = threading.Thread(target=lambda: v6box.extend(find_cable_ipv6(3.2)), daemon=True)
        nb.start()
        wbox = []
        wt = threading.Thread(target=lambda: wbox.append(laptop_wifi()), daemon=True)
        wt.start()
        wt.join(max(0.1, min(2.0, deadline - time.time())))
        wifi_ssid = (wbox[0] or {}).get('ssid') if wbox else None
        static = self.candidate_list(extra, wifi_ssid=wifi_ssid)
        start_probes(static)
        nb.join(max(0.1, deadline - time.time()))
        cands = self.candidate_list(extra, v6box, wifi_ssid)
        start_probes([c for c in cands if c['host'] not in res and c['host'] not in [s['host'] for s in static]])
        for th in threads:
            th.join(max(0.05, deadline - time.time()))
        for c in cands:
            ok, ms = res.get(c['host'], (False, int((time.time() - t0) * 1000)))
            c['reachable'], c['ms'] = ok, ms
        cands.sort(key=lambda c: not c['reachable'])  # stable: reachable first, order kept
        self.last_cands = cands
        self.bus.publish({'ev': 'discover', 'candidates': cands})
        if self.bus.last_conn.get('state') == 'discovering':
            self.conn('disconnected', prev.get('host'), prev.get('via'))
        return cands

    # ---------------------------------------------------------------- v1.3: search the whole network
    def deep_discover(self):
        if not self.deep_lock.acquire(blocking=False):
            return {'ok': False, 'error': 'already searching'}
        try:
            return self._deep_discover()
        except Exception as e:  # never leave the button spinning
            self.log('error', 'network search failed: %s' % e)
            return {'ok': False, 'error': 'search failed: %s' % e}
        finally:
            self.deep_lock.release()

    def _deep_discover(self):
        def progress(done, total):
            self.bus.publish({'ev': 'deep_progress', 'done': done, 'total': total})
        if self.fake:
            for i in range(1, 21):
                time.sleep(0.1)
                progress(254 * i // 20, 254)
            cands = [{'host': 'fake', 'label': 'Your robot (identity confirmed)', 'via': 'custom', 'reachable': True,
                      'ms': 1, 'identity': 'confirmed', 'pi': True}]
        else:
            cands, err = deep_scan(self.trusted_keys(), progress)
            if err:
                return {'ok': False, 'error': err}
        self.last_cands = cands
        self.bus.publish({'ev': 'discover', 'candidates': cands, 'deep': True})
        self.log('info', 'network search: %d device(s) with ssh, %d confirmed as your robot'
                 % (len(cands), sum(1 for c in cands if c.get('identity') == 'confirmed')))
        return {'ok': True, 'candidates': cands}

    # ---------------------------------------------------------------- v1.3: automatic reconnect
    def bridge_lost(self, host, via, msg, kind):
        """Called by the bridge when it ended on its own while connected. True = Studio takes over (reconnects)."""
        self.teleop_off('Connection lost.')
        if self.closing or not host or not self.settings.get('auto_reconnect', True):
            return False
        if kind in ('host_key', 'key_not_set_up', 'key_missing', 'no_ssh'):
            return False  # waiting will not fix these
        with self.reconn_lock:
            if self.reconn is not None:
                return True
            st = self.reconn = {'cancel': threading.Event(), 'since': time.time(), 'host': host, 'via': via}
        threading.Thread(target=self._reconnect_loop, args=(st, msg), daemon=True, name='reconnect').start()
        return True

    def _reconnect_end(self, st):
        with self.reconn_lock:
            if self.reconn is not st:
                return False
            self.reconn = None
        return True

    def _reconnect_loop(self, st, msg):
        """Backoff 2, 4, 8, 15, 30, 30 ... s for up to reconnect_give_up s. It only opens the connection again:
        it never starts a program, never sends motion and never releases an e-stop."""
        host, via, attempt, fails = st['host'], st['via'], 0, 0
        self.log('warn', 'connection to %s lost (%s): reconnecting' % (host, msg))
        while not st['cancel'].is_set():
            attempt += 1
            delay = reconnect_delay(attempt, self.reconnect_delays)
            self.bus.publish({'ev': 'conn', 'state': 'reconnecting', 'host': host, 'via': via, 'error': msg,
                              'attempt': attempt, 'next_in': delay, 'since': st['since']})
            if st['cancel'].wait(delay):
                return
            if time.time() - st['since'] >= self.reconnect_give_up:
                break
            res = self.connect(host, auto=True)
            if st['cancel'].is_set():
                return
            if res.get('ok'):
                if self._reconnect_end(st):
                    self.log('info', 'reconnected to %s after %d attempt(s)' % (res.get('host') or host, attempt))
                    if not self.bridge.connected and not self.closing:  # dropped again at once
                        self.bridge_lost(host, via, 'connection lost again', 'other')
                return
            fails += 1
            msg = res.get('error') or msg
            if fails >= 2:  # the robot may have a new address: look around quickly
                try:
                    best = next((c for c in self.discover() if c.get('reachable')), None)
                except Exception:
                    best = None
                if best and not st['cancel'].is_set():
                    host, via = best['host'], best.get('via') or via
            if time.time() - st['since'] >= self.reconnect_give_up:
                break
        if st['cancel'].is_set() or not self._reconnect_end(st):
            return
        text = gave_up_text(self.reconnect_give_up)
        self.log('error', text)
        self.conn('disconnected', host, via, text, kind='gave_up')

    def reconnect_cancel(self, quiet=False):
        """Stop trying. quiet=True is used by Disconnect / Connect / shutdown, which publish the next state themselves."""
        with self.reconn_lock:
            st, self.reconn = self.reconn, None
        if st is None:
            return {'ok': True, 'was_reconnecting': False}
        st['cancel'].set()
        try:
            self.bridge.stop()  # also ends an attempt that is in flight
        except Exception:
            pass
        self.log('info', 'automatic reconnect stopped')
        if not quiet:
            self.conn('disconnected', st['host'], st['via'])
        return {'ok': True, 'was_reconnecting': True}

    def fake_drop(self):
        """Fake mode only: end the fake bridge like a lost ssh connection (exit code non-zero)."""
        p = self.bridge.proc
        if p is None or p.poll() is not None or not self.bridge.connected:
            return {'ok': False, 'error': 'not connected'}
        p.kill()
        return {'ok': True}

    # ---------------------------------------------------------------- bridge forwarding
    def forward(self, req):
        cmd = dict(req)
        name = cmd.get('cmd')
        if not isinstance(name, str) or not name:
            return {'ok': False, 'error': 'missing cmd'}
        reasons = None
        if name == 'run':
            reasons = self.motion_for_run(cmd)
        if name in ('teleop_arm', 'teleop'):
            # the limits always come from Studio's settings, whatever the page sent; the bridge caps them again
            cmd['max_linear'] = self.settings.get('teleop_linear', TELEOP_DEFAULT_LINEAR)
            cmd['max_angular'] = self.settings.get('teleop_angular', TELEOP_DEFAULT_ANGULAR)
        if name == 'stop':      # before the request: the program's exit event can arrive before the answer
            if cmd.get('run_id') == 'all':
                self.estop_until = time.time() + 12.0
            elif cmd.get('run_id'):
                self.run_stopped.add(str(cmd.get('run_id')))
        if name == 'teleop' and (not self.tele_armed or self.tele_gen != self.bridge.gen):
            # never send motion unless this very bridge process was armed (no resend after a reconnect)
            return {'ok': False, 'error': 'Manual driving is not armed.', 'armed': False}
        try:
            r = self.bridge.request(cmd, 8 if name == 'estop' else 2 if name == 'teleop' else 15)
        except BridgeError as e:
            return {'ok': False, 'error': str(e)}
        if name.startswith('mapping_') and isinstance(r, dict) and r.get('ok'):
            self.maps.set_info(r)
        if reasons is not None and isinstance(r, dict):
            r['motion_decision'] = {'motion': bool(cmd.get('motion')), 'reasons': reasons}
        if name == 'teleop_arm' and isinstance(r, dict) and r.get('ok'):
            if cmd.get('on') is True:
                self.tele_armed, self.tele_gen = True, self.bridge.gen
            else:
                self.tele_armed = False
        if name == 'run' and isinstance(r, dict) and r.get('ok') and r.get('run_id'):
            pname = os.path.basename(str(cmd.get('path', ''))) or 'program'
            self.run_names[r['run_id']] = pname
            self.alerts.raise_alert('program_started', 'info', 'Started %s.' % pname)
        return r

    def teleop_off(self, reason, wait=2.0):
        """Disarm manual driving (the bridge publishes zero velocity). Safe to call at any time and from any thread."""
        was = self.tele_armed
        self.tele_armed = False
        confirmed = False
        if self.bridge.connected:
            try:
                r = self.bridge.request({'cmd': 'teleop_arm', 'on': False, 'reason': reason}, wait)
                confirmed = bool(r.get('ok'))
            except BridgeError:
                pass
        if was and not confirmed:   # the bridge could not say it: tell the page ourselves
            self.bus.publish({'ev': 'teleop', 'armed': False, 'reason': reason})
        return was

    def client_gone(self):
        """An event stream (page) closed. When it was the last one nobody is watching the robot: stop manual driving."""
        if self.closing or self.bus.count() > 0:
            return
        if self.tele_armed or self.bridge.connected:
            threading.Thread(target=self.teleop_off, args=('The last Studio page was closed.',), daemon=True,
                             name='teleop-off').start()

    def teleop_limits(self, req=None):
        if req is not None:
            upd = {}
            for key, setting, lo, hi, unit in (('linear', 'teleop_linear', TELEOP_MIN_LINEAR, TELEOP_MAX_LINEAR, 'm/s'),
                                               ('angular', 'teleop_angular', TELEOP_MIN_ANGULAR, TELEOP_MAX_ANGULAR, 'rad/s')):
                if key not in req:
                    continue
                n = finite_num(req[key])
                if n is None or n <= 0:
                    return {'ok': False, 'error': '%s must be a number above 0 (%s, at most %.2f)' % (key, unit, hi)}
                upd[setting] = round(min(hi, max(lo, n)), 3)
            if not upd:
                return {'ok': False, 'error': 'give linear and/or angular'}
            with self.set_lock:
                self.settings.update(upd)
                self.save_settings()
        return {'ok': True, 'linear': self.settings['teleop_linear'], 'angular': self.settings['teleop_angular'],
                'max_linear': TELEOP_MAX_LINEAR, 'max_angular': TELEOP_MAX_ANGULAR}

    def _tap(self, ev):
        """Every published event passes here: raises alerts for connection, driving and program events."""
        kind = ev.get('ev')
        if kind == 'conn':
            st, host = ev.get('state'), ev.get('host') or 'the robot'
            if st == 'connected':
                if self.conn_lost:
                    self.alerts.raise_alert('conn_restored', 'info', 'Connection to %s restored.' % host)
                else:
                    self.alerts.raise_alert('conn_connected', 'info', 'Connected to %s.' % host)
                self.conn_lost = False
            elif st == 'reconnecting':
                if not self.conn_lost:
                    self.conn_lost = True
                    self.alerts.raise_alert('conn_lost', 'critical', 'Connection to %s lost. Studio is reconnecting.' % host)
            elif st == 'error':
                self.alerts.raise_alert('conn_error', 'warn', 'Connection problem: %s' % (ev.get('error') or 'unknown'))
            elif st == 'disconnected':
                self.conn_lost = False
                self.alerts.raise_alert('conn_disconnected', 'info', 'Disconnected from %s.' % host)
        elif kind == 'teleop':
            self.tele_armed = bool(ev.get('armed'))
            if ev.get('armed'):
                self.alerts.raise_alert('teleop_armed', 'info', 'Manual driving is armed.')
            else:
                self.alerts.raise_alert('teleop_disarmed', 'info', 'Manual driving is off: %s' % (ev.get('reason') or 'disarmed'))
        elif kind == 'run_exit':
            name = self.run_names.get(ev.get('run_id'), 'A program')
            code = ev.get('code')
            if code != 0 and (str(ev.get('run_id')) in self.run_stopped or time.time() < self.estop_until):
                self.alerts.raise_alert('program_exited', 'info', '%s was stopped.' % name)
            elif code == 0:
                self.alerts.raise_alert('program_exited', 'info', '%s finished.' % name)
            else:
                self.alerts.raise_alert('program_failed', 'warn', '%s exited with an error%s.' % (
                    name, '' if code is None else ' (code %s)' % code))

    def estop(self):
        self.tele_armed = False     # the bridge disarms manual driving first thing; Studio stops sending at once
        self.estop_until = time.time() + 15.0
        out = {'ok': False}
        try:
            r = self.bridge.request({'cmd': 'estop'}, 8)
            out['bridge'] = r
            out['ok'] = bool(r.get('ok'))
        except BridgeError as e:
            out['bridge'] = {'ok': False, 'error': str(e)}
        if not out['ok']:
            out['fallback'] = self._estop_fallback()
            out['ok'] = bool(out['fallback'].get('ok'))
        self.log('warn' if out['ok'] else 'error', 'E-stop requested: %s' % ('sent' if out['ok'] else 'FAILED, check the robot!'))
        return out

    def _estop_fallback(self):
        if self.fake:
            return {'ok': False, 'error': 'no robot in fake mode'}
        host = self.bridge.host or self.settings.get('last_host') or self.args.host_override
        ssh = find_exe('ssh')
        if not host or not ssh or not valid_host(host):
            return {'ok': False, 'error': 'no known robot address or no ssh'}
        cmd = ("touch ~/STOP; pkill -INT -f '%s'; source /etc/turtlebot4/setup.bash >/dev/null 2>&1; "
               "timeout 5 ros2 service call /e_stop irobot_create_msgs/srv/EStop '{e_stop_on: true}'" % MOTION_PKILL_REGEX)
        try:
            argv = build_ssh_argv(ssh, host, self.key_path(create=False), self.known_hosts, cmd, connect_timeout=5,
                                  user=self.user())
            r = subprocess.run(argv, capture_output=True, text=True, timeout=15, **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
        except (OSError, subprocess.TimeoutExpired, BridgeError) as e:
            return {'ok': False, 'error': str(e)}
        # pkill finds nothing -> exit 1 is normal; success means ssh reached the robot and the service call ran.
        reached = r.returncode != 255
        return {'ok': reached and 'success' in (r.stdout or '').lower(), 'reached': reached, 'exit': r.returncode,
                'stdout': (r.stdout or '')[-400:], 'stderr': (r.stderr or '')[-300:]}

    # ---------------------------------------------------------------- sync
    def _remote_exec_argv(self, shell_cmd, fake_args):
        """Argv for a command on the robot (ssh) or, in fake mode, the local helper standing in for it."""
        if self.fake:
            return self_argv('--_fake-tar', *fake_args)
        ssh = find_exe('ssh')
        if not ssh:
            raise BridgeError('ssh not found')
        host = self.bridge.host or self.settings.get('last_host')
        if not host:
            raise BridgeError('not connected')
        return build_ssh_argv(ssh, host, self.key_path(create=False), self.known_hosts, shell_cmd, connect_timeout=8,
                              user=self.user())

    def sync(self, req):
        direction = req.get('direction', 'up')
        if direction not in ('up', 'down'):
            return {'ok': False, 'error': 'direction must be up or down'}
        local_dir = req.get('local_dir') or self.settings.get('local_dir')
        remote_dir = req.get('remote_dir') or self.settings.get('remote_dir') or DEFAULT_REMOTE_DIR
        delete, dry = bool(req.get('delete')), bool(req.get('dry_run'))
        if not local_dir:
            return {'ok': False, 'error': 'choose a local folder first'}
        local_dir = os.path.abspath(os.path.expanduser(local_dir))
        if direction == 'up' and not os.path.isdir(local_dir):
            return {'ok': False, 'error': 'local folder does not exist: ' + local_dir}
        if not self.sync_lock.acquire(blocking=False):
            return {'ok': False, 'error': 'another sync is running'}
        try:
            self.bus.publish({'ev': 'sync', 'state': 'running', 'direction': direction})
            res = self._sync(direction, local_dir, remote_dir, delete, dry, bool(req.get('confirm_delete')))
        except (BridgeError, OSError, ValueError, tarfile.TarError) as e:
            res = {'ok': False, 'error': str(e)}
        finally:
            self.sync_lock.release()
        self.bus.publish({'ev': 'sync', 'state': 'done' if res.get('ok') else 'error', 'direction': direction,
                          'uploaded': res.get('uploaded', []), 'skipped': res.get('skipped', 0),
                          'deleted': res.get('deleted', []), 'error': res.get('error')})
        return res

    def _sync(self, direction, local_dir, remote_dir, delete, dry, confirm_delete):
        r = self.bridge.request({'cmd': 'ls', 'dir': remote_dir, 'recursive': True}, 20)
        remote = {}
        if r.get('ok'):
            remote = {f['name'].replace('\\', '/'): {'size': f.get('size'), 'sha1': f.get('sha1')}
                      for f in r.get('files', []) if not f.get('is_dir')
                      and not should_skip_local(f['name'].split('/'), f['name'].split('/')[-1])}
        elif direction == 'down' or not re.search(r'no such|not exist|not found', str(r.get('error', '')), re.I):
            return {'ok': False, 'error': r.get('error') or 'could not list the robot folder'}
        local = scan_local(local_dir) if os.path.isdir(local_dir) else {}
        plan = plan_sync(local, remote, direction)
        out = {'ok': True, 'direction': direction, 'dry_run': dry, 'new': plan['new'], 'changed': plan['changed'],
               'skipped': plan['same'], 'uploaded': [], 'deleted': [], 'would_delete': plan['extra'] if delete else []}
        if dry:
            out['would_transfer'] = plan['transfer']
            return out
        if delete and plan['extra'] and not confirm_delete:
            out['ok'] = False
            out['error'] = 'delete needs confirmation: run with dry_run first and send confirm_delete=true'
            return out
        if plan['transfer']:
            if direction == 'up':
                self._upload(local_dir, remote_dir, plan['transfer'])
            else:
                self._download(local_dir, remote_dir, plan['transfer'])
            out['uploaded'] = plan['transfer']
        if delete and plan['extra']:
            self._delete(direction, local_dir, remote_dir, plan['extra'])
            out['deleted'] = plan['extra']
        return out

    def _run_stream(self, argv, writer, timeout):
        """Run argv with stdin pipe; writer(stdin) feeds it. Returns (code, stdout, stderr)."""
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
        timer = threading.Timer(timeout, p.kill)
        timer.start()
        err = io.BytesIO()
        t = threading.Thread(target=lambda: err.write(p.stderr.read()), daemon=True)
        t.start()
        try:
            try:
                writer(p.stdin)
            finally:
                try:
                    p.stdin.close()
                except OSError:
                    pass
            out = p.stdout.read()
            code = p.wait()
        finally:
            timer.cancel()
            if p.poll() is None:
                p.kill()
        t.join(2)
        return code, out, err.getvalue().decode('utf-8', 'replace')

    def _upload(self, local_dir, remote_dir, rels):
        rd = remote_path_expr(remote_dir)
        total = sum(os.path.getsize(os.path.join(local_dir, *r.split('/'))) for r in rels)
        argv = self._remote_exec_argv('mkdir -p %s && tar -xmf - -C %s' % (rd, rd),
                                      ['extract', expand_remote(remote_dir, self.fake_home)])
        code, _, err = self._run_stream(argv, lambda w: write_tar_stream(w, local_dir, rels), 60 + total / 200000)
        if code != 0:
            kind, msg = map_ssh_error(err, code)
            if 'tar' in err.lower() and 'not found' in err.lower():
                return self._upload_scp(local_dir, remote_dir, rels)
            raise BridgeError('upload failed: ' + (msg if kind != 'other' else err.strip()[-200:] or msg))

    def _upload_scp(self, local_dir, remote_dir, rels):
        scp, host = find_exe('scp'), self.bridge.host or self.settings.get('last_host')
        if not scp or not host:
            raise BridgeError('remote tar is missing and scp is not available')
        for rel in rels:
            rpath = remote_dir.rstrip('/') + '/' + rel
            parent = rpath.rsplit('/', 1)[0]
            argv = build_ssh_argv(find_exe('ssh'), host, self.key_path(False), self.known_hosts, 'mkdir -p ' + remote_path_expr(parent),
                                 user=self.user())
            subprocess.run(argv, capture_output=True, timeout=20, **hide_flags())
            r = subprocess.run(build_scp_argv(scp, host, self.key_path(False), self.known_hosts,
                                              os.path.join(local_dir, *rel.split('/')), rpath, user=self.user()), capture_output=True, text=True, timeout=60, **hide_flags())
            if r.returncode != 0:
                raise BridgeError('scp failed for %s: %s' % (rel, r.stderr.strip()[-200:]))

    def _download(self, local_dir, remote_dir, rels):
        rd = remote_path_expr(remote_dir)
        argv = self._remote_exec_argv('tar -cf - -C %s -T -' % rd, ['create', expand_remote(remote_dir, self.fake_home)])
        os.makedirs(local_dir, exist_ok=True)
        code, out, err = self._run_stream(argv, lambda w: w.write(('\n'.join(rels) + '\n').encode()), 120)
        if code != 0:
            kind, msg = map_ssh_error(err, code)
            raise BridgeError('download failed: ' + (msg if kind != 'other' else err.strip()[-200:] or msg))
        extract_tar_stream(io.BytesIO(out), local_dir)

    def _delete(self, direction, local_dir, remote_dir, rels):
        if direction == 'down':
            for rel in rels:
                p = safe_member_path(local_dir, rel)
                if p and os.path.isfile(p):
                    os.remove(p)
            return
        rd = remote_path_expr(remote_dir)
        argv = self._remote_exec_argv("cd %s && xargs -d '\\n' -r rm -f --" % rd, ['rm', expand_remote(remote_dir, self.fake_home)])
        code, _, err = self._run_stream(argv, lambda w: w.write(('\n'.join(rels) + '\n').encode()), 60)
        if code != 0:
            raise BridgeError('delete failed: ' + err.strip()[-200:])

    # ---------------------------------------------------------------- terminals / vscode
    def _terminal_argv(self, inner_argv):
        """Returns argv that opens a system terminal running inner_argv."""
        if IS_WIN:
            cmd = '& ' + ' '.join(ps_quote(a) for a in inner_argv)
            ps = shutil.which('powershell') or 'powershell'
            return [ps, '-NoExit', '-NoProfile', '-Command', cmd], subprocess.CREATE_NEW_CONSOLE
        line = ' '.join(shlex.quote(a) for a in inner_argv)
        if sys.platform == 'darwin':
            esc = line.replace('\\', '\\\\').replace('"', '\\"')
            return ['osascript', '-e', 'tell application "Terminal" to activate', '-e',
                    'tell application "Terminal" to do script "%s"' % esc], 0
        wrapped = line + '; echo; echo "Finished. Press Enter to close."; read _x'
        for t in ('x-terminal-emulator', 'gnome-terminal', 'konsole', 'xterm'):
            exe = shutil.which(t)
            if exe:
                if t == 'gnome-terminal':
                    return [exe, '--', 'bash', '-c', wrapped], 0
                return [exe, '-e', 'bash', '-c', wrapped], 0
        raise BridgeError('no terminal program found (tried x-terminal-emulator, gnome-terminal, konsole, xterm)')

    def _launch_terminal(self, inner_argv):
        argv, flags = self._terminal_argv(inner_argv)
        # Windows: no std handles at all, so the new console window gets its own keyboard input. With
        # stdin=DEVNULL PowerShell read end-of-input and the window closed at once (seen 2026-10-24).
        kw = {'creationflags': flags} if IS_WIN else {'stdin': subprocess.DEVNULL}
        subprocess.Popen(argv, **kw)

    def _terminal_host(self):
        host = self.bridge.host if self.bridge.host and self.bridge.host != 'fake' else None
        host = host or self.settings.get('last_host') or self.args.host_override
        if not host or not valid_host(host):
            raise BridgeError('no robot address yet: press Discover or Connect first')
        return host

    def open_terminal(self):
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        try:
            host = self._terminal_host()
            argv = build_ssh_argv(ssh, host, self.key_path(), self.known_hosts, None, batch=False, user=self.user())
            self.write_known_hosts()
            self._launch_terminal(argv)
        except (BridgeError, OSError) as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def setup_key(self):
        if self.fake:
            return {'ok': True, 'fake': True, 'note': 'fake mode: no terminal'}
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        try:
            host = self._terminal_host()
            pub = self.public_key_line()
            q = shlex.quote(pub)
            remote = ("umask 077; mkdir -p ~/.ssh; grep -qxF %s ~/.ssh/authorized_keys 2>/dev/null || "
                      "echo %s >> ~/.ssh/authorized_keys" % (q, q))
            argv = build_ssh_argv(ssh, host, None, self.known_hosts, remote, batch=False, password_only=True, user=self.user())
            self.write_known_hosts()
            self._launch_terminal(argv)
        except (BridgeError, OSError) as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'note': 'Type the robot password in the terminal window that opened. The app never sees it.'}

    def open_vscode(self, req):
        code = shutil.which('code')
        if not code:
            return {'ok': False, 'error': "VS Code command 'code' not found on PATH"}
        try:
            host = self._terminal_host()
            block = ssh_config_block(host, self.key_path(), self.known_hosts, user=self.user())
        except BridgeError as e:
            return {'ok': False, 'error': str(e)}
        cfg_path = os.path.join(os.path.expanduser('~'), '.ssh', 'config')
        try:
            with open(cfg_path, encoding='utf-8', newline='') as f:
                existing = f.read()
        except OSError:
            existing = ''
        new, action = insert_ssh_config_block(existing, block)
        if action != 'unchanged' and not req.get('confirm_write_ssh_config'):
            return {'ok': False, 'needs_confirm': True, 'preview': block, 'action': action, 'file': cfg_path}
        if action != 'unchanged':
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            if existing:
                shutil.copy2(cfg_path, cfg_path + '.studio-backup')
            with open(cfg_path, 'w', encoding='utf-8', newline='') as f:
                f.write(new)
            self.log('info', 'ssh config block %s in %s (backup: config.studio-backup)' % (action, cfg_path))
        rd = (self.settings.get('remote_dir') or DEFAULT_REMOTE_DIR)
        rd = '/home/%s/%s' % (self.user(), rd[2:]) if rd.startswith('~/') else rd
        try:
            subprocess.Popen([code, '--remote', 'ssh-remote+turtlebot-studio', rd], stdin=subprocess.DEVNULL,
                             **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
        except OSError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'config': action}

    # ---------------------------------------------------------------- settings api / local files
    def trusted_list(self):
        out = [{'key': LAB_HOST_KEY, 'label': 'Built-in robot key', 'builtin': True,
                'enabled': bool(self.settings.get('builtin_host_key', True)), 'fingerprint': key_fingerprint(LAB_HOST_KEY),
                'added': None}]
        for e in self.settings.get('trusted_host_keys') or []:
            out.append({'key': e['key'], 'label': e.get('label') or 'Robot', 'builtin': False, 'enabled': True,
                        'fingerprint': key_fingerprint(e['key']), 'added': e.get('added')})
        return out

    def trusted_label(self, key):
        """Label of a trusted key (built-in key counts only while it is switched on), else None."""
        for e in self.trusted_list():
            if e['key'] == key and e['enabled']:
                return e['label']
        return None

    def get_settings(self):
        s = dict(self.settings)
        s.update({'ok': True, 'default_key': self.default_key(), 'config_dir': self.cfg, 'fake': self.fake,
                  'version': VERSION, 'motion_defaults': MOTION_FILES, 'pinned_host_key': LAB_HOST_KEY,
                  'lab_host_key': LAB_HOST_KEY, 'defaults': dict(DEFAULT_SETTINGS), 'trusted': self.trusted_list(),
                  'default_remote_dir': DEFAULT_REMOTE_DIR})
        return s

    def post_settings(self, req):
        with self.set_lock:
            upd, trust_add, trust_clear = {}, None, False
            for k in ('last_host', 'key_path', 'local_dir', 'remote_dir', 'motion_files', 'trust_host_key', 'robot_hostname',
                      'robot_user', 'hotspot_ssid', 'hotspot_addr', 'cable_addr', 'builtin_host_key', 'setup_done',
                      'auto_reconnect', 'update_check', 'update_dismissed', 'window_mode', 'ui'):
                if k not in req:
                    continue
                v = req[k]
                if k == 'motion_files':
                    if not isinstance(v, list) or not all(isinstance(x, str) and '/' not in x for x in v):
                        return {'ok': False, 'error': 'motion_files must be a list of file names'}
                elif k == 'trust_host_key':  # old one-slot setting: now an entry of trusted_host_keys
                    if v in (None, ''):
                        trust_clear = True
                    elif not KEY_LINE_RE.match(str(v).strip()):
                        return {'ok': False, 'error': 'host key must look like: ssh-ed25519 AAAA...'}
                    else:
                        trust_add = ' '.join(str(v).split()[:2])
                    continue
                elif k in ('builtin_host_key', 'setup_done', 'auto_reconnect', 'update_check'):
                    if not isinstance(v, bool):
                        return {'ok': False, 'error': k + ' must be true or false'}
                elif k == 'window_mode':
                    if v not in WINDOW_MODES:
                        return {'ok': False, 'error': 'window_mode must be app or browser'}
                elif k == 'ui':
                    if v not in UI_CHOICES:
                        return {'ok': False, 'error': 'ui must be v2 or classic'}
                elif k == 'update_dismissed':
                    if v not in (None, '') and not (isinstance(v, str) and VERSION_RE.match(v)):
                        return {'ok': False, 'error': 'update_dismissed must be a version number'}
                elif k in DEFAULT_SETTINGS:
                    v = DEFAULT_SETTINGS[k] if v in (None, '') else v
                    ok = isinstance(v, str)
                    if ok and k == 'robot_hostname':
                        ok = bool(DNS_LABEL_RE.match(v))
                    elif ok and k == 'robot_user':
                        ok = bool(USER_RE.match(v))
                    elif ok and k == 'hotspot_ssid':
                        ok = valid_ssid(v)
                    elif ok:
                        ok = valid_host(v) and '@' not in v
                    if not ok:
                        return {'ok': False, 'error': 'invalid ' + k.replace('_', ' ')}
                elif k == 'last_host':
                    if v and not valid_host(v):
                        return {'ok': False, 'error': 'invalid host'}
                elif v is not None and not isinstance(v, str):
                    return {'ok': False, 'error': k + ' must be text'}
                upd[k] = (v or None) if k not in ('motion_files', 'builtin_host_key', 'setup_done', 'auto_reconnect', 'update_check') else v
            self.settings.update(upd)
            if not self.settings.get('remote_dir'):
                self.settings['remote_dir'] = DEFAULT_REMOTE_DIR
            if trust_clear:
                self.settings['trusted_host_keys'] = [e for e in self.settings['trusted_host_keys'] if e.get('label') != LEGACY_TRUST_LABEL]
            if trust_add:
                self._add_trusted(trust_add, LEGACY_TRUST_LABEL)
            self.save_settings()
            self.write_known_hosts()
        if trust_add:
            self.log('warn', 'a different robot host key is trusted (settings): only do this for another TurtleBot')
        return self.get_settings()

    def _add_trusted(self, key, label):
        """Caller holds set_lock. The built-in key is switched on instead of being listed twice."""
        if key == LAB_HOST_KEY:
            self.settings['builtin_host_key'] = True
            return
        for e in self.settings['trusted_host_keys']:
            if e['key'] == key:
                e['label'] = label
                return
        self.settings['trusted_host_keys'].append({'key': key, 'label': label, 'added': int(time.time())})

    # ---------------------------------------------------------------- v1.2: first-run wizard
    def ssh_version(self, ssh):
        if self._ssh_ver is not None and self._ssh_ver[0] == ssh:
            return self._ssh_ver[1]
        ver = None
        try:
            r = subprocess.run([ssh, '-V'], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL, **hide_flags())
            lines = ((r.stderr or '') + (r.stdout or '')).strip().splitlines()
            ver = lines[0].strip()[:120] if lines else None
        except (OSError, subprocess.TimeoutExpired):
            pass
        self._ssh_ver = (ssh, ver)
        return ver

    def key_info(self):
        k = os.path.expanduser(self.settings.get('key_path') or self.default_key())
        exists, fp = os.path.isfile(k), None
        if exists:
            try:
                with open(k + '.pub', encoding='utf-8') as f:
                    line = f.read().strip()
                if PUB_LINE_RE.match(line):
                    fp = key_fingerprint(line)
            except OSError:
                pass
        return {'path': k, 'exists': exists, 'fingerprint': fp}

    def setup_status(self):
        ssh = find_exe('ssh')
        osname = 'windows' if IS_WIN else ('macos' if sys.platform == 'darwin' else 'linux')
        return {'ok': True, 'ssh': {'found': bool(ssh), 'path': ssh, 'version': self.ssh_version(ssh) if ssh else None},
                'keygen': {'found': bool(find_exe('ssh-keygen'))}, 'keyscan': {'found': bool(find_exe('ssh-keyscan'))},
                'key': self.key_info(), 'host': self.settings.get('last_host'), 'setup_done': bool(self.settings.get('setup_done')),
                'fake': self.fake, 'os': osname, 'user': self.user()}

    def create_key(self):
        try:
            k = os.path.expanduser(self.settings.get('key_path') or self.default_key())
            existed = os.path.isfile(k)
            self.key_path(create=True)
        except (BridgeError, OSError, subprocess.TimeoutExpired) as e:
            return {'ok': False, 'error': str(e)}
        info = self.key_info()
        return {'ok': True, 'path': info['path'], 'fingerprint': info['fingerprint'], 'created': not existed}

    def scan_host_key(self, req):
        host = strip_user(str(req.get('host') or self.settings.get('last_host') or '').strip())
        if not host or not valid_host(host):
            return {'ok': False, 'error': 'enter the robot address first', 'kind': 'other'}
        if self.fake:
            key = FAKE_HOST_KEY
        else:
            ks = find_exe('ssh-keyscan')
            if not ks:
                return {'ok': False, 'error': 'ssh-keyscan not found (install the OpenSSH client)', 'kind': 'no_ssh'}
            try:
                r = subprocess.run([ks, '-T', '6', '-t', 'ed25519', host], capture_output=True, text=True, timeout=15,
                                   stdin=subprocess.DEVNULL, **hide_flags())
            except (OSError, subprocess.TimeoutExpired) as e:
                return {'ok': False, 'error': 'could not run ssh-keyscan: %s' % e, 'kind': 'other'}
            key = parse_keyscan(r.stdout)
            if not key:
                return {'ok': False, 'kind': 'unreachable', 'error': 'no host key received from %s (is the robot on and reachable, '
                                                                      'and is SSH running?)' % host}
        label = self.trusted_label(key)
        return {'ok': True, 'host': host, 'key': key, 'fingerprint': key_fingerprint(key), 'trusted': label is not None,
                'label': label}

    def trust_key(self, req):
        key = req.get('key')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not isinstance(key, str) or not KEY_LINE_RE.match(key.strip()):
            return {'ok': False, 'error': 'host key must look like: ssh-ed25519 AAAA...'}
        key = ' '.join(key.split()[:2])
        label = ''.join(c for c in str(req.get('label') or '') if c.isprintable()).strip()[:60] or 'Robot'
        with self.set_lock:
            self._add_trusted(key, label)
            self.save_settings()
            self.write_known_hosts()
        self.log('info', 'trusted a robot host key (%s, %s)' % (label, key_fingerprint(key)))
        return {'ok': True, 'key': key, 'fingerprint': key_fingerprint(key), 'label': label, 'trusted': self.trusted_list()}

    def untrust_key(self, req):
        key = req.get('key')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not isinstance(key, str) or not KEY_LINE_RE.match(key.strip()):
            return {'ok': False, 'error': 'host key must look like: ssh-ed25519 AAAA...'}
        key = ' '.join(key.split()[:2])
        with self.set_lock:
            if key == LAB_HOST_KEY:
                self.settings['builtin_host_key'] = False
            else:
                keep = [e for e in self.settings['trusted_host_keys'] if e['key'] != key]
                if len(keep) == len(self.settings['trusted_host_keys']):
                    return {'ok': False, 'error': 'that key is not in the trusted list'}
                self.settings['trusted_host_keys'] = keep
            self.save_settings()
            self.write_known_hosts()
        self.log('info', 'removed a trusted robot host key (%s)' % key_fingerprint(key))
        return {'ok': True, 'trusted': self.trusted_list()}

    def test_login(self, req):
        if self.fake:
            return {'ok': True, 'hostname': 'fake-turtlebot4', 'fake': True}
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'kind': 'no_ssh', 'error': 'ssh not found: install the OpenSSH client'}
        host = strip_user(str(req.get('host') or '').strip())
        try:
            host = host or self._terminal_host()
            if not valid_host(host):
                return {'ok': False, 'kind': 'other', 'error': 'invalid host name or address'}
            key = self.key_path(create=False)
        except BridgeError as e:
            return {'ok': False, 'kind': 'other', 'error': str(e)}
        if not os.path.isfile(key):
            return {'ok': False, 'kind': 'key_missing', 'error': 'no ssh key yet: create one first'}
        self.write_known_hosts()
        argv = build_ssh_argv(ssh, host, key, self.known_hosts, 'echo studio-login-ok; hostname', connect_timeout=8,
                              user=self.user())
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL, **hide_flags())
        except subprocess.TimeoutExpired:
            return {'ok': False, 'kind': 'unreachable', 'error': 'robot not reachable (timed out)'}
        except OSError as e:
            return {'ok': False, 'kind': 'other', 'error': str(e)}
        lines = [x.strip() for x in (r.stdout or '').splitlines() if x.strip()]
        if r.returncode == 0 and lines and lines[0] == 'studio-login-ok':
            return {'ok': True, 'hostname': lines[1] if len(lines) > 1 else None}
        kind, msg = map_ssh_error(r.stderr, r.returncode)
        return {'ok': False, 'kind': kind, 'error': msg}

    def local_files(self, req):
        d = req.get('dir') or self.settings.get('local_dir')
        if not d or not os.path.isdir(os.path.expanduser(d)):
            return {'ok': False, 'error': 'folder not found: %s' % d}
        files = scan_local(os.path.expanduser(d))
        items = [{'name': k, 'size': v['size'], 'mtime': v['mtime'], 'sha1': v['sha1']} for k, v in sorted(files.items())][:5000]
        return {'ok': True, 'dir': os.path.abspath(os.path.expanduser(d)), 'files': items}

    # ---------------------------------------------------------------- v1.1: catalog, templates, motion decision
    def catalog(self):
        return load_catalog(self.catalog_path, self.templates_dir)

    def template_text(self, name):
        if not TEMPLATE_NAME_RE.match(name or '') or name not in list_templates(self.templates_dir):
            return None
        try:
            with open(os.path.join(self.templates_dir, name), 'rb') as f:
                return f.read().decode('utf-8')
        except (OSError, UnicodeDecodeError):
            return None

    def motion_for_run(self, cmd):
        """Sets cmd['motion'] (never lowers an explicit True) and returns the reasons."""
        path = str(cmd.get('path', ''))
        base = os.path.basename(path)
        cat = self.catalog()['programs']
        reasons_known = decide_motion(base, cat, self.settings.get('motion_files'), None)
        if reasons_known[0] or cmd.get('motion'):
            cmd['motion'] = True
            return reasons_known[1] or ['requested']
        described = None
        try:
            r = self.bridge.request({'cmd': 'describe', 'dir': cmd.get('dir') or DEFAULT_REMOTE_DIR}, 10)
            if r.get('ok'):
                described = next((p for p in r.get('programs', []) if p.get('name') == path or p.get('name') == base), None)
            else:
                described = 'unavailable'
        except BridgeError:
            described = 'unavailable'
        motion, reasons = decide_motion(base, cat, self.settings.get('motion_files'), described)
        cmd['motion'] = bool(motion)
        return reasons

    # ---------------------------------------------------------------- v1.1: laptop network, known addresses
    def laptop_net(self):
        osname = 'windows' if IS_WIN else ('macos' if sys.platform == 'darwin' else 'linux')
        if self.fake and not os.environ.get('STUDIO_REAL_LAPTOP_NET'):
            # the simulated robot gets a simulated computer network too, so screenshots and tests never show the real one
            return {'ok': True, 'wifi': {'ssid': 'HomeNet', 'signal_pct': 80, 'state': 'connected', 'interface': 'Wi-Fi'},
                    'wired': [], 'os': osname, 'fake': True}
        box = {}
        ths = [threading.Thread(target=lambda: box.__setitem__('wifi', laptop_wifi()), daemon=True),
               threading.Thread(target=lambda: box.__setitem__('wired', laptop_wired()), daemon=True)]
        for t in ths:
            t.start()
        for t in ths:
            t.join(8)
        return {'ok': True, 'wifi': box.get('wifi'), 'wired': box.get('wired') or [], 'os': osname}

    # ---------------------------------------------------------------- mapping (2.1)
    def on_map(self, ev):
        """A bridge `map` event: keep the picture, publish the same event without its data."""
        try:
            if ev.get('encoding') != 'cells':
                raise ValueError('live map must use the cells encoding')
            meta, gray = decode_map_payload(ev)
            png = png_gray(meta['width'], meta['height'], gray)
        except (ValueError, KeyError) as e:
            self.log('warn', 'bad map event dropped: %s' % e)
            return
        self.maps.set_map(meta, png)
        self.bus.publish(dict(meta, ev='map'))

    def mapping_info(self):
        info = self.maps.get_info()
        return dict(info, ok=True) if info else {'ok': True, 'state': 'unknown'}

    def map_preview_png(self, name, max_px):
        """(status, body, content type) of a saved map's preview picture; body is a dict for an error."""
        if not valid_map_name(name):
            return 400, {'ok': False, 'error': 'bad map name'}, None
        try:
            r = self.bridge.request({'cmd': 'map_preview', 'name': name, 'max_px': max_px}, 30)
        except BridgeError as e:
            return (409 if str(e) == 'not connected' else 502), {'ok': False, 'error': str(e)}, None
        if not r.get('ok'):
            err = str(r.get('error') or 'the robot refused')
            return (404 if re.search(r'no such|not found|missing', err, re.I) else 502), {'ok': False, 'error': err}, None
        try:
            meta, gray = decode_map_payload(r)
            return 200, png_gray(meta['width'], meta['height'], gray), 'image/png'
        except (ValueError, KeyError) as e:
            return 502, {'ok': False, 'error': 'bad preview from the robot: %s' % e}, None

    def map_download_zip(self, name):
        """(status, body, content type): the existing files of a saved map as a zip, built in memory."""
        if not valid_map_name(name):
            return 400, {'ok': False, 'error': 'bad map name'}, None
        try:
            r = self.bridge.request({'cmd': 'maps_list'}, 15)
        except BridgeError as e:
            return (409 if str(e) == 'not connected' else 502), {'ok': False, 'error': str(e)}, None
        if not r.get('ok'):
            return 502, {'ok': False, 'error': str(r.get('error') or 'the robot refused')}, None
        entry = next((m for m in r.get('maps') or [] if isinstance(m, dict) and m.get('name') == name), None)
        if entry is None:
            return 404, {'ok': False, 'error': 'no such map'}, None
        files = entry.get('files') if isinstance(entry.get('files'), dict) else {}
        rels = [name + ext for key, ext in MAP_FILE_EXTS if files.get(key) is not None]
        if not rels:
            return 404, {'ok': False, 'error': 'the map has no files'}, None
        tmp = tempfile.mkdtemp(prefix='studio_map_')
        try:
            self._download(tmp, MAP_REMOTE_DIR, rels)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                for rel in rels:
                    p = os.path.join(tmp, rel)
                    if os.path.isfile(p):
                        z.write(p, rel)
            return 200, buf.getvalue(), 'application/zip'
        except (BridgeError, OSError, ValueError, tarfile.TarError) as e:
            return 502, {'ok': False, 'error': str(e)}, None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def route_upload(self, req):
        """Copy a route folder (files as base64) to ~/robot_code/routes/<name> on the robot; never overwrites a route."""
        name = req.get('name')
        ok, info = validate_route_upload(name, req.get('files'))
        if not ok:
            return {'ok': False, 'error': info}
        try:
            r = self.bridge.request({'cmd': 'routes_list'}, 15)
            if not r.get('ok'):
                return {'ok': False, 'error': str(r.get('error') or 'the robot refused')}
            if any(isinstance(x, dict) and x.get('name') == name for x in r.get('routes') or []):
                return {'ok': False, 'error': 'a route named %s already exists on the robot' % name, 'exists': True}
            tmp = tempfile.mkdtemp(prefix='studio_route_')
            try:
                rels = []
                for rel, data in info:
                    with open(os.path.join(tmp, rel), 'wb') as f:
                        f.write(data)
                    rels.append(rel)
                self._upload(tmp, '~/robot_code/routes/' + name, rels)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            r = self.bridge.request({'cmd': 'routes_list'}, 15)
            entry = next((x for x in (r.get('routes') or []) if isinstance(x, dict) and x.get('name') == name), None)                 if r.get('ok') else None
            return {'ok': True, 'name': name, 'route': entry}
        except (BridgeError, OSError) as e:
            return {'ok': False, 'error': str(e)}

    def on_status(self, ev):
        """Record metrics and raise alerts, then remember the robot's Wi-Fi address per SSID (client mode only)."""
        try:
            self.history.add(ev)
            self.alerts.check_status(ev, is_status_moving(ev, self.tele_armed))
        except Exception as e:
            self.log('warn', 'status bookkeeping failed: %s' % e)
        try:
            net = ev.get('net') or {}
            ssid, ip = net.get('ssid'), (net.get('addresses') or {}).get('wlan0')
            if net.get('wifi_mode') != 'client' or not ssid or not ip or not valid_host(ip):
                return
            known = self.settings.setdefault('known_addresses', {})
            old = known.get(ssid) or {}
            if old.get('ip') != ip or time.time() - old.get('seen', 0) > 3600:
                known[ssid] = {'ip': ip, 'seen': int(time.time())}
                self.save_settings()
        except Exception:
            pass

    # ---------------------------------------------------------------- v1.3: diagnostics
    def diagnostics(self):
        """Plain text for a bug report. Everything goes through redact(); no password or token is ever collected."""
        s, L = self.settings, []

        def sec(title):
            L.extend(['', '== %s ==' % title])

        def kv(k, v):
            L.append('%s: %s' % (k, v if v not in (None, '') else '-'))
        L.append('TurtleBot Studio diagnostics (%s)' % time.strftime('%Y-%m-%d %H:%M:%S'))
        sec('Studio')
        kv('Version', VERSION)
        kv('Running as', 'built app' if FROZEN else 'source (python studio.py)')
        kv('Fake robot mode', 'yes' if self.fake else 'no')
        sec('This computer')
        kv('Operating system', platform.platform())
        kv('Python', sys.version.split()[0])
        ssh = find_exe('ssh')
        kv('ssh -V', (self.ssh_version(ssh) or 'ssh found, version unknown') if ssh else 'ssh NOT FOUND')
        kv('Config folder', self.cfg)
        if self.fake:
            kv('Wi-Fi / wired', 'not queried (fake mode)')
        else:
            try:
                ln = self.laptop_net()
                wifi = ln.get('wifi') or {}
                kv('Wi-Fi name', wifi.get('ssid') if wifi else 'not connected / no Wi-Fi')
                kv('Wired connection up', 'yes' if any(w.get('up') for w in ln.get('wired') or []) else 'no')
            except Exception as e:
                kv('Wi-Fi / wired', 'could not read (%s)' % e)
        sec('Settings')
        for k in ('robot_hostname', 'robot_user', 'last_host', 'last_via', 'hotspot_ssid', 'hotspot_addr', 'cable_addr'):
            kv(k, route_words(s.get(k)) if k == 'last_via' else s.get(k))
        ki = self.key_info()
        kv('ssh key file present', 'yes' if ki['exists'] else 'no')
        kv('ssh key fingerprint (public)', ki['fingerprint'])
        tl = self.trusted_list()
        kv('Trusted robots', '%d (%s)' % (sum(1 for t in tl if t['enabled']),
                                          ', '.join(t['label'] for t in tl if t['enabled']) or 'none'))
        kv('Built-in lab key', 'on' if s.get('builtin_host_key', True) else 'off')
        kv('auto_reconnect', 'on' if s.get('auto_reconnect', True) else 'off')
        kv('update_check', 'on' if s.get('update_check', True) else 'off')
        kv('window_mode', s.get('window_mode', DEFAULT_WINDOW_MODE))
        sec('Connection')
        c = self.bus.last_conn
        kv('State', c.get('state'))
        kv('Host', c.get('host'))
        kv('Reached over', route_words(c.get('via')))
        kv('Last error', c.get('error'))
        if c.get('state') == 'reconnecting':
            kv('Reconnect attempt', c.get('attempt'))
        sec('Last robot search')
        if not self.last_cands:
            L.append('(none yet)')
        for cd in self.last_cands:
            L.append('%s  reachable=%s  %s ms%s' % (cd.get('host'), 'yes' if cd.get('reachable') else 'no', cd.get('ms'),
                                                     '  identity=' + cd['identity'] if cd.get('identity') else ''))
        sec('Robot status')
        st = self.bus.last_status if self.bridge.connected else None
        if not st:
            L.append('(not connected)')
        else:
            net = st.get('net') or {}
            kv('Battery %', (st.get('battery') or {}).get('percent'))
            kv('Robot Wi-Fi mode', net.get('wifi_mode'))
            kv('Robot Wi-Fi name', net.get('ssid'))
            kv('Robot IP addresses', ', '.join('%s=%s' % (k, v) for k, v in (net.get('addresses') or {}).items()))
        sec('Last 60 log lines')
        with self.bus.lock:
            logs = list(self.bus.logs)[-60:]
        for e in logs:
            L.append('%s %s %s' % (time.strftime('%H:%M:%S', time.localtime(e.get('t') or time.time())), e.get('level'), e.get('text')))
        return {'ok': True, 'text': redact('\n'.join(L) + '\n', secrets=(self.token,))}

    # ---------------------------------------------------------------- v1.3: update notice
    def update_status(self):
        with self.update_lock:
            u = dict(self.update)
        newer = bool(u['latest']) and version_newer(u['latest'], VERSION)
        return {'ok': True, 'current': VERSION, 'latest': u['latest'], 'page': u['page'] or DEFAULT_UPDATE_PAGE,
                'notes': u['notes'], 'newer': newer, 'checked': u['checked'], 'error': u['error'],
                'dismissed': self.settings.get('update_dismissed')}

    def check_updates(self, force=False):
        """Reads version.json from GitHub (or STUDIO_UPDATE_URL): at most once a day unless forced. Sends nothing
        about this computer. Every failure (offline, file not published yet) is silent apart from one log line."""
        if not force:
            last = (self.settings.get('update_last') or {}).get('t') or 0
            if not self.settings.get('update_check', True) or time.time() - last < UPDATE_EVERY:
                return self.update_status()
        url = os.environ.get('STUDIO_UPDATE_URL') or DEFAULT_UPDATE_URL
        info, err = None, None
        try:
            parts = urllib.parse.urlsplit(url)
            if parts.scheme not in ('http', 'https') or not parts.hostname:
                raise ValueError('not an http(s) address')
            req = urllib.request.Request(url, headers={'User-Agent': 'TurtleBotStudio/' + VERSION})
            local = parts.hostname in ('127.0.0.1', 'localhost', '::1')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if local else urllib.request.build_opener()
            with opener.open(req, timeout=5) as r:
                raw = r.read(65536)
            info = parse_update_info(raw)
            if info is None:
                err = 'the version file is not understood'
        except Exception as e:
            err = str(e)[:120] or type(e).__name__
        now = time.time()
        with self.update_lock:
            self.update['checked'] = now
            if info:
                self.update.update(latest=info['version'], page=info['page'], notes=info['notes'], error=None)
            else:
                self.update['error'] = err
        if info:
            with self.set_lock:
                self.settings['update_last'] = {'t': now, 'latest': info['version']}
                self.save_settings()
        elif not self._update_logged:
            self._update_logged = True
            self.log('info', 'update check skipped: %s' % err)
        st = self.update_status()
        st['result'] = 'failed' if not info else 'newer' if st['newer'] else 'latest'
        if st['newer']:
            self.bus.publish({'ev': 'update', 'current': VERSION, 'latest': st['latest'], 'page': st['page'], 'notes': st['notes']})
        return st

    def start_update_check(self):
        """5 s after start (hidden --update-delay), in the background. Not in --fake unless STUDIO_UPDATE_URL is set."""
        if self.fake and not os.environ.get('STUDIO_UPDATE_URL'):
            return
        t = threading.Timer(self.update_delay, self.check_updates)
        t.daemon = True
        t.start()

    # ---------------------------------------------------------------- v1.1: Wi-Fi help
    def _robot_script_terminal(self, script, args):
        ssh = find_exe('ssh')
        if not ssh:
            return {'ok': False, 'error': 'ssh not found: install the OpenSSH client'}
        if self.fake:
            return {'ok': False, 'error': 'not available in fake mode (no real robot)'}
        if not self.bridge.connected:
            return {'ok': False, 'error': 'connect to the robot first (cable or its hotspot)'}
        try:
            host = self._terminal_host()
            argv = build_ssh_argv(ssh, host, self.key_path(), self.known_hosts, build_robot_script_cmd(script, *args),
                                  batch=False, tty=True, user=self.user())
            self.write_known_hosts()
            self._launch_terminal(argv)
        except (BridgeError, OSError, ValueError) as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def robot_wifi_add(self, req):
        """Join any WPA2-personal network. The Wi-Fi password goes to the bridge once, in memory, and never into a
        log, a reply, argv, the environment or a file; this wrapper makes sure no error path can echo it."""
        try:
            return self._robot_wifi_add(req)
        except Exception as e:
            self.log('error', 'Wi-Fi add failed (%s)' % type(e).__name__)
            return {'ok': False, 'error': 'internal error (%s)' % type(e).__name__}
        finally:
            if isinstance(req, dict) and 'psk' in req:
                req['psk'] = None

    def _robot_wifi_add(self, req):
        ssid, psk = req.get('ssid'), req.get('psk')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not valid_ssid(ssid):
            return {'ok': False, 'error': 'invalid network name (empty, line break, or longer than 32 bytes)'}
        if ssid == self.settings['hotspot_ssid'] or ssid in PROTECTED_CONNECTIONS:
            return {'ok': False, 'error': "'%s' is the robot's own hotspot name and cannot be added as a network" % ssid}
        if not valid_psk(psk):
            return {'ok': False, 'error': 'the Wi-Fi password must have 8 to 63 characters (or be 64 hex digits)'}
        if not self.bridge.connected:
            return {'ok': False, 'error': 'connect to the robot first (cable or its hotspot)'}
        connect_now = bool(req.get('connect_now'))
        try:
            info = self.bridge.request({'cmd': 'wifi_info'}, 12)
        except BridgeError as e:
            return {'ok': False, 'error': str(e)}
        if info.get('ok') and any(ssid in (x.get('name'), x.get('ssid')) for x in info.get('saved') or []):
            return {'ok': False, 'error': 'a network with this name is already saved on the robot: remove it first'}
        nonce = secrets.token_hex(16)
        try:
            r = self.bridge.request({'cmd': 'wifi_secret_put', 'nonce': nonce, 'psk': psk, 'ttl': WIFI_SECRET_TTL}, 10)
        except BridgeError as e:
            return {'ok': False, 'error': 'could not hand the Wi-Fi password to the robot: %s' % e}
        if not r.get('ok'):
            return {'ok': False, 'error': 'the robot did not accept the Wi-Fi password: %s' % str(r.get('error'))[:120]}
        if self.fake:
            try:
                r = self.bridge.request({'cmd': 'wifi_fake_add', 'nonce': nonce, 'ssid': ssid, 'connect_now': connect_now}, 10)
            except BridgeError as e:
                return {'ok': False, 'error': str(e)}
            if not r.get('ok'):
                return {'ok': False, 'error': str(r.get('error'))[:200]}
            res = {'ok': True, 'fake': True, 'note': 'fake mode: no terminal, the robot is simulated'}
        else:
            res = self._robot_script_terminal(wifi_add_script(), [b64s(ssid), safe_conn_filename(ssid), '1' if connect_now else '0',
                                                                 nonce, str(WIFI_JOIN_TIMEOUT)])
            if not res.get('ok'):
                try:
                    self.bridge.request({'cmd': 'wifi_secret_drop', 'nonce': nonce}, 5)
                except BridgeError:
                    pass
                return res
            res['note'] = ('A terminal opened. Type only the robot (sudo) password there. The Wi-Fi password was sent from '
                           'here, is kept in the robot\'s memory for 3 minutes and never written to a log or file.')
        self.wifi_jobs[nonce] = ssid
        while len(self.wifi_jobs) > 8:
            self.wifi_jobs.popitem(last=False)
        self.log('info', 'Wi-Fi add requested for %s (connect now: %s)' % (''.join(c if c.isprintable() else '?' for c in ssid),
                                                                          'yes' if connect_now else 'no'))
        res.update({'nonce': nonce, 'ssid': ssid, 'connect_now': connect_now, 'ttl': WIFI_SECRET_TTL, 'timeout': WIFI_JOIN_TIMEOUT})
        return res

    def robot_wifi_status(self, req):
        nonce = req.get('nonce')
        if nonce is not None and not (isinstance(nonce, str) and NONCE_RE.match(nonce)):
            return {'ok': False, 'error': 'invalid nonce'}
        cmd = {'cmd': 'wifi_join_status'}
        if nonce:
            cmd['nonce'] = nonce
        try:
            r = self.bridge.request(cmd, 8)
        except BridgeError as e:
            return {'ok': False, 'error': str(e), 'kind': 'not_connected'}
        if not r.get('ok'):
            return {'ok': False, 'error': str(r.get('error'))[:200]}
        join, stored = r.get('join'), False
        want = self.wifi_jobs.get(nonce) if nonce else None
        if isinstance(join, dict) and want is not None and join.get('ssid') != want:
            join = None  # an old result file of another network
        if isinstance(join, dict) and join.get('state') == 'joined' and isinstance(join.get('ssid'), str) \
                and isinstance(join.get('ip'), str) and valid_host(join['ip']):
            with self.set_lock:
                known = self.settings.setdefault('known_addresses', {})
                known[join['ssid']] = {'ip': join['ip'], 'seen': int(time.time()), 't': int(time.time())}
                self.save_settings()
            stored = True
        return {'ok': True, 'secret': r.get('secret') or 'none', 'join': join, 'stored': stored}

    def robot_wifi_remove(self, req):
        name = req.get('name')
        if req.get('confirm') is not True:
            return {'ok': False, 'error': 'confirmation needed'}
        if not isinstance(name, str) or not name or '\n' in name or '\r' in name or '\x00' in name or len(name.encode('utf-8')) > 120:
            return {'ok': False, 'error': 'invalid connection name'}
        hs = self.settings['hotspot_ssid']
        if name in PROTECTED_CONNECTIONS or name in (hs, 'netplan-wlan0-' + hs):
            return {'ok': False, 'error': "'%s' is the robot's own hotspot or cable link and cannot be removed here" % name}
        res = self._robot_script_terminal(WIFI_REMOVE_SCRIPT, [b64s(name)])
        if res.get('ok'):
            self.log('info', 'Wi-Fi remove requested for %s' % ''.join(c if c.isprintable() else '?' for c in name))
        return res

    def laptop_wifi_settings(self):
        try:
            if IS_WIN:
                os.startfile('ms-settings:network-wifi')  # noqa: S606 (fixed, harmless URI)
            elif sys.platform == 'darwin':
                r = subprocess.run(['open', 'x-apple.systempreferences:com.apple.Network-Settings.extension'], capture_output=True)
                if r.returncode != 0:
                    subprocess.run(['open', '/System/Library/PreferencePanes/Network.prefPane'], capture_output=True)
            else:
                for argv in (['nm-connection-editor'], ['gnome-control-center', 'wifi']):
                    if shutil.which(argv[0]):
                        subprocess.Popen(argv, stdin=subprocess.DEVNULL)
                        break
                else:
                    return {'ok': False, 'error': 'no Wi-Fi settings program found (open your desktop network settings)'}
        except OSError as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def join_hotspot(self):
        warn = 'While your computer is on the robot hotspot it has no internet (unless it has a second connection).'
        if not IS_WIN:
            return {'ok': False, 'needs_settings': True, 'warning': warn,
                    'error': 'Join the Wi-Fi "%s" in your computer Wi-Fi settings.' % self.settings['hotspot_ssid']}
        hs = self.settings['hotspot_ssid']
        profiles = parse_netsh_profiles(_run_quiet(['netsh', 'wlan', 'show', 'profiles'], 4))
        name = next((p for p in profiles if p.lower() == hs.lower()), None)
        if not name:
            return {'ok': False, 'needs_settings': True, 'warning': warn,
                    'error': 'This computer has no saved "%s" network yet. Join it once in Wi-Fi settings.' % hs}
        try:
            r = subprocess.run(['netsh', 'wlan', 'connect', 'name=' + name], capture_output=True, text=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {'ok': False, 'error': str(e), 'warning': warn}
        out = (r.stdout or '').strip()
        return {'ok': r.returncode == 0, 'warning': warn, 'detail': out[-200:],
                'error': None if r.returncode == 0 else (out or 'netsh failed')}

    def quit(self):
        """Quit Studio button: answer first, then stop cleanly (the page shows 'Studio has stopped')."""
        self.log('info', 'Quit requested from the page')
        self.teleop_off('Studio is quitting.', 1.5)
        self.bus.publish({'ev': 'quit'})
        t = threading.Timer(0.4, lambda: self.stop_cb() if self.stop_cb else None)
        t.daemon = True
        t.start()
        return {'ok': True}

    def shutdown(self):
        self.closing = True
        self.teleop_off('Studio is quitting.', 1.5)
        self.reconnect_cancel(quiet=True)
        try:
            self.bridge.stop()
        except Exception:
            pass
        self.bus.close_all()


# ============================================================================ discovery helpers


def has_cable_v4():
    """True if this computer has a 192.168.185.x address (route to the robot's cable address exists)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('192.168.185.3', 9))
        ip = s.getsockname()[0]
        s.close()
        return ip.startswith('192.168.185.')
    except OSError:
        return False


WIN_NEIGH_PS = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "$a = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object { $_.OperationalStatus -eq 'Up' -and $_.NetworkInterfaceType -eq 'Ethernet' } | ForEach-Object { $_.GetIPProperties().GetIPv6Properties().Index }; "
    "$p = foreach ($i in $a) { Start-Process -FilePath ping.exe -ArgumentList '-n','1','-w','500',('ff02::1%' + $i) "
    "-WindowStyle Hidden -PassThru }; if ($p) { $p | Wait-Process -Timeout 2 }; "
    "Get-NetNeighbor -AddressFamily IPv6 | Where-Object { $_.LinkLayerAddress } | "
    "Select-Object IPAddress,LinkLayerAddress,InterfaceIndex | ConvertTo-Json -Compress")


def _run_quiet(argv, timeout):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           **({'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WIN else {}))
        return r.stdout or ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def find_cable_ipv6(timeout=3.2):
    """Link-local IPv6 addresses (with %scope) of Raspberry Pi devices on wired links."""
    if IS_WIN:
        ps = shutil.which('powershell') or 'powershell'
        return parse_windows_neighbors(_run_quiet([ps, '-NoProfile', '-NonInteractive', '-Command', WIN_NEIGH_PS], timeout))
    ifs = []
    try:
        ifs = [n for _, n in socket.if_nameindex() if n != 'lo' and not n.startswith(('docker', 'veth', 'br-', 'virbr', 'utun', 'awdl', 'llw', 'bridge'))]
    except (OSError, AttributeError):
        pass
    ping6 = shutil.which('ping6') if sys.platform == 'darwin' else None
    ths = []
    for n in ifs[:8]:
        if sys.platform == 'darwin':
            argv = [ping6 or 'ping6', '-c', '1', '-i', '0.5', 'ff02::1%' + n]
        else:
            argv = ['ping', '-6', '-c', '1', '-W', '1', 'ff02::1%' + n]
        th = threading.Thread(target=_run_quiet, args=(argv, 2.0), daemon=True)
        th.start()
        ths.append(th)
    for th in ths:
        th.join(2.2)
    if sys.platform == 'darwin':
        return parse_ndp(_run_quiet(['ndp', '-an'], 2))
    return parse_ip6_neigh(_run_quiet(['ip', '-6', 'neigh'], 2))


# ---- v1.3: the sweep behind "Search the whole network" (explicit button only; one /24 per network, port 22) ----
WIN_IPV4_PS = ("$ErrorActionPreference='SilentlyContinue'; Get-NetIPAddress -AddressFamily IPv4 | "
               "Select-Object IPAddress,PrefixLength,InterfaceAlias | ConvertTo-Json -Compress")
WIN_NEIGH4_PS = ("$ErrorActionPreference='SilentlyContinue'; Get-NetNeighbor -AddressFamily IPv4 | "
                 "Where-Object { $_.LinkLayerAddress } | Select-Object IPAddress,LinkLayerAddress | ConvertTo-Json -Compress")


def local_ipv4_ifaces():
    if IS_WIN:
        ps = shutil.which('powershell') or 'powershell'
        return parse_win_ipv4(_run_quiet([ps, '-NoProfile', '-NonInteractive', '-Command', WIN_IPV4_PS], 8))
    if sys.platform == 'darwin':
        return parse_ifconfig(_run_quiet(['ifconfig'], 4))
    return parse_ip4_addr(_run_quiet(['ip', '-4', '-o', 'addr'], 4))


def neighbor_table_v4():
    if IS_WIN:
        ps = shutil.which('powershell') or 'powershell'
        return parse_win_neigh4(_run_quiet([ps, '-NoProfile', '-NonInteractive', '-Command', WIN_NEIGH4_PS], 8))
    if sys.platform == 'darwin':
        return parse_arp_an(_run_quiet(['arp', '-an'], 4))
    return parse_ip4_neigh(_run_quiet(['ip', '-4', 'neigh'], 4))


def tcp_sweep(targets, progress=None, deadline=DEEP_DEADLINE, timeout=DEEP_CONNECT_TIMEOUT, workers=DEEP_WORKERS, port=22):
    """TCP connect to `port` on every target. Returns {ip: connect ms} of the hosts that answered. Stops at `deadline` s."""
    todo = queue.Queue()
    for t in targets:
        todo.put(t)
    found, lock, done = {}, threading.Lock(), [0]
    stop_at = time.time() + deadline

    def work():
        while time.time() < stop_at:
            try:
                ip = todo.get_nowait()
            except queue.Empty:
                return
            t0 = time.time()
            try:
                socket.create_connection((ip, port), timeout=timeout).close()
                ok = True
            except OSError:
                ok = False
            with lock:
                done[0] += 1
                if ok:
                    found[ip] = int((time.time() - t0) * 1000)
    ths = [threading.Thread(target=work, daemon=True) for _ in range(min(workers, len(targets)))]
    for th in ths:
        th.start()
    last = -1
    while any(th.is_alive() for th in ths):
        time.sleep(0.15)
        if progress and done[0] != last:
            last = done[0]
            progress(last, len(targets))
    if progress and done[0] != last:
        progress(done[0], len(targets))
    return found


def deep_scan(trusted_keys, progress=None):
    """Returns (candidates, error). See POST /api/deep_discover."""
    targets = sweep_targets(local_ipv4_ifaces())
    if not targets:
        return [], "this computer has no private IPv4 network (10.x, 172.16-31.x or 192.168.x) to search; is it connected?"
    macs = {e['ip']: e for e in neighbor_table_v4()}
    found = tcp_sweep(targets, progress)
    macs.update({e['ip']: e for e in neighbor_table_v4()})  # the sweep filled the neighbour table
    hosts = sorted(found, key=lambda ip: (not (macs.get(ip) or {}).get('pi'), int(ipaddress.IPv4Address(ip))))
    keys = {}
    ks = find_exe('ssh-keyscan')

    def scan(ip):
        try:
            r = subprocess.run([ks, '-T', '4', '-t', 'ed25519', ip], capture_output=True, text=True, timeout=10,
                               stdin=subprocess.DEVNULL, **hide_flags())
            return ip, parse_keyscan(r.stdout)
        except (OSError, subprocess.TimeoutExpired):
            return ip, None
    if ks and hosts:
        with concurrent.futures.ThreadPoolExecutor(DEEP_KEYSCAN_PARALLEL) as ex:
            keys = dict(ex.map(scan, hosts[:DEEP_KEYSCAN_MAX]))
    cands = []
    for ip in hosts:
        pi = bool((macs.get(ip) or {}).get('pi'))
        confirmed = keys.get(ip) is not None and keys[ip] in trusted_keys
        cands.append({'host': ip, 'via': 'cable' if ip.startswith('192.168.185.') else 'wifi', 'reachable': True,
                      'ms': found[ip], 'identity': 'confirmed' if confirmed else 'unknown', 'pi': pi,
                      'label': 'Your robot (identity confirmed)' if confirmed else
                               'Raspberry Pi with ssh' if pi else 'Other device with ssh'})
    return order_deep(cands), None


# ============================================================================ HTTP server

PLACEHOLDER = (b'<!doctype html><meta charset="utf-8"><title>TurtleBot Studio</title>'
               b'<body style="font-family:sans-serif;max-width:40em;margin:3em auto"><h1>TurtleBot Studio</h1>'
               b'<p>The user interface files are missing (web/index.html was not found next to studio.py). '
               b'The backend is running; the API works, but there is nothing to show here.</p></body>')
CTYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
          '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json',
          '.txt': 'text/plain; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.map': 'application/json',
          '.woff2': 'font/woff2', '.woff': 'font/woff', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
          '.gif': 'image/gif', '.webmanifest': 'application/manifest+json', '.zip': 'application/zip'}
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'")


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def make_handler(app):
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'TurtleBotStudio'

        def log_message(self, *a):
            pass

        def _host_ok(self):
            h = (self.headers.get('Host') or '').lower()
            return h in ('127.0.0.1:%d' % app.port, 'localhost:%d' % app.port)

        def _origin_ok(self):
            o = self.headers.get('Origin')
            return o is None or o in ('http://127.0.0.1:%d' % app.port, 'http://localhost:%d' % app.port)

        def _token_ok(self, query):
            t = self.headers.get('X-Studio-Token') or (query.get('token') or [''])[0]
            return hmac.compare_digest(t.encode(), app.token.encode())

        def _send(self, code, body, ctype='application/json', extra=None):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode())

        def _deny(self, why):
            self._json({'ok': False, 'error': why}, 403)

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._host_ok():
                return self._deny('bad host')
            if u.path.startswith('/api/'):
                if not self._token_ok(q):
                    return self._deny('bad token')
                if u.path == '/api/events':
                    return self._events()
                if u.path == '/api/settings':
                    return self._json(app.get_settings())
                if u.path == '/api/setup_status':
                    return self._json(app.setup_status())
                if u.path == '/api/catalog':
                    return self._json(app.catalog())
                if u.path == '/api/laptop_net':
                    return self._json(app.laptop_net())
                if u.path == '/api/diagnostics':
                    return self._json(app.diagnostics())
                if u.path == '/api/update_status':
                    return self._json(app.update_status())
                if u.path == '/api/history':
                    mins = clamp_minutes(_to_float((q.get('minutes') or ['15'])[0]))
                    return self._json(dict(app.history.query(mins), ok=True, minutes=mins, interval_s=1))
                if u.path == '/api/alerts':
                    since = _to_int((q.get('since') or ['0'])[0])
                    items, last = app.alerts.since(since)
                    return self._json({'ok': True, 'alerts': items, 'last_id': last})
                if u.path == '/api/teleop_limits':
                    return self._json(app.teleop_limits())
                if u.path == '/api/mapping':
                    return self._json(app.mapping_info())
                if u.path == '/api/map/live.png':
                    got = app.maps.get_map()
                    if got is None:
                        return self._json({'ok': False, 'error': 'no map yet'}, 404)
                    return self._send(200, got[0], 'image/png', {'X-Map-Meta': json.dumps(got[1], separators=(',', ':'))})
                if u.path in ('/api/maps/preview.png', '/api/maps/download'):
                    name = (q.get('name') or [''])[0]
                    if u.path == '/api/maps/download':
                        code, body, ctype = app.map_download_zip(name)
                    else:
                        mx = _to_int((q.get('max') or ['512'])[0]) or 512
                        code, body, ctype = app.map_preview_png(name, min(1024, max(64, mx)))
                    if ctype is None:
                        return self._json(body, code)
                    extra = {'Content-Disposition': 'attachment; filename="%s.zip"' % name} if ctype == 'application/zip' else None
                    return self._send(code, body, ctype, extra)
                if u.path.startswith('/api/templates/'):
                    txt = app.template_text(urllib.parse.unquote(u.path[len('/api/templates/'):]))
                    if txt is None:
                        return self._json({'ok': False, 'error': 'no such template'}, 404)
                    return self._send(200, txt.encode('utf-8'), 'text/plain; charset=utf-8')
                return self._json({'ok': False, 'error': 'not found'}, 404)
            self._static(u.path, u.query)

        def _file(self, base, rel, html_ok=True):
            full = safe_member_path(base, rel)
            if full and os.path.isfile(full):
                with open(full, 'rb') as f:
                    body = f.read()
                ext = os.path.splitext(full)[1].lower()
                return self._send(200, body, CTYPES.get(ext, 'application/octet-stream'),
                                  {'Content-Security-Policy': CSP} if ext == '.html' else None)
            return None

        def _redirect(self, where):
            self.send_response(302)
            self.send_header('Location', where)
            self.send_header('Content-Length', '0')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

        def _static(self, path, query=''):
            web = app.web_dir
            v2 = os.path.join(web, 'v2')
            qs = ('?' + query) if query else ''
            if path == '/favicon.ico':     # the 1.3 page has no icon link: answer "no icon" instead of a 404 in the browser console
                self.send_response(204)
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                return
            if path in ('/', '', '/index.html'):
                if app.settings.get('ui') != 'classic' and os.path.isfile(os.path.join(v2, 'index.html')):
                    return self._file(v2, 'index.html')
                if self._file(web, 'index.html') is None:
                    self._send(200, PLACEHOLDER, 'text/html; charset=utf-8')
                return
            if path in ('/classic', '/v2'):
                return self._redirect(path + '/' + qs)
            if path.startswith('/classic/'):
                if self._file(web, path[len('/classic/'):] or 'index.html') is None:
                    self._send(404, b'not found', 'text/plain')
                return
            if path.startswith('/v2/'):
                if self._file(v2, path[len('/v2/'):] or 'index.html') is None:
                    self._send(404, b'not found', 'text/plain')
                return
            if self._file(web, path.lstrip('/')) is None:
                self._send(404, b'not found', 'text/plain')

        def _events(self):
            q = app.bus.subscribe()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                self.wfile.write(b': hello\n\n')
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=app.heartbeat)
                    except queue.Empty:
                        self.wfile.write(b': heartbeat\n\n')
                        self.wfile.flush()
                        continue
                    if ev is None:
                        break
                    self.wfile.write(b'data: ' + json.dumps(ev).encode() + b'\n\n')
                    self.wfile.flush()
            except (OSError, ValueError):
                pass
            finally:
                app.bus.unsubscribe(q)
                app.client_gone()

        def do_POST(self):
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._host_ok() or not self._origin_ok():
                return self._deny('bad host')
            if not self._token_ok(q):
                return self._deny('bad token')
            try:
                n = int(self.headers.get('Content-Length') or 0)
                limit = ROUTE_UPLOAD_MAX + 1_000_000 if u.path == '/api/routes/upload' else 1_000_000
                if n > limit:
                    return self._json({'ok': False, 'error': 'request too large'}, 413)
                raw = self.rfile.read(n) if n else b'{}'
                req = json.loads(raw.decode('utf-8') or '{}')
                if not isinstance(req, dict):
                    raise ValueError
            except ValueError:
                return self._json({'ok': False, 'error': 'bad JSON'}, 400)
            routes = {
                '/api/discover': lambda: {'ok': True, 'candidates': app.discover(req.get('host'))},
                '/api/connect': lambda: app.connect(req.get('host')),
                '/api/disconnect': app.disconnect,
                '/api/bridge': lambda: app.forward(req),
                '/api/routes/upload': lambda: app.route_upload(req),
                '/api/estop': app.estop,
                '/api/sync': lambda: app.sync(req),
                '/api/settings': lambda: app.post_settings(req),
                '/api/open_terminal': app.open_terminal,
                '/api/setup_key': app.setup_key,
                '/api/setup_status': app.setup_status,
                '/api/create_key': app.create_key,
                '/api/scan_host_key': lambda: app.scan_host_key(req),
                '/api/trust_host_key': lambda: app.trust_key(req),
                '/api/untrust_host_key': lambda: app.untrust_key(req),
                '/api/test_login': lambda: app.test_login(req),
                '/api/robot_wifi_status': lambda: app.robot_wifi_status(req),
                '/api/open_vscode': lambda: app.open_vscode(req),
                '/api/local_files': lambda: app.local_files(req),
                '/api/robot_wifi_add': lambda: app.robot_wifi_add(req),
                '/api/robot_wifi_remove': lambda: app.robot_wifi_remove(req),
                '/api/laptop_wifi_settings': app.laptop_wifi_settings,
                '/api/join_hotspot': app.join_hotspot,
                '/api/deep_discover': app.deep_discover,
                '/api/reconnect_cancel': app.reconnect_cancel,
                '/api/quit': app.quit,
                '/api/teleop_limits': lambda: app.teleop_limits(req),
                '/api/check_updates': lambda: app.check_updates(force=bool(req.get('force', True))),
            }
            if app.fake:
                routes['/api/fake_drop'] = app.fake_drop
            fn = routes.get(u.path)
            if not fn:
                return self._json({'ok': False, 'error': 'not found'}, 404)
            try:
                res = fn()
            except Exception as e:  # never kill the handler thread silently
                app.log('error', 'internal error in %s: %s' % (u.path, e))
                res = {'ok': False, 'error': 'internal error: %s' % e}
            self._json(res)
    return H


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def serve(app, port, tries=1):
    last = None
    for p in range(port, port + tries):
        try:
            srv = Server(('127.0.0.1', p), make_handler(app))
            app.port = srv.server_address[1]
            return srv
        except OSError as e:
            last = e
    raise SystemExit('cannot bind 127.0.0.1:%d (%s)' % (port, last))


def fake_tar_main(argv):
    """Hidden helper used by --fake: stands in for the robot's tar/rm so the real streaming code is tested."""
    mode, d = argv[0], argv[1]
    if mode == 'extract':
        os.makedirs(d, exist_ok=True)
        extract_tar_stream(sys.stdin.buffer, d)
    elif mode == 'create':
        rels = [x for x in sys.stdin.buffer.read().decode().splitlines() if x]
        write_tar_stream(sys.stdout.buffer, d, rels)
        sys.stdout.buffer.flush()
    elif mode == 'rm':
        for rel in [x for x in sys.stdin.buffer.read().decode().splitlines() if x]:
            p = safe_member_path(d, rel)
            if p and os.path.isfile(p):
                os.remove(p)
    return 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='TurtleBot Studio desktop backend')
    ap.add_argument('--port', type=int, default=None, help='port on 127.0.0.1 (default 8765, next free if busy)')
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    ap.add_argument('--host-override', default=None, help='robot address to use instead of discovery')
    ap.add_argument('--fake', action='store_true', help='run robot_bridge.py --fake locally instead of ssh (demo/tests)')
    ap.add_argument('--config-dir', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--fake-home', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--bridge-script', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--catalog', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--templates-dir', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--web-dir', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--heartbeat', type=float, default=15.0, help=argparse.SUPPRESS)
    ap.add_argument('--update-delay', type=float, default=5.0, help=argparse.SUPPRESS)
    ap.add_argument('--exit-when-closed', action='store_true', help='stop Studio when its window has been closed for a while (default in the built app)')
    ap.add_argument('--stay-open', action='store_true', help='keep running after the window is closed (default when run from source)')
    ap.add_argument('--close-grace', type=float, default=CLOSE_GRACE, help=argparse.SUPPRESS)
    ap.add_argument('--version-file', default=None, help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '--_fake-tar':
        return fake_tar_main(argv[1:])
    if argv and argv[0] == '--_fake-bridge':  # frozen exe: the fake robot runs from the same binary
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import robot_bridge
        return robot_bridge.main(argv[1:])
    if '--version' in argv:
        line = 'TurtleBot Studio %s' % VERSION
        say(line)
        if '--version-file' in argv:   # hidden: the windowed build has no console, so the build smoke test reads a file
            try:
                with open(argv[argv.index('--version-file') + 1], 'w', encoding='utf-8') as f:
                    f.write(line + '\n')
            except (OSError, IndexError):
                return 1
        return 0
    if sys.version_info < (3, 10):
        say('Python 3.10 or newer is required.')
        return 2
    args = parse_args(argv)
    if args.host_override and not valid_host(args.host_override):
        say('invalid --host-override')
        return 2
    cfg = args.config_dir or config_dir()
    os.makedirs(cfg, exist_ok=True)
    old = read_instance(cfg)
    if old and instance_alive(old):   # Studio is already running for this user: show its window and leave
        url = 'http://127.0.0.1:%d/?token=%s' % (old['port'], old['token'])
        say('TurtleBot Studio is already running; opening its window.')
        if not args.no_browser:
            open_window(url, stored_window_mode(cfg), cfg)
        return 0
    app = Studio(args)
    srv = serve(app, 8765 if args.port is None else args.port, 20 if args.port is None else 1)
    url = 'http://127.0.0.1:%d/?token=%s' % (app.port, app.token)
    say('TurtleBot Studio %s%s' % (VERSION, ' (fake robot)' if app.fake else ''))
    say('Open this address in your browser (keep it private, it contains a one-time token):')
    say('  ' + url)
    say('Press Ctrl+C to stop.')
    app.log('info', 'Studio started on port %d (config: %s)' % (app.port, app.cfg))
    try:
        write_instance(app.cfg, app.port, app.token)
    except OSError as e:
        app.log('warn', 'could not write instance.json: %s' % e)
    app.start_update_check()
    stopping = threading.Event()

    def stop(*_):
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=srv.shutdown, daemon=True).start()
    app.stop_cb = stop
    try:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
    except (ValueError, OSError, AttributeError):
        pass
    if resolve_exit_when_closed(args.exit_when_closed, args.stay_open, FROZEN, app.fake):
        def watch():
            w = CloseWatcher(args.close_grace)
            while not stopping.wait(0.5):
                if w.tick(app.bus.count(), time.time()):
                    app.log('info', 'No Studio window open for %d s: stopping' % args.close_grace)
                    stop()
                    return
        threading.Thread(target=watch, daemon=True).start()
    if not args.no_browser:
        mode = app.settings.get('window_mode', DEFAULT_WINDOW_MODE)
        t = threading.Timer(0.5, lambda: open_window(url, mode, app.cfg))
        t.daemon = True
        t.start()
    try:
        srv.serve_forever(poll_interval=0.3)
    finally:
        app.shutdown()
        srv.server_close()
        remove_instance(app.cfg, os.getpid())
        say('Stopped.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
