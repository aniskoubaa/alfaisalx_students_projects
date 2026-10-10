# Lidar diagnosis: "lidar not detected" (2026-10-03), resolved 2026-10-04

Markdown version of [lidar-diagnosis.html](lidar-diagnosis.html), for reading on GitHub. The admin record is in [MAINTENANCE.md](../MAINTENANCE.md#incident-lidar-not-detected-2026-10-03-resolved-2026-10-04); the task is [ROADMAP.md, TB-02](../ROADMAP.md#tb-02-fix-lidar-detection).

This page is the fault story. To use the lidar (how it works, how to read and use its data), see the [lidar user guide](LIDAR-GUIDE.md) ([interactive version](lidar-guide.html)).

| | |
|---|---|
| Robot | Lab TurtleBot 4 Standard, `ubuntu@turtlebot4.local` |
| Fault | Lidar spins but is not detected on USB; no `/scan` |
| Found | 2026-10-03, about 20:31 (laptop time, UTC+3) |
| Resolved | 2026-10-04, before the 11:44 boot (robot time, EDT) |
| Root cause | Loose USB connection between the lidar and the Raspberry Pi |
| Fix | Lidar USB cable reseated (same cable, same port). No software change |
| Times | 2026-10-04 times are the robot's clock as shown in its journal (EDT, UTC-4). 11:44 EDT is 18:44 in UTC+3, the time zone used in the 2026-10-03 notes |

## Verdict

The lidar hardware and software are fine. The USB data connection was loose. After the cable was reseated, every layer checked out: USB device, device link, driver, ROS topic and scan data. The "no `/scan` while docked" behaviour is the TurtleBot 4 power saver, not a fault.

## Symptoms on 2026-10-03

- The lidar spun.
- `lsusb` showed no Silicon Labs CP210x device, docked or undocked.
- `/dev/RPLIDAR` did not exist.
- The driver log said "cannot bind to the specified serial port '/dev/RPLIDAR'".
- A full power cycle (Pi shut down, base off and on) did not help.

Spinning shows the lidar had power. The lidar's motor and its USB data link are separate, so a loose data connection gives exactly this picture.

## Checks on 2026-10-04, layer by layer

All checks were read only. Run them in a terminal on the robot (`ssh ubuntu@turtlebot4.local`).

### 1. Physical and USB

```bash
lsusb | grep -i -E "silicon labs|cp210"
ls -la /dev/RPLIDAR /dev/ttyUSB0
```

| Item | Value on 2026-10-04 |
|---|---|
| USB device | `10c4:ea60` Silicon Labs CP210x UART Bridge |
| Device link | `/dev/RPLIDAR -> ttyUSB0` |
| Serial port | `crw-rw-rw-`, owner `root`, group `dialout` |
| Kernel log | Not read: `dmesg` needs `sudo` on this robot |

### 2. Driver

```bash
journalctl -u turtlebot4 -b --no-pager | grep -i -E "rplidar|RPLIDAR"
```

| Item | Value |
|---|---|
| Node | `rplidar_composition` started |
| Serial number | `6DE9ED95C4E493C8A5E69EF0FC394B6C` |
| Firmware | 1.29 |
| Hardware revision | 7 |
| Health status | 0 (OK) |
| Scan mode | Sensitivity, maximum distance 12 m, 7.9K samples/s |
| Power saver | 11:48 "RPLIDAR stopped" (on the dock); 12:09:54 "RPLIDAR started" (after undock) |

### 3. ROS

```bash
printenv | grep -E "ROS_DOMAIN_ID|RMW_IMPLEMENTATION|ROS_AUTOMATIC_DISCOVERY_RANGE"
ros2 node list
ros2 topic info -v /scan
```

| Item | Value |
|---|---|
| Environment | `ROS_DOMAIN_ID=0`, `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`, `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` |
| Relevant nodes | `/rplidar_composition`, `/turtlebot4_base_node`, `/oakd`, `/turtlebot4_diagnostics` |
| `/scan` | 1 publisher (reliable); subscriber `turtlebot4_diagnostics` (best effort) |
| `/cmd_vel` | `geometry_msgs/msg/TwistStamped`; subscriber `create3_repub` (best effort); `teleop_twist_joy` publishes |
| Base | `/dock_status` received; Pi and base clocks within seconds of each other |

### 4. Data (off the dock)

The robot was undocked with `ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}"`, sent detached; it succeeded at about 12:09.

```bash
ros2 topic hz /scan
ros2 topic echo --once --full-length /scan
ros2 run tf2_ros tf2_echo base_link rplidar_link
cd ~/robot_code && python3 clearance_check.py 0.6; echo "exit code $?"
```

| Item | Value |
|---|---|
| Rate | 7.75 Hz; period 0.119 to 0.139 s; standard deviation 0.0064 s |
| Frame | `rplidar_link` |
| Angles | `angle_min` -3.124 rad, `angle_max` 3.1416 rad, `angle_increment` 0.008715 rad: 720 beams, one every 0.5 degrees |
| Range limits | `range_min` 0.15 m, `range_max` 12.0 m |
| Valid beams | 519 of 720 (72 %) |
| Ranges | 0.261 to 6.800 m, median 1.442 m |
| Mount | `base_link` to `rplidar_link`: translation (-0.040, 0, 0.193) m, yaw +90 degrees |
| `clearance_check.py 0.6` | "lidar frame offset 90 deg, beams in front 78, nearest in front 1.73 m", exit code 0 |

Because of the +90 degree mount, straight ahead of the robot is laser angle -90 degrees. The front sector of ±30 degrees therefore covers laser angles -120 to -60 degrees. At 0.5 degrees per beam that is about 120 beams; 78 of them were valid in this scan.

## The dock power saver

| Robot state | Lidar | `/scan` |
|---|---|---|
| On the dock | Stopped by `turtlebot4_node` ("RPLIDAR stopped") | Publisher present, no messages |
| Undocked | Started ("RPLIDAR started") | About 7.75 Hz |

Always undock (or lift the robot off the dock) before judging the lidar.

## Gotchas found on the way

- `ros2 topic echo` shows only the first 128 entries of an array, then `...`. Add `--full-length` to see all 720 ranges.
- `ros2 topic hz` in ROS 2 Jazzy has no `--qos-reliability` option (the command fails with an argument error). Run it without the option; it receives `/scan`.
- `dmesg` needs `sudo` on this robot.
- Long-running `ros2 action send_goal` calls should be sent detached (`setsid nohup ... &`) so a Wi-Fi drop does not cancel them.

## Follow-ups

- Confirm detection after the next, separate reboot (only the boot right after the reseat has been checked). Update 2026-10-10: after the robot was powered off and switched on again on 2026-10-04, a single SSH check at about 15:42 (robot time) found the lidar on USB; no `/scan` result was recorded. Keep checking after restarts.
- Strain relief and a label for the lidar cable: [ROADMAP.md, TB-18](../ROADMAP.md#tb-18-lidar-cable-strain-relief-and-label).
- Read-only health check script: [ROADMAP.md, TB-19](../ROADMAP.md#tb-19-read-only-health-check-script). Written as [examples/health_check.py](../examples/health_check.py) and tested offline; first robot run pending (2026-10-10).
