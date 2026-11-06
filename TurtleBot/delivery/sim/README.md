# Delivery simulator (runs on the robot, robot on its dock, cannot move the real base)

This folder runs the REAL Nav2, AMCL, costmap filters and `delivery_mission.py` on the robot's Raspberry Pi against a
fake base. `fake_base.py` imitates the Create 3 base, the lidar and the front panel, so a whole delivery (undock,
drive 60 m along a wall past a glass room and two glass doors, wait for the vendor's button, drive home, wait for the
student's button, dock) can be rehearsed while the real robot sits on its dock. It finds configuration, timing and
interface mistakes before the robot ever drives. It does not prove that the real lidar, floor and glass behave: that
still needs a supervised run.

## Why it cannot move the robot

- Everything runs with `ROS_DOMAIN_ID=77`. The real base (Create 3) and the robot's own ROS programs live in
  domain 0, so nothing published here reaches them and nothing from the real robot reaches the simulator.
- Discovery is forced to this computer (`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`) and a discovery-server setting
  from `/etc/turtlebot4/setup.bash` is dropped, so even a shared discovery server cannot bridge the domains.
- `run_e2e.sh`, `fake_base.py` and `ci_check_params.py` refuse to start when `ROS_DOMAIN_ID` is unset, not a number
  or 0. `run_e2e.sh` checks it before every process it starts and reads `/proc/<pid>/environ` of each process after
  the start. `run_e2e.sh` also refuses to start while a mission or a navigation stack is running (so it can never
  share the robot with a real run), and while `~/STOP` exists.
- Files go only into the run folder `~/robot_code/logs/delivery/sim_<time>_<scenario>/` (and `/tmp`);
  `fake_base.py` refuses any other `--run-dir`. ROS logs go into the run folder too (`ROS_LOG_DIR`).
- The real `~/STOP` file is still honoured: if it appears during a run, the mission and all simulator processes stop.

## Files

| File | What it does |
|---|---|
| `fake_base.py` | One ROS node: `/cmd_vel` (TwistStamped) in; `/odom`, `/tf`, `/tf_static` (`base_link` to `rplidar_link` at +90 deg yaw, and `base_footprint`), `/scan` (5 Hz, 360 beams, 0.15 to 12 m, ray cast on the map, off while docked like the real lidar), `/dock_status`, `/battery_state`, `/hmi/buttons`, `/hazard_detection` out; `/hmi/display/message` and `/cmd_audio` logged; actions `/undock` (about 6 s, backs 0.3 m), `/dock` (only within 1.0 m of the dock pose) and `/wall_follow` (`irobot_create_msgs/WallFollow`, see Closed-loop mapping scenario). Fake human, fault injection, ground-truth log. |
| `sim_map.py` | Writes the synthetic hall (70 m x 12 m, 5 cm cells, straight wall, glass room with a doorway, two glass-door recesses), `route_spec.yaml` for `tools/plan_route.py`, and `sim_world.json` (ground truth for the analysis). |
| `analyse_run.py` | Judges a run: PASS or FAIL per check, writes `results.json`. Also reports (not a pass or fail check) `amcl_error_m` (`max_x`, `max_y`, `median_x`, `last_x`, `last_y`: how far AMCL's estimate is from the true pose) and `dock_goal_distance_m` (true distance to the dock at each `/dock` goal). |
| `run_e2e.sh` | Orchestrates one scenario on the robot. |
| `run_mapping.sh` | The closed-loop scenario: the fake robot maps the hall with the real slam_toolbox, then the real delivery runs on that SLAM map (see Closed-loop mapping scenario). |
| `ci_check_params.py` | Starts the real `map_server` with our mask files and compares what it publishes with the expected values; configures each server in `config/nav2_delivery.yaml` to check that the parameters declare. For the `ros:jazzy` CI job and for the robot. Prints SKIP when ROS is missing. |
| `../../tests/offline/test_delivery_sim.py` | Offline tests (no ROS). |

The hall: dock at (1.5, 0.5) facing +x, lane along the south wall at y = 0.5, pickup at (60, 0.5). The glass room
(x 28 to 34, y -4 to 0) and the door recesses (x 44 to 45.4, 50 to 51.4) are glass: the lidar sees through them, so
the MAP shows pockets, while the ground truth (`--glass`) blocks them. The route spec closes them with keepout lines
(that is what the keepout filter has to do).

Ground truth versus map: Nav2 and AMCL see only the map and the fake scan. The fake base knows the real world (map plus
glass), detects collisions with it (robot radius 0.17 m: BUMP on `/hazard_detection`, stops 3 s) and logs the true pose
and the true distance to the nearest obstacle at 5 Hz.

## How to run (on the robot)

Log in to the robot with ssh first (see `delivery/README.md`, Connecting). Copy the `delivery` folder to
`~/robot_code/delivery` (for example with `scp -r`, see the same README). The robot must be on its dock and no real
mission or navigation stack may be running. Dry run first, it starts nothing:

```bash
bash ~/robot_code/delivery/sim/run_e2e.sh happy --dry-run
```

Then the real simulation (about 10 to 15 minutes; 20 s of that is the mission's TB-25 settle time):

```bash
bash ~/robot_code/delivery/sim/run_e2e.sh happy
```

Detached, so a Wi-Fi drop (TB-10) does not kill it:

```bash
setsid nohup bash ~/robot_code/delivery/sim/run_e2e.sh happy > /tmp/e2e_happy.out 2>&1 < /dev/null &
tail -f /tmp/e2e_happy.out
```

The last line is `E2E <scenario>: PASS (<run folder>)` or `FAIL`. Stop at any time with Ctrl+C, `touch ~/STOP`
(delete it afterwards) or `pkill -INT -f run_e2e.sh`; the script stops everything it started (process groups, SIGINT,
then SIGTERM, then SIGKILL) and analyses what happened.

Knobs (environment): `SIM_DRIFT` (odometry error, for example `0.02` for 2 %; default none, so the fake odometry is perfect; added 2026-11-06), `SIM_GOAL_X=20` for a short run,
`SIM_ACTIVE_WAIT` (s to wait for 'Managed nodes are active', default 150), `SIM_TOTAL_TIMEOUT` (default 1800),
`SIM_DOMAIN` (default 77, never 0). *(The knob `SIM_PAUSE` was removed on 2026-11-06; nothing used it.)* `--keep` keeps the map copy and ROS logs in the run folder.

The run folder holds: `fake_base.log`, `localization.log`, `filters.log`, `nav2.log`, `mission.out`,
`mission_log/delivery_*.log` (the mission's event log), `ground_truth.jsonl`, `top.log` (CPU every 30 s),
`mission_exit.txt`, `results.json`, `route/` (route.yaml and masks), `state.txt`.

## Scenarios and pass criteria

| Scenario | What happens | Expected mission exit code |
|---|---|---|
| `happy` | the fake human presses button 3 at the pickup and 4 at the handoff | 0 |
| `pickup_timeout` | nobody presses; `pickup_timeout_s` is 25 s; the robot drives home and docks | 4 |
| `stall` | `/odom` and `/tf` stop for 5 s, 25 s after the undock (TB-25); the mission holds and goes on | 0 |
| `nav_fail` | the robot jams at the 3rd outbound pose (`--fail-after-pose 3`), `leg_timeout_s` is 120 s | 3 |
| `dock_retry` | the first `/dock` goal fails wherever the robot is (`--dock-fail-first 1`); the mission drives to a point 0.45 m from the dock and docks at the second try (added 2026-11-06) | 0 |

`analyse_run.py` checks, for every scenario: the mission exit code is the expected one; the true robot never entered
the glass room; never closer than 0.20 m to the nearest true obstacle while driving; the median true wall distance on
the straight stretches is within 0.15 m of `wall_offset_m` (0.5 m; skipped for `nav_fail` when fewer than 10 moving
samples lie on a straight stretch); maximum true speed under 0.21 m/s; no BUMP. It also prints the run time, the
distance, and the Pi CPU (mean and maximum) from `top.log`.

Fake human: `--press "pickup:3,handoff:4"` presses the button 4 s after the display shows the matching prompt;
leaving an entry out means nobody presses it. Faults: `--stall "t0,len"` (seconds after the undock finished),
`--fail-after-pose N`, `--drift 0.02` (odometry error; the yaw bias applies only while the robot moves, since 2026-11-06,
because a real gyro does not tilt the whole map at rest), `--dock-fail-first N` (the first N `/dock` goals fail wherever the
robot is, to test the mission's retry; the `dock_retry` scenario uses 1), `--map-at-dock` (the map frame starts at the dock,
as in a SLAM map, so the logged AMCL error is taken in that frame; `run_mapping.sh` uses it). `--scan-when-docked`
publishes `/scan` while docked (the real lidar is off then; see below).

**AMCL error in the log (added 2026-11-06).** `ground_truth.jsonl` now holds, next to the true pose, AMCL's estimate and its
error: `est_x`, `est_y`, `est_err_x`, `est_err_y` (metres, along the wall is x). `analyse_run.py` turns them into
`amcl_error_m` in its output and in `results.json`. This is how the AMCL drift along a plain wall was found (Results below).

## Closed-loop mapping scenario (`run_mapping.sh`)

Everything above hands Nav2 a ready-made map. This scenario also tests the mapping: the fake robot maps the route
with the REAL slam_toolbox, the map is saved with the REAL `robot/save_map.sh`, `tools/plan_route.py` plans on that
SLAM map, and then the real delivery runs on it. Same isolation and guards as `run_e2e.sh` (domain 77, no domain 0,
process groups, `~/STOP`, refuses while a stack or mission runs). Dry run first, it starts nothing:

```bash
bash ~/robot_code/delivery/sim/run_mapping.sh --dry-run
bash ~/robot_code/delivery/sim/run_mapping.sh
```

Steps (all in the run folder `sim_<time>_mapping/`):

1. `fake_base.py` (with `--scan-when-docked`, like the lidar motor start of `start_stack.sh`) and slam_toolbox,
   started exactly as `start_stack.sh map` does: `ros2 launch turtlebot4_navigation slam.launch.py sync:=false`.
2. A python helper (`mapping_tools.py`, written into the run folder by the script) waits for `/map` and the
   `/slam_toolbox/save_map` service, undocks, and drives with `/wall_follow` goals of 10 s each (as the real controller
   does, R2). At the glass room opening (only when `SIM_GOAL_X` is beyond it) it cancels the goal and crosses with
   `/cmd_vel` at 0.2 m/s, as a person would, then wall-follows on. At the pickup X it turns round in place,
   wall-follows back to about 0.8 m from the dock and calls `/dock`.
3. `robot/save_map.sh run_folder/slam_map/map`, then slam and the mapping fake base are stopped. The saved map is
   checked: width and height plausible, enough occupied and free cells, and the south wall where the dock-origin frame
   says (a wrong frame or a broken map fails here). The mapping drive's ground truth must show no BUMP and no entry
   into the glass room.
4. The SLAM map frame starts at the robot's start pose, the dock. The hall's `route_spec.yaml` is therefore shifted by
   the dock pose (dock becomes (0, 0, 0)); keepout lines over the glass room opening and both glass doors are kept,
   because the lidar saw through them. `plan_route.py` plans on the SLAM map; `preview.html` is copied to the run folder.
5. A fresh `fake_base.py` with the same hall (ground truth, dock pose given with `--dock-pose`, so no offset is needed:
   the odometry starts at the dock, which is the origin of the SLAM frame), the stack and `delivery_mission.py` on the
   SLAM map, `analyse_run.py` as for `happy`.

The last line is `E2E mapping: PASS (<run folder>)` or `E2E mapping: FAIL`. Options: `--dry-run`, `--keep`; knobs
`SIM_GOAL_X` (default 25; with 25 the robot stops before the glass room, use 40 to exercise the opening crossing),
`SIM_DRIFT` (odometry error, as in `run_e2e.sh`), `SIM_MAP_ONLY=1` (stop after the map check, no delivery),
`SIM_SLAM_PARAMS` (another slam_toolbox yaml to compare settings; the default is `config/slam_delivery.yaml`, which is
also what `start_stack.sh map` uses),
`SIM_MAP_TIMEOUT` (900 s mapping drive), `SIM_SLAM_WAIT` (90 s for slam_toolbox to publish `/map`), plus the knobs of
`run_e2e.sh`. About 15 to 20 minutes.

**Map checks (changed 2026-11-06).** The check after the drive no longer looks only at the wall's y position. A SLAM frame
follows the robot's heading at the start, so a straight wall can be a little tilted. The check therefore fits a line to the
south wall and judges its straightness (80 % of columns within 0.15 m), its position at the dock (0.3 m) and its tilt (limit
5 degrees; 1.68 degrees was measured on a run with 2 % odometry error). The route spec is rotated by the measured tilt
(`make-spec --tilt-deg` in the helper). The new `along_wall_report` looks along the wall and reports the position of the end
wall, a ghost second end wall (a copy of the end wall a short distance inside it, a symptom of the map shrinking), and the
position of the glass room's west wall. The helper also moves the robot out to about 0.6 m from the wall before it crosses the
glass room opening (the straight drive from wall-follow distance touched the glass in `sim_20261106_083122_mapping`, with 2 %
odometry error). Two bugs fixed the same day: the helper lacked `rclpy.init()`, and the crossing on the way back reversed
instead of driving forward.

`/wall_follow` in `fake_base.py` is a simple follower on the ground truth (map plus glass): wall on the chosen side
(`follow_side` LEFT 1, RIGHT -1) about 0.30 m from the robot centre (0.13 m from its edge), 0.2 m/s, a wall ahead turns
the robot away from the wall, a missing wall (an opening) turns it in, so it WOULD go into the glass room through the
doorway; shallow glass-door recesses are crossed. It ends after `max_runtime` (feedback `engaged`, result `runtime`),
ignores `/cmd_vel` while it runs, and refuses while docked. `--stall` only silences `/odom` and `/tf`; the base keeps
driving. The real Create 3 follower is not modelled beyond this.

## Open points (not verified without the robot)

**Updated 2026-11-06.** What has now run, all on the robot's Pi with the robot on its dock (fake base, ROS domain 77):

- `run_e2e.sh` ran with the scenarios `stall` and `dock_retry` (and one `stall` run on 2026-11-05). `run_mapping.sh`, the `/wall_follow` action server and the helper's ROS part ran several times (25 m and 40 m halls). Bugs found by running them are fixed (see the Closed-loop mapping scenario). Results are below.
- The installed `slam.launch.py` runs without `/clock`. A saved SLAM map encodes unknown cells as 205 and free as 254 (trinary mode, `free_thresh` 0.25, `occupied_thresh` 0.65). `save_map.sh` works: both service calls returned `result=0`.
- The installed `slam.yaml` shrinks a long plain wall; `config/slam_delivery.yaml` fixes that in the simulator (Results).
- Regulated Pure Pursuit replaced MPPI on 2026-11-05 (MPPI missed its loop rate on the Pi).

Still **NOT VERIFIED** (needs the real robot, floor or lidar): the real lidar with glass and cables; the real Create 3 dock range (the fake base accepts `/dock` within 1.0 m, an assumption); the real size of the SLAM shrink on the real hall; the real Pi load (the fake base itself uses about half a core); how long a display message stays visible; the real wall-follow distance; the real odometry error.

*Original open points (2026-11-03 to 2026-11-05), kept for history:*

- `run_mapping.sh`, the `/wall_follow` action server and the helper's ROS part have never run (no ROS here). The pure
  wall follower, the shift of the spec, the map check and `plan_route.py` on a synthetic SLAM-like map are tested offline. *(Ran on 2026-11-06, see above.)*
- Whether the installed `slam.launch.py` and its yaml run without `/clock` (the robot's `slam.yaml` has no `use_sim_time`),
  and how the saved SLAM map encodes unknown cells (205 with `free_thresh 0.25` may load as free), are unknown until it runs. *(Answered 2026-11-06, see above.)*

- Nothing here has run on the robot yet. *(Superseded 2026-11-06: the simulator has run on the robot; the real base has not driven.)*
- While docked the real lidar is off and the fake one is too. If AMCL needs a scan before it publishes `map` to `odom`,
  Nav2 cannot become active until the robot has undocked, and `run_e2e.sh` prints a warning after `SIM_ACTIVE_WAIT`
  and goes on; the mission then fails with "Nav2 ... not active". That would be the same on the real robot. To see the
  rest of the run anyway, start `fake_base.py` with `--scan-when-docked` (edit the `FAKE_ARGS` line).
- The real base keeps driving during an `/odom` pause; the fake one does too (it keeps its last command), but real
  pauses may also delay `/dock_status` and `/battery_state`; the fake stall only stops `/odom` and `/tf`.
- MPPI behaviour on the real Pi depends on CPU; read `top.log` for the load. *(Superseded 2026-11-05: MPPI missed its loop rate on the Pi and was replaced by Regulated Pure Pursuit. The load is still worth reading from `top.log`.)*
- The installed `turtlebot4_navigation` yaml files set `use_sim_time: true`. The launch commands here are those of
  `robot/start_stack.sh`; if localization or Nav2 wait for `/clock`, that is the cause (see the facts sheet). *(2026-11-06: the project uses its own copies, `config/localization_delivery.yaml`, `config/nav2_delivery.yaml` and `config/slam_delivery.yaml`.)*

## Known differences from the real robot (added 2026-11-06, after the first real driving)

The real robot drove at home on 2026-11-06 (a small room, one robot, a few runs each; see [../README.md](../README.md), section 13). What differs from this simulator:

| Point | Simulator | Real robot (measured 2026-11-06) |
|---|---|---|
| Dock yaw and undock | Dock yaw 0; undock backs straight out | Docked, the robot faces the dock (yaw -32 on the dock, 147 after undocking in that room); undock backs about 0.13 m and turns about 180 degrees, 5.6 s. Not modelled, left as it is. The specs in `sim/` set `start` explicitly, so the planner fix (default `start` now opposite to the dock yaw) does not affect them |
| Wall-follow distance | The fake wall-follow keeps the centre about 0.30 m from the wall | One 8 s run: nearest return about 0.15 m from the lidar centre, so the edge almost touches the wall. One short run in one room |
| Dock range | `DOCK_RANGE` 1.0 m in `fake_base.py` (an assumption) | Docking worked from 0.13 to about 1.55 m when facing the dock or seeing it; it failed after 16 s from about 1 to 2 m when the dock was not seen; a closer second try (0.45 m) worked. So 1.0 m is on the safe side, not real data |

*Earlier text below is unchanged.*

## Results (2026-11-06)

All runs on the robot's Pi in ROS domain 77, robot on its dock, fake base. Run folders are on the robot under `~/robot_code/logs/delivery/`. Each row is one run, a small sample and not a guarantee. The real base has not driven any of this.

### Why the old `stall` run failed ("Dock failed", exit 3, `sim_20261105_022632_stall`)

Not the stall: the hold and resume worked. The chain of causes:

1. AMCL drifted along the wall. With `alpha1` to `alpha4` at 0.2 the estimate fell behind the truth by about 3.7 % of the distance driven when nothing in view fixes the position along the wall (only the end wall came into lidar range, at about 12 m). At the failure the true position was 0.53 m from the estimate and 1.23 m from the dock.
2. The fake base accepts `/dock` only within 1.0 m. That limit is an assumption; the real Create 3 range is NOT VERIFIED.
3. The retry drove to the hand-off pose, where the robot already believed it was. The leg succeeded at once with no motion, so the second dock failed the same way. This was a real mission bug, now fixed (`dock_retry_pose()`: the second try starts 0.45 m from the dock).

It was intermittent: the same scenario with no code change passed on the next run.

### AMCL results (25 m route)

| Run folder | Setting | Max error along wall | Median | True distance at `/dock` | Result |
|---|---|---|---|---|---|
| `sim_20261106_072408_stall` | alpha 0.2 | 1.38 m | 0.36 m | 0.82 m | PASS |
| `sim_20261106_073123_stall` | alpha 0.05 | 0.24 m | 0.14 m | 0.92 m | PASS |
| `sim_20261106_073736_stall` | alpha 0.05, 2 % odometry error | 0.27 m | 0.08 m | 0.95 m | PASS |
| `sim_20261106_074528_dock_retry` | alpha 0.05, first dock forced to fail | 0.60 m | 0.10 m | 0.98 m, then 0.72 m | PASS, the retry drove closer |

The side-to-side error stayed under 0.1 m in all of them. The robot stops 0.92 to 0.98 m from the dock because the hand-off pose is 0.7 m from the dock and `xy_goal_tolerance` is 0.25 m. That leaves little margin against the assumed 1.0 m dock range: measure the real range on the first real runs.

### SLAM results (`run_mapping.sh`, real slam_toolbox)

| Run folder | Setting | Result |
|---|---|---|
| `sim_20261106_075322_mapping` (25 m) | installed `slam.yaml` | Passed then, but the picture shows a ghost second end wall about 0.9 m from the first. Delivery on that map: PASS (AMCL max error 0.83 m). The check at the time looked only at the wall's y position, which is why it passed |
| `sim_20261106_081034_mapping` (40 m) | installed `slam.yaml` | Map shrunk by about 30 %: end wall at x -6.0 (true -1.5), glass room west wall at 13.7 (true 26.5). Map check FAIL |
| `sim_20261106_082310_mapping` (40 m) | `distance_variance_penalty` 0.05 | End wall -1.53, glass room 25.57 (about 3.4 % short), no ghost wall. Map check PASS |
| `sim_20261106_083122_mapping` | 2 % odometry error | BUMP at x 31.45: the straight drive across the glass room opening from wall-follow distance touched the glass front. The helper now moves out to about 0.6 m first |

Why: the match score is nearly flat along a plain wall, and with the installed 0.5 the penalty for a 0.25 m slip is only 2.5 %, so the scan matcher slides the robot back onto cells it already knows. The real hall has more features than this synthetic one, so the real size of the effect is NOT VERIFIED. People should still compare the saved map with a measured distance before planning (`../README.md`, section 6, step 7).

### Pi load in the simulator

CPU mean about 75 to 91 %, maximum 95 to 99 %, load average up to about 9.5. Part of that is `fake_base.py` itself (about 50 % of a core). The real load with the real base is NOT VERIFIED.

### Regression runs on the final code

| Run folder | What | Result |
|---|---|---|
| `sim_20261106_085440_mapping` | `run_mapping.sh`, 40 m through the glass room crossing, 2 % odometry error | PASS, 78.2 m driven. Map: tilt 0.7 degrees, end wall -1.85, room 26.05 (true 26.5). AMCL max error 0.61 m along the wall, 0.47 m across. First `/dock` failed at 1.12 m, the retry moved to 0.88 m and docked |
| `sim_20261106_091206_mapping` | `run_mapping.sh`, 25 m | FAIL, exit 2, false refusal: Nav2 fully active, but a `get_state` reply never arrived and the adapter never asked again. Fixed (`GET_STATE_TIMEOUT`, ask again after 3 s) |
| `sim_20261106_092013_happy` | `happy`, 60 m | PASS, 117.4 m in 846 s. AMCL max error 0.34 m. `/dock` at 0.91 m. CPU mean 92.6 %, maximum 100 %, load average up to 11.9 |
| `sim_20261106_093656_mapping` | `run_mapping.sh`, 25 m, rerun after the fix | PASS. Map: tilt 0.0, end wall -1.58. AMCL max error 0.35 m. `/dock` at 0.84 m |
| `sim_20261106_094811_stall` | `stall`, 25 m | PASS, hold and resume worked. AMCL max error 0.31 m. First `/dock` failed at 1.07 m, the retry moved to 0.79 m and docked: this is the old failure, now handled |
| `sim_20261106_120110_happy` | `happy`, 20 m, after the display fix | PASS. AMCL max error 0.19 m. `/dock` at 0.98 m |

Which code each run had: the two 40 m and 60 m runs and the failed 25 m run came before both late mission fixes (asking `get_state` again, `display_wire`); the 25 m rerun and `stall` had the first; only `happy` 20 m had both. `dock_retry` (earlier table) had neither. The SLAM and AMCL settings were the same in all of these.

The first `/dock` failed in two of these runs, because the robot stops close to the fake base's assumed 1.0 m limit. The retry handled both. Measure the real range before relying on this margin.

The soak test ran on the real base, not in this simulator: see [ROADMAP TB-29](../../ROADMAP.md#tb-29-campus-food-delivery-along-the-wall-supervised-demo).
