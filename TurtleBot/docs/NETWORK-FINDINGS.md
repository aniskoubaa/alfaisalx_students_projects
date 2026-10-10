# Network and connectivity: robot Wi-Fi drops (2026-10-04 and 2026-10-05) and the lab router

Markdown version of [network-and-connectivity.html](network-and-connectivity.html), for reading on GitHub (the HTML page has the network diagram). The admin record is in [MAINTENANCE.md](../MAINTENANCE.md#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05); the tasks are [ROADMAP.md, TB-20](../ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving), [TB-21](../ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router) and [TB-22](../ROADMAP.md#tb-22-secure-the-lab-router). Instructions for users: [HOW-TO-CONNECT.md, Troubleshooting](../HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found).

| | |
|---|---|
| Robot | Lab TurtleBot 4 Standard, `ubuntu@turtlebot4.local` or the address on its display |
| Fault | The robot answers SSH only briefly, then drops off the Wi-Fi; `turtlebot4.local` fails now and then |
| Seen | 2026-10-04, about 15:42 (robot time, EDT) and 2026-10-05, afternoon (laptop time, UTC+3) |
| Status on 2026-10-10 | **Open. Fix proposed, not applied.** Cause not confirmed |
| Likely cause | Wi-Fi power saving on the Raspberry Pi (diagnosis, not confirmed) |
| Robot changes | None for this problem. The only robot change since 2026-10-04 is `~/robot_code/motion_shapes.py` (R11) |
| Lab router | Linksys WRT54G set up on 2026-10-05. **The robot is not on it** |
| Times | 2026-10-04: robot clock (EDT, UTC-4). 2026-10-03 and 2026-10-05: laptop clock (UTC+3) |

## Networks around the robot

The Pi has one Wi-Fi interface, `wlan0`, which is either on `Students` or runs the robot's own access point.

| Network | Who is on it | Addresses | Status on 2026-10-10 |
|---|---|---|---|
| `Students` (campus Wi-Fi) | Laptops; the robot's `wlan0` (NetworkManager priority 10) | Robot by DHCP, `10.87.x.x` (`10.87.10.205` on 2026-10-03 and 2026-10-04), subnet `10.87.0.0/18`. HTTPS to the internet works; NTP and ping are blocked | Normal network; robot drops off since 2026-10-04 |
| `Turtlebot4` (robot's own access point) | A laptop that joins it; used by the robot only when `Students` is not available (priority 0) | Robot always `10.42.0.1`; laptops `10.42.0.x`. 5 GHz. No internet | Fallback, unchanged |
| Pi to Create 3 link | The Pi (`usb0`) and the base | Pi `192.168.186.3`, base `192.168.186.2` (web page on port 80) | Internal; not reachable from a laptop |
| Lab router (Linksys WRT54G) | A laptop on a cable (2026-10-05 test). Not the robot | Admin `192.168.1.1`; LAN `192.168.1.x` by DHCP (the laptop got `192.168.1.103`); uplink by wall Ethernet to the campus network | Set up; robot not moved (proposal) |

## Timeline and evidence

| When | Clock | What was seen | Result |
|---|---|---|---|
| 2026-10-03, during the motion test (about 20:31) | Laptop, UTC+3 | SSH dropped as docking started; the robot briefly left the Wi-Fi while moving, likely roaming between campus access points. The dock command was re-sent detached and the robot docked | Known |
| 2026-10-04, about 11:44 to 12:31 | Robot, EDT | Lidar checks and motion runs over SSH ([test results](test-results.html)) | Worked |
| 2026-10-04, between sessions | Robot, EDT | The robot was off the network for about 1.5 hours. It was powered off between sessions; the cause of the drop is not confirmed | Not confirmed |
| 2026-10-04, about 15:42 | Robot, EDT | After being switched on, the robot answered SSH once: up 4 min, address `10.87.10.205`, clock correct, lidar on USB. Then it dropped off the network. `turtlebot4.local` failed to resolve intermittently. It did not come back during about 25 minutes of watching | Dropped |
| 2026-10-05, afternoon | Laptop, UTC+3 | SSH by address and by key worked for about a minute, then the robot disappeared again. Afterwards it answered only in short windows (about 10 to 40 s). The laptop's Wi-Fi stayed fine the whole time. The robot's logs showed no Wi-Fi disconnects (which log was read is not recorded) | Dropped |
| 2026-10-05 | Laptop, UTC+3 | Lab router set up and measured with a laptop on a cable. The robot was not moved to it | Router up |
| 2026-10-10 | n/a | Documentation updated. The fix is still not applied and the robot has not been rechecked | Open |

## Likely causes (diagnosis, not confirmed), most likely first

1. **Wi-Fi power saving on the Raspberry Pi.** It is on by default in Ubuntu, and the robot's `Students` profile (written on 2026-10-03 by `write_keyfile.py`) sets no value. With it on, the Pi stays associated with the access point but stops answering incoming connections most of the time. This fits the evidence: no disconnects in the robot's logs, a healthy laptop Wi-Fi, and short answer windows.
2. **`turtlebot4.local` (mDNS) is unreliable on the campus Wi-Fi.** This explains the name failures, not the failures by address. Use the address on the robot's display instead, for example `ssh ubuntu@10.87.10.205`.
3. **Roaming between campus access points**, which also drops SSH while the robot drives (known since 2026-10-03). Run motion programs detached.

## Proposed fix for cause 1 (not applied)

Run in a terminal on the robot by a person who knows the `ubuntu` password (`sudo` asks for it). Connect by the display address first, retrying if needed.

```bash
sudo nmcli connection modify Students 802-11-wireless.powersave 2
sudo nmcli connection up Students
```

| | |
|---|---|
| Verify | `nmcli -g 802-11-wireless.powersave connection show Students` should print the value for "disable", 2. Then check from a laptop that the robot keeps answering over a longer time (TB-20: 30 attempts over 30 minutes, on two days) |
| Undo | The same command with `powersave 0` (the default): `sudo nmcli connection modify Students 802-11-wireless.powersave 0`, then `sudo nmcli connection up Students` |
| Risk | The Wi-Fi reconnects, so SSH may drop for a few seconds. No reboot. If the session drops after the first command, log in again and run the second |
| Record | When applied: add it to the MAINTENANCE.md change register as R14, with the date, and update the incident and Known issues |
| If it does not help | Record that cause 1 is ruled out, read the robot's NetworkManager log during a drop, and consider the lab router (below) |

## Workarounds that worked

1. **Connect by IP address.** Read the address on the robot's display and use it instead of `turtlebot4.local`.
2. **Retry in a loop.** The robot answers in short windows, so keep trying. These loops reconnect until you log out normally (ssh exits with 255 when it cannot connect or loses the connection). Set up key login first; press Ctrl+C to stop trying. Replace the example address with the one on the display.

   macOS and Linux (also Git Bash on Windows):

   ```bash
   while true; do ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; [ $? -ne 255 ] && break; sleep 5; done
   ```

   Windows PowerShell:

   ```powershell
   while ($true) { ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; if ($LASTEXITCODE -ne 255) { break }; Start-Sleep 5 }
   ```

3. **The robot's own access point.** When the display shows `10.42.0.1`, join `Turtlebot4`. To keep internet at the same time the laptop needs a second Wi-Fi adapter (or Ethernet, or phone tethering).

## Lab router (set up 2026-10-05)

Set up on 2026-10-05 by Ibrahim, with the AI assistant, as a dedicated lab network. **The robot has not been moved to it, and nothing on the robot was changed for it.** No login or Wi-Fi password is recorded here.

| Item | Value |
|---|---|
| Model | Linksys WRT54G: old 802.11g, 2.4 GHz only. Firmware very old (end of life); version not recorded |
| Admin page | `http://192.168.1.1`. Admin login still the factory default when it was set up; credentials changed on 2026-10-10 by the lab RA (not recorded here) |
| LAN | `192.168.1.x` with DHCP; a laptop on a cable got `192.168.1.103` |
| Uplink | The university wall Ethernet cable in the router's **Internet** port. The first cable gave no internet; a different cable worked |
| Wi-Fi | SSID starting with `AlfaisalX` (exact final name not confirmed in the record; read it on the router's Wireless page). WPA2-Personal with AES |

Measured on 2026-10-05 with a laptop on a cable:

| Measurement | Value |
|---|---|
| Packet loss | 0 % |
| Round trip to the router | About 7 ms |
| Round trip to the campus network (first hop `10.22.10.253`) | About 6 ms |
| DNS and HTTPS | Work |
| Download | About 12 to 13 Mbit/s on two runs, against about 3 Mbit/s on the `Students` Wi-Fi in the same test |
| ICMP ping to the internet | No reply through this wall port (websites work) |
| Not measured | Throughput over the router's Wi-Fi, NTP through the router, ROS 2 discovery, any robot traffic |

Security to-dos ([TB-22](../ROADMAP.md#tb-22-secure-the-lab-router)):

- Change the factory admin login; keep the new one in the lab password manager, never in this repository. **Done 2026-10-10** (credentials changed by the lab RA).
- Keep the admin page reachable from the lab network only: the WRT54G firmware is end of life.
- Consider a newer router.

## Proposal: put the robot on the lab router (not done)

A robot change that needs `sudo`. The full steps, with commands, are in [ROADMAP.md, TB-21](../ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router). First decide, using the result of the power-saving fix, whether staying on `Students` is enough.

1. Secure the router first (TB-22). Read the exact SSID and the robot's Wi-Fi hardware address.
2. Reserve a fixed address for the robot on the router (check that the WRT54G firmware offers DHCP reservations).
3. Add a NetworkManager Wi-Fi profile for the lab router on the robot, with a higher autoconnect priority than `Students` (10), for example 20. The Wi-Fi password is typed at a hidden prompt, as for `Students`. The `Turtlebot4` access point stays as the last fallback.
4. Test it once with autoconnect off, ideally with a scripted test phase that returns to `Students` by itself, as on 2026-10-03.
5. Check the same address after reboots, the fallback to `Students` with the router off, SSH stable for 30 minutes, and the `/scan` rate on a laptop. Record the change in MAINTENANCE.md with verify and undo.

| Expected benefit | Risk or cost |
|---|---|
| A stable address (reservation), no reliance on `turtlebot4.local` | 2.4 GHz 802.11g is slow: fine for SSH and topics like `/odom`; check `/scan` and camera bandwidth |
| No campus roaming or client limits | End-of-life router firmware (TB-22) |
| Likely working ROS 2 discovery between a laptop and the robot ([TB-09](../ROADMAP.md#tb-09-ros-2-from-a-laptop-over-campus-wi-fi)); not tested | Users must join the lab Wi-Fi (password from the maintainer) |
| Laptops on the lab network keep internet through the router's uplink | Outside the router's range, or with it off, the robot falls back to `Students` |

Verify: `nmcli -t -f NAME,DEVICE connection show --active` shows the lab profile on `wlan0`, and `ip -4 -br addr show wlan0` shows the reserved `192.168.1.x` address. Undo: `sudo nmcli connection delete "<lab SSID>"`; the robot returns to `Students`; then remove the reservation on the router.

## Not known yet

- Whether power saving is actually on for `wlan0` on this robot (the value has not been read).
- Why the robot did not come back at all for about 25 minutes on 2026-10-04, and why it was off the network for about 1.5 hours earlier that day.
- Which robot log was read on 2026-10-05.
- Whether the drops also happen on the lab router network.
- The lab router's exact SSID and firmware version, and whether its firmware offers DHCP reservations.
- Whether NTP works through the lab router (relevant to the clock problem, [TB-04](../ROADMAP.md#tb-04-choose-a-reliable-time-strategy)).

Step log: [General Tasks/TurtleBot4 - network and connectivity.txt](../../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt). No passwords, Wi-Fi keys or router logins in this file.
