"""Wi-Fi script helpers (names, arguments) and parsers for the laptop's own Wi-Fi and wired
network on Windows, macOS and Linux.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip
from .wifi_scripts import *  # bundle: skip


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
