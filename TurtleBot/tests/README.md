# TurtleBot 4 tests

Raw logs and diagnostic scripts from the lidar check and the first motion-program runs on 2026-10-04. Times in the logs are robot time (EDT). The write-up is in [../docs/test-results.html](../docs/test-results.html) and [../MAINTENANCE.md](../MAINTENANCE.md).

## Logs (`logs/`)

| File | What it records | Outcome |
|---|---|---|
| `2026-10-04_undock.log` | `/undock` action, sent detached | SUCCEEDED |
| `2026-10-04_shapes_square.log` | `motion_shapes.py square` with `ODOM_STALE` 1.0 s | Done: 8 segments in 39 s, odometry error 0.9 cm, +0.8 deg |
| `2026-10-04_shapes_rest.log` | rotate, back_and_forth, triangle (same version) | rotate 0.1 cm / +0.7 deg; back_and_forth 0.6 cm / +0.9 deg; triangle ABORTED on a 1.0 s odometry gap |
| `2026-10-04_shapes_rest2.log` | triangle with the hold fix | Refused at start: path not clear (0.48 m ahead, needs 0.65 m). Correct behaviour |
| `2026-10-04_shapes_rest3.log` | `/rotate_angle` 180 deg, triangle, figure_eight | Turn SUCCEEDED; triangle done 1.0 cm / +2.2 deg with holds of 11, 8 and 1 cycles; figure_eight ABORTED on a 2.0 s odometry gap (robot held still) |
| `2026-10-04_odomprobe.log` | 10 cm instrumented drive | Largest `/odom` gap 0.413 s (header stamps 0.419 s) 0.12 s after motion start |

The first square attempt (ODOM_STALE 0.5 s) aborted after 1 s; its log was overwritten by the next run. The record is in the General Tasks log.

## Diagnostic scripts

Run on the robot (`source /etc/turtlebot4/setup.bash` first). They expect `motion_shapes.py` in `~/robot_code`.

| Script | Moves the robot? | What it does |
|---|---|---|
| `gapprobe.py` | No | Runs the `motion_shapes` control loop for 20 s without a velocity publisher and reports the worst odometry age |
| `gapprobe0.py` | No | Same, but publishes **zero** velocity at 20 Hz, to test whether publishing causes gaps |
| `odomprobe.py` | **Yes, 10 cm forward at 0.05 m/s** | Logs every `/odom` arrival and header-stamp gap during a short drive |
| `opensectors.py` | No | Prints the nearest lidar range per 30 degree sector in the robot frame (0 = ahead, + = left); use it to choose a clear direction |

For a fuller sensor-rate report use [../examples/sensor_report.py](../examples/sensor_report.py).

## Offline tests (`offline/`, any computer, no robot, no ROS)

These check the example programs without a robot. `sim.py` replaces ROS with small stand-ins and simulates a robot with a virtual clock, so a 40 s shape runs in well under a second. They need only Python 3.10 or newer.

```bash
cd TurtleBot/tests/offline
python test_pure.py        # 101 logic checks: shape plans, angle maths, lidar sectors, controllers, scan plot HTML, health thresholds
python test_sim_runs.py    # 38 simulated runs: every shape, odometry gaps, docked refusal, fence, wall approach, 18 health-check faults
```

`test_sim_runs.py` also checks two safety rules on every simulated run: the speed never goes above 0.15 m/s or 1.0 rad/s, and the last command sent is zero velocity. Generated files go to a temporary folder, not into the repository.

The same tests run on GitHub on every push that changes `TurtleBot/` ([.github/workflows/turtlebot-tests.yml](../../.github/workflows/turtlebot-tests.yml)).

To try one program by hand against the simulator: `python sim.py motion square --yes` (scenarios: `motion`, `shapes`, `wall`, `keep`, `report`, `snapshot`, `light`, `health`; environment variables `SIM_ODOM_GAP="t0,length"`, `SIM_DOCKED=1`, `SIM_WALL=metres`, `SIM_OBJECT="x0,vx"`, `SIM_ROOM` (room radius in m, 0 = no walls), `SIM_HEALTH="fault,fault"` (faults listed at the top of sim.py)).

Passing these tests does not prove a program works on the robot. Timing, odometry dropouts and real sensors only show up on the robot; record those runs in the logs above.
