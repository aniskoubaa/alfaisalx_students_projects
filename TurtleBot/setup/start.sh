#!/bin/bash
# Moves the TurtleBot 4 onto the "Students" Wi-Fi with a test run and an automatic undo.
# Run once:  sudo bash /home/ubuntu/wifi-switch/start.sh
set -u
SSID="Students"
DIR=/home/ubuntu/wifi-switch
KEYFILE=/etc/NetworkManager/system-connections/Students.nmconnection

if [ "$(id -u)" -ne 0 ]; then echo "Please run with sudo:  sudo bash $0"; exit 1; fi
if systemctl is-active --quiet tb4-wifi-switch; then echo "The switch is already running. Nothing to do."; exit 0; fi

read -r -s -p "Type the password of the '$SSID' Wi-Fi and press Enter (it stays hidden): " PSK; echo
if [ "${#PSK}" -lt 8 ] || [ "${#PSK}" -gt 63 ]; then echo "That doesn't look like a Wi-Fi password (8 to 63 characters). Nothing changed."; exit 1; fi

nmcli connection delete "$SSID" >/dev/null 2>&1
printf '%s' "$PSK" | python3 "$DIR/write_keyfile.py" "$KEYFILE" "$SSID"
unset PSK
if ! nmcli connection load "$KEYFILE" || ! nmcli -t -f NAME connection show | grep -qx "$SSID"; then
  echo "Could not save the Wi-Fi profile. Nothing else changed."; exit 1
fi

install -m 700 -o root -g root "$DIR/controller.sh" /run/tb4-wifi-controller.sh
rm -f "$DIR/GO" "$DIR/KEEP"
: > "$DIR/log.txt"; chown ubuntu:ubuntu "$DIR/log.txt"
systemd-run --unit=tb4-wifi-switch --collect --quiet /bin/bash /run/tb4-wifi-controller.sh
echo "Saved. In about 10 seconds the robot leaves its own Wi-Fi for a short test, then comes back by itself."
echo "You can close this window now."
