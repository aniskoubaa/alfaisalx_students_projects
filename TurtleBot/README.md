# TurtleBot 4

The lab's TurtleBot 4 robot: an app to control it, guides, example programs and setup records.

## About this project

This folder holds everything the AlfaisalX lab has built and written for its TurtleBot 4 Standard: a Raspberry Pi 4 on an iRobot Create 3 base, Ubuntu 24.04 Server, ROS 2 Jazzy, with a lidar and an OAK-D camera.

Three things live here:

- **TurtleBot Studio**, a desktop app that finds the robot, shows what it sees, runs programs, lets you drive it and has an emergency stop. Students do not need Python, ROS or a terminal.
- **Campus food delivery (task TB-29)**: the robot drives food from the food court to the lab along a wall with Nav2, started from a menu on its front panel.
- **Documentation and records**: guides, explanations, findings, example programs, the configuration record and the roadmap.

How the parts fit together: [ARCHITECTURE.md](ARCHITECTURE.md).

## Start here

Pick the line that matches you.

| You are | Go to |
|---|---|
| **A new student** | [Meet the robot](docs/getting-started/meet-the-robot.html) (what the parts do), then [Do it yourself](docs/getting-started/do-it-yourself.md) (power on, connect, first program), then [What you can build](docs/getting-started/what-you-can-build.html). Connection help: [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) |
| **A Studio user** | [Install Studio](#start-here-control-the-robot-with-turtlebot-studio) below, then [First connection](tools/studio/docs/FIRST-CONNECTION.md), [Everyday use](tools/studio/docs/EVERYDAY-USE.md), [Studio 2.1 lab demo](docs/getting-started/studio-lab-demo.md) and [Troubleshooting](tools/studio/docs/TROUBLESHOOTING.md) |
| **A developer** | [ARCHITECTURE.md](ARCHITECTURE.md), [Studio architecture with diagrams](tools/studio/docs/ARCHITECTURE.md), [Studio code map](tools/studio/docs/CODE-MAP.md), [CONTRIBUTING.md](CONTRIBUTING.md), [Studio technical README](tools/studio/README.md), [delivery/README.md](delivery/README.md), [tests/README.md](tests/README.md) |
| **A maintainer** | [MAINTENANCE.md](MAINTENANCE.md) (change register, known issues), [ROADMAP.md](ROADMAP.md) (open tasks), [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md), [network findings](docs/findings/network-findings.md), [setup/](setup/) |

All documents by type (tutorials, guides, explanations, reference, findings): [docs/README.md](docs/README.md), or open [docs/index.html](docs/index.html) in a browser.

## Repository map

```
TurtleBot/
  README.md            this page
  ARCHITECTURE.md      the system at three levels, with diagrams
  CONTRIBUTING.md      where things go and how to work here
  ROADMAP.md           open tasks (TB-nn) and their status
  MAINTENANCE.md       change register, incidents, known issues
  HOW-TO-CONNECT.md    connect from any computer, log in, run code
  Download/            TurtleBot Studio installer for Windows
  docs/                documentation, sorted as tutorials, guides, explanations,
                       reference and findings (see docs/README.md)
    getting-started/   tutorials: meet the robot, do it yourself, Studio demo
    guides/            how-to guides (lidar)
    explanations/      how a command travels, docking, motion program, network
    reference/         test results, parts list, spoken messages
    findings/          lidar and network investigations
    index.html         illustrated hub
  delivery/            campus food delivery (TB-29): mission, menu, Nav2 config,
                       robot scripts, route planner, simulator, voice player
  examples/            example programs for the robot (hello_robot.py, motion_shapes.py, ...)
  setup/               admin scripts used to configure the robot
  tools/
    studio/            TurtleBot Studio: desktop app, interface source, guides
    connect/           connect tool (TurtleBotConnect.exe, connect-turtlebot.sh)
    timing/            /odom timing recorder and analyzer
  tests/
    offline/           offline tests and the simulated robot (no robot needed)
    robot/             diagnostic scripts that run on the robot
    logs/              evidence from real runs
    check_links.py     documentation link check
```

Dated step logs are in `General Tasks/` at the repository root.

## Status at a glance

Details and dates are in [ROADMAP.md](ROADMAP.md) and [MAINTENANCE.md](MAINTENANCE.md). This table summarises those records and is not a new source.

| Area | State | Task |
|---|---|---|
| TurtleBot Studio | Version 2.2.1 installer for Windows in [Download/](Download/README.md). Tested on the real robot in part (a first map made while driving, from the Maps screen, on 2026-11-26); the open checks are under [Not verified yet](tools/studio/README.md#not-verified-yet) in the Studio README | [TB-27](ROADMAP.md#tb-27-desktop-control-app-for-connecting-file-sync-and-running-programs) |
| Campus delivery | Full deliveries have run on the real robot at home from the front-panel menu (2026-11-06). The campus route has not been driven | [TB-29](ROADMAP.md#tb-29-campus-food-delivery-along-the-wall-supervised-demo) |
| Wi-Fi drops | Wi-Fi power saving was switched off (R14, R17, 2026-10-24). Whether that ends the drops can only be checked on campus | [TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving) |
| Base stalls at motion start | Open. Located in the Create 3 base; a new ROS participant can trigger a stall. Studio and the delivery stack keep to one participant | [TB-25](ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving) |
| Spoken messages, voice player | Written and tested offline only. No speaker installed | [spoken-messages.md](docs/reference/spoken-messages.md) |

## Run the offline tests

No robot and no ROS are needed. Use Python 3.10 or newer. From the repository root:

```bash
python TurtleBot/tests/check_links.py                 # documentation links, must report 0 problems
python TurtleBot/delivery/tools/verify_all.py         # linters (if installed), syntax checks and the offline tests
python TurtleBot/tests/offline/test_pure.py           # one test on its own
python TurtleBot/tests/offline/test_sim_runs.py
```

The delivery tests need PyYAML (`python -m pip install pyyaml`). To test the Studio interface, run `npm ci` and then `npm test` in `TurtleBot/tools/studio/ui/`. The full list is in [tests/README.md](tests/README.md) and [tools/studio/README.md](tools/studio/README.md#tests). GitHub runs the same checks on every push that changes this folder. A pass says nothing about the real robot.

## Safety

The robot is shared lab hardware and it moves.

- A person stays next to the robot whenever it moves. Clear about 1 m of floor around it first.
- The red **E-STOP** button is always at the top right of Studio; **Esc** or **Space** also stops the robot.
- Without Studio: `touch ~/STOP` on the robot stops the motion programs and the delivery. Controller button **B** toggles the Create 3 emergency stop (NOT VERIFIED on this robot).
- Start with a dry run (`--dry-run`) where a program has one. Read [examples/README.md](examples/README.md) first.

More: [emergency stop paths](ARCHITECTURE.md#emergency-stop-paths) and [safety before motion](CONTRIBUTING.md#7-safety-before-motion).

## Start here: control the robot with TurtleBot Studio

TurtleBot Studio is a desktop app. It finds the robot, shows what the robot sees, runs programs, lets you drive it and has an emergency stop. You do not need Python, ROS or a terminal.

**[Download TurtleBot Studio for Windows](https://github.com/aniskoubaa/alfaisalx_students_projects/raw/main/TurtleBot/Download/TurtleBotStudio-Setup-2.2.1.exe)** (version <!-- studio-version -->2.2.1<!-- /studio-version -->, <!-- studio-size -->8.9 MB<!-- /studio-size -->). More about the download, and macOS and Linux: [Download/](Download/README.md).

| Step | What to do |
|---|---|
| 1. Install | Open the downloaded file. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**. Click **Next**, **Install**, **Finish** |
| 2. Practice (optional) | Start **TurtleBot Studio (simulated robot)** from the Start menu. It is a pretend robot: click everything, nothing real moves |
| 3. Turn the robot on | Put the robot on its dock. After about 2 minutes it plays a chime and shows its address on its small screen |
| 4. Connect the first time | Plug an Ethernet cable from your computer into the robot. Open **TurtleBot Studio** from the desktop and follow the setup wizard. You need the robot password once: user `ubuntu`, password `turtlebot4`. Step by step: [First connection](tools/studio/docs/FIRST-CONNECTION.md) |
| 5. Every day after that | Open Studio, press **Discover**, then **Connect**. No cable and no password |

**Safety first.** The red **E-STOP** button is always at the top right of Studio; **Esc** or **Space** also stops the robot. Before the robot moves, clear about 1 m of floor around it and stay next to it. Driving by hand is described in [Live view and driving](tools/studio/docs/LIVE-AND-DRIVING.md).

| Guide | When you need it |
|---|---|
| [First connection](tools/studio/docs/FIRST-CONNECTION.md) | The one-time setup over the cable |
| [Everyday use](tools/studio/docs/EVERYDAY-USE.md) | Start, connect, run a program, edit code, move files |
| [Live view and driving](tools/studio/docs/LIVE-AND-DRIVING.md) | See the lidar map, drive with the keyboard or the joystick, charts, events and the robot log |
| [Find the robot](tools/studio/docs/FIND-THE-ROBOT.md) | Studio cannot find the robot, or its address changed |
| [Troubleshooting](tools/studio/docs/TROUBLESHOOTING.md) | Something does not work |

## Everything else (for advanced users and maintainers)

Documentation, example programs and setup scripts for the lab's TurtleBot 4 Standard (Raspberry Pi 4 on an iRobot Create 3 base, Ubuntu 24.04 Server, ROS 2 Jazzy). To connect without the app (ssh, VS Code), start with [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md). Earlier status paragraphs are kept under [Project history](#project-history).

**Quick connect** (details and troubleshooting: [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md)):

| | |
|---|---|
| User name | `ubuntu` |
| Password | `turtlebot4` (the factory default from the [TurtleBot 4 user manual](https://turtlebot.github.io/turtlebot4-user-manual/setup/basic.html); also the `sudo` password). Better: set up [key login](HOW-TO-CONNECT.md#recommended-log-in-with-a-key-instead-of-a-password) once |
| Robot name | `turtlebot4.local` (works on most networks) |
| On the university Wi-Fi `Students` | The address on the robot's display (starts with `10.87.`; it can change) |
| On the robot's own Wi-Fi `Turtlebot4` | `10.42.0.1` |
| Ethernet cable, no setup | `fe80::da3a:ddff:fe41:d5df` plus your interface (see [Option A](HOW-TO-CONNECT.md#option-a-ipv6-link-local-address-no-settings-change-verified-2026-10-24)) |
| Ethernet cable, fixed address | `192.168.185.3` (see [Option B](HOW-TO-CONNECT.md#option-b-give-your-computer-a-fixed-address-on-the-cable-recommended-for-regular-use)) |
| Robot network card (MAC) | `D8:3A:DD:41:D5:DF` |
| Command | `ssh ubuntu@turtlebot4.local`, or `ssh ubuntu@<address>` |

| File | What it is for |
|---|---|
| [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) | Connect from any computer (Windows, macOS, Linux), log in, write and run code, turn the robot off, troubleshoot. **Start here.** |
| [Download/](Download/README.md) | **The TurtleBot Studio installer for Windows** (version 2.1 from 2026-11-14, with mapping, routes and the robot menu page; it replaced version 2.0 from 2026-10-30). Download it from there; no Python needed |
| [tools/studio/](tools/studio/README.md) | **TurtleBot Studio (recommended way to work with the robot).** From version 2.0 (2026-10-30): an installed app with its own window, a live lidar map, driving with the keyboard or a joystick, charts, events and the robot log; technical details in its README. Earlier text: a local app that opens in your browser (`Start TurtleBot Studio.cmd` on Windows, `bash start-studio.sh` on macOS and Linux, or `python studio.py`). Finds the robot over Wi-Fi, hotspot or cable, shows its status, explains each program, copies and runs programs, has a code editor with templates (spin, circle, forward and back) and a Wi-Fi guide, watches topics and has an E-STOP. Nothing is installed on the robot. Built and tested over the cable on 2026-10-24 with the robot docked, no motion; macOS, Linux and Wi-Fi not tested yet |
| [delivery/](delivery/README.md) | **Campus food delivery (ROADMAP TB-29, started 2026-11-03).** The robot maps the route from the food court to the lab, then drives it about 0.5 m from the wall with Nav2, past a glass room it must not enter. The vendor presses front-panel button 3 when the food is on; the student presses 4. Contents: route planner for the laptop, Nav2 settings, start and stop scripts, Phase 0 check scripts and the delivery program. Tested offline only; nothing has run on the robot yet *(superseded: since 2026-11-06 full deliveries run on the real robot at home from a front-panel menu; the campus route is not done yet, see ROADMAP TB-29)* |
| [tools/connect/](tools/connect/README.md) | Connect tool: `TurtleBotConnect.exe` (Windows 10 or 11, no installation) and `connect-turtlebot.sh` (macOS, Linux). A menu that finds the robot, opens a terminal, sets up key login, shows the robot's status, stops the motion programs in an emergency and copies files. Not yet used with the real robot as of 2026-10-10 |
| [tools/timing/](tools/timing/README.md) | Timing recorder and analyzer: records when `/odom` and the other base topics arrive, together with processor load, network counters, ping to the base and Wi-Fi events, then lists every pause and what it coincides with. Read only; run it next to a motion test. First used on the robot on 2026-10-24 (results in [tests/logs/](tests/logs/)) |
| [MAINTENANCE.md](MAINTENANCE.md) | Configuration record: every change made to the robot with verify and undo steps, incident reports (clock fix, lidar, Wi-Fi drops), the lab router, known issues, admin scripts |
| [ROADMAP.md](ROADMAP.md) | Plan for the next iterations (TB-01 to TB-27), including the Wi-Fi fix, the network decision and remote desktop |
| [docs/getting-started/field-guide.html](docs/getting-started/field-guide.html) | Beginner overview of the hardware and ROS 2 (open it in a browser) |
| [examples/](examples/) | Example programs. Copies of the first six (`hello_robot.py` to `motion_shapes.py`) are in `~/robot_code` on the robot; the newer ones are not on the robot yet (2026-10-10) |
| [examples/README.md](examples/README.md) | How to run each example safely: undock and dock, `motion_shapes.py` (square, triangle, rotate, back-and-forth, figure eight), how to stop the robot, troubleshooting |
| [examples/health_check.py](examples/health_check.py) | One-command robot health checklist (Wi-Fi, ROS service, base, clock, lidar, odometry gaps, temperature, disk). Read only. How to run it: [examples/README.md](examples/README.md#health_checkpy-read-only-health-checklist). Tested offline; first robot run pending |
| [tests/](tests/README.md) | Robot run logs, diagnostic scripts, and offline tests that check the example programs on any computer (101 logic checks and 38 simulated runs; also run automatically on GitHub by [.github/workflows/turtlebot-tests.yml](../.github/workflows/turtlebot-tests.yml)) |
| [docs/](docs/index.html) | Illustrated pages (open in a browser): start at [docs/index.html](docs/index.html) |
| [docs/getting-started/studio-lab-demo.md](docs/getting-started/studio-lab-demo.md) | **Studio 2.1 quick guide for a lab demo (2026-11-25):** install Studio, connect over the campus Wi-Fi, what each screen does, map a room, put a route on the robot and run the delivery from the front panel. Interactive version with checklists: [docs/getting-started/studio-lab-demo.html](docs/getting-started/studio-lab-demo.html) |
| [docs/getting-started/meet-the-robot.html](docs/getting-started/meet-the-robot.html) | **Meet the robot:** click a part of the TurtleBot 4 to see what it does, its ROS 2 topics and how to try it; what works and what is being fixed (interactive; for visitors, new students and reviewers) |
| [docs/explanations/how-a-command-travels.html](docs/explanations/how-a-command-travels.html) | **How a command travels:** one drive command from a program to the wheels and back as `/odom`, step by step, and why a starting program could pause the base (TB-25) |
| [docs/getting-started/what-you-can-build.html](docs/getting-started/what-you-can-build.html) | **What you can build:** project ladder from a first program to mapping and navigation, with filters, a project picker and what is tested on this robot |
| [docs/getting-started/do-it-yourself.html](docs/getting-started/do-it-yourself.html) | **Do it yourself, with no AI help:** power on, Wi-Fi, SSH, getting your code onto the robot, sensors, undock, drive, dock, stop and a first program, for Windows, macOS and Linux (interactive; Markdown version: [docs/getting-started/do-it-yourself.md](docs/getting-started/do-it-yourself.md)) |
| [docs/guides/lidar-guide.html](docs/guides/lidar-guide.html) | **Lidar user guide:** how the RPLIDAR works, one scan field by field, the 90 degree mounting, a lidar explorer, the commands to get the data, and Python code to use it (interactive; Markdown version: [docs/guides/lidar-guide.md](docs/guides/lidar-guide.md)) |
| [docs/explanations/motion-simulator.html](docs/explanations/motion-simulator.html) | Interactive simulator of `motion_shapes.py`: watch the robot drive a square or other shape, the speed commands, the lidar stop zone and odometry dropouts, compared with the real runs |
| [docs/explanations/docking-explained.html](docs/explanations/docking-explained.html) | How the robot finds its dock (infrared signals, the docking stages, undocking), as a simplified interactive animation, plus the dock and undock commands |
| [docs/explanations/network-and-connectivity.html](docs/explanations/network-and-connectivity.html) | The networks around the robot, the Wi-Fi drops of 2026-10-04 and 2026-10-05, likely causes, the proposed fix, workarounds, and the lab router proposal. Markdown version: [docs/findings/network-findings.md](docs/findings/network-findings.md) |
| [docs/findings/lidar-diagnosis.html](docs/findings/lidar-diagnosis.html) | How the "lidar not detected" fault was diagnosed and fixed on 2026-10-04, with the measured values. Markdown version: [docs/findings/lidar-findings.md](docs/findings/lidar-findings.md) |
| [docs/explanations/motion-program-design.html](docs/explanations/motion-program-design.html) | How `motion_shapes.py` works: segment planner, controller, safety layers, the `/odom` pause finding, parameters |
| [docs/reference/test-results.html](docs/reference/test-results.html) | Results of the motion program runs |
| Step logs | Dated logs including what failed: [2026-10-03 Wi-Fi setup](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt), [2026-10-04 lidar and motion programs](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt), [2026-10-04 to 2026-10-10 network and connectivity](../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt), [2026-10-24 Ethernet, Wi-Fi power save, odometry timing and TurtleBot Studio](../General%20Tasks/TurtleBot4%20-%20Ethernet%2C%20Wi-Fi%20power%20save%20and%20odometry%20timing.txt) |
| [setup/](setup/) | Admin scripts used to configure the robot. Read MAINTENANCE.md before running any of them. |

## Quick start

Want to learn to do everything yourself? Follow [docs/getting-started/do-it-yourself.html](docs/getting-started/do-it-yourself.html) (open it in a browser; on GitHub read [docs/getting-started/do-it-yourself.md](docs/getting-started/do-it-yourself.md)). The steps below are the short version.

1. Put the robot on its dock, wait about 2 minutes for the chime, and read the address on its display.
2. Join the same Wi-Fi as the robot: `Students` if the address starts with `10.87.`, or the robot's own `Turtlebot4` network if it shows `10.42.0.1`. (The lab router network does not have the robot on it.)

Or skip the manual steps and use the app: [TurtleBot Studio](#start-here-control-the-robot-with-turtlebot-studio). On Windows, install it from [Download/](Download/README.md) (no Python needed). On macOS or Linux it needs Python 3.10 or newer: run `bash tools/studio/start-studio.sh` (on Windows the Python way is `tools/studio/Start TurtleBot Studio.cmd`). Press Discover, then Connect.

Otherwise connect in one of two ways.

### Easiest: the connect tool

3. Get the tool from [tools/connect/](tools/connect/README.md): on Windows download `TurtleBotConnect.exe` and double-click it; on macOS or Linux download `connect-turtlebot.sh` and run `bash connect-turtlebot.sh` in a terminal. The Windows program is not code-signed, so the first time SmartScreen warns: choose **More info**, then **Run anyway**, or build it yourself from its source (see its README).
4. Type `1` (Connect) and type the `ubuntu` password when ssh asks for it (nothing shows while you type). If the robot is not found, type the address from the display. Type `3` once to set up key login, so you no longer need the password.

The tool only talks to a device that presents the lab robot's host key, so it will not log in to another device that took over an old campus address. It was tested against a simulated robot only; if it does not work, use the manual way below.

### Manual: plain `ssh` (works on any computer)

3. Open a terminal (PowerShell on Windows, Terminal on macOS or Linux) and log in. Type the `ubuntu` password when asked (nothing shows while you type):

   ```bash
   ssh ubuntu@turtlebot4.local
   ```

   If the name does not work, use the address from the display instead, for example `ssh ubuntu@10.42.0.1` on the robot's own Wi-Fi, or `ssh ubuntu@10.87.10.205` on `Students` (read the current address on the display). On the campus Wi-Fi the name has failed now and then since 2026-10-04.
4. You are now on the robot (the prompt reads `ubuntu@turtlebot4:~$`). Run the first example, which is safe on the dock, then log out:

   ```bash
   cd ~/robot_code
   python3 hello_robot.py
   exit
   ```

The robot login is user `ubuntu`, password `turtlebot4`. Full instructions, including key login and VS Code, are in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md).

**Safety:** `drive_test.py`, `motion_test.sh` and `motion_shapes.py` move the robot. Clear about 1 m around it before running them and stay nearby. Read [examples/README.md](examples/README.md) first.


**Campus delivery (TB-29), planning documents (2026-11-12):** [docs/reference/parts-list.md](docs/reference/parts-list.md) (what the project still needs, with Saudi shop links and SAR prices) and [docs/reference/spoken-messages.md](docs/reference/spoken-messages.md) (plan for English and Arabic spoken lines at the food court and the lab; not tested on the robot).

## Project history

Status paragraphs from earlier dates, moved here on 2026-11-28 so the top of this page can stay current. They are kept as written. The current state is in "Status at a glance" above, [ROADMAP.md](ROADMAP.md) and [MAINTENANCE.md](MAINTENANCE.md).

*Superseded 2026-11-28 by the status at a glance above and the roadmap; kept as history.*

**Status on 2026-10-24:** the robot was reached with a direct Ethernet cable ([HOW-TO-CONNECT.md, Ethernet](HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed)). Wi-Fi power saving, the leading suspect for the Wi-Fi drops, was found switched on and is now off for the `Students` profile (MAINTENANCE.md R14). Whether that ends the drops can only be checked on campus. A recorded motion test showed that the `/odom` pauses start in the Create 3 base when it begins to move, not in the Wi-Fi or the Pi's processor ([MAINTENANCE.md](MAINTENANCE.md), [ROADMAP.md](ROADMAP.md) TB-15 and TB-25). After undocking, the lidar may stay stopped: see Known issues in MAINTENANCE.md. The new app [TurtleBot Studio](tools/studio/README.md) (finds the robot, shows its status, copies and runs programs, emergency stop) was built and tested over the cable with the robot docked and no motion; the remaining checks are listed in its README.

*Superseded: the status of 2026-10-10 below was replaced by the status of 2026-10-24 above (Wi-Fi power saving is now off for `Students`, see MAINTENANCE.md R14); kept as history.*

**Status on 2026-10-10:** since 2026-10-04 the robot drops off the Wi-Fi and answers SSH only for short periods. A fix is proposed but not applied. Connect by the address on the robot's display and retry: see [HOW-TO-CONNECT.md, Troubleshooting](HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found) and [docs/explanations/network-and-connectivity.html](docs/explanations/network-and-connectivity.html).
