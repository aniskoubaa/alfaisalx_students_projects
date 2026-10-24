# TurtleBot 4 tests

Raw logs and diagnostic scripts from the lidar check and the first motion-program runs on 2026-10-04. Times in the logs are robot time (EDT). The write-up is in [../docs/test-results.html](../docs/test-results.html) and [../MAINTENANCE.md](../MAINTENANCE.md).

Status on 2026-10-24: new robot logs from a session over a direct Ethernet cable (rows dated 2026-10-24 below). Times inside them are robot time, and the robot clock read 2024-10-28 that day, so the timing tools use seconds since the start of the recording instead.

Update 2026-10-24, evening: three more logs from the same day, recorded over the robot's home Wi-Fi with the robot clock correct (robot time = laptop time minus 7 hours). They are the last three rows of the table below.

Status on 2026-10-10: no robot runs since 2026-10-04 (the robot has been dropping off the Wi-Fi, see [../docs/network-and-connectivity.html](../docs/network-and-connectivity.html)), so there are no new logs. The offline tests below were rerun on 2026-10-10: 101 checks and 38 scenarios, 0 failures.

## Logs (`logs/`)

| File | What it records | Outcome |
|---|---|---|
| `2026-10-04_undock.log` | `/undock` action, sent detached | SUCCEEDED |
| `2026-10-04_shapes_square.log` | `motion_shapes.py square` with `ODOM_STALE` 1.0 s | Done: 8 segments in 39 s, odometry error 0.9 cm, +0.8 deg |
| `2026-10-04_shapes_rest.log` | rotate, back_and_forth, triangle (same version) | rotate 0.1 cm / +0.7 deg; back_and_forth 0.6 cm / +0.9 deg; triangle ABORTED on a 1.0 s odometry gap |
| `2026-10-04_shapes_rest2.log` | triangle with the hold fix | Refused at start: path not clear (0.48 m ahead, needs 0.65 m). Correct behaviour |
| `2026-10-04_shapes_rest3.log` | `/rotate_angle` 180 deg, triangle, figure_eight | Turn SUCCEEDED; triangle done 1.0 cm / +2.2 deg with holds of 11, 8 and 1 cycles; figure_eight ABORTED on a 2.0 s odometry gap (robot held still) |
| `2026-10-04_odomprobe.log` | 10 cm instrumented drive | Largest `/odom` gap 0.413 s (header stamps 0.419 s) 0.12 s after motion start |
| `2026-10-24_idle_timing_summary.json` | 180 s idle timing probe, robot docked, connected by Ethernet | `/odom` 19.9 Hz; one 1.31 s gap at the probe's own start-up, otherwise clean; no ping loss to the base; Pi and base clocks within 31 ms (median) |
| `2026-10-24_timing_motion.jsonl.gz` | 300 s run of [../tools/timing/record_timing.py](../tools/timing/record_timing.py) during undock, a 0.3 m drive and dock (gzip; read it with [../tools/timing/analyze_timing.py](../tools/timing/analyze_timing.py)) | Undock: all base topics stalled 1.39 s. Drive: stall 2.0 s after the start, longest `/odom` gap 3.16 s, `motion_shapes.py back_and_forth` ABORTED on stale odometry. Header stamps stopped too, base ping 0 % loss but slower, Pi CPU at most 61 % |
| `2026-10-24_wifi_powersave.log` | Read-only Wi-Fi power-save checks (NetworkManager configuration, profiles, driver) | Power saving on by default for all profiles; changed for `Students` afterwards (MAINTENANCE.md R14) |
| `2026-10-24_wifi_journal_keyevents.log` | Wi-Fi events from the journals of the earlier boots (connects, disconnects, roams, rejects) | No disconnects on the days with the SSH-window symptom; three disconnects in the long session of 2026-10-04 |
| `2026-10-24_timing_wifi_before_base_restart.jsonl.gz` | Evening, over Wi-Fi: 607 s `record_timing.py --light` run starting 22:00:27 robot time (05:00:27 laptop time), covering an idle stall, the undock through Studio and the first spin | `/odom` stall of 7.51 s at idle, 7.81 s gap in the spin that aborted. The robot clock was correct (gzip; read it with [../tools/timing/analyze_timing.py](../tools/timing/analyze_timing.py)) |
| `2026-10-24_timing_wifi_after_base_restart.jsonl.gz` | Evening, over Wi-Fi: 1500 s `--light` run starting 22:11:11 robot time (05:11:11 laptop time), after the first Create 3 application restart; second spin, circle, dock, base clock re-sync, second base restart, idle | No stall over 0.68 s in the spin and the circle; 373 s of silence during the second base restart; an 11 s idle stall at 22:35 robot time. Recorder used 7.4 % of one core |
| `2026-10-24_studio_motion_runs.log` | Output of the programs run through Studio in the evening (`my_spin_in_place.py`, `my_drive_circle.py`) | First spin ABORTED ("odometry is stale"); second spin done, 359 degrees in 14 s; circle done in about 22 s, but its "17.3 cm from the start" closure is not valid (robot crossed the dock edge and was moved by hand) |

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

## Documentation link check

[`check_links.py`](check_links.py) checks every relative link and `#anchor` in the Markdown and HTML files under `TurtleBot/`, and exits 1 if any is broken. Run it from the repository root with `python TurtleBot/tests/check_links.py`. The GitHub workflow runs it too, so a broken link fails the check.

To try one program by hand against the simulator: `python sim.py motion square --yes` (scenarios: `motion`, `shapes`, `wall`, `keep`, `report`, `snapshot`, `light`, `health`; environment variables `SIM_ODOM_GAP="t0,length"`, `SIM_DOCKED=1`, `SIM_WALL=metres`, `SIM_OBJECT="x0,vx"`, `SIM_ROOM` (room radius in m, 0 = no walls), `SIM_HEALTH="fault,fault"` (faults listed at the top of sim.py)).

Passing these tests does not prove a program works on the robot. Timing, odometry dropouts and real sensors only show up on the robot; record those runs in the logs above.
