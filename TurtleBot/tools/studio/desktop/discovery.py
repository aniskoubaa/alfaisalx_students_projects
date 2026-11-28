"""Laptop-side network discovery: cable IPv6, neighbour tables, and the port-22 sweep behind
"Search the whole network".
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip
from .wifi_scripts import *  # bundle: skip
from .laptop_network import *  # bundle: skip
from .programs import *  # bundle: skip
from .events import *  # bundle: skip
from .alerts import *  # bundle: skip
from .mapping import *  # bundle: skip
from .bridge_process import *  # bundle: skip
from .connection import *  # bundle: skip
from .forwarding import *  # bundle: skip
from .telemetry import *  # bundle: skip
from .file_sync import *  # bundle: skip
from .terminals import *  # bundle: skip
from .settings import *  # bundle: skip
from .trust import *  # bundle: skip
from .map_api import *  # bundle: skip
from .updates import *  # bundle: skip
from .wifi import *  # bundle: skip
from .app import *  # bundle: skip


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
