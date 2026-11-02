# Lidar auto-restart for the TurtleBot 4

A small service that starts the lidar motor again when it did not start after an undock.

## What it does

The TurtleBot 4 dock power saver stops the lidar motor while the robot is docked. Sometimes the motor is not started again after an undock, `/scan` stays silent, and programs fail with "no /scan" ([ROADMAP.md, TB-24](../../ROADMAP.md#tb-24-lidar-motor-does-not-restart-after-undocking)). By hand the fix is `ros2 service call /start_motor std_srvs/srv/Empty`, after which `/scan` returns at about 7.6 Hz. This service does that automatically:

- Docked: it does nothing.
- Undocked (or the service starts while the robot is undocked): wait 10 s. If no `/scan` arrived in the last 3 s, call `/start_motor`, wait 8 s and check again.
- At most 3 calls per undock. Then it logs one warning and stops trying until the next undock.

It never publishes to `/cmd_vel` and never calls a motion action. Its only action on the robot is the `/start_motor` call. The decision logic is a plain Python class tested offline ([test_lidar_restart.py](../../tests/offline/test_lidar_restart.py)).

## Install (on the robot, once)

Copy this folder to the robot, then run the installer there with root rights (a terminal on the robot, for example over SSH):

```bash
cd lidar-restart
sudo ./install.sh
```

It copies the program to `/usr/local/lib/tb4/` and the unit to `/etc/systemd/system/`, and enables the unit. The service starts 20 s after `turtlebot4.service` and stops and restarts with it. A different file already at a target path is kept as a `.before-<time>` copy.

## Verify

```bash
systemctl status tb4-lidar-restart
journalctl -u tb4-lidar-restart -n 30 --no-pager
```

Expected: `active (running)`, and log lines such as "undocked: checking /scan in 10 s" and "/scan is arriving, lidar is running". After an undock, `ros2 topic hz /scan` should show the scan rate.

## Undo

```bash
sudo ./uninstall.sh
```

Stops and disables the service and deletes the two installed files.

## Note on the Create 3 base (TB-25)

TB-25 found that each new ROS participant joining the graph can trigger Create 3 base stalls of several seconds. This service joins the graph once, right after the bringup starts at boot (hence the 20 s start delay), and uses a single node without parameter services. It does not join again later, except when the bringup restarts. Not yet verified on the robot: whether even that one join causes a stall.

## Files

| File | Purpose |
|---|---|
| `tb4_lidar_restart.py` | The ROS 2 node and the decision logic |
| `tb4-lidar-restart.service` | systemd unit (user `ubuntu`, ROS environment from `/etc/turtlebot4/setup.bash`) |
| `install.sh`, `uninstall.sh` | Add-only install and its undo |
