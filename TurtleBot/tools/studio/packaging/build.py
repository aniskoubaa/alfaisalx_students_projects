#!/usr/bin/env python3
"""Build the TurtleBot Studio program with PyInstaller (standard library only, any OS).

  python build.py                       build, print the output path and size
  python build.py --smoke               build, then start the program with --fake and check it works
  python build.py --smoke-only          skip the build, only run the smoke test on the existing program
  python build.py --installer           (Windows) build, then make dist/TurtleBotStudio-Setup-<version>.exe with NSIS 3
                                        (makensis from PATH, Program Files (x86)\\NSIS or the electron-builder cache)
  python build.py --smoke --installer   build, smoke test, then the installer

The built program has no console window (Windows, macOS), so the smoke test reads the address and token from
instance.json in a temporary STUDIO_CONFIG_DIR and checks --version through the hidden --version-file option.
"""
import argparse
import glob
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
IS_WIN = os.name == 'nt'
IS_MAC = sys.platform == 'darwin'
NAME = 'TurtleBotStudio' + ('.exe' if IS_WIN else '')
DIST = os.path.join(HERE, 'dist')
BUILD = os.path.join(HERE, 'build')
ICON = os.path.join(HERE, 'studio.ico')   # generated below, not committed
START_TIMEOUT = 60   # onefile unpacking is slow on first start (antivirus scans on Windows)


def app_version():
    with open(os.path.join(STUDIO, 'version.json'), encoding='utf-8') as f:
        return json.load(f)['version']


def binary_path():
    if IS_MAC:   # the windowed app bundle; its inner program is what runs
        return os.path.join(DIST, 'TurtleBotStudio.app', 'Contents', 'MacOS', 'TurtleBotStudio')
    return os.path.join(DIST, NAME)


# ---------------------------------------------------------------- icon (no third-party art, standard library only)
def _round_box(u, v, x0, y0, x1, y1, r):
    if not (x0 <= u <= x1 and y0 <= v <= y1):
        return False
    cx = min(max(u, x0 + r), x1 - r)
    cy = min(max(v, y0 + r), y1 - r)
    return (u - cx) ** 2 + (v - cy) ** 2 <= r * r


def _icon_colour(u, v):
    """RGB at (u, v) in 0..1 of a blue rounded square with a white robot face, or None outside the square."""
    if not _round_box(u, v, 0.02, 0.02, 0.98, 0.98, 0.2):
        return None
    for ex in (0.36, 0.64):                                    # eyes
        if (u - ex) ** 2 + (v - 0.55) ** 2 <= 0.075 ** 2:
            return (0x1F, 0x3A, 0x5F)
    if (u - 0.5) ** 2 + (v - 0.15) ** 2 <= 0.055 ** 2:         # antenna ball
        return (0x2E, 0xC4, 0xB6)
    if 0.47 <= u <= 0.53 and 0.15 <= v <= 0.3:                 # antenna
        return (0xFF, 0xFF, 0xFF)
    if _round_box(u, v, 0.18, 0.3, 0.82, 0.8, 0.12):           # head
        return (0xFF, 0xFF, 0xFF)
    return (0x2B, 0x59, 0x8F)


def _icon_pixels(n):
    """n x n BGRA pixels, bottom row first, with 4x4 supersampling."""
    rows = []
    for y in range(n - 1, -1, -1):
        row = bytearray()
        for x in range(n):
            acc, cov = [0, 0, 0], 0
            for sy in range(4):
                for sx in range(4):
                    c = _icon_colour((x + (sx + 0.5) / 4) / n, (y + (sy + 0.5) / 4) / n)
                    if c:
                        cov += 1
                        for i in range(3):
                            acc[i] += c[i]
            if cov:
                row += bytes((acc[2] // cov, acc[1] // cov, acc[0] // cov, cov * 255 // 16))   # B, G, R, A
            else:
                row += b'\x00\x00\x00\x00'
        rows.append(bytes(row))
    return b''.join(rows)


def make_ico(path, sizes=(16, 32, 48)):
    """Write a classic multi-size .ico (32-bit BMP images, which PyInstaller and NSIS both accept)."""
    images = []
    for n in sizes:
        mask_row = ((n + 31) // 32) * 4
        header = struct.pack('<IiiHHIIiiII', 40, n, 2 * n, 1, 32, 0, 0, 0, 0, 0, 0)
        images.append(header + _icon_pixels(n) + b'\x00' * (mask_row * n))
    out = struct.pack('<HHH', 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for n, img in zip(sizes, images):
        out += struct.pack('<BBBBHHII', n, n, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    with open(path, 'wb') as f:
        f.write(out + b''.join(images))


def ensure_icon():
    if not os.path.isfile(ICON):
        make_ico(ICON)
        print('Generated %s' % ICON)
    return ICON


# ---------------------------------------------------------------- build
def build():
    t0 = time.time()
    ensure_icon()
    cmd = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
           '--distpath', DIST, '--workpath', BUILD, 'studio.spec']
    print('+ ' + ' '.join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=HERE)
    # the work folder is only a cache; its generated HTML reports would trip the repo's link check
    shutil.rmtree(BUILD, ignore_errors=True)
    if r.returncode != 0:
        print('FAIL: PyInstaller exited with %d' % r.returncode)
        return False
    exe = binary_path()
    if not os.path.isfile(exe):
        print('FAIL: expected output not found: ' + exe)
        return False
    print('Built %s (%.1f MB) in %.0f s' % (exe, os.path.getsize(exe) / 1048576.0, time.time() - t0))
    return True


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def kill_tree(proc):
    if proc.poll() is not None:
        return
    if IS_WIN:
        try:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=20)
        except Exception:
            proc.terminate()
    else:
        proc.terminate()   # SIGTERM: the bootloader forwards it to the child
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        pass


def read_instance(cfg):
    try:
        with open(os.path.join(cfg, 'instance.json'), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get('port') and d.get('token') else None
    except (OSError, ValueError):
        return None


def smoke():
    exe = binary_path()
    if not os.path.isfile(exe):
        print('FAIL: binary not found: ' + exe + ' (build first)')
        return False
    cfg = tempfile.mkdtemp(prefix='studio-smoke-')
    env = dict(os.environ, STUDIO_CONFIG_DIR=cfg)
    proc = None
    try:
        # 1. --version (the windowed program has no console: it also writes the line to a file)
        vfile = os.path.join(cfg, 'version.txt')
        r = subprocess.run([exe, '--version', '--version-file', vfile], capture_output=True, text=True, timeout=START_TIMEOUT, env=env)
        out = open(vfile, encoding='utf-8').read().strip() if os.path.isfile(vfile) else ''
        print('--version -> exit %d, %r' % (r.returncode, out))
        want = 'TurtleBot Studio ' + app_version()
        if r.returncode != 0 or out != want:
            print('FAIL: --version must exit 0 and write %r' % want)
            return False
        # 2. start in fake mode without opening any window; the address is in instance.json
        port = free_port()
        proc = subprocess.Popen([exe, '--fake', '--no-browser', '--stay-open', '--port', str(port)], env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        info = None
        while time.time() - t0 < START_TIMEOUT and proc.poll() is None:
            info = read_instance(cfg)
            if info:
                break
            time.sleep(0.2)
        if not info:
            print('FAIL: no instance.json within %d s (exit code %s)' % (START_TIMEOUT, proc.poll()))
            log = os.path.join(cfg, 'studio.log')
            if os.path.isfile(log):
                print(open(log, encoding='utf-8', errors='replace').read()[-2000:])
            return False
        p, token = info['port'], info['token']
        print('Started in %.1f s on port %s' % (time.time() - t0, p))
        # 3. GET /api/settings with the token header
        req = urllib.request.Request('http://127.0.0.1:%s/api/settings' % p, headers={'X-Studio-Token': token})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data.get('fake') is not True or data.get('version') != app_version():
            print('FAIL: /api/settings unexpected: fake=%r version=%r' % (data.get('fake'), data.get('version')))
            return False
        print('/api/settings ok: fake=%s version=%s' % (data['fake'], data['version']))
        # 4. the web UI is bundled
        req = urllib.request.Request('http://127.0.0.1:%s/?token=%s' % (p, token))
        with urllib.request.urlopen(req, timeout=20) as resp:
            status, page = resp.status, resp.read()
        if status != 200 or b'<html' not in page.lower():
            print('FAIL: web page not served')
            return False
        print('web page ok (%d bytes)' % len(page))
        # 5. a second start finds the running one and exits 0 without a new server
        r = subprocess.run([exe, '--fake', '--no-browser', '--stay-open'], env=env, capture_output=True, timeout=START_TIMEOUT)
        if r.returncode != 0 or read_instance(cfg) != info:
            print('FAIL: a second start must exit 0 and leave the first instance alone (exit %d)' % r.returncode)
            return False
        print('second start exits 0 (single instance ok)')
        # 6. Quit Studio: clean stop, instance.json removed
        req = urllib.request.Request('http://127.0.0.1:%s/api/quit' % p, data=b'{}', method='POST',
                                     headers={'X-Studio-Token': token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            if not json.loads(resp.read().decode('utf-8')).get('ok'):
                print('FAIL: /api/quit refused')
                return False
        try:
            code = proc.wait(30)
        except subprocess.TimeoutExpired:
            print('FAIL: the program did not stop after /api/quit')
            return False
        if code != 0 or read_instance(cfg) is not None:
            print('FAIL: Quit must exit 0 and remove instance.json (exit %s)' % code)
            return False
        print('quit ok (exit 0, instance.json removed)')
        print('SMOKE OK')
        return True
    except Exception as e:
        print('FAIL: %s: %s' % (type(e).__name__, e))
        return False
    finally:
        if proc is not None:
            kill_tree(proc)
        shutil.rmtree(cfg, ignore_errors=True)


# ---------------------------------------------------------------- Windows installer (NSIS 3)
def find_makensis():
    exe = shutil.which('makensis')
    if exe:
        return exe
    cands = []
    for var in ('ProgramFiles(x86)', 'ProgramFiles'):
        base = os.environ.get(var)
        if base:
            cands.append(os.path.join(base, 'NSIS', 'makensis.exe'))
    local = os.environ.get('LOCALAPPDATA')
    if local:   # the copy electron-builder downloads: Cache\nsis-3.x\nsis-3.x-<hash>\makensis.exe (and Bin\makensis.exe)
        for pat in (os.path.join(local, 'electron-builder', 'Cache', 'nsis-*', '**', 'makensis.exe'),
                    os.path.join(local, 'electron-builder', 'Cache', 'nsis', 'nsis-*', '**', 'makensis.exe')):
            # the one at the top of the NSIS folder first (it finds Include and Stubs next to itself)
            cands += sorted(glob.glob(pat, recursive=True), key=lambda p: (os.path.basename(os.path.dirname(p)) == 'Bin', p))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def installer():
    if not IS_WIN:
        print('FAIL: --installer builds the Windows setup program; run it on Windows')
        return False
    exe = binary_path()
    if not os.path.isfile(exe):
        print('FAIL: binary not found: ' + exe + ' (build first)')
        return False
    mk = find_makensis()
    if not mk:
        print('FAIL: makensis (NSIS 3) not found. Install it with "choco install nsis -y" or from https://nsis.sourceforge.io/ ,\n'
              '      or put makensis.exe on PATH (also looked in Program Files (x86)\\NSIS and the electron-builder cache).')
        return False
    ver = app_version()
    parts = (ver.split('.') + ['0', '0', '0', '0'])[:4]
    cmd = [mk, '/V2', '/DAPP_VERSION=' + ver, '/DAPP_VERSION_NUM=' + '.'.join(parts), '/DAPP_EXE=' + exe,
           '/DAPP_ICON=' + ensure_icon(), '/DOUT_DIR=' + DIST, os.path.join(HERE, 'installer.nsi')]
    print('+ ' + ' '.join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=HERE)
    out = os.path.join(DIST, 'TurtleBotStudio-Setup-%s.exe' % ver)
    if r.returncode != 0 or not os.path.isfile(out):
        print('FAIL: makensis exited with %d' % r.returncode)
        return False
    print('Installer %s (%.1f MB)' % (out, os.path.getsize(out) / 1048576.0))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--smoke', action='store_true', help='build, then smoke-test the program')
    ap.add_argument('--smoke-only', action='store_true', help='smoke-test the existing program, no build')
    ap.add_argument('--installer', action='store_true', help='(Windows) after the build and smoke test, make the setup program with NSIS')
    a = ap.parse_args(argv)
    if not a.smoke_only and not build():
        return 1
    if (a.smoke or a.smoke_only) and not smoke():
        return 1
    if a.installer and not installer():
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
