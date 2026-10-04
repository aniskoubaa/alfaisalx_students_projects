# TurtleBot 4

Documentation, example programs and setup scripts for the lab's TurtleBot 4 Standard (Raspberry Pi 4 on an iRobot Create 3 base, Ubuntu 24.04 Server, ROS 2 Jazzy). New users start with [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md).

| File | What it is for |
|---|---|
| [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md) | Connect from any computer (Windows, macOS, Linux), log in, write and run code, turn the robot off, troubleshoot. **Start here.** |
| [MAINTENANCE.md](MAINTENANCE.md) | Configuration record: every change made to the robot with verify and undo steps, incident report, known issues, admin scripts |
| [ROADMAP.md](ROADMAP.md) | Plan for the next iterations, including remote desktop |
| [turtlebot4-field-guide.html](turtlebot4-field-guide.html) | Beginner overview of the hardware and ROS 2 (open it in a browser) |
| [examples/](examples/) | Example programs; copies are in `~/robot_code` on the robot |
| [examples/README.md](examples/README.md) | How to run each example safely: undock and dock, `motion_shapes.py` (square, triangle, rotate, back-and-forth, figure eight), how to stop the robot, troubleshooting |
| [examples/health_check.py](examples/README.md) | One-command robot health checklist (Wi-Fi, ROS service, base, clock, lidar, odometry gaps, temperature, disk). Read only |
| [tests/](tests/README.md) | Robot run logs, diagnostic scripts, and offline tests that check the example programs on any computer (also run automatically on GitHub) |
| [docs/](docs/index.html) | Illustrated pages (open in a browser): start at [docs/index.html](docs/index.html) |
| [docs/lidar-diagnosis.html](docs/lidar-diagnosis.html) | How the "lidar not detected" fault was diagnosed and fixed on 2026-10-04, with the measured values. Markdown version: [docs/LIDAR-FINDINGS.md](docs/LIDAR-FINDINGS.md) |
| [docs/motion-program-design.html](docs/motion-program-design.html) | How `motion_shapes.py` works: segment planner, controller, safety layers, the `/odom` pause finding, parameters |
| [docs/test-results.html](docs/test-results.html) | Results of the motion program runs |
| [setup/](setup/) | Admin scripts used to configure the robot. Read MAINTENANCE.md before running any of them. |

## Quick start

1. Put the robot on its dock, wait about 2 minutes for the chime, and read the address on its display.
2. Join the same Wi-Fi as the robot: `Students` if the address starts with `10.87.`, or the robot's own `Turtlebot4` network if it shows `10.42.0.1`.
3. Open a terminal (PowerShell on Windows, Terminal on macOS or Linux) and log in. Type the `ubuntu` password when asked (nothing shows while you type):

   ```bash
   ssh ubuntu@turtlebot4.local
   ```

   If the name does not work, use the address from the display instead, for example `ssh ubuntu@10.42.0.1` on the robot's own Wi-Fi.
4. You are now on the robot (the prompt reads `ubuntu@turtlebot4:~$`). Run the first example, which is safe on the dock, then log out:

   ```bash
   cd ~/robot_code
   python3 hello_robot.py
   exit
   ```

Passwords are not stored in this repository; ask the lab maintainer. Full instructions, including key login and VS Code, are in [HOW-TO-CONNECT.md](HOW-TO-CONNECT.md).

**Safety:** `drive_test.py`, `motion_test.sh` and `motion_shapes.py` move the robot. Clear about 1 m around it before running them and stay nearby. Read [examples/README.md](examples/README.md) first.
