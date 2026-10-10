# Lidar user guide

Markdown version of [lidar-guide.html](lidar-guide.html), for reading on GitHub. The HTML page has an interactive lidar simulator ("Lidar explorer", section 4) that GitHub only shows as source: download the repository and open `TurtleBot/docs/lidar-guide.html` in a browser. Everything else is here. Back to the [docs index](index.html).

What the lidar on the lab TurtleBot 4 measures, how one scan is laid out, why the lidar is mounted turned 90 degrees, and how to get its data by hand and in your own Python code. Written 2026-10-10 from the session record of 2026-10-03 to 2026-10-10 and the programs in [`examples/`](../examples/README.md). Values are measured on this robot unless a command is marked "untested".

Related: [the lidar fault of 2026-10-03](lidar-diagnosis.html) ([Markdown](LIDAR-FINDINGS.md)), [How to connect](../HOW-TO-CONNECT.md).

## 1. What it is and how it connects

The robot carries an **RPLIDAR A1M8** on top. Inside its head a laser and a sensor spin around, measuring the distance to whatever the laser hits. One turn gives a distance in every direction around the robot (360 degrees). The TurtleBot 4 manual describes it as a 360 degree laser range scanner with a 12 m range. The program-side name for what it produces is a *laser scan*.

| Beams per scan | Scans per second | Range | Typical valid beams |
|---|---|---|---|
| 720 (one every 0.5 deg) | about 7.7 (measured 7.745 Hz) | 0.15 to 12 m | 72 % (519 of 720 in the lab) |

The data path:

```
1 Laser head     2 USB cable          3 Driver                 4 /scan topic            5 Your program
RPLIDAR A1M8  -> USB-serial chip   -> rplidar_composition  -> sensor_msgs/LaserScan -> subscribes to /scan
spins, measures  CP210x (10c4:ea60)   on the Raspberry Pi,     about 7.7 per second     with sensor-data QoS
distance/angle   /dev/RPLIDAR         started by               frame rplidar_link       (section 6)
                                      turtlebot4.service
```

On this robot (checked 2026-10-04) the lidar appears to the Pi as a Silicon Labs CP210x USB-serial device (`lsusb` shows `10c4:ea60`), with the stable name `/dev/RPLIDAR` pointing at `/dev/ttyUSB0`. The driver is the `rplidar_composition` node (package `rplidar_ros`), started by `turtlebot4.service` when the robot boots. It reported firmware 1.29, hardware revision 7, health status 0, scan mode "Sensitivity" and a maximum distance of 12.0 m. The one time this chain broke (a loose USB cable) is told on [the diagnosis page](lidar-diagnosis.html); this guide does not repeat it.

> **Docked means off.** To save power the TurtleBot 4 stops the lidar while the robot is on its dock (the log says "RPLIDAR stopped" and "RPLIDAR started"). On the dock there is no `/scan`. That is normal, not a fault.

## 2. One scan, explained

Each message on `/scan` is one full turn of the lidar, a `sensor_msgs/msg/LaserScan`. The distances are in one list, `ranges[]`. The list has no angles in it: beam number `i` (0 to 719) was measured at an angle you work out from numbers in the message. Values on this robot:

| Field | Meaning | This robot |
|---|---|---|
| `header.frame_id` | The coordinate frame the angles belong to: the lidar's own | `rplidar_link` |
| `header.stamp` | Time of the scan (the Pi's clock) | changes every message |
| `angle_min` | Angle of beam 0, radians, in the lidar's frame | -3.1241 rad (-179.0 deg) |
| `angle_max` | Angle of the last beam | 3.1416 rad (180.0 deg) |
| `angle_increment` | Angle step between beams | 0.0087145 rad (about 0.5 deg) |
| `range_min` | Closest distance it can report | 0.15 m |
| `range_max` | Farthest distance it can report | 12.0 m |
| `ranges[]` | Distance in metres per beam, measured from the lidar | 720 values; typical lab scan 0.26 to 6.80 m, median 1.44 m |
| `time_increment`, `scan_time` | Time between beams, time for a whole turn | not read from the message; one turn is about 1/7.7 = 0.13 s (period seen 0.119 to 0.139 s) |
| `intensities[]` | Signal strength per beam, if the driver fills it | not checked on this robot |

### Index to angle to x, y

```
laser_angle = angle_min + i * angle_increment          # radians, in the lidar's frame
robot_angle = laser_angle + 90 deg                      # radians, in the robot's frame (section 3)
x = lidar_x + r * cos(robot_angle)                      # forward, metres   (lidar_x = -0.04)
y =           r * sin(robot_angle)                      # left, metres

# the other way round:
i = round((laser_angle - angle_min) / angle_increment)
```

Worked example, beam 178: laser angle = -3.1241 + 178 x 0.0087145 = -1.5729 rad = -90.1 deg. Robot angle = -90.1 + 90 = -0.1 deg, so the beam points straight ahead. If it reads `r` = 1.00 m, then x = -0.04 + 1.00 x cos(-0.1 deg) = 0.96 m and y = -0.002 m. (Measured from the lidar itself, x = 1.00 m, which is also correct if you want positions relative to the lidar.) The robot frame has x forward and y to the left; positive angles turn left (counter-clockwise seen from above).

### What the unusual values mean

- **`inf`**: the beam did not hit anything within range (open door, far wall beyond 12 m), or the surface sent nothing back (glass, very dark or very shiny things). Not an error.
- **Smaller than `range_min`** (0.15 m): too close to measure reliably. Ignore it.
- **`nan`**: also no measurement. The test `range_min < r < range_max` rejects `inf`, `nan` and both out-of-limit cases in one line, which is what the example programs use.
- **About 72 % valid** is normal in a lab. Never treat `inf` as "distance 0" or "very far" without deciding on purpose: a program that stops only when it sees a small number will drive happily at a black wall that returns `inf`.

Note: `angle_min` is -3.1241, not -pi, and the last beam is at +3.1416. So the beam at exactly 180 degrees (the robot's right) is index 719 (718.996 by the formula); the beam at -179 degrees is index 0.

## 3. The +90 degree mounting

This is the one thing that confuses everybody. The lidar sits on top of the robot **turned 90 degrees**, so the angle the lidar calls 0 is not the front of the robot. The transform from `base_link` (the robot) to `rplidar_link` (the lidar), measured on this robot: translation (-0.040, 0, 0.193) m (4 cm behind the robot's centre, 19 cm up) and a rotation of **yaw +90 deg**. Therefore:

**robot angle = laser angle + 90 deg**, so straight ahead is **laser -90 deg** (beam about 178).

```
                    FRONT
          robot 0 = laser -90 = beam 178
                      ^   robot x axis
                      |
   LEFT            .-----.            RIGHT
 robot +90   <--- (  o    )           robot -90
 laser 0          '-----'             laser +-180
 beams 358-359   (o = lidar,          beams 719 and 0
 (laser's own     4 cm behind
  "forward")      the centre)
                    BEHIND
          robot +-180 = laser +90 = beam 539
```

| Direction | Robot angle | Laser angle | Beam index |
|---|---|---|---|
| Front | 0 | -90 | about 178 |
| Left | +90 | 0 | 358 / 359 |
| Behind | +-180 | +90 | about 539 |
| Right | -90 | +-180 | 719 and 0 |

### How the example programs find the offset

They ask ROS's transform system (TF) for the transform `base_link` to the scan's `frame_id`, take its yaw from the rotation (a quaternion), and add that yaw to every beam angle. In `clearance_check.py`: `tf_buffer.lookup_transform('base_link', node.scan.header.frame_id, rclpy.time.Time())`, then `yaw_of(t.transform.rotation)`. You can hard-code +90 deg instead, but then your program is wrong if the lidar is ever remounted.

**The fallback if TF is missing.** [`lidar_snapshot.py`](../examples/lidar_snapshot.py) waits 5 s and then uses **+90 deg** with a warning. [`clearance_check.py`](../examples/clearance_check.py) used to assume **0 deg** ("the lidar faces forward"), which on this robot is wrong by 90 deg (it would look at the robot's left). Fixed in the repository on 2026-10-10: it now also falls back to +90 deg, with a warning. The copy on the robot (copied 2026-10-03) still has the old fallback until the programs are copied again ([ROADMAP.md](../ROADMAP.md), TB-23); while TF works, both versions read the correct +90 deg. The program in section 6 uses +90 deg. To look at the transform yourself: `ros2 run tf2_ros tf2_echo base_link rplidar_link` (run on this robot on 2026-10-04: translation (-0.040, 0, 0.193) m, yaw 90 deg).

## 4. Lidar explorer (HTML page only)

The interactive simulator is in [lidar-guide.html](lidar-guide.html) (open it from a downloaded copy). It simulates 720 beams from -3.1241 rad in 0.0087145 rad steps, range 0.15 to 12 m, the lidar 4 cm behind the centre and turned +90 deg, in a room you edit (drag boxes, add boxes, draw walls). It lets you:

- hover or tap a dot to see beam index, laser angle, robot angle, range and x, y in the robot frame;
- switch between the robot frame and the raw laser frame (the picture turns 90 deg);
- see the +-30 deg "ahead" sector, its nearest distance, and what `clearance_check.py` would print and exit with for a limit of 0.3 to 1.5 m (default 0.6);
- add noise, and a "glass / black surface" setting, to see why only about 72 % of beams are valid in a real room;
- see all 720 `ranges[]` values as a heat bar with markers for front (178), left (358-359), behind (539) and right (0 and 719).

It is a simulation: ideal flat walls, simple noise. Open it with `#autoplay` at the end of the address to get a preset room with a beam selected.

## 5. Get the data by hand

Run these in a terminal on the robot (connect first: [How to connect](../HOW-TO-CONNECT.md)). ROS command-line calls are slow on the Pi: expect 30 to 60 s per command and 10 to 20 s for a Python program to start.

**1. Undock first.** The lidar is off on the dock. Clear about 1 m behind the robot (it backs out and turns 180 degrees), then (verified on this robot 2026-10-04; fails if already undocked):

```
ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}"
```

Lifting the robot off the dock also starts the lidar. Wait a few seconds for the first scans.

**2. Is the topic there?** (both run on this robot on 2026-10-04; the topic list was filtered with a wider pattern)

```
ros2 topic list | grep scan
ros2 topic info /scan -v
```

Expect `/scan`; the verbose info lists the publisher (`rplidar_composition`), its QoS settings and the type `sensor_msgs/msg/LaserScan`. On 2026-10-04 it showed one publisher (`rplidar_composition`, reliable) and one subscriber (`turtlebot4_diagnostics`, best effort).

**3. How fast?**

```
ros2 topic hz /scan
```

Expect about **7.7 Hz** (7.745 Hz measured, period 0.119 to 0.139 s). Stop with Ctrl+C. Jazzy's `hz` has no `--qos-reliability` option; you do not need one.

**4. One raw message.**

```
ros2 topic echo --once --full-length /scan
```

Without `--full-length`, `echo` cuts arrays at **128 entries** and prints `'...'`, so you would see about a sixth of `ranges[]`. The full message is long (720 values); add `> scan.txt` or pipe to `less`.

**5. The example programs.** All are in [`TurtleBot/examples/`](../examples/README.md#sensor-programs-that-do-not-move-the-robot); none moves the robot. What each prints is taken from reading its source; it was not re-run for this guide.

| Run | What it prints |
|---|---|
| `python3 scan_test.py` | One line per scan until Ctrl+C: `Nearest object: 1.44 m` (nearest valid beam in any direction, as a ROS log line). Does not use angles. |
| `python3 clearance_check.py 0.6` | Reads one scan and prints, for example, `lidar frame offset 90 deg, beams in front: 121, nearest in front: 1.17 m (limit 0.60 m)`. Argument = limit in metres (default 0.6). Exit code 0 = clear (nearest > limit), 1 = blocked, 2 = no scan (`NO SCAN: the lidar is not publishing`). Check with `echo $?`. |
| `python3 lidar_snapshot.py --count 3 --out ~/robot_code/room.json` | Saves scans (robot-frame angles) to JSON, or CSV if the name ends in `.csv`, then prints the valid-beam percentage, the lidar yaw and its source (`tf` or `fallback`), and the nearest return in each of 36 sectors of 10 deg as a text bar chart. Exit 2 if no scan. |
| `python3 scan_plot_html.py room.json` | Runs on any computer, no ROS. Writes `room.html`, a polar plot with the robot in the middle, front up. Options `--out`, `--max-range`. |
| `python3 sensor_report.py --seconds 20` | Rates and gaps for `/odom`, `/scan` (expect about 7.7 Hz), `/imu`, `/battery_state`, `/dock_status`, plus the lidar's valid-beam percentage, min and median range, and its yaw from TF. Safe on the dock. |
| `python3 health_check.py` | PASS / WARN / FAIL rows with fix hints, including the lidar USB device and, off the dock, the `/scan` rate and valid beams. Exit 0 all fine, 1 warning, 2 failure. |

**6. Save a scan and plot it on your own computer.** On the robot (the examples are in `~/robot_code`):

```
python3 ~/robot_code/lidar_snapshot.py --count 3 --out ~/robot_code/room.json
```

Then on your computer, in the folder that contains `scan_plot_html.py` (`TurtleBot/examples`), copy the file back and plot it. Replace `<address>` with the robot's address from its display, or `turtlebot4.local`.

Windows (PowerShell):

```
scp ubuntu@<address>:robot_code/room.json .
python scan_plot_html.py room.json
start room.html
```

macOS:

```
scp ubuntu@<address>:robot_code/room.json .
python3 scan_plot_html.py room.json
open room.html
```

Linux:

```
scp ubuntu@<address>:robot_code/room.json .
python3 scan_plot_html.py room.json
xdg-open room.html
```

On Windows the command may be `python` or `py`. This whole chain was not run end to end for this guide.

## 6. Use it in your own code

A complete minimal ROS 2 (rclpy) program: it subscribes to `/scan`, finds the nearest obstacle within +-30 degrees of straight ahead (using the +90 deg offset, read from TF with a fallback) and prints it twice a second. It follows the same pattern as `clearance_check.py` and does not move the robot. It was checked with `python -m py_compile` and its calculation was run on a fake scan on a PC; **it has not been run on the robot**.

Three things matter. **Subscribe with `qos_profile_sensor_data`** (best effort, small queue), as the example programs do. **Skip invalid beams** with `range_min < r < range_max`. **Add the mounting yaw** before deciding what is "ahead".

```python
"""Print the nearest obstacle in front of the robot, twice a second. Does not move the robot.

"In front" means within +/-30 degrees of straight ahead in the ROBOT frame. The lidar on this
robot is mounted turned +90 degrees, so the program reads the real mounting angle from TF
(base_link -> rplidar_link) and falls back to +90 degrees if TF is missing.
Needs the robot off the dock (the lidar is switched off while docked).
Usage: python3 front_distance.py        (stop with Ctrl+C)
"""
import math
import time

import rclpy
import tf2_ros
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

HALF_WIDTH = math.radians(30)   # "in front" = +/-30 degrees
FALLBACK_YAW = math.radians(90)  # measured on this robot; used only if TF never arrives
TF_WAIT = 5.0                   # s, wait this long for TF before using the fallback
PRINT_PERIOD = 0.5              # s, print twice a second
STALE_AFTER = 2.0               # s, no new scan for this long = say so


def wrap(angle):
    """Wrap an angle in radians to [-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def yaw_of(q):
    """Yaw (rotation about the vertical axis) of a quaternion."""
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def nearest_in_front(scan, yaw):
    """Return (nearest range in metres or None, number of valid beams in front)."""
    nearest, count = None, 0
    for i, r in enumerate(scan.ranges):
        if not (scan.range_min < r < scan.range_max):
            continue                      # inf, nan, too close or too far: no usable return
        laser_angle = scan.angle_min + i * scan.angle_increment
        robot_angle = wrap(laser_angle + yaw)   # 0 = straight ahead, + = left
        if abs(robot_angle) <= HALF_WIDTH:
            count += 1
            if nearest is None or r < nearest:
                nearest = r
    return nearest, count


class FrontDistance(Node):
    def __init__(self):
        super().__init__('front_distance')
        self.scan = None
        self.scan_time = 0.0
        self.first_scan_time = None
        self.yaw = None
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        # Sensor data QoS (best effort) matches how the lidar driver publishes /scan.
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_timer(PRINT_PERIOD, self.report)

    def on_scan(self, msg):
        self.scan = msg
        self.scan_time = time.monotonic()
        if self.first_scan_time is None:
            self.first_scan_time = self.scan_time
        if self.yaw is None:
            try:
                t = self.tf_buffer.lookup_transform('base_link', msg.header.frame_id, rclpy.time.Time())
                self.yaw = yaw_of(t.transform.rotation)
            except tf2_ros.TransformException:
                pass                      # TF not there yet; try again on the next scan

    def report(self):
        now = time.monotonic()
        if self.scan is None or now - self.scan_time > STALE_AFTER:
            print('no scan: is the robot on the dock? (the lidar is off there)', flush=True)
            return
        yaw = self.yaw
        if yaw is None:
            if now - self.first_scan_time < TF_WAIT:
                return                    # give TF a few seconds
            yaw = FALLBACK_YAW
            print('warning: no TF for the lidar, assuming it is turned +90 deg', flush=True)
        nearest, count = nearest_in_front(self.scan, yaw)
        if nearest is None:
            print('nothing in front (no valid beam within +/-30 deg)', flush=True)
        else:
            print(f'nearest in front: {nearest:.2f} m ({count} beams)', flush=True)


def main():
    rclpy.init()
    node = FrontDistance()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
```

### Copy it to the robot and run it

Save the program as `front_distance.py` on your computer. Then, from that folder:

```
scp front_distance.py ubuntu@<address>:robot_code/
ssh ubuntu@<address>
python3 ~/robot_code/front_distance.py
```

The robot must be off the dock. Stop with Ctrl+C. Output looks like `nearest in front: 1.17 m (109 beams)`. If you start it from a script or `ssh host command` (a non-login shell), run `source /etc/turtlebot4/setup.bash` first. [How to connect](../HOW-TO-CONNECT.md) lists the other ways to get code onto the robot (VS Code Remote-SSH, `nano`).

### Scan to x, y points

To draw the scan, build a map or fit lines you usually want points rather than (angle, distance) pairs. This function converts a scan to points in the robot frame (x forward, y left, origin at the robot's centre). It needs no ROS to test: any object with `ranges`, `angle_min`, `angle_increment`, `range_min` and `range_max` works.

```python
import math

LIDAR_YAW = math.radians(90)   # lidar mounting, from TF (see above); +90 deg on this robot
LIDAR_X = -0.04                # lidar is 4 cm behind the robot centre (TF translation x)
LIDAR_Y = 0.0


def scan_to_xy(scan, yaw=LIDAR_YAW):
    """Convert a LaserScan to a list of (x, y) points in metres in the robot frame.

    x is forward, y is left, the origin is the robot centre (base_link).
    Beams without a usable return (inf, nan, below range_min, above range_max) are skipped.
    """
    points = []
    for i, r in enumerate(scan.ranges):
        if not (scan.range_min < r < scan.range_max):
            continue
        laser_angle = scan.angle_min + i * scan.angle_increment   # angle in the lidar's own frame
        a = laser_angle + yaw                                     # angle in the robot frame
        # point in the robot frame = lidar position + range along that direction
        points.append((LIDAR_X + r * math.cos(a), LIDAR_Y + r * math.sin(a)))
    return points
```

Call it inside `on_scan`: `points = scan_to_xy(msg, self.yaw)`. The CSV from `lidar_snapshot.py` has `x_m, y_m` columns of the same kind; that program computes x, y from the lidar's position, without the 4 cm offset.

## 7. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| No `/scan`, or no messages | The robot is on the dock; the lidar is off there. | Undock (section 5) or lift the robot off the dock; wait a few seconds. |
| No `/scan` shortly after boot | The robot is still starting. | Wait about 2 minutes after switching on (until the chime and the address on the display), then check again. Each ROS command is slow. |
| No `/scan` although undocked and started | The lidar is not detected on USB (happened 2026-10-03: a loose cable). The lidar may still spin, because the motor and the data link are separate. | On the robot: `lsusb \| grep 10c4:ea60` must show a Silicon Labs CP210x line and `ls -l /dev/RPLIDAR` must show a link to `ttyUSB0`. If not, switch the robot off, reseat the lidar's USB cable, start again. See [the diagnosis page](lidar-diagnosis.html). |
| `echo` shows only 128 values | `ros2 topic echo` truncates long arrays. | `ros2 topic echo --once --full-length /scan` |
| A script says `ros2: command not found` (or `No module named rclpy`) | A non-login shell does not load the ROS setup. | Run `source /etc/turtlebot4/setup.bash` first. |
| My program waits forever, no callback | QoS mismatch (the subscriber asks for a policy the publisher does not offer), or the robot is docked. | Subscribe with `qos_profile_sensor_data` (section 6). Check `ros2 topic hz /scan` first. |
| Distances look rotated by 90 deg | Your code treats the laser angle as the robot angle. | Add the +90 deg mounting offset (section 3). Front is laser -90 deg, about beam 178. |
| Many `inf` values | Normal: nothing within 12 m, or glass, very dark or very shiny surfaces. About 72 % valid is typical. | Skip them with `range_min < r < range_max`. If far lower than usual in a normal room, check the head is clean and not blocked. |
| RViz from a laptop does not work | ROS 2 discovery across the network has not been tested on campus Wi-Fi ([TB-09](../ROADMAP.md#tb-09-ros-2-from-a-laptop-over-campus-wi-fi)). Untested on campus. | Save a scan on the robot and plot it on your computer (section 5), or run RViz on the robot. |

## 8. Safety

- **Laser.** The RPLIDAR A1M8 contains a laser. For its safety class and the exact wording about looking at it, see the manufacturer's manual (and the TurtleBot 4 user manual). This page does not state a class because the wording was not checked here.
- **Do not touch the spinning head** while it turns, and do not hold it still.
- **Do not block or cover the head.** Anything on or around it gives wrong distances and hides obstacles from your program. Keep it clean and keep cables clear of it.
- These programs only read the lidar. When you later use it to drive the robot, follow the lab rules in the [safety checklist](../examples/README.md#safety-checklist-before-anything-moves): 0.15 m/s at most, 1 m clear around the robot, a person next to it. Glass and black surfaces can be invisible to the lidar, so a lidar-only stop is not a guarantee.

## Not verified on this robot

The commands marked "untested", the two Python programs in section 6 (compiled and run on a fake scan only), the copy-and-plot chain in section 5, the output formats of the example programs (read from source, not re-run), and RViz from a laptop. The explorer is a simulation.
