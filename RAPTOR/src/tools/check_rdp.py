#!/usr/bin/env python3
"""Check that the Jetson's RDP server is genuinely answering - before opening a client.

Runs ON THE LAPTOP. No dependencies.

    python check_rdp.py
    python check_rdp.py --host 100.100.100.1 --port 3389

Sends an X.224 Connection Request carrying an RDP Negotiation Request and reads
the Connection Confirm. A valid confirm proves the RDP stack is serving; an open
port alone proves nothing.

What it cannot see: whether your credentials are right. GNOME Remote Desktop
checks those later, over TLS. The one credential failure seen on this board -
the server resetting every connection - meant credentials had never been set:
    journalctl -u gnome-remote-desktop | grep "Credentials are not set"
Fix with src/setup/setup_rdp.sh. Note these are NOT the Linux login password.
"""
from __future__ import annotations

import argparse
import socket
import struct

PROTOCOLS = {0: "legacy RDP", 1: "TLS", 2: "CredSSP (NLA)", 8: "RDSTLS", 16: "CredSSP + early user auth"}

# TPKT header (4) + X.224 Connection Request (7) + RDP_NEG_REQ (8) = 19 bytes,
# requesting TLS | CredSSP (0x03).
CONNECTION_REQUEST = bytes([
    0x03, 0x00, 0x00, 0x13,                         # TPKT v3, length 19
    0x0E, 0xE0, 0x00, 0x00, 0x00, 0x00, 0x00,       # X.224 CR TPDU
    0x01, 0x00, 0x08, 0x00, 0x03, 0x00, 0x00, 0x00, # RDP_NEG_REQ: TLS|CredSSP
])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="100.100.100.1")
    ap.add_argument("--port", type=int, default=3389)
    args = ap.parse_args()

    try:
        with socket.create_connection((args.host, args.port), timeout=10) as s:
            s.sendall(CONNECTION_REQUEST)
            resp = s.recv(64)
    except ConnectionResetError:
        print("FAIL: the server reset the connection.")
        print("  On this board that has meant RDP credentials were never set - run src/setup/setup_rdp.sh.")
        return 1
    except OSError as exc:
        print(f"FAIL: cannot reach {args.host}:{args.port} - {exc}")
        return 1

    if len(resp) < 11 or resp[0] != 0x03:
        print(f"FAIL: not an RDP (TPKT) response: {resp.hex()}")
        return 1
    if resp[5] != 0xD0:
        print(f"FAIL: expected an X.224 Connection Confirm (0xd0), got 0x{resp[5]:02x}")
        return 1
    print("X.224          : Connection Confirm")

    if len(resp) >= 19 and resp[11] == 0x02:
        selected = struct.unpack("<I", resp[15:19])[0]
        print(f"negotiation    : accepted, server chose {PROTOCOLS.get(selected, selected)}")
        print("VERDICT: RDP is live. Connect with mstsc or mRemoteNG using the RDP credentials.")
        return 0
    if len(resp) >= 19 and resp[11] == 0x03:
        code = struct.unpack("<I", resp[15:19])[0]
        print(f"FAIL: negotiation refused, code {code}")
        return 1
    print("VERDICT: RDP answered, but without a negotiation response (legacy server?).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
