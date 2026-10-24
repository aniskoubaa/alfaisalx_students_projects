# TurtleBot 4 roadmap

Plan of work for the lab's TurtleBot 4.

**Last updated:** 2026-10-24, late evening (10 supervised motion starts with the start-up check: all completed, short start pauses remain; TB-25 follow-up joins done, Pi-local ROS silence fixed as R18, 240 automatic package upgrades noted in TB-28). Earlier the same evening (home Wi-Fi network added as R16; supervised motion through Studio over Wi-Fi; long `/odom` stalls seen at idle, new hypothesis in TB-25; new task TB-28; TB-17 proposal added). Earlier on 2026-10-24 (Wi-Fi power-save fix applied as R14, effect not verified; `/odom` stall cause located in the base; new tasks TB-24 to TB-27). Previous update: 2026-10-10 (state as of 2026-10-10: no robot change since 2026-10-04; robot last reached briefly on 2026-10-05). Previous update: 2026-10-04 (robot state as of 2026-10-04, about 12:30 robot time)

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
7. New work gets the next free ID (TB-15, TB-16, and so on; on 2026-10-24 the last ID was TB-27; updated in the evening: the last ID is now TB-28, so the next is TB-29). Do not reuse or renumber IDs.

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

## State on 2026-10-24

The robot was reached over an Ethernet cable and ran its own `Turtlebot4` hotspot (`Students` out of range). Details: [MAINTENANCE.md](MAINTENANCE.md#state-on-2026-10-24) and the [step log](../General%20Tasks/TurtleBot4%20-%20Ethernet%2C%20Wi-Fi%20power%20save%20and%20odometry%20timing.txt). Times are laptop time (UTC+3) or seconds since the start of a recording; the robot clock was about two years wrong.

| Item | State on 2026-10-24 | Tasks |
|---|---|---|
| Robot Wi-Fi | **Fix applied, effect not verified.** Power saving was on (global NetworkManager setting; kernel log). It was switched off in the `Students` profile as R14. `nmcli connection up Students` was not run; it takes effect at the next join. The logs show no disconnects on the symptom days, which fits power saving. Needs the robot on campus | [TB-20](#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving), [TB-26](#tb-26-measure-students-signal-strength-on-campus) (new) |
| Wired access | Ethernet works: the robot is at `192.168.185.3` (no DHCP on the cable); IPv6 link-local with key login verified. A fixed address on the computer is the proposed regular method, not yet tested | [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed), [TB-09](#tb-09-ros-2-from-a-laptop-over-campus-wi-fi) |
| `/odom` pauses | Measured with the timing recorder: stalls of 1.39 s (undock) and 3.16 s (2.0 s into a drive) in **all base topics**, header stamps stop too, ping RTT to the base rises, Pi CPU at most 61 %, not Wi-Fi. The cause is in the base, triggered by motion start; why is still open. Evening update: see the section below | [TB-15](#tb-15-characterise-the-odom-pauses-at-motion-start), [TB-25](#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving) (new) |
| Lidar | The motor did not restart after undocking; started by hand with `/start_motor` | [TB-24](#tb-24-lidar-motor-does-not-restart-after-undocking) (new) |
| Supervised motion test | Undock, one `motion_shapes.py back_and_forth` attempt (aborted by the 3.16 s stall after a few cm) and dock, with the timing recorder running on the robot | [TB-23](#tb-23-first-robot-run-of-the-new-programs-and-the-connect-tool), [TB-16](#tb-16-motion-program-test-campaign-and-demo-shapes) |
| Clock | Wrong (28 October 2024); no internet over the cable or hotspot so the HTTPS fix cannot run. Not touched | [TB-17](#tb-17-decide-whether-to-keep-or-remove-the-clock-fix), [TB-04](#tb-04-choose-a-reliable-time-strategy) |
| Lab control app | **Built:** [TurtleBot Studio](tools/studio/README.md). Tested over the cable on 2026-10-24 with the robot docked, no motion (discover, connect, status, topics, files, run and stop, health check, E-STOP on and off). Not yet tested: Undock/Dock and motion through Studio, macOS, Linux, Wi-Fi, the window-opening buttons | [TB-27](#tb-27-desktop-control-app-for-connecting-file-sync-and-running-programs) (new) |

Status unchanged since 2026-10-10: TB-01, TB-03, TB-04, TB-05, TB-06, TB-07, TB-13, TB-14, TB-17, TB-18, TB-21, TB-22.

### Update 2026-10-24, evening: home Wi-Fi and supervised motion through Studio

The robot joined a home Wi-Fi network (MAINTENANCE.md R16), the cable was unplugged and Studio ran over Wi-Fi only. Times are laptop time (UTC+3) unless marked robot time (7 hours earlier). Details: [MAINTENANCE.md runtime table](MAINTENANCE.md#restarts-and-service-interruptions) and the [step log](../General%20Tasks/TurtleBot4%20-%20Ethernet%2C%20Wi-Fi%20power%20save%20and%20odometry%20timing.txt).

| Item | State on the evening of 2026-10-24 | Tasks |
|---|---|---|
| Robot Wi-Fi | The robot works on a saved home network (`TP-LINK_Extender_5GHz`, 5 GHz, -60 dBm, no errors or drops) and `turtlebot4.local` resolves there. This says nothing about `Students` on campus: the TB-20 effect is still not verified. The robot returns to the lab on 2026-10-25 | [TB-20](#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving), [TB-26](#tb-26-measure-students-signal-strength-on-campus) |
| `/odom` pauses | Idle stalls of 7.51 s and 10.97 s while docked, and 7.81 s in a spin that aborted; Wi-Fi not involved; a Create 3 application restart did not fix them. New hypothesis (not proven): they follow new ROS 2 participants joining | [TB-25](#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving), [TB-15](#tb-15-characterise-the-odom-pauses-at-motion-start) |
| Lidar | Running after the undock: the TB-24 fault did not reproduce this time (one undock only) | [TB-24](#tb-24-lidar-motor-does-not-restart-after-undocking) |
| Supervised motion test | Through Studio: undock, spin (aborted by a stall), spin (done, 359 degrees), circle (the 17.3 cm closure is invalid), dock; 5 motion starts in all | [TB-27](#tb-27-desktop-control-app-for-connecting-file-sync-and-running-programs), [TB-25](#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving) |
| Clock | Correct on the Pi since the robot got internet (chrony stepped it by about 1.99 years while ROS ran). The base clock was re-synchronised by hand at 22:20 and 22:21 robot time. Without internet it will be wrong again | [TB-17](#tb-17-decide-whether-to-keep-or-remove-the-clock-fix) (proposal added), [TB-04](#tb-04-choose-a-reliable-time-strategy) |
| Ubuntu updates | With internet the robot started downloading Ubuntu updates by itself (one core at 100 % for more than 45 minutes). Not stopped | [TB-28](#tb-28-decide-whether-the-robot-installs-ubuntu-updates-by-itself) (new) |
| Lab control app | Add to the robot, Wi-Fi connection, Undock and Dock, and two motion templates are now verified on the real robot. Four bugs fixed in the code. Gaps remain (listed in TB-27) | [TB-27](#tb-27-desktop-control-app-for-connecting-file-sync-and-running-programs) |

## State on 2026-10-10

No change was made to the robot after 2026-10-04 (details in [MAINTENANCE.md](MAINTENANCE.md#state-on-2026-10-10)). Times: 2026-10-04 entries are robot time (EDT), 2026-10-05 entries are laptop time (UTC+3). Evidence: [docs/network-and-connectivity.html](docs/network-and-connectivity.html) and the [network log](../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt).

| Item | State on 2026-10-10 | Tasks |
|---|---|---|
| Robot Wi-Fi (the main problem this week) | **Open.** On 2026-10-04 (about 15:42) the robot answered SSH once after being switched on, then dropped off for at least 25 minutes. On 2026-10-05 it answered for about a minute, then only in short windows (about 10 to 40 s). Likely cause: Wi-Fi power saving on the Pi (diagnosis, not confirmed). Fix proposed, **not applied** | [TB-20](#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving) (new, P0) |
| `turtlebot4.local` | Failed to resolve intermittently on the campus Wi-Fi on 2026-10-04. Use the address on the display | [TB-08](#tb-08-stable-addressing), TB-20 |
| Lab router | Linksys WRT54G set up on 2026-10-05 (`192.168.1.1`, LAN `192.168.1.x`). **The robot has not been moved to it.** Admin login was still the factory default when it was set up; credentials changed on 2026-10-10 (reported by the lab RA) | [TB-21](#tb-21-decide-the-robots-network-students-or-the-lab-router), [TB-22](#tb-22-secure-the-lab-router) (new) |
| New example programs | Written 2026-10-04 and tested offline (101 logic checks, 38 simulated runs, rerun 2026-10-10). Not copied to the robot (R12 not applied) | [TB-23](#tb-23-first-robot-run-of-the-new-programs-and-the-connect-tool) (new) |
| `health_check.py` | Written 2026-10-04, tested offline; first robot run pending | [TB-19](#tb-19-read-only-health-check-script) (now Prepared), TB-23 |
| Connect tool | `TurtleBotConnect.exe` (Windows) and `connect-turtlebot.sh` (macOS, Linux) in [tools/connect/](tools/connect/README.md). Work in progress was committed on 2026-10-05 (7007f51; its exe is v1.0.0 and does not match its source); the final design is v1.1.0. Not yet used with the real robot | TB-23 |
| Motion programs | No runs since 2026-10-04. On 2026-10-04 square, rotate, back-and-forth and triangle completed; the figure eight aborted on a 2.0 s odometry gap with the robot held still ([test results](docs/test-results.html)) | [TB-16](#tb-16-motion-program-test-campaign-and-demo-shapes), [TB-03](#tb-03-complete-the-movement-test-with-the-lidar) |
| Way of working | An hour-long unattended test campaign run by an AI subagent on 2026-10-04 was blocked by the AI tool's safety guard. Motion tests are run supervised, in short batches, with a person next to the robot | TB-16 |
| `/odom` pauses | Cause not known; `motion_shapes.py` holds still through them | [TB-15](#tb-15-characterise-the-odom-pauses-at-motion-start) |
| Clock fix | Still installed as last seen on 2026-10-04; decision open. The clock was also correct at 15:42 on 2026-10-04 after a power-on | [TB-17](#tb-17-decide-whether-to-keep-or-remove-the-clock-fix), [TB-01](#tb-01-restore-create-3-base-communication) |
| Lidar | On USB again after the later power-on on 2026-10-04 (no `/scan` result recorded) | [TB-02](#tb-02-fix-lidar-detection) (Done), [TB-18](#tb-18-lidar-cable-strain-relief-and-label) |
| Repository | GitHub Desktop switched the local clone to `main` with uncommitted TurtleBot changes (2026-10-05); resolved 2026-10-10, nothing lost. As seen on 2026-10-10, the TurtleBot work from a8c0b4e on is not on `main` yet; it was merged into `main` later on 2026-10-10 | [TB-12](#tb-12-documentation-follow-ups) |
| Documentation | Brought up to date on 2026-10-10: network page, Wi-Fi troubleshooting, statuses, new tasks TB-20 to TB-23 | [TB-11](#tb-11-generalise-the-documentation), TB-12 |

Status unchanged since 2026-10-04: TB-01 (waits for TB-17), TB-03 (not rerun), TB-04, TB-05, TB-06, TB-07, TB-13, TB-14, TB-18.

## State on 2026-10-04

Times are robot time (EDT, from the robot's journal). Details and evidence: [MAINTENANCE.md](MAINTENANCE.md), [docs/](docs/index.html) and the [2026-10-04 log](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt).

Working (new or confirmed today):
- **Lidar fixed** ([TB-02](#tb-02-fix-lidar-detection), Done). The cause was a loose USB cable; the user reseated it before the 11:44 boot. Off the dock `/scan` runs at 7.75 Hz with 720 beams, and `clearance_check.py 0.6` exits 0.
- **Base talking** on this boot: `/dock_status` received, Pi and base clocks within seconds. Undock succeeded at about 12:09.
- **Motion program** [examples/motion_shapes.py](examples/motion_shapes.py) drove a 40 cm square (8 segments in 39 s, odometry end error 0.9 cm / +0.8 degrees), a 360 degree rotation (0.1 cm / +0.7 degrees) and a back-and-forth run (0.6 cm / +0.9 degrees). Errors are from odometry only; the floor was not measured.

Not working or open:
- The HTTPS clock fix is **still installed** and `undo-clock` was not run. It did no harm on this boot. Keep or remove is now a decision ([TB-17](#tb-17-decide-whether-to-keep-or-remove-the-clock-fix)); TB-01 stays open until it is made.
- The base pauses `/odom` for 0.4 to 1.0 s when the wheels start ([TB-15](#tb-15-characterise-the-odom-pauses-at-motion-start)). `motion_shapes.py` now holds still during a pause instead of aborting.
- `motion_test.sh` itself has not been rerun ([TB-03](#tb-03-complete-the-movement-test-with-the-lidar), in progress). The first runs of the motion programs are done; the longer test campaign is waiting for a supervised session ([TB-16](#tb-16-motion-program-test-campaign-and-demo-shapes)).
- Unchanged from 2026-10-03: the long-term time strategy (TB-04), security hardening (TB-05), Wi-Fi drops during motion (TB-10), remote desktop (TB-06).

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
| [TB-01](#tb-01-restore-create-3-base-communication) | Restore Create 3 base communication | P0 | Prepared (base working on 2026-10-04 with the clock fix still installed; waits for TB-17) | TB-17 |
| [TB-02](#tb-02-fix-lidar-detection) | Fix lidar detection | P0 | **Done** 2026-10-04 | None |
| [TB-03](#tb-03-complete-the-movement-test-with-the-lidar) | Complete the movement test with the lidar | P1 | In progress (2026-10-04) | TB-01, TB-02 |
| [TB-04](#tb-04-choose-a-reliable-time-strategy) | Choose a reliable time strategy | P1 | Open | TB-01 |
| [TB-05](#tb-05-security-hardening) | Security hardening | P1 | Open | None |
| [TB-06](#tb-06-remote-desktop-access) | Remote desktop access | P1 | Open | TB-04, TB-05, TB-07 |
| [TB-07](#tb-07-sd-card-backups) | SD card backups | P2 | Open | None |
| [TB-08](#tb-08-stable-addressing) | Stable addressing | P2 | Open | None |
| [TB-09](#tb-09-ros-2-from-a-laptop-over-campus-wi-fi) | ROS 2 from a laptop over campus Wi-Fi | P2 | Open | TB-01 |
| [TB-10](#tb-10-make-long-commands-survive-wi-fi-drops) | Make long commands survive Wi-Fi drops | P2 | Open | None |
| [TB-11](#tb-11-generalise-the-documentation) | Generalise the documentation | P2 | In progress (2026-10-03; docs updated 2026-10-10; hands-on and lidar guides added 2026-10-10) | None |
| [TB-12](#tb-12-documentation-follow-ups) | Documentation follow-ups | P2 | In progress (2026-10-10) | TB-11 |
| [TB-13](#tb-13-teleoperation-how-to) | Teleoperation how-to | P3 | Open (command-line driving documented 2026-10-10; keyboard teleop not yet) | TB-01 |
| [TB-14](#tb-14-onboarding-checklist-for-new-lab-members) | Onboarding checklist for new lab members | P3 | In progress (do-it-yourself guide written 2026-10-10; not yet tried by a new member) | TB-05, TB-11 |
| [TB-15](#tb-15-characterise-the-odom-pauses-at-motion-start) | Characterise the `/odom` pauses at motion start | P2 | In progress (2026-10-04; 2026-10-24: cause located in the base, triggered by motion start; why it stalls is open, TB-25) | None |
| [TB-16](#tb-16-motion-program-test-campaign-and-demo-shapes) | Motion program test campaign and demo shapes | P2 | Open (started 2026-10-04: first runs done; campaign waiting for a supervised session, no runs since 2026-10-04) | TB-02 |
| [TB-17](#tb-17-decide-whether-to-keep-or-remove-the-clock-fix) | Decide whether to keep or remove the clock fix | P1 | Open (proposed 2026-10-04; 2026-10-24 evening: proposal for the decision added) | None |
| [TB-18](#tb-18-lidar-cable-strain-relief-and-label) | Lidar cable strain relief and label | P2 | Open (proposed 2026-10-04) | None |
| [TB-19](#tb-19-read-only-health-check-script) | Read-only health check script | P3 | Prepared (written 2026-10-04 as `examples/health_check.py`, tested offline; robot run pending, TB-23) | None |
| [TB-20](#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving) | Fix the robot Wi-Fi drops (Wi-Fi power saving) | P0 | Applied 2026-10-24 (R14 for `Students`; R17 for all networks, global `wifi.powersave=2`); effect to verify on campus | None |
| [TB-21](#tb-21-decide-the-robots-network-students-or-the-lab-router) | Decide the robot's network: Students or the lab router | P1 | Open (proposed 2026-10-10) | TB-20, TB-22 |
| [TB-22](#tb-22-secure-the-lab-router) | Secure the lab router | P1 | In progress (credentials changed 2026-10-10) | None |
| [TB-23](#tb-23-first-robot-run-of-the-new-programs-and-the-connect-tool) | First robot run of the new programs and the connect tool | P1 | Open (proposed 2026-10-10). Note 2026-10-24: the timing recorder `tools/timing/record_timing.py` ran on the robot during a supervised motion test; the new example programs and the connect tool still have not run on it | TB-20 |
| [TB-24](#tb-24-lidar-motor-does-not-restart-after-undocking) | Lidar motor does not restart after undocking | P1 | Open (proposed 2026-10-24; 2026-10-24 evening: did not reproduce on one undock) | None |
| [TB-25](#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving) | Find why the Create 3 base stalls when it starts moving | P1 | Open (proposed 2026-10-24; evening: longer stalls seen at idle, new hypothesis; late evening: an `/odom` subscriber triggers 7 to 12 s stalls; program-side wait added; 10 supervised motion starts done, 10 of 10 completed, 2 short start pauses remain; steps 3 and 4 done read only, likely cause discovery load on the base, two changes proposed; change A applied as R19, then 0 of 8 joins stalled in one test, against 5 of 8 before; change B not applied) | TB-15 |
| [TB-26](#tb-26-measure-students-signal-strength-on-campus) | Measure `Students` signal strength on campus | P1 | Open (proposed 2026-10-24) | None |
| [TB-27](#tb-27-desktop-control-app-for-connecting-file-sync-and-running-programs) | Desktop control app for connecting, file sync, running and stopping programs | P1 | Built and tested on the robot over the cable 2026-10-24 (no motion); evening: also tested over Wi-Fi with supervised motion; remaining checks listed in the task | None |
| [TB-28](#tb-28-decide-whether-the-robot-installs-ubuntu-updates-by-itself) | Decide whether the robot installs Ubuntu updates by itself | P2 | Open (proposed 2026-10-24, evening) | None |

Suggested order (updated 2026-10-24): **TB-27 is the next task** (owner the user). On the next campus visit, in one session: **TB-26** (signal strength, read only) together with **TB-20** steps 5 and 6 (30 connection attempts over 30 minutes, then the reboot test), because R14 is applied but its effect is unverified. At the robot, which also works over the Ethernet cable: **TB-24** (small, makes every motion run start cleanly) and **TB-25** (why the base stalls; it blocks reliable shapes and feeds TB-15 and TB-16). Then the order of 2026-10-10 below: TB-22 and TB-21, TB-23, TB-17, TB-05, TB-07 before risky changes.

Previous order (2026-10-10): **TB-20 first**, because nothing else can be done on the robot while it drops off the Wi-Fi. Then TB-22 and the network decision TB-21 (secure the router before the robot uses it). Then TB-23 (copy the new programs and run them, and the connect tool, for the first time; supervised, in short batches), which also feeds TB-19, TB-16 and TB-15. TB-17 (the clock decision, which closes TB-01) can be done in the same sessions. Do TB-05 soon. Take a backup (TB-07) before the first risky change in TB-04, TB-05, TB-06 or TB-21.

Previous order (2026-10-04): TB-17 (decide on the clock fix), which closes TB-01; finish TB-03 and TB-16 while the lidar and base work. Do TB-05 soon, because the factory passwords are public and the robot is reachable from the whole `Students` network. Take a backup (TB-07) before the first risky change in TB-04, TB-05 or TB-06. (Original order on 2026-10-03: TB-01 and TB-02 in one session at the robot, then TB-03.)

---

## P0: blocking

### TB-01 Restore Create 3 base communication

**Priority:** P0 | **Status:** Prepared | **Depends on:** TB-17 (added 2026-10-04)

**Goal.** The Create 3 base publishes `/dock_status` and `/battery_state` to ROS again, and dock and undock work, with the HTTPS clock fix removed.

**Update 2026-10-04.** On the boot at about 11:44 (robot time) the base talked to ROS without any action: `/dock_status` arrived, the Pi and base clocks agreed within seconds, and undock succeeded at about 12:09. The clock fix (R7, R8) is still installed and `undo-clock` was **not** run; the user decided not to touch the clock while ROS runs. Whether to remove the fix at all is now [TB-17](#tb-17-decide-whether-to-keep-or-remove-the-clock-fix). If TB-17 decides to keep it, rewrite this goal and close the task on the base criteria alone. The steps below remain the procedure if the fix is removed or the base goes silent again.

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
- [ ] `/dock_status` and `/battery_state` each print a message within 60 s. (2026-10-04: `/dock_status` received with the clock fix still installed; `/battery_state` not recorded.)
- [ ] Undock and dock goals are accepted and succeed (checked in TB-03, or by hand with the commands in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md)). (2026-10-04: undock succeeded at about 12:09; dock result to be recorded.)
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

**Priority:** P0 | **Status:** **Done** 2026-10-04 | **Depends on:** None

**Outcome (2026-10-04).** Root cause: a loose USB connection. The user reseated the lidar USB cable (same cable, same port) before booting the robot at about 11:44 robot time; no software change was needed and steps 2 to 11 below were not required. Evidence: `lsusb` shows `10c4:ea60` Silicon Labs CP210x; `/dev/RPLIDAR` points to `ttyUSB0`; the driver reported firmware 1.29, hardware revision 7, health 0; after undocking `/scan` ran at 7.75 Hz with 720 beams (519 valid, median 1.44 m); `clearance_check.py 0.6` printed "nearest in front 1.73 m" and exited 0. Full record: [MAINTENANCE.md](MAINTENANCE.md#incident-lidar-not-detected-2026-10-03-resolved-2026-10-04), [docs/lidar-diagnosis.html](docs/lidar-diagnosis.html), [docs/LIDAR-FINDINGS.md](docs/LIDAR-FINDINGS.md). Follow-up: [TB-18](#tb-18-lidar-cable-strain-relief-and-label). The steps are kept for the next time the lidar disappears.

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
- [x] `lsusb` lists a Silicon Labs (CP210x) device. (2026-10-04: `10c4:ea60`)
- [x] `/dev/RPLIDAR` exists. (2026-10-04: link to `ttyUSB0`)
- [x] Off the dock, `scan_test.py` prints distances and `clearance_check.py` exits 0 or 1. (2026-10-04: `clearance_check.py 0.6` exit 0; `/scan` checked with `ros2 topic hz` and `ros2 topic echo --full-length` instead of `scan_test.py`)
- [x] The lidar is still detected after a reboot. (2026-10-04: detected on the 11:44 boot, which came after the reseat. A second, separate reboot has not been checked yet; note it the next time the robot restarts. Update 2026-10-10: after the robot was powered off and switched on again on 2026-10-04, a single SSH check at about 15:42 robot time found the lidar on USB; no `/scan` result was recorded.)
- [x] Port or cable changes are recorded in MAINTENANCE.md. (No port or cable change; the reseat is recorded.)

**Risks and rollback.**
- Unplugging the wrong cable can cut the base link or the camera. Identify the lidar cable before unplugging (a photo of it is a TB-12 item).
- If moving to another port does not help, put the cable back in its original port.
- No software configuration is changed by this task.

**Estimated effort:** 30 to 60 minutes. A hardware replacement adds delivery time.

---

### TB-20 Fix the robot Wi-Fi drops (Wi-Fi power saving)

**Priority:** P0 | **Status:** Applied 2026-10-24 (R14 for `Students`; R17 for all networks, global `wifi.powersave=2`, see MAINTENANCE); effect to verify on campus | **Depends on:** None

**Goal.** The robot stays reachable over SSH on `Students`, and the cause of the drops seen on 2026-10-04 and 2026-10-05 is confirmed or ruled out.

**Why it matters.** Since 2026-10-04 the robot answers SSH only briefly. On 2026-10-04 (about 15:42 robot time) it answered once after being switched on, then stayed away for at least 25 minutes. On 2026-10-05 (afternoon, UTC+3) it answered for about a minute, then only in short windows of about 10 to 40 s. Nothing on this roadmap that needs the robot can be done reliably until this is fixed. The laptop's Wi-Fi stayed fine and the robot's logs showed no Wi-Fi disconnects. That fits the leading diagnosis, which is **not confirmed**: Wi-Fi power saving on the Raspberry Pi (on by default in Ubuntu; the `Students` profile written on 2026-10-03 sets no value) keeps the Pi associated with the access point but stops it answering incoming connections most of the time. Record: [MAINTENANCE.md, Wi-Fi incident](MAINTENANCE.md#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05).

**Update 2026-10-24.** Steps 2 to 4 were done in part. Evidence (read only, from the journal and NetworkManager files): power saving was on, because `/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf` sets `wifi.powersave = 3` and the `Students` profile had `0` (default), which inherits it; the kernel log says "power save enabled" at every boot; `iw` is not installed. The logs show no disconnects on 2026-10-04 afternoon or 2026-10-05, so the robot stayed associated while it answered only in windows, which fits power saving (inference, not proven). The change was applied as R14 (`sudo nmcli connection modify Students 802-11-wireless.powersave 2`; before `default`, after `disable`; about 00:22 laptop time). `nmcli connection up Students` was not run, because `Students` was out of range and it would have disturbed the hotspot. **Still open:** steps 5 and 6 (30 attempts on two days, reboot test), which need the robot on campus, and the acceptance items about them.

**Steps.**

1. Get a session. Robot on its dock; read the address on its display and connect by address, not by `turtlebot4.local`, retrying if needed ([HOW-TO-CONNECT.md](HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found)). A person who knows the `ubuntu` password must be there.
2. Collect evidence first (read only). Record the output in the network log.

   ```bash
   nmcli -g 802-11-wireless.powersave connection show Students
   iw dev wlan0 get power_save
   journalctl -u NetworkManager -b --no-pager | tail -n 50
   ```

   The first prints the profile's power-save value. `iw` may not be installed on this image **[to verify]**; if it is, it prints whether power saving is on for `wlan0` right now.
3. Apply the fix. `sudo` asks for the `ubuntu` password. The Wi-Fi reconnects, so SSH may drop for a few seconds; no reboot. If the session drops after the first command, log in again and run the second. **[prepared]**

   ```bash
   sudo nmcli connection modify Students 802-11-wireless.powersave 2
   sudo nmcli connection up Students
   ```

4. Verify the setting. Expected: the value for "disable", 2. **[prepared]**

   ```bash
   nmcli -g 802-11-wireless.powersave connection show Students
   ```

5. Verify the effect. From a laptop on `Students`, with the robot on its dock, try to connect once a minute for 30 minutes and note each failure. `BatchMode=yes` makes ssh fail instead of asking for a password, so set up key login first. **[to verify]**

   On the laptop (macOS, Linux or Git Bash):

   ```bash
   for i in $(seq 1 30); do date +%T; ssh -o ConnectTimeout=5 -o BatchMode=yes ubuntu@<robot-address> uptime || echo FAILED; sleep 60; done
   ```

   On the laptop (Windows PowerShell):

   ```powershell
   1..30 | ForEach-Object { Get-Date -Format T; ssh -o ConnectTimeout=5 -o BatchMode=yes ubuntu@<robot-address> uptime; if ($LASTEXITCODE -ne 0) { "FAILED" }; Start-Sleep 60 }
   ```

   Repeat on a second day.
6. Reboot test: `sudo reboot`, wait 2 minutes, then repeat step 4 and a shorter step 5. The setting is stored in the profile, so it should survive.
7. Record the change in [MAINTENANCE.md](MAINTENANCE.md) as R14 (location `/etc/NetworkManager/system-connections/Students.nmconnection`, verify and undo as below), set the incident and Known issues rows to the new status, and update the troubleshooting in HOW-TO-CONNECT.md and the [network page](docs/network-and-connectivity.html).
8. If the drops continue with power saving off: record that the first cause is ruled out, then look at the others listed in the incident record (mDNS on campus, roaming), at the NetworkManager log during a drop, and at the lab network option (TB-21).

**Acceptance criteria.**
- [ ] The power-save value before the fix is recorded.
- [ ] `nmcli -g 802-11-wireless.powersave connection show Students` prints the value for "disable" (2), also after a reboot.
- [ ] From a laptop on `Students`, 30 connection attempts by address over 30 minutes all succeed, on two different days.
- [ ] R14 is in MAINTENANCE.md with verify and undo; the incident record and Known issues are updated.
- [ ] Or: the fix is shown not to help, this is recorded, and the next step is chosen.

**Risks and rollback.**
- The Wi-Fi reconnects when the profile is brought up again, so SSH may drop for a few seconds. No reboot is needed.
- With power saving off the Wi-Fi may use a little more battery (not measured).
- Rollback: `sudo nmcli connection modify Students 802-11-wireless.powersave 0` (0 is the default), then `sudo nmcli connection up Students`.

**Estimated effort:** 30 minutes at the robot, plus 30 minutes of observation on each of two days. Needs a person who can type the `ubuntu` password.

---

## P1: important

### TB-03 Complete the movement test with the lidar

**Priority:** P1 | **Status:** In progress (2026-10-04) | **Depends on:** TB-01, TB-02

**Progress 2026-10-04.** TB-02 is done and the base talks, so the preconditions hold in practice (TB-01 is formally open only for the clock decision). `motion_test.sh` itself has **not** been rerun. Forward driving with the lidar active has been shown by [examples/motion_shapes.py](examples/motion_shapes.py), which stops if anything is within 0.25 m and ±30 degrees in front while driving forward: square, rotate and back-and-forth completed. Undock succeeded at about 12:09. Still to do: one end-to-end `motion_test.sh` run, the blocked-path run (step 5) and recording the dock result. Results go to [docs/test-results.html](docs/test-results.html).

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

**Update 2026-10-10.** The lab router set up on 2026-10-05 is a separate device with its own factory admin login; securing it is [TB-22](#tb-22-secure-the-lab-router). The robot is not on that network, so this task is unchanged.

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

### TB-17 Decide whether to keep or remove the clock fix

**Priority:** P1 | **Status:** Open (proposed 2026-10-04) | **Depends on:** None

**Goal.** A recorded decision on the HTTPS clock fix (R7 timer, service and script; R8 drop-in): remove it with `undo-clock` as planned on 2026-10-03, or keep it, possibly changed.

**Why it matters.** On 2026-10-03 the fix silenced the base twice. On 2026-10-04 it was still installed, the clock was correct and the base talked, so the reason for removing it is less clear than it was. Its 15 minute timer can still step the clock while ROS runs if the boot-time fetch fails. TB-01 and TB-04 both wait on this decision.

**Evidence so far (2026-10-10).**

| Boot (robot time, EDT) | Clock right at boot? | `tb4-https-time` result | Base talked? |
|---|---|---|---|
| 2026-10-04, about 11:44 | Yes (2026) | Not recorded | Yes (`/dock_status`, clocks within seconds) |
| 2026-10-04, about 15:38 (power-on after the robot was off between sessions) | Correct at 15:42 (uptime 4 min) | Not recorded | Not recorded |

No later boot is recorded.

**Steps.**

1. Collect evidence without changing anything (read only). Over the next few boots, record for each: whether the clock was right at boot, whether `tb4-https-time` succeeded or failed, whether it stepped the clock, and whether the base talked.

   ```bash
   journalctl -u tb4-https-time -b --no-pager
   systemctl list-timers --all | grep tb4
   timeout 60 ros2 topic echo --once /dock_status
   ```

2. Weigh the options against the evidence:
   - **Remove** (`sudo ./undo-clock`, then restart the base application, TB-01 steps 4 to 6). Clock wrong after power cycles, but nothing steps it while ROS runs.
   - **Keep as is.** Clock usually right; risk of a step while ROS runs when the boot fetch fails.
   - **Keep the boot fetch, remove the 15 minute timer** so the clock is only set before ROS starts. Needs an admin change; propose it here first. **[to verify]**
3. Agree the choice with the lab supervisor, record it here and in MAINTENANCE.md (R7, R8), and update TB-01 and TB-04.

**Acceptance criteria.**
- [ ] Evidence from at least three boots is recorded.
- [ ] The decision, the date and who made it are recorded here and in MAINTENANCE.md.
- [ ] TB-01 is closed or rewritten to match the decision.

**Risks and rollback.** Collecting evidence changes nothing. Removing the fix: rollback is not recommended (see TB-01). Any clock change while ROS runs can silence the base; restart the base application if it does.

**Estimated effort:** 15 minutes per boot to collect evidence; 30 minutes for the decision.

**Update 2026-10-24, evening: new evidence and a proposal (to approve, not applied).**

New evidence: when R16 gave the robot internet, the Pi set its own time (`chronyd` stepped the clock by +62,648,406.93 s, about 1.99 years, at 21:49:23 robot time, while ROS ran). `tb4-https-time` at 21:59 then said "Clock already correct". The Create 3 base kept its 2024 clock until `restart-ntpd` on the base (22:20:50 robot time, clock right within 15 s) and an application restart of the base (22:21:17, 373 s of silence). The base needs both steps; its ntpd will not step the clock while it runs. See [MAINTENANCE.md, clock incident update](MAINTENANCE.md#update-2026-10-24-clock-stepped-by-the-internet-and-base-re-sync).

Why the clock is not fixed for good: the Pi 4 has no battery-backed real-time clock, the campus blocks NTP, the 2026-10-03 HTTPS fix stepped the clock while ROS ran and silenced the base, and this decision is still open.

Proposal (needs approval from the lab supervisor; nothing applied):

- **Option A (recommended):** add a DS3231 real-time-clock module on the Pi's I2C pins (about 30 SAR), so the Pi boots with the right date even without internet; and make `turtlebot4.service` start only after the time is set. **[to verify]** on this robot: the I2C pins must be free and the module and its driver must work with this image.
- **Option B (software only):** at boot, before ROS starts, set the time once (chrony `makestep` or the HTTPS fetch) with `Requires=` ordering, and never step the clock while ROS runs. After any step, restart the base ntpd and then the base application.
- **Either way:** document the base re-sync procedure (`restart-ntpd`, then `restart-app`, wait up to about 6 minutes), as in the MAINTENANCE.md runtime table.

---

### TB-21 Decide the robot's network: Students or the lab router

**Priority:** P1 | **Status:** Open (proposed 2026-10-10) | **Depends on:** TB-20 (its result informs the decision), TB-22 (secure the router before the robot uses it)

**Goal.** A recorded decision on which Wi-Fi the robot uses: stay on `Students`, or move to the lab router with `Students` and the robot's own `Turtlebot4` access point as fallbacks. If the decision is to move, the robot has a working lab-router profile and a fixed address.

**Why it matters.** On `Students` the robot's address comes from campus DHCP and can change, `turtlebot4.local` is unreliable, the robot roams between access points while it drives, and anyone on `Students` can reach it (TB-05). The lab router set up on 2026-10-05 ([MAINTENANCE.md, Lab router](MAINTENANCE.md#lab-router-not-used-by-the-robot-yet)) is expected to give a stable address, no campus roaming or client limits, and likely working ROS 2 discovery between a laptop and the robot (TB-09). None of these benefits has been tested with the robot. A laptop on the lab router keeps internet through the router's uplink (DNS and HTTPS worked on 2026-10-05), so no second Wi-Fi adapter is needed.

**Options.**

| Option | What it means | For | Against |
|---|---|---|---|
| A. Stay on `Students` | Keep R1 as it is, plus the TB-20 fix | No robot change beyond TB-20; works anywhere on campus | Address can change; mDNS unreliable on campus; roaming; reachable from the whole `Students` network |
| B. Lab router first, `Students` and `Turtlebot4` as fallbacks (proposal) | A new NetworkManager Wi-Fi profile for the lab router with a higher autoconnect priority than `Students` (10), and a DHCP reservation on the router | Stable address; no campus roaming or client limits; a lab-only network; likely working ROS 2 discovery | 802.11g, 2.4 GHz only: fine for SSH and topics like `/odom`, but `/scan` and camera bandwidth must be checked; end-of-life router firmware (TB-22); users must join the lab Wi-Fi (password from the maintainer) |

**Steps.** Step 1 decides; steps 2 to 8 are the proposal for option B. Every robot step needs `sudo` and a person who knows the `ubuntu` password. Do it with a person at the robot, the robot on its dock, and the laptop on the lab router's network. Nothing here has been run.

1. Decide with the TB-20 result: if the robot is reliable on `Students` after TB-20, option A may be enough. Agree the choice with the lab supervisor and record it, the date and the reasons here and in MAINTENANCE.md. Stop here for option A.
2. Prerequisites: TB-22 steps 1 and 2 are done; the exact SSID is read from the router's Wireless page; the robot's Wi-Fi hardware address is read (`cat /sys/class/net/wlan0/address`, as in TB-08 step 1).
3. On the router: reserve a fixed address for that hardware address (DHCP reservation). Check first that the WRT54G firmware offers this **[to verify]**. Record the reserved address in HOW-TO-CONNECT.md (a private lab address, not secret).
4. On the robot: create the profile with autoconnect off. Use the same method as R1 so the Wi-Fi password is typed at a hidden prompt and never appears on a command line or in this repository. `write_keyfile.py` (copy in `~/wifi-switch/`) writes a profile with autoconnect off and priority 10. Replace `<lab SSID>` with the exact name. **[to verify]**

   ```bash
   sudo -v
   read -r -s -p "Lab Wi-Fi password: " PSK; echo
   printf '%s' "$PSK" | sudo python3 ~/wifi-switch/write_keyfile.py "/etc/NetworkManager/system-connections/<lab SSID>.nmconnection" "<lab SSID>"
   unset PSK
   sudo nmcli connection load "/etc/NetworkManager/system-connections/<lab SSID>.nmconnection"
   ```

5. Test it once. Recommended: adapt `start.sh` and `controller.sh` from [setup/](setup/), which moved the robot to `Students` on 2026-10-03 with a 3-minute test phase and an automatic return. Manual alternative: `sudo nmcli connection up "<lab SSID>"`. The robot leaves `Students`, so an SSH session over `Students` ends; read the new address on the display and connect from the laptop on the lab network. Because the new profile has autoconnect off, a reboot returns the robot to `Students`. **[to verify]**
6. Check on the lab network:

   ```bash
   nmcli -t -f NAME,DEVICE connection show --active
   ip -4 -br addr show wlan0
   timeout 60 ros2 topic echo --once /dock_status
   ```

   Expected: `<lab SSID>:wlan0`, the reserved `192.168.1.x` address, one `/dock_status` message. Then from a laptop with ROS 2 (TB-09): `ros2 topic list`, and `ros2 topic hz /scan` off the dock, compared with the robot's own 7.75 Hz (2026-10-04). Use compressed camera topics only.
7. Make it permanent and test the fallback:

   ```bash
   sudo nmcli connection modify "<lab SSID>" connection.autoconnect yes connection.autoconnect-priority 20
   ```

   Reboot and check that the robot comes back on the lab network by itself. Then switch the router off and check that the robot returns to `Students` (priority 10). **[to verify]**
8. Record the profile and the reservation in MAINTENANCE.md as new change-register rows (R14 onward) with verify and undo, and update HOW-TO-CONNECT.md (which Wi-Fi to join, the fixed address), README.md and the [network page](docs/network-and-connectivity.html).

**Verify (option B).**

```bash
nmcli -f connection.id,connection.autoconnect,connection.autoconnect-priority connection show "<lab SSID>"
nmcli -t -f NAME,DEVICE connection show --active
ip -4 -br addr show wlan0
```

Expected: autoconnect `yes`, priority `20`; `<lab SSID>:wlan0` active; the reserved address.

**Undo (option B).** `sudo nmcli connection delete "<lab SSID>"`. The robot returns to `Students` (or its own access point); an SSH session over the lab network ends, so reconnect on `Students` with the address on the display. Then remove the reservation on the router.

**Acceptance criteria.**
- [ ] The decision (A or B), the date, the reasons and who decided are recorded here and in MAINTENANCE.md.
- [ ] If B: after two reboots on different days the robot is back on the lab network with the same address; it falls back to `Students` when the router is off; from a laptop, 30 connection attempts over 30 minutes all succeed (as in TB-20).
- [ ] If B: `/scan` received on a laptop reaches about the robot's own rate, or the limit is recorded.
- [ ] If B: the change-register rows, HOW-TO-CONNECT.md and README.md are updated.

**Risks and rollback.**
- Losing the connection during the switch: do it at the robot, and prefer the scripted test phase with automatic return.
- 2.4 GHz 802.11g is slow: fine for SSH and `/odom`; check `/scan` and the camera.
- The router firmware is end of life (TB-22).
- When the router is off or out of range the robot falls back to `Students`, then to its own access point. The display always shows the current address.
- Rollback: the undo above.

**Estimated effort:** decision 30 minutes; option B 1 to 2 hours at the robot, plus test time on two days.

---

### TB-22 Secure the lab router

**Priority:** P1 | **Status:** In progress (credentials changed 2026-10-10) | **Depends on:** None

**Update 2026-10-10.** The lab RA changed the router's credentials (step 1) and reports that the router works afterwards. The new credentials are not recorded in this repository. Steps 2 to 4 are still open.

**Goal.** The lab router no longer uses a factory admin login, its admin page is reachable from the lab network only, its settings are recorded without secrets, and a decision on replacing it is recorded.

**Why it matters.** When the router was set up on 2026-10-05 its admin login was still the factory default. Anyone on its network could change its settings. The WRT54G firmware is very old (end of life). If the robot moves to this network (TB-21), the router becomes part of the robot's setup.

**Steps.** On a laptop connected to the router, preferably by cable. All **[to verify]** on this router's firmware.

1. Open `http://192.168.1.1` and change the admin password. Store it in the lab password manager (for example an entry "Lab router WRT54G: admin"). Never put it in this repository, in chat messages or in the logs.
2. Check that remote management (admin access from the router's Internet side) is off, so the admin page can only be reached from the lab network.
3. Record in MAINTENANCE.md (Lab router table): the firmware version (router's status page), the exact SSID, the security mode (WPA2-Personal, AES) and the DHCP range. The Wi-Fi password goes in the password manager only.
4. Decide whether to keep the WRT54G or replace it with a current router (newer firmware, 5 GHz). Record the decision.

**Acceptance criteria.**
- [x] The factory admin login no longer works; the new login is in the lab password manager. (2026-10-10: credentials changed by the lab RA; where the new login is stored is for the lab maintainer to confirm.)
- [ ] Remote management is off.
- [ ] Firmware version and exact SSID are recorded in MAINTENANCE.md, and no secret appears in the repository.
- [ ] The keep-or-replace decision is recorded.

**Risks and rollback.**
- A forgotten admin login means a factory reset, which also erases the router's settings (SSID, Wi-Fi password, reservations). Store the new login before you log out.
- Changing settings over the router's own Wi-Fi can drop your connection; use a cable.
- Rollback: change the settings back on the admin page.

**Estimated effort:** 30 minutes; a replacement adds purchase and setup time.

---

### TB-23 First robot run of the new programs and the connect tool

**Priority:** P1 | **Status:** Open (proposed 2026-10-10) | **Depends on:** TB-20 (the robot must stay reachable)

**Goal.** The programs written on 2026-10-04 and the connect tool have each run on the real robot at least once, and the results are recorded, so the docs can drop "not yet tested on the robot".

**Why it matters.** `health_check.py`, `sensor_report.py`, `lidar_snapshot.py`, `lightring_status.py`, `more_shapes.py`, `wall_approach.py`, `keep_distance.py` and `campaign.sh` were tested offline only (101 logic checks and 38 simulated runs, see [tests/README.md](tests/README.md)) and are not on the robot (MAINTENANCE.md R12, not applied). The connect tool ([tools/connect/README.md](tools/connect/README.md)) was tested against a simulated robot only. A complete figure eight is also still missing (TB-16). Offline tests cannot show timing, `/odom` gaps or real sensor data.

**Steps.** Motion runs are supervised, in short batches, with a person next to the robot (lesson of 2026-10-04). Go through the [safety checklist](examples/README.md#safety-checklist-before-anything-moves) before anything moves, and dry-run every moving program first.

Part A, the programs:

1. Copy the programs (this applies R12, and also replaces the robot's `clearance_check.py` with the version whose lidar fallback was fixed on 2026-10-10). On the laptop, from `TurtleBot/examples/`:

   ```bash
   scp *.py *.sh ubuntu@<robot-address>:robot_code/
   ```

   This also replaces `motion_shapes.py` on the robot with the repo version. Record R12 as applied in MAINTENANCE.md, with the date and the file list.
2. On the dock (read only): `python3 health_check.py`, and compare each row with a manual run of the [verification checklist](MAINTENANCE.md#verification-checklist) (TB-19). Then `python3 sensor_report.py --seconds 60` and `python3 lightring_status.py --seconds 30`.
3. Off the dock (undock detached, see [examples/README.md](examples/README.md#undock-and-dock)): `python3 health_check.py` again (it checks `/scan` off the dock), `python3 lidar_snapshot.py`, then `scan_plot_html.py` on the laptop.
4. Moving programs, one at a time, `--dry-run` first, then one real run detached with `--yes`: `motion_shapes.py figure_eight`, `more_shapes.py star`, `wall_approach.py`, `keep_distance.py --duration 30`, and a short `campaign.sh` list.
5. Record the results in [docs/test-results.html](docs/test-results.html), the status lines in [examples/README.md](examples/README.md) and the step log.

Part B, the connect tool (v1.1.0):

6. On Windows, run `TurtleBotConnect.exe` against the real robot: options 2 (find), 1 (connect), 3 (key login), 4 (status), 5 (VS Code), 6 (SSH config shortcut) and 8 (copy a file). Note the SmartScreen prompt on first run.
7. On macOS or Linux, the same with `connect-turtlebot.sh`.
8. During a supervised `motion_shapes.py rotate` run, use option 7 (emergency stop): the robot must stop and `~/STOP` must exist. Remove it afterwards with `rm ~/STOP`.
9. Check the host-key pinning: the tool connects to the lab robot (ED25519 fingerprint `SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4`) and refuses another SSH device before any password prompt. **[to verify]** how to point it at a second device for this test.
10. Record the results in the step log, and ask the tool's maintainer to update the status line in tools/connect/README.md.

**Acceptance criteria.**
- [ ] R12 is recorded as applied in MAINTENANCE.md, with the date and file list.
- [ ] `health_check.py` ran on and off the dock, and its rows match a manual checklist run (TB-19).
- [ ] Each new program ran once on the robot, or its failure is recorded with the log.
- [ ] One complete figure eight is recorded in docs/test-results.html.
- [ ] The connect tool connected to the real robot from Windows and from macOS or Linux; option 7 stopped a running motion program; the pinning refused a different device.
- [ ] "Not yet tested on the robot" is removed from the status lines of the programs that ran.

**Risks and rollback.**
- Collision: speeds are capped (0.15 m/s), the lidar front stop is active, and a person stands next to the robot.
- Copying changes only `~/robot_code`. Rollback: delete the files listed under R12.
- Option 3 adds one line to `~/.ssh/authorized_keys` on the robot; record its owner (TB-05). Option 6 edits the laptop's SSH config and keeps a backup.

**Estimated effort:** half a day at the robot, in two or three short sessions.

---

### TB-24 Lidar motor does not restart after undocking

**Priority:** P1 | **Status:** Open (proposed 2026-10-24) | **Depends on:** None

**Goal.** After an undock the lidar publishes `/scan` by itself, so programs that need it do not fail at setup.

**Why it matters.** On 2026-10-24 the robot undocked successfully, but `motion_shapes.py` failed at setup with "no /scan". The `rplidar` log shows "Stop" at 14:37:45 robot time (clock wrong by about two years) when the robot was docked, and no "Start" after the undock. `ros2 service call /start_motor std_srvs/srv/Empty` by hand brought `/scan` back at 7.6 Hz. On 2026-10-04 "RPLIDAR started" was logged at undock, so this may be new, intermittent, or tied to the order of actions. The cause is not known.

**Steps.**

1. Reproduce read only first: dock, wait for "RPLIDAR stopped", undock, and check `/scan` with `ros2 topic hz /scan` and the `rplidar` and `turtlebot4_node` logs (`journalctl -u turtlebot4 --no-pager | grep -i rplidar`). Note whether the undock was sent by `ros2 action send_goal /undock` or by the display or button. **[to verify]**
2. Read how the TurtleBot 4 node starts and stops the lidar on undock and dock (the dock power saver) in the `turtlebot4_node` source or documentation for this image. **[to verify]**
3. Decide a fix and write it here before applying it. Options: a documented workaround step in the programs (call `/start_motor` after undocking and wait for `/scan`), or an upstream fix. Any robot change goes through MAINTENANCE.md with verify and undo.
4. Make the example programs ask for `/start_motor` when `/scan` is silent after an undock, with a clear message. Update the affected status lines.

**Acceptance criteria.**
- [ ] The cause is stated, or "unknown" with what was ruled out.
- [ ] Ten undocks in a row either give `/scan` within 10 s by themselves, or the documented workaround gives it every time.
- [ ] The Known issues row in MAINTENANCE.md is updated.

**Risks and rollback.** Undocking moves the robot a few centimetres back: clear floor behind the dock, a person next to it. No configuration change in steps 1 and 2.

**Estimated effort:** 1 to 2 hours at the robot.

**Update 2026-10-24, evening.** The fault did **not** reproduce on the undock at 22:03 robot time (through Studio, "undock: succeeded (status 4)"): `/scan` was already running at 8 Hz after it (the nearest value ahead changed from 0.77 m to 1.93 m). One undock is not ten, so the task stays open. Studio also showed 8 Hz on the dock, so the lidar motor may not have stopped while docked this time; this is not explained.

---

### TB-25 Find why the Create 3 base stalls when it starts moving

**Priority:** P1 | **Status:** Open (proposed 2026-10-24) | **Depends on:** TB-15

**Goal.** Know why all base topics stop for up to 3.16 s when the wheels start, and either remove the stalls or keep `/odom` gaps under 0.3 s.

**Why it matters.** On 2026-10-24 a forward drive aborted after a few centimetres because `/odom` stopped for 3.16 s, longer than the program's 2.0 s stale limit. Gaps of this size make closed-loop motion unreliable and block the figure eight and the test campaign (TB-16, TB-23). Evidence so far: the stall is in the base (stamps stop, all base topics, ping RTT up), triggered by motion start, and is not the Wi-Fi or Pi CPU. Inferred, not proven: load inside the Create 3 (firmware `I.0.0.FastDDS`, ROS Iron). The recorder itself used 44 % of one core and subscribed to many topics, so it may have added load. Record: [MAINTENANCE.md](MAINTENANCE.md#update-2026-10-24-measurements-with-the-timing-recorder).

**Steps.** Supervised, with a person next to the robot, short moves, the usual [safety checklist](examples/README.md#safety-checklist-before-anything-moves).

1. Repeat the same run with the recorder in light mode (`--light`: only `/odom`, `/dock_status` and `/cmd_vel`, about 20 % of one core instead of 50 %; see [tools/timing/](tools/timing/README.md)) and compare the stalls. Do at least 10 motion starts.
2. Test with fewer subscribers: stop the recorder's `/imu` and `/tf` subscriptions, then repeat. Note whether the stall length changes.
3. Read the `create3_republisher` configuration on the robot (which base topics it republishes and at what rate) and compare it with the TurtleBot 4 Jazzy defaults. Read only. **[to verify]**
4. Read the iRobot Create 3 release notes and known issues for firmware `I.0.0.FastDDS` and for later versions. Do not update the firmware in this task.
5. Only with the user's explicit OK: run the base with the Pi's ROS stopped and drive it by its own interface or a minimal client, to see whether the stall exists without the Pi's ROS load. This changes what runs on the robot; record it in MAINTENANCE.md with how to restore.
6. Record gap length and frequency per condition in MAINTENANCE.md and [docs/test-results.html](docs/test-results.html). Choose a mitigation (for example a program-side start-up pause before checking `/odom`, or a changed republisher setting) and propose it here before applying it.

**Acceptance criteria.**
- [ ] The cause is found, or "unknown" with the conditions ruled out and the numbers.
- [ ] Or a mitigation keeps `/odom` gaps under 0.3 s over 10 motion starts.
- [ ] TB-15's acceptance criteria are updated from these results.

**Risks and rollback.** Moving the robot: speeds capped at 0.15 m/s, lidar front stop active. Steps 1 to 4 change nothing on the robot. Step 5 and any republisher change need the user's OK and an undo.

**Estimated effort:** half a day at the robot, in short sessions.

**Update 2026-10-24, evening (over Wi-Fi).**

Measured:
- Idle, docked: `/odom` stalled 7.51 s at 22:00:33 robot time (6 s after the recorder started) and 10.97 s at 22:35:06; `/dock_status` stalled 4.7 s and 9.9 s. The earlier idle maximum was 1.75 s.
- In motion: a 7.81 s gap aborted the first spin. After a Create 3 application restart, the second spin and the circle had no gap over 0.68 s.
- Ping to the base rose in every long stall (up to 41 ms and 36 ms). Wi-Fi was not involved (no errors or drops, about -60 dBm).
- The base application restart is **not a fix**: the 10.97 s idle stall came later, with the Pi and base clocks already in agreement.
- Motion starts that evening: 5 (undock, spin, spin, circle, dock). Step 1 asks for at least 10, so the count is still too low.
- Recordings: `tests/logs/2026-10-24_timing_wifi_before_base_restart.jsonl.gz`, `tests/logs/2026-10-24_timing_wifi_after_base_restart.jsonl.gz`, `tests/logs/2026-10-24_studio_motion_runs.log`.

**Hypothesis, not proven:** the long stalls follow new ROS 2 participants joining the graph (DDS discovery load on the Create 3, Fast DDS, firmware `I.0.0.FastDDS`). They came 6 s after the recorder started, seconds after a spin program started, and while several `ros2 topic echo` and `ros2 topic hz` commands were starting. If so, the earlier "triggered by motion start" may really be "triggered by the program start" just before the motion. Pi CPU load (the update job, command-line tools) may contribute.

New first step (cheap, docked, no motion): record with `--light` for 10 minutes; every 60 s start and stop a minimal `rclpy` node (or run `ros2 topic list`), log the times, and see whether stalls follow the joins. Then, read only, compare the Create 3 `Discovery Server` and `ROS_DOMAIN` settings and the republisher settings. Do this before the 10 motion starts of step 1. Details: [MAINTENANCE.md, /odom update](MAINTENANCE.md#update-2026-10-24-evening-over-wi-fi).

**Update 2026-10-24, later (DDS-join test done, docked, no motion).** Ran the "new first step" above: 12 min `--light` recording, 120 s quiet baseline, then a minimal `rclpy` node (create node, spin 5 s, exit) every 60 s, 8 times; no `ros2` CLI on the robot. Result: **hypothesis supported in part, not proven.**
- Baseline 0 to 120 s: no `/odom` or `/dock_status` gap. 5 of 8 joins: none.
- 3 of 8 joins were followed by a stall: join 2 (a cluster starting when the node *left*: `/dock_status` 6.50 s, `/odom` 2.46 s, 1.95 s, 0.38 s), join 4 (`/odom` 0.50 s), join 5 (`/odom` 0.41 s and 0.31 s). One unrelated 0.27 s gap. All 7 other gaps started within 12 s of a join.
- Stalls are `publisher stopped` (the base produced nothing), no Wi-Fi errors, ping to the base normal except single spikes inside the long cluster.
- The earlier 7.5 to 11 s stalls were not reproduced by this light probe; heavier joins (several `ros2` CLI commands, a spin program) may be worse. Not tested.
- Recording: `tests/logs/2026-10-24_timing_tb25_dds_joins.jsonl.gz`, join times in `..._dds_joins_joins.log`. Details and numbers: [MAINTENANCE.md](MAINTENANCE.md#update-2026-10-24-afternoon-tb-25-dds-join-test-docked-no-motion).
- Next: repeat with `ros2 topic list` as the joiner and with a node that subscribes to `/odom`; then step 3 (read-only) and the 10 motion starts. No configuration was changed. Acceptance criteria are still open (cause not final).


**Update 2026-10-24, follow-up joins (R-d done).** Docked on the home Wi-Fi, Ibrahim present, no motion; times are laptop time (UTC+3) with robot time (EDT) in brackets where useful. Two recordings that started at 16:13 (09:13) and 16:26 (09:26) received nothing on `/odom` and `/dock_status` and are invalid (not stored): after the last SSH logout, systemd-logind removed the shared memory of the `ubuntu` user and Pi-local ROS delivery stopped. Fixed by R18 (user lingering on; see [MAINTENANCE.md](MAINTENANCE.md#change-register); verified, not yet checked after a reboot). Details: [MAINTENANCE.md, Known issues](MAINTENANCE.md#known-issues). Whether earlier TB-25 evidence was affected is not known and is not claimed either way. The valid runs after R18 used the same method as the first run (720 s `--light` recording, 120 s baseline, 8 joins 60 s apart):

| Joiner | Joins followed by a stall | Longest `/odom` gap | Longest `/dock_status` gap |
|---|---|---|---|
| Bare node, 5 s (first run) | 3 of 8 | 2.46 s | 6.50 s |
| A: `ros2 topic list --no-daemon` | 1 of 8 | 0.26 s | none |
| B: node subscribing to `/odom`, 5 s | 5 of 8 | 10.87 s | 12.28 s |

- Reading: a participant that subscribes to `/odom` triggers base stalls more often and much longer than a bare node, and a short `ros2 topic list` almost never does. Run B reproduces the 7.5 to 11 s stalls of the evening of 2026-10-23/24. Stalls start 0.8 to 14.7 s after the subscriber starts and every cluster had ended by about 17 s after it. The base itself stops producing (header stamps stop, ping to the base rises to 19.5 to 73.5 ms against a median of 0.5 ms); no Wi-Fi errors, drops or lost pings (-69 to -72 dBm).
- Why a new subscriber makes the Create 3 stall is still open. Inferred, not confirmed: discovery and endpoint matching load on the Create 3 (firmware `I.0.0.FastDDS`, simple discovery, `ROS_DISCOVERY_SERVER` empty, RMW `rmw_fastrtps_cpp`, `/etc/turtlebot4/fastdds_rpi.xml` an empty default profile). Limits: one run of each joiner, one robot, home Wi-Fi.
- Consequence: every motion program subscribes to `/odom`, so its own start can stall the base for up to about 12 s. Mitigation R-c (code in `examples/` and the Studio templates, see [examples/README.md](examples/README.md)): before the first motion a program waits until at least 20 s after it started and 5 s of steady `/odom` (no gap over 0.3 s), with a 30 s timeout that never fires before that can be met. The first version used 3 s of steady `/odom`; it was changed after run B because 3 s could pass before the program's own stall or inside a 3.2 s quiet stretch within a cluster. Not yet tested in motion.
- Next: (1) the 10 supervised motion starts with the new check (step 1); (2) step 3, read only: the `create3_republisher` configuration; (3) consider whether programs should keep one long-running node instead of starting a new one for each run. Acceptance criteria are still open (cause not final).
- Files: `tests/logs/2026-10-24_timing_tb25_joins_ros2cli.jsonl.gz` with `..._ros2cli_joins.log`, and `tests/logs/2026-10-24_timing_tb25_joins_odom_sub.jsonl.gz` with `..._odom_sub_joins.log`. Details: [MAINTENANCE.md](MAINTENANCE.md#update-2026-10-24-evening-tb-25-follow-up-joins-docked-no-motion).

**Update 2026-10-24, motion starts.** 10 supervised program runs (spin and forward-and-back templates with the start-up check) between an undock and a dock, home Wi-Fi, Ibrahim next to the robot, 17:54 to 18:04 laptop time. Result: 10 of 10 completed, no abort, no hold over the 2.0 s stale limit. The two long stalls of the test (9.8 s in run 6, 4.4 s in run 7) came about 9 s after those programs started, while they were still waiting, so the robot stood still through them; inferred, not separately tested, that the first version of the check would most likely have aborted both. Acceptance criterion 2 (a mitigation keeps `/odom` gaps under 0.3 s over 10 motion starts) is **not met**: 2 of 10 runs had a short gap at or just after motion start (0.52 s and 0.79 s), the original TB-15 pause, covered by the programs' 0.3 s hold. Long join-triggered stalls are avoided by waiting; short motion-start pauses remain. Cost: each program waits about 20 s (20.0 to 22.5 s). No box ticked; step 3 (read the `create3_republisher` configuration, read only) is still next. Table and numbers: [MAINTENANCE.md](MAINTENANCE.md#update-2026-10-24-evening-supervised-motion-starts-with-the-start-up-check). Files: `tests/logs/2026-10-24_timing_tb25_motion_starts.jsonl.gz` and `tests/logs/2026-10-24_tb25_motion_starts_runs.log`.

**Update 2026-10-24 (step 3 and 4).** Steps 3 and 4 are done, read only. Robot docked on the home Wi-Fi, read over SSH from about 15:42 to 15:50 robot time (EDT). The Create 3 web pages were read from the Pi with `curl` GET requests only: no POST, no restart, no configuration change. Short-lived copies of the base's log were written to `/tmp` on the Pi and deleted again. **Two changes are proposed below. Neither is applied.**

What was read (step 3):

| Item | Value on the robot | Reading |
|---|---|---|
| Republisher parameters, `/opt/ros/jazzy/share/turtlebot4_bringup/config/republisher.yaml` | Republishes `battery_state`, `dock_status`, `imu`, `interface_buttons`, `odom`, `tf`, `tf_static`, `wheel_status`; 4 subscriptions (`cmd_audio`, `cmd_lightring`, `cmd_vel`, `cmd_vel_stamped`), 3 services, 9 actions. `cliff_intensity`, `hazard_detection`, `ir_intensity`, `wheel_ticks`, `wheel_vels` and others are commented out | Same entity lists as the package default (`create3_republisher/bringup/params.yaml`), so the Jazzy default. No rate setting exists in this file |
| Republisher launch | Started by `turtlebot4_bringup/launch/robot.launch.py` with that file, `robot_namespace: _do_not_use`, `respawn=True`, `cmd_vel` remapped to `cmd_vel_unstamped`. Process at 18.8 % of one core | Default |
| Unused republisher profiles | `create3_republisher/dds-config/` ships `fastdds-active-unicast.xml`, `fastdds-passive-unicast.xml` and `fastdds-robot-passive-unicast.xml` | Not referenced by the TurtleBot 4 setup |
| `/etc/turtlebot4/setup.bash` | `ROS_DOMAIN_ID="0"`, `RMW_IMPLEMENTATION="rmw_fastrtps_cpp"`, `ROS_DISCOVERY_SERVER=""`, `ROS_SUPER_CLIENT="False"`, `FASTRTPS_DEFAULT_PROFILES_FILE="/etc/turtlebot4/fastdds_rpi.xml"`, `ROBOT_NAMESPACE=""`, `TURTLEBOT4_DIAGNOSTICS="1"` | Simple discovery mode |
| `/etc/turtlebot4/fastdds_rpi.xml` | One default participant profile with an empty `<rtps/>` | Fast DDS defaults: multicast discovery on every interface, including `usb0` to the base |
| `/etc/turtlebot4/fastdds_discovery_create3.xml` | Present, not in use: a profile for the base with UDP only, 32 KB socket buffers, 8 KB maximum message size | `turtlebot4-setup` writes it to the base only in discovery-server mode (source below) |
| `/etc/turtlebot4/discovery.sh`, `discovery.conf` | `fastdds discovery -i 0 -p 11811` as a systemd unit template | No `discovery.service` is installed or running |
| `/etc/turtlebot4/system` | `MODEL:standard`, `VERSION:2.0.2`, `ROS:Jazzy` | |
| Packages | `ros-jazzy-create3-republisher` 1.0.0, `ros-jazzy-fastrtps` 2.14.3, `ros-jazzy-rmw-fastrtps-cpp` 8.4.1, `ros-jazzy-turtlebot4-bringup` 2.0.1, `ros-jazzy-turtlebot4-setup` 2.0.2 | Upstream `turtlebot4_setup` 2.0.3 adds `RemoveIPC=no`, the same effect as R18; apt on the robot shows no newer candidate (TB-28) |
| Create 3 Application, Configuration (`/ros-config`) | ROS 2 domain `0`, namespace `/_do_not_use`, RMW `rmw_fastrtps_cpp`, "Enable Fast DDS discovery server?" **not ticked** (address field holds `192.168.186.3:11811`), parameters file only sets `safety_override: "none"` | What `turtlebot4-setup` writes in simple discovery mode |
| Create 3 Override RMW Profile (`/rmw-profile-override`) | Empty, so the base uses its built-in profile | Simple discovery mode |
| Create 3 NTP (`/beta-ntp-conf`) | `server 192.168.186.3 prefer iburst minpoll 4 maxpoll 6` | Time from the Pi, as the setup tool writes it |
| Create 3 firmware (`/about`) | `I.0.0.FastDDS` (ROS 2 Iron), SKU RCi3099 | The latest release (below) |
| Create 3 Wi-Fi (`/wifi` and its log) | No IP address. The base's log shows a Wi-Fi scan about every 7.5 s with `CTRL-EVENT-NETWORK-NOT-FOUND`, "wifi is disconnected" and a DHCP `sending discover` error each time (336 in 43 minutes) | The base still holds a saved Wi-Fi network it cannot find and keeps searching for it. The TurtleBot 4 Jazzy manual says the Create 3 should be left offline |
| Create 3 load (base log, `system_health`, one line a minute, 19:02 to 19:44 base time, UTC) | Docked and idle: CPU mean 52 to 56 %, max 55 to 63 %; RAM 37 of 59 MB. One minute reached max 81 % (mean 60 %) while the web pages were being read | The base runs at about half of its CPU while doing nothing, and a small extra job raises it clearly. Its log keeps only about 45 minutes, so it does not cover the stalls measured earlier today |

What was found (step 4, web):

- Firmware. `I.0.0` is the newest Create 3 release; there is no Jazzy firmware. The release notes list Fast-DDS 2.10.1 on the base, say it "appears to be fully compatible with ROS 2 Jazzy", and list no known issues ([I.0.0 release notes](https://iroboteducation.github.io/create3_docs/releases/i_0_0/), [release overview](https://iroboteducation.github.io/create3_docs/releases/overview/)). A firmware update is therefore not an option.
- Known issue that matches. In [create3_docs issue 381](https://github.com/iRobotEducation/create3_docs/issues/381) (open), an iRobot developer summarises one case as: Create 3 "hits 100% CPU usage when new ROS 2 nodes are created in the same network (even if they don't communicate with the robot)", with both Fast DDS and Cyclone DDS. Other users report stop-start motion under ROS 2 traffic. iRobot later cut base load by about 9 % in G.5.2 and H.2.2; no fix for the join case is listed.
- TurtleBot 4 networking ([networking page](https://turtlebot.github.io/turtlebot4-user-manual/setup/networking.html)). Simple discovery "requires significant baseline network traffic" and can raise CPU use on each device; discovery server mode has much lower baseline traffic and is recommended for complex functions such as navigation. In both Jazzy modes the Create 3 stays off the Wi-Fi.
- Discovery server setup ([discovery server page](https://turtlebot.github.io/turtlebot4-user-manual/setup/discovery_server.html)): `turtlebot4-setup`, ROS Setup, Discovery Server, Enabled `True`, port `11811`, server ID `0`, apply. The manual also says to update the base firmware and factory reset it first. In [turtlebot4 issue 689](https://github.com/turtlebot/turtlebot4/issues/689) a Jazzy user's Nav2 problems were solved by this mode.
- What the setup tool does in that mode (source: [`turtlebot4_setup` script, `update_create3`](https://github.com/turtlebot/turtlebot4_setup/blob/jazzy/turtlebot4_setup/turtlebot4_setup) and [`conf.py`](https://github.com/turtlebot/turtlebot4_setup/blob/jazzy/turtlebot4_setup/conf.py)): it sets `ROS_DISCOVERY_SERVER="127.0.0.1:11811;"` on the Pi and `ROS_SUPER_CLIENT=True` only in interactive terminals (`[ -t 0 ]`); installs and starts `discovery.service`; then sends the base: discovery server on at `192.168.186.3:11811`, the profile `fastdds_discovery_create3.xml` as the RMW override, the NTP line above, and a base reboot.
- Why that helps. With discovery server version 2 a node "will not receive every topic data unless it has a reader in that topic", while a super client receives everything ([Fast DDS 2.10 docs](https://fast-dds.docs.eprosima.com/en/2.10.x/fastdds/ros2/discovery_server/ros2_discovery_server.html)). The base would then hear from the server instead of from every new Pi participant directly.
- Create 3 Wi-Fi. In [turtlebot4 issue 629](https://github.com/turtlebot/turtlebot4/issues/629), Clearpath support asks users to disconnect the base from Wi-Fi with "Forget Wi-Fi Network" and to disable diagnostics to save CPU.
- `RemoveIPC`. [turtlebot4 issue 559](https://github.com/turtlebot/turtlebot4/issues/559) and the `turtlebot4_setup` 2.0.3 changelog confirm the shared-memory problem fixed here by R18.

Candidate causes, ranked (inferred from the numbers, not proven):

1. **Discovery load on the base in simple discovery mode (most likely, for the 1 to 12 s stalls).** Every new Pi participant announces itself by multicast on `usb0`, and the base's Fast DDS must exchange participant and endpoint data with it directly. This fits the measurements: stalls follow joins within 0.8 to 14.7 s and end within about 17 s; a node with more endpoints stalls the base more often (`ros2 topic list --no-daemon` 1 of 8, bare node 3 of 8, `/odom` subscriber 5 of 8); the base stops producing and its ping time rises, which points to a busy base, not the network. It also matches iRobot's own description in issue 381 and a base that idles at about 55 % CPU. Not explained: why the `/odom` subscriber is so much worse than a bare node, which has nearly the same number of endpoints (one run each).
2. **The base's Wi-Fi search loop (possible contributor).** A scan and DHCP attempt every 7.5 s costs CPU on a base with little headroom. On its own it does not explain why stalls follow joins.
3. **Motion start on a busy base (for the short 0.5 to 0.8 s pauses).** These come right at motion start without a join (TB-15). Only less load can help here (changes A and B); no setting addresses it directly.

Ruled out or unlikely: the republisher settings (Jazzy default), the Create 3 settings (they match simple discovery mode), old firmware (none newer), the Wi-Fi link and Pi CPU (earlier updates), and shared-memory removal (fixed by R18).

**Proposed change A (small, do first): remove the saved Wi-Fi network from the base.** Status: proposed, not applied; needs Ibrahim's OK.
- Commands, from a robot terminal (laptop terminal, then `ssh -i ~/.ssh/turtlebot4_ed25519 ubuntu@192.168.100.31` on the home Wi-Fi; on campus see [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md)). Robot docked, no motion:
  ```bash
  curl -s -m 10 http://192.168.186.2/logs-raw | grep -c 'CTRL-EVENT-SCAN-STARTED'
  curl -s -m 10 -X POST http://192.168.186.2/api/forget-wifi
  ```
  The second line is the same call as the base's "Beta Features, Forget Wi-Fi Network" button. Record the time.
- Verify: after 5 minutes `curl -s -m 10 http://192.168.186.2/logs-raw | grep -E 'SCAN-STARTED|sending discover' | tail -n 3` shows no new lines after the recorded time, and `curl -s -m 10 http://192.168.186.2/logs-raw | grep 'CPU usage' | tail -n 5` shows the base's idle CPU (today a mean of 52 to 56 %). Then run the join test below and compare with run B.
- Undo: connect the base to the network again on its web page, Connect (needs that network's name and password; which network it is was not visible). Normally not wanted, since the Jazzy setup keeps the base offline.
- Risk: low. The base may restart its network service. The `usb0` link to the Pi does not use Wi-Fi.

**Proposed change B (main fix): switch the robot to the TurtleBot 4 discovery server mode.** Status: proposed, not applied; needs Ibrahim's OK and his sudo password. Do it after change A and its join test, so the effect of each is known.
- Commands, in a robot terminal as above, robot docked:
  ```bash
  cp /etc/turtlebot4/setup.bash ~/setup.bash.before-tb25-ds
  turtlebot4-setup
  ```
  In the menu: ROS Setup, Discovery Server, Enabled `True`, Onboard Server Port `11811`, Server ID `0`, Offboard IP left blank, Save; back to the main menu, Apply settings (asks for the sudo password), Exit. This restarts `turtlebot4.service`, starts `discovery.service`, writes the base settings listed above and reboots the base. When the base chimes:
  ```bash
  turtlebot4-source
  turtlebot4-daemon-restart
  ```
  The manual's factory reset of the base is not needed because the setup tool rewrites every base setting it owns (domain, namespace, RMW, discovery server, RMW profile, NTP). If the base does not come back, factory reset it and apply again, as the manual says.
- Verify: `systemctl is-active discovery` prints `active`; `grep -E 'DISCOVERY|SUPER' /etc/turtlebot4/setup.bash` shows `127.0.0.1:11811;` and the `[ -t 0 ]` line; the base's `/ros-config` page shows the box ticked and `/rmw-profile-override` shows the profile (`curl -s http://192.168.186.2/ros-config | grep 'id="fast_discovery_server_enabled"'` contains `checked`); `ros2 topic list` shows `/odom`; `ros2 topic hz /odom` is about 20 Hz. Then the join test below, then a full power cycle (Pi and base) and `ros2 topic hz /odom` again, because [turtlebot4 issue 629](https://github.com/turtlebot/turtlebot4/issues/629) reports the base link lost after power cycles in this mode on Humble. Last, 10 supervised motion starts (step 1) with the start-up wait kept as it is.
- Undo: `turtlebot4-setup`, ROS Setup, Discovery Server, Enabled `False`, Save, Apply settings. This removes `discovery.service`, sets `ROS_DISCOVERY_SERVER` empty and `ROS_SUPER_CLIENT` False, and writes the base back to the values in the table above (discovery server off, empty RMW profile). If needed also `cp ~/setup.bash.before-tb25-ds /etc/turtlebot4/setup.bash` and `sudo systemctl restart turtlebot4`.
- Risks: the base and the ROS bringup restart (docked, no motion). Every ROS program on the robot depends on the discovery service from now on (it restarts on failure). Programs started over SSH without a terminal (TurtleBot Studio, the timing recorder) are not super clients, so they see only the topics they use: running programs works, but Studio's Topics list and the `ros2` CLI inside scripts may show fewer topics and need checking. A laptop running ROS 2 would need the manual's `configure_discovery.sh`. Not proven to remove the stalls: the base's nodes also use the global `/rosout` and `/parameter_events` topics, so the server may still tell the base about some new nodes. The join test decides.

Join test for both changes (the run B method, docked, no motion, about 15 minutes). Copy the recorder and create the joiner on the robot (from the repo's `TurtleBot/tools/timing` folder on the laptop):
```bash
scp -i ~/.ssh/turtlebot4_ed25519 record_timing.py ubuntu@192.168.100.31:/tmp/
```
Then in a robot terminal:
```bash
cat > /tmp/tb25_joiner.py <<'EOF'
import time, rclpy
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
rclpy.init()
node = rclpy.create_node('tb25_joiner')
count = [0]
node.create_subscription(Odometry, '/odom', lambda m: count.__setitem__(0, count[0] + 1), qos_profile_sensor_data)
end = time.time() + 5
while time.time() < end:
    rclpy.spin_once(node, timeout_sec=0.1)
print('odom messages in 5 s:', count[0])
node.destroy_node()
rclpy.shutdown()
EOF
source /etc/turtlebot4/setup.bash
nohup python3 /tmp/record_timing.py --light --duration 720 --out /tmp/tb25_after.jsonl > /tmp/tb25_rec.log 2>&1 &
sleep 120; for i in 1 2 3 4 5 6 7 8; do python3 -c 'import time; print("join", time.monotonic())'; python3 /tmp/tb25_joiner.py; python3 -c 'import time; print("leave", time.monotonic())'; sleep 52; done > /tmp/tb25_joins.log 2>&1
```
Copy `/tmp/tb25_after.jsonl` and `/tmp/tb25_joins.log` back with `scp` and run `python analyze_timing.py tb25_after.jsonl` ([tools/timing/README.md](tools/timing/README.md)). Pass, proposed: at most 1 of 8 joins followed by an `/odom` gap over 0.3 s, and no `/odom` or `/dock_status` gap over 1.0 s (run B: 5 of 8, 10.87 s and 12.28 s). One run is a first check, not proof; repeat once before shortening the programs' 20 s start-up wait.

Not proposed now: a smaller republisher list (for example without `imu` or `tf`, if nothing uses them) would cut the data the base sends, and turning diagnostics off (`TURTLEBOT4_DIAGNOSTICS`, the `diagnostics_updater` process used 32 % of one Pi core) would cut Pi load. Both are for later, if the short motion-start pauses remain after A and B. Acceptance criteria: still open; criterion 1 can be ticked only after the join test with change B.

**Update 2026-10-24, change A applied (R19) and join test.** Ibrahim approved change A. It was applied at 16:03:13 robot time (23:03:13 laptop time) with `curl -X POST http://192.168.186.2/api/forget-wifi` from the Pi. The base cleared its saved network, took `wlan0` down and stopped the scan and DHCP loop (no such lines after 20:03:17 base time); its CPU reached max 96 %, mean 61 % in that minute; no base restart. Record: R19 in [MAINTENANCE.md](MAINTENANCE.md#change-register). Then the join test above (the run B method: `--light` recording of 720 s, 120 s baseline, 8 joins of the `/odom` subscriber about 60 s apart), started 16:04:52 robot time, docked, no motion, home Wi-Fi, no other ROS program running (a `ros2` daemon from another session was up throughout).

| Run | Joins followed by a stall (gap over 0.3 s within 17 s) | Longest `/odom` gap | Longest `/dock_status` gap | Gaps not after a join |
|---|---|---|---|---|
| B, before R19 (17:23 laptop time) | 5 of 8 | 10.87 s | 12.28 s | none |
| B, after R19 (23:04 laptop time) | **0 of 8** | 1.27 s (not after a join) | none (largest interval 1.29 s at 1 Hz) | `/odom` 0.35 s at 608.2 s (70 s after join 8; Pi CPU 95 % at that moment, `create3_republisher` 78 % of a core) and 1.27 s at 651.2 s (113 s after join 8; ping to the base 12.9 ms; no correlate found) |

- Recording: 17,248 records, `/odom` 14,224 messages at 19.9 Hz, `/dock_status` 718 at 1.0 Hz, recorder 9.9 % of one core. Ping to the base median 0.46 ms, max 12.9 ms, none lost. Both gaps are "publisher stopped". The joiner received 87, 94, 101, 101, 92, 101, 101 and 101 `/odom` messages in its 5 s (about 100 expected).
- Reading: after R19 no join was followed by a stall, against 5 of 8 in the same test before. If the base still stalled after 5 of 8 joins, 8 clean joins in a row would be very unlikely (about 0.04 % under a simple model of independent joins), but the two runs differ in time of day and background load, so this is a strong hint from one run, not proof. Inferred, not proven: the base's Wi-Fi search loop was a large part of the problem, probably because it ran on the same busy base computer that also has to handle discovery when a node joins. The ranking above changes: cause 2 is now at least as likely a contributor as cause 1.
- Proposed pass check: the join part is met (0 of 8, at most 1 allowed); "no gap over 1.0 s" is not met because of the 1.27 s idle gap, which did not follow a join. Acceptance criteria: still open.
- Change B stays proposed and is not needed for now. Next: (1) repeat the same join test once, docked (about 15 minutes); (2) the 10 supervised motion starts (step 1) with the 20 s start-up wait kept; (3) after the next reboot, check that the base stays off the Wi-Fi (its `/wifi` page shows no IP address and its log has no `SCAN-STARTED` lines); (4) only if join stalls return, change B.
- Files: `tests/logs/2026-10-24_timing_tb25_joins_after_r19.jsonl.gz` with `tests/logs/2026-10-24_timing_tb25_joins_after_r19_joins.log` (join and leave times on the robot's monotonic clock). Temporary files on the robot were removed. Details: [MAINTENANCE.md](MAINTENANCE.md#update-2026-10-24-late-evening-tb-25-change-a-r19-and-join-test-docked-no-motion).

---

### TB-26 Measure Students signal strength on campus

**Priority:** P1 | **Status:** Open (proposed 2026-10-24) | **Depends on:** None

**Goal.** Know how strong the `Students` signal is where the robot sits and drives, and whether it changes with the robot's position.

**Why it matters.** On 2026-10-24 the robot was out of range of `Students`, so the signal could not be measured, and no signal strength is recorded in the journals. The Wi-Fi drops (TB-20) might also have a coverage part. `iw` is not installed, so use the tools that are.

**Steps.** Read only. Needs the robot on campus, on `Students`.

1. Confirm the robot is on `Students`: `nmcli -t -f NAME,DEVICE connection show --active`.
2. `nmcli -f IN-USE,SSID,CHAN,SIGNAL,BARS dev wifi list` (while on `Students` the robot can scan; in hotspot mode it cannot). Note the signal of the access point in use and of the others.
3. `cat /proc/net/wireless`: the link quality and signal level lines for `wlan0` (earlier, in hotspot mode, there was no `wlan0` line).
4. `journalctl -u NetworkManager -b --no-pager | tail -n 100` for roaming or reconnect events; note the times and the robot clock offset.
5. Repeat at the dock and at two places along a planned route, once a minute for five minutes each. Record the numbers with the place and the time.
6. Add the results to the Wi-Fi incident record and to TB-20.

**Acceptance criteria.**
- [ ] Signal values for at least three places are recorded.
- [ ] Any roaming or reconnect events in the same period are listed.

**Risks and rollback.** None; nothing is changed. Do it in the same session as TB-20 steps 5 and 6.

**Estimated effort:** 1 hour on campus.

---

### TB-27 Desktop control app for connecting, file sync and running programs

**Priority:** P1 | **Status:** Built and tested on the robot over the cable 2026-10-24 (no motion); remaining checks listed below | **Depends on:** None | **Owner:** the user

**Update 2026-10-24.** The app is built: [TurtleBot Studio](tools/studio/README.md) in `tools/studio/` (a local web app: Python 3.10+, no installs on the robot, pinned robot host key, no passwords handled). Tabs: Dashboard, Programs, Files, Topics, Tools, and an always-visible E-STOP. Record: [step log](../General%20Tasks/TurtleBot4%20-%20Ethernet%2C%20Wi-Fi%20power%20save%20and%20odometry%20timing.txt) and the "Tested on the robot" section of its README.

Done on 2026-10-24 (over the Ethernet cable, robot docked, no motion):
- [x] Discover and connect (13 ms to the cable candidate, connect 7.2 s).
- [x] Live status at 1 Hz with real values; topics list and watch.
- [x] Sync a test script to the robot, run it with a live log, stop it; a motion run without confirmation is refused.
- [x] Health check (13 checks).
- [x] E-STOP on and off three times (command line, API, UI button); wheels disabled and enabled again, `~/STOP` removed.
- [x] Four bugs found and fixed (Pi CPU use, `/e_stop` service result, narrow-window layout, wrong lidar hint).
- [x] Offline tests: 74 bridge checks and about 100 desktop checks pass.

Remaining:
- [x] Version 1.1 (2026-10-24, docked, no motion): program catalog with explanations, 5 templates (offline simulator results; `my_first_program.py` run on the robot, `spin_in_place.py` refused without confirmation and run with `--dry-run`), battery charging derived from current, Wi-Fi information call. Code tab and Wi-Fi tab built; tested through the API and mock screenshots only.
- [x] Undock and Dock through Studio, and two motion programs through Studio, supervised, over Wi-Fi (2026-10-24, evening). Still open: E-STOP during a move.
- [ ] **Open terminal**, **Set up key login**, **Open in VS Code** buttons.
- [ ] macOS and Linux; Wi-Fi connections over the hotspot and `Students` (the home network was verified 2026-10-24, evening); discovery on other computers.
- [x] Wi-Fi tab "Add to the robot" for real (2026-10-24, evening: `TP-LINK_Extender_5GHz`, joined at once); the Code and Wi-Fi tabs in a real browser; `spin_in_place` and `drive_circle` on the real robot. Four bugs found and fixed (Windows hid the Wi-Fi name without Location services; the terminal window closed at once; the script got wrong arguments; the confirm text gave the wrong password order). See [tools/studio/README.md](tools/studio/README.md#evening-session-2026-10-24-home-wi-fi-and-supervised-motion).
- [ ] Wi-Fi tab "Remove" for real; the other motion templates on the real robot.
- [ ] Fix: in a narrow window (about 800 px) the confirm dialogs overflow past the right edge.
- [ ] Fix: **Save and Run** writes a `.bak` copy even when the file is unchanged, so deleting a program leaves `<name>.py.bak` behind.
- [ ] Fix: option B offers "Add Students" even when the robot already has it saved.
- [ ] Runs that keep going on the robot after the connection drops (POSIX path).
- [ ] The GitHub Actions run on Linux.
- [ ] Lower the helper's CPU use: 23 % of one core measured (about 6 % of the Pi), target was 10 %.
- [ ] Documented for new members in the onboarding checklist (TB-14).

**Goal.** One desktop app, usable on Windows, macOS and Linux, that lets a lab member connect to the robot (Wi-Fi, hotspot or Ethernet cable), sync files to `~/robot_code`, run programs, watch their output and stop them safely.

**Why it matters.** Connecting today takes many manual steps and several address forms (name, display address, `10.42.0.1`, `192.168.185.3`, IPv6 link-local). The connect tool ([tools/connect/README.md](tools/connect/README.md)) covers connecting and an emergency stop but not file sync or running programs, and has not yet been used with the real robot (TB-23).

**Steps.** To be planned by the owner. Starting points, each **[to verify]**:

1. List what the connect tool already does and reuse it (host-key pinning, emergency stop, key login).
2. Decide the scope of the first version: connect and find, send files, run a program detached with a live log, stop (the `~/STOP` file), and a visible "robot status" line.
3. Support all connection forms, including the Ethernet cable ([HOW-TO-CONNECT.md](HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed)).
4. Write the design here and have it approved before building. No passwords stored in the app or the repository.

**Acceptance criteria.**
- [ ] A written design is approved.
- [ ] A first version connects over each connection form, copies a file, runs and stops a program on the real robot.
- [ ] Documented in HOW-TO-CONNECT.md.

**Risks and rollback.** A control app can send motion commands: keep the emergency stop prominent and test motion only supervised.

**Estimated effort:** to be estimated by the owner.

---

## P2: improvements

### TB-28 Decide whether the robot installs Ubuntu updates by itself

**Priority:** P2 | **Status:** Open (proposed 2026-10-24, evening) | **Depends on:** None

**Goal.** A recorded decision on whether the lab robot lets Ubuntu download and install updates by itself, and what is done about it.

**Why it matters.** When R16 gave the robot internet for the first time since 2026-10-04, Ubuntu's `apt-daily` and `apt-daily-upgrade` timers fired at 21:49:23 robot time. `unattended-upgrade --download-only` then ran at 100 % of one core (nice 19) from 21:50 and was still running at 22:35 robot time (45 minutes). The Pi CPU was 45 to 50 % and the temperature 65 to 72 degrees C while docked. The allowed origins are Ubuntu only (`noble`, `noble-security`, ESM), not the ROS repository. It was not stopped or changed. The load can disturb timing measurements (TB-25), and the upgrade step can install Ubuntu packages while ROS runs. Automatic reboot is off by default.

**Update 2026-10-24, late evening.** An automatic update ran during a session: `unattended-upgrade` was found installing at 15:18 laptop time (08:18 robot; about 50 min in, load average 2.8) and finished at 16:11:40 laptop (09:11:40 robot). `dpkg.log` shows 240 package upgrades that day, among them `linux-firmware`, `util-linux`, the GCC 13 cross compilers, `linux-libc-dev` and a new kernel package; `/var/run/reboot-required` lists `linux-image-6.8.0-1065-raspi` and `linux-base`. Automatic reboot is off, so the next reboot will be the first run on that kernel (re-check R14, R17 and R18 after it). systemd stopped and started the ROS bringup (`turtlebot4.service`) at least 8 times during the update (inferred, not confirmed: services restarted after libraries were replaced). Nothing was stopped or changed by us. Details: [MAINTENANCE.md, Known issues](MAINTENANCE.md#known-issues).

**Steps.** Nothing here has been done; each change needs the lab supervisor's approval and an entry in MAINTENANCE.md with verify and undo.

1. Read only: `cat /etc/apt/apt.conf.d/20auto-upgrades`, `systemctl list-timers apt-daily*`, `pgrep -a unattended-upgrade`, and the log in `/var/log/unattended-upgrades/` after the job has finished. Note how many packages it wants and whether any touch ROS, the kernel or networking. **[to verify]**
2. Weigh the options:
   - **Leave as is.** The robot patches itself whenever it has internet; extra CPU load for some minutes to hours, and packages can change under a running robot.
   - **Turn the timers off** and update by hand in a planned maintenance window, with an SD card backup first (TB-07).
   - **Allow security updates only,** at a fixed hour when the robot is not in use. **[to verify]** that the configuration can restrict this on this image.
3. Record the decision, the date and who made it here and in MAINTENANCE.md (Known issues row on automatic updates), and apply it with an undo.

**Acceptance criteria.**
- [ ] The decision is recorded with the date and who made it.
- [ ] If changed: the MAINTENANCE.md register has the change with verify and undo.
- [ ] Timing measurements are only run when no update job is running (check with `pgrep -a unattended-upgrade`).

**Risks and rollback.** Step 1 changes nothing. Turning timers off means no automatic security patches; the robot is on the campus network and TB-05 (security hardening) should be planned with this. Rollback: switch the timers on again.

**Estimated effort:** 30 minutes to read and decide; 30 minutes to apply.

---

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

**Update 2026-10-10.** On 2026-10-04 `turtlebot4.local` failed to resolve intermittently on the campus Wi-Fi, so the display address is the reliable method for now. The address was again `10.87.10.205` on 2026-10-04. A DHCP reservation on the lab's own router is an alternative to an IT reservation on `Students` ([TB-21](#tb-21-decide-the-robots-network-students-or-the-lab-router)).

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

**Update 2026-10-10.** Still not tested. mDNS failed intermittently on campus on 2026-10-04. The lab router (TB-21) is expected to make discovery between a laptop and the robot likely to work, because there is no campus Wi-Fi in between; not tested either.

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

**Update 2026-10-10.** A second Wi-Fi problem, the main one of that week, appeared on 2026-10-04 and 2026-10-05: the robot answered SSH only in short windows ([TB-20](#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving)). Roaming, the subject of this task, is the third likely cause in that list. Detached runs remain the workaround for drops during motion.

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

**Priority:** P2 | **Status:** In progress (2026-10-03; docs updated 2026-10-10; hands-on and lidar guides added 2026-10-10) | **Depends on:** None

**Update 2026-10-10 (later).** Added guides written for any lab member: [docs/do-it-yourself.html](docs/do-it-yourself.html) ([Markdown](docs/DO-IT-YOURSELF.md)), [docs/lidar-guide.html](docs/lidar-guide.html) ([Markdown](docs/LIDAR-GUIDE.md)), and the interactive [motion simulator](docs/motion-simulator.html) and [docking explainer](docs/docking-explained.html). They are linked from README.md, HOW-TO-CONNECT.md and the docs index.

**Goal.** Documentation that any lab member can follow on any laptop, with the configuration and change history kept separately.

**Why it matters.** The first guide was written for one person's laptop (its shortcuts, SSH aliases and second Wi-Fi adapter).

**Progress 2026-10-10.** Steps 1 to 3 are done. The docs were brought up to date with the week of 2026-10-04 to 2026-10-10: network and connectivity page, Wi-Fi troubleshooting in HOW-TO-CONNECT.md, connect tool in the README quick start, consistent statuses across all files. Still open: a new lab member trying the guide (first criterion).

**Steps.**
1. Rewrite [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) as a general user guide, and add [README.md](README.md) as the entry point.
2. Move the configuration record, the change register with undo steps, the incident report on the clock and the Create 3 base, and the known issues to [MAINTENANCE.md](MAINTENANCE.md).
3. Keep this roadmap for open work.

**Acceptance criteria.**
- [ ] A new lab member can connect and run `hello_robot.py` using only README.md and HOW-TO-CONNECT.md.
- [x] No step in the user guide depends on one person's workstation. (Reviewed 2026-10-10: the main flows use `ubuntu@turtlebot4.local` or the address on the display; the SSH config shortcut is optional.)
- [x] Every change made to the robot so far appears in MAINTENANCE.md with verify and undo steps. (2026-10-10: R1 to R13; no robot change since 2026-10-04.)
- [x] Links between the four documents work. (2026-10-10: a link check of every Markdown and HTML file under `TurtleBot/` found 0 broken relative links or anchors.)

**Risks and rollback.** Documentation only; Git history keeps earlier versions.

**Estimated effort:** in progress; about half a day in total.

---

### TB-12 Documentation follow-ups

**Priority:** P2 | **Status:** In progress (2026-10-10) | **Depends on:** TB-11

**Goal.** Keep the documentation accurate and easy to follow over time.

**Why it matters.** Several open tasks need someone to find a cable or button quickly, and the docs will drift as the robot changes and people leave.

**Progress 2026-10-10.** Stale statements corrected (step 3): the claim that `~/robot_code` holds copies of every program in `examples/` (only R4 and R11 are there; R12 is not applied); the 2026-10-04 run summary in HOW-TO-CONNECT.md, which left out the triangle and the figure eight; the TB-19 status (the script exists); the 2026-10-03 log's pointer to a HOW-TO-CONNECT section that moved to MAINTENANCE.md (a correction note was appended to the log). Step 6 was added after the 2026-10-05 repository incident.

**Steps.**
1. Add photos (in a folder such as `TurtleBot/images/`) of: the robot's display and buttons; the lidar USB cable at both ends and the Pi's USB ports; the USB-C link to the base (to avoid unplugging it); access to the SD card. Check that no password label, screen with secrets, or person is visible.
2. Keep MAINTENANCE.md current after every change, and this roadmap after every task.
3. Correct stale statements when found. For example, the "next steps" plan at the end of the General Tasks log predates the Wi-Fi switch.
4. When the original author leaves: remove workstation-specific notes (desktop shortcuts, second Wi-Fi adapter, their SSH aliases), and remove their public key from the robot (see TB-05). Record both in MAINTENANCE.md.
5. Make the example programs neutral where they include a person's name (for example the message in `hello_robot.py`).
6. Added 2026-10-10: work on a branch, and merge it into `main` when it is finished; GitHub's `main` is what lab members read. Commit or discard changes before switching branches (lesson of the 2026-10-05 branch switch, [MAINTENANCE.md](MAINTENANCE.md#repository-note-branch-switch-in-github-desktop-2026-10-05-resolved-2026-10-10)). As seen on 2026-10-10, the TurtleBot work from a8c0b4e (2026-10-04) on is on `turtlebot/lidar-check-and-motion-programs` and not yet on `main`. Done later on 2026-10-10: the branch, including the finished connect tool 1.1.0, was merged into `main`.

**Acceptance criteria.**
- [ ] The photos are in the repo and linked from HOW-TO-CONNECT.md or MAINTENANCE.md.
- [ ] MAINTENANCE.md matches the robot (spot-check three entries).
- [ ] No workstation-specific notes remain once the original author has left.
- [x] The finished TurtleBot work is merged into `main`, and every link in `main` points at a file that exists on `main` (2026-10-10; link check of every TurtleBot Markdown and HTML file: 0 problems).

**Risks and rollback.** Documentation only, apart from the key removal in step 4 (reversible by re-adding the key).

**Estimated effort:** 2 hours, then a few minutes per change.

---

### TB-15 Characterise the /odom pauses at motion start

**Priority:** P2 | **Status:** In progress (2026-10-04; 2026-10-24: cause located in the base, triggered by motion start) | **Depends on:** None

**Goal.** Know when, how often and why the Create 3 base stops publishing `/odom` for 0.4 to 1.0 s, and make sure the example programs handle it.

**Why it matters.** The first `motion_shapes.py` runs aborted on stale odometry. An instrumented 10 cm move showed a 0.413 s gap in arrival and a 0.419 s gap in header stamps 0.12 s after the wheels started, so the base itself pauses. A triangle run later hit a 1.0 s gap at a segment change with a Pi load average of 3.4. No gap was seen with the robot still (19.98 Hz, largest gap 0.064 s). Details: [MAINTENANCE.md](MAINTENANCE.md#finding-odom-pauses-at-motion-start).

**Update 2026-10-24.** A supervised run with the timing recorder (`tools/timing/record_timing.py`, 300 s, 33,324 records) found: all base topics (`/odom`, `/tf`, `/imu`, `/wheel_status`) stall together, their header stamps stop too, the ping round-trip time to the base rises (21 to 27 ms against a median of 0.5 ms), and the Pi stayed at 61 % CPU or less. Stalls: 1.39 s at undock motion start (33.76 s into the recording) and 3.16 s 2.0 s after a forward drive started (178.51 s), followed by gaps of 0.49 to 1.50 s until about 185 s. The 3.16 s gap aborted `motion_shapes.py` (stale limit 2.0 s). So steps 2 (other topics) and part of step 1 are done, and the cause is in the base and triggered by motion start; it is not the Wi-Fi and not Pi overload. Inferred, not proven: load or blocking inside the Create 3 when the motors start. Later on 2026-10-24, with the robot docked and idle, `/odom` age reached 1.75 s once while a template program and Studio's helper were running, so a stall can also happen without motion. Why is now [TB-25](#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving). Details: [MAINTENANCE.md](MAINTENANCE.md#update-2026-10-24-measurements-with-the-timing-recorder). Note that a 2.0 s stale limit is shorter than the longest stall seen (3.16 s); do not raise it without a decision, since it is a safety stop.

**Steps.**

1. Log `/odom` arrival time and header stamp during repeated short moves (start, stop, turn), with and without the camera running, and note the Pi load (`uptime`).
2. Check whether other base topics (for example `/imu`, `/wheel_vels`) pause at the same moments. **[to verify]** topic names on this robot.
3. Look for known reports in the Create 3 and TurtleBot 4 issue trackers and release notes.
4. Record gap length, frequency and conditions in [docs/test-results.html](docs/test-results.html) and MAINTENANCE.md.
5. Keep the program-side handling (hold at 0.3 s, abort at 2.0 s) unless the data shows a better threshold.

**Acceptance criteria.**
- [ ] Gap statistics over at least 20 motion starts are recorded. (_Placeholder: test campaign numbers_)
- [ ] The likely cause is stated with its evidence, or "unknown" with what was ruled out.
- [ ] Example programs that drive the robot tolerate the measured gaps.

- Note 2026-10-24 (evening): 10 supervised motion starts with the start-up check gave 2 short pauses at motion start (0.52 s and 0.79 s) and 8 with none over 0.3 s; counts toward the 20 starts, not the full campaign. See [TB-25](#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving).

**Risks and rollback.** Short moves only, with the usual safety checklist. No configuration change.

**Estimated effort:** 2 to 3 hours.

---

### TB-16 Motion program test campaign and demo shapes

**Priority:** P2 | **Status:** Open (first runs 2026-10-04; campaign waiting for a supervised session, no runs since 2026-10-04) | **Depends on:** TB-02

**Update 2026-10-10.** No runs since 2026-10-04. On 2026-10-04 an hour-long unattended test campaign run by an AI subagent was blocked by the AI tool's safety guard. Lesson: robot motion tests are run supervised, in short batches, with a person next to the robot; do step 1 that way. The new moving programs must first be copied to the robot ([TB-23](#tb-23-first-robot-run-of-the-new-programs-and-the-connect-tool)), and the robot must stay reachable ([TB-20](#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving)).

**Goal.** Every shape in `motion_shapes.py` (and the other moving examples) has a recorded, repeatable result, including a floor measurement, so lab members can use them as demos and as a starting point.

**Why it matters.** On 2026-10-04 square, rotate and back-and-forth completed with odometry end errors under 1 cm and 1 degree, triangle completed after the second odometry fix (1.0 cm, +2.2 deg, with three short holds) and figure eight aborted on a 2.0 s odometry gap (robot held still), the safety stops have not all been exercised, and the real (floor) error was not measured.

**Steps.**

1. Run each shape at least three times, detached, from the same taped start mark. Record duration, odometry end error and the measured floor error.
2. Exercise each safety stop once: obstacle in front, `~/STOP`, Ctrl+C, `pkill -INT`, lift (wheel drop), and a dry run on the dock (must refuse a real run).
3. Fill the runs table in [docs/test-results.html](docs/test-results.html) and update the status block in [examples/README.md](examples/README.md).
4. Pick one or two shapes as the standard lab demo and write the exact command in HOW-TO-CONNECT.md.

**Acceptance criteria.**
- [ ] Every shape has at least three recorded runs with odometry and floor error. (_Placeholder: test campaign results_)
- [ ] Every safety stop has been triggered once and stopped the robot.
- [ ] The results page and the examples README are updated.

**Risks and rollback.** Collision: speed is capped at 0.15 m/s, lidar front stop active, a person stands next to the robot. No configuration change.

**Estimated effort:** half a day.

---

### TB-18 Lidar cable strain relief and label

**Priority:** P2 | **Status:** Open (proposed 2026-10-04) | **Depends on:** None

**Goal.** The lidar USB cable cannot work loose easily, and anyone can identify it quickly.

**Why it matters.** A loose lidar USB cable caused the lidar outage from 2026-10-03 to 2026-10-04 (TB-02). The same fault is likely to return as the robot moves and is handled.

**Steps.**

1. With the robot shut down, photograph the lidar cable at both ends and its route (a TB-12 item). Check that no password label or screen is visible.
2. Add strain relief with a cable tie or clip so the plugs are not pulled by the cable's weight. Do not block the lidar's view or the moving parts, and do not touch the USB-C link to the base.
3. Label the cable "LIDAR USB" at the Pi end.
4. Boot, undock and check `/scan` (MAINTENANCE.md verification step 6).
5. Add the photos to the repo and record the change in MAINTENANCE.md.

**Acceptance criteria.**
- [ ] Strain relief and label fitted; photos in the repo.
- [ ] `/scan` publishes off the dock after the change.
- [ ] Recorded in MAINTENANCE.md.

**Risks and rollback.** Pulling the wrong cable can cut the base link or the camera; identify the cable first. Rollback: cut the tie.

**Estimated effort:** 30 minutes.

---

## P3: nice to have

### TB-13 Teleoperation how-to

**Priority:** P3 | **Status:** Open (command-line driving documented 2026-10-10; keyboard teleop not yet) | **Depends on:** TB-01

**Update 2026-10-10.** Step 8 of [docs/do-it-yourself.html](docs/do-it-yourself.html) now documents driving by hand from the command line (`ros2 topic pub` with `TwistStamped`, and the `drive_distance` and `rotate_angle` actions, with a speed-capped command builder). Those commands are not yet tested on this robot. Keyboard teleop (this task) is still to do.

**Note 2026-10-24.** Keyboard teleoperation could become a tab in [TurtleBot Studio](tools/studio/README.md) (TB-27), with its E-STOP always within reach. Not planned yet.

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

**Priority:** P3 | **Status:** In progress (do-it-yourself guide written 2026-10-10; not yet tried by a new member) | **Depends on:** TB-05, TB-11

**Update 2026-10-10.** [docs/do-it-yourself.html](docs/do-it-yourself.html) ([Markdown](docs/DO-IT-YOURSELF.md)) covers most of the suggested items as eleven steps with progress checkboxes, and README.md's quick start links to it. Still open: access to the password manager entries and the rule for recording changes (step 1 items), and step 2 (a new member follows it and gives feedback).

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

### TB-19 Read-only health check script

**Priority:** P3 | **Status:** Prepared (proposed and written 2026-10-04 as [examples/health_check.py](examples/health_check.py), tested offline; first robot run pending, part of [TB-23](#tb-23-first-robot-run-of-the-new-programs-and-the-connect-tool)) | **Depends on:** None

**Goal.** One command on the robot runs the [MAINTENANCE.md verification checklist](MAINTENANCE.md#verification-checklist) and prints pass or fail per item.

**Why it matters.** On 2026-10-04 the lidar check took a dozen separate commands, and two of them needed retries because of command-line gotchas (128-entry truncation, a missing `--qos-reliability` option). A script makes the check quick and repeatable for anyone.

**Steps.**

1. Write `health_check.py` in [examples/](examples/) (written 2026-10-04, tested offline; first robot run pending): Wi-Fi profile and address, `turtlebot4` active, ROS environment, `/dock_status`, lidar device and (off the dock only) `/scan` rate and beam count, clock and clock-fix files. Read only: no `sudo`, no motion.
2. Test it docked and undocked, and add sample output to the examples README.

**Acceptance criteria.**
- [ ] The script runs without `sudo` and changes nothing.
- [ ] Its output matches a manual run of the checklist.

**Risks and rollback.** Read only. Delete the file to roll back.

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
| [2026-10-04 log](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt) | Lidar check and motion programs, including what failed |
| [2026-10-24 log](../General%20Tasks/TurtleBot4%20-%20Ethernet%2C%20Wi-Fi%20power%20save%20and%20odometry%20timing.txt) | Ethernet access, the Wi-Fi power-save change (R14), the supervised motion test with the timing recorder, including what failed |
| [Network log](../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt) | Wi-Fi drops, lab router and repository incident, 2026-10-04 evening to 2026-10-10, including what failed |
| [docs/](docs/index.html) | Illustrated pages: lidar diagnosis, motion program design, test results, network and connectivity |
| [docs/network-and-connectivity.html](docs/network-and-connectivity.html) | The Wi-Fi drops, likely causes, fix and workarounds, the lab router and the proposal (TB-20 to TB-22). Markdown version: [docs/NETWORK-FINDINGS.md](docs/NETWORK-FINDINGS.md) |
| [examples/README.md](examples/README.md) | How to run the example programs safely, including `motion_shapes.py` |
| [tests/](tests/) | Test campaign for the example programs |
| [setup/](setup/) | Scripts used to configure the robot, including `undo-clock.sh` |
| [examples/](examples/) | Example programs and `motion_test.sh` |
| [turtlebot4-field-guide.html](turtlebot4-field-guide.html) | Background on the platform, ROS 2 concepts and commands |
| [Official TurtleBot 4 user manual](https://turtlebot.github.io/turtlebot4-user-manual/) | Vendor documentation, including powering off and setup |
