#!/usr/bin/env bash
# Enable RDP on the Jetson via GNOME Remote Desktop's system-level "Remote Login".
#
# Runs ON THE JETSON, as root:
#   sudo bash setup_rdp.sh                          # user alfaisal-x-nx, generated password
#   sudo bash setup_rdp.sh <username> <password>    # choose your own
#
# Why RDP as well as VNC:
#   - GNOME 46 (Ubuntu 24.04) dropped VNC from gnome-remote-desktop; RDP is the
#     natively supported protocol on this OS.
#   - It is TLS-encrypted. The VNC setup here is not.
#   - A Remote Login session negotiates its own resolution, instead of mirroring
#     the headless console (stuck at 1024x768 - see set_headless_display.sh).
# The trade-off: RDP gives you a NEW session, not the physical screen. Use VNC
# when you need to see what is actually on the console.
#
# IMPORTANT - the credentials are NOT your Linux login password. System-level RDP
# keeps its own username/password pair, set with `grdctl --system rdp
# set-credentials`. Until that is done, every connection is refused and the log
# says "[RDP] Credentials are not set, denying client". An earlier version of
# this script skipped that step, which is exactly the failure it produced.
#
# The "Init TPM credentials failed ... using GKeyFile as fallback" lines grdctl
# prints are harmless: this board has no TPM, so credentials go to a key file.
set -uo pipefail

RDP_USER="${1:-alfaisal-x-nx}"
RDP_PASS="${2:-}"
CERTDIR=/etc/gnome-remote-desktop
CRT="$CERTDIR/rdp-tls.crt"
KEY="$CERTDIR/rdp-tls.key"
PORT=3389

if [ "$(id -u)" -ne 0 ]; then echo "run with sudo" >&2; exit 1; fi
command -v grdctl >/dev/null || { echo "grdctl missing: apt-get install gnome-remote-desktop" >&2; exit 1; }

quiet() { grep -vE 'TPM|GKeyFile|fallback' || true; }

echo "=== 1. TLS certificate ==="
mkdir -p "$CERTDIR"
if [ ! -f "$CRT" ] || [ ! -f "$KEY" ]; then
    openssl req -new -newkey rsa:4096 -days 3650 -nodes -x509 \
        -subj "/C=SA/ST=Riyadh/L=Riyadh/O=RAPTOR/CN=$(hostname)" \
        -keyout "$KEY" -out "$CRT" 2>/dev/null
    echo "generated a self-signed certificate (valid 10 years)"
else
    echo "certificate already present, reusing"
fi
# The daemon runs as its own unprivileged user and must be able to read these.
chown gnome-remote-desktop:gnome-remote-desktop "$CRT" "$KEY" 2>/dev/null || true
chmod 640 "$CRT"
chmod 600 "$KEY"

echo "=== 2. credentials ==="
if [ -z "$RDP_PASS" ]; then
    RDP_PASS="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 12)"
    echo "generated RDP password: $RDP_PASS"
fi
grdctl --system rdp set-credentials "$RDP_USER" "$RDP_PASS" 2>&1 | quiet

echo "=== 3. enable ==="
grdctl --system rdp set-tls-cert "$CRT" 2>&1 | quiet
grdctl --system rdp set-tls-key "$KEY" 2>&1 | quiet
grdctl --system rdp enable 2>&1 | quiet
systemctl enable gnome-remote-desktop >/dev/null 2>&1
systemctl restart gnome-remote-desktop
sleep 6

echo "=== 4. verify ==="
grdctl --system status 2>/dev/null | grep -E 'Status:|Port:|Username:|TLS fingerprint:'
if ss -lnt 2>/dev/null | grep -q ":$PORT "; then
    echo "listening on $PORT"
else
    echo "WARNING: nothing listening on $PORT - see: journalctl -u gnome-remote-desktop -n 30" >&2
fi

echo
echo "Connect with Remote Desktop (mstsc) or mRemoteNG (protocol RDP):"
echo "    host 100.100.100.1   port $PORT   user $RDP_USER   password $RDP_PASS"
echo "Expect a certificate warning on first connect - the certificate is self-signed."
echo "Change later:  sudo grdctl --system rdp set-credentials <user> <password>"
echo "               sudo systemctl restart gnome-remote-desktop"
