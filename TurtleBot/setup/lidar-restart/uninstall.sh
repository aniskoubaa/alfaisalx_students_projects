#!/bin/bash
# Removes the lidar auto-restart service (TB-24). Run on the robot, from this folder:  sudo ./uninstall.sh
set -e
if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo:  sudo ./uninstall.sh"; exit 1; fi
systemctl disable --now tb4-lidar-restart.service 2>/dev/null || true
rm -f /etc/systemd/system/tb4-lidar-restart.service /usr/local/lib/tb4/tb4_lidar_restart.py
rmdir /usr/local/lib/tb4 2>/dev/null || true   # only if empty
systemctl daemon-reload
systemctl reset-failed tb4-lidar-restart.service 2>/dev/null || true
echo "Removed. Check:  systemctl status tb4-lidar-restart   (should say 'could not be found')"
echo "A tb4-lidar-restart.service.before-* backup next to the unit, if any, was left in place; delete it by hand if not needed."
