# TurtleBot 4

Documentation, example programs and setup scripts for the lab's TurtleBot 4 Standard (Raspberry Pi 4 on an iRobot Create 3 base, Ubuntu 24.04 Server, ROS 2 Jazzy). New users start with [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md).

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

**Status on 2026-10-24:** the robot was reached with a direct Ethernet cable ([HOW-TO-CONNECT.md, Ethernet](HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed)). Wi-Fi power saving, the leading suspect for the Wi-Fi drops, was found switched on and is now off for the `Students` profile (MAINTENANCE.md R14). Whether that ends the drops can only be checked on campus. A recorded motion test showed that the `/odom` pauses start in the Create 3 base when it begins to move, not in the Wi-Fi or the Pi's processor ([MAINTENANCE.md](MAINTENANCE.md), [ROADMAP.md](ROADMAP.md) TB-15 and TB-25). After undocking, the lidar may stay stopped: see Known issues in MAINTENANCE.md. The new app [TurtleBot Studio](tools/studio/README.md) (finds the robot, shows its status, copies and runs programs, emergency stop) was built and tested over the cable with the robot docked and no motion; the remaining checks are listed in its README.

**Status on 2026-10-10:** since 2026-10-04 the robot drops off the Wi-Fi and answers SSH only for short periods. A fix is proposed but not applied. Connect by the address on the robot's display and retry: see [HOW-TO-CONNECT.md, Troubleshooting](HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found) and [docs/network-and-connectivity.html](docs/network-and-connectivity.html).

| File | What it is for |
|---|---|
| [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) | Connect from any computer (Windows, macOS, Linux), log in, write and run code, turn the robot off, troubleshoot. **Start here.** |
| [tools/studio/](tools/studio/README.md) | **TurtleBot Studio (recommended way to work with the robot):** a local app that opens in your browser (`Start TurtleBot Studio.cmd` on Windows, `bash start-studio.sh` on macOS and Linux, or `python studio.py`). Finds the robot over Wi-Fi, hotspot or cable, shows its status, explains each program, copies and runs programs, has a code editor with templates (spin, circle, forward and back) and a Wi-Fi guide, watches topics and has an E-STOP. Nothing is installed on the robot. Built and tested over the cable on 2026-10-24 with the robot docked, no motion; macOS, Linux and Wi-Fi not tested yet |
| [tools/connect/](tools/connect/README.md) | Connect tool: `TurtleBotConnect.exe` (Windows 10 or 11, no installation) and `connect-turtlebot.sh` (macOS, Linux). A menu that finds the robot, opens a terminal, sets up key login, shows the robot's status, stops the motion programs in an emergency and copies files. Not yet used with the real robot as of 2026-10-10 |
| [tools/timing/](tools/timing/README.md) | Timing recorder and analyzer: records when `/odom` and the other base topics arrive, together with processor load, network counters, ping to the base and Wi-Fi events, then lists every pause and what it coincides with. Read only; run it next to a motion test. First used on the robot on 2026-10-24 (results in [tests/logs/](tests/logs/)) |
| [MAINTENANCE.md](MAINTENANCE.md) | Configuration record: every change made to the robot with verify and undo steps, incident reports (clock fix, lidar, Wi-Fi drops), the lab router, known issues, admin scripts |
| [ROADMAP.md](ROADMAP.md) | Plan for the next iterations (TB-01 to TB-27), including the Wi-Fi fix, the network decision and remote desktop |
| [turtlebot4-field-guide.html](turtlebot4-field-guide.html) | Beginner overview of the hardware and ROS 2 (open it in a browser) |
| [examples/](examples/) | Example programs. Copies of the first six (`hello_robot.py` to `motion_shapes.py`) are in `~/robot_code` on the robot; the newer ones are not on the robot yet (2026-10-10) |
| [examples/README.md](examples/README.md) | How to run each example safely: undock and dock, `motion_shapes.py` (square, triangle, rotate, back-and-forth, figure eight), how to stop the robot, troubleshooting |
| [examples/health_check.py](examples/health_check.py) | One-command robot health checklist (Wi-Fi, ROS service, base, clock, lidar, odometry gaps, temperature, disk). Read only. How to run it: [examples/README.md](examples/README.md#health_checkpy-read-only-health-checklist). Tested offline; first robot run pending |
| [tests/](tests/README.md) | Robot run logs, diagnostic scripts, and offline tests that check the example programs on any computer (101 logic checks and 38 simulated runs; also run automatically on GitHub by [.github/workflows/turtlebot-tests.yml](../.github/workflows/turtlebot-tests.yml)) |
| [docs/](docs/index.html) | Illustrated pages (open in a browser): start at [docs/index.html](docs/index.html) |
| [docs/meet-the-robot.html](docs/meet-the-robot.html) | **Meet the robot:** click a part of the TurtleBot 4 to see what it does, its ROS 2 topics and how to try it; what works and what is being fixed (interactive; for visitors, new students and reviewers) |
| [docs/how-a-command-travels.html](docs/how-a-command-travels.html) | **How a command travels:** one drive command from a program to the wheels and back as `/odom`, step by step, and why a starting program could pause the base (TB-25) |
| [docs/what-you-can-build.html](docs/what-you-can-build.html) | **What you can build:** project ladder from a first program to mapping and navigation, with filters, a project picker and what is tested on this robot |
| [docs/do-it-yourself.html](docs/do-it-yourself.html) | **Do it yourself, with no AI help:** power on, Wi-Fi, SSH, getting your code onto the robot, sensors, undock, drive, dock, stop and a first program, for Windows, macOS and Linux (interactive; Markdown version: [docs/DO-IT-YOURSELF.md](docs/DO-IT-YOURSELF.md)) |
| [docs/lidar-guide.html](docs/lidar-guide.html) | **Lidar user guide:** how the RPLIDAR works, one scan field by field, the 90 degree mounting, a lidar explorer, the commands to get the data, and Python code to use it (interactive; Markdown version: [docs/LIDAR-GUIDE.md](docs/LIDAR-GUIDE.md)) |
| [docs/motion-simulator.html](docs/motion-simulator.html) | Interactive simulator of `motion_shapes.py`: watch the robot drive a square or other shape, the speed commands, the lidar stop zone and odometry dropouts, compared with the real runs |
| [docs/docking-explained.html](docs/docking-explained.html) | How the robot finds its dock (infrared signals, the docking stages, undocking), as a simplified interactive animation, plus the dock and undock commands |
| [docs/network-and-connectivity.html](docs/network-and-connectivity.html) | The networks around the robot, the Wi-Fi drops of 2026-10-04 and 2026-10-05, likely causes, the proposed fix, workarounds, and the lab router proposal. Markdown version: [docs/NETWORK-FINDINGS.md](docs/NETWORK-FINDINGS.md) |
| [docs/lidar-diagnosis.html](docs/lidar-diagnosis.html) | How the "lidar not detected" fault was diagnosed and fixed on 2026-10-04, with the measured values. Markdown version: [docs/LIDAR-FINDINGS.md](docs/LIDAR-FINDINGS.md) |
| [docs/motion-program-design.html](docs/motion-program-design.html) | How `motion_shapes.py` works: segment planner, controller, safety layers, the `/odom` pause finding, parameters |
| [docs/test-results.html](docs/test-results.html) | Results of the motion program runs |
| Step logs | Dated logs including what failed: [2026-10-03 Wi-Fi setup](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt), [2026-10-04 lidar and motion programs](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt), [2026-10-04 to 2026-10-10 network and connectivity](../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt), [2026-10-24 Ethernet, Wi-Fi power save, odometry timing and TurtleBot Studio](../General%20Tasks/TurtleBot4%20-%20Ethernet%2C%20Wi-Fi%20power%20save%20and%20odometry%20timing.txt) |
| [setup/](setup/) | Admin scripts used to configure the robot. Read MAINTENANCE.md before running any of them. |

## Quick start

Want to learn to do everything yourself? Follow [docs/do-it-yourself.html](docs/do-it-yourself.html) (open it in a browser; on GitHub read [docs/DO-IT-YOURSELF.md](docs/DO-IT-YOURSELF.md)). The steps below are the short version.

1. Put the robot on its dock, wait about 2 minutes for the chime, and read the address on its display.
2. Join the same Wi-Fi as the robot: `Students` if the address starts with `10.87.`, or the robot's own `Turtlebot4` network if it shows `10.42.0.1`. (The lab router network does not have the robot on it.)

Or skip the manual steps and use the app: [TurtleBot Studio](tools/studio/README.md) (needs Python 3.10 or newer; on Windows double-click `tools/studio/Start TurtleBot Studio.cmd`, on macOS or Linux run `bash tools/studio/start-studio.sh`). Press Discover, then Connect.

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

Passwords are not stored in this repository; ask the lab maintainer. Full instructions, including key login and VS Code, are in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md).

**Safety:** `drive_test.py`, `motion_test.sh` and `motion_shapes.py` move the robot. Clear about 1 m around it before running them and stay nearby. Read [examples/README.md](examples/README.md) first.
