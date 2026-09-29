#!/usr/bin/env python3
"""Minimal forward HTTP/HTTPS proxy so the Jetson can reach the internet
through this laptop's Wi-Fi.

Runs ON THE LAPTOP. Normally started for you by jetson_internet.sh, which also
opens the SSH tunnel; run it directly only when debugging:

    python laptop_proxy.py

How the Jetson reaches it: not over the network. An SSH reverse port-forward
(`ssh -R 3128:127.0.0.1:3128 ...`) makes the Jetson's own 127.0.0.1:3128 lead
here, so no firewall exception is needed on the laptop. apt on the Jetson is
pointed at that address by /etc/apt/apt.conf.d/99proxy.

Supports:
  - CONNECT  -> tunnels TLS (pip, https, huggingface, github)
  - GET/POST with an absolute URI -> plain HTTP (the apt repositories)

Listens on 127.0.0.1 ONLY. An earlier version listened on 0.0.0.0 and relied on
an allowlist of 100.100.100.x - but this ISP puts the laptop's Wi-Fi inside the
carrier-grade NAT range 100.64.0.0/10, which contains 100.100.100.x, so that
allowlist could have admitted strangers on the ISP side. The tunnel only ever
connects from loopback, so loopback is all it needs.

Stop it with Ctrl+C; nothing is installed or persisted.
"""
import socket
import select
import sys
import threading
from urllib.parse import urlsplit

# Loopback only - the Jetson arrives through the SSH reverse tunnel, never directly.
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 3128
BUFSIZE = 65536
CONNECT_TIMEOUT = 20


def pipe(a, b):
    """Shuttle bytes both ways until either side closes."""
    socks = [a, b]
    try:
        while True:
            r, _, x = select.select(socks, [], socks, 60)
            if x or not r:
                break
            for s in r:
                other = b if s is a else a
                data = s.recv(BUFSIZE)
                if not data:
                    return
                other.sendall(data)
    except (OSError, ValueError):
        pass


def read_headers(conn):
    """Read up to the end of the HTTP request head."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUFSIZE)
        if not chunk:
            break
        data += chunk
        if len(data) > 256 * 1024:
            break
    return data


def handle(conn, addr):
    upstream = None
    try:
        # Defence in depth: the socket is bound to loopback, so this should never trip.
        if addr[0] != "127.0.0.1":
            conn.close()
            return

        head = read_headers(conn)
        if not head:
            conn.close()
            return

        first_line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = first_line.split()
        if len(parts) < 3:
            conn.close()
            return
        method, target, _version = parts[0], parts[1], parts[2]

        if method.upper() == "CONNECT":
            host, _, port = target.rpartition(":")
            port = int(port or 443)
            upstream = socket.create_connection((host, port), CONNECT_TIMEOUT)
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            print(f"CONNECT {host}:{port}", flush=True)
            pipe(conn, upstream)
        else:
            split = urlsplit(target)
            if not split.hostname:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                conn.close()
                return
            host = split.hostname
            port = split.port or 80
            path = split.path or "/"
            if split.query:
                path += "?" + split.query

            # Rewrite the absolute-URI request line into origin form.
            rest = head.split(b"\r\n", 1)[1]
            new_head = f"{method} {path} {_version}\r\n".encode("latin-1") + rest

            upstream = socket.create_connection((host, port), CONNECT_TIMEOUT)
            upstream.sendall(new_head)
            print(f"{method} {host}:{port}{path[:60]}", flush=True)
            pipe(conn, upstream)
    except Exception as exc:  # noqa: BLE001 - proxy must never die on one request
        print(f"error from {addr[0]}: {exc}", flush=True)
    finally:
        for s in (conn, upstream):
            try:
                if s:
                    s.close()
            except OSError:
                pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(128)
    print(f"proxy listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    while True:
        try:
            conn, addr = srv.accept()
        except KeyboardInterrupt:
            break
        except OSError:
            continue
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
