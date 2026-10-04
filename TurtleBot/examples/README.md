# TurtleBot 4 examples

Small ROS 2 Jazzy programs for the lab's TurtleBot 4 Standard (Raspberry Pi 4 on an iRobot Create 3 base). They run **on the robot**, not on your computer. Every command below works from Windows, macOS or Linux.

New to the robot? First follow [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md) to join the robot's network and log in with `ssh ubuntu@turtlebot4.local` (or `ssh ubuntu@` followed by the address on the robot's display).

**Contents**

1. [The examples](#the-examples)
2. [Copy the files to the robot](#copy-the-files-to-the-robot)
3. [Safety checklist before anything moves](#safety-checklist-before-anything-moves)
4. [Undock and dock](#undock-and-dock)
5. [motion_shapes.py: drive a square, triangle, circle and more](#motion_shapespy-drive-a-square-triangle-circle-and-more)
6. [How to stop the robot](#how-to-stop-the-robot)
7. [Parameters](#parameters)
8. [Expected output](#expected-output)
9. [Troubleshooting](#troubleshooting)
10. [Sensor programs that do not move the robot](#sensor-programs-that-do-not-move-the-robot): sensor_report, lidar_snapshot, scan_plot_html, lightring_status
11. [More motion programs](#more-motion-programs): more_shapes, wall_approach, keep_distance, campaign
12. [health_check.py: read-only health checklist](#health_checkpy-read-only-health-checklist)

## The examples

| File | What it does | Moves the robot? | Where it works |
|---|---|---|---|
| `hello_robot.py` | Shows a message on the display and turns the light ring green for 5 s. | No | Anywhere, also on the dock |
| `scan_test.py` | Prints the distance to the nearest object the lidar sees, until Ctrl+C. | No | Off the dock (the lidar is off while docked) |
| `clearance_check.py` | One lidar scan: nearest object within ±30° of straight ahead. Exit code 0 clear, 1 blocked, 2 no scan. | No | Off the dock |
| `drive_test.py` | Drives forward 20 cm at 0.1 m/s, then stops. No obstacle check. | **Yes** | Off the dock, 1 m clear in front |
| `motion_test.sh` | Undocks, checks the way ahead, drives 20 cm if clear, spins 360°, docks again. | **Yes** | Starts on the dock; run detached |
| `motion_shapes.py` | Drives a square, triangle, in-place rotation, back-and-forth or figure eight, closed-loop on odometry, with obstacle, hazard, stall and timeout stops. | **Yes** | Off the dock, 1 m clear all round; run detached |
| `sensor_report.py` | Measures rates and the largest gaps (arrival time and header stamp) of `/odom`, `/scan`, `/imu`, `/battery_state`, `/dock_status`; battery, dock state, lidar valid beams and range, lidar TF yaw. Table, optional JSON. The odometry-gap diagnostic. | No | Anywhere (no lidar data on the dock) |
| `lidar_snapshot.py` | Saves one or more scans to JSON or CSV (angles in the robot frame) and prints the nearest return in each of 36 sectors. | No | Off the dock |
| `scan_plot_html.py` | Turns a `lidar_snapshot.py` JSON file into an HTML page with a polar plot (robot at the centre, forward up). No ROS needed. | No | **Any computer** with Python 3 |
| `lightring_status.py` | Shows battery level (number and colour of LEDs) and a stale lidar (blinking red) on the light ring for N seconds, then hands it back. | No | Anywhere, also on the dock |
| `health_check.py` | One-command robot health checklist: Wi-Fi, ROS service, base data and battery, Pi vs base clock, lidar USB and `/scan`, `/odom` gaps, clock-fix files, temperature, throttling, disk, memory, `~/STOP`, running motion programs. PASS/WARN/FAIL/INFO table with a fix hint per row; exit code 0, 1 or 2; optional JSON. Read only, no `sudo`. | No | On or off the dock (`/scan` is checked off the dock only) |
| `more_shapes.py` | More shapes on top of `motion_shapes.py`: polygon, star, circle, square spiral, zigzag, and a repeatability test (a shape K times, odometry error per loop). | **Yes** | Off the dock, 1 m clear all round; run detached |
| `wall_approach.py` | Drives slowly towards a wall until the lidar reads the target distance (default 0.50 m, min 0.30 m, max 1.0 m of travel); prints odometry vs lidar. | **Yes** | Off the dock, facing a wall 0.5 to 1.5 m away |
| `keep_distance.py` | Holds 0.6 m to the object straight ahead: follows it forward, backs off slowly (0.05 m/s, at most 0.2 m). Runs at most 60 s. | **Yes** | Off the dock, 1 m clear all round |
| `campaign.sh` | Runs a list of `motion_shapes.py` / `more_shapes.py` commands one after another with a sensor report before and after, logged to a file; stops at the first failure. | **Yes** | Off the dock; run detached |
| `motion_common.py` | Not a program: shared safety code (start-up checks, total timeout, 1.2 m fence) used by `more_shapes.py`, `wall_approach.py` and `keep_distance.py`. | - | Copy it with them |

Copies of these files live in `~/robot_code` on the robot. Run them there with `python3 <file>` (or `bash motion_test.sh`). ROS programs take 10 to 20 s to start on the Pi, and `ros2` command-line calls 30 to 60 s, so be patient before deciding nothing is happening.

## Copy the files to the robot

If `~/robot_code` already has the version you want, skip this. Otherwise pick one way.

**scp** (works the same in PowerShell, macOS Terminal and Linux). From the folder that holds `motion_shapes.py` on your computer:

```bash
scp motion_shapes.py ubuntu@turtlebot4.local:robot_code/
```

The newer motion programs need their helpers next to them. To copy everything in this folder at once (from inside it):

```bash
scp *.py *.sh ubuntu@turtlebot4.local:robot_code/
```

Use the display address instead of `turtlebot4.local` if the name does not work, for example `ubuntu@10.42.0.1:robot_code/` on the robot's own Wi-Fi.

**VS Code Remote-SSH**: connect to `ubuntu@turtlebot4.local`, open `/home/ubuntu/robot_code`, and drag the file into the Explorer panel (or create it there and paste the code). Setup steps are in [HOW-TO-CONNECT.md, Write and run code](../HOW-TO-CONNECT.md#write-and-run-code).

Copying from your computer works even when the robot's clock is wrong (when `git` on the robot fails with certificate errors).

## Safety checklist before anything moves

Go through this every time, before running any program marked "Moves the robot":

- [ ] About **1 m of clear floor all round** the robot. No cables, bags, feet or table legs. No stairs or drop-offs nearby.
- [ ] The robot is **off the dock** (see [Undock and dock](#undock-and-dock)), with space for the shape you chose.
- [ ] **A person stands beside the robot** for the whole run, ready to pick it up or stop it.
- [ ] You know [how to stop it](#how-to-stop-the-robot), and a second terminal is open on the robot if you run it detached.
- [ ] Speed stays at or below **0.15 m/s**. `motion_shapes.py` enforces this cap; your own programs should too.
- [ ] Do a **dry run first** (`--dry-run`) to see the plan and check the sensors.

## Undock and dock

Run these on the robot. Send them detached so a Wi-Fi drop does not cancel them halfway (see [HOW-TO-CONNECT.md, Moving the robot](../HOW-TO-CONNECT.md#moving-the-robot-run-motion-scripts-detached)):

```bash
# Undock (the robot backs off the dock)
setsid nohup ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}" > ~/robot_code/undock.log 2>&1 &

# Dock again when you are done
setsid nohup ros2 action send_goal /dock irobot_create_msgs/action/Dock "{}" > ~/robot_code/dock.log 2>&1 &
```

Each takes up to a minute. Check the result with `cat ~/robot_code/undock.log` (look for `SUCCEEDED`), or ask the base directly:

```bash
timeout 60 ros2 topic echo --once /dock_status
```

`is_docked: false` means it is off the dock. After undocking, give the lidar a few seconds to spin up before running a lidar program. Docking only works when the robot is near the dock and can see it, so finish your run near the dock or carry the robot back in front of it first.

## motion_shapes.py: drive a square, triangle, circle and more

> **Status: tested on the robot on 2026-10-04** (odometry errors, not floor measurements): square 0.9 cm / +0.8 deg, rotate 0.1 cm / +0.7 deg,
> back_and_forth 0.6 cm / +0.9 deg, triangle 1.0 cm / +2.2 deg (held still three times through odometry gaps). figure_eight completed its
> first circle, then aborted on a 2.0 s odometry gap with the robot standing still. Logs: [../tests/logs/](../tests/logs/); results:
> [../docs/test-results.html](../docs/test-results.html).

`motion_shapes.py` **moves the robot.** It plans a shape as a list of segments (drive straight, turn in place, drive a full circle), then drives each one using wheel odometry (`/odom`): straight segments stop when the robot has moved the planned distance, turns stop when the summed heading change reaches the planned angle. It sends velocity on `/cmd_vel` as `TwistStamped`.

| Shape | What the robot does | Space needed |
|---|---|---|
| `square` | 4 × (forward 0.40 m, turn left 90°) | 0.4 m square ahead and to the left |
| `triangle` | 3 × (forward 0.40 m, turn left 120°) | 0.4 m triangle ahead and to the left |
| `rotate` | One full turn (360°) on the spot | Its own footprint |
| `back_and_forth` | Forward 0.40 m, turn 180°, forward 0.40 m back, turn 180° (it never reverses, because the Create 3 limits driving backwards and the lidar check only covers the front) | 0.4 m ahead |
| `figure_eight` | A full left circle, then a full right circle, radius 0.20 m | 0.4 m to each side, 0.4 m ahead and behind |

It refuses to start, or stops the robot, when:

- the robot is on the dock, or the base sends no `/odom` or `/dock_status` within 30 s;
- the lidar sends no `/scan` within 30 s, or the path ahead is not clear at the start;
- while driving forward or on a circle, anything is closer than 0.25 m within ±30° of straight ahead;
- odometry is older than 0.3 s: it holds still (zero velocity) until fresh odometry arrives, and aborts if there is none for 2.0 s (the base was seen pausing `/odom` for 0.4 to 1.0 s around motion starts); the lidar scan is older than 1.0 s: it aborts;
- the base reports a hazard (bump, cliff, wheel drop, stall, ...); its "backup limit" message is ignored;
- a segment takes more than 2 × its expected time + 5 s, or the whole shape more than 120 s;
- it commands motion but odometry shows no progress for 3 s (stuck);
- you stop it (Ctrl+C, `SIGTERM`, or the `~/STOP` file).

While **turning in place** there is no lidar obstacle stop. The Create 3 is round and turns about its centre, so turning on the spot sweeps no new floor; the bumper (hazard stop) still works, and stale-lidar and all other checks stay on. A check during turns would mainly add false stops from close objects at the robot's sides.

### 1. Dry run first

A dry run waits for the sensors, runs all the checks, prints the plan with expected times, and exits. It **never** sends a velocity command, so it is safe on the dock (on the dock it skips the lidar check, because the lidar is switched off there, and just warns that a real run would refuse).

```bash
cd ~/robot_code
python3 motion_shapes.py square --dry-run
```

### 2. Real run in the terminal (good Wi-Fi only)

After [undocking](#undock-and-dock) and the [checklist](#safety-checklist-before-anything-moves):

```bash
python3 motion_shapes.py square
```

It asks `Is 1 m around it clear and are you next to it? Type yes:` before moving. If SSH drops while it runs, the program keeps going (and its safety checks keep working), but you lose Ctrl+C; use the `~/STOP` file from a new login.

### 3. Real run detached (recommended)

Campus Wi-Fi can drop as the robot moves. Run it detached so it is not affected, and watch the log. Detached runs have no keyboard, so you must add `--yes` (you are confirming the checklist now); without it the program refuses to start.

```bash
setsid nohup python3 ~/robot_code/motion_shapes.py square --yes > ~/robot_code/shapes.log 2>&1 &
tail -f ~/robot_code/shapes.log
```

Ctrl+C in `tail` only stops watching; it does **not** stop the robot. To stop the robot, see the next section.

### Every shape

```bash
python3 motion_shapes.py square --dry-run
python3 motion_shapes.py triangle --dry-run
python3 motion_shapes.py rotate --dry-run
python3 motion_shapes.py back_and_forth --dry-run
python3 motion_shapes.py figure_eight --dry-run
```

Drop `--dry-run` (and add `--yes` when detached) for the real run. Options:

| Option | Meaning |
|---|---|
| `--side 0.3` | Side or leg length in m (default 0.40, max 1.0). Not used by `rotate` and `figure_eight`. |
| `--speed 0.08` | Forward speed in m/s (default 0.10). Anything above 0.15 is lowered to 0.15, with a note in the output. |
| `--turn-speed 0.4` | Turn speed in rad/s (default 0.5). Anything above 1.0 is lowered to 1.0. |
| `--no-lidar` | Do not use the lidar: **no obstacle stop.** Prints a warning. Only for when the lidar is broken, with extra care. |
| `--dry-run` | Checks and plan only, never moves. |
| `--yes` | Skip the "area clear?" question. Needed when detached. |

## How to stop the robot

Any of these stops the robot within one control cycle (1/20 s). The program then sends zero velocity for 0.5 s and exits.

1. **Ctrl+C** in the terminal where it runs (not the `tail -f` terminal).
2. **The STOP file.** From any other terminal on the robot (log in again if SSH dropped):

   ```bash
   touch ~/STOP
   ```

   Delete it afterwards, or the next run refuses to start: `rm ~/STOP`.
3. **Send the stop signal** from another terminal on the robot:

   ```bash
   pkill -INT -f motion_shapes.py
   ```

If the software does not respond, pick the robot up: the Create 3 stops its wheels when lifted (wheel drop). The power button on the base also stops everything.

Exit codes, useful in scripts: `0` done, `1` aborted by a safety check, `2` setup failure (docked, no odometry, no lidar, `~/STOP` present, no `--yes` when detached, plan too long), `130` stopped by you.

## Parameters

The values are at the top of `motion_shapes.py`. Change them there if you need to; keep the speed caps.

| Name | Default | Meaning |
|---|---|---|
| `SIDE_LENGTH` | 0.40 m | Side of square/triangle, leg of back_and_forth (`--side`, max `MAX_SIDE_LENGTH` 1.0 m) |
| `LINEAR_SPEED` | 0.10 m/s | Forward speed (`--speed`) |
| `MAX_LINEAR_SPEED` | 0.15 m/s | Hard cap on forward speed |
| `ANGULAR_SPEED` | 0.5 rad/s | Turn speed (`--turn-speed`) |
| `MAX_ANGULAR_SPEED` | 1.0 rad/s | Hard cap on turn speed |
| `MIN_LINEAR_SPEED`, `MIN_ANGULAR_SPEED` | 0.03 m/s, 0.15 rad/s | Slowest speeds used when slowing down near a goal |
| `DISTANCE_TOLERANCE`, `ANGLE_TOLERANCE` | 1 cm, 1.5° | When a segment counts as done |
| `CIRCLE_RADIUS` | 0.20 m | Radius of each figure-eight circle. Turn rate is speed / radius, limited to the turn speed by lowering the forward speed. |
| `OBSTACLE_STOP_DISTANCE` | 0.25 m | Stop if anything is closer than this in front |
| `OBSTACLE_HALF_ANGLE` | 30° | "In front" means within ±30° of straight ahead |
| `TOTAL_TIMEOUT` | 120 s | Limit for the whole shape (the program refuses plans that would need longer) |
| Segment timeout | 2 × expected + 5 s | Limit for each segment |
| `ODOM_HOLD` | 0.3 s | Odometry older than this: send zero velocity and wait for fresh data (the segment carries on afterwards) |
| `ODOM_STALE`, `SCAN_STALE` | 2.0 s, 1.0 s | Abort if odometry or lidar data is older than this |
| `STALL_TIME` | 3 s | Abort if commanding motion but odometry does not change |
| `STARTUP_WAIT` | 30 s | How long to wait for `/odom`, `/dock_status` and `/scan` |
| `PAUSE` | 0.5 s | Standing still between segments |
| `CONTROL_RATE` | 20 Hz | Control loop rate |
| `STOP_FILE` | `~/STOP` | Stop file |

The lidar is mounted turned 90° on this robot (the transform `base_link` → `rplidar_link` has yaw +90°), so straight ahead of the robot is laser angle −90°. The program reads this from TF, like `clearance_check.py`, and falls back to +90° with a warning if TF is missing.

## Expected output

A dry run on the floor looks like this (times and distances will differ):

```text
10:02:11 shape square: 8 segments, about 33 s in total
10:02:11   1. forward 0.40 m at 0.10 m/s (about 4.0 s, timeout 13.0 s)
10:02:11   2. turn left 90 deg at 0.50 rad/s (about 3.1 s, timeout 11.3 s)
   ... (segments 3 to 8)
10:02:24 waiting up to 30 s for /odom and /dock_status (ROS starts slowly on the Pi)
10:02:25 odometry OK, docked: False
10:02:25 waiting up to 30 s for /scan
10:02:26 lidar yaw in the robot frame (from TF): 90 deg
10:02:26 lidar OK: nearest in front 1.85 m, nearest anywhere 0.62 m
10:02:27 dry run: all checks done, nothing was sent to /cmd_vel
```

A real run then prints each segment and, at the end, the planned against the measured end pose:

```text
10:05:40 starting. To stop: Ctrl+C, or "touch ~/STOP", or "pkill -INT -f motion_shapes.py"
10:05:40 segment 1/8: forward 0.40 m at 0.10 m/s (about 4.0 s, timeout 13.0 s)
10:05:45 segment 1 done in 4.9 s
...
10:06:19 planned end: x +0.000 m, y +0.000 m, heading change +360.0 deg
10:06:19 odometry end: x +0.004 m, y -0.003 m, heading change +358.7 deg
10:06:19 error: position 0.5 cm, heading -1.3 deg (odometry only; the real error is larger, measure it on the floor)
10:06:19 done
```

The error line compares the plan with the robot's own odometry, which drifts. To know how well it really drove, mark the start on the floor with tape and measure.

A safety stop looks like `ABORTED: obstacle 0.24 m ahead (limit 0.25 m)`, and a stop by you like `STOPPED: /home/ubuntu/STOP exists`.

## Troubleshooting

| What you see | Likely cause | What to do |
|---|---|---|
| `SETUP FAILED: no /scan from the lidar` | The robot is on the dock (the lidar is switched off there to save power), or the lidar is not detected | Undock first and wait a few seconds. If it still fails, see [Known issues](../HOW-TO-CONNECT.md#known-issues). |
| `SETUP FAILED: the robot is on the dock` | It is docked | [Undock](#undock-and-dock) it. |
| `SETUP FAILED: no /odom` or `no /dock_status` | The Create 3 base application is stuck (its clock is out of sync with the Pi) | [Restart the Create 3 base application](../HOW-TO-CONNECT.md#restart-the-create-3-base-application), wait for the chime, try again. |
| `SETUP FAILED: no terminal to ask ...` | Started detached without `--yes` | Go through the checklist, then add `--yes`. |
| `REFUSING: /home/ubuntu/STOP exists` | The stop file from an earlier stop is still there | `rm ~/STOP` |
| `path not clear` at the start | Something is within (first leg + 0.25 m) ahead | Clear the way or move the robot. |
| Nothing printed for 10 to 20 s | ROS starts slowly on the Pi | Wait. With `nohup`, output appears in the log as it happens. |
| Your own program publishes on `/cmd_vel` but the robot does not move | On this robot (Jazzy) `/cmd_vel` takes `geometry_msgs/msg/TwistStamped`, not `Twist` | Publish `TwistStamped` with `header.stamp` set to now and `header.frame_id = 'base_link'`, as `drive_test.py` does. |
| `ABORTED: odometry is stale` or `lidar is stale` | A sensor stopped publishing mid-run (Pi overloaded, lidar USB, base stuck) | Run `python3 sensor_report.py --seconds 60` to see the rates and gaps; restart the base application if `/odom` is gone. |
| `held still for N control cycles waiting for odometry` | `/odom` paused for more than 0.3 s; the robot stood still and carried on | Normal now and then. If it happens a lot, run `sensor_report.py` and compare arrival and stamp gaps. |
| `ABORTED: hazard reported by the base: BUMP ...` | The bumper touched something, or a cliff sensor saw an edge | Clear the area and start again. |
| `ABORTED: stalled` | Wheels blocked, or robot lifted | Check the floor and the wheels. |
| SSH dropped while the robot moved | Wi-Fi roaming | The program keeps running and stops on its own. Log in again and `tail ~/robot_code/shapes.log`. Next time run it detached. |
| The robot ends far from where odometry says | Wheel slip, especially on carpet or in turns | Normal for odometry alone. Lower `--speed` and `--turn-speed`. |

## Sensor programs that do not move the robot

> **Status: not yet tested on the robot.** Logic checked off the robot only (unit tests and a simulated robot).

These are safe to run at any time. Run them from `~/robot_code` on the robot.

### sensor_report.py: rates, gaps and battery

Listens for `--seconds` (default 20) and prints one line per topic: message count, rate, expected rate, mean period, the largest gap between message **arrivals** (Pi clock), the largest gap between header **stamps** (the sender's clock), how many gaps were longer than 2.5 × the usual period, and the median age (Pi clock minus stamp; large or negative means the clocks disagree). Below the table: the largest `/odom` and `/scan` gaps with when they happened, battery %, docked state, lidar valid-beam %, nearest and median range, and the lidar's yaw from TF (should be 90°).

```bash
python3 sensor_report.py
python3 sensor_report.py --seconds 60 --json ~/robot_code/sensors.json
```

How to read the gaps: an `/odom` arrival gap **with** the same stamp gap means the base itself paused; an arrival gap **without** a stamp gap means the data was produced on time but delayed on the way (Pi load, DDS, Wi-Fi). On the dock `/scan` shows 0 messages, which is normal. Exit code 2 means no messages at all.

### lidar_snapshot.py and scan_plot_html.py: save and draw a scan

`lidar_snapshot.py` saves scans with every angle in the **robot frame** (0° straight ahead, +90° left) and prints the nearest return in each 10° sector:

```bash
python3 lidar_snapshot.py                                   # 1 scan -> ~/robot_code/scan_<date>_<time>.json
python3 lidar_snapshot.py --count 5 --out ~/robot_code/room.json
python3 lidar_snapshot.py --out ~/robot_code/room.csv       # CSV: scan,beam,angle_robot_deg,range_m,x_m,y_m
```

`scan_plot_html.py` needs no ROS and runs on your own computer. Copy the JSON over and make a picture:

```bash
scp ubuntu@turtlebot4.local:robot_code/room.json .
python3 scan_plot_html.py room.json                 # writes room.html; open it in a browser
python3 scan_plot_html.py room.json --max-range 3   # zoom to 3 m
```

The robot is the blue circle in the middle, straight ahead is **up**, the robot's left is on the left, rings every 0.5 m.

### lightring_status.py: robot state on the light ring

```bash
python3 lightring_status.py                 # 30 s
python3 lightring_status.py --seconds 120
```

Number of lit LEDs = battery level (6 = full). Green ≥ 50 %, yellow 20 to 50 %, red < 20 %. All six blinking red: no `/scan` for 2 s while off the dock (on the dock the lidar is off on purpose, so it shows the battery). Blinking white: no battery reading yet. At the end, or on Ctrl+C, it sends `override_system: false` so the robot's own light patterns come back.

## More motion programs

> **Status: not yet tested on the robot.** Logic checked off the robot only (unit tests and a simulated robot with odometry gaps, stop file, signals and bumps).

All of these **move the robot**. They need `motion_shapes.py` and `motion_common.py` in the same folder, and they behave like `motion_shapes.py`: same [checklist](#safety-checklist-before-anything-moves), `--dry-run` first, `--yes` when detached, the same [ways to stop](#how-to-stop-the-robot) (Ctrl+C, `touch ~/STOP`, `pkill -INT -f <program>`), the same exit codes, and the same stops (docked, bump/cliff hazards, obstacle within 0.25 m ahead, odometry hold at 0.3 s and abort at 2.0 s, stale lidar, stall, timeouts). On top of that they abort if odometry puts the robot more than **1.2 m from its start point**, and they refuse plans that would go more than 1.0 m from it. Speeds stay capped at 0.15 m/s and 1.0 rad/s.

### more_shapes.py

| Shape | What the robot does | Farthest from start (defaults) |
|---|---|---|
| `polygon --sides N` | N × (forward `--side`, turn left 360/N°), N = 3 to 12 | 0.49 m (5 sides of 0.30 m) |
| `star` | 5 × (forward `--side`, turn left 144°): a five-point star, two full turns in total | 0.30 m |
| `circle --radius R` | One full left circle, R = 0.15 to 0.45 m (default 0.25) | 0.50 m |
| `square_spiral` | Legs 0.1, 0.1, 0.2, 0.2 ... 0.5, 0.5 m with left 90° turns (`--step`, `--max-leg` ≤ 0.5 m); ends 0.3 m ahead and 0.3 m left | 0.42 m |
| `zigzag --legs N` | Turn left 30°, then N legs of `--side` (default 0.25 m) with alternating 60° turns, then turn back to the start heading. Ends N × side × 0.87 ahead (on the start line when N is even) | 0.87 m (4 legs of 0.25 m) |
| `repeatability --shape S --loops K` | Drives a closed shape (`square`, `triangle`, `rotate`, `back_and_forth`, `figure_eight`, `polygon`, `star`, `circle`) K times (1 to 5) and prints the odometry error after each loop and a summary table | as the shape |

```bash
python3 more_shapes.py polygon --sides 6 --side 0.25 --dry-run
python3 more_shapes.py star --dry-run
python3 more_shapes.py repeatability --shape square --loops 3 --dry-run
setsid nohup python3 ~/robot_code/more_shapes.py star --yes > ~/robot_code/more_shapes.log 2>&1 &
tail -f ~/robot_code/more_shapes.log
```

Options as in `motion_shapes.py` (`--side`, `--speed`, `--turn-speed`, `--no-lidar`, `--dry-run`, `--yes`). The total timeout is 1.5 × the expected time + 20 s, at most 300 s; longer plans are refused (use fewer loops or a shorter side).

### wall_approach.py

Point the robot at a wall or a large flat box 0.5 to 1.5 m away. It stands still for 1.5 s and takes the median lidar range straight ahead (±5°), then drives forward at 0.08 m/s for at most `min(range − target, 1.0 m)`, slowing down near the end, and stops when the lidar range (corrected for the distance driven since the last scan) or odometry says it has arrived. It never plans to end closer than the target. Then it measures again and prints the **odometry vs lidar calibration**: distance driven by odometry, change in lidar range, difference and ratio, and the slope of range against odometry during the drive (ideal −1.000).

```bash
python3 wall_approach.py --dry-run                       # shows the start range and the planned travel
python3 wall_approach.py --target 0.5
setsid nohup python3 ~/robot_code/wall_approach.py --yes --csv ~/robot_code/wall.csv > ~/robot_code/wall.log 2>&1 &
```

`--target` is 0.30 to 2.0 m (default 0.50), `--max-travel` at most 1.0 m, `--speed` default 0.08 m/s, `--csv` saves the samples. If the robot is already at or inside the target it does not move.

### keep_distance.py

Stand in front of the robot (or hold a big box) about 0.6 m away. Step back and it follows; step closer and it backs off.

```bash
python3 keep_distance.py --dry-run
python3 keep_distance.py --target 0.6 --duration 30
setsid nohup python3 ~/robot_code/keep_distance.py --yes > ~/robot_code/keep.log 2>&1 &
```

Speed = 0.5 × (distance − target), forward at most `--speed` (0.10 m/s), backward at most 0.05 m/s. It never goes more than 0.8 m ahead of or 0.2 m behind its start point (the Create 3 limits backing up and nothing watches behind the robot); if the base reports its backup limit, it stops reversing for the rest of the run. Within 3 cm of the target, or with nothing within 1.5 m ahead, it stands still. It prints a status line every second and stops after `--duration` (default and maximum 60 s). The 0.25 m obstacle stop applies only while driving forward.

### campaign.sh

Runs several shape commands in a row, with a 10 s `sensor_report.py` before and after (battery, rates, gaps), and writes everything to `~/robot_code/logs/campaign_<date>_<time>.log` (plus `_before.json` and `_after.json`). Each command gets `--yes` added; only `motion_shapes.py` and `more_shapes.py` commands are allowed. The campaign stops at the first command that does not exit 0, and refuses to start while `~/STOP` exists.

```bash
bash ~/robot_code/campaign.sh --dry-run                           # every command as a dry run
setsid nohup bash ~/robot_code/campaign.sh > /dev/null 2>&1 &     # the built-in list (rotate, square, hexagon, star, circle, zigzag)
setsid nohup bash ~/robot_code/campaign.sh my_list.txt > /dev/null 2>&1 &
tail -f $(ls -t ~/robot_code/logs/campaign_*.log | head -1)
```

A list file has one command per line, for example `more_shapes.py star --side 0.3`; blank lines and `#` comments are ignored. To stop: `touch ~/STOP` (the running program stops the robot, and the campaign stops), or `pkill -TERM -f campaign.sh`.

## health_check.py: read-only health checklist

> **Status: not yet tested on the robot.** Logic checked off the robot only (unit tests and a simulated robot with faked system commands and files).

One command for the [MAINTENANCE.md verification checklist](../MAINTENANCE.md#verification-checklist) (ROADMAP TB-19). It **never moves the robot**, publishes nothing, changes nothing and needs no `sudo`. It works on or off the dock. Run it in a login shell on the robot, so ROS is set up:

```bash
cd ~/robot_code
python3 health_check.py                                  # 10 s measuring window
python3 health_check.py --seconds 20 --json ~/robot_code/health.json
python3 health_check.py > health.txt                     # progress on screen, only the report in the file
```

It first runs the system checks (commands such as `nmcli`, `ip`, `systemctl`, `lsusb`, `vcgencmd`, `pgrep`, and files in `/proc` and `/sys`), then waits up to 30 s for the first `/odom`, `/dock_status` and `/battery_state` and listens for `--seconds`. It usually takes 15 to 25 s, and about 45 s when the base is silent. Each check is isolated: one that fails, hangs (4 s limit per command) or crashes gets its own row, and the rest still run.

| Row | WARN when | FAIL when |
|---|---|---|
| Wi-Fi | on the fallback access point `netplan-wlan0-Turtlebot4` (10.42.0.x) | no IPv4 address on `wlan0` |
| `turtlebot4.service` | still starting | not `active` |
| ROS environment | `ROS_DOMAIN_ID` not 0, another RMW, or ROS not set up in this shell | - |
| Base `/odom` | below 15 Hz (normal 20 Hz) | no message |
| Base `/dock_status`, `/battery_state` | battery below 30 % | no message |
| Clock Pi vs base | - | Pi clock and base header stamps 5 s or more apart |
| Lidar USB | - | no CP210x `10c4:ea60` in `lsusb`, or no `/dev/RPLIDAR` |
| Lidar `/scan` (off the dock) | below 5 Hz, or under 40 % valid beams | no `/scan` off the dock. On the dock: INFO, not checked |
| Odometry gaps | largest `/odom` arrival gap over 0.3 s | over 2 s |
| CPU temperature | over 75 °C | over 82 °C |
| Throttling (`vcgencmd get_throttled`) | any flag set (INFO if `vcgencmd` is missing) | - |
| Disk free on `/` | under 2 GB | - |
| `~/STOP` | present (fix: `rm ~/STOP`) | - |

Always INFO: the clock-fix files (TB-17), load average, memory, uptime and running motion programs. Gaps in `/odom` mostly show up while the robot moves (the base pauses it, TB-15); with the robot still the largest gap is normally about 0.05 s.

Example (from the offline simulator, robot on the dock with a `~/STOP` left over; numbers on the robot differ):

```text
TurtleBot 4 health check, 2026-10-04 12:31:05 on turtlebot4, ROS window 10.1 s
Read only: nothing was moved or changed.

STATUS CHECK                RESULT
------ -----                ------
PASS   Wi-Fi                Students on wlan0, 10.87.10.205/18
PASS   turtlebot4.service   active
PASS   ROS environment      ROS_DISTRO jazzy, ROS_DOMAIN_ID 0, RMW_IMPLEMENTATION rmw_fastrtps_cpp
PASS   Base /odom           20.0 Hz, 201 messages (expected about 20 Hz)
PASS   Base /dock_status    received, docked: yes
PASS   Base /battery_state  battery 42 %
PASS   Clock Pi vs base     Pi 0.00 s ahead of the base stamps (limit 5 s); Pi clock 2026-10-04 12:31:05
PASS   Lidar USB            CP210x (10c4:ea60) in lsusb, /dev/RPLIDAR -> /dev/ttyUSB0
INFO   Lidar /scan          scan not checked: the lidar is switched off on the dock (/scan publishers: 1)
                            note: undock and run again to check it
PASS   Odometry gaps        largest arrival gap 0.05 s (WARN > 0.3 s, FAIL > 2 s); gaps mostly show up during motion
INFO   Clock fix (TB-17)    installed: tb4-https-time.timer, 10-wait-for-clock.conf
                            note: keep or remove is an open decision (ROADMAP.md TB-17); never change the clock while ROS runs
PASS   CPU temperature      48.3 C (WARN > 75, FAIL > 82)
PASS   Throttling           throttled=0x0 (no under-voltage or throttling since boot)
INFO   Load average         1.52 1.31 1.20 (1, 5, 15 min; 4 CPUs)
PASS   Disk free on /       37.20 GB free of 58.9 GB
INFO   Memory               2366 MB available of 3975 MB
INFO   Uptime               up 1 h 25 min
WARN   STOP file            ~/STOP exists: motion programs refuse to start
                            fix: rm ~/STOP
INFO   Motion programs      none running

12 PASS, 1 WARN, 0 FAIL, 6 INFO. Exit code 1 (0 all PASS or INFO, 1 a WARN, 2 a FAIL).
```

Exit codes: `0` every row PASS or INFO, `1` at least one WARN, `2` at least one FAIL. To report a problem, paste the report into the issue between two lines of three backticks (as above), so the columns stay aligned. The `--json` file has the same rows (`id`, `status`, `result`, `hint`) plus the raw measurements, for comparing runs.

When a row fails, follow its `fix:` line. The most common ones: no base data means restarting the Create 3 base application (`curl -X POST http://192.168.186.2/api/restart-app`, wait for the chime); a missing lidar means reseating its USB cable with the robot powered off ([MAINTENANCE.md, lidar incident](../MAINTENANCE.md#incident-lidar-not-detected-2026-10-03-resolved-2026-10-04)); a clock FAIL points at [MAINTENANCE.md](../MAINTENANCE.md#incident-create-3-base-stopped-responding-after-the-clock-fix). Never change the clock while ROS runs.
