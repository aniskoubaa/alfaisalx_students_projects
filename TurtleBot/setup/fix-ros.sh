#!/bin/bash
# Makes the clock fix run before the ROS bringup, then restarts the bringup with the correct time.
# Run:  sudo ./fix-ros
set -e
if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo:  sudo ./fix-ros"; exit 1; fi
DIR=/home/ubuntu/wifi-switch

echo "1/3 Updating the clock fix so it runs before the robot software"
install -m 755 -o root -g root "$DIR/tb4-https-time" /usr/local/sbin/tb4-https-time
install -m 644 -o root -g root "$DIR/tb4-https-time.service" /etc/systemd/system/tb4-https-time.service
install -d -m 755 /etc/systemd/system/turtlebot4.service.d
install -m 644 -o root -g root "$DIR/10-wait-for-clock.conf" /etc/systemd/system/turtlebot4.service.d/10-wait-for-clock.conf
systemctl daemon-reload

echo "2/3 Checking the clock"
/usr/local/sbin/tb4-https-time || true

echo "3/3 Restarting the robot software (takes about a minute; the robot does not reboot)"
systemctl restart turtlebot4
sleep 3
systemctl is-active turtlebot4
echo "Done. You can close this window."
