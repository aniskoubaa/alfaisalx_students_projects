#!/bin/bash
# Install the Wi-Fi retry timer. Add-only: three files plus enabling the timer. Run with sudo.
set -e
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo: sudo bash $0" >&2; exit 1; fi
here=$(cd "$(dirname "$0")" && pwd)
install -m 0755 "$here/tb4-wifi-retry" /usr/local/sbin/tb4-wifi-retry
install -m 0644 "$here/tb4-wifi-retry.service" /etc/systemd/system/tb4-wifi-retry.service
install -m 0644 "$here/tb4-wifi-retry.timer" /etc/systemd/system/tb4-wifi-retry.timer
systemctl daemon-reload
systemctl enable --now tb4-wifi-retry.timer
echo
echo "Installed. Verify:"
echo "  systemctl list-timers tb4-wifi-retry.timer"
echo "  journalctl -t tb4-wifi-retry"
echo "Undo:"
echo "  sudo bash $here/uninstall.sh"
