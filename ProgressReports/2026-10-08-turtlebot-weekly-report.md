# AlfaisalX Weekly Progress Report (TurtleBot 4)

**From:** Ibrahim (RA, AlfaisalX lab)
**Week:** 3 to 10 October 2026
**Repository:** [TurtleBot/ in alfaisalx_students_projects](https://github.com/aniskoubaa/alfaisalx_students_projects/tree/main/TurtleBot)

## What was achieved this week

- Found why the LiDAR was not detected: a loose USB cable. After reseating it, the LiDAR publishes 7.7 scans per second, 720 points each, with sensible distances.
- Wrote the first motion program, `motion_shapes.py`. It drives a 40 cm square, a full turn, a back and forth, a triangle and a figure eight, using wheel odometry for distance and heading. It stops for obstacles closer than 25 cm, for bumper hits and on timeouts, has an emergency stop, and is capped at 0.15 m/s. On the robot, the square, turn, back and forth and triangle each ended within 1 cm and 2.2° of where they started (measured by odometry; floor measurements are still to do).
- Added more programs: a one-command health check, a sensor report, a LiDAR snapshot with an HTML plot, extra shapes, a wall approach and a keep-distance controller. So far these have only run in simulation. A simulated robot (101 logic checks, 38 scenarios) runs on GitHub after every change, and it passes.
- Built a connect tool: a Windows program (no install needed) and a script for Mac and Linux that find the robot and open a terminal on it. It only connects to the real lab robot, because it checks the robot's identity key, so nobody types the robot password into the wrong device. Tested against a test server; its first run on the robot is next week.
- Set up a dedicated lab router (Linksys) on the wall Ethernet port. It measured about 12 to 13 Mbit/s, compared with about 3 Mbit/s on the Students Wi-Fi.
- Documented all of it in the repository: the user guide, a maintenance record listing every change to the robot and how to undo it, the roadmap with next tasks, test logs, and illustrated HTML pages, including a new page on the network problems.

## Challenges faced

- Connecting to the robot was the biggest problem this week. On the campus Wi-Fi it kept dropping off the network or answered only for 10 to 40 seconds at a time, `turtlebot4.local` often did not resolve, and SSH dropped whenever the robot drove. My best guess is Wi-Fi power saving on the Raspberry Pi combined with the campus network. The fix is a single setting, but it needs the robot's admin password, so it is not applied yet. Moving the robot onto the lab router is the backup plan.
- The base sometimes stops reporting odometry for 0.4 to 2 seconds while driving. The program now waits in place when that happens, but one figure-eight run still had to stop (safely). I don't know the cause yet.
- The campus blocks internet time servers. Earlier in the week a clock mismatch between the Pi and the base made the base go silent. A clock fix is installed, but whether to keep it is still open.
- Motion tests need someone standing next to the robot, so I could not leave long test runs going unattended.

## Main outcome or deliverable

The TurtleBot 4 is usable for lab work: the LiDAR works, a tested motion program drives the requested shapes safely, and lab members have tools to connect to the robot and check its health. The code, configuration changes, tests, results and step-by-step logs are in the GitHub repository under `TurtleBot/`, merged into `main`.

## Plan for next week

1. Apply the Wi-Fi power-saving fix and check whether the robot stays reachable. If it does not, move it to the lab router with a fixed address.
2. Run the new programs and the connect tool on the robot for the first time (supervised), get a full figure eight, and measure the real accuracy on the floor.
3. Find out why the odometry pauses.
4. Decide on the clock setup, and change the lab router's default admin login.
