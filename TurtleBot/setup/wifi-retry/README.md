# Wi-Fi retry for the TurtleBot 4

## Problem

When the robot boots and none of its saved Wi-Fi networks is in range, NetworkManager starts the factory hotspot (`netplan-wlan0-Turtlebot4`, 10.42.0.1/24). While `wlan0` runs as an access point it does not scan for the saved networks (`Students`, `TP-LINK_Extender_5GHz`), so the robot stays on its hotspot even after a known network comes back.

## What it does

`tb4-wifi-retry` runs as root from a systemd timer, 3 minutes after boot and then every 5 minutes. On each run it:

1. Does nothing if `wlan0` is not in AP mode (the normal case when the robot is on a client network).
2. Does nothing if a device is connected to the hotspot (neighbour entries for 10.42.0.x, or an unexpired DHCP lease).
3. Otherwise tries the saved client profiles that have autoconnect on, highest autoconnect priority first, and stops at the first one that connects (up to 40 s each).
4. If none connects, it brings the hotspot back, so the robot is never left without Wi-Fi.

It never touches `eth0` or `usb0`. Runs never overlap (`flock`). Every decision is logged.

## Risk

Each failed attempt takes the hotspot down for up to about a minute. This only happens when nobody is connected to the hotspot. A device that left the hotspot less than its lease time ago can still count as a client, which only delays the retry.

## Install and remove

Copy this folder to the robot, then:

```bash
sudo bash install.sh
sudo bash uninstall.sh      # undo: removes exactly the three installed files
```

Installed files: `/usr/local/sbin/tb4-wifi-retry`, `/etc/systemd/system/tb4-wifi-retry.service`, `/etc/systemd/system/tb4-wifi-retry.timer`.

## Verify

```bash
systemctl list-timers tb4-wifi-retry.timer
journalctl -t tb4-wifi-retry
```

Exit codes: 0 nothing to do, skipped, or joined a network; 10 no network joined and the hotspot was restored; 11 hotspot restore failed; 12 NetworkManager state unreadable.

## Offline test

`python TurtleBot/tests/offline/test_wifi_retry.py` runs the real script against stub `nmcli`, `ip`, `logger` and `flock` (needs bash, no robot).
