# TurtleBot 4: Maintenance and Configuration Record

| | |
|---|---|
| Robot | Lab TurtleBot 4 Standard, hostname `turtlebot4` |
| Owner | AlfaisalX lab, College of Engineering and Advanced Computing. Ask the lab maintainer or the lab supervisor for access, passwords and approval of changes |
| Last updated | 2026-10-04 (robot state as of 2026-10-04, about 12:30 robot time) |
| Audience | Lab maintainers and whoever administers the robot next |
| Covers | Current configuration, every change made, admin scripts, incidents, open issues, health checks |
| Times | 2026-10-03 entries use the original author's laptop time (UTC+3). 2026-10-04 entries use the robot's own clock as shown in its journal (EDT, UTC-4), so 11:44 robot time is 18:44 in UTC+3 |

## Purpose

This is the administrative record for the lab's TurtleBot 4. Everyday use (connecting, running code) is in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md). Planned work is in [ROADMAP.md](ROADMAP.md). The raw chronological logs, including failed attempts, are in [General Tasks/TurtleBot4 - connect to university Wi-Fi.txt](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt) (2026-10-03) and [General Tasks/TurtleBot4 - lidar check and motion programs.txt](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt) (2026-10-04). Illustrated write-ups (lidar diagnosis, motion program design, test results) are in [docs/](docs/index.html).

Rule followed: change only what is necessary on shared hardware, and record every change with how to verify it and how to undo it. When you change the robot, add a row to the [change register](#change-register) in the same commit.

No passwords, Wi-Fi keys or other credentials are recorded here or anywhere in this repository (it is public).

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

### Network

| | `Students` | `netplan-wlan0-Turtlebot4` |
|---|---|---|
| Role | Primary: robot joins the university Wi-Fi | Fallback: robot's own access point (factory) |
| Defined in | NetworkManager keyfile `/etc/NetworkManager/system-connections/Students.nmconnection`, root only (mode 600). Added 2026-10-03 | netplan `/etc/netplan/50-wifis.yaml`. Not modified |
| SSID and security | `Students`, WPA2-Personal (one shared password) | `Turtlebot4`, 5 GHz |
| Robot address | DHCP, `10.87.x.x` (was `10.87.10.205/18` on 2026-10-03; it can change) | `10.42.0.1`; clients get `10.42.0.x` |
| Autoconnect priority | 10 | 0 |

NetworkManager uses Students when it is in range and falls back to the access point otherwise. After the reboot on 2026-10-03 the robot came back on Students by itself. The robot joined Students on 5 GHz during the test phase and on 2.4 GHz in the permanent phase.

avahi is limited to `wlan0`, so `turtlebot4.local` resolves only to the Wi-Fi address. Before this change it sometimes resolved to `192.168.186.3`, the internal link to the base, which a laptop cannot reach.

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

## Change register

R1 to R10 were made on 2026-10-03, R11 onward on 2026-10-04. Run robot commands in a robot terminal.

### On the robot

| ID | Change | Location | Purpose | Verify | Undo | Status |
|---|---|---|---|---|---|---|
| R1 | Wi-Fi profile `Students` (WPA2-Personal, `wlan0`, DHCP, autoconnect on, priority 10) | `/etc/NetworkManager/system-connections/Students.nmconnection` (root only, mode 600) | Join the university Wi-Fi; factory access point kept as fallback | `nmcli -f connection.id,connection.autoconnect,connection.autoconnect-priority connection show Students` | `sudo nmcli connection delete Students`, then `sudo reboot`. The robot returns to its `Turtlebot4` access point (10.42.0.1). Expect an SSH session over Students to drop; reconnect through the access point | Active |
| R2 | One SSH public key | `/home/ubuntu/.ssh/authorized_keys` | Password-free SSH and VS Code from the original author's workstation (key W1) | `ssh-keygen -lf ~/.ssh/authorized_keys` (lists key fingerprints) | Delete that key's line from the file | Active. The key belongs to one person's workstation: remove or replace it when that person leaves the project |
| R3 | Wi-Fi switch and admin scripts | `~/wifi-switch/` | Copies of the scripts in `TurtleBot/setup/`, the switch log `log.txt` and `students_ip.txt` | `ls -la ~/wifi-switch` | `rm -r ~/wifi-switch`, but only after `undo-clock` has run, because the R5 links point into this folder. Installed copies (R1, R6, R7, R8) are separate and keep working | Present |
| R4 | Example programs | `~/robot_code/` (`hello_robot.py`, `scan_test.py`, `clearance_check.py`, `drive_test.py`, `motion_test.sh`; copies in `TurtleBot/examples/`) | Folder VS Code opens for users | `ls -la ~/robot_code` | Delete the folder after saving any user files in it | Present. Users may have added files; detached runs write `motion.log` and `dock.log` here |
| R5 | Admin shortcuts (symlinks) | `~/finish-setup` to `root-setup.sh`, `~/fix-ros` to `fix-ros.sh`, `~/undo-clock` to `undo-clock.sh` | Short admin commands, run as `sudo ./name` from `~` | `ls -l ~/finish-setup ~/fix-ros ~/undo-clock` | `rm ~/finish-setup ~/fix-ros ~/undo-clock` (removes only the links) | Present. Proposed: remove `finish-setup` and `fix-ros` after `undo-clock` has run, since either one reinstalls the clock fix |
| R6 | avahi limited to Wi-Fi | `/etc/avahi/avahi-daemon.conf` (`allow-interfaces=wlan0` under `[server]`); original saved as `/etc/avahi/avahi-daemon.conf.before-tb4` | `turtlebot4.local` resolves only to the Wi-Fi address | `grep -n '^allow-interfaces' /etc/avahi/avahi-daemon.conf` | `sudo cp /etc/avahi/avahi-daemon.conf.before-tb4 /etc/avahi/avahi-daemon.conf`, then `sudo systemctl restart avahi-daemon` | Active. Keep |
| R7 | HTTPS clock fix | `/usr/local/sbin/tb4-https-time`, `/etc/systemd/system/tb4-https-time.service`, `/etc/systemd/system/tb4-https-time.timer` (enabled: 60 s after boot, then every 15 min) | Set the clock from an HTTPS `Date` header, because campus blocks NTP | `systemctl list-unit-files 'tb4-https-time*'` | `cd ~ && sudo ./undo-clock` (removes R7 and R8, restarts ROS); [manual steps](#removing-the-clock-fix-by-hand) | Removal prepared (`sudo ./undo-clock`), not confirmed run as of 2026-10-03. Caused the incident below. **2026-10-04: still installed** (timer file present), clock correct, base talking; left in place by the user's decision. Keep or remove: ROADMAP TB-17 |
| R8 | ROS waits for the clock (drop-in) | `/etc/systemd/system/turtlebot4.service.d/10-wait-for-clock.conf` (`Wants=` and `After=tb4-https-time.service`) | Start `turtlebot4.service` only after the clock fix has run | `systemctl cat turtlebot4` (the drop-in is listed at the end if present) | Removed by `sudo ./undo-clock`; [manual steps](#removing-the-clock-fix-by-hand) | Removal prepared (`sudo ./undo-clock`), not confirmed run as of 2026-10-03. **2026-10-04: still installed** (drop-in present). See R7 |
| R9 | VS Code server | `~/.vscode-server` (207 MB download, about 600 MB unpacked) | Installed automatically by VS Code Remote-SSH on the first connect | `du -sh ~/.vscode-server` | `rm -rf ~/.vscode-server`. VS Code downloads it again on the next connect (about 10 minutes over campus Wi-Fi) | Present. Safe to delete |
| R10 | Temporary switch job | Transient systemd unit `tb4-wifi-switch` and `/run/tb4-wifi-controller.sh`, created by `start.sh` | Ran `controller.sh` in the background | `systemctl status tb4-wifi-switch` (expected: unit not found) | None needed: `/run` is cleared at boot and the unit was started with `--collect` | Gone after the reboot at about 19:56 |
| R11 | Motion program `motion_shapes.py` (2026-10-04) | `~/robot_code/motion_shapes.py` (copy of [examples/motion_shapes.py](examples/motion_shapes.py)) | Drive test shapes closed-loop on `/odom`, with safety stops | `ls -l ~/robot_code/motion_shapes.py` | `rm ~/robot_code/motion_shapes.py` | Present. User file, no system change. The version on the robot may lag the repo copy during testing; compare before relying on it |
| R12 | Further example programs (2026-10-04) | Not deployed yet: the programs are in [examples/](examples/) only. The robot went offline before they could be copied. When copied, list them here (`health_check.py`, `sensor_report.py`, `lidar_snapshot.py`, `lightring_status.py`, `more_shapes.py`, `wall_approach.py`, `keep_distance.py`, `motion_common.py`, `campaign.sh`) | More example programs | `ls -l ~/robot_code` | Delete the listed files | Not applied |
| R13 | Test results folder (2026-10-04) | Not created. The 2026-10-04 run logs were copied from `/tmp` on the robot into [tests/logs/](tests/logs/) | Keep the raw run logs | n/a | n/a | Not applied |

Not changed: the factory access point profile and `/etc/netplan/50-wifis.yaml`, the ROS and TurtleBot configuration, the robot password, and the Create 3 settings (the base was only restarted).

On 2026-10-04 no `sudo` was used, no configuration was changed and the clock was not touched. The only physical change was reseating the lidar USB cable (same cable, same port) before the 11:44 boot. Temporary diagnosis files were written to `/tmp` (`undock.log`, `shapes_*.log`, `gapprobe*.py`, `odomprobe.py`, `odomprobe.log`, `scan_*.txt`); `/tmp` is cleared at reboot, so they need no undo.

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
| _To be completed_ | Further undock and dock actions during the test campaign | Test campaign | _Placeholder_ |

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
| `undo-clock.sh` | `~/undo-clock` | `sudo ./undo-clock` | Yes | Disables and deletes R7 and R8, removes the empty drop-in folder, reloads systemd, restarts `turtlebot4.service` (no reboot; also picks up a re-plugged lidar) | Prepared; not confirmed run as of 2026-10-03. Follow it with a Create 3 application restart |
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
| Status | Worked around in `motion_shapes.py`; root cause under characterisation ([ROADMAP.md, TB-15](ROADMAP.md#tb-15-characterise-the-odom-pauses-at-motion-start)) |
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

### Changes made to the program

1. Fix 1: `ODOM_STALE` raised from 0.5 s to 1.0 s. Square, rotate and back-and-forth then completed. The triangle still aborted once on a 1.0 s gap.
2. Fix 2 (current): if odometry is older than `ODOM_HOLD` = 0.3 s the program sends zero velocity and waits, and it aborts only when odometry is older than `ODOM_STALE` = 2.0 s. A hold does not count as a stall.

### Open questions

- Whether the pause comes from the Create 3 firmware, the USB network link or Pi load. See TB-15.
- Whether other programs on this robot (Nav2, teleop) are affected.

## Known issues

| Issue | Symptoms | Evidence | Status | Next action |
|---|---|---|---|---|
| Lidar not detected on USB (since the reboot at about 19:56 on 2026-10-03) | No `/scan` data; `scan_test.py` and `clearance_check.py` get nothing; `motion_test.sh` skips its forward drive | No `/dev/RPLIDAR`; no Silicon Labs CP210x device in `lsusb`, docked or undocked; `rplidar_ros` log: "cannot bind to the specified serial port '/dev/RPLIDAR'". The lidar spins. It worked before the reboot. A full power cycle did not help | **Resolved 2026-10-04**: loose USB cable, reseated by the user. See the [lidar record](#incident-lidar-not-detected-2026-10-03-resolved-2026-10-04) | Confirm detection after the next reboot. Strain relief and label: ROADMAP TB-18 |
| `/odom` pauses when the wheels start | Programs that require fresh odometry stop; `motion_shapes.py` printed "odometry is stale" | 0.41 s gap in arrival and header stamps 0.12 s after motion start; 1.0 s gap at a segment change with Pi load 3.4. No gap while still. See the [finding](#finding-odom-pauses-at-motion-start) | Worked around in `motion_shapes.py` (hold at 0.3 s, abort at 2.0 s) | Characterise the cause (ROADMAP TB-15). Treat short `/odom` gaps as normal in your own programs |
| Robot clock wrong | Certificate or date errors from HTTPS, `git`, `pip` and `apt` | Campus blocks NTP (chrony sources unreachable); the Pi has no battery-backed clock and booted in October 2024 | Accepted once the clock fix is removed | Copy code from a laptop. Propose any clock solution in [ROADMAP.md](ROADMAP.md) before applying it |
| Create 3 base silent at handover | No `/battery_state` or `/dock_status`; undock and dock time out | Pi in 2024, base in 2026 after the power cycle | Fix prepared, not run. Not occurring on 2026-10-04 (base talking, clocks agree, clock fix still installed) | If it happens again, run the [resolution plan](#resolution-plan). Keep-or-remove decision: ROADMAP TB-17 |
| SSH sessions drop while the robot moves | A running `ros2 action send_goal` is cancelled, so the move is not finished | Happened on 2026-10-03 as docking started; the robot briefly left the Wi-Fi, likely roaming between campus access points | Workaround in place | Run motion scripts detached on the robot (`setsid nohup` or `tmux`), as described in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) |
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
8. Name resolution, from a laptop on Students. Expected: `turtlebot4`.
   ```bash
   ssh ubuntu@turtlebot4.local hostname
   ```

## Maintainer notes

- Copy files to the robot with `scp` or VS Code, not through a shell heredoc: a heredoc collapsed double backslashes and broke a Python file.
- Right after the robot joins Students, `turtlebot4.local` could briefly resolve to the wrong address; the first VS Code connect timed out until the SSH `ConnectTimeout` was lowered to 5 s. R6 addresses the cause.
- On the laptop, a VS Code extension install failed with `ENOTFOUND` while Wi-Fi 2 still listed the robot's DNS server (`10.42.0.1`); it worked once the adapter showed Disconnected.
- Windows may show an "8-digit PIN" box when joining `Turtlebot4`. That is the WPS screen; choose "Connect using a security key instead".
- To power the robot off, follow the official manual and shut down the Pi before cutting power, so the SD card is not damaged.

## Related documents

- [README.md](README.md): index of the TurtleBot documents.
- [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md): user guide (connecting, running code, troubleshooting).
- [ROADMAP.md](ROADMAP.md): plan for the next iterations, including remote desktop.
- [General Tasks/TurtleBot4 - connect to university Wi-Fi.txt](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt): raw chronological log, including failures.
- [General Tasks/TurtleBot4 - lidar check and motion programs.txt](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt): log of the 2026-10-04 lidar check and motion program work, including failures.
- [docs/](docs/index.html): illustrated pages on the lidar diagnosis, the motion program design and the test results.
- [examples/README.md](examples/README.md) and [tests/](tests/): how to run the example programs, and the test campaign.
- [`setup/`](setup/) and [`examples/`](examples/): copies of the scripts and programs installed on the robot.
- [turtlebot4-field-guide.html](turtlebot4-field-guide.html): general TurtleBot 4 background.
- Official TurtleBot 4 user manual: https://turtlebot.github.io/turtlebot4-user-manual/
