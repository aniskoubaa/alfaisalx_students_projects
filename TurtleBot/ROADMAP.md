# TurtleBot 4 roadmap

Plan of work for the lab's TurtleBot 4.

**Last updated:** 2026-10-04 (robot state as of 2026-10-03)

## Purpose

This file lists the open work on the lab's TurtleBot 4, in priority order. Each task has a goal, concrete steps, checkable acceptance criteria, risks with rollback, and an effort estimate. It is the place to look first when you have time to work on the robot.

How the robot is configured, and every change made to it, is recorded in [MAINTENANCE.md](MAINTENANCE.md). How to connect and run code is in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md).

## How to use this file

1. Pick the top task in the [task summary](#task-summary): P0 before P1, then the lowest ID, among tasks whose dependencies are Done.
2. Set its status to **In progress**, in the summary table and in the task section, with your name and the date.
3. Read the whole task before you start. Commands marked **[to verify]** have not been run on this robot; check them first, and correct this file if they need changes.
4. Change only what the task needs. The robot is shared lab hardware.
5. Record every change to the robot, or to shared accounts and network settings, in [MAINTENANCE.md](MAINTENANCE.md), with how to verify it and how to undo it. Add a dated entry to the [General Tasks log](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt).
6. When the acceptance criteria are met, set the status to **Done** with the date, and go through the [definition of done](#definition-of-done-for-any-change).
7. New work gets the next free ID (TB-15, TB-16, and so on). Do not reuse or renumber IDs.

Admin steps (`sudo`, Wi-Fi changes) need a person who knows the robot's `ubuntu` password to type it. Never write passwords, Wi-Fi keys or private keys in this repository: it is public.

### Conventions

| Term | Meaning |
|---|---|
| P0 | Blocking: the robot cannot do its basic job until this is fixed |
| P1 | Important |
| P2 | Improvement |
| P3 | Nice to have |
| Open | Not started |
| Prepared | Steps or scripts are ready but have not been run |
| In progress | Someone is working on it (name and date in the task) |
| Done | Acceptance criteria met (date in the task) |
| **[verified]** | The command was run successfully on this robot (date given) |
| **[prepared]** | Written and reviewed, not yet run on this robot |
| **[to verify]** | Not tested on this robot; check before relying on it |

Commands run in a terminal on the robot (SSH or VS Code Remote-SSH), from the home folder, unless marked **On the laptop**. Text in angle brackets, such as `<robot-address>`, is a placeholder.

## State on 2026-10-03

Working:
- The robot (TurtleBot 4 Standard: Raspberry Pi 4 on an iRobot Create 3 base, Ubuntu 24.04.1 Server without a desktop, ROS 2 Jazzy) joins the university `Students` Wi-Fi by itself. If `Students` is not available it falls back to its own access point `Turtlebot4` (robot address 10.42.0.1).
- It is reachable as `turtlebot4.local` or by the address on its display. SSH and VS Code Remote-SSH work.
- Example programs are in `~/robot_code` on the robot and in [examples/](examples/).
- Earlier on 2026-10-03, undock, a 360° spin and docking worked.

Not working or open:
- The Create 3 base sends no data to ROS because the Pi and base clocks disagree. A fix is prepared but has not been confirmed as run ([TB-01](#tb-01-restore-create-3-base-communication)).
- The lidar spins but is not detected on USB since about 19:56 ([TB-02](#tb-02-fix-lidar-detection)), so the forward drive of the movement test has never run ([TB-03](#tb-03-complete-the-movement-test-with-the-lidar)).
- The robot clock is wrong: campus blocks NTP and the Pi has no battery-backed clock ([TB-04](#tb-04-choose-a-reliable-time-strategy)).
- The `ubuntu` account and the access point probably still use the factory passwords published in the TurtleBot 4 manual ([TB-05](#tb-05-security-hardening)).
- SSH and `ros2 action send_goal` can drop while the robot moves ([TB-10](#tb-10-make-long-commands-survive-wi-fi-drops)).
- Remote desktop is not set up ([TB-06](#tb-06-remote-desktop-access)).

## Task summary

| ID | Title | Priority | Status | Depends on |
|---|---|---|---|---|
| [TB-01](#tb-01-restore-create-3-base-communication) | Restore Create 3 base communication | P0 | Prepared | None |
| [TB-02](#tb-02-fix-lidar-detection) | Fix lidar detection | P0 | Open | None |
| [TB-03](#tb-03-complete-the-movement-test-with-the-lidar) | Complete the movement test with the lidar | P1 | Open | TB-01, TB-02 |
| [TB-04](#tb-04-choose-a-reliable-time-strategy) | Choose a reliable time strategy | P1 | Open | TB-01 |
| [TB-05](#tb-05-security-hardening) | Security hardening | P1 | Open | None |
| [TB-06](#tb-06-remote-desktop-access) | Remote desktop access | P1 | Open | TB-04, TB-05, TB-07 |
| [TB-07](#tb-07-sd-card-backups) | SD card backups | P2 | Open | None |
| [TB-08](#tb-08-stable-addressing) | Stable addressing | P2 | Open | None |
| [TB-09](#tb-09-ros-2-from-a-laptop-over-campus-wi-fi) | ROS 2 from a laptop over campus Wi-Fi | P2 | Open | TB-01 |
| [TB-10](#tb-10-make-long-commands-survive-wi-fi-drops) | Make long commands survive Wi-Fi drops | P2 | Open | None |
| [TB-11](#tb-11-generalise-the-documentation) | Generalise the documentation | P2 | In progress | None |
| [TB-12](#tb-12-documentation-follow-ups) | Documentation follow-ups | P2 | Open | TB-11 |
| [TB-13](#tb-13-teleoperation-how-to) | Teleoperation how-to | P3 | Open | TB-01 |
| [TB-14](#tb-14-onboarding-checklist-for-new-lab-members) | Onboarding checklist for new lab members | P3 | Open | TB-05, TB-11 |

Suggested order: TB-01 and TB-02 in one session at the robot, then TB-03. Do TB-05 soon, because the factory passwords are public and the robot is reachable from the whole `Students` network. Take a backup (TB-07) before the first risky change in TB-04, TB-05 or TB-06.

---

## P0: blocking

### TB-01 Restore Create 3 base communication

**Priority:** P0 | **Status:** Prepared | **Depends on:** None

**Goal.** The Create 3 base publishes `/dock_status` and `/battery_state` to ROS again, and dock and undock work, with the HTTPS clock fix removed.

**Why it matters.** Without data from the base, nothing that moves or docks works. TB-03, TB-09 and TB-13 are blocked until this is done. The base was observed to talk to ROS only when the Pi and base clocks agree; the HTTPS clock fix broke that twice on 2026-10-03 (details in [MAINTENANCE.md](MAINTENANCE.md)).

**Steps.**

1. Put the robot on its dock and wait about 2 minutes for ROS to start. If you are also doing TB-02, reseat the lidar cable first ([TB-02](#tb-02-fix-lidar-detection) steps 2 to 4), so the software restart in step 4 below also picks up the lidar.
2. Record the current clock (read only):

   ```bash
   date -u
   timedatectl
   ```

3. Check whether the clock fix has already been removed (read only):

   ```bash
   ls /etc/systemd/system/tb4-https-time.timer
   ls /etc/systemd/system/turtlebot4.service.d/
   ```

   If both print "No such file or directory", `undo-clock` has already run: skip to step 5.
4. Remove the clock fix. It disables and deletes the `tb4-https-time` timer, service and script, deletes the `10-wait-for-clock.conf` drop-in, reloads systemd and restarts `turtlebot4.service` (the ROS software only, not a reboot). **[prepared]**

   ```bash
   cd ~
   ls -l ~/undo-clock
   sudo ./undo-clock
   ```

   It should end with `active` and `Done.` If `~/undo-clock` is missing, copy the script from this repo and run it directly. **[to verify]**

   On the laptop:

   ```bash
   scp TurtleBot/setup/undo-clock.sh ubuntu@turtlebot4.local:
   ```

   On the robot:

   ```bash
   sudo bash ~/undo-clock.sh
   ```

5. Wait about a minute, then restart the Create 3 application so the base re-syncs its clock from the Pi. The robot chimes. This is the Restart Application request that fixed the stuck base on 2026-10-03. **[verified]**

   ```bash
   curl -X POST http://192.168.186.2/api/restart-app
   ```

   The base web page (`http://192.168.186.2`, port 80) is reachable from the robot only. To use its Restart Application button from a laptop browser instead, open an SSH tunnel and browse to `http://localhost:8080`. **[to verify]**

   On the laptop:

   ```bash
   ssh -N -L 8080:192.168.186.2:80 ubuntu@turtlebot4.local
   ```

6. Check that the base is talking (each should print one message within 60 s). **[verified]** (same check as in `motion_test.sh`)

   ```bash
   timeout 60 ros2 topic echo --once /dock_status
   timeout 60 ros2 topic echo --once /battery_state
   ```

   If `ros2` is not found, run `source /etc/turtlebot4/setup.bash` first.
7. Check that the two clocks agree: the `sec:` value of the base's message stamp should be within a few seconds of the Pi's time. **[to verify]**

   ```bash
   timeout 60 ros2 topic echo --once /battery_state | grep -A 2 stamp
   date -u +%s
   ```

8. Confirm the fix is gone and ROS is running:

   ```bash
   systemctl list-timers --all | grep tb4
   systemctl is-active turtlebot4
   ```

   The first command should print nothing; the second should print `active`.
9. Reboot test (recommended; needs about 5 minutes): run `sudo reboot`, wait 2 minutes, reconnect and repeat step 6 **without** restarting the base. Record whether base data arrived on its own. If it did not, run step 5 again and record that too. The result feeds TB-04.
10. While on the robot, check whether `create3_republisher` is still crashing (it exited with code -11 twice on 2026-10-03 and restarted itself). **[to verify]**

    ```bash
    journalctl -u turtlebot4 -b --no-pager | grep -i -E "republisher|exit code"
    ```

11. Record the removal of the clock fix and the reboot-test result in [MAINTENANCE.md](MAINTENANCE.md) and in the General Tasks log.

**Acceptance criteria.**
- [ ] `/etc/systemd/system/tb4-https-time.timer`, `tb4-https-time.service`, `/usr/local/sbin/tb4-https-time` and the `10-wait-for-clock.conf` drop-in no longer exist.
- [ ] `systemctl is-active turtlebot4` prints `active`.
- [ ] `/dock_status` and `/battery_state` each print a message within 60 s.
- [ ] Undock and dock goals are accepted and succeed (checked in TB-03, or by hand with the commands in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md)).
- [ ] The reboot-test result (base data with or without a manual base restart) is recorded.
- [ ] MAINTENANCE.md and the General Tasks log are updated.

**Risks and rollback.**
- `undo-clock` restarts the ROS software. Nothing moves, but programs running at the time stop.
- After this task the Pi clock is still wrong, so `git`, `pip` and `apt` over HTTPS can fail with certificate or date errors. Copy code with VS Code or `scp` until TB-04 is done.
- Possible repeat: after a power cycle on 2026-10-03 the Pi started at its factory date (2024) while the base kept the later date. If that happens again after the reboot test, the base goes silent until step 5 is repeated. The reboot test in step 9 shows whether this still happens with the factory clock setup.
- Rollback (reinstalling the clock fix) is **not recommended**, because the fix caused the outage. Its source files stay in `~/wifi-switch/` on the robot and in [setup/](setup/) in this repo in case TB-04 reuses parts of them.

**Estimated effort:** 30 minutes, plus 10 minutes for the reboot test. Needs a person who can type the `ubuntu` password.

---

### TB-02 Fix lidar detection

**Priority:** P0 | **Status:** Open | **Depends on:** None

**Goal.** The Raspberry Pi detects the lidar on USB (`/dev/RPLIDAR` exists) and `/scan` publishes when the robot is off the dock.

**Why it matters.** The lidar is the robot's main obstacle sensor. Without it `scan_test.py` and `clearance_check.py` get no data, `motion_test.sh` skips its forward drive, and mapping or navigation cannot run.

**What is known.** Since about 19:56 on 2026-10-03 (after the reboot): the lidar spins, but `/dev/RPLIDAR` is missing, `lsusb` shows no Silicon Labs (CP210x) device whether docked or undocked, and the `rplidar_ros` log says it cannot bind to `/dev/RPLIDAR`. A full power cycle (Pi shut down, base off and on) did not help. Spinning shows the lidar gets power; the missing USB device suggests the data connection (cable, connector or the lidar's USB adapter board). Before the reboot the logs only showed the dock power saver stopping and starting the lidar; scan data was not captured then.

**Steps.**

1. Do this at the robot, ideally in the same session as TB-01. Do **not** unplug the USB-C cable between the Pi and the Create 3 base (it carries the base's network link, 192.168.186.x) or the camera cable.
2. Watch the kernel log in one terminal while you work. **[to verify]**

   ```bash
   sudo dmesg -w
   ```

3. Unplug and firmly replug the lidar's USB cable at both ends: at the lidar and at the Raspberry Pi. A detected lidar shows new lines mentioning `cp210x` and `ttyUSB` in the kernel log (exact wording to verify).
4. Check in a second terminal. **[verified]** (the checks used on 2026-10-03)

   ```bash
   lsusb | grep -i -E "silicon labs|cp210"
   ls -l /dev/RPLIDAR
   ```

5. If the device is back, restart the robot software. If TB-01 is not done yet, `sudo ./undo-clock` does this (TB-01 step 4). Otherwise:

   ```bash
   sudo systemctl restart turtlebot4
   ```

   Then repeat TB-01 step 6 to confirm the base still reports.
6. Check scan data off the dock (the robot switches the lidar off while docked). Undock, or lift the robot off the dock by hand and set it on the floor, wait about 10 s, then:

   ```bash
   cd ~/robot_code
   timeout -s INT 30 python3 scan_test.py
   python3 clearance_check.py 0.6; echo "exit code $?"
   ```

   `scan_test.py` should print distances; `clearance_check.py` should exit 0 or 1, not 2.
7. If the device is still missing: move the lidar cable to another USB port on the Pi, note which port it was in, and repeat steps 3 to 6.
8. If it is still missing: try a known-good cable of the same type, and repeat steps 3 to 6.
9. Isolate the fault: plug the lidar into a laptop. If the laptop sees no new USB device (Windows Device Manager, or `lsusb` on Linux), the lidar or its USB adapter board is faulty. If the laptop sees it, suspect the Pi side. **[to verify]**
10. If it is hardware: take photos, write down what was tried, tell the lab supervisor, and arrange a repair or replacement. Keep using the robot for work that does not need the lidar.
11. Record any port or cable change in [MAINTENANCE.md](MAINTENANCE.md) and the outcome in the General Tasks log.

**Acceptance criteria.**
- [ ] `lsusb` lists a Silicon Labs (CP210x) device.
- [ ] `/dev/RPLIDAR` exists.
- [ ] Off the dock, `scan_test.py` prints distances and `clearance_check.py` exits 0 or 1.
- [ ] The lidar is still detected after a reboot.
- [ ] Port or cable changes are recorded in MAINTENANCE.md.

**Risks and rollback.**
- Unplugging the wrong cable can cut the base link or the camera. Identify the lidar cable before unplugging (a photo of it is a TB-12 item).
- If moving to another port does not help, put the cable back in its original port.
- No software configuration is changed by this task.

**Estimated effort:** 30 to 60 minutes. A hardware replacement adds delivery time.

---

## P1: important

### TB-03 Complete the movement test with the lidar

**Priority:** P1 | **Status:** Open | **Depends on:** TB-01, TB-02

**Goal.** Run `motion_test.sh` end to end: undock, lidar clearance check, 20 cm forward drive, 360° spin, dock.

**Why it matters.** Undock, spin and dock were shown on 2026-10-03, but the forward drive was skipped because there was no lidar data. This test proves the whole chain (base, lidar, motion, docking) before anyone builds on it.

**Steps.**

1. Preconditions: TB-01 and TB-02 are Done; the robot is on its dock; at least 1 m is clear around the dock; a person stays next to the robot.
2. Make sure the robot's copy matches the repo copy of [examples/motion_test.sh](examples/motion_test.sh) (compare the files, or copy the repo version with `scp`).
3. Run it detached, so it keeps going if SSH drops while the robot roams between access points. **[verified]** for the dock command on 2026-10-03; same method.

   ```bash
   setsid nohup bash ~/robot_code/motion_test.sh > ~/robot_code/motion.log 2>&1 &
   tail -f ~/robot_code/motion.log
   ```

   Ctrl+C stops watching the log; the script keeps running.
4. Read the log. Expected lines include `Path is clear, driving forward 20 cm`, `Drive finished`, the rotate goal accepted, and `Docked at end: true`.
5. Blocked-path test: watch where the robot faces after it undocks in the first run, put a box about 0.3 m in front of that position, and run step 3 again. Expected: `Something is closer than 0.6 m in front, NOT driving`, and no forward movement.
6. If the robot ends off the dock, send it home detached (the command is in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md)).
7. Record the result in the General Tasks log and update the test note in HOW-TO-CONNECT.md.

To stop a run early (the robot finishes or cancels its current action): **[to verify]**

```bash
pkill -f motion_test.sh
pkill -f "ros2 action send_goal"
```

**Acceptance criteria.**
- [ ] The log shows `Path is clear, driving forward 20 cm` and `Drive finished`, and the robot moved about 20 cm.
- [ ] The 360° spin completes.
- [ ] The log ends with `Docked at end: true`.
- [ ] In the blocked-path run the log shows `NOT driving` and the robot does not move forward.
- [ ] Results are recorded in the General Tasks log.

**Risks and rollback.**
- Collision: speed is 0.1 m/s over 20 cm, and the drive only runs when the lidar reports a clear path. Keep the area clear and stay next to the robot.
- SSH drop during the run: handled by running detached.
- No configuration changes, so there is nothing to roll back.

**Estimated effort:** 30 minutes.

---

### TB-04 Choose a reliable time strategy

**Priority:** P1 | **Status:** Open | **Depends on:** TB-01

**Goal.** Decide, and if needed implement, a way to keep the robot's clock correct that **never steps the clock while ROS is running** and keeps the Pi and Create 3 clocks consistent.

**Why it matters.** With a wrong clock, `git`, `pip` and `apt` over HTTPS fail, and logs and recorded data carry wrong dates. A badly timed correction is worse: on 2026-10-03 the base went silent twice, once when the clock was stepped 2 years while ROS ran, and once when the Pi started in 2024 while the base had kept 2026.

**Constraints (observed on 2026-10-03).**
- Campus blocks NTP and ping to the internet. HTTPS to the internet works.
- The Raspberry Pi 4 has no battery-backed real-time clock (RTC). After a power cycle it started at its factory date.
- The base re-syncs its clock from the Pi when its application restarts (`curl -X POST http://192.168.186.2/api/restart-app`).
- Rule for any option: the Pi clock may only be stepped before `turtlebot4.service` starts, or with ROS stopped. After any change to the Pi's time, the base must be re-synced (restart its application) and `/dock_status` checked.

**Options.**

| Option | How it works | Pros | Cons |
|---|---|---|---|
| A. Leave the factory clock | No time sync. After TB-01 both clocks agree on a wrong date. | No changes to the robot. ROS works. | HTTPS tools (`git`, `pip`, `apt`) fail with certificate or date errors. Wrong dates in logs and data. |
| B. Internal NTP server from university IT | IT provides an NTP server reachable from `Students`. chrony on the Pi uses it. ROS starts only after the first sync. | Standard, automatic and accurate. After the first sync chrony corrects small drift gradually, without steps. | Depends on IT. Needs a boot ordering rule. If the server cannot be reached at boot, the "late sync" case must be handled (see steps). |
| C. Battery-backed RTC module | A small RTC board (for example DS3231 based) on the Pi's I2C pins. The kernel reads it at boot, before anything else starts. | Correct time at every boot, with no network and no IT dependency. | Hardware purchase and a modification to shared lab hardware. Must check the pins and I2C bus are free next to the TurtleBot 4 interface board. Needs a boot configuration change, an initial time set, and an occasional correction for drift. |
| D. Set the clock once at boot, strictly before ROS and the Create 3 start, then re-sync the Create 3 | An improved version of the removed HTTPS fix: one attempt at boot, no periodic timer, ROS waits for it, the base is restarted after a step. | No IT and no hardware needed. | This is close to what failed: it depends on HTTPS answering within a short window at boot. Custom boot logic to maintain. The old script used `curl -k` (certificate check off), so a spoofed reply could set any time. |
| E. Laptop as time source | A person pushes the laptop's time to the robot with ROS stopped, or the laptop runs an NTP server. | No IT and no hardware needed. | Manual, and depends on one laptop being present. Laptops on campus face the same NTP block, so their clocks can drift too. Running an NTP server changes the laptop's system and firewall settings. The laptop address changes. |

**Recommendation.**
1. Ask university IT for an internal NTP server reachable from `Students` (option B). This is the standard fix and needs no hardware.
2. Until then, stay on option A. When someone needs HTTPS tools on the robot, use the manual procedure below, which follows the rule above.
3. If IT cannot help, prefer C (it removes the root cause, the missing clock at boot) over D. Use E only as the manual one-off procedure.

**Steps.**

1. After TB-01, keep the factory clock (option A) and record the decision in [MAINTENANCE.md](MAINTENANCE.md).
2. Send IT a request: "Is there an NTP server reachable from the Students Wi-Fi (UDP port 123)? Please give its address or host name. It is for a lab robot without a battery clock." Record the ticket number in the General Tasks log.
3. When IT gives an address, test it without changing anything (prints the offset, does not set the clock). **[to verify]**

   ```bash
   sudo chronyd -Q -t 20 "server <ntp-address> iburst"
   ```

4. Before changing chrony, find out how the Pi serves time to the base, and keep that part unchanged. Look for `allow` lines covering 192.168.186.0/24 and a `local stratum` line. **[to verify]**

   ```bash
   cat /etc/chrony/chrony.conf
   ls /etc/chrony/
   sudo chronyc clients
   ```

5. Design the change (take a backup first, TB-07; try it on a spare SD card if possible). Points to cover, all **[to verify]**:
   - Add the server in its own file, for example `/etc/chrony/sources.d/campus.sources` containing `server <ntp-address> iburst`, if `chrony.conf` reads that folder (`sourcedir /etc/chrony/sources.d`). Load it with `sudo chronyc reload sources`.
   - Make `turtlebot4.service` wait for the first sync with a time limit, for example a drop-in with `ExecStartPre=-/usr/bin/chronyc waitsync 12 1`, or Ubuntu's `chrony-wait.service` if present.
   - Handle the late-sync case. If the server is unreachable at boot, ROS starts with the factory date and chrony steps the clock at its first successful update, while ROS runs. Either keep ROS waiting until sync (accepting a slow start when the server is down), or restart `turtlebot4.service` and the base application right after such a step.
6. Implement, then run the acceptance tests below. Record every file added, with undo steps, in MAINTENANCE.md.

**Manual one-off time set (interim, option E).** Use only when HTTPS tools are needed. Robot on the dock, nothing moving. **[to verify]**

On the laptop, get the current time in seconds since 1970 from a clock you trust: in Windows PowerShell `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`, on macOS or Linux `date -u +%s`.

On the robot:

```bash
sudo systemctl stop turtlebot4
sudo date -u -s "@<seconds-since-1970>"
sudo systemctl start turtlebot4
sleep 60
curl -X POST http://192.168.186.2/api/restart-app
timeout 60 ros2 topic echo --once /dock_status
```

After the next power cycle the Pi starts at its factory date again, so expect to restart the base application after that boot (pattern observed on 2026-10-03).

**Acceptance criteria.**
- [ ] The chosen option, the date and the reason are recorded here and in MAINTENANCE.md.
- [ ] If a sync method is implemented, over 3 cold starts (Pi and base powered off and on) and 3 reboots:
  - [ ] the Pi clock is within 2 s of a trusted reference after boot;
  - [ ] no clock step is logged after `turtlebot4.service` started (compare `journalctl -u chrony -b` with `systemctl show turtlebot4 -p ActiveEnterTimestamp`) **[to verify]**;
  - [ ] `/dock_status` arrives within 5 minutes of power-on without a manual base restart;
  - [ ] `curl -sSI https://github.com | head -1` succeeds with certificate checks on;
  - [ ] `sudo apt update` shows no "not valid yet" or certificate errors.

**Risks and rollback.**
- Any automatic clock step while ROS runs can silence the base again. Remedy: restart the base application (TB-01 step 5).
- Changes touch the boot path. Rollback for option B: delete the added source file and drop-in, run `sudo systemctl daemon-reload` and `sudo systemctl restart chrony`, then restart `turtlebot4.service` and the base application.
- Option C rollback: remove the overlay line from the boot configuration and the module, then reboot.

**Estimated effort:** decision and IT request 1 hour (IT response time unknown); option B implementation and boot tests 2 to 4 hours; option C 2 to 3 hours plus purchase.

---

### TB-05 Security hardening

**Priority:** P1 | **Status:** Open | **Depends on:** None

**Goal.** No factory passwords remain, every authorized SSH key has a known owner, and (optionally) SSH accepts keys only.

**Why it matters.** The `ubuntu` account and the `Turtlebot4` access point probably still use the factory default passwords, which are published in the public TurtleBot 4 manual. Devices on `Students` can reach each other, so anyone on that network can try SSH on the robot. A lab SSH public key from one person's workstation is authorized on the robot; its ownership should be recorded and reviewed.

**Steps.**

1. Agree with the lab supervisor who holds the new passwords. Store them in the lab's password manager (for example entries "TurtleBot 4: ubuntu account" and "TurtleBot 4: access point"). Never put them in this repo, in chat messages or in the log.
2. Change the `ubuntu` password (asks for the current one, then the new one twice):

   ```bash
   passwd
   ```

   `sudo` and Wi-Fi changes then use the new password. The saved `Students` Wi-Fi profile and SSH keys are not affected.
3. Review the authorized SSH keys. This prints one line per key with its fingerprint and comment:

   ```bash
   ssh-keygen -lf ~/.ssh/authorized_keys
   ```

   For each key, record its owner and fingerprint in MAINTENANCE.md (fingerprints are not secret). Each person should use their own key, with a comment naming them. Before removing a key, keep a copy (`cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak-<date>`), keep your current session open, and test a new login from a second terminal.
4. Change the access point password. **[to verify]**
   - The access point is the NetworkManager connection `netplan-wlan0-Turtlebot4`, defined in `/etc/netplan/50-wifis.yaml`. Check `ls /etc/netplan/` for other files first.
   - The TurtleBot 4 setup tool (`turtlebot4-setup`) is not on PATH in this image. Check the official manual for the supported way on Jazzy. Otherwise back up the file outside `/etc/netplan` (`sudo cp /etc/netplan/50-wifis.yaml /root/50-wifis.yaml.before-TB05`), edit the password, and validate with `sudo netplan generate`. Do not run `sudo netplan apply` over Wi-Fi: it can drop your connection.
   - The new password takes effect when the access point next starts. Test it with physical access to the robot: the access point only runs when `Students` is unavailable, so the test means forcing a fallback (for example `sudo nmcli connection down Students`, which ends your Wi-Fi session), then joining `Turtlebot4` from a laptop with the new password. A reboot brings the robot back on `Students`.
   - Laptops with a saved `Turtlebot4` profile must forget it and rejoin with the new password.
5. Optional, once every user has a key: disable SSH password login. Create `/etc/ssh/sshd_config.d/10-no-password.conf` containing the lines below. sshd uses the first value it reads, and reads that folder in name order, so `10-` comes before an existing `50-cloud-init.conf`. **[to verify]**

   ```text
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   ```

   Then check the syntax, reload, and confirm the effective values:

   ```bash
   sudo sshd -t
   sudo systemctl reload ssh
   sudo sshd -T | grep -i -E "passwordauthentication|kbdinteractiveauthentication"
   ```

   Keep your current session open. From a second terminal, confirm a key login works and a password-only login is refused.

   On the laptop:

   ```bash
   ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password ubuntu@turtlebot4.local
   ```

6. Consider the ROS domain: anyone on `Students` running ROS 2 on the same domain ID could see, and possibly command, the robot if discovery works across the network (see TB-09). A non-default `ROS_DOMAIN_ID` must be set on both the Pi and the Create 3 base. Check the official manual before changing it. **[to verify]**
7. Record what changed (never the secrets) in MAINTENANCE.md, and tell lab members where to get the new passwords.

**Acceptance criteria.**
- [ ] The factory `ubuntu` password no longer works; the new one is in the lab password manager.
- [ ] The access point password is changed, stored in the password manager, and a fallback connection with it has been tested.
- [ ] Every line in `~/.ssh/authorized_keys` has a known owner, recorded in MAINTENANCE.md.
- [ ] If step 5 was done: `sshd -T` shows `passwordauthentication no`, password-only login is refused, and key login works.
- [ ] No credentials appear in the repo or in the log.

**Risks and rollback.**
- Lockout. Keep a session open while changing SSH settings. Rollback for step 5: delete the drop-in and run `sudo systemctl reload ssh`.
- A wrong access point configuration only matters when `Students` is unavailable; a reboot returns the robot to `Students`. Rollback: restore the backed-up `50-wifis.yaml` and run `sudo netplan generate`.
- Removed keys can be restored from the `.bak` copy.
- Passwords can be changed again at any time.

**Estimated effort:** 1 to 2 hours, plus coordination with lab members.

---

### TB-06 Remote desktop access

**Priority:** P1 | **Status:** Open | **Depends on:** TB-04, TB-05, TB-07

**Goal.** Give lab members a graphical way to work with the robot, without slowing down ROS on the Raspberry Pi.

**Why it matters.** The robot runs Ubuntu Server with no desktop. Lab members want a remote desktop. The Pi already runs the ROS bringup, and the camera container alone uses about one CPU core, so every extra process competes with the robot's own software.

**Options.** Resource figures are rough estimates; measure them on this robot before deciding.

| Option | Robot cost (rough) | Pros | Cons | Connect from Windows | Connect from macOS |
|---|---|---|---|---|---|
| (a) xrdp with a lightweight desktop (XFCE) | Several hundred MB to about 1 GB of disk; roughly 200 to 500 MB of RAM per open session; CPU mostly when the screen changes | Full desktop; Windows has a built-in client; sessions persist between connections | Uses RAM and CPU the robot needs; graphical tools such as RViz2 would render in software on the Pi; port 3389 exposes a password login to the network unless limited to an SSH tunnel; more packages to maintain | Remote Desktop Connection (built in) to the robot on port 3389, or through an SSH tunnel | Microsoft's Windows App (Remote Desktop client) |
| (b) VNC server (for example TigerVNC) with a lightweight desktop | Similar to (a) | Can listen on the robot only and be reached through an SSH tunnel; easy to start and stop by hand | Same resource cost as (a); a separate VNC password to manage; Windows needs a VNC viewer installed | TigerVNC Viewer or another VNC viewer, through `ssh -L 5901:localhost:5901` | Built-in Screen Sharing (`vnc://localhost:5901`) through the tunnel |
| (c) Keep the robot headless; run visual tools on the laptop | One `foxglove_bridge` process, started on demand; its cost grows with the topics viewed (camera images cost the most) | Rendering happens on the laptop; Foxglove uses one WebSocket port, which avoids ROS 2 discovery problems on campus; nothing runs at boot | Not a full desktop; RViz2 needs ROS 2 Jazzy on the laptop and working discovery (TB-09) | Foxglove app or web app; VS Code Remote-SSH for editing | Same |

**Recommendation.** Use (c) for visualisation, plus VS Code Remote-SSH (already working) for editing and terminals. Add (a) only if a full desktop is really required: install it with `--no-install-recommends`, start it on demand rather than at boot, limit it to an SSH tunnel, and only after TB-05, so the login is not protected by a published factory password.

**Steps for (c), the recommended option.** All **[to verify]**.

1. Measure the baseline with ROS and the camera running, and record it in MAINTENANCE.md:

   ```bash
   free -h
   uptime
   top -b -n 1 | head -n 15
   df -h /
   ```

2. Check whether `foxglove_bridge` is already installed:

   ```bash
   ros2 pkg prefix foxglove_bridge
   ```

3. If it is not, install it. `apt` needs a correct clock (TB-04, or the manual time set), and a backup should exist (TB-07). Preview first and check that no ROS packages are upgraded or removed:

   ```bash
   sudo apt-get -s install ros-jazzy-foxglove-bridge
   sudo apt-get install ros-jazzy-foxglove-bridge
   ```

4. Start it on demand, listening on the robot only (in `tmux` or detached, see TB-10):

   ```bash
   ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:=127.0.0.1 port:=8765
   ```

5. Connect from the laptop through an SSH tunnel, then in Foxglove open a "Foxglove WebSocket" connection to `ws://localhost:8765`. Add a 3D panel with `/scan` and `/tf`. The Foxglove desktop app asks for a free account; the open-source fork Lichtblick is an alternative.

   On the laptop:

   ```bash
   ssh -N -L 8765:localhost:8765 ubuntu@turtlebot4.local
   ```

6. Stop the bridge with Ctrl+C (or `pkill -f foxglove_bridge`) when done.
7. Document the procedure in HOW-TO-CONNECT.md.

**Outline for (a), only if a full desktop is required.** Verify on a spare SD card or after a backup (TB-07) first. All **[to verify]**.

1. Preview, review the list (no ROS package upgrades or removals), then install:

   ```bash
   sudo apt-get -s install --no-install-recommends xrdp xorgxrdp xfce4 xfce4-terminal dbus-x11
   sudo apt-get install --no-install-recommends xrdp xorgxrdp xfce4 xfce4-terminal dbus-x11
   ```

2. Configure the session and the certificate group:

   ```bash
   echo xfce4-session > ~/.xsession
   sudo adduser xrdp ssl-cert
   ```

3. Limit xrdp to the robot itself: back up `/etc/xrdp/xrdp.ini` and set `port=tcp://.:3389` (listen on 127.0.0.1 only; check the syntax for the installed xrdp version).
4. Do not start it at boot. Start it only when needed, and stop it afterwards:

   ```bash
   sudo systemctl disable --now xrdp xrdp-sesman
   sudo systemctl start xrdp
   sudo systemctl stop xrdp xrdp-sesman
   ```

5. Connect through a tunnel, then point Remote Desktop Connection (Windows) or Windows App (macOS) at `localhost:13389` and log in as `ubuntu`.

   On the laptop:

   ```bash
   ssh -N -L 13389:localhost:3389 ubuntu@turtlebot4.local
   ```

6. With a session open, repeat the baseline measurements and compare.

Rollback for (a): stop and disable xrdp; purge exactly the packages listed for that install in `/var/log/apt/history.log` (`sudo apt-get purge <packages>`); preview `sudo apt-get -s autoremove --purge` before running it; delete `~/.xsession`. Rollback for (c): stop the bridge; if it was installed by this task, `sudo apt-get remove ros-jazzy-foxglove-bridge`.

**Acceptance criteria.**
- [ ] The chosen approach and the baseline measurements are recorded in MAINTENANCE.md.
- [ ] (c): from a laptop on `Students`, Foxglove shows live `/scan` (off the dock) and `/tf`; `ss -ltnp | grep 8765` shows the bridge listening on 127.0.0.1 only; nothing starts at boot.
- [ ] (a), if installed: a desktop session opens from Windows and from macOS through the tunnel; `systemctl is-enabled xrdp` prints `disabled`; installed packages are listed in MAINTENANCE.md.
- [ ] While in use, `/dock_status` still publishes, `ros2 topic hz /scan` matches the baseline, and `free -h` shows at least 500 MB available.
- [ ] HOW-TO-CONNECT.md explains how to connect.

**Risks and rollback.**
- Resource pressure can slow ROS or the camera. Stop the desktop or bridge first if the robot misbehaves.
- An open port 3389 or 8765 is reachable by everyone on `Students`. Keep them on 127.0.0.1 behind SSH. `foxglove_bridge` can let clients publish topics, including movement commands.
- Installing packages can upgrade shared libraries. Always preview with `-s` and keep a backup.
- Rollback as listed above.

**Estimated effort:** evaluation 1 to 2 hours; (c) 1 to 2 hours; (a) 2 to 4 hours plus a backup.

---

## P2: improvements

### TB-07 SD card backups

**Priority:** P2 | **Status:** Open | **Depends on:** None

**Goal.** A full image of the robot's SD card exists, with its location and checksum recorded, before any risky change.

**Why it matters.** All configuration lives on one SD card. A failed change, a corrupt card or a bad boot configuration could otherwise mean rebuilding the robot from the factory image and redoing every change in MAINTENANCE.md.

**Steps.** All **[to verify]** on this robot.

1. Choose where images are kept: lab storage with restricted access. Never in this repo or any public place, because the image contains the `Students` Wi-Fi key, SSH keys and any other secrets on the robot.
2. Shut down the Pi properly and power off the robot, following the "powering off" steps in the [official TurtleBot 4 user manual](https://turtlebot.github.io/turtlebot4-user-manual/).
3. Remove the microSD card from the Raspberry Pi (see the manual for access; a photo of the steps is a TB-12 item).
4. Read the whole card into an image file on a computer:
   - Windows: an imaging tool with a "Read" function, such as Win32 Disk Imager.
   - Linux: `sudo dd if=/dev/<card-device> of=tb4-<date>.img bs=4M status=progress`. Check the device name twice: `dd` overwrites whatever `of=` points to.
5. Record a checksum: `sha256sum tb4-<date>.img` (Linux or macOS) or `Get-FileHash tb4-<date>.img` (Windows PowerShell). Compress the image if space is short.
6. Put the card back, power on, and check that the robot returns on `Students` and `/dock_status` publishes.
7. Record in MAINTENANCE.md: date, file name, size, checksum, storage location, and what state it captures.
8. Optional: write the image to a spare card and boot from it, to prove the backup restores. The spare card can also be used to try TB-04 and TB-06 changes.

The factory image from the official manual remains the last-resort restore, but it loses all lab configuration.

**Acceptance criteria.**
- [ ] An image and its checksum exist in restricted lab storage.
- [ ] The location and checksum are recorded in MAINTENANCE.md.
- [ ] The robot works normally after the card is reinserted.
- [ ] Optional: a restore to a spare card has booted successfully.

**Risks and rollback.**
- Removing the card while the Pi runs can corrupt it: always shut down first.
- Choosing the wrong device in `dd` can destroy a disk.
- Nothing on the robot changes.

**Estimated effort:** 1 to 2 hours, mostly waiting for the copy.

---

### TB-08 Stable addressing

**Priority:** P2 | **Status:** Open | **Depends on:** None

**Goal.** Lab members can always find the robot: a fixed address or host name from university IT, or a documented reliance on `turtlebot4.local` and the robot's display.

**Why it matters.** The robot's address comes from DHCP (10.87.10.205/18 was observed) and can change. `turtlebot4.local` (mDNS) works on `Students` and the display shows the current address, but some tools and laptops resolve `.local` names poorly.

**Steps.**

1. Read the Wi-Fi hardware address, and check that the `Students` profile does not use a random one (an empty value, `preserve` or `permanent` means the real address is used). **[to verify]**

   ```bash
   cat /sys/class/net/wlan0/address
   nmcli -g 802-11-wireless.cloned-mac-address connection show Students
   ```

2. Ask university IT for a DHCP reservation for that hardware address on `Students`, and if possible a host name. Say it is a lab robot and name the responsible professor. Record the ticket in the General Tasks log.
3. If granted: confirm the address and name stay the same across two reboots on different days, then document them in HOW-TO-CONNECT.md. A private campus address is not secret, but the host name is enough for the public docs.
4. If refused: document `turtlebot4.local` and the display as the official way to find the robot (already the case), and close the task.

**Acceptance criteria.**
- [ ] Either the same address or host name works after two reboots on different days, or the decision to rely on `turtlebot4.local` is recorded.
- [ ] HOW-TO-CONNECT.md describes the method.

**Risks and rollback.** No change on the robot. Rollback: ask IT to remove the reservation.

**Estimated effort:** 30 minutes, plus IT response time.

---

### TB-09 ROS 2 from a laptop over campus Wi-Fi

**Priority:** P2 | **Status:** Open | **Depends on:** TB-01

**Goal.** A laptop with ROS 2 Jazzy on `Students` sees the robot's topics, so RViz2 and laptop-side nodes can be used.

**Why it matters.** Running heavy tools on the laptop keeps load off the Pi. Campus Wi-Fi may block the multicast that ROS 2 discovery uses. mDNS works on `Students`, which shows some multicast passes, but ROS 2 discovery uses different multicast groups, so it must be tested.

**Steps.** All **[to verify]**.

1. Laptop: ROS 2 Jazzy on Ubuntu 24.04 (native, or a virtual machine with bridged networking). Windows with WSL2 can work but discovery over Wi-Fi is harder.
2. On the robot, read its ROS settings (read only). Note `RMW_IMPLEMENTATION`, `ROS_DOMAIN_ID` and any discovery variables:

   ```bash
   cat /etc/turtlebot4/setup.bash
   ```

3. Test plain discovery from the laptop:

   ```bash
   source /opt/ros/jazzy/setup.bash
   export ROS_DOMAIN_ID=<robot value>
   export RMW_IMPLEMENTATION=<robot value>
   ros2 daemon stop
   ros2 topic list
   ```

4. If no robot topics appear, try unicast from the laptop side only (no change on the robot), then repeat step 3:

   ```bash
   export ROS_STATIC_PEERS=<robot-address>
   ```

5. Only if that fails: consider a Fast DDS discovery server on the robot. This changes how every node on the robot finds the others, including the link to the Create 3 base. Check the official manual for the Jazzy setup first, take a backup (TB-07), record the change in MAINTENANCE.md, and re-check `/dock_status` afterwards.
6. Avoid streaming raw camera images over Wi-Fi; use compressed topics.
7. Document the working laptop setup in HOW-TO-CONNECT.md. For visualisation only, Foxglove (TB-06 option c) avoids ROS 2 discovery entirely.

**Acceptance criteria.**
- [ ] `ros2 topic list` on the laptop shows the robot's topics, including `/dock_status` and `/tf`.
- [ ] `ros2 topic echo --once /battery_state` works from the laptop.
- [ ] RViz2 on the laptop shows `/scan` (needs TB-02).
- [ ] Robot-side `/dock_status` is unaffected.
- [ ] The setup is documented.

**Risks and rollback.**
- Steps 3 and 4 change only the laptop's shell environment.
- A discovery server on the robot (step 5) can break base communication. Rollback: restore the previous settings, restart `turtlebot4.service`, restart the base application (TB-01 step 5).
- Other students' ROS 2 machines on the same domain could interfere; see TB-05 step 6.

**Estimated effort:** 1 to 2 hours for steps 1 to 4; half a day if a discovery server is needed.

---

### TB-10 Make long commands survive Wi-Fi drops

**Priority:** P2 | **Status:** Open | **Depends on:** None

**Goal.** Commands that take a while, especially motion, finish even when the laptop's SSH session drops, and the cause of the drops is understood.

**Why it matters.** While the robot moves it can briefly leave the Wi-Fi as it switches between campus access points. When SSH drops, a running `ros2 action send_goal` is cancelled. This happened on 2026-10-03 just as docking started. Running scripts detached (`setsid nohup`) is the documented workaround.

**Steps.**

1. Keep using detached runs for motion (see [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md)).
2. Check whether `tmux` is installed, and document a short workflow for interactive work. **[to verify]**

   ```bash
   command -v tmux
   tmux new -s robot
   tmux attach -t robot
   ```

   Inside tmux, Ctrl+B then D detaches; the session keeps running.
3. Measure roaming during a motion test (read only), in a detached or tmux session, and note access point changes and drops. **[to verify]**

   ```bash
   journalctl -u NetworkManager -f
   ```

4. If drops are frequent, discuss options with IT (for example coverage in the lab). Do not lock the robot to one access point: it would lose Wi-Fi whenever that access point is down.
5. Record findings in the General Tasks log.

**Acceptance criteria.**
- [ ] The detached and tmux workflows are documented in HOW-TO-CONNECT.md.
- [ ] A motion test during which SSH dropped still ended with the robot docked.
- [ ] Roaming observations are recorded.

**Risks and rollback.** No configuration change unless tmux has to be installed (rollback: `sudo apt-get remove tmux`).

**Estimated effort:** 1 hour.

---

### TB-11 Generalise the documentation

**Priority:** P2 | **Status:** In progress (2026-10-03) | **Depends on:** None

**Goal.** Documentation that any lab member can follow on any laptop, with the configuration and change history kept separately.

**Why it matters.** The first guide was written for one person's laptop (its shortcuts, SSH aliases and second Wi-Fi adapter).

**Steps.**
1. Rewrite [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) as a general user guide, and add [README.md](README.md) as the entry point.
2. Move the configuration record, the change register with undo steps, the incident report on the clock and the Create 3 base, and the known issues to [MAINTENANCE.md](MAINTENANCE.md).
3. Keep this roadmap for open work.

**Acceptance criteria.**
- [ ] A new lab member can connect and run `hello_robot.py` using only README.md and HOW-TO-CONNECT.md.
- [ ] No step in the user guide depends on one person's workstation.
- [ ] Every change made to the robot so far appears in MAINTENANCE.md with verify and undo steps.
- [ ] Links between the four documents work.

**Risks and rollback.** Documentation only; Git history keeps earlier versions.

**Estimated effort:** in progress; about half a day in total.

---

### TB-12 Documentation follow-ups

**Priority:** P2 | **Status:** Open | **Depends on:** TB-11

**Goal.** Keep the documentation accurate and easy to follow over time.

**Why it matters.** Several open tasks need someone to find a cable or button quickly, and the docs will drift as the robot changes and people leave.

**Steps.**
1. Add photos (in a folder such as `TurtleBot/images/`) of: the robot's display and buttons; the lidar USB cable at both ends and the Pi's USB ports; the USB-C link to the base (to avoid unplugging it); access to the SD card. Check that no password label, screen with secrets, or person is visible.
2. Keep MAINTENANCE.md current after every change, and this roadmap after every task.
3. Correct stale statements when found. For example, the "next steps" plan at the end of the General Tasks log predates the Wi-Fi switch.
4. When the original author leaves: remove workstation-specific notes (desktop shortcuts, second Wi-Fi adapter, their SSH aliases), and remove their public key from the robot (see TB-05). Record both in MAINTENANCE.md.
5. Make the example programs neutral where they include a person's name (for example the message in `hello_robot.py`).

**Acceptance criteria.**
- [ ] The photos are in the repo and linked from HOW-TO-CONNECT.md or MAINTENANCE.md.
- [ ] MAINTENANCE.md matches the robot (spot-check three entries).
- [ ] No workstation-specific notes remain once the original author has left.

**Risks and rollback.** Documentation only, apart from the key removal in step 4 (reversible by re-adding the key).

**Estimated effort:** 2 hours, then a few minutes per change.

---

## P3: nice to have

### TB-13 Teleoperation how-to

**Priority:** P3 | **Status:** Open | **Depends on:** TB-01

**Goal.** A short, tested guide to driving the robot by keyboard.

**Why it matters.** Manual driving is the quickest way to test motion, reposition the robot and check networking. On this robot `/cmd_vel` takes `geometry_msgs/msg/TwistStamped`, so the usual keyboard teleop command needs an extra option.

**Steps.** All **[to verify]**.

1. Check the package is installed:

   ```bash
   ros2 pkg prefix teleop_twist_keyboard
   ```

2. Run it in a robot terminal with stamped messages:

   ```bash
   ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -p stamped:=true
   ```

   Alternative: publish unstamped messages to `/cmd_vel_unstamped`, which also exists on this robot, with `--ros-args -r cmd_vel:=cmd_vel_unstamped`.
3. Test at low speed in a clear area, starting off the dock.
4. Check what happens if the SSH session drops while a key is held: the robot must stop. Record the result.
5. Write the guide as a section of HOW-TO-CONNECT.md.

**Acceptance criteria.**
- [ ] The robot drives forward, backward and turns by keyboard.
- [ ] The behaviour on an SSH drop is tested and documented.
- [ ] The guide is in HOW-TO-CONNECT.md.

**Risks and rollback.** Collision risk at speed: keep the speed low and stay near the robot. No configuration change.

**Estimated effort:** 1 hour.

---

### TB-14 Onboarding checklist for new lab members

**Priority:** P3 | **Status:** Open | **Depends on:** TB-05, TB-11

**Goal.** A one-page checklist that takes a new lab member from nothing to running their first program safely.

**Why it matters.** It saves the maintainer repeated explanations, and makes sure every user has their own SSH key and knows the safety and change-recording rules.

**Steps.**
1. Draft the checklist as a section of [README.md](README.md). Suggested items: read README.md and HOW-TO-CONNECT.md; get access to the password manager entries; create a personal SSH key and send the public key to the maintainer; join `Students`; connect with VS Code Remote-SSH; run `hello_robot.py` on the dock; learn to dock, undock and shut down safely; learn to run motion scripts detached; know to record changes in MAINTENANCE.md and the General Tasks log.
2. Have the next new lab member follow it, and fix what was unclear.

**Acceptance criteria.**
- [ ] The checklist is in README.md.
- [ ] One new member has completed it without extra help, or their feedback has been applied.

**Risks and rollback.** Documentation only.

**Estimated effort:** 1 to 2 hours.

---

## Definition of done for any change

A change to the robot, a laptop setup used by the lab, or a shared account is done only when all of these are true:

- [ ] **Tested:** it was tried, ideally on a spare SD card or after a backup if it is risky (TB-07).
- [ ] **Verified:** the task's acceptance criteria are met on the robot, and the robot still works: it is reachable over SSH, and `/dock_status` publishes.
- [ ] **Recorded:** [MAINTENANCE.md](MAINTENANCE.md) lists what changed, where, why, how to verify it and how to undo it.
- [ ] **Logged:** a dated entry is in the [General Tasks log](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt), including what failed.
- [ ] **No credentials committed:** no passwords, Wi-Fi keys, private keys or tokens in the repo. Review the diff before every commit.
- [ ] **Docs updated:** HOW-TO-CONNECT.md, README.md and this roadmap reflect the change; task status and date are set.
- [ ] **Minimal:** only what the task needed was changed.

## Related documents

| Document | Contents |
|---|---|
| [README.md](README.md) | Entry point for the TurtleBot 4 folder |
| [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) | User guide: connecting, running code, troubleshooting |
| [MAINTENANCE.md](MAINTENANCE.md) | Configuration record, change register with undo steps, incident report, known issues |
| [General Tasks log](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt) | Dated step-by-step log of the setup, including what failed |
| [setup/](setup/) | Scripts used to configure the robot, including `undo-clock.sh` |
| [examples/](examples/) | Example programs and `motion_test.sh` |
| [turtlebot4-field-guide.html](turtlebot4-field-guide.html) | Background on the platform, ROS 2 concepts and commands |
| [Official TurtleBot 4 user manual](https://turtlebot.github.io/turtlebot4-user-manual/) | Vendor documentation, including powering off and setup |
