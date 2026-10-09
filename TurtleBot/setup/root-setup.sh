#!/bin/bash
# One-time admin setup for the TurtleBot 4 on the university "Students" Wi-Fi.
# Run:  sudo bash /home/ubuntu/wifi-switch/root-setup.sh
set -e
if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo:  sudo bash $0"; exit 1; fi
DIR=/home/ubuntu/wifi-switch

echo "1/3 Clock: installing the HTTPS time fix (the university blocks normal time servers)"
install -m 755 -o root -g root "$DIR/tb4-https-time" /usr/local/sbin/tb4-https-time
install -m 644 -o root -g root "$DIR/tb4-https-time.service" /etc/systemd/system/tb4-https-time.service
install -m 644 -o root -g root "$DIR/tb4-https-time.timer" /etc/systemd/system/tb4-https-time.timer
systemctl daemon-reload
systemctl enable --now tb4-https-time.timer
/usr/local/sbin/tb4-https-time || true

echo "2/3 Name: making turtlebot4.local answer only with the Wi-Fi address"
CONF=/etc/avahi/avahi-daemon.conf
cp -n "$CONF" "$CONF.before-tb4"
if grep -qE '^[[:space:]]*#?[[:space:]]*allow-interfaces=' "$CONF"; then
  sed -i -E 's/^[[:space:]]*#?[[:space:]]*allow-interfaces=.*/allow-interfaces=wlan0/' "$CONF"
else
  sed -i '/^\[server\]/a allow-interfaces=wlan0' "$CONF"
fi
systemctl restart avahi-daemon

echo "3/3 Restarting the robot to check it comes back on the university Wi-Fi by itself (about 2 minutes)."
echo "You can close this window."
sleep 3
systemctl reboot
