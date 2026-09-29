#!/usr/bin/env bash
# Set up VNC on the Jetson so the *console* screen can be reached remotely.
#
# Runs ON THE JETSON, as root:
#   sudo bash setup_vnc.sh             # generates an 8-character password
#   sudo bash setup_vnc.sh Pass1234    # or choose one (8 characters max)
#
# What it installs (both kept in ../system/, mirrored to their real paths):
#   /usr/local/sbin/raptor-x11vnc-start        launcher that finds the X auth file
#   /etc/systemd/system/x11vnc.service         keeps x11vnc running, follows logins
# plus the x11vnc package and a password file at /etc/x11vnc.pass.
#
# Why mirror the console (:0) instead of a virtual desktop: this board's GDM runs
# X11 (WaylandEnable=false), so the real screen can be captured - you see the
# login screen, then the desktop, and anything started there such as the RAPTOR
# demo window. On Wayland this would not work at all.
#
# Two lessons baked in, both learned the hard way:
#   1. VNC passwords are limited to 8 characters. Classic VNC auth is DES and
#      only uses the first 8 bytes; a longer password is silently truncated on
#      one side but not the other, and every login fails with
#      "password check failed". This script refuses anything longer.
#   2. `x11vnc -auth guess` does not work under systemd here (no HOME, and the
#      greeter's auth file is not where it looks). raptor-x11vnc-start reads the
#      auth path from the running Xorg command line instead.
#
# Security: VNC traffic is NOT encrypted. Fine on the direct cable to the laptop;
# if the board joins a shared network, bind to localhost and tunnel over SSH, or
# use RDP (setup_rdp.sh), which is TLS-encrypted.
set -uo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SYSTEM="$HERE/../system"
PASSFILE=/etc/x11vnc.pass
PORT=5900
PASS="${1:-}"

if [ "$(id -u)" -ne 0 ]; then echo "run with sudo" >&2; exit 1; fi
for f in "$SYSTEM/usr/local/sbin/raptor-x11vnc-start" "$SYSTEM/etc/systemd/system/x11vnc.service"; do
    [ -f "$f" ] || { echo "missing $f - run this from the repository's src/setup/" >&2; exit 1; }
done

if [ -n "$PASS" ] && [ "${#PASS}" -gt 8 ]; then
    echo "ERROR: VNC passwords are limited to 8 characters (the protocol uses DES)." >&2
    echo "  '${PASS}' is ${#PASS}. Pick 8 or fewer, or omit it to generate one." >&2
    exit 1
fi

echo "=== 1. install x11vnc ==="
if ! command -v x11vnc >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y x11vnc || {
        echo "ERROR: apt could not install x11vnc - does the board have internet?" >&2
        echo "  (see src/tools/README.md, 'Giving the Jetson internet')" >&2
        exit 1
    }
fi
x11vnc -version 2>&1 | head -1

echo "=== 2. password ==="
if [ -z "$PASS" ]; then
    PASS="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 8)"
    echo "generated VNC password: $PASS"
fi
x11vnc -storepasswd "$PASS" "$PASSFILE" >/dev/null
chmod 600 "$PASSFILE"
echo "stored in $PASSFILE (change later: sudo x11vnc -storepasswd <new> $PASSFILE)"

echo "=== 3. install launcher + service ==="
install -m 0755 "$SYSTEM/usr/local/sbin/raptor-x11vnc-start" /usr/local/sbin/raptor-x11vnc-start
install -m 0644 "$SYSTEM/etc/systemd/system/x11vnc.service" /etc/systemd/system/x11vnc.service
systemctl daemon-reload
systemctl enable x11vnc.service >/dev/null 2>&1
systemctl restart x11vnc.service
sleep 4

echo "=== 4. verify ==="
systemctl is-active x11vnc.service
if ss -lnt 2>/dev/null | grep -q ":$PORT "; then
    echo "listening on $PORT"
else
    echo "WARNING: nothing listening on $PORT - see: journalctl -u x11vnc -n 30" >&2
fi

echo
echo "Connect (mRemoteNG / any VNC client):"
echo "    protocol VNC   host 100.100.100.1   port $PORT   password $PASS"
echo "You land on the GDM login screen; log in as alfaisal-x-nx."
