#!/usr/bin/env python3
"""Check that the Jetson's VNC server accepts a login - the way a real client does.

Runs ON THE LAPTOP. Needs:  pip install pycryptodome

    python check_vnc.py --password <vnc-password>
    python check_vnc.py --host 100.100.100.1 --port 5900 --password <vnc-password>

Why this exists: "port 5900 is open" proves nothing. This completes the full RFB
handshake - version, security negotiation, the DES challenge/response - and on
success reads the desktop size, so it tells you whether a VNC client will
actually get in, and what it will see.

It also explains the two failures actually hit on this board:
  - "password check failed" with a password longer than 8 characters: classic
    VNC authentication only uses the first 8 bytes. Use 8 or fewer.
  - a 640x480 desktop: the console has no monitor attached; see
    src/setup/set_headless_display.sh.

Nothing here stores or prints the password.
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys


def vnc_des_key(password: str) -> bytes:
    """The VNC DES key: first 8 bytes of the password, each byte BIT-REVERSED.

    The bit reversal is a quirk of the original VNC implementation, and the usual
    reason a hand-rolled check disagrees with real clients.
    """
    raw = password.encode("latin-1")[:8].ljust(8, b"\x00")
    return bytes(int(f"{b:08b}"[::-1], 2) for b in raw)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("server closed the connection")
        data += chunk
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="100.100.100.1")
    ap.add_argument("--port", type=int, default=5900)
    ap.add_argument("--password", required=True, help="VNC password (8 characters max)")
    args = ap.parse_args()

    try:
        from Crypto.Cipher import DES
    except ImportError:
        print("needs pycryptodome:  pip install pycryptodome", file=sys.stderr)
        return 2

    if len(args.password) > 8:
        print(f"note: VNC only uses the first 8 characters; testing with those "
              f"({len(args.password)} given)")

    try:
        s = socket.create_connection((args.host, args.port), timeout=10)
    except OSError as exc:
        print(f"FAIL: cannot reach {args.host}:{args.port} - {exc}")
        print("  Is the cable in and the board on? (Do not trust ping here - see src/tools/README.md.)")
        return 1

    with s:
        version = recv_exact(s, 12)
        print(f"server version : {version.decode(errors='replace').strip()}")
        s.sendall(b"RFB 003.008\n")

        count = recv_exact(s, 1)[0]
        types = list(recv_exact(s, count)) if count else []
        print(f"security types : {types}  (2 = VNC password auth)")
        if 2 not in types:
            print("FAIL: server does not offer VNC password auth")
            return 1
        s.sendall(bytes([2]))

        challenge = recv_exact(s, 16)
        s.sendall(DES.new(vnc_des_key(args.password), DES.MODE_ECB).encrypt(challenge))

        result = struct.unpack(">I", recv_exact(s, 4))[0]
        if result != 0:
            reason_len = struct.unpack(">I", recv_exact(s, 4))[0]
            print(f"FAIL: authentication rejected - {recv_exact(s, reason_len).decode(errors='replace')}")
            return 1

        s.sendall(b"\x01")                         # request a shared session
        width, height = struct.unpack(">HH", recv_exact(s, 4))
        recv_exact(s, 16)                          # pixel format, not needed here
        name_len = struct.unpack(">I", recv_exact(s, 4))[0]
        name = recv_exact(s, name_len).decode(errors="replace")

    print("authentication : OK")
    print(f"desktop        : {width}x{height}  \"{name}\"")
    if (width, height) == (640, 480):
        print("warning        : 640x480 means no display config - run src/setup/set_headless_display.sh")
    print("VERDICT: a VNC client can log in and see the screen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
