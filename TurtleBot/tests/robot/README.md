# Robot diagnostics

Small diagnostic scripts from the lidar check and the odometry gap work of 2026-10-04. They run on the robot, not on a laptop. Used when checking how late `/odom` messages arrive.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `gapprobe.py` | Runs the `motion_shapes` control loop for 20 s without a velocity publisher and reports the worst odometry age. Does not move the robot | robot |
| `gapprobe0.py` | Same, but publishes zero velocity at 20 Hz, to test whether publishing causes gaps. Does not move the robot | robot |
| `odomprobe.py` | Drives 10 cm forward at 0.05 m/s and logs every `/odom` arrival gap. Moves the robot | robot |
| `opensectors.py` | Reads one lidar scan and prints the nearest range per 30 degree sector in the robot frame (0 = ahead, + = left), to choose a clear direction. Does not move the robot | robot |

They import `motion_shapes.py` from `/home/ubuntu/robot_code`, so copy the example program there first. Copy and run, from the repo root (use `ubuntu@turtlebot4.local` or the address on the robot's display; see [HOW-TO-CONNECT.md](../../HOW-TO-CONNECT.md)):

```bash
scp TurtleBot/tests/robot/gapprobe.py ubuntu@turtlebot4.local:robot_code/
ssh ubuntu@turtlebot4.local
source /etc/turtlebot4/setup.bash
python3 ~/robot_code/gapprobe.py
```

For `odomprobe.py` keep a person next to the robot with the controller, and undock first. The logs of the 2026-10-04 runs are in [../logs/](../logs/).

See also: [tests/README.md, Diagnostic scripts](../README.md#diagnostic-scripts).
