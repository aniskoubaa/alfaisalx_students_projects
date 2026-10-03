#!/bin/bash
# Removes the HTTPS clock fix and its "start ROS after the clock" rule, returning the clock setup to how it
# came from the factory, then restarts the robot software (so a re-plugged lidar is picked up too).
# Run:  sudo ./undo-clock
if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo:  sudo ./undo-clock"; exit 1; fi

echo "1/2 Removing the clock fix"
systemctl disable --now tb4-https-time.timer 2>/dev/null
rm -f /etc/systemd/system/tb4-https-time.timer /etc/systemd/system/tb4-https-time.service /usr/local/sbin/tb4-https-time
rm -f /etc/systemd/system/turtlebot4.service.d/10-wait-for-clock.conf
rmdir /etc/systemd/system/turtlebot4.service.d 2>/dev/null
systemctl daemon-reload
systemctl reset-failed tb4-https-time.service 2>/dev/null

echo "2/2 Restarting the robot software (about a minute; the robot does not reboot)"
systemctl restart turtlebot4
systemctl is-active turtlebot4
echo "Done. You can close this window."
