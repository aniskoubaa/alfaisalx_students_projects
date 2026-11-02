#!/bin/bash
# Remove exactly the three files installed by install.sh. Run with sudo.
if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo: sudo bash $0" >&2; exit 1; fi
systemctl disable --now tb4-wifi-retry.timer 2>/dev/null || true
rm -f /etc/systemd/system/tb4-wifi-retry.timer /etc/systemd/system/tb4-wifi-retry.service /usr/local/sbin/tb4-wifi-retry
systemctl daemon-reload
echo "Removed tb4-wifi-retry (script, service, timer)."
