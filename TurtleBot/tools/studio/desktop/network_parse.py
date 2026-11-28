"""Pure parsers for the laptop and robot neighbour tables, IPv4 interfaces and the address list
that "Search the whole network" probes. They only turn command output into data.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip


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
