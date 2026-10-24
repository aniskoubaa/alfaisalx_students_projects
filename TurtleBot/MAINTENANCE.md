# TurtleBot 4: Maintenance and Configuration Record

| | |
|---|---|
| Robot | Lab TurtleBot 4 Standard, hostname `turtlebot4` |
| Owner | AlfaisalX lab, College of Engineering and Advanced Computing. Ask the lab maintainer or the lab supervisor for access, passwords and approval of changes |
| Last updated | 2026-10-24 (Wi-Fi power-save setting changed, R14; supervised motion test with a timing recorder; read-only checks of the Wi-Fi logs). Evening of 2026-10-24: home Wi-Fi network added (R16), supervised motion through TurtleBot Studio over Wi-Fi, base clock re-synchronised and the Create 3 application restarted twice (runtime actions, no configuration change), Ubuntu auto-updates found running. Earlier: 2026-10-10. State as of 2026-10-10: no change to the robot since 2026-10-04; the robot was last reached over SSH on 2026-10-05 (briefly). Earlier: 2026-10-04 (robot state as of 2026-10-04, about 12:30 robot time) |
| Audience | Lab maintainers and whoever administers the robot next |
| Covers | Current configuration, every change made, admin scripts, incidents, open issues, health checks |
| Times | 2026-10-03 entries use the original author's laptop time (UTC+3). 2026-10-04 entries use the robot's own clock as shown in its journal (EDT, UTC-4), so 11:44 robot time is 18:44 in UTC+3. 2026-10-05 entries use laptop time (UTC+3). 2026-10-24 entries use laptop time (UTC+3) or seconds since the start of the recording; the robot's own clock was about two years wrong that day (it read 28 October 2024) |

## Purpose

This is the administrative record for the lab's TurtleBot 4. Everyday use (connecting, running code) is in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md). Planned work is in [ROADMAP.md](ROADMAP.md). The raw chronological logs, including failed attempts, are in [General Tasks/TurtleBot4 - connect to university Wi-Fi.txt](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt) (2026-10-03) and [General Tasks/TurtleBot4 - lidar check and motion programs.txt](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt) (2026-10-04), and [General Tasks/TurtleBot4 - network and connectivity.txt](../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt) (2026-10-04 evening to 2026-10-10). Illustrated write-ups (lidar diagnosis, motion program design, test results, network and connectivity) are in [docs/](docs/index.html).

Rule followed: change only what is necessary on shared hardware, and record every change with how to verify it and how to undo it. When you change the robot, add a row to the [change register](#change-register) in the same commit.

No Wi-Fi passwords, keys or other credentials are recorded here or anywhere in this repository (it is public). One exception, decided by the lab maintainer on 2026-10-25: the robot's `ubuntu` login password (the TurtleBot 4 factory default) is written in [README.md](README.md) and [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) so lab members can connect easily.

### State on 2026-10-24

The robot was reached over a direct Ethernet cable ([HOW-TO-CONNECT.md](HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed)) and was running its own `Turtlebot4` hotspot, because `Students` was not in range. Times are laptop time (UTC+3) unless marked; the robot clock was wrong (see below), so recording times are given as seconds since the start of the recording.

| Area | State on 2026-10-24 | Details |
|---|---|---|
| Robot configuration | **One change: R14.** The `Students` profile now has Wi-Fi power saving switched off. Applied by the user typing the `sudo` password (about 00:22 laptop time, as recorded). `nmcli connection up Students` was **not** run, so the setting takes effect the next time the robot joins `Students`. **Later the same day, R16:** a saved home Wi-Fi network (`TP-LINK_Extender_5GHz`) added through TurtleBot Studio, about 04:49; the robot left its hotspot and joined it | [R14, R16](#change-register) |
| Wi-Fi drops | **Fix applied, effect not verified.** The robot cannot be tested on `Students` until it is on campus. New evidence: power saving was on (global NetworkManager file); the logs show no disconnects on the symptom days | [Wi-Fi incident, update 2026-10-24](#update-2026-10-24-new-evidence-and-fix-applied-r14), [ROADMAP.md, TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving) |
| `/odom` pauses | **Cause located in the Create 3 base**, triggered when the base starts to move. A 3.16 s stall on 2026-10-24 aborted `motion_shapes.py`. **Update, evening, over Wi-Fi:** stalls of 7.5 s and 11 s while docked and idle, and 7.8 s in a spin that aborted; not a Wi-Fi effect, and a base restart did not remove them. Possible link to new ROS 2 participants joining the graph (hypothesis, not proven) | [Finding, update 2026-10-24](#update-2026-10-24-measurements-with-the-timing-recorder), [TB-15](ROADMAP.md#tb-15-characterise-the-odom-pauses-at-motion-start), [TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving) |
| Lidar | Detected and working after a manual `/start_motor`. **New issue:** the lidar motor did not restart by itself after undocking | [Known issues](#known-issues), [TB-24](ROADMAP.md#tb-24-lidar-motor-does-not-restart-after-undocking) |
| Clock | **Wrong:** 28 October 2024, about two years behind. `tb4-https-time.service` failed (no internet over the cable or the hotspot). Not touched, as required while ROS runs. **Update, evening (laptop time, UTC+3):** correct on the Pi since R16 (internet reached at 04:49; `chronyd` stepped it by +62,648,406.93 s, about 1.99 years, while ROS ran). The Create 3 base kept its 2024 clock until the base clock re-sync at 05:20 and 05:21 (22:20 and 22:21 robot time); the Pi and base clocks then agreed within 1 s | [Known issues](#known-issues), [TB-17](ROADMAP.md#tb-17-decide-whether-to-keep-or-remove-the-clock-fix), [clock incident update](#update-2026-10-24-clock-stepped-by-the-internet-and-base-re-sync) |
| Runtime actions | Undock, `/start_motor` by hand, one `motion_shapes.py` attempt, dock. No configuration change. **Evening:** undock, two spins and a circle through Studio, dock, base clock re-sync and two Create 3 application restarts ([runtime table](#restarts-and-service-interruptions)) | [Restarts and service interruptions](#restarts-and-service-interruptions) |
| Base | Create 3 firmware `I.0.0.FastDDS` (ROS Iron), read from the base's web page meta (`http://192.168.186.2`). Pi and base clocks agreed (median offset 31 ms) | [Current configuration](#robot) |

### State on 2026-10-10

| Area | State on 2026-10-10 | Since | Details |
|---|---|---|---|
| Robot configuration | **Unchanged since 2026-10-04.** The only robot change since 2026-10-03 is `~/robot_code/motion_shapes.py` (R11). No `sudo` was used, no setting was changed, the clock fix (R7, R8) was not touched | 2026-10-04 | [Change register](#change-register) |
| Robot Wi-Fi | **Open: the robot drops off the Wi-Fi** and answers SSH only in short windows. Likely cause Wi-Fi power saving on the Pi (diagnosis, not confirmed). Fix proposed, **not applied** | 2026-10-04, about 15:42 robot time | [Wi-Fi incident](#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05), [ROADMAP.md, TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving) |
| `turtlebot4.local` | Failed to resolve intermittently on the campus Wi-Fi. Use the address on the robot's display | 2026-10-04 | [Known issues](#known-issues) |
| Lab router | Linksys WRT54G set up as a lab network on 2026-10-05. **Not used by the robot**; nothing on the robot was changed for it. Its admin login was still the factory default when it was set up; the router's credentials were changed on 2026-10-10 by the lab RA (reported by the RA; the new credentials are not recorded in this repository: ask the lab maintainer) (to-do) | 2026-10-05 | [Lab router](#lab-router-not-used-by-the-robot-yet), [TB-21](ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router), [TB-22](ROADMAP.md#tb-22-secure-the-lab-router) |
| Lidar | On USB after the robot was switched on again on 2026-10-04 (one SSH check at about 15:42 robot time, uptime 4 min). This is the first check after a power-on separate from the reseat; no `/scan` result was recorded then | 2026-10-04 | [Lidar record](#incident-lidar-not-detected-2026-10-03-resolved-2026-10-04) |
| Pending on the robot | Copy the new programs (R12, not applied); first robot runs of `health_check.py`, `sensor_report.py`, the new shapes and the connect tool; a complete figure eight; the cause of the `/odom` gaps (TB-15); the clock-fix decision (TB-17); the Wi-Fi power-saving fix (TB-20); the network decision (TB-21) | 2026-10-04 | [ROADMAP.md, state on 2026-10-10](ROADMAP.md#state-on-2026-10-10) |
| Way of working | Robot motion tests are run supervised, in short batches, with a person next to the robot. An unattended test campaign on 2026-10-04 was blocked by the AI tool's safety guard; the campaign (TB-16) is still open | 2026-10-04 | [ROADMAP.md, TB-16](ROADMAP.md#tb-16-motion-program-test-campaign-and-demo-shapes) |
| Repository | GitHub Desktop switched the local clone to `main` with TurtleBot changes uncommitted (2026-10-05). Resolved 2026-10-10, nothing lost | 2026-10-05 | [Maintainer note](#repository-note-branch-switch-in-github-desktop-2026-10-05-resolved-2026-10-10) |

### State on 2026-10-04

- **Working:** everything listed for 2026-10-03, plus: the lidar is detected again and publishes `/scan` off the dock. It was fixed by reseating its USB cable; see the [lidar record](#incident-lidar-not-detected-2026-10-03-resolved-2026-10-04). The Create 3 base sends data (`/dock_status` received; Pi and base clocks within seconds of each other). Undock succeeded at about 12:09 robot time. The new program `motion_shapes.py` drove a square, a 360 degree rotation and a back-and-forth run.
- **Still installed:** the HTTPS clock fix (R7, R8). On this boot the robot clock was correct (2026) and the base talked to ROS, so `undo-clock` was not run. Keep or remove is an open decision ([ROADMAP.md, TB-17](ROADMAP.md#tb-17-decide-whether-to-keep-or-remove-the-clock-fix)). Do not change the clock while ROS runs.
- **New finding:** the base pauses `/odom` for 0.4 to 1.0 s when the wheels start moving. See [the finding](#finding-odom-pauses-at-motion-start).
- **No configuration change** on 2026-10-04: no `sudo`, no service or system file changed. Only user files were added (R11 onward).

### State at handover (2026-10-03)

- **Working:** Students Wi-Fi with the robot's own access point as fallback, `turtlebot4.local` name resolution, key-based SSH and VS Code access, screen and light ring, undock, spin and dock (all verified on 2026-10-03, before the full power cycle).
- **Pending admin action:** remove the clock fix and resync the Create 3 base. See the [incident report](#incident-create-3-base-stopped-responding-after-the-clock-fix). Until this is done the base is expected to send no data.
- **Pending physical check:** the lidar is not detected on USB. See [Known issues](#known-issues).

## Current configuration (as of 2026-10-03, rechecked where marked on 2026-10-04)

### Robot

| Item | Value |
|---|---|
| Model | TurtleBot 4 Standard (has the screen that shows the robot's address) |
| Image version | 2.0.2 |
| Operating system | Ubuntu 24.04.1 Server, no desktop |
| ROS | ROS 2 Jazzy, Fast DDS (`RMW_IMPLEMENTATION=rmw_fastrtps_cpp`), `ROS_DOMAIN_ID` 0. Read from `/etc/turtlebot4/setup.bash` on 2026-10-03; recheck with the [verification checklist](#verification-checklist). Rechecked in a login shell on 2026-10-04: same values, plus `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` |
| Lidar | Slamtec RPLIDAR on USB through a Silicon Labs CP210x bridge (`lsusb` ID `10c4:ea60`); device link `/dev/RPLIDAR` points to `ttyUSB0`. On 2026-10-04 the driver node `rplidar_composition` reported firmware 1.29, hardware revision 7, health status 0, scan mode Sensitivity, 12 m maximum range. Mounted turned +90 degrees: transform `base_link` to `rplidar_link` is translation (-0.040, 0, 0.193) m, yaw +90 degrees. Switched off on the dock by the TurtleBot 4 power saver |
| `/cmd_vel` | `geometry_msgs/msg/TwistStamped` (rechecked 2026-10-04: subscriber `create3_repub`, best effort; `teleop_twist_joy` also publishes) |
| ROS bringup | systemd unit `turtlebot4.service` |
| User and hostname | `ubuntu` on `turtlebot4`, advertised as `turtlebot4.local` by avahi |
| Admin access | `sudo` asks for the `ubuntu` password; NetworkManager changes by `ubuntu` over SSH also ask for it |
| Clock | Factory chrony setup, which cannot reach NTP on campus. No battery-backed clock: after a power cycle the Pi came back in October 2024. HTTPS clock fix installed on 2026-10-03; removal prepared but not run. On 2026-10-04 the fix was still installed, the clock was correct (2026) and the base talked to ROS. Keep or remove: open decision (ROADMAP TB-17) |
| Setup tool | `turtlebot4-setup` is not on `PATH` in this image; Wi-Fi was configured with `nmcli` and a keyfile |
| Load note | The OAK-D camera container uses about one CPU core |
| Create 3 base firmware (added 2026-10-24) | `I.0.0.FastDDS` (ROS Iron), read from the robot-info meta on the base's web page `http://192.168.186.2` |
| Wi-Fi hardware and driver (added 2026-10-24) | Driver `brcmfmac`, chip BCM43455, firmware 7.45.234. `iw` and `iwconfig` are not installed. The kernel log says `brcmf_cfg80211_set_power_mgmt: power save enabled` at every boot |
| Global Wi-Fi power saving (added 2026-10-24) | `/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf` sets `wifi.powersave = 3` (enable; the Ubuntu default). A profile with value `0` (default) inherits this. File not changed. Since R14 the `Students` profile overrides it with `2` (disable) |

### Network

| | `Students` | `netplan-wlan0-Turtlebot4` |
|---|---|---|
| Role | Primary: robot joins the university Wi-Fi | Fallback: robot's own access point (factory) |
| Defined in | NetworkManager keyfile `/etc/NetworkManager/system-connections/Students.nmconnection`, root only (mode 600). Added 2026-10-03 | netplan `/etc/netplan/50-wifis.yaml`. Not modified |
| SSID and security | `Students`, WPA2-Personal (one shared password) | `Turtlebot4`, 5 GHz |
| Robot address | DHCP, `10.87.x.x` (was `10.87.10.205/18` on 2026-10-03; it can change) | `10.42.0.1`; clients get `10.42.0.x` |
| Autoconnect priority | 10 | 0 |
| Wi-Fi power saving (added 2026-10-10) | Not set in the profile: the R1 keyfile written by `write_keyfile.py` has no power-save line, so NetworkManager's default applies, and power saving is on by default in Ubuntu (2026-10-05 diagnosis; the value was not read on the robot). Proposed: `2` (disable), [ROADMAP.md, TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving). Not applied | Not checked |

NetworkManager uses Students when it is in range and falls back to the access point otherwise. After the reboot on 2026-10-03 the robot came back on Students by itself. The robot joined Students on 5 GHz during the test phase and on 2.4 GHz in the permanent phase.

avahi is limited to `wlan0`, so `turtlebot4.local` resolves only to the Wi-Fi address. Before this change it sometimes resolved to `192.168.186.3`, the internal link to the base, which a laptop cannot reach. Since 2026-10-04 the name has also failed to resolve intermittently on the campus Wi-Fi (mDNS is unreliable there); use the address on the robot's display. See [Known issues](#known-issues).

### Wired and internal links (added 2026-10-24)

| Link | Value |
|---|---|
| `eth0` (Raspberry Pi Ethernet port) | `192.168.185.3/24`, static, from the TurtleBot 4 netplan file `40-ethernets.yaml`. No DHCP server on the cable, so a computer plugged in directly must use a `192.168.185.x` address or the robot's IPv6 link-local address (MAC `D8:3A:DD:41:D5:DF`, link-local `fe80::da3a:ddff:fe41:d5df` on 2026-10-24). How: [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed) |
| `usb0` | `192.168.186.3/24`, link to the Create 3 base at `192.168.186.2` |
| `wlan0` | `Students` (priority 10) or the own hotspot `Turtlebot4` (`10.42.0.1/24`, priority 0). On 2026-10-24 it was the hotspot |
| NetworkManager connections (2026-10-24) | `netplan-wlan0-Turtlebot4` (active), `netplan-eth0`, `netplan-usb0`, `Students` (autoconnect yes, priority 10, not active) |

### Lab router (not used by the robot yet)

Set up on 2026-10-05 by Ibrahim, with the AI assistant, as a dedicated lab network. **The robot has not been moved to this network, and nothing on the robot was changed for it.** Moving the robot is a proposal: [ROADMAP.md, TB-21](ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router). Security to-dos: [TB-22](ROADMAP.md#tb-22-secure-the-lab-router). No login or Wi-Fi password for the router is recorded here; ask the lab maintainer.

| Item | Value (2026-10-05) |
|---|---|
| Model | Linksys WRT54G: old 802.11g, 2.4 GHz only. Firmware very old (end of life); version not recorded |
| Admin page | `http://192.168.1.1`. Admin login: still the factory default when the router was set up; changed on 2026-10-10 by the lab RA (reported by the RA; the new credentials are not recorded in this repository: ask the lab maintainer). The router works after the change (reported by the RA) |
| LAN | `192.168.1.x`, addresses from the router's DHCP. A laptop on a cable got `192.168.1.103` |
| Uplink | The university wall Ethernet cable in the router's **Internet** port. The first cable tried gave no internet; a different cable worked |
| Wi-Fi | SSID set to a name starting with `AlfaisalX` (the exact final name is not confirmed in the record; read it on the router's Wireless page). WPA2-Personal with AES |
| Measured through the router (laptop on a cable) | 0 % packet loss; about 7 ms to the router and about 6 ms to the campus network (first hop `10.22.10.253`); DNS and HTTPS work; download about 12 to 13 Mbit/s on two runs, against about 3 Mbit/s on the `Students` Wi-Fi in the same test; ICMP ping to the internet gets no reply through this wall port (websites work) |
| Not measured | Throughput over the router's Wi-Fi; NTP through the router; ROS 2 discovery; any robot traffic |
| Used by the robot | **No** (as of 2026-10-10) |

Security to-dos (TB-22): change the factory admin login and store the new one in the lab password manager; keep the admin page reachable from the lab network only (the WRT54G firmware is end of life); consider a newer router.

Update 2026-10-10: the router's credentials were changed on 2026-10-10 by the lab RA (reported by the RA; the new credentials are not recorded in this repository: ask the lab maintainer). Still open in TB-22: confirm remote management is off, record the firmware version and the exact SSID here, and record the keep-or-replace decision.

### Create 3 base link

| Item | Value |
|---|---|
| Pi side | `usb0`, `192.168.186.3` |
| Base | `192.168.186.2` |
| Base web page | `http://192.168.186.2`, port 80 (port 8080 does not answer). Reachable from the robot only, not from a laptop |
| Restart the base application | "Restart Application" button on the web page, or `POST /api/restart-app` (the robot chimes). The base re-syncs its clock from the Pi when it restarts |

### Campus network facts (found on 2026-10-03)

- Devices on Students can reach each other (laptop to robot SSH works; no client isolation).
- HTTPS to the internet works (github.com and packages.ros.org returned 200). Plain HTTP checks were inconsistent.
- NTP and ICMP (ping) to the internet are blocked.
- ROS 2 discovery between a laptop and the robot across Students was not tested.
- Other university networks were not used: `AU-Students` is WPA2-Enterprise (PEAP, personal username and password; a device account from IT would be preferable to storing a personal login on a shared robot) and `AU-Students-WIFI` is open with a likely web login page, unsuitable for a robot without a browser.
- Added 2026-10-05: in a laptop download test the `Students` Wi-Fi gave about 3 Mbit/s (about 12 to 13 Mbit/s through the lab router's cable uplink in the same test). `turtlebot4.local` (mDNS) failed intermittently on campus on 2026-10-04. Campus access points move the robot between them (roaming), which drops SSH while it drives (since 2026-10-03).

## Change register

R1 to R10 were made on 2026-10-03, R11 onward on 2026-10-04. Run robot commands in a robot terminal.

Status check 2026-10-10: no change was made to the robot from 2026-10-05 to 2026-10-10, so there are no new rows. The statuses below are from the records; the robot itself was not rechecked (it could not be reached reliably, see the [Wi-Fi incident](#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05)). The Wi-Fi power-saving fix (TB-20) and a lab-router profile (TB-21) are proposals; when one is applied, add it here as R14 onward.

### On the robot

| ID | Change | Location | Purpose | Verify | Undo | Status |
|---|---|---|---|---|---|---|
| R1 | Wi-Fi profile `Students` (WPA2-Personal, `wlan0`, DHCP, autoconnect on, priority 10) | `/etc/NetworkManager/system-connections/Students.nmconnection` (root only, mode 600) | Join the university Wi-Fi; factory access point kept as fallback | `nmcli -f connection.id,connection.autoconnect,connection.autoconnect-priority connection show Students` | `sudo nmcli connection delete Students`, then `sudo reboot`. The robot returns to its `Turtlebot4` access point (10.42.0.1). Expect an SSH session over Students to drop; reconnect through the access point | Active |
| R2 | One SSH public key | `/home/ubuntu/.ssh/authorized_keys` | Password-free SSH and VS Code from the original author's workstation (key W1) | `ssh-keygen -lf ~/.ssh/authorized_keys` (lists key fingerprints) | Delete that key's line from the file | Active. The key belongs to one person's workstation: remove or replace it when that person leaves the project |
| R3 | Wi-Fi switch and admin scripts | `~/wifi-switch/` | Copies of the scripts in `TurtleBot/setup/`, the switch log `log.txt` and `students_ip.txt` | `ls -la ~/wifi-switch` | `rm -r ~/wifi-switch`, but only after `undo-clock` has run, because the R5 links point into this folder. Installed copies (R1, R6, R7, R8) are separate and keep working | Present |
| R4 | Example programs | `~/robot_code/` (`hello_robot.py`, `scan_test.py`, `clearance_check.py`, `drive_test.py`, `motion_test.sh`; copies in `TurtleBot/examples/`) | Folder VS Code opens for users | `ls -la ~/robot_code` | Delete the folder after saving any user files in it | Present. Users may have added files; detached runs write `motion.log` and `dock.log` here |
| R5 | Admin shortcuts (symlinks) | `~/finish-setup` to `root-setup.sh`, `~/fix-ros` to `fix-ros.sh`, `~/undo-clock` to `undo-clock.sh` | Short admin commands, run as `sudo ./name` from `~` | `ls -l ~/finish-setup ~/fix-ros ~/undo-clock` | `rm ~/finish-setup ~/fix-ros ~/undo-clock` (removes only the links) | Present. Proposed: remove `finish-setup` and `fix-ros` after `undo-clock` has run, since either one reinstalls the clock fix |
| R6 | avahi limited to Wi-Fi | `/etc/avahi/avahi-daemon.conf` (`allow-interfaces=wlan0` under `[server]`); original saved as `/etc/avahi/avahi-daemon.conf.before-tb4` | `turtlebot4.local` resolves only to the Wi-Fi address | `grep -n '^allow-interfaces' /etc/avahi/avahi-daemon.conf` | `sudo cp /etc/avahi/avahi-daemon.conf.before-tb4 /etc/avahi/avahi-daemon.conf`, then `sudo systemctl restart avahi-daemon` | Active. Keep |
| R7 | HTTPS clock fix | `/usr/local/sbin/tb4-https-time`, `/etc/systemd/system/tb4-https-time.service`, `/etc/systemd/system/tb4-https-time.timer` (enabled: 60 s after boot, then every 15 min) | Set the clock from an HTTPS `Date` header, because campus blocks NTP | `systemctl list-unit-files 'tb4-https-time*'` | `cd ~ && sudo ./undo-clock` (removes R7 and R8, restarts ROS); [manual steps](#removing-the-clock-fix-by-hand) | Removal prepared (`sudo ./undo-clock`), not confirmed run as of 2026-10-03. Caused the incident below. **2026-10-04: still installed** (timer file present), clock correct, base talking; left in place by the user's decision. Keep or remove: ROADMAP TB-17. **2026-10-10:** not touched since; last seen installed on 2026-10-04 |
| R8 | ROS waits for the clock (drop-in) | `/etc/systemd/system/turtlebot4.service.d/10-wait-for-clock.conf` (`Wants=` and `After=tb4-https-time.service`) | Start `turtlebot4.service` only after the clock fix has run | `systemctl cat turtlebot4` (the drop-in is listed at the end if present) | Removed by `sudo ./undo-clock`; [manual steps](#removing-the-clock-fix-by-hand) | Removal prepared (`sudo ./undo-clock`), not confirmed run as of 2026-10-03. **2026-10-04: still installed** (drop-in present). See R7. **2026-10-10:** not touched since; last seen installed on 2026-10-04 |
| R9 | VS Code server | `~/.vscode-server` (207 MB download, about 600 MB unpacked) | Installed automatically by VS Code Remote-SSH on the first connect | `du -sh ~/.vscode-server` | `rm -rf ~/.vscode-server`. VS Code downloads it again on the next connect (about 10 minutes over campus Wi-Fi) | Present. Safe to delete |
| R10 | Temporary switch job | Transient systemd unit `tb4-wifi-switch` and `/run/tb4-wifi-controller.sh`, created by `start.sh` | Ran `controller.sh` in the background | `systemctl status tb4-wifi-switch` (expected: unit not found) | None needed: `/run` is cleared at boot and the unit was started with `--collect` | Gone after the reboot at about 19:56 |
| R11 | Motion program `motion_shapes.py` (2026-10-04) | `~/robot_code/motion_shapes.py` (copy of [examples/motion_shapes.py](examples/motion_shapes.py)) | Drive test shapes closed-loop on `/odom`, with safety stops | `ls -l ~/robot_code/motion_shapes.py` | `rm ~/robot_code/motion_shapes.py` | Present. User file, no system change. The version on the robot may lag the repo copy during testing; compare before relying on it. **2026-10-10:** unchanged; last seen 2026-10-04 |
| R12 | Further example programs (2026-10-04) | Not deployed yet: the programs are in [examples/](examples/) only. The robot went offline before they could be copied. When copied, list them here (`health_check.py`, `sensor_report.py`, `lidar_snapshot.py`, `lightring_status.py`, `more_shapes.py`, `wall_approach.py`, `keep_distance.py`, `motion_common.py`, `campaign.sh`) | More example programs | `ls -l ~/robot_code` | Delete the listed files | Not applied. **2026-10-10:** still not applied (planned in ROADMAP TB-23) Note 2026-10-10: `clearance_check.py` was fixed in the repository (its fallback when TF is missing is now +90 deg instead of 0 deg); the copy on the robot from 2026-10-03 has the old fallback, so copy the fixed file along with the others. |
| R13 | Test results folder (2026-10-04) | Not created. The 2026-10-04 run logs were copied from `/tmp` on the robot into [tests/logs/](tests/logs/) | Keep the raw run logs | n/a | n/a | Not applied. **2026-10-10:** unchanged |
| R14 | Wi-Fi power saving off in the `Students` profile (2026-10-24, about 00:22 laptop time, UTC+3). Applies TB-20 steps 3 and 4 only | `/etc/NetworkManager/system-connections/Students.nmconnection` (root only). The global file `/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf` and the `Turtlebot4` profile were not touched | Stop the Pi's Wi-Fi from sleeping; leading cause of the SSH drops of 2026-10-04 and 2026-10-05 (diagnosis, not confirmed) | `nmcli -g 802-11-wireless.powersave connection show Students` prints `disable` | `sudo nmcli connection modify Students 802-11-wireless.powersave 0`, which restores the value before (`default`) | Applied by the user typing the `sudo` password. Command run: `sudo nmcli connection modify Students 802-11-wireless.powersave 2`. Before: `default`; after: `disable`. `nmcli connection up Students` was **not** run (`Students` was out of range and bringing it up would have disturbed the hotspot), so the setting takes effect the next time the robot joins `Students`. **Effect not verified until the robot is on campus** (TB-20 steps 5 and 6, and TB-26) |
| R15 | Run-log folder created by TurtleBot Studio (2026-10-24, laptop time about 00:45 to 01:15) | `~/robot_code/logs/` (empty at the end of the test; Studio keeps run logs and `.pid` files of the programs it starts there) | Used by [TurtleBot Studio](tools/studio/README.md), the tool for running and stopping programs | `ls -ld ~/robot_code/logs` | `rm -r ~/robot_code/logs` (user files only; Studio creates it again when needed) | Present. User files only: no `sudo`, no system change. The Studio test folder `~/robot_code/studio_test` and its logs were removed after the test |
| R16 | Saved Wi-Fi network for a home test network, `TP-LINK_Extender_5GHz` (2026-10-24, about 04:49 laptop time, UTC+3). Added with TurtleBot Studio, Wi-Fi tab, **Add to the robot** with "Switch the robot to it right now" ticked | New file `/etc/NetworkManager/system-connections/studio-TP-LINK_Extender_5GHz.nmconnection` (root only, mode 600; its date shows 2024 because the robot clock was still wrong when it was written). Autoconnect on, priority 10, Wi-Fi power save off (`2`). The `Students` profile, the `Turtlebot4` hotspot profile and netplan were not touched | Put the robot on the home Wi-Fi while it was away from campus, and the first real test of Studio's Add flow (TB-27) | `nmcli -g connection.autoconnect,connection.autoconnect-priority,802-11-wireless.powersave connection show TP-LINK_Extender_5GHz` prints `yes`, `10`, `disable`; while in range `nmcli -t -f NAME,DEVICE connection show --active` lists it on `wlan0` | `sudo nmcli connection delete id TP-LINK_Extender_5GHz` (or Studio, Wi-Fi tab, **Remove**). Out of range the robot falls back to `Students` or its own hotspot by itself, so the entry is harmless on campus | Applied by the user typing the Wi-Fi password and the `sudo` password in the terminal Studio opened. The robot joined at once: `wlan0` 192.168.100.31/24, channel 36 (5 GHz), signal 61 % (-60 dBm), default route via the home router, and the clock synchronised for the first time since 2026-10-04. Studio then connected over Wi-Fi only (cable unplugged) through `turtlebot4.local`. **Side effect:** with internet, Ubuntu's `apt-daily` timer started `unattended-upgrade --download-only` (one core at 100 %, nice 19); see [Known issues](#known-issues). **Added later the same evening:** the Pi clock was stepped by chrony while ROS ran, and the Create 3 base clock had to be re-synchronised by hand (base runtime actions, below). The Remove flow was not run, so the undo above is still only the `nmcli` command. The robot goes back to the lab on 2026-10-25; the entry does no harm out of range. **Removed on 2026-10-25 by R21** |
| R17 | Wi-Fi power saving off for **all** networks by a global NetworkManager drop-in (2026-10-24, laptop time UTC+3: file created 14:54, renamed and effective 15:18; robot 07:54 and 08:18 EDT) | New file `/etc/NetworkManager/conf.d/zz-wifi-powersave-off.conf` (root, 644), content `[connection]` / `wifi.powersave = 2`. The existing `default-wifi-powersave-on.conf` (`wifi.powersave = 3`) was not edited; the `zz-` name makes NetworkManager read it after `default-...` (files are read in alphabetical order, digits before letters, so the first name `99-...` was overridden and had no effect) | Turn Wi-Fi power saving off for every profile that does not set its own value (the `Turtlebot4` hotspot profile, still `default`, and any future network), instead of profile by profile (R14, R16). Supports TB-20 | `NetworkManager --print-config | grep powersave` prints `wifi.powersave=2` (no root needed); the header line lists `etc: default-wifi-powersave-on.conf, zz-wifi-powersave-off.conf` | `sudo rm /etc/NetworkManager/conf.d/zz-wifi-powersave-off.conf && sudo nmcli general reload conf` | Applied by the user typing the `sudo` password, in two steps: `printf ... | sudo tee /etc/NetworkManager/conf.d/99-wifi-powersave-off.conf` plus `sudo nmcli general reload conf` (still `3`), then `sudo mv ... zz-wifi-powersave-off.conf` plus reload. After: `wifi.powersave=2`. Journal: `op="reload" result="success"` both times; no Wi-Fi drop, the robot stayed on `TP-LINK_Extender_5GHz`. A profile with its own value keeps it (`Students` and `TP-LINK_Extender_5GHz` are `disable`). The value is applied to a connection when it is next activated. **Not yet checked after a reboot**, and the effect on the campus drops is still TB-20 |
| R18 | User lingering on for `ubuntu` (2026-10-24, laptop time UTC+3 about 17:07; robot about 10:07 EDT) | systemd-logind state (`/var/lib/systemd/linger/ubuntu`); no config file edited. Side effect: a systemd user manager for `ubuntu` now runs permanently (about 10 MB) and starts Ubuntu's default user units (obex, gpg-agent sockets and similar; no custom user units exist) | Stop systemd-logind from deleting the shared memory of `ubuntu` (and with it Pi-local ROS delivery) when the last login session closes; see [Known issues](#known-issues) and the TB-25 evening update | `loginctl show-user ubuntu -p Linger` prints `Linger=yes`; while the bringup runs, `ls /dev/shm \| grep -c fastrtps` is above 0; after logging out and in again, `ros2 topic hz /odom` shows about 20 Hz | `sudo loginctl disable-linger ubuntu` (the Pi-local silence then returns after the last SSH logout) | Applied by the user typing the `sudo` password: `sudo loginctl enable-linger ubuntu`, then `sudo systemctl restart turtlebot4` (active 10:08:21 robot time). Verified: after the user's logout and three more logouts, 93 `fastrtps` files remained, `/odom` 19.997 Hz, `/dock_status` 1 Hz. Alternative not applied: a logind drop-in with `RemoveIPC=no`. **Not yet checked after a reboot** |
| R19 | Saved Wi-Fi network removed from the Create 3 base (2026-10-24, laptop time UTC+3 23:03:13; robot 16:03:13 EDT, base 20:03:13 UTC). TB-25 change A, approved by the user | Create 3 network settings (its saved SSID and password keys). Its ROS settings (domain, namespace, RMW, discovery server, RMW profile), NTP setting and firmware were not touched | The base had no IP address but kept searching for a saved network it could not find: a Wi-Fi scan and a failed DHCP request about every 7.5 s on a base that idles at about 55 % CPU. The TurtleBot 4 Jazzy manual keeps the base off the Wi-Fi. See [ROADMAP.md, TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving) | From a robot terminal: `curl -s -m 10 http://192.168.186.2/logs-raw \| grep -E 'SCAN-STARTED\|sending discover' \| tail -n 3` shows no lines after 20:03:17 base time; the base's Wi-Fi page shows no IP address | Connect the base to a network again on its web page (Connect); needs that network's name and password, which were not visible. Normally not wanted | Applied from the Pi with `curl -X POST http://192.168.186.2/api/forget-wifi` (the call behind the base's "Forget Wi-Fi Network" button; reply `{"status":"Forgetting Wi-Fi network."}`). The base logged "Forget WiFi network command received. Clearing WiFi credentials now", deleted `network.ssid` and `network.password`, stopped its DHCP client and took `wlan0` down; ping to the base stayed at 0.4 to 0.9 ms; its CPU peaked at 96 % in that minute. No base restart. Effect on the stalls: see the TB-25 update |
| R20 | Robot time zone set to `Asia/Riyadh` (UTC+3), was `America/Toronto` (EDT, UTC-4) (2026-10-24, 23:51:58 laptop and robot time) | systemd time zone setting (`/etc/localtime` link), changed with `timedatectl` | The robot clock was correct (synced, 0.4 ms off) but showed Toronto time, 7 hours behind the lab, which made every log and journal time confusing. From this change on, robot time and laptop time are the same; entries before it give robot time in EDT | `timedatectl` shows `Time zone: Asia/Riyadh (+03, +0300)` and `System clock synchronized: yes` | `sudo timedatectl set-timezone America/Toronto` | Applied by the user typing the `sudo` password: `sudo timedatectl set-timezone Asia/Riyadh`. Verified with `timedatectl` right after. ROS 2 time stamps are in UTC and did not change; systemd timers that use local time (for example the Ubuntu update timers, TB-28) now follow Saudi time |
| R21 | Home Wi-Fi profile `TP-LINK_Extender_5GHz` (R16) deleted from the robot, then the robot shut down for the move to the lab (2026-10-25, about 00:20 laptop and robot time, UTC+3) | `/etc/NetworkManager/system-connections/` (the R16 profile file, which held the home Wi-Fi password) | The robot's `ubuntu` password is now published in this repository, so anyone who can log in could read a stored home Wi-Fi password with `sudo`; on campus the robot joins `Students` (R1) by itself and does not need the home profile | On the next boot: `nmcli -t -f NAME connection show` no longer lists `TP-LINK_Extender_5GHz`; still listed: `Students`, `netplan-wlan0-Turtlebot4`, `netplan-eth0`, `netplan-usb0` | Add the home network again with TurtleBot Studio, Wi-Fi tab (needs its password), as in R16 | Applied by the user typing the `sudo` password in one command: `sudo systemd-run --on-active=8 systemctl poweroff && sudo nmcli connection delete TP-LINK_Extender_5GHz`. Output: `Connection 'TP-LINK_Extender_5GHz' (0f24cae0-...) successfully deleted.`; the SSH session then closed and the robot stopped answering on the home network. The power-off itself was not seen remotely: check that the display and lights are off before unplugging. The next power-on at the lab is the first boot on the new kernel installed by the automatic update (TB-28) |

Not changed: the factory access point profile and `/etc/netplan/50-wifis.yaml`, the ROS and TurtleBot configuration, the robot password, and the Create 3 settings (the base was only restarted). Since 2026-10-24 (R19) the base's saved Wi-Fi network is removed; its ROS settings are still unchanged.

On 2026-10-04 no `sudo` was used, no configuration was changed and the clock was not touched. The only physical change was reseating the lidar USB cable (same cable, same port) before the 11:44 boot. Temporary diagnosis files were written to `/tmp` (`undock.log`, `shapes_*.log`, `gapprobe*.py`, `odomprobe.py`, `odomprobe.log`, `scan_*.txt`); `/tmp` is cleared at reboot, so they need no undo.

2026-10-24: two changes, R14 and R16 (above; R15 is a user folder). Runtime actions that day (undock, `/start_motor`, dock) changed no configuration and are listed under [Restarts and service interruptions](#restarts-and-service-interruptions). The robot clock, the global NetworkManager file, the `Turtlebot4` profile and the Create 3 settings were not touched. Temporary files were written to `/tmp` only (the timing recording `/tmp/timing_motion_2026-10-24.jsonl`, copied to the laptop); `/tmp` is cleared at reboot.

On 2026-10-04 at about 15:42 (robot time) and on 2026-10-05 (laptop time) the robot was reached only briefly over SSH, for read-only checks; nothing was changed. No `sudo` was used by the assistant at any point since 2026-10-04.

### Restarts and service interruptions

| When (local time, UTC+3) | Action | Run by | Result |
|---|---|---|---|
| About 19:04 to 19:12 | Wi-Fi switch: robot left its access point for a 3 minute test on Students, returned, then switched permanently | `start.sh` and `controller.sh` | Network moves only, no reboot. Log ends with CONFIRMED |
| About 19:56 | Robot reboot (boot time derived from the robot's journal: the clock fix ran 82 s after boot, at 16:57 UTC) | End of `root-setup.sh` (`sudo ./finish-setup`) | Came back on Students by itself. Clock stepped at about 82 s; base went silent. Lidar missing from this point |
| About 20:12 | Restart of `turtlebot4.service` (ROS only, no reboot) | End of `fix-ros.sh` (`sudo ./fix-ros`) | Base still silent |
| About 20:28 | Create 3 application restart | "Restart Application" (`POST /api/restart-app`) from the robot | Base data returned |
| About 20:31 | `motion_test.sh` (undock, spin, dock) | From a laptop over SSH | Undock and spin succeeded; dock completed after a detached re-send |
| About 20:50 (robot back at about 20:52) | Full power cycle: `sudo poweroff`, base off and on, back on the dock | Original author | Lidar still missing. Clock fix failed at boot; base silent again |

2026-10-04 (robot time, EDT, from the robot's journal):

| When | Action | Run by | Result |
|---|---|---|---|
| Before 11:44 | Lidar USB cable reseated | User (physical) | See the next row |
| About 11:44 | Robot boot | User | Lidar detected (CP210x, `/dev/RPLIDAR`), base talking, clock correct |
| 11:48 | Dock power saver stops the lidar (`turtlebot4_node`: "RPLIDAR stopped") | Automatic | No `/scan` while docked, as designed |
| About 12:09 | Undock (`ros2 action send_goal /undock`, sent detached) | From a laptop over SSH | SUCCEEDED; "RPLIDAR started" at 12:09:54 |
| After 12:09 | `motion_shapes.py` runs and short diagnostic moves | From a laptop over SSH, detached | See [docs/test-results.html](docs/test-results.html) |
| Between the sessions (time not recorded) | Robot off the network for about 1.5 hours | n/a | It was powered off between sessions; the cause of the drop is not confirmed |
| About 15:38 (derived: uptime 4 min at about 15:42) | Robot switched on | User | Answered SSH once at about 15:42 (address `10.87.10.205`, clock correct, lidar on USB), then dropped off the Wi-Fi and did not come back during about 25 minutes of watching. See the [Wi-Fi incident](#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05) |
| _To be completed_ | Further undock and dock actions during the test campaign | Test campaign | _Placeholder_ |

2026-10-05 (laptop time, UTC+3):

| When | Action | Run by | Result |
|---|---|---|---|
| Afternoon | SSH to the robot by address and by key | From a laptop | Worked for about a minute, then the robot disappeared again; afterwards it answered only in short windows (about 10 to 40 s). The laptop's Wi-Fi stayed fine. No restart of the robot is recorded |

2026-10-24 (seconds since the start of the timing recording; the robot clock read 15:05:35 at 0 s and was about two years wrong, so only the offsets are reliable). No configuration change in any of these actions:

| When | Action | Run by | Result |
|---|---|---|---|
| About 00:22 laptop time | R14: `sudo nmcli connection modify Students 802-11-wireless.powersave 2` | User (typed the `sudo` password) | Profile value `default` to `disable`. Not brought up |
| 32.5 s | Undock (`/undock` action goal) | Main session, user next to the robot | SUCCEEDED at about 41 s. All base topics stalled for 1.39 s at 33.76 s and 0.57 s at 35.19 s (see the [finding](#update-2026-10-24-measurements-with-the-timing-recorder)) |
| About 93 s | First `motion_shapes.py` attempt | Main session | Setup failed: no `/scan`. The lidar motor had not restarted after undocking (the `rplidar` log has "Stop" at 14:37:45 robot time when docked and no "Start" after the undock) |
| After 93 s | `ros2 service call /start_motor std_srvs/srv/Empty` by hand | Main session | `/scan` at 7.6 Hz. Runtime action only |
| 173.4 s to about 180.5 s | `motion_shapes.py back_and_forth --side 0.3`: forward at 0.1 m/s from 176.50 s | Main session, user next to the robot | At 178.51 s all base topics stalled; the program held still and aborted ("odometry is stale (none for 2.0 s)") at about 180.5 s. The robot moved a few centimetres |
| About 00:33 laptop time | Dock (`/dock` action) | Main session | SUCCEEDED |

TurtleBot Studio test, 2026-10-24 (laptop time about 00:45 to 01:15, UTC+3; robot docked, over the Ethernet cable). No configuration change in any of these actions:

| When | Action | Run by | Result |
|---|---|---|---|
| During the test | E-stop on and off three times while docked: once with the command line, once through the Studio API, once with the Studio button | Main session, user present | Wheels disabled then enabled each time (read from `/wheel_status` `wheels_enabled`); `~/STOP` created and removed. No motion |
| During the test | Test folder `~/robot_code/studio_test` created by a sync, a test script run and stopped, then folder and test logs removed | Studio | The empty `~/robot_code/logs/` remains (R15) |
| During the Studio 1.1 test (about 01:30 to 03:00 laptop time) | Test folder `~/robot_code/studio_test` written (two templates), `my_first_program.py` run, `spin_in_place.py` run with `--dry-run` only, then folder and files removed | Studio, user present | No motion (nothing sent to `/cmd_vel`). No configuration change |
| During the test | Studio's robot-side helper `robot_bridge.py` streamed over ssh and run for the session | Studio | Nothing installed on the robot; it exits when Studio disconnects. It used about 23 % of one core (97 % before the executor was changed) |

Home Wi-Fi and supervised motion through Studio, 2026-10-24 (laptop time from about 04:26, UTC+3; the robot clock was correct from about 04:50, after it reached the internet):

| When | Action | Run by | Result |
|---|---|---|---|
| About 04:34 | First **Add to the robot** attempt | Studio, user | The terminal window closed at once (Studio bug), nothing ran on the robot |
| About 04:40 | Second attempt | Studio, user | The script printed "bad arguments" before asking for anything (Studio bug: wrong argument order). Nothing changed |
| About 04:49 | R16: network saved and brought up (`nmcli connection up`) | User (typed the Wi-Fi and `sudo` passwords) | Robot left its `Turtlebot4` hotspot and joined `TP-LINK_Extender_5GHz` (192.168.100.31). No reboot, no ROS restart |
| About 04:52 | Ethernet cable unplugged; Studio connected over Wi-Fi | User, main session | Connected through `turtlebot4.local` (233 ms to answer). Status, battery and odometry live |
| From about 04:50 | `unattended-upgrade --download-only` started by Ubuntu's `apt-daily` timer | Automatic (Ubuntu) | One core at 100 % (nice 19), Pi temperature 67 °C. Not stopped or changed |

Update 2026-10-24, evening: supervised motion through Studio over Wi-Fi, with the user next to the robot and the motion confirmations ticked. Times are laptop time (UTC+3); robot time (EDT) is 7 hours earlier and is shown in brackets. The timing recorder ([tools/timing/record_timing.py](tools/timing/record_timing.py) with `--light`) was copied to `/tmp` on the robot and run detached. Recording 1 started 05:00:27 (robot 22:00:27) and ran 607 s; recording 2 started 05:11:11 (robot 22:11:11) and ran 1500 s, using 7.4 % of one core. Files: [tests/logs/2026-10-24_timing_wifi_before_base_restart.jsonl.gz](tests/logs/2026-10-24_timing_wifi_before_base_restart.jsonl.gz), [tests/logs/2026-10-24_timing_wifi_after_base_restart.jsonl.gz](tests/logs/2026-10-24_timing_wifi_after_base_restart.jsonl.gz), [tests/logs/2026-10-24_studio_motion_runs.log](tests/logs/2026-10-24_studio_motion_runs.log).

| When | Action | Run by | Result |
|---|---|---|---|
| 05:00 (robot 22:00:33) | Recording 1 running, robot docked and idle | Main session | 6 s after the recorder started: `/odom` stall of 7.51 s, `/dock_status` 4.7 s, ping to the base up to 41 ms. The longest idle stall seen so far (earlier maximum 1.75 s) |
| 05:03 (robot 22:03) | Undock through the Studio Dashboard | Studio, user | "undock: succeeded (status 4)". The lidar was running after the undock (8 Hz; nearest value ahead changed from 0.77 m to 1.93 m), so the lidar-motor issue (TB-24) did not reproduce this time. The lidar motor may not have stopped while docked (Studio showed 8 Hz on the dock) |
| 05:03:39 (robot 22:03:39) | `my_spin_in_place.py --turns 1 --yes`, from the Code tab (**Save and Run**) | Studio, user | `/cmd_vel` started 194.6 s into the recording. `/odom` gaps of 0.79 s, 1.07 s, then 7.81 s: the program aborted at 22:03:50 robot time on "odometry is stale (none for 2.0 s)". The robot stopped, as designed |
| 05:06:42 (robot 22:06:42) | Create 3 application restart (`POST /api/restart-app` on the base) | Main session, user approved | The HTTP reply timed out but the base restarted. `/odom` was silent for 163 s and came back at about 22:09:30 robot time. The base clock was still 2024 afterwards: an application restart does not re-synchronise the base clock |
| 05:12:35 (robot 22:12:35) | Spin again (`my_spin_in_place.py --turns 1 --yes`) | Studio, user | Done: "turned 359 degrees in total (odometry)", 14 s. Gaps: 0.33 s at program start (delivery delayed) and 0.68 s at motion start. No abort |
| About 05:16:50 | Robot moved by hand to open floor (lidar saw the user's bed 0.34 m ahead) | User | An idle `/odom` gap of 0.67 s, probably the lift |
| 05:17:47 (robot 22:17:47) | `my_drive_circle.py --radius 0.3 --yes` | Studio, user | Done in about 22 s. The program printed "ended 17.3 cm from the start (odometry)". **This closure figure is not valid:** the robot drove over the dock edge and the user moved it during the lap. Timing only: a 0.30 s delivery delay at the start and no stall during the lap |
| 05:19 to 05:20 (robot 22:19:51 to 22:20:02) | Robot carried to 30 to 50 cm in front of the dock, then **Dock** through Studio | User, Studio | A 1.07 s idle gap while handling. "dock: succeeded (status 4)" |
| 05:20:50 (robot 22:20:50) | Base clock re-sync: `POST /api/restart-ntpd` on the base | Main session, user approved | The base clock stepped to 2026 within 15 s. `/odom` stamps matched the Pi (difference 0 s) and data kept flowing |
| 05:21:17 (robot 22:21:17) | Create 3 application restart again | Main session, user approved | `/odom` and `/dock_status` silent for 373 s (back at about 22:27:30 robot time); the base web page timed out for part of that. Then normal: clocks within 1 s, charging at 0.41 A |
| 05:35:06 (robot 22:35:06) | Docked and idle, base and Pi clocks in agreement | Main session | `/odom` stall of 10.97 s (plus 0.76 s just before), `/dock_status` 9.9 s, Pi load average 9.06, CPU 100 %, temperature 72.5 °C, ping to the base up to 36 ms. At that time the assistant was running several `ros2 topic echo` and `ros2 topic hz` commands on the robot (each is a new ROS 2 participant) and the Ubuntu update job was still running |
| Afterwards | Cleanup | Main session | The test programs, their `.bak` copies, the run logs and the recorder files in `/tmp` were removed from the robot. `~/robot_code/logs` stays (R15). An older 2024 `drive_test` log was left in place |

Other runtime facts of the evening: at 05:35 laptop time the Ubuntu update job `unattended-upgrade --download-only` was still running after 45 minutes (started 21:50 robot time, one core at 100 %, nice 19); Pi CPU 45 to 50 % and temperature 65 to 72 °C docked. It was not stopped (decision: ROADMAP TB-28). At 100 % charge Studio showed "On battery (-0.69 A)": the base stops charging when full and the Pi then draws from the battery; later the battery was at 91 % and charging at 0.41 A. This is normal, not a fault. Motion starts that evening: undock, spin, spin, circle and dock, 5 in all (TB-25 asks for at least 10).

**Base runtime actions (how the Create 3 clock was re-synchronised on 2026-10-24).** The base clock does not follow the Pi. After the Pi clock changed: (1) `POST /api/restart-ntpd` on the base, which stepped the base clock to the right time within about 15 s with `/odom` still flowing; (2) then `POST /api/restart-app` on the base, after which `/odom` and `/dock_status` were silent for 163 s and 373 s in the two restarts (expect up to about 6 minutes). Both calls interrupt the base and were run with the user present and approving, and the second one with the robot docked. Whether step 2 is needed once step 1 has made the clocks agree was not tested. The HTTP reply of `restart-app` can time out even though the restart happens. Both calls were sent from the Pi in an SSH session (no `sudo`): `curl -X POST http://192.168.186.2/api/restart-ntpd` and `curl -X POST http://192.168.186.2/api/restart-app`; the base web page has the same two buttons. Not yet tested on another day or from a script; treat as [to verify] before relying on it.

### Removing the clock fix by hand

Use this only if `~/undo-clock` is missing. It does the same as `undo-clock.sh`:

```bash
sudo systemctl disable --now tb4-https-time.timer
sudo rm -f /etc/systemd/system/tb4-https-time.timer /etc/systemd/system/tb4-https-time.service /usr/local/sbin/tb4-https-time
sudo rm -f /etc/systemd/system/turtlebot4.service.d/10-wait-for-clock.conf
sudo rmdir /etc/systemd/system/turtlebot4.service.d   # fails harmlessly if other files are in it
sudo systemctl daemon-reload
sudo systemctl reset-failed tb4-https-time.service
sudo systemctl restart turtlebot4
```

Then restart the Create 3 application and check the base, as in the [resolution plan](#resolution-plan).

### On the original author's workstation (for the record only)

These changes are on one person's Windows laptop, not on lab equipment. They are listed so the setup can be reproduced or cleaned up. Other users need their own key and settings; see [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md).

| ID | Change | Location | Purpose | Undo |
|---|---|---|---|---|
| W1 | SSH key pair for the robot | `~/.ssh/turtlebot4_ed25519` and `turtlebot4_ed25519.pub` | Key login; the public half is R2 | Delete both files and remove R2 from the robot |
| W2 | SSH host aliases | `~/.ssh/config`: `turtlebot4` (HostName `turtlebot4.local`) and `turtlebot4-ap` (HostName `10.42.0.1`), user `ubuntu`, key W1. Both blocks also set `StrictHostKeyChecking accept-new` and `ConnectTimeout 5` | Short names for `ssh`, `scp` and VS Code | Delete the two `Host` blocks |
| W3 | VS Code Remote-SSH extension and user settings `remote.SSH.remotePlatform` (`turtlebot4`: linux), `remote.SSH.localServerDownload` = `always`, `remote.SSH.connectTimeout` = `30` | VS Code extensions and user `settings.json` | Edit and run code on the robot | Uninstall the extension and remove the three settings |
| W4 | Windows Wi-Fi profile `Turtlebot4` | USB adapter "Wi-Fi 2". Imported from an export of the built-in card's saved profile (made when the laptop first joined `Turtlebot4`), which also remains | Reach the robot's access point while the built-in card stays on Students | `netsh wlan delete profile name="Turtlebot4" interface="Wi-Fi 2"`; leave out `interface=...` to delete it from every adapter |
| W5 | Second USB Wi-Fi adapter (Realtek 8811CU) | USB port | Hardware for W4. No routing changes were needed: Windows prefers the built-in card (interface metric 45 against 55) | Unplug |
| W6 | Desktop shortcuts "TurtleBot - VS Code" and "TurtleBot - Terminal" | Desktop | One double-click to reach the robot | Delete them |
| W7 | Desktop shortcut "TurtleBot - one-time setup.cmd" | Desktop | Meant to launch the one-time setup; never used (the setup was run from the Terminal shortcut) | Delete it |

Temporary profile export files (`%TEMP%\tb4w`) were deleted after the import.

## Admin scripts

Copies of every script are in [`setup/`](setup/). Admin steps need a person who knows the `ubuntu` password to type it: `sudo` asks for it, and NetworkManager asks for it on Wi-Fi changes over SSH. The password is not in this repository. Run the shortcut commands from the home folder (`cd ~` first).

| Script | On the robot | How it is run | sudo | What it does | Status |
|---|---|---|---|---|---|
| `start.sh` | `~/wifi-switch/start.sh` | `sudo bash /home/ubuntu/wifi-switch/start.sh` | Yes | Prompts for the Students password (hidden), writes the profile through `write_keyfile.py` (autoconnect off, priority 10), loads it, then starts `controller.sh` as the transient unit `tb4-wifi-switch` | Run once. The switch completed with a test phase and automatic undo as the safety net. Rerunning deletes and recreates the Students profile |
| `controller.sh` | Copied to `/run/tb4-wifi-controller.sh` | By `start.sh` only | Root (systemd) | Test phase: joins Students, logs address, gateway, DNS and a web check, holds 3 minutes, returns to the access point, waits up to 30 minutes for a `GO` file. Permanent phase: joins Students, turns autoconnect on (priority 10), waits up to 10 minutes for a `KEEP` file, otherwise turns autoconnect off and returns to the access point. Log: `~/wifi-switch/log.txt` | Ran once; ended CONFIRMED |
| `write_keyfile.py` | `~/wifi-switch/` | By `start.sh` only; the password goes through stdin, never the command line | Root | Writes `Students.nmconnection` with mode 600 and keyfile escaping | Used once. Self-tested with a fake password containing spaces, quotes, `#` and a backslash |
| `root-setup.sh` | `~/finish-setup` | `sudo ./finish-setup` | Yes | Installs, enables and runs the clock fix (R7); limits avahi to `wlan0` with a backup (R6); reboots | Run once (reboot at about 19:56). Do not run again: it reinstalls the clock fix and reboots |
| `fix-ros.sh` | `~/fix-ros` | `sudo ./fix-ros` | Yes | Reinstalls the clock fix with a 90 s retry, adds the drop-in (R8), runs the clock fix, restarts `turtlebot4.service` (no reboot) | Run once. Do not run again: it reinstalls the clock fix |
| `undo-clock.sh` | `~/undo-clock` | `sudo ./undo-clock` | Yes | Disables and deletes R7 and R8, removes the empty drop-in folder, reloads systemd, restarts `turtlebot4.service` (no reboot; also picks up a re-plugged lidar) | Prepared; not confirmed run as of 2026-10-03. Not run as of 2026-10-04 (the clock fix was still installed); no change by 2026-10-10. Follow it with a Create 3 application restart |
| `tb4-https-time` | `/usr/local/sbin/` | By its service | Root | Reads the `Date` header from google.com, github.com or packages.ros.org with `curl -k` (certificates are not checked; only the time is used) and steps the clock if it is more than 30 s off. Retries for 90 s. The repo copy is the `fix-ros.sh` version; the first version installed by `root-setup.sh` had no retry and was not kept | Installed; removal pending (R7) |
| `tb4-https-time.service`, `tb4-https-time.timer` | `/etc/systemd/system/` | systemd | n/a | Oneshot after `network-online.target`, 120 s start timeout. Timer: 60 s after boot, then 15 minutes after each run | Enabled; removal pending (R7) |
| `10-wait-for-clock.conf` | `/etc/systemd/system/turtlebot4.service.d/` | systemd | n/a | `Wants=` and `After=tb4-https-time.service` for the ROS bringup. Because it is `Wants=`, ROS still starts when the fix fails, but only after it gives up (about 2 minutes) | Installed; removal pending (R8) |

During the Wi-Fi switch the phases were released by creating the marker files: `GO` after the test phase, `KEEP` once the laptop reached the robot by name on Students.

```bash
touch ~/wifi-switch/GO     # start the permanent phase (within 30 minutes of the test)
touch ~/wifi-switch/KEEP   # confirm the switch (within 10 minutes), otherwise it is undone
```

The example programs in [`examples/`](examples/) are user code, described in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) and [examples/README.md](examples/README.md). `drive_test.py` and `motion_test.sh` move the robot. Test record for `motion_test.sh` on 2026-10-03: undock and the 360 degree spin succeeded, the forward drive was skipped (no lidar data), and the dock succeeded after a detached re-send because the SSH session dropped.

## Incident: Create 3 base stopped responding after the clock fix

| | |
|---|---|
| Date | 2026-10-03 |
| Status at handover | Open. Cause identified; fix prepared, not confirmed applied |
| Status on 2026-10-04 | Not occurring on the 11:44 boot: clock correct, base data arriving, clocks within seconds. Fix (R7, R8) still installed, `undo-clock` not run. Keep open until the keep-or-remove decision ([ROADMAP.md, TB-17](ROADMAP.md#tb-17-decide-whether-to-keep-or-remove-the-clock-fix)) |
| Status on 2026-10-10 | Unchanged: decision TB-17 still open, fix still installed as last seen on 2026-10-04. The boot at about 15:38 on 2026-10-04 (robot time) also had a correct clock at 15:42; whether the base talked on that boot was not recorded |
| Changes involved | R7 (clock fix), R8 (drop-in) |

### Summary

A clock fix added on 2026-10-03 stepped the Raspberry Pi's clock forward by about two years while ROS was running. The Create 3 base then stopped sending data to ROS. Restarting the base application restored it. After a later full power cycle the fix could not reach any HTTPS server, the Pi booted with an October 2024 date while the base had kept 2026, and the base went silent again. The decision is to remove the clock fix.

### Impact

- No `/battery_state` or `/dock_status`; undock and dock actions time out. Programs that rely on the base fail.
- Duration: first occurrence from about 82 s after the 19:56 reboot until the Create 3 application restart; second occurrence from the power cycle until handover (unresolved).
- The lidar fault found in the same period is tracked separately under [Known issues](#known-issues). No link to the clock fix has been established.

### Timeline (2026-10-03, local time, UTC+3)

| Time | Event |
|---|---|
| Earlier | Robot moved to Students. Campus found to block NTP. Dry run of the time fetch: web said 2026-10-03, Pi said 2024-10-28 |
| About 19:56 | `root-setup.sh` (`sudo ./finish-setup`) installs and runs the clock fix, limits avahi, and reboots the robot |
| Boot + about 26 s | `turtlebot4.service` (ROS) starts with the Pi clock back in 2024 |
| Boot + about 82 s | The timer runs the clock fix, which steps the clock forward about 2 years while ROS runs. From then on the base sends no data |
| About 20:12 | `fix-ros.sh`: clock fix gets a 90 s retry, the drop-in makes ROS start after it, ROS restarted. Base still silent |
| About 20:28 | Base web server on `192.168.186.2` port 80 still answers. Create 3 application restarted (`POST /api/restart-app`, robot chimes). `/dock_status` returns |
| About 20:31 | `motion_test.sh`: undock, spin and dock succeed. Lidar found missing on USB |
| About 20:50 | Full power cycle to recover the lidar. Lidar still missing |
| Boot after power cycle | Clock fix fails ("Could not read the time from any HTTPS server" after 116 s of retries). ROS starts with the Pi in October 2024 while the base has 2026. Base silent again |
| Handover | Decision to remove the clock fix. `undo-clock.sh` prepared; not confirmed run |

### Root cause

The Create 3 base communicates with ROS only when the Pi and base clocks agree. This is an observed pattern from two occurrences, not confirmed against iRobot documentation. The base takes its time from the Pi when its application starts. A large step on the Pi while both are running (first occurrence), or a Pi that boots with a different date from the base (second occurrence), breaks the link until the base application restarts and re-syncs.

Contributing factors:
- Campus blocks NTP and the Pi has no battery-backed clock, so it boots with a stale date.
- The clock fix was an optional addition, not needed for the Wi-Fi task, and it was applied instead of proposed.
- The fix steps the clock in one jump, and its 15 minute timer can do so again while ROS runs.
- The drop-in uses `Wants=`, so when the fix fails ROS still starts with the stale date.
- Why HTTPS was unreachable for the first 2 minutes after the power cycle was not determined.

### Resolution plan

To be run by an admin in a robot terminal. Reseat the lidar USB cable first if possible, so the ROS restart also picks it up.

```bash
cd ~
sudo ./undo-clock
curl -X POST http://192.168.186.2/api/restart-app
# wait for the chime, then:
timeout 60 ros2 topic echo --once /dock_status
```

Done when `/dock_status` prints a message. Then update R7 and R8 in this file to "Removed" with the date, and run the [verification checklist](#verification-checklist).

Accepted cost: the Pi date stays wrong, so `git clone`, `pip` and `apt` over HTTPS can fail with certificate or date errors. Copy code from a laptop with VS Code or `scp` instead. Any new clock approach must be proposed first; see [ROADMAP.md](ROADMAP.md).

### Lessons

- Never step the clock by a large amount while ROS is running.
- Keep the Pi and base clocks consistent. After any clock change on the Pi, restart the Create 3 application.
- When the base goes silent, restart the Create 3 application first. Restarting `turtlebot4.service` alone did not help.
- Nice-to-have changes on shared hardware should be proposed, not applied.

### Update 2026-10-24: clock stepped by the internet, and base re-sync

Times are laptop time (UTC+3) unless marked robot time (EDT, 7 hours earlier).

Measured:

- Before the evening the Pi clock read 28 October 2024. When R16 gave the robot internet, `chronyd` stepped the Pi clock by +62,648,406.93 s (about 1.99 years) at 21:49:23 robot time, while ROS was running. The Pi clock was correct from 04:49 laptop time (21:49 robot time). `tb4-https-time` at 21:59 robot time said "Clock already correct".
- The Create 3 base kept its 2024 clock: the `/odom` header stamps were 62,648,407 s behind the Pi.
- Base re-sync: `restart-ntpd` on the base at 22:20:50 robot time stepped its clock to 2026 within 15 s with `/odom` flowing; a base application restart at 22:21:17 robot time followed (373 s of silence). Afterwards the clocks agreed within 1 s. The procedure is in the [runtime table](#restarts-and-service-interruptions) under "Base runtime actions".

Why the clock is not fixed for good (answer given on 2026-10-24): the Pi 4 has no battery-backed real-time clock; the campus network blocks NTP; the 2026-10-03 HTTPS clock fix stepped the clock while ROS ran and silenced the base (this incident); and the keep-or-remove decision ([TB-17](ROADMAP.md#tb-17-decide-whether-to-keep-or-remove-the-clock-fix)) is still open. No permanent fix has been approved. Proposals for TB-17 are in the roadmap and have not been applied.

## Incident: lidar not detected (2026-10-03), resolved 2026-10-04

| | |
|---|---|
| Date | Found 2026-10-03 at about 20:31 (UTC+3); resolved 2026-10-04 before the 11:44 boot (robot time, EDT) |
| Status | **Resolved** 2026-10-04 |
| Changes involved | None in software. Physical: lidar USB cable reseated (same cable, same port) |
| Illustrated version | [docs/lidar-diagnosis.html](docs/lidar-diagnosis.html); Markdown version [docs/LIDAR-FINDINGS.md](docs/LIDAR-FINDINGS.md) |

### Summary

After the reboot at about 19:56 on 2026-10-03 the lidar still spun, but the Raspberry Pi did not see it on USB: no CP210x device in `lsusb`, no `/dev/RPLIDAR`, and the driver could not open the port. A full power cycle did not help. On 2026-10-04 the user reseated the lidar's USB cable and booted the robot at about 11:44 (robot time). The lidar was detected, the driver started, and off the dock `/scan` published at 7.75 Hz with plausible ranges. Root cause: a loose USB connection. Fixed physically; no software change.

### Evidence on 2026-10-04 (read-only checks, robot time; the commands are the way to repeat each check)

| Layer | How to check | Result on 2026-10-04 |
|---|---|---|
| USB | `lsusb` | `10c4:ea60` Silicon Labs CP210x UART Bridge present |
| Device | `ls -la /dev/RPLIDAR` | Link to `ttyUSB0`; `ttyUSB0` is `crw-rw-rw-`, owner `root`, group `dialout` |
| Driver | `journalctl -u turtlebot4 -b` | `rplidar_composition` started: serial number `6DE9ED95C4E493C8A5E69EF0FC394B6C`, firmware 1.29, hardware revision 7, health status 0, scan mode Sensitivity, maximum distance 12 m, sample rate 7.9K points/s |
| Power saver | Same journal | 11:48 `turtlebot4_node`: "RPLIDAR stopped" (docked). 12:09:54 "RPLIDAR started" (after undock). Expected behaviour, not a fault |
| ROS graph | `ros2 node list`, `ros2 topic info -v /scan` | Nodes include `/rplidar_composition`, `/turtlebot4_base_node`, `/oakd`, `/turtlebot4_diagnostics`. `/scan`: 1 publisher (reliable), subscriber `turtlebot4_diagnostics` (best effort) |
| Data (off the dock) | `ros2 topic hz /scan` | 7.75 Hz; period 0.119 to 0.139 s; standard deviation 0.0064 s |
| Data | `ros2 topic echo --once --full-length /scan` | Frame `rplidar_link`; `angle_min` -3.124 rad, `angle_max` 3.1416 rad, increment 0.008715 rad (720 beams); `range_min` 0.15 m, `range_max` 12.0 m; 519 of 720 beams valid (72 %); ranges 0.261 to 6.800 m, median 1.442 m |
| Robot frame | `ros2 run tf2_ros tf2_echo base_link rplidar_link` | Translation (-0.040, 0, 0.193) m, yaw +90 degrees. Straight ahead of the robot is laser angle -90 degrees |
| Program | `python3 clearance_check.py 0.6` | "lidar frame offset 90 deg, beams in front 78, nearest in front 1.73 m", exit code 0 |

`dmesg` needs `sudo` on this robot and was not run.

### Root cause

A loose USB connection between the lidar and the Pi. The lidar's motor is powered separately from its USB data link, so it kept spinning while the Pi saw no USB device. After the user reseated the cable, the CP210x bridge enumerated at boot and the driver bound to it without any software change. Not related to the clock fix.

### Resolution and verification

- Resolution: cable reseated by the user before the 11:44 boot on 2026-10-04 (same port, same cable).
- Verified on the boot after the reseat: USB device, device link, driver start, `/scan` at about 7.75 Hz off the dock, `clearance_check.py` exit 0.
- Not yet verified: detection after a second, separate reboot or power cycle. Record it the next time the robot restarts.
- Update 2026-10-10: the robot was powered off between sessions on 2026-10-04 and switched on again at about 15:38 (robot time). A single SSH check at about 15:42 found the lidar on USB. No `/scan` result was recorded; the robot dropped off the Wi-Fi straight after ([Wi-Fi incident](#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05)). Keep recording detection after later restarts.

### Lessons

- When a USB sensor spins but is not in `lsusb`, check the cable first: power and data are separate.
- "No `/scan` on the dock" is the power saver, not a fault. Undock before judging the lidar.
- `ros2 topic echo` cuts arrays at 128 entries; add `--full-length` to see all 720 ranges.
- `ros2 topic hz` in Jazzy has no `--qos-reliability` option; it works on `/scan` without one.
- A cable strain relief and a label would make this less likely and quicker to check ([ROADMAP.md, TB-18](ROADMAP.md#tb-18-lidar-cable-strain-relief-and-label)).

## Finding: /odom pauses at motion start

| | |
|---|---|
| Date | 2026-10-04 (robot time) |
| Status | Worked around in `motion_shapes.py`. **Updated 2026-10-24:** cause located in the Create 3 base, triggered when it starts to move; why it stalls is still open ([ROADMAP.md, TB-15](ROADMAP.md#tb-15-characterise-the-odom-pauses-at-motion-start), [TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving)) |
| Affects | Any program that stops when `/odom` is late, in particular `motion_shapes.py` |
| Illustrated version | [docs/motion-program-design.html](docs/motion-program-design.html#odom-pause) |

### Summary

The first real run of `motion_shapes.py square` aborted about 1 s after starting with "odometry is stale (none for 0.5 s)". Tests without motion found no gap. A 10 cm instrumented move showed that the base itself stops publishing `/odom` for about 0.4 s just after the wheels start: the gap appears both in the arrival times on the Pi and in the message header stamps, so it is not a Pi-side delivery delay.

### Measurements (2026-10-04)

| Test | Result |
|---|---|
| Program loop alone, robot still | Worst `/odom` age 0.104 s |
| Publishing zero velocity on `/cmd_vel`, robot still | Worst `/odom` age 0.100 s |
| `ros2 topic hz /odom`, robot still | 19.98 Hz, largest gap 0.064 s |
| Instrumented 10 cm move | Arrival gap 0.413 s, header-stamp gap 0.419 s, 0.12 s after motion started |
| Triangle run after fix 1 | Aborted at a segment change with a 1.0 s gap; Pi load average 3.4 at the time |
| Root-cause characterisation | _Placeholder: numbers from the test campaign (gap length and frequency, when gaps occur, load dependence)_ |

### Update 2026-10-24: measurements with the timing recorder

Recorder: [tools/timing/record_timing.py](tools/timing/record_timing.py), run on the robot and piped over SSH for 300 s; 33,324 records, saved as `/tmp/timing_motion_2026-10-24.jsonl` on the robot and copied to the laptop. The recorder itself used 44 % of one core (high; being reduced). The robot was on Ethernet plus its own hotspot, with a person next to it. Times are seconds since the start of the recording.

| Event | Time | What was recorded |
|---|---|---|
| Undock goal sent | 32.5 s | Undock SUCCEEDED at about 41 s |
| First stall (undock motion start) | 33.76 s | `/odom`, `/tf`, `/imu` and `/wheel_status` all stopped for **1.39 s**; their header stamps also stopped. A second stall of 0.57 s at 35.19 s |
| `motion_shapes.py` start-up | 173.4 s | Pi CPU 100 % (load1 4.43) for the program start; only a 0.29 s `/imu` gap |
| Forward drive starts | 176.50 s | `/cmd_vel` 0.1 m/s |
| Second stall (drive) | 178.51 s, 2.0 s after the start | All base topics stalled; **`/odom` receive gap 3.16 s**. Then gaps of 0.57 s, 1.50 s, 0.49 s and 0.91 s until about 185 s |
| Program | from 178.85 s | Held still (zero `/cmd_vel`); aborted at about 180.5 s on "odometry is stale (none for 2.0 s)". The robot moved a few centimetres |
| Idle baseline (docked, 180 s) | n/a | `/odom` 19.9 Hz, one 1.31 s gap at its own start-up, otherwise clean. Pi to base clock offset: median 31 ms |

During the stalls: `ping` to the base over `usb0` lost 0 % but the round-trip time rose to 21 to 27 ms (median 0.5 ms); `eth0`, `usb0` and `wlan0` showed 0 errors and 0 drops; no link changed; Pi CPU was 40 to 61 % in total (busiest core up to 71 %), temperature up to 59 C, `vcgencmd get_throttled` 0x0.

**Conclusion, evidence (measured on 2026-10-24):**

- The pauses start in the Create 3 base: header stamps stop too, all base topics stall together, and the base answers `ping` more slowly during the stall.
- They are triggered by the base starting to move: both stalls came at a motion start (undock, forward drive).
- They are not the Wi-Fi (the robot was on Ethernet and its own hotspot) and not an overloaded Pi (CPU at most 61 % in total at the stall; throttling none).

**Inferred, not proven:** the base is overloaded inside, or blocked, when the motors start (firmware `I.0.0.FastDDS`, ROS Iron). Not yet tested: whether fewer subscribers or republished topics (the recorder subscribed to many) change the stalls; the Create 3 known issues and release notes; the `create3_republisher` settings. These are TB-25. The repeat count is small (2 stalls in one run), so no frequency is claimed.

### Update 2026-10-24 (evening, over Wi-Fi)

The robot was on the home Wi-Fi (R16), docked or driven under supervision through Studio. Details and times are in the [runtime table](#restarts-and-service-interruptions); recordings are in `tests/logs/` (`2026-10-24_timing_wifi_before_base_restart.jsonl.gz`, `2026-10-24_timing_wifi_after_base_restart.jsonl.gz`, `2026-10-24_studio_motion_runs.log`).

Measured:

- Idle, docked: `/odom` stall of 7.51 s at 22:00:33 robot time (6 s after the recorder started) and 10.97 s at 22:35:06 (clocks in agreement), `/dock_status` stalls of 4.7 s and 9.9 s. Earlier idle maximum: 1.75 s.
- In motion: a 7.81 s gap aborted the first spin; after the base application restart the second spin (gaps 0.33 s and 0.68 s) and the circle (0.30 s) ran without a stall over 0.68 s.
- The ping round-trip time to the base rose in every long stall (up to 41 ms and 36 ms), so the stall is on the base side.
- The Wi-Fi was not involved: no errors or drops, signal steady at about -60 dBm.
- The restart of the base application is **not a fix**: an 11 s idle stall came after it, with the clocks already in agreement.
- Undock and dock through Studio worked; the lidar was running after the undock (TB-24 did not reproduce).

**Hypothesis, not proven:** long stalls follow new ROS 2 participants joining the graph (DDS discovery load on the Create 3, Fast DDS, firmware `I.0.0.FastDDS`). Three observations fit it: the 7.5 s stall came 6 s after the recorder started; the abort came seconds after the spin program started; the 11 s stall came while several `ros2 topic echo` and `ros2 topic hz` commands were starting (run by the assistant, alongside the update job). If so, the earlier idea that stalls are triggered by the motion start may really be triggered by the program start just before the motion. Pi CPU load (update job, command-line tools) may contribute. Next test, cheap, docked, no motion: record with `--light` for 10 minutes; every 60 s start and stop a minimal `rclpy` node (or run `ros2 topic list`), log the times and see whether stalls follow the joins; then read the Create 3 discovery-server and ROS domain settings and the republisher settings (read-only). See [TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving).

The 5 motion starts of the evening (undock, spin, spin, circle, dock) are too few to give a frequency.

### Update 2026-10-24 (afternoon; TB-25 DDS-join test, docked, no motion)

Test of the hypothesis above. Run 14:23 to 14:35 laptop time (UTC+3; robot clock 07:23 EDT, correct). The Pi had rebooted about 14:10 (uptime 12 min at the start); not caused by this test. The robot was docked on the home Wi-Fi (`192.168.100.31`), Ibrahim present, no motion. `record_timing.py --light --duration 720` ran detached from `/tmp` (CPU cost 8.8 % of one core). After a 120 s quiet baseline, a minimal `rclpy` node (create node, spin 5 s, exit) was started every 60 s, 8 times; start times were logged with the monotonic clock. No `ros2` CLI command ran on the robot during the recording. Robot configuration was not changed. Files: `tests/logs/2026-10-24_timing_tb25_dds_joins.jsonl.gz` and `tests/logs/2026-10-24_timing_tb25_dds_joins_joins.log`. The recording started at monotonic 752.11 s; join starts were at 119.7, 179.8, 239.8, 299.8, 359.8, 419.8, 479.8, 539.8 s (recording time).

Result (17,155 records, `/odom` 14,141 messages at 19.8 Hz):

| Period | `/odom` and `/dock_status` gaps |
|---|---|
| Quiet baseline, 0 to 119.7 s (no joins; includes the recorder's own start) | **none** |
| Join 1 (119.7 s), 3 (239.8 s), 6 (419.8 s), 7 (479.8 s), 8 (539.8 s) | **none** |
| Join 2 (179.8 s; node exited at 186.9 s) | cluster of four starting 186.9 s, the moment the node left: `/odom` 0.38 s, `/dock_status` **6.50 s**, `/odom` **2.46 s**, `/odom` 1.95 s |
| Join 4 (299.8 s) | `/odom` 0.50 s at 303.5 s (3.7 s after start) |
| Join 5 (359.8 s) | `/odom` 0.41 s at 360.4 s (0.6 s after start; core 1 at 100 %, `create3_republisher` 52 %) and `/odom` 0.31 s at 361.6 s |
| Outside every join (456.5 s) | `/odom` 0.27 s (core 1 at 100 %) |

Reading:

- 7 of the 8 gaps (all of the long ones) started within 12 s of a join; 3 of the 8 joins were followed by a stall; 5 of 8 joins and the whole 120 s baseline were clean. The one unrelated gap was 0.27 s.
- **The hypothesis is supported in part, not proven.** A new participant can trigger base stalls, but not every time (3 of 8), and the worst one (6.5 s `/dock_status`, 2.5 s `/odom`) came when the node *left*, not when it joined. The cause is DDS participant churn (discovery or removal), not the wheels: no motion was involved.
- Ping to the base stayed at its 0.5 ms median except for single spikes (27 ms and 15 ms) inside the long cluster. Wi-Fi had no errors or drops, signal -67 to -72 dBm. The stalls are `publisher stopped` (the base produced nothing).
- The earlier 7.5 s to 11 s stalls were **not reproduced** by this light-weight probe. They happened with heavier events (several `ros2` CLI commands, a spin program). Likely the stall length grows with how many participants or endpoints change at once. Not tested.
- Limits: one 12 minute run, 8 joins, one robot, home Wi-Fi. A repeat on campus and a run with `ros2` CLI commands as the joiners would show whether CLI joins are worse.

Next test (read-only first): repeat with 8 `ros2 topic list` joins (CLI) and with 8 joins of a node that also subscribes to `/odom`; compare with this table. Possible mitigations to propose, not applied: start programs with a short wait before the first `/odom` check; keep one long-running node instead of starting and stopping many.

### Update 2026-10-24 (evening; TB-25 follow-up joins, docked, no motion)

Follow-up to the DDS-join test above. All times are laptop time (UTC+3) with robot time (EDT, 7 h earlier) in brackets. The robot was docked on the home Wi-Fi (`192.168.100.31`), Ibrahim present, no motion. The only robot configuration change was R18 (change register above).

Two things happened first.

- Automatic update. At 15:18 (08:18) a preflight found `unattended-upgrade` installing packages; it finished at 16:11:40 (09:11:40). `dpkg.log` shows 240 package upgrades on 2026-10-24, and `/var/run/reboot-required` lists `linux-image-6.8.0-1065-raspi` and `linux-base` (not rebooted). systemd stopped and started `turtlebot4.service` at least 8 times in that period (stops at 08:07:08 together with fwupd and packagekit, 08:10:55, 08:49:16, 08:52:42, 08:57:34, 09:00:17, 09:03:02 and one more before 08:47:17; starts at 08:08:16, 08:11:34, 08:47:17, 08:50:10, 08:53:21, 08:58:11, 09:00:55, 09:03:39, robot time). The update was waited out before testing. See the Known issues row and TB-28.
- Invalid runs. Two recordings started at 16:13 (09:13) and 16:26 (09:26) received 0 messages on `/odom` and `/dock_status` for 720 s each, and joiner B printed "odom messages in 5 s: 0" every time. Both are invalid and were not stored in `tests/logs/`. The cause is described in the Known issues row "Pi-local ROS topics silent after the last SSH logout" and was fixed by R18 (about 17:07 laptop time).

Method, valid runs after R18: as the first run. `record_timing.py --light --duration 720` copied to `/tmp` and run detached, 120 s quiet baseline, then 8 joins 60 s apart; start and end times logged with `time.monotonic()`; then `analyze_timing.py` and a correlation of gaps with join start and end.

Run A: joiner `ros2 topic list --no-daemon` (a fresh CLI participant each time; `--no-daemon` so that no ros2 daemon stays running and every join is a real join and leave). Started 17:11 (10:11), 3 min after the R18 bringup restart. 17,339 records, `/odom` 14,319 messages at 19.9 Hz, recorder CPU 9.7 % of one core. Each join lasted 3.0 to 3.8 s. Gaps: `/odom` 0.32 s at 34.9 s (baseline, before any join; ping max 14.9 ms) and `/odom` 0.26 s at 362.1 s (join 5, 2.6 s after its start). No other gaps, no `/dock_status` gap.

Run B: joiner = an `rclpy` node that subscribes to `/odom` (sensor-data QoS) for 5 s and exits. Started 17:23 (10:23). 16,729 records, `/odom` 13,736 messages at 19.1 Hz, recorder CPU 9.9 %. Each join lasted 7.4 to 8.2 s (start-up about 2.5 s plus 5 s). Messages the joiner itself received in its 5 s (about 100 expected): 99, 101, 99, 101, 89, 58, 40, 100.

Gaps in run B (start in recording time, length, offset from that join's start):

| Join (start) | Gaps |
|---|---|
| Baseline, 0 to 119.5 s | none |
| 1 (119.5 s) | none |
| 2 (179.5 s) | `/odom` 0.40 s at 180.4 s (+0.9 s) |
| 3, 4 | none |
| 5 (359.5 s) | `/dock_status` 7.26 s at 367.1 s (+7.5 s); `/odom` 7.05 s at 367.2 s (+7.6 s); `/odom` 2.68 s at 374.2 s (+14.7 s) |
| 6 (419.5 s) | `/odom` 0.35 s (+0.8 s), 0.50 s (+1.6 s), 0.67 s (+4.8 s), 1.75 s (+5.9 s), 2.52 s (+10.9 s); `/dock_status` 12.28 s at 424.1 s (+4.6 s) |
| 7 (479.5 s) | `/odom` 10.87 s at 484.6 s (+5.1 s); `/dock_status` 9.73 s at 485.1 s (+5.6 s) |
| 8 | none |

Analyzer classes: "publisher stopped" (header stamps stop too) except one "delivery delayed" (the 7.05 s gap) and one "unclear". Ping to the base rose to 19.5, 22, 65.8 and 73.5 ms in the long stalls (median 0.5 ms). Network: no errors, no drops, no link changes, Wi-Fi -69 to -72 dBm, no ping lost.

Comparison with the first run:

| Joiner | Joins followed by a stall | Longest `/odom` gap | Longest `/dock_status` gap |
|---|---|---|---|
| Bare node, 5 s (first run, afternoon) | 3 of 8 | 2.46 s | 6.50 s |
| A: `ros2 topic list --no-daemon` | 1 of 8 | 0.26 s | none |
| B: node subscribing to `/odom`, 5 s | 5 of 8 | 10.87 s | 12.28 s |

Reading:

- A participant that subscribes to `/odom` triggers base stalls more often and much longer than a bare node, and a short `ros2 topic list` almost never does. Run B reproduces the 7.5 to 11 s stalls of the evening of 2026-10-23/24.
- Stalls started 0.8 to 14.7 s after the subscriber started, and every cluster had ended by about 17 s after it.
- The base itself stops producing (stamps stop, ping to the base rises); the network does not.
- Why a new subscriber on the Pi makes the Create 3 stall is still open. Inferred, not confirmed: discovery and endpoint matching load on the Create 3 (firmware `I.0.0.FastDDS`, simple discovery: `ROS_DISCOVERY_SERVER` empty, RMW `rmw_fastrtps_cpp`, profile `/etc/turtlebot4/fastdds_rpi.xml` is an empty default profile).
- Limits: one run of each joiner, one robot, home Wi-Fi.

Consequence for programs: every motion program subscribes to `/odom`, so its own start can stall the base for up to about 12 s. Mitigation R-c (code, in `examples/` and the Studio templates, see [examples/README.md](examples/README.md)): before the first motion a program waits until at least 20 s after it started and 5 s of steady `/odom` (no gap over 0.3 s), with a 30 s timeout that never fires before that can be met. The first version used 3 s of steady `/odom`; it was changed after run B because 3 s could pass before the program's own stall, or in a 3.2 s quiet stretch inside a cluster (join 6). Not yet tested in motion: the 10 supervised motion starts are next.

Files: `tests/logs/2026-10-24_timing_tb25_joins_ros2cli.jsonl.gz` with `tests/logs/2026-10-24_timing_tb25_joins_ros2cli_joins.log`, and `tests/logs/2026-10-24_timing_tb25_joins_odom_sub.jsonl.gz` with `tests/logs/2026-10-24_timing_tb25_joins_odom_sub_joins.log`. Task: [TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving).

### Update 2026-10-24 (evening; supervised motion starts with the start-up check)

Run 17:54 to 18:04 laptop time (UTC+3; robot 10:54 to 11:03:57 EDT). Ibrahim next to the robot, about 1 m clear, home Wi-Fi. The Studio templates `spin_in_place.py` and `drive_forward_and_back.py` with the new start-up check (R-c: at least 20 s after start plus 5 s of steady `/odom`, no gap over 0.3 s) were copied to `/tmp/tb25_motion` on the robot (cleared at reboot; nothing added to `~/robot_code`, no robot configuration change) and run with `--yes` from a script that stops at the first failure. `record_timing.py --light` ran for the whole test (587.5 s, 10,808 `/odom` messages, 13.1 % of one core). Sequence: undock (`ros2 action send_goal /undock`, SUCCEEDED, 17 s), 10 program runs 10 s apart, dock (`ros2 action send_goal /dock`, SUCCEEDED, 35 s).

"Wait" is the start-up check; "gaps seen" are gaps over 0.3 s that the check saw while waiting; "max interval" is the largest `/odom` interval during the motion itself.

| Run | Program | Wait after start | Gaps seen while waiting | Result | Max interval in motion |
|---|---|---|---|---|---|
| 1 | spin +0.5 turn | 20.0 s | 0 | turned 179 deg | 0.07 s |
| 2 | spin -0.5 | 20.0 s | 0 | -179 deg | 0.08 s |
| 3 | forward and back 0.3 m | 20.0 s | 0 | ended 0.8 cm from start (odometry) | 0.27 s |
| 4 | spin +0.5 | 20.0 s | 0 | 179 deg | 0.07 s |
| 5 | spin -0.5 | 20.0 s | 0 | -180 deg | 0.06 s |
| 6 | forward and back | 22.5 s | 2 (9.8 s and 1.4 s; `/dock_status` 9.1 s; ping to base up to 34.6 ms), starting about 9 s after the program started | ended 1.1 cm from start | 0.16 s |
| 7 | spin +0.5 | 20.0 s | 2 (4.4 s and 0.6 s; `/dock_status` 9.55 s) | 179 deg | 0.52 s gap right at motion start |
| 8 | spin -0.5 | 20.1 s | 0 | -179 deg | 0.11 s |
| 9 | forward and back | 20.0 s | 1 (0.5 s) | ended 0.6 cm | 0.14 s |
| 10 | forward and back | 20.0 s | 1 (0.5 s) | ended 1.1 cm | 0.79 s gap about 0.8 s after motion start, and 0.30 s later |

Undock: `/odom` gaps of 1.80 s and 0.46 s. Dock: `/odom` gaps of 1.50, 5.39 and 1.51 s and a `/dock_status` gap of 5.46 s (ping to the base up to 44 ms). Both are started by a fresh `ros2 action send_goal` participant; the base docks and undocks by itself, so no program depended on `/odom` there.

Reading:

- 10 of 10 motion starts completed, no abort, no hold over the 2.0 s stale limit. The success measure "10 supervised motion starts with no abort" is met.
- The check worked as intended: the two long stalls of the test (9.8 s in run 6 and 4.4 s in run 7) came about 9 s after those programs started, while they were still waiting, so the robot stood still through them. With the first version of the check (3 s steady, passing a few seconds after start) both would most likely have hit during the motion and aborted the run (2.0 s stale limit). This is an inference from the timing, not a separate test.
- The TB-25 acceptance item "a mitigation keeps `/odom` gaps under 0.3 s over 10 motion starts" is not met: 2 of 10 runs had a short gap right at or just after motion start (0.52 s, 0.79 s), the original TB-15 motion-start pause; the programs' 0.3 s hold covered them. The long join-triggered stalls are avoided by waiting; short motion-start pauses remain.
- Cost: every program now waits about 20 s before moving (20.0 to 22.5 s here).
- Limits: 10 starts, one robot, home Wi-Fi.

Files: `tests/logs/2026-10-24_timing_tb25_motion_starts.jsonl.gz` and `tests/logs/2026-10-24_tb25_motion_starts_runs.log` (marks with monotonic times, and the undock, run and dock outputs). Task: [TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving).

### Update 2026-10-24 (late evening; TB-25 change A (R19) and join test, docked, no motion)

Read-only steps 3 and 4 of TB-25 (republisher, TurtleBot 4 and Create 3 settings, firmware notes, known issues) are written up in [ROADMAP.md, TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving). One finding: the Create 3 had no IP address but still held a saved Wi-Fi network and searched for it about every 7.5 s (scan, `NETWORK-NOT-FOUND`, failed DHCP request), on a base that idles at a CPU mean of 52 to 56 %. With Ibrahim's approval the saved network was removed at 16:03:13 robot time (R19 in the change register above). Nothing else on the base or the Pi was changed.

Then the follow-up join test was repeated with the same joiner B (an `rclpy` node that subscribes to `/odom` for 5 s) and the same method: `record_timing.py --light --duration 720`, 120 s baseline, 8 joins about 60 s apart, join and leave times from `time.monotonic()`. Start 16:04:52 robot time, robot docked, home Wi-Fi.

| Run | Joins followed by a stall | Longest `/odom` gap | Longest `/dock_status` gap |
|---|---|---|---|
| B, before R19 | 5 of 8 | 10.87 s | 12.28 s |
| B, after R19 | 0 of 8 | 1.27 s, 113 s after the last join | none (largest interval 1.29 s) |

Gaps after R19, both "publisher stopped": `/odom` 0.35 s at 608.2 s (Pi CPU 95 % at that moment) and 1.27 s at 651.2 s (ping to the base 12.9 ms, no correlate). No gap in the baseline or within 17 s of a join. Ping to the base median 0.46 ms, none lost; `/odom` 19.9 Hz overall.

Reading: a strong hint that the base's Wi-Fi search loop was a large contributor to the join stalls; one run only, so not proof. The idle 1.27 s gap shows the base can still pause without a join. Next steps are in TB-25 (repeat the test, the 10 motion starts, check after the next reboot that the base stays off the Wi-Fi).

Files: `tests/logs/2026-10-24_timing_tb25_joins_after_r19.jsonl.gz` and `tests/logs/2026-10-24_timing_tb25_joins_after_r19_joins.log`. Temporary files on the robot (`/tmp/tb25A_*`, `/tmp/tb25_joiner.py`) were removed.

### Changes made to the program

1. Fix 1: `ODOM_STALE` raised from 0.5 s to 1.0 s. Square, rotate and back-and-forth then completed. The triangle still aborted once on a 1.0 s gap.
2. Fix 2 (current): if odometry is older than `ODOM_HOLD` = 0.3 s the program sends zero velocity and waits, and it aborts only when odometry is older than `ODOM_STALE` = 2.0 s. A hold does not count as a stall.

### Open questions

- Whether the pause comes from the Create 3 firmware, the USB network link or Pi load. See TB-15.
- Whether other programs on this robot (Nav2, teleop) are affected.
- Added 2026-10-24: why the base stalls when it starts to move, and whether fewer subscribers or a different `create3_republisher` setup shorten the stalls (TB-25). The 2026-10-04 placeholder row "Root-cause characterisation" is partly filled by the table above; the 20-start campaign numbers are still missing.
- Added 2026-10-24 (evening): why a new subscriber to `/odom` on the Pi makes the Create 3 stall for up to about 12 s, while a bare node and a short `ros2 topic list` rarely do (see the evening follow-up update above). Inferred, not confirmed: discovery and endpoint matching load on the Create 3. Also open: whether the stall frequency changes with the `create3_republisher` setup.

## Incident: robot drops off the Wi-Fi (2026-10-04 and 2026-10-05)

| | |
|---|---|
| Dates | 2026-10-04 (robot time, EDT) and 2026-10-05 (laptop time, UTC+3) |
| Status on 2026-10-10 | **Open. Fix proposed, not applied.** The cause is a diagnosis, not confirmed |
| Status on 2026-10-24 | **Fix applied as R14 (power saving off in the `Students` profile); effect not verified.** It needs the robot on campus: TB-20 steps 5 and 6 |
| Changes involved | None so far. Proposed: turn Wi-Fi power saving off in the `Students` profile ([ROADMAP.md, TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving)) |
| Illustrated version | [docs/network-and-connectivity.html](docs/network-and-connectivity.html); Markdown version [docs/NETWORK-FINDINGS.md](docs/NETWORK-FINDINGS.md) |

### Summary

After being switched on on 2026-10-04, the robot answered SSH once and then dropped off the network; it did not come back during about 25 minutes of watching. On 2026-10-05 SSH by address and by key worked for about a minute, then the robot disappeared again and afterwards answered only in short windows of about 10 to 40 s. The laptop's Wi-Fi stayed fine the whole time, so the problem is on the robot side, and the robot's logs showed no Wi-Fi disconnects. The most likely cause is Wi-Fi power saving on the Raspberry Pi. The fix needs `sudo` and has not been applied.

### Impact

- Lab members cannot reach the robot reliably: SSH, VS Code and file copies fail or drop.
- Robot work planned on 2026-10-04 has not been done since: the new programs are not on the robot (R12; the robot went offline before they could be copied), and the first robot runs and the test campaign are pending ([ROADMAP.md, TB-23](ROADMAP.md#tb-23-first-robot-run-of-the-new-programs-and-the-connect-tool) and TB-16).
- No change to the robot and no damage are known.

### Timeline and evidence

| When | Clock | What was seen |
|---|---|---|
| 2026-10-03, about 20:31 | Laptop, UTC+3 | SSH dropped as docking started; the robot briefly left the Wi-Fi while moving, likely roaming between campus access points (see [Known issues](#known-issues)) |
| 2026-10-04, between sessions | Robot, EDT | The robot was off the network for about 1.5 hours. It was powered off between sessions; the cause of the drop is not confirmed |
| 2026-10-04, about 15:42 | Robot, EDT | After being switched on, it answered SSH once: up 4 min, address `10.87.10.205`, clock correct, lidar on USB. Then it dropped off the network. `turtlebot4.local` failed to resolve intermittently. It did not come back during about 25 minutes of watching |
| 2026-10-05, afternoon | Laptop, UTC+3 | SSH by address and by key worked for about a minute, then the robot disappeared again. It answered only in short windows (about 10 to 40 s). The laptop's Wi-Fi stayed fine the whole time. The robot's logs showed no Wi-Fi disconnects (which log was read is not recorded) |
| 2026-10-05 | Laptop, UTC+3 | Lab router set up as a possible dedicated network ([Lab router](#lab-router-not-used-by-the-robot-yet)). The robot was not moved to it |
| 2026-10-10 | n/a | Fix still not applied; robot not rechecked |

### Likely causes (diagnosis, not confirmed), most likely first

1. **Wi-Fi power saving on the Raspberry Pi** (on by default in Ubuntu; the R1 profile sets no value). The Pi stays associated with the access point but stops answering incoming connections most of the time. This fits the evidence: no disconnects in the robot's logs, a healthy laptop Wi-Fi, and short answer windows.
2. **`turtlebot4.local` (mDNS) is unreliable on the campus Wi-Fi.** This explains the name failures, not the failures by address. Use the address on the robot's display, for example `ssh ubuntu@10.87.10.205`.
3. **Roaming between campus access points**, which also drops SSH while the robot drives (known since 2026-10-03).

### Proposed fix (not applied)

To be run in a robot terminal by a person who knows the `ubuntu` password (`sudo` asks for it). Get a session first: connect by the address on the display, retrying if needed ([HOW-TO-CONNECT.md, Troubleshooting](HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found)).

```bash
sudo nmcli connection modify Students 802-11-wireless.powersave 2
sudo nmcli connection up Students
```

- **Verify:** `nmcli -g 802-11-wireless.powersave connection show Students` should print the value for "disable", 2. Then check from a laptop that the robot keeps answering SSH over a longer time (acceptance criteria in TB-20).
- **Undo:** the same command with `powersave 0` (the default), then reconnect: `sudo nmcli connection modify Students 802-11-wireless.powersave 0` and `sudo nmcli connection up Students`.
- **Risk:** the Wi-Fi reconnects, so SSH may drop for a few seconds. No reboot. If the session drops after the first command, log in again and run the second.
- **Record:** when applied, add it to the [change register](#change-register) as R14 with the date and the verify and undo steps, and update this record and the Known issues.

### Update 2026-10-24: new evidence and fix applied (R14)

Read-only checks on the robot (journal and NetworkManager files), then one change. The robot was not on `Students` that day (out of range, so its signal strength there could not be measured).

Evidence:

- **Power saving was on.** `/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf` sets `wifi.powersave = 3` (enable; the Ubuntu default). The `Students` and `Turtlebot4` profiles had the value `0` (default), so they inherited 3. The kernel log says `brcmfmac: brcmf_cfg80211_set_power_mgmt: power save enabled` at every boot. Driver `brcmfmac`, chip BCM43455, firmware 7.45.234. `iw` and `iwconfig` are not installed, so the live state of `wlan0` could not be read.
- **No disconnects on the symptom days.** Journal boots per day: boot -2 (2026-10-04 afternoon) has 0 disconnects; before connecting at 83 s it had 6 association rejects (status 16). Boot -1 (2026-10-05) has 0 disconnects and 5 WNM "Disassociation Imminent" notices (the access point asking the robot to move to another one). Boot -5 (2026-10-04, 6.8 h) has 3 disconnects (reason 8 at 1920 s; reason 3, locally generated, at 5978 s and 9818 s), roaming across 3 campus access points and one outage of about 67 s after the first. No beacon loss and no deauthentication anywhere.
- **Inference (not proven):** on the days with the "answers only in 10 to 40 s windows" symptom the robot stayed associated. That is consistent with Wi-Fi power saving (or filtering on the campus side) and not with Wi-Fi disconnects.

Change: R14, `sudo nmcli connection modify Students 802-11-wireless.powersave 2` (before `default`, after `disable`). `nmcli connection up Students` was not run, so it applies at the next join. Verify with `nmcli -g 802-11-wireless.powersave connection show Students`; undo with the same command and `0`. **Verification pending:** 30 connection attempts over 30 minutes on two days and a reboot test (TB-20), and a signal-strength measurement on campus (TB-26).

### Workarounds that worked

- Connect by IP address (the one on the robot's display) instead of `turtlebot4.local`.
- A retry loop on the laptop that reconnects when SSH fails ([HOW-TO-CONNECT.md](HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found)).
- The robot's own access point `Turtlebot4` (`10.42.0.1`), when the robot is on it. To keep internet, the laptop needs a second Wi-Fi adapter.

### Open questions

- Is power saving actually on for `wlan0` on this robot? Answered 2026-10-24: the global setting and the kernel log say yes (see the update above). The live state of `wlan0` was not read (`iw` is not installed).
- Does R14 stop the drops? Not known until the robot is tested on `Students` (TB-20 steps 5 and 6).
- Why the robot did not come back at all for about 25 minutes on 2026-10-04.
- Whether the drops also happen on the lab router network (TB-21).

### Lessons

- On campus, read the address from the robot's display; do not rely on `turtlebot4.local`.
- When the robot answers only sometimes, check the laptop's own Wi-Fi first. On 2026-10-05 it was fine, which pointed at the robot.
- Robot-side Wi-Fi changes need `sudo` and a reachable robot: plan them for a session with a person at the robot.

## Known issues

| Issue | Symptoms | Evidence | Status | Next action |
|---|---|---|---|---|
| Pi-local ROS topics silent after the last SSH logout (found 2026-10-24) | Programs on the robot get no `/odom` (motion programs stop with "no /odom from the Create 3 base"); `ros2 topic hz /odom` shows nothing, but `ros2 topic hz /_do_not_use/odom` shows 20 Hz; the bringup processes keep running | Two DDS-join recordings (16:13 and 16:26 laptop time) received 0 messages on `/odom` and `/dock_status` for 720 s each (both invalid, not stored). The base's raw `/_do_not_use/odom` arrived at 20 Hz, but `create3_republisher` (running, no errors) delivered nothing, and restarting the bringup did not help once the user had logged out. Cause: the bringup runs as `ubuntu`; Fast DDS passes messages between processes on the same Pi through `/dev/shm/fastrtps_*` files owned by `ubuntu`; `loginctl show-user ubuntu -p Linger` was `no` and `/etc/systemd/logind.conf` has `#RemoveIPC=yes` (the default), so when the last login session of `ubuntu` closes (every SSH logout when nobody else is logged in) systemd-logind deletes all shared memory of `ubuntu`, including the running bringup's. Earlier runs probably worked because a session stayed open (for example TurtleBot Studio's SSH connection); that is inferred. Whether this also caused earlier `/odom` stalls is not known and is not claimed | **Fixed by R18** (lingering on, see the change register), applied and verified 2026-10-24; not yet checked after a reboot | Without R18, restarting the bringup (`sudo systemctl restart turtlebot4`) helps only until the last SSH session closes. If the symptom returns, check `loginctl show-user ubuntu -p Linger` and `ls /dev/shm \| grep -c fastrtps` |
| Lidar not detected on USB (since the reboot at about 19:56 on 2026-10-03) | No `/scan` data; `scan_test.py` and `clearance_check.py` get nothing; `motion_test.sh` skips its forward drive | No `/dev/RPLIDAR`; no Silicon Labs CP210x device in `lsusb`, docked or undocked; `rplidar_ros` log: "cannot bind to the specified serial port '/dev/RPLIDAR'". The lidar spins. It worked before the reboot. A full power cycle did not help | **Resolved 2026-10-04**: loose USB cable, reseated by the user. See the [lidar record](#incident-lidar-not-detected-2026-10-03-resolved-2026-10-04) | Confirm detection after the next reboot (2026-10-04, about 15:42 robot time: on USB after a later power-on; `/scan` not recorded). Strain relief and label: ROADMAP TB-18 |
| `/odom` pauses when the wheels start | Programs that require fresh odometry stop; `motion_shapes.py` printed "odometry is stale" | 0.41 s gap in arrival and header stamps 0.12 s after motion start; 1.0 s gap at a segment change with Pi load 3.4. No gap while still. See the [finding](#finding-odom-pauses-at-motion-start) | Worked around in `motion_shapes.py` (hold at 0.3 s, abort at 2.0 s). **2026-10-24:** a 3.16 s stall at 2.0 s into a drive still aborted the program. Cause located in the Create 3 base, triggered by motion start (not Wi-Fi, not Pi CPU) | Characterise the cause (ROADMAP TB-15). Treat short `/odom` gaps as normal in your own programs. **Update 2026-10-24, evening:** idle stalls of 7.5 s and 11 s and a 7.8 s stall in a spin were seen over Wi-Fi; a base application restart did not remove them; hypothesis (not proven): they follow new ROS 2 participants joining ([TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving)) |
| Automatic Ubuntu updates run as soon as the robot has internet (2026-10-24) | Pi CPU 45 to 50 % and temperature about 67 °C while docked and idle, starting a minute after the robot reached the internet | `/etc/apt/apt.conf.d/20auto-upgrades` has `Update-Package-Lists "1"` and `Unattended-Upgrade "1"` (the Ubuntu default, not changed). `apt-daily.timer` and `apt-daily-upgrade.timer` both fired at 21:49 robot time, right after the clock synchronised (R16). `unattended-upgrade --download-only` then used one core at 100 % (nice 19). Allowed origins are the Ubuntu ones only (`noble`, `noble-security`, ESM), not the ROS repository | Open. Not changed. Automatic reboot is off by default, but the upgrade step can install Ubuntu packages while ROS runs | Decide whether the lab robot should install updates by itself (a new ROADMAP task). Until then, expect extra CPU load for some minutes after the robot first gets internet, and do timing measurements only when `pgrep -a unattended-upgrade` shows just the `-shutdown` helper. **Update, evening:** the download job was still running 45 minutes later (21:50 to 22:35 robot time, one core at 100 %); Pi CPU 45 to 50 %, temperature 65 to 72 °C docked. Not stopped. Decision: [ROADMAP.md, TB-28](ROADMAP.md#tb-28-decide-whether-the-robot-installs-ubuntu-updates-by-itself) |
| Ubuntu installed 240 package upgrades by itself during a session (2026-10-24) | The ROS bringup (`turtlebot4.service`) was stopped and started at least 8 times by systemd between 08:07 and 09:04 robot time; a kernel update waits for a reboot | `unattended-upgrade` was found running at 15:18 laptop time (08:18 robot; about 50 min in, load average 2.8) and finished at 16:11:40 laptop (09:11:40 robot). `dpkg.log` shows 240 upgrades that day, among them `linux-firmware`, `util-linux`, the GCC 13 cross compilers, `linux-libc-dev` and a new kernel package; `/var/run/reboot-required` lists `linux-image-6.8.0-1065-raspi` and `linux-base`. Automatic reboot is off, so the robot was not rebooted. Inferred, not confirmed: the upgrade restarted services after replacing libraries. Nothing was stopped or changed by us; the update was waited out before testing | Open (TB-28). The next reboot will be the first run on the new kernel | Check `pgrep -a unattended-upgrade` before any timing test; plan the reboot and re-check R14, R17, R18 afterwards. [ROADMAP.md, TB-28](ROADMAP.md#tb-28-decide-whether-the-robot-installs-ubuntu-updates-by-itself) |
| Lidar motor not restarted after undock (2026-10-24) | After undocking, `motion_shapes.py` fails at setup with "no /scan" | The `rplidar` log has "Stop" at 14:37:45 robot time while docked and no "Start" after the undock, which succeeded. `/scan` came back at 7.6 Hz after the service call below | Open. Workaround in place (runtime action, no configuration change) | Workaround: `ros2 service call /start_motor std_srvs/srv/Empty`. Find out why it did not restart: [ROADMAP.md, TB-24](ROADMAP.md#tb-24-lidar-motor-does-not-restart-after-undocking). On 2026-10-04 "RPLIDAR started" was logged at undock, so this may be new or intermittent |
| `/e_stop` service reports failure although it works (found 2026-10-24) | A call to the Create 3 `/e_stop` service returns `success=False` with an empty message, yet the wheels are disabled | Seen with Create 3 firmware `I.0.0.FastDDS`: after the call, `wheels_enabled` in `/wheel_status` was false and the wheels did stop; the same on release | Open. Workaround in place | Do not trust the service result: check `wheels_enabled` in `/wheel_status`. [TurtleBot Studio](tools/studio/README.md) does this and reports "confirmed by wheels" |
| Create 3 `/battery_state` `power_supply_status` is always 0 (found 2026-10-24) | A tool shows "not charging" or "unknown" while the robot is docked and charging | Docked, `power_supply_status` stayed 0 (unknown) while the current was +0.57 A and the battery rose | Open. Workaround in place | Judge charging from the current (positive = charging). [TurtleBot Studio](tools/studio/README.md) does this |
| Robot clock wrong | Certificate or date errors from HTTPS, `git`, `pip` and `apt` | Campus blocks NTP (chrony sources unreachable); the Pi has no battery-backed clock and booted in October 2024. 2026-10-24: the clock read 28 October 2024 (about two years behind); `tb4-https-time.service` failed because there is no internet over Ethernet or the hotspot | Accepted once the clock fix is removed | Copy code from a laptop. Propose any clock solution in [ROADMAP.md](ROADMAP.md) before applying it. **Update 2026-10-24, evening:** the Pi clock has been correct since R16 (internet via the home Wi-Fi) and the base clock was re-synchronised by hand; without internet the Pi has no way to keep the date across a power-off (no battery-backed clock). Proposals in TB-17 |
| Create 3 base silent at handover | No `/battery_state` or `/dock_status`; undock and dock time out | Pi in 2024, base in 2026 after the power cycle | Fix prepared, not run. Not occurring on 2026-10-04 (base talking, clocks agree, clock fix still installed) | If it happens again, run the [resolution plan](#resolution-plan). Keep-or-remove decision: ROADMAP TB-17 |
| SSH sessions drop while the robot moves | A running `ros2 action send_goal` is cancelled, so the move is not finished | Happened on 2026-10-03 as docking started; the robot briefly left the Wi-Fi, likely roaming between campus access points | Workaround in place | Run motion scripts detached on the robot (`setsid nohup` or `tmux`), as described in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) |
| Robot drops off the Wi-Fi; answers SSH only in short windows (since 2026-10-04) | SSH works for a short time (about 10 to 40 s windows; once about a minute), then connections time out; the robot can stay away for 25 minutes or more | 2026-10-04 about 15:42 (robot time) and 2026-10-05 afternoon (UTC+3). Laptop Wi-Fi fine; robot logs showed no Wi-Fi disconnects. See the [Wi-Fi incident](#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05) | **Open. Fix proposed, not applied** (2026-10-10). Likely cause Wi-Fi power saving (not confirmed). **2026-10-24: fix applied as R14; effect not verified until the robot is on campus.** New evidence: power saving was on, and the logs show no disconnects on the symptom days | Admin: apply and verify the power-saving fix ([ROADMAP.md, TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving)). Users: connect by the display address and retry ([HOW-TO-CONNECT.md](HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found)) |
| `turtlebot4.local` not found on the campus Wi-Fi (intermittent, since 2026-10-04) | `Could not resolve hostname turtlebot4.local`, or the name hangs, while the robot is on `Students` | Failed intermittently on 2026-10-04 (about 15:42 robot time). mDNS is unreliable on campus Wi-Fi | Open. Workaround in place | Use the address on the robot's display. A fixed address would remove the dependency: [TB-08](ROADMAP.md#tb-08-stable-addressing) or the lab router proposal ([TB-21](ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router)) |
| Clock timer can step the clock while ROS runs | Base goes silent some time after boot | If the boot-time fetch fails, the timer retries 15 minutes later and can then jump the clock with ROS running | Still possible: R7 is still installed on 2026-10-04. Moot once R7 is removed | Decide in ROADMAP TB-17. Until then, if the base goes silent, restart the base application |
| `create3_republisher` crashed | Process restarts | Exited with code -11 twice and restarted by itself; seen before any system change | Watch | Note any recurrence here |

## Verification checklist

Run on the robot (`ssh ubuntu@turtlebot4.local`, or the address on its display). A login shell already has ROS set up; a script must first run `source /etc/turtlebot4/setup.bash`, as `motion_test.sh` does. Allow 2 minutes after power-on, and 30 to 60 seconds for each `ros2` command-line call (the Pi is slow to start them).

1. Wi-Fi profile active. Expected: `Students:wlan0` (or `netplan-wlan0-Turtlebot4:wlan0` if Students is out of range).
   ```bash
   nmcli -t -f NAME,DEVICE connection show --active
   ```
2. Wi-Fi address. Expected: `10.87.x.x` on Students, `10.42.0.1` on the fallback.
   ```bash
   ip -4 -br addr show wlan0
   ```
3. ROS service. Expected: `active`.
   ```bash
   systemctl is-active turtlebot4
   ```
4. ROS environment. Expected: `ROS_DOMAIN_ID` 0; `RMW_IMPLEMENTATION` is `rmw_fastrtps_cpp` or unset (Fast DDS is the Jazzy default).
   ```bash
   printenv ROS_DOMAIN_ID RMW_IMPLEMENTATION
   ```
5. Base data. Expected: one message each. If nothing prints, restart the Create 3 application (`curl -X POST http://192.168.186.2/api/restart-app`) and try again.
   ```bash
   timeout 60 ros2 topic echo --once /dock_status
   timeout 60 ros2 topic echo --once /battery_state
   ```
6. Lidar. Expected: `/dev/RPLIDAR` exists, a CP210x device is listed, `/scan` has a publisher. Scan data arrives only off the dock (the lidar is stopped on the dock to save power).
   ```bash
   ls -la /dev/RPLIDAR
   lsusb | grep -i cp210
   ros2 topic info /scan
   ```
   Values seen on 2026-10-04: `/dev/RPLIDAR -> ttyUSB0`; `lsusb` line with ID `10c4:ea60` (Silicon Labs CP210x UART Bridge); `/scan` with 1 publisher. Off the dock only:
   ```bash
   ros2 topic hz /scan
   ros2 topic echo --once --full-length /scan
   ```
   Expected off the dock: about 7.7 to 7.8 Hz; frame `rplidar_link`; 720 ranges (`angle_increment` about 0.0087 rad), `range_min` 0.15, `range_max` 12.0; most ranges finite in a room (72 % on 2026-10-04). `python3 ~/robot_code/clearance_check.py 0.6` should print "lidar frame offset 90 deg" and exit 0 or 1.

   Gotchas: without `--full-length`, `ros2 topic echo` shows only the first 128 ranges followed by `...`. `ros2 topic hz` in Jazzy has no `--qos-reliability` option; run it without one. On the dock, `/scan` has a publisher but no messages: that is the power saver, not a fault.
7. Clock. Record the value; a wrong date is a known issue. After the clock fix is removed, expect no `tb4-https-time` units and no drop-in folder.
   ```bash
   date
   systemctl list-unit-files 'tb4-https-time*'
   ls /etc/systemd/system/turtlebot4.service.d
   ```
8. Name resolution, from a laptop on Students. Expected: `turtlebot4`. Since 2026-10-04 the name can fail intermittently on campus; if it does, repeat with the address on the display and note the failure.
   ```bash
   ssh ubuntu@turtlebot4.local hostname
   ```
9. Wi-Fi power saving (added 2026-10-10, read only). Expected after the TB-20 fix: the value for "disable", 2. Before the fix the profile sets no value (the value on the robot has not been read yet).
   ```bash
   nmcli -g 802-11-wireless.powersave connection show Students
   ```

## Maintainer notes

- Copy files to the robot with `scp` or VS Code, not through a shell heredoc: a heredoc collapsed double backslashes and broke a Python file.
- Shell scripts and Python programs that run on the robot keep Linux (LF) line endings, also in Windows clones: `TurtleBot/.gitattributes` (added 2026-10-10) sets `*.sh` and `*.py` to `eol=lf`. Before it, a Windows clone with `core.autocrlf=true` checked these files out with CRLF endings, and a `.sh` file copied to the robot from such a clone fails in bash (`$'\r': command not found`). The files stored in git were always LF.
- Right after the robot joins Students, `turtlebot4.local` could briefly resolve to the wrong address; the first VS Code connect timed out until the SSH `ConnectTimeout` was lowered to 5 s. R6 addresses the cause.
- On the laptop, a VS Code extension install failed with `ENOTFOUND` while Wi-Fi 2 still listed the robot's DNS server (`10.42.0.1`); it worked once the adapter showed Disconnected.
- Windows may show an "8-digit PIN" box when joining `Turtlebot4`. That is the WPS screen; choose "Connect using a security key instead".
- To power the robot off, follow the official manual and shut down the Pi before cutting power, so the SD card is not damaged.
- Robot motion tests are run supervised, in short batches, with a person next to the robot (lesson of 2026-10-04: an hour-long unattended test campaign run by an AI subagent was blocked by the AI tool's safety guard).
- On campus, connect by the address on the robot's display; `turtlebot4.local` has been unreliable there since 2026-10-04.

### Repository note: branch switch in GitHub Desktop (2026-10-05, resolved 2026-10-10)

| | |
|---|---|
| What happened | On 2026-10-05 GitHub Desktop switched the local clone to `main` while TurtleBot changes were uncommitted. The changes were carried over and conflicted in `TurtleBot/README.md`, and an unrelated RAPTOR report got staged. On `main` the README then pointed at files that only existed on the TurtleBot branch, which made the guide look broken |
| Resolved | 2026-10-10: conflict cleared, `main` updated, nothing lost |
| Robot impact | None (repository only) |
| Branches as seen on 2026-10-10 | In the local clone (remote refs as last fetched), `main` (906b14b, 2026-10-09) contains the TurtleBot commits up to 4d59c85 (2026-10-04). a8c0b4e (2026-10-04) and 7007f51 (2026-10-05) are on the branch `turtlebot/lidar-check-and-motion-programs` only. Merging that branch into `main` once it is finished is open ([ROADMAP.md, TB-12](ROADMAP.md#tb-12-documentation-follow-ups)). Later on 2026-10-10 the branch was merged into `main`, which closes this point |

Lessons:
- Commit or discard changes before switching branches.
- Work on a branch, and merge it into `main` when the work is finished.
- GitHub's `main` is what lab members read, so links in `main` must point at files that exist on `main`.

## Related documents

- [README.md](README.md): index of the TurtleBot documents.
- [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md): user guide (connecting, running code, troubleshooting).
- [ROADMAP.md](ROADMAP.md): plan for the next iterations, including remote desktop.
- [General Tasks/TurtleBot4 - connect to university Wi-Fi.txt](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt): raw chronological log, including failures.
- [General Tasks/TurtleBot4 - lidar check and motion programs.txt](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt): log of the 2026-10-04 lidar check and motion program work, including failures.
- [General Tasks/TurtleBot4 - Ethernet, Wi-Fi power save and odometry timing.txt](../General%20Tasks/TurtleBot4%20-%20Ethernet%2C%20Wi-Fi%20power%20save%20and%20odometry%20timing.txt): log of 2026-10-24 (Ethernet access, the Wi-Fi power-save change R14, the supervised motion test with the timing recorder), including what failed.
- [General Tasks/TurtleBot4 - network and connectivity.txt](../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt): log of the Wi-Fi drops, the lab router and the repository incident (2026-10-04 evening to 2026-10-10), including failures.
- [docs/](docs/index.html): illustrated pages on the lidar diagnosis, the motion program design, the test results and the network and connectivity findings ([docs/network-and-connectivity.html](docs/network-and-connectivity.html)).
- [examples/README.md](examples/README.md) and [tests/](tests/): how to run the example programs, and the test campaign.
- [`setup/`](setup/) and [`examples/`](examples/): copies of the scripts and programs installed on the robot.
- [turtlebot4-field-guide.html](turtlebot4-field-guide.html): general TurtleBot 4 background.
- Official TurtleBot 4 user manual: https://turtlebot.github.io/turtlebot4-user-manual/
