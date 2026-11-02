#!/bin/bash
# Installs the lidar auto-restart service (TB-24). Add-only: copies two files, enables one unit.
# Run on the robot, from this folder:  sudo ./install.sh
set -e
if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo:  sudo ./install.sh"; exit 1; fi
DIR="$(cd "$(dirname "$0")" && pwd)"
PY=/usr/local/lib/tb4/tb4_lidar_restart.py
UNIT=/etc/systemd/system/tb4-lidar-restart.service
STAMP=$(date +%Y%m%d-%H%M%S)

put() {  # put MODE SRC DEST : copy; a different file already there is kept as DEST.before-STAMP
  if [ -e "$3" ] && ! cmp -s "$2" "$3"; then cp -p "$3" "$3.before-$STAMP"; echo "  kept the old $3 as $3.before-$STAMP"; fi
  install -m "$1" -o root -g root "$2" "$3"
}

echo "1/3 Copying the program to /usr/local/lib/tb4 and the unit to /etc/systemd/system"
install -d -m 755 /usr/local/lib/tb4
put 755 "$DIR/tb4_lidar_restart.py" "$PY"
put 644 "$DIR/tb4-lidar-restart.service" "$UNIT"
systemctl daemon-reload

echo "2/3 Enabling and starting tb4-lidar-restart (it waits 20 s, then watches /dock_status and /scan)"
systemctl enable --now tb4-lidar-restart.service

echo "3/3 Done."
cat <<'MSG'

Verify:
  systemctl status tb4-lidar-restart
  journalctl -u tb4-lidar-restart -n 30 --no-pager
Expected: "active (running)" and a line "tb4_lidar_restart started" about 20 s after the start.

Undo:
  sudo ./uninstall.sh
MSG
