# Campus food delivery with the TurtleBot 4 (ROADMAP TB-29)

User guide for the lab's delivery project: map the route, plan it, test it with no motion, then run supervised deliveries. Task record: [ROADMAP.md, TB-29](../ROADMAP.md#tb-29-campus-food-delivery-along-the-wall-supervised-demo).

**Status (2026-11-06): tested offline and in the simulator on the robot's Pi, with the robot on its dock. The real base has not driven any of this.** The simulator (`sim/`) replaces the base and the lidar with a fake base in ROS domain 77, so the real Nav2, AMCL, slam_toolbox and `delivery_mission.py` ran on the Pi without moving the robot. Everything that needs the real floor, lidar or Create 3 is still a plan, marked **[to verify]** or **NOT VERIFIED**. Record every real run and every change in [MAINTENANCE.md](../MAINTENANCE.md). Results of the simulator runs are in [sim/README.md](sim/README.md#results-2026-11-06).

**Update 2026-11-06 (later the same day): the real robot has driven.** At home, over Wi-Fi with the Ethernet cable out, in a room of about 2.5 x 1.8 m with a corridor, the real base docked and undocked, Nav2 delivered food on a 1.1 m route (full delivery from the menu, exit 0), and a front-panel menu with the delivery as its first entry was installed. **The robot has NOT been to campus.** Results are in sections 9, 11 and 13 and in the new subsection "The front-panel menu" (end of section 9). The statement above about the simulator is kept as history.

*Earlier status (2026-11-03, superseded 2026-11-06): tested offline only. Nothing in this folder had run on the robot.*

Contents: 1 What this is, 2 Safety first, 3 Files, 4 Connecting and copying, 5 Phase 0, 6 Phase 1 (mapping), 7 Clean the map, 8 Plan the route, 9 Phase 2 (supervised runs), 10 Phase 3 (demo), 11 Tuning, 12 Offline tests, 13 Not verified yet, 14 How the checks fit together.

Each command is marked **on your computer** or **on the robot** (in a terminal where you logged in with ssh, see section 4).

---

## 1. What this is

**Goal.** The robot carries food from the campus food court to the AlfaisalX lab, staying close to the wall. The route is on one floor, about 50 to 100 m (estimate), straight, in open space along walls. It passes glass doors and a glass room that opens off the wall; the robot must pass straight by the glass room and not enter it. Ramps or cables may lie on the floor. The target is a **supervised demo**: a person walks behind the robot with the TurtleBot 4 controller. No money and no new hardware.

**How it works, in order.**

1. **Map.** The robot drives along the wall (Create 3 wall-follow from the controller, or by hand) while slam_toolbox builds a map. You clean the map on your computer.
2. **Plan the lane.** `tools/plan_route.py` finds a path about 0.5 m from the wall on the saved map and writes waypoints plus two mask images.
3. **Nav2 with three helpers.** Nav2 localizes with AMCL and drives the waypoints (Regulated Pure Pursuit controller at 10 Hz, speed cap 0.20 m/s). The whole stack is one process, `launch/delivery_stack.launch.py` (section 3 says why). *Earlier versions used the MPPI controller; replaced 2026-11-05 because on the Pi it missed its loop rate all the time and kept the CPU at 100 % in the simulator.* The keepout mask gives a soft preferred lane (cheap in the lane, dearer outside) and lethal lines across the glass room opening and in front of glass doors. The speed mask slows the robot in slow zones (ramps, cables).
4. **Hand-off with the front-panel buttons.** At the food court the display asks for button 3 ("food placed", pressed by the vendor; button 1 also works since 2026-11-06). Back at the lab it asks for button 4 ("received", pressed by the student; button 1 also works). Then the robot docks.
5. **Start from the front-panel menu (since 2026-11-06).** The first entry of the robot's menu is `Go to food court` (when docked) or `Back to the lab` (when not docked). Select it with button 1 and answer `1 = Yes`. People no longer need a terminal to start a delivery once the navigation stack is running. See "The front-panel menu" at the end of section 9.

**Phases.**

| Phase | What | Robot moves? |
|---|---|---|
| 0 | Read-only checks, a soak test with the delivery stack running on the dock (the earlier plan had SLAM running too, see section 5 B), walking the route | No |
| 1 | Map the route by wall-following, clean the map, plan the route | Yes (mapping drive) |
| 2 | Supervised Nav2 runs, round trips, logged | Yes |
| 3 | Demo with a vendor and a student | Yes |

---

## 2. Safety first

- **Supervised only.** A person walks behind the robot, holding the TurtleBot 4 controller, for every run that moves it. Never leave it alone.
- **Emergency stop, first layer:** controller button **B** toggles the Create 3 emergency stop (press B again to clear it). **[to verify on this robot]** Test it in Phase 1 with the robot off the dock and you next to it, before relying on it.
- **Second layer:** the **E-STOP** in [TurtleBot Studio](../tools/studio/README.md). Note TB-25 below: do not connect Studio during a run just to get this; connect it before, or leave it closed and use the controller.
- **Stop file:** `touch ~/STOP` on the robot stops `delivery_mission.py` (Nav2 goal cancelled, base stopped). Delete the file afterwards with `rm ~/STOP`; the mission refuses to start while it exists.
- **Speed cap:** 0.20 m/s (Nav2 velocity smoother limits and the controller's `desired_linear_vel` in `config/nav2_delivery.yaml`), gentle acceleration (0.3 m/s^2) so food does not spill. The robot's own maximum is about 0.31 m/s.
- **Outside lunch hours.** The route is very crowded at lunch; crowds are not handled in this prototype.
- **Front-panel buttons (changed 2026-11-06).** *Replaced rule:* until 2026-11-06 this guide said "Never press front-panel buttons 1 or 2", because on the stock menu button 1 (Select) runs the highlighted entry (for example Undock) and button 2 is Back. *What changed:* the robot now runs the delivery menu (section 9, "The front-panel menu"). Its first entry starts a delivery, and every trip and `Power` ask `1 = Yes / 2 = No` first. **Button 2 is Stop while the robot is moving**, so it is now the button to press, not to avoid. Buttons 1 (Select), 3 (Up) and 4 (Down) work as written in the menu table. If you uninstall the menu (`install_menu.sh --uninstall`), the stock menu comes back and the old rule applies again: buttons 1 and 2 would run stock entries such as Undock, Dock and Power. The menu was tested on the real robot with simulated presses; a press of the PHYSICAL buttons on the new menu is **NOT yet confirmed**. Keep a person next to the robot and the controller button B ready for the first physical presses.
- **TB-25 (base stalls).** Every new ROS participant (each `ros2` command, each Studio connection) can stall the Create 3 base topics for several seconds. Start the navigation stack **once**, then run no other `ros2` commands and make no Studio reconnects during a run. The mission waits by itself for a steady `/odom` before it moves.
- **Glass and cables are invisible to the lidar.** The map edits, keepout lines and slow zones help; the person behind the robot is the backstop. Black cables may also trigger the cliff sensors.
- **Secrets.** The robot password is in the repo's README; for anything else secret, ask the lab maintainer.

---

## 3. Files

All paths are relative to this folder (`TurtleBot/delivery/`).

**Which programs move the robot:** `delivery_mission.py` (a whole trip), `delivery_menu.py` (it starts trips and runs Dock, Undock, EStop and Wall Follow), `robot/motion_probe.py` (single supervised steps) and `robot/press_buttons.py` (only when it presses button 1 on a menu entry that moves). The simulator in `sim/` moves only a fake base. Everything else reads, plans, copies or starts and stops the navigation stack.

| File | What it is |
|---|---|
| [delivery_mission.py](delivery_mission.py) | The mission program, **runs on the robot, moves it.** Undock, drive the route with Nav2, wait for button 3, drive home, wait for button 4, dock. Has `--dry-run`. |
| [delivery_core.py](delivery_core.py) | Pure logic with no ROS: route file reader, odometry watch, button edges, display text, the mission state machine. Tested offline with a fake robot. |
| [route.example.yaml](route.example.yaml) | Example of the `route.yaml` format (made-up coordinates). |
| [tools/plan_route.py](tools/plan_route.py) | **On your computer.** Plans the route and writes the route, masks and a preview on a saved map. Standard library plus PyYAML. Moves nothing. |
| [tools/route_spec.example.yaml](tools/route_spec.example.yaml) | Example of the spec file you give `plan_route.py` (dock, goal, keepout lines, slow zones). |
| [config/nav2_delivery.yaml](config/nav2_delivery.yaml) | Nav2 parameters for delivery: upstream TurtleBot 4 Jazzy file with changes marked `# delivery:` (Regulated Pure Pursuit controller, speed caps, lower inflation, filters, BT timeouts). |
| [config/localization_delivery.yaml](config/localization_delivery.yaml) | AMCL parameters: the installed file with `use_sim_time` set to false (the installed file says true), AMCL `alpha1` to `alpha4` 0.05 and 800 particles. [tools/make_localization_params.py](tools/make_localization_params.py) adds the route's dock pose as the initial pose. |
| [config/slam_delivery.yaml](config/slam_delivery.yaml) | slam_toolbox parameters for mapping: a copy of the installed `slam.yaml` with one change, `distance_variance_penalty` 0.5 to 0.05 (stops the map shrinking along a long plain wall, see section 6). Used by `start_stack.sh map`. |
| [config/delivery_through_poses_bt.xml](config/delivery_through_poses_bt.xml) | The behaviour tree for driving the waypoint list. |
| [config/upstream/turtlebot4_nav2_jazzy.yaml](config/upstream/turtlebot4_nav2_jazzy.yaml) | Unchanged upstream copy, for comparison. |
| [launch/delivery_stack.launch.py](launch/delivery_stack.launch.py) | Starts the whole navigation stack in **one process**: map server, AMCL, the two mask servers and two filter-info servers, and the Nav2 servers, under one lifecycle manager with `bond_timeout` 0 (no bond watchdog since 2026-11-06; it was 20 s, see section 11). *Earlier versions started the stock `localization.launch.py`, a separate `delivery_filters.launch.py` and the stock `nav2.launch.py`; replaced 2026-11-05.* Why: the stock launch files start about 15 processes on the Pi, the load average reached 14, one server missed its 4 s heartbeat and Nav2 shut itself down; and every process is a new ROS participant, which can stall the base (TB-25). One process is one participant. It leaves out servers a delivery does not use (docking server, waypoint follower, smoother server). |
| [robot/start_stack.sh](robot/start_stack.sh) | **On the robot.** `map` mode starts slam_toolbox with `config/slam_delivery.yaml`; `nav` mode writes the AMCL file with the dock pose and starts `delivery_stack.launch.py`, detached, with logs. |
| [robot/stop_stack.sh](robot/stop_stack.sh) | **On the robot.** Stops what `start_stack.sh` started (SIGINT, no sudo, no SIGKILL). |
| [robot/save_map.sh](robot/save_map.sh) | **On the robot.** Saves the slam_toolbox map (.pgm and .yaml) and its pose graph. |
| [menu_core.py](menu_core.py) | Pure logic of the front-panel menu with no ROS: the entries, the button rules, the screen texts. Tested offline. Does not move anything. *Added 2026-11-06.* |
| [delivery_menu.py](delivery_menu.py) | **On the robot, moves it.** The front-panel menu program (ROS). Draws the menu on the display, reads the buttons, and runs the entries: it starts `delivery_mission.py` for a trip, and runs Dock, Undock, EStop and Wall Follow itself. Runs as the `delivery-menu` service. *Added 2026-11-06.* |
| [ros_buttons.py](ros_buttons.py) | Reads `/hmi/buttons` by polling every 0.1 s, instead of waking up about 95 times a second. Used by the menu and by the mission. Moves nothing. *Added 2026-11-06.* |
| [robot/delivery-menu.service](robot/delivery-menu.service) | The systemd user service file that starts `delivery_menu.py` at boot (no sudo). *Added 2026-11-06.* |
| [robot/install_menu.sh](robot/install_menu.sh) | **On the robot.** Installs, checks (`--status`) or removes (`--uninstall`) the menu service; `--dry-run` prints the commands and changes nothing. Moves nothing itself. *Added 2026-11-06.* |
| [robot/press_buttons.py](robot/press_buttons.py) | **On the robot.** Test tool: presses the front-panel buttons from software and prints what the screen shows. Button 1 can start a trip, so it can make the robot move: use it only with a person next to the robot. *Added 2026-11-06.* |
| [robot/motion_probe.py](robot/motion_probe.py) | **On the robot, MOVES it.** Short supervised motion steps (status, scan, undock, dock, drive, turn, wall follow, face the dock) in one program; every step is a built-in Create 3 action. A person stays next to the robot. Log: `~/robot_code/logs/delivery/motion/`. *Added 2026-11-06.* |
| [phase0/p0_checks.sh](phase0/p0_checks.sh) | **On the robot.** Read-only checks A1 to A9 of Phase 0, writes a report. |
| [phase0/p0_soak.sh](phase0/p0_soak.sh) | **On the robot.** Soak test with the delivery stack running on the dock on a synthetic route, no goals, no motion. Needs the lab maintainer's OK and a person next to the robot. |
| [tools/deploy.py](tools/deploy.py) | **On your computer.** Copies this folder to the robot as a numbered release with checks, and can roll back (section 4). Standard library only; uses your `ssh` and `scp`. |
| [tools/verify_all.py](tools/verify_all.py) | **On your computer.** One command that runs the linters (when installed), syntax checks, the link check and all offline tests, and prints a PASS, FAIL or SKIP table (section 14). |
| [tools/make_localization_params.py](tools/make_localization_params.py) | Writes the AMCL parameter file for one route with the route's dock pose as the initial pose. Called by `start_stack.sh nav` and by `sim/run_e2e.sh`. |
| [sim/](sim/README.md) | The simulator: runs the real Nav2, AMCL, slam_toolbox and `delivery_mission.py` on the robot's Pi against a fake base, with the robot on its dock. `run_e2e.sh` (scenarios `happy`, `pickup_timeout`, `stall`, `nav_fail`, `dock_retry`), `run_mapping.sh` (map with slam_toolbox, then deliver on that map), `fake_base.py`, `sim_map.py`, `analyse_run.py`, `ci_check_params.py`. Cannot move the real base. |
| [../tests/offline/test_delivery_mission.py](../tests/offline/test_delivery_mission.py) | Offline test: route file, odometry watch, buttons, display text, state machine with a virtual clock. |
| [../tests/offline/test_plan_route.py](../tests/offline/test_plan_route.py) | Offline test: planner on synthetic maps (wall distance, keepouts, masks, preview). |
| [../tests/offline/test_delivery_config.py](../tests/offline/test_delivery_config.py) | Offline test: Nav2 config differs from upstream only in the intended keys, launch file, and every shell script (`bash -n` and `--dry-run` with fakes). |
| [../tests/offline/test_delivery_sim.py](../tests/offline/test_delivery_sim.py) | Offline test of the simulator's pure parts (wall follower, map checks, run analysis). No ROS. |
| [../tests/offline/test_delivery_deploy.py](../tests/offline/test_delivery_deploy.py) | Offline test of `tools/deploy.py` (packing, manifest, command sequence). |

---

## 4. Connecting and copying the folder to the robot

### Connecting (ssh)

Full details and troubleshooting: [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md).

**1. Open a terminal on your computer.**

| System | How |
|---|---|
| Windows 10 or 11 | Start menu, type `PowerShell`, Enter. If `ssh` is not recognized, add **OpenSSH Client** under Optional features in Windows Settings. |
| macOS | Cmd+Space, type `Terminal`, Enter. |
| Linux | Ctrl+Alt+T, or open Terminal from the applications menu. |

**2. The key.** The lab key is `turtlebot4_ed25519` in your `.ssh` folder (create it once as described in [HOW-TO-CONNECT.md, key login](../HOW-TO-CONNECT.md#recommended-log-in-with-a-key-instead-of-a-password)).

| System | Key path |
|---|---|
| Windows (PowerShell) | `$env:USERPROFILE\.ssh\turtlebot4_ed25519` |
| macOS and Linux | `~/.ssh/turtlebot4_ed25519` |

Without the key, leave out `-i ...` and type the robot password `turtlebot4` when asked.

**3. The address.** Prefer the Ethernet cable for Phases 0 and 1: it does not drop like the campus Wi-Fi.

| How you connect | Address in the command |
|---|---|
| Ethernet cable, no setup ([Option A](../HOW-TO-CONNECT.md#option-a-ipv6-link-local-address-no-settings-change-verified-2026-10-24)) | `ubuntu@fe80::da3a:ddff:fe41:d5df%<interface>`, in quotes. `<interface>` is your Ethernet adapter: its number on Windows (from `Get-NetAdapter`, for example `%8`), its name on macOS or Linux (for example `%en5` or `%eth0`) |
| Ethernet cable, fixed address ([Option B](../HOW-TO-CONNECT.md#option-b-give-your-computer-a-fixed-address-on-the-cable-recommended-for-regular-use)) | `ubuntu@192.168.185.3` |
| Campus Wi-Fi `Students` | `ubuntu@` plus the address on the robot's display (starts with `10.87.`; it can change) |
| Name lookup | `ubuntu@turtlebot4.local` |

**4. Log in (on your computer).** Windows:

```powershell
ssh -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 "ubuntu@fe80::da3a:ddff:fe41:d5df%8"
```

macOS and Linux:

```bash
ssh -i ~/.ssh/turtlebot4_ed25519 "ubuntu@fe80::da3a:ddff:fe41:d5df%eth0"
```

Over Wi-Fi or with a fixed address, replace the quoted part, for example `ubuntu@turtlebot4.local` or `ubuntu@192.168.185.3`. The prompt changes to `ubuntu@turtlebot4:~$`. Commands marked **on the robot** are typed there. Commands marked **on your computer** are typed in a second terminal on your computer, from the repo's `TurtleBot` folder. The macOS and Linux forms of the `fe80::` login were not run against this robot [to verify].

### Copy the folder to the robot with `tools/deploy.py` (recommended since 2026-11-05)

`tools/deploy.py` runs on your computer (Python 3.10 or newer, standard library only; it uses your `ssh` and `scp`). It never uses sudo and never touches `~/robot_code/routes` or `~/robot_code/logs` on the robot. Its default key is `~/.ssh/turtlebot4_ed25519` and its default address is the Ethernet link-local address in section 4 (`ubuntu@fe80::da3a:ddff:fe41:d5df%8`, where `8` is the interface number on the author's Windows computer, so give your own with `--host`). Use `--key` for another key. **On your computer**, from the repo root (use `python3` on macOS and Linux):

```bash
python TurtleBot/delivery/tools/deploy.py deploy --dry-run --host "ubuntu@fe80::da3a:ddff:fe41:d5df%8"    # shows every step and remote command, changes nothing
python TurtleBot/delivery/tools/deploy.py deploy --host "ubuntu@fe80::da3a:ddff:fe41:d5df%8"              # deploys
python TurtleBot/delivery/tools/deploy.py status --host "ubuntu@fe80::da3a:ddff:fe41:d5df%8"              # which release is live; does it match its manifest
python TurtleBot/delivery/tools/deploy.py rollback --host "ubuntu@fe80::da3a:ddff:fe41:d5df%8"            # back to the previous release
```

Replace the quoted address as in the table above (for example `ubuntu@turtlebot4.local`). `deploy` does this, in order, and stops at the first failure:

1. Packs `TurtleBot/delivery` (without `__pycache__`, `*.pyc` and `docs`; `config/upstream` is kept) plus the timing tools `record_timing.py` and `analyze_timing.py`, with `MANIFEST.sha256` (a checksum of every file) and `VERSION` (git commit, dirty flag, UTC time).
2. Refuses while a mission runs on the robot (`--force` overrides).
3. Uploads and unpacks to `~/robot_code/delivery-releases/<UTC time>-<git commit>`.
4. Checks every file against the manifest on the robot, then `bash -n` on every `.sh` and `python3 -m py_compile` on every `.py`.
5. Only then switches the symlink `~/robot_code/delivery` to the new release (atomic). If step 3 or 4 fails, the new release is removed and the live one is untouched.
6. Keeps the newest 5 releases; the live one is never removed.

So `~/robot_code/delivery` is a symlink to a numbered release, and the timing recorder is at `~/robot_code/delivery/robot_tools/record_timing.py`. The commands in this guide that say `~/robot_code/delivery/...` work unchanged. Exit codes: 0 ok, 1 failure, 2 refused. The tool's own tests ran offline with fake `ssh` and `scp` (`tests/offline/test_delivery_deploy.py`); the tool also deployed to the real robot over the cable several times on 2026-11-06, with every file matching the manifest.

### Copy the folder by hand (manual alternative, the earlier method)

*Before `deploy.py` existed this was the only way. It still works but gives no checks, no release history and no rollback. Do not mix it with `deploy.py`: `scp -r delivery ...` into a folder that is already a symlink would write into the live release.*

Wi-Fi drops (TB-10) can end a long job, so copy with `scp`, not by piping through `ssh`. In Windows PowerShell 5.1 the `>` operator re-encodes files, which corrupts scripts; `scp` does not.

**On your computer**, from the repo's `TurtleBot` folder. `scp` needs square brackets around an IPv6 address. Windows:

```powershell
scp -r -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 delivery "ubuntu@[fe80::da3a:ddff:fe41:d5df%8]:~/robot_code/"
```

macOS and Linux:

```bash
scp -r -i ~/.ssh/turtlebot4_ed25519 delivery "ubuntu@[fe80::da3a:ddff:fe41:d5df%eth0]:~/robot_code/"
```

With another address use `ubuntu@turtlebot4.local:~/robot_code/` (no brackets). Result on the robot: `~/robot_code/delivery`. If `~/robot_code` does not exist, create it first with `mkdir -p ~/robot_code` on the robot. Copy again after every change on your computer; the old folder is replaced file by file.

For the soak test (section 5) with a hand copy, also copy the timing recorder to `/tmp` (on your computer; Windows shown, change the key path and address as above). After `deploy.py` this is not needed, because the recorder is already on the robot:

```powershell
scp -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 tools/timing/record_timing.py "ubuntu@[fe80::da3a:ddff:fe41:d5df%8]:/tmp/"
```

No other setup is needed on the robot: run the scripts as `bash ~/robot_code/delivery/robot/start_stack.sh ...`. The repo stores them with LF line endings and `scp` does not change them.

---

## 5. Phase 0: no motion

Do this before any motion for this project. The robot stays on the dock. Stop and ask the lab maintainer if a check fails (the **Stop if** rules are below).

### A. Read-only checks

**On the robot:**

```bash
bash ~/robot_code/delivery/phase0/p0_checks.sh --dry-run        # prints the commands, runs nothing
bash ~/robot_code/delivery/phase0/p0_checks.sh                  # the real checks
bash ~/robot_code/delivery/phase0/p0_checks.sh --interactive    # adds the button check A7 and the controller check A8
```

- It changes nothing, publishes nothing and uses no sudo. The `ros2` commands run one at a time with a timeout and a 10 s pause between them (TB-25), so expect 5 to 10 minutes.
- `--interactive`: when asked, press front-panel **button 3** and **button 4** once each (**never 1 or 2**), and move a stick of the controller (turn it on first).
- The report is `~/robot_code/logs/delivery/p0_checks_<date-time>.txt`. Verdicts: PASS, CHECK (look at it yourself), FAIL (a stop condition), SKIP. Exit code 1 if any check FAILs.
- What it covers: base health (`/dock_status`, battery, base log), clock, network/CPU/temperature/disk, lidar rate, installed packages (slam_toolbox, nav2_bringup, turtlebot4_navigation, `ros2 bag`), the robot's own `turtlebot4.yaml` button settings, buttons and display, the controller, and optional internet over HTTPS.
- Stop if: `/dock_status` or `/battery_state` prints nothing within 60 s, the base log stops at a "Configuring" line, the clock differs from the base stamp by more than a minute, or a required package is missing.
- The button check matters: the plan relies on buttons 3 and 4 only scrolling the menu. The upstream file says so; this robot's copy has not been read yet **[to verify]**.

### B. Soak test (about 80 minutes, mostly waiting)

*Earlier plan (2026-11-03, replaced 2026-11-05): the soak started `slam.launch.py` and then the stock `nav2.launch.py` (about 15 ROS programs) and took about 1 h 45 min. It was replaced because the stock launch files overload the Pi (load average 14 in the simulator, Nav2 shut itself down), so they are not what a delivery runs. The soak now tests the stack a delivery really uses.*

Purpose: find out whether the base stays steady with the delivery stack running (TB-25), and whether the Pi has enough CPU. The script starts `launch/delivery_stack.launch.py` on a synthetic route (made with `sim/sim_map.py` and `tools/plan_route.py`) with the robot on the dock and **no goals sent**, so nothing should move. **Needs the lab maintainer's OK and a person next to the robot.** If the robot moves anyway, press the E-STOP or lift it off the floor. Decide first whether Studio stays connected for the whole test or stays closed; do not connect it during the test. Run no `ros2` commands during the test.

The timing recorder is needed. After `tools/deploy.py` it is on the robot at `~/robot_code/delivery/robot_tools/record_timing.py`, and you pass it with `--recorder`. With a hand copy (section 4) it is in `/tmp/record_timing.py`. **On the robot** (log in as in the Connecting part of section 4: key `~/.ssh/turtlebot4_ed25519`, the robot's address, a terminal on your computer), start the script detached so a dropped ssh session does not end it:

```bash
bash ~/robot_code/delivery/phase0/p0_soak.sh --recorder ~/robot_code/delivery/robot_tools/record_timing.py --dry-run    # prints the timeline, starts nothing
setsid nohup bash ~/robot_code/delivery/phase0/p0_soak.sh --recorder ~/robot_code/delivery/robot_tools/record_timing.py --baseline 1 --soak 5 > ~/p0_soak_console.log 2>&1 < /dev/null &    # short trial, about 12 min
setsid nohup bash ~/robot_code/delivery/phase0/p0_soak.sh --recorder ~/robot_code/delivery/robot_tools/record_timing.py > ~/p0_soak_console.log 2>&1 < /dev/null &                          # full test: 3 min baseline, 70 min soak
```

Run one of the two real lines, not both. Timeline of the full test: dock check (refuses unless the robot is docked), lidar motor on, 60 s wait (about 1 min), recorder on, 3 min quiet baseline, `delivery_stack.launch.py` starts, CPU snapshots 20 and 50 min after the start (and one just before the stop), stop the stack after 70 min, 20 s, 5 min of tail recording. That is about 3 + 70 + 5 + 1 = 79 min, so plan 80 min. Output: `~/robot_code/logs/delivery/p0_soak_<date-time>/` with `p0_soak.jsonl`, `summary.txt`, logs and `top.txt`.

**Status:** the full soak on the final code has not been reported here yet. The result will be added to the Results section of [sim/README.md](sim/README.md#results-2026-11-06), [ROADMAP.md](../ROADMAP.md) (TB-29) and [MAINTENANCE.md](../MAINTENANCE.md).

**Stopping early.** The script then stops the Nav2 and SLAM it started. Any one of:

- `touch ~/STOP` on the robot (checked during every wait; delete it afterwards with `rm ~/STOP`)
- `kill <pid>` of the `p0_soak.sh` process (SIGTERM). Find the pid with `pgrep -f p0_soak.sh`.
- Ctrl+C, only if you started it in the foreground

**Fetch and analyse (on your computer**, from the `TurtleBot` folder; Windows key path shown):

```powershell
scp -r -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 "ubuntu@[fe80::da3a:ddff:fe41:d5df%8]:~/robot_code/logs/delivery/p0_soak_<date-time>" .
python tools/timing/analyze_timing.py p0_soak_<date-time>/p0_soak.jsonl --csv p0_gaps.csv --html p0_timeline.html
```

Use `python3` on macOS and Linux. After `deploy.py` the analyser is also on the robot at `~/robot_code/delivery/robot_tools/analyze_timing.py`. Open `p0_timeline.html` in a browser. How to read the report: [tools/timing/README.md](../tools/timing/README.md).

**Pass rule.** No `/odom` gap over 0.3 s from 10 minutes after the stack starts until the stop. (Earlier wording: "after the Nav2 start"; the stack start is the same moment now that Nav2 is part of the one launch.)

| Measure | Pass | What to do otherwise |
|---|---|---|
| Longest `/odom` gap in the baseline | Under 0.3 s | Base not quiet: stop and ask the lab maintainer |
| Start-up stalls after the stack starts | Recorded; note the longest and when they end | Becomes the start-up wait |
| `/odom` gaps over 0.3 s from 10 min after the stack starts | **None** | Stalls after start-up: do not go on; options are fewer running nodes or a different DDS setup (ROADMAP TB-09, TB-25) |
| Load average and temperature with the stack | Load under 4, temperature under 80 degrees C (limits from the Phase 0 plan) | Turn off the OAK-D during navigation, or run navigation on a laptop |

### C. Walk the route (no robot)

At a quiet time, walk from the lab dock to the pickup spot along the wall the robot will follow. Take photos. A tape measure, a phone measuring app or counting paces (about 0.75 m each) are fine. Note:

| Item | What to note |
|---|---|
| Total length | Metres, dock to pickup spot |
| Wall side | Left or right on the way out; is the wall continuous? |
| Pickup spot | Where the vendor meets the robot; free floor about 1 m around |
| Glass doors | How many, metres from the start, open or closed in the daytime |
| Glass room | Start and end (metres), width of its opening |
| Other glass or mirrors | Where |
| Ramps | Where, length, rise, any lip |
| Cables | Where, fixed or loose, colour (black matters for the cliff sensors), cable cover or not |
| Ledges and overhangs | Anything between about 12 and 40 cm high (benches, shelves, pipes) that the robot's tower can hit |
| Dark floor patches | Black mats or dark tiles (cliff sensors) |
| Narrow spots | Anything under about 1 m wide |
| Quiet times | For the Phase 1 and 2 runs |

These notes become the keepout lines and slow zones in section 8.

---

## 6. Phase 1: map the route by wall-following

> **BEFORE CAMPUS (added 2026-11-06).** The menu and the mission read the route from the folder `~/robot_code/routes/current`, which is a link. Today it points to the home test route `home`. Once the campus route is on the robot (section 8, step 6, folder `route1`), point the link at it. **On the robot** (log in as in section 4: open a terminal on your computer, then `ssh -i ~/.ssh/turtlebot4_ed25519 ubuntu@turtlebot4.local`, or use the address on the robot's display; on Windows the key is `$env:USERPROFILE\.ssh\turtlebot4_ed25519`):
>
> ```bash
> ln -sfn route1 ~/robot_code/routes/current
> ls -l ~/robot_code/routes/current
> ```
>
> The second command must show `current -> route1`. Without a `route.yaml` in the folder the menu shows `No route saved`. The environment variable `DELIVERY_ROUTE_DIR` overrides the link. To go back to the home test route: `ln -sfn home ~/robot_code/routes/current`. Mapping itself (below) does not need the link; the first delivery from the menu does.

Do this at a quiet hour with a person walking behind the robot, controller in hand. Charge the controller first. Prefer the Ethernet cable if the route allows it; otherwise use the Wi-Fi address and keep long jobs detached. Mapping here needs only the TurtleBot's own controller; no new ROS program is needed for the drive, which suits TB-25.

1. **Start mapping, on the robot:**

   ```bash
   bash ~/robot_code/delivery/robot/start_stack.sh map --dry-run     # check what it will run
   bash ~/robot_code/delivery/robot/start_stack.sh map
   ```

   This starts `slam.launch.py` (`sync:=false`) detached with `params:=config/slam_delivery.yaml` (since 2026-11-06; *earlier it used the installed `slam.yaml`, which shrank a long plain wall in the simulator, see below*); logs go to `~/robot_code/logs/delivery/<date-time>/`. Nav2 is not started. Add `--with-nav2` only if you want it for a test (it then uses the upstream parameters, since the delivery masks do not exist yet). Wait until `/odom` is steady, then do the TB-25 rule: no other `ros2` commands until you save the map.
2. **Undock** with the controller (Home button held for 3 s toggles Dock/Undock) or in Studio. Check the robot is clear of the dock. **[to verify]** Remember: on the stock menu front-panel button 1 runs a menu entry; with the delivery menu installed (section 9) it starts a trip only after `1 = Yes`. Use the controller for this step.
3. **Follow the wall with the controller.** **R2 = Wall Follow Right, L2 = Wall Follow Left.** According to the `turtlebot4_node` source, each press of R2 or L2 runs the Create 3 wall-follow for **only 10 seconds**, so press it again about every 10 s while you walk behind. This needs no new ROS program. **[to verify on this robot]**
   - Alternative with fewer presses (but every command is a new ROS participant, TB-25, so expect a short base pause when you send it). **On the robot:**

     ```bash
     ros2 action send_goal /wall_follow irobot_create_msgs/action/WallFollow "{follow_side: -1, max_runtime: {sec: 60}}"
     ```

     `follow_side: 1` is the left wall, `-1` the right wall. Ctrl+C cancels it. **[to verify]**

   *Updated 2026-11-06, real robot.* One 8 s run of the Create 3 wall-follow action (`/wall_follow`) in a small room: the nearest lidar return ended **about 0.15 m from the lidar centre**, so the robot's edge is almost touching the wall, and it moved 0.75 m in the 8 s. This is one short run in one room; the distance on the campus wall, with glass and with a long run, is **NOT VERIFIED**. The simulator's fake wall-follow keeps the robot centre about 0.30 m from the wall (about 0.13 m from its edge); that was an assumption and is **wrong for the real robot (0.15 m measured)**. Plan the "move out before crossing" step below with this in mind: the real robot is closer to the wall than the simulator showed.
   - *Earlier text, replaced 2026-11-06:* "How close wall-follow keeps the robot to the wall is NOT VERIFIED on the real Create 3. In the simulator the fake wall-follow keeps the robot centre about 0.30 m from the wall."
   - Wall follow is also a menu entry (`Wall Follow Left` and `Wall Follow Right`, tested with a simulated press for Left only).
4. **Glass room and glass doors.** The lidar does not see glass, so wall-follow may turn into the glass room or hit a door. Press **B** (emergency stop) before it does, press **B** again to clear it, drive across the opening with the controller sticks or in Studio, then press R2 (or L2) again. Whether wall-follow copes with the glass at all is **not yet tested** on this robot.
   - **Move out before crossing.** Wall-follow leaves the robot very close to the wall. In the simulator, with 2 % odometry error, a straight drive across the glass room opening from that position touched the glass front (run `sim_20261106_083122_mapping`). The simulator's helper now moves out to about 0.6 m first. Do the same by hand: **before you cross an opening or pass glass, steer out to at least 0.6 m from the wall, cross, then return to the wall** and press R2 (or L2) again.
5. **Close the loop.** Drive back along the same wall to the dock, so slam_toolbox sees the start again.
6. **Save the map, on the robot** (one `ros2` command after another with a timeout each; it will not overwrite an existing map without `--force`):

   ```bash
   bash ~/robot_code/delivery/robot/save_map.sh --dry-run ~/robot_code/maps/route1
   bash ~/robot_code/delivery/robot/save_map.sh ~/robot_code/maps/route1
   ```

   Writes `route1.pgm`, `route1.yaml`, `route1.posegraph` and `route1.data`. *Verified 2026-11-06 in the simulator on the robot's Pi, with the real slam_toolbox:* both service calls, `/slam_toolbox/save_map` with `{name: {data: ...}}` and `/slam_toolbox/serialize_map` with `{filename: ...}`, returned `result=0` and wrote all four files (`.posegraph` 13 MB and `.data` 6 MB in that run). Unknown cells in the saved map are 205 and free cells 254 (trinary mode, `free_thresh` 0.25, `occupied_thresh` 0.65). Not yet run with the real lidar. Do not use `ros2 interface show slam_toolbox/srv/SaveMap` to look at the fields: on this robot it crashes (a ros2cli error on a comment in the `.srv` file). Read the source or make the call. If the script reports no map, check `~/robot_code/maps/` and the script output before repeating.
7. **Check the saved map against one measured distance before you plan on it.** Measure one known distance on the floor with a tape or a measuring wheel, for example from the dock to the far end of the glass room, and measure the same two points on the map (`plan_route.py --info` gives the resolution and origin, and an image editor gives pixels). **If the map is more than about 3 % shorter than the floor, the map has shrunk along the wall; do not plan on it** (map again, see below). The size of this effect on the real hall is **NOT VERIFIED**.
8. **Dock the robot** (controller Home, held 3 s, or Studio) and **stop mapping, on the robot:**

   ```bash
   bash ~/robot_code/delivery/robot/stop_stack.sh
   ```

9. **Copy the map to your computer (on your computer**, from the `TurtleBot` folder; Windows shown):

   ```powershell
   scp -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 "ubuntu@[fe80::da3a:ddff:fe41:d5df%8]:~/robot_code/maps/route1.*" .
   ```

   On macOS and Linux use the key `~/.ssh/turtlebot4_ed25519` and your interface name in the address. Keep the `.posegraph` and `.data` files with the map; they allow a later mapping session to continue.

**Why `slam_delivery.yaml` (found 2026-11-06 in the simulator, real slam_toolbox on the Pi).** The installed `slam.yaml` shrinks a long plain wall along its length. On a 40 m synthetic hall the map came out about 30 % short (end wall at x -6.0 where the truth is -1.5, glass room west wall at 13.7 where the truth is 26.5). The match score is almost flat along a plain wall, and with the installed `distance_variance_penalty` 0.5 the penalty for a 0.25 m slip is only 2.5 %, so the scan matcher slides the robot back onto cells it already knows. With 0.05 (`config/slam_delivery.yaml`) the same run gave end wall -1.53 and glass room 25.57 (about 3.4 % short) with no ghost second end wall. The real hall has more features than the synthetic one, so the real size of the effect is **NOT VERIFIED**; that is why step 7 asks for a measurement. To undo: start mapping with the installed file instead (edit `SLAM_PARAMS` in `robot/start_stack.sh`, or in a simulator run set `SIM_SLAM_PARAMS`).

**Real mapping, 2026-11-06.** `start_stack.sh map` with `config/slam_delivery.yaml` ran on the real robot in the small room, driven with `robot/motion_probe.py` and saved with `save_map.sh`: the map is 4.10 x 4.45 m with closed walls. **The map distances were NOT compared with a tape measure, so the real SLAM scale is still NOT VERIFIED**, and that room is too small to show the shrink along a long wall. Do step 7 on campus.

**Fallback if wall-follow fails:** drive the route by hand with the controller or Studio while recording `ros2 bag record /scan /odom /tf /tf_static /imu`, then build the map on a computer. Offline SLAM needs ROS 2 Jazzy on that computer **[to verify]**; this has not been tried.

---

## 7. Clean the map

The lidar sees glass as free space or not at all, and people walking by leave marks. Edit the `.pgm` copy on your computer (keep the original).

1. Open `route1.pgm` in [GIMP](https://www.gimp.org/) (free, Windows, macOS, Linux) or another image editor that can save PGM.
2. Paint the glass doors and the front of the glass room **black** (occupied) with the pencil tool. Thin 1 to 2 px lines are not enough on their own; the planner's keepout lines (section 8) are the real protection.
3. Erase marks left by people and anything that does not belong (paint white, free space). Leave grey (unknown) cells only where the robot never goes; the planner treats unknown cells as obstacles.
4. **Do not resize or crop** the image: the resolution and origin in `route1.yaml` must still match.
5. Save as PGM (same file name). Check that `route1.yaml` still names the right image.

---

## 8. Plan the route on your computer

You need Python 3.10 or newer and PyYAML (`python -m pip install pyyaml`). Use `python3` on macOS and Linux. From the repo root:

1. **Learn the coordinates.** This prints size, origin, resolution and the pixel to metre conversion:

   ```bash
   python TurtleBot/delivery/tools/plan_route.py --map route1.yaml --info
   ```

   Coordinates are map-frame metres (x right, y up, yaw in degrees, 0 = +x). Positions you read in an image editor are pixels counted from the **top-left** of the image; write them as `{px: COLUMN, py: ROW}` in the spec and the tool converts them.
2. **Write a spec.** Copy [tools/route_spec.example.yaml](tools/route_spec.example.yaml) and replace the made-up numbers:

   | Key | Meaning |
   |---|---|
   | `dock_pose` | Robot pose on the dock (becomes the AMCL initial pose). `yaw` is the **real yaw of the robot on the dock**, which faces the dock (measured 2026-11-06: -32 degrees on the dock, 147 after undocking, in that room). Do not assume 0: take the direction the robot faces on the dock [to verify the easiest way to read it on campus] |
   | `start` | Where the lane begins (default since 2026-11-06: 0.7 m straight out from the dock, that is **opposite** to the dock yaw, because the real robot faces the dock; *earlier the default was 0.7 m in the direction of the dock yaw, which is INTO the dock on a real robot, fixed in `tools/plan_route.py`*) |
   | `goal` | Pickup spot (yaw optional; default is the direction of travel) |
   | `via` | Optional points the path must pass through |
   | `wall_offset_m` | Wanted distance from the robot centre to the nearest obstacle: **0.5** |
   | `clearance_m` | Hard minimum distance to obstacles (0.30) |
   | `lane_half_width_m` | Half width of the preferred lane (0.25) |
   | `waypoint_spacing_m` | Distance between waypoints (2.0) |
   | `keepout_lines` | Lethal lines across the glass room opening and in front of each glass door (`from`, `to`, `width_m`) |
   | `keepout_polygons` | Lethal filled areas |
   | `slow_zones` | Ramps, cables, near the dock: `speed_percent` 10 to 100, with `points` or `center` plus `radius_m` |
   | `settings` | Overrides copied into `route.yaml` (timeouts, buttons) |
3. **Run the planner** (writes only files):

   ```bash
   python TurtleBot/delivery/tools/plan_route.py --map route1.yaml --spec my_spec.yaml --out route1_plan
   ```

   Exit code 0 is success, 2 is bad input, 3 means no path exists (the message names the likely cause).
4. **Open `route1_plan/preview.html`** in a browser (one self-contained file). Check the numbers report and every warning: the path should stay near the wall (a warning appears when it may not), keep out of the glass room, and cross each slow zone. Fix the spec and run again until it looks right.
5. **The output folder** is complete for the robot:

   | File | What it is |
   |---|---|
   | `route.yaml` | Dock pose, outbound and inbound waypoints, settings. Its `map:` entry is `map.yaml` |
   | `map.yaml`, `map.pgm` | A copy of your map, so the folder holds everything `start_stack.sh nav` needs |
   | `keepout_mask.yaml`, `keepout_mask.pgm` | Preferred lane (0), lethal lines (100) |
   | `speed_mask.yaml`, `speed_mask.pgm` | Slow zones |
   | `preview.html` | The plan and the numbers |

6. **Copy the folder to the robot (on your computer;** Windows shown):

   ```powershell
   ssh -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 "ubuntu@fe80::da3a:ddff:fe41:d5df%8" "mkdir -p ~/robot_code/routes"
   scp -r -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 route1_plan "ubuntu@[fe80::da3a:ddff:fe41:d5df%8]:~/robot_code/routes/route1"
   ```

   If `~/robot_code/routes/route1` already exists, `scp -r` puts the folder inside it; use a new name or delete the old one first (rm of your own route folder is fine; do not delete anything else).

---

## 9. Phase 2: supervised runs

Pre-conditions: Phase 0 passed, the route folder is on the robot (and `~/robot_code/routes/current` points to it, section 6 box, if you will start from the menu), the robot is on the dock with battery above 40 % (the route's `min_battery_start`), the controller is charged and on, a person is ready to walk behind the robot, and it is outside lunch hours.

**1. Start the navigation stack once (on the robot):**

```bash
bash ~/robot_code/delivery/robot/start_stack.sh nav --route-dir ~/robot_code/routes/route1 --dry-run
bash ~/robot_code/delivery/robot/start_stack.sh nav --route-dir ~/robot_code/routes/route1
```

**The robot must be on the dock.** The script first writes an AMCL parameter file with the route's dock pose as AMCL's initial pose (`tools/make_localization_params.py`), starts the lidar motor, and then starts **one** process, `launch/delivery_stack.launch.py`, with the map, the two masks and `config/nav2_delivery.yaml`. AMCL therefore starts already localized at the dock, and Nav2 comes up on its own. **You do not send an initial pose and you do not wait for any message before the dry run.** Why: Nav2's lifecycle manager gives up after 60 s if the map frame does not exist, and AMCL publishes it only after it has a pose, so a program that sent the pose later was too late (seen in the simulator on 2026-11-05). *Earlier versions of this guide said to wait for "Managed nodes are active" and then send the initial pose, and started localization, the filters and Nav2 as three launches 20 s apart; replaced 2026-11-05.* It refuses to start if a stack already runs. Logs and a `state.txt` with the PIDs are in `~/robot_code/logs/delivery/<date-time>/`.

**2. Wait and check.** Wait about 2 minutes. Reading a log is not a ROS command, so TB-25 allows it. **On the robot:**

```bash
grep -i "Managed nodes are active" ~/robot_code/logs/delivery/latest/stack.log | tail
grep -i "error" ~/robot_code/logs/delivery/latest/stack.log | tail
```

This is a check that the stack is up, not a step before something else: the line `Managed nodes are active` comes from the lifecycle manager once all twelve servers are active. Do not go on if it did not appear; use `stop_stack.sh` and read the log. (`latest` is a link to the newest log folder; the log name `stack.log` comes from `start_stack.sh`.)

**3. Dry run (moves nothing; on the robot):**

```bash
python3 ~/robot_code/delivery/delivery_mission.py --route ~/robot_code/routes/route1/route.yaml --dry-run
```

It connects, checks `/odom`, `/dock_status`, `/battery_state`, the buttons topic, Nav2 and the route, shows the first display text, and never sends a goal or velocity. The dry run is itself a new ROS participant (TB-25): let it finish and wait until `/odom` is steady before the real run.

**4. Real run.** Interactive (it asks "is a person next to the robot?"):

```bash
python3 ~/robot_code/delivery/delivery_mission.py --route ~/robot_code/routes/route1/route.yaml
```

Or detached, so a Wi-Fi drop (TB-10) does not kill it (`--yes` because nobody can answer a question; the person walking behind is then the only check, so be sure):

```bash
setsid nohup python3 ~/robot_code/delivery/delivery_mission.py --route ~/robot_code/routes/route1/route.yaml --yes > ~/robot_code/logs/delivery.out 2>&1 &
tail -f ~/robot_code/logs/delivery.out
```

Other options: `--allow-undocked` (the robot is already localized on the map; skips the undock and sends no initial pose), `--log-dir DIR`.

**What the robot shows and does, in order.**

| Step | Robot display (18 characters per line, 5 lines) | Chime | What happens |
|---|---|---|---|
| Preflight | `Cannot start` plus the reason, if refused | none | Refuses if `~/STOP` exists, battery is below the minimum, or the robot is not docked. Exit code 2, nothing moved |
| Prepare | | none | Sends the dock pose again (AMCL already has it from the start), waits for Nav2, waits 20 s after program start and 5 s of `/odom` without a gap over 0.3 s (TB-25) |
| Start | `Going to food court` | start | Undocks, then drives the outbound leg (one retry: costmaps cleared and the poses not yet reached are sent again) |
| Pickup | `Food placed?` / `Press button 3` | arrive | Waits for button 3, at most `pickup_timeout_s` (600 s). Other buttons are ignored and the text is shown again. The text is re-published every 5 s *(replaced 2026-11-06: now every 0.5 s, and button 1 also answers; see the table below)* |
| Food placed | `Thank you!` | thanks | Waits `hands_clear_s` (5 s), then drives the inbound leg |
| No press in time | `No food. Going home` | | Drives home empty; ends with exit code 4 |
| Handoff | `Your food is here` / `Take it, press 4` *(replaced 2026-11-06, see below)* | arrive | Waits for button 4, at most `handoff_timeout_s` (900 s) |
| Received | `Thank you!` / `Docking` | thanks | Docks; verifies `/dock_status` for 10 s. If the first dock fails: see "Dock retry" below |
| No press in time | the food message stays | | Docks anyway; exit code 0 |

**Dock retry (changed 2026-11-06).** The hand-off pose is 0.7 m from the dock, and the goal tolerance (`xy_goal_tolerance`) is 0.25 m, so the robot stops 0.92 to 0.98 m from the dock in the simulator (four runs). The fake base accepts `/dock` only within 1.0 m, which is an assumption: **the real Create 3 dock range is NOT VERIFIED**, so there is little margin. Record the distance at which the real `/dock` succeeds or fails on the first real runs (the mission log has the event). If the first dock fails, the mission now drives to a point 0.45 m from the dock pose, on the line from the hand-off pose to the dock (`DOCK_RETRY_DISTANCE` in `delivery_core.py`), and docks once more; the event text is "dock failed, driving closer to the dock and docking once more". *Earlier the second try started at the hand-off pose, where the robot already believed it was, so the leg ended at once with no motion and the second dock failed the same way (found in the simulator on 2026-11-06).*

**Display texts and buttons since 2026-11-06 (replaces the "Robot display" texts above where they differ).** Tested on the real robot with simulated presses; how the screen looks to a person and the physical buttons are **NOT yet confirmed**.

| Moment | Screen | Buttons |
|---|---|---|
| Driving, undocking, docking, preparing | Status text and `2 = Stop` | **Button 2 = Stop** (exit code 130, display `Stopped`) |
| At the food court | `Food placed?` / `>Back to the lab` / `Press button 1` | Button 1 (or 3) = food placed, the robot drives home. Button 2 only puts the text back |
| At the lab | `Your food is here` / `>Done, thank you` / `Press button 1` | Button 1 (or 4) = received, the robot docks. Button 2 only puts the text back |
| After a stop or an alarm | The text stays until a button is pressed | Any press returns to the menu, which then offers `Back to the lab` |

The mission re-shows the text every 0.5 s while it waits for a button (`RESHOW_PERIOD`; it was 5 s). Reason: on the real robot, a press of button 2 wiped the screen for up to 3 s. The menu also redraws after the press and after the release.

**Exit behaviour (tested 2026-11-06).** Exit codes are as in the table below. In the real runs: run 1 (mission started by hand, no button pressed) gave exit 4 (returned without food) after outbound 18 s, waiting, inbound 9 s and docking at the first try in 26 s, with 0 holds and 0 retries; run 2 (from the menu, the press came too early, inside the 0.5 s ignore window) gave exit 4; run 3 (from the menu, full delivery with presses) gave exit 0. Each trip started from the menu writes its output to `~/robot_code/logs/delivery/menu_<date>_<time>.out`. The route was 1.1 m long, in a small room, slowed near the dock. These are tiny trips; see section 13 for what is still open.

**`--trip home`.** `delivery_mission.py --route ROUTE.yaml --trip home` is "Back to the lab" from wherever the robot stands: it must be undocked and localized, skips the undock, drives the inbound route from the nearest route pose, docks with the normal retry, and asks for no button. It refuses when `/amcl_pose` gave no position within 10 s. Exit 4 means "returned" (nobody got food); already docked also gives exit 4. The menu uses it after a stop or alarm, and refuses `Back to the lab` with `Not on the map` when the navigation stack is not running (AMCL would be told that the robot is on the dock).

Other behaviour: a stale `/odom` or `/scan` (over 2 s) during a leg pauses the robot (display `Paused`), and the leg resumes when the sensor is back (at most 3 holds per leg). A battery under 15 % raises the alarm. Any **alarm** cancels navigation, stops the robot, plays the alarm chime and shows `NEED HELP` with the reason; it never drives on again.

**Exit codes and the log.**

| Code | Meaning |
|---|---|
| 0 | Delivered (also when the student did not press "received" and the robot docked anyway) |
| 2 | Refused, or setup failed; nothing moved |
| 3 | Alarm, the robot needs help (display shows `NEED HELP`) |
| 4 | Returned without food (nobody pressed "food placed") |
| 130 | Stopped by you (Ctrl+C, SIGTERM or `~/STOP`) |

The event log is written to `~/robot_code/logs/delivery_<date>_<time>.log` (folder set by `--log-dir`), one line per event.

**How to stop it at any time.** Press **B** on the controller first (the base stops). Then one of:

- Ctrl+C in the terminal that runs it
- `touch ~/STOP` from another terminal on the robot (a new login is a new ssh session, not a ROS participant; delete the file afterwards: `rm ~/STOP`)
- `pkill -INT -f delivery_mission.py` from another terminal on the robot

The program cancels the Nav2 goal, stops the base, and shows `Stopped`. Afterwards press B again to clear the emergency stop.

**5. After the run, stop the stack (on the robot):**

```bash
bash ~/robot_code/delivery/robot/stop_stack.sh
```

It sends SIGINT to Nav2, then the filters, then localization and SLAM, waits up to 20 s for each group, and lists what is left. It never uses SIGKILL or sudo.

**6. Record each run** for TB-29 (ROADMAP and a dated step log in `General Tasks/`): date and time, route name, success or exit code, number of takeovers (B pressed, manual driving), time for each leg, battery at start and end, distance from the wall on straight stretches (acceptance: within 0.15 m of the chosen value), what you saw at the glass doors, ramps and cables. The target is 10 round trips outside lunch hours, at least 9 without a takeover.

### The front-panel menu (added 2026-11-06)

**Why it exists.** The first version showed `Going to food court` as a temporary message, and it vanished at the next button press. People wanted the delivery as a real menu entry above Dock, Undock and Power. The stock menu of the robot (`turtlebot4_node`) has a fixed list of entries, so one cannot be added without changing that program. While a text is on `/hmi/display/message`, the stock buttons 1, 3 and 4 do nothing, button 2 clears the text, and the stock program acts when a button is *released*. So `delivery_menu.py` draws its own menu through that message channel and redraws after every press and release. It needs no sudo and changes no stock file. (Source read: `display.cpp` of turtlebot4 `jazzy`; behaviour then tested on the robot.)

**What is on the screen.** The first entry depends on the dock: `>Go to food court` when the robot is docked, `>Back to the lab` when it is not. Below it: Dock, Undock, EStop, Wall Follow Left, Wall Follow Right, Power, Help. The `>` marks the highlighted entry.

| Button | What it does in the menu |
|---|---|
| 1 | Select the highlighted entry. A trip and `Power` first ask `1 = Yes / 2 = No` |
| 2 | Back. While a trip is running it is **Stop** |
| 3 | Up |
| 4 | Down |

The menu ignores a second press within 0.2 s (debounce), so a bouncing button cannot answer `1 = Yes` by itself.

**During a trip.** The screen shows the status text and `2 = Stop`. At the food court it shows `Food placed?` / `>Back to the lab` / `Press button 1` (button 3 also works). At the lab it shows `Your food is here` / `>Done, thank you` / `Press button 1` (button 4 also works). After a stop or an alarm the text stays until a button is pressed; then the menu offers `Back to the lab`, which drives from the nearest route pose and docks (`delivery_mission.py --trip home`). `Back to the lab` refuses with `Not on the map` when the navigation stack is not running.

**What a trip needs.** The navigation stack must be running first (`start_stack.sh nav`, steps 1 and 2 above). Reasons: the menu starts `delivery_mission.py`, and the mission needs Nav2. Measured 2026-11-06 on the real robot: the stack was ready 27 to 70 s after the start, and from pressing `Yes` to the first movement took about 1 min 15 s. With no stack the trip entry refuses.

**The route folder rule.** The menu reads `~/robot_code/routes/current`, a link to a route folder. On 2026-11-06 it points to `home` (a 1.1 m test route in the room at home). **Before campus point it to the campus route** (box at the start of section 6): `ln -sfn route1 ~/robot_code/routes/current`. With no `route.yaml` in the folder the screen shows `No route saved`. The variable `DELIVERY_ROUTE_DIR` overrides the link.

**Install, check, remove (on the robot).** Log in first: open a terminal on your computer (Windows: PowerShell; macOS: Terminal; Linux: Ctrl+Alt+T), then `ssh -i ~/.ssh/turtlebot4_ed25519 ubuntu@turtlebot4.local` (on Windows the key is `$env:USERPROFILE\.ssh\turtlebot4_ed25519`; or use the address on the robot's display). Copy the delivery folder first (`tools/deploy.py`, section 4); the service runs the program from `~/robot_code/delivery`.

```bash
bash ~/robot_code/delivery/robot/install_menu.sh --dry-run    # prints the commands, changes nothing
bash ~/robot_code/delivery/robot/install_menu.sh              # installs, enables and starts the service
bash ~/robot_code/delivery/robot/install_menu.sh --status     # enabled? active? last log lines
bash ~/robot_code/delivery/robot/install_menu.sh --uninstall  # stops it, disables it, removes the unit file; the stock menu comes back
```

It is a systemd user service (`~/.config/systemd/user/delivery-menu.service`), needs no sudo, and starts at boot because the robot's user has lingering enabled. Stopping or restarting it does not stop the navigation stack or a running mission (`KillMode=process`). A deploy restarts it when it is enabled and no mission runs. Change register: [MAINTENANCE.md](../MAINTENANCE.md) (menu service).

**Logs.** `~/robot_code/logs/delivery/menu.log` is the menu's own log. Each trip's output is in `~/robot_code/logs/delivery/menu_<date>_<time>.out`. The mission's event log is as in the table above.

**Test tool.** `robot/press_buttons.py` presses the buttons from software (a flood of `/hmi/buttons` messages for 0.15 s, because the real publisher runs at about 95 Hz), for example `python3 ~/robot_code/delivery/robot/press_buttons.py show 4 4 3 1 2 show` after `source /etc/turtlebot4/setup.bash`. Button 1 can start a trip: use it only with a person next to the robot.

**What was tested on the real robot (2026-11-06, simulated presses):** scrolling, confirm and No, Yes, a whole delivery, Stop in the middle of a route, Back to the lab, Dock, Undock, EStop on and off, Wall Follow Left. **NOT tested:** `Power` (it would switch the robot off; only checked that the service `/robot_power` exists as `irobot_create_msgs/srv/RobotPower`), `Wall Follow Right`, and a press of the PHYSICAL buttons on the new menu, and how the screen looks to a person.

**Known weakness, fixed 2026-11-06.** The first version read `/hmi/buttons` at about 95 Hz and used 33 % of a core when idle. `ros_buttons.py` polls every 0.1 s instead, and the menu left the top of the CPU list (under 14 %, not measured exactly). The mission uses it too.

---

## 10. Phase 3: demo checklist

- [ ] Phase 2 targets met; the route folder on the robot is the one you tested.
- [ ] Robot charged (above 40 %); controller charged; the display shows the address.
- [ ] Time chosen outside lunch hours; the area told about the demo.
- [ ] A person walks behind the robot with the controller; B tested that day; TurtleBot Studio ready as second layer (connected before the start, not during the run: TB-25).
- [ ] `~/STOP` does not exist. The robot was on the dock when the stack was started (once); the log shows `Managed nodes are active` (no initial pose to send, section 9); dry run passed.
- [ ] The saved map was compared with a measured distance (section 6, step 7).
- [ ] The vendor knows: put the food in, press **button 3** on the front panel. The student knows: take the food, press **button 4**. Neither presses 1 or 2. *(Replaced 2026-11-06: with the delivery menu, button 1 also answers the prompt, and button 2 is Stop. Brief the vendor and the student on that, and that nobody should press other buttons at the food court.)*
- [ ] Run the real mission; watch the display texts from section 9.
- [ ] Afterwards: `stop_stack.sh`, record the result, add changes and findings to MAINTENANCE.md and the TB-29 task.

---

## 11. Tuning

**In the planner** (spec file, then re-plan and copy the route folder again):

| Key | Effect |
|---|---|
| `wall_offset_m` (0.5) | Distance from the robot centre to the wall. Larger moves the lane away from the wall |
| `lane_half_width_m` (0.25) | Width of the cheap lane. Narrower holds the robot to the lane more strongly; too narrow may make it stall or oscillate **[to verify]** |
| `keepout_lines`, `keepout_polygons` | Lethal areas. Add lines when the robot cuts into a glass door or the glass room |
| `slow_zones[].speed_percent` | Speed limit inside the zone, 10 to 100 percent of the normal speed |
| `waypoint_spacing_m` (2.0) | Closer waypoints hold the path tighter |

**How the masks encode values.** Both masks are loaded in Nav2 "scale" mode with `negate: 0`, `occupied_thresh: 0.99`, `free_thresh: 0.01`. Pixel 255 (white) reads as value 0, pixel 0 (black) as value 100; values between are linear.

- **Keepout mask.** Value 0 on the lane, rising to 50 over 1 m outside the lane, 50 elsewhere, 100 on keepout lines and polygons. The filter copies the mask value into the costmap, scaled to 0 to 254, when it is higher than the existing cost: 50 is a soft cost of about 127, 100 is lethal.
- **Speed mask.** Speed limit in percent = 100 - mask value. So **0 = full speed**, and 60 means a 40 % limit.

**In `config/nav2_delivery.yaml`.** The changes from upstream are marked `# delivery:`:

| Key | Upstream | Delivery |
|---|---|---|
| controller (`FollowPath`) plugin | MPPI | `nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController` |
| `controller_frequency` | 20 Hz | 10 Hz (enough at 0.20 m/s; within the Pi's means) |
| RPP `desired_linear_vel` | n/a (MPPI `vx_max` 0.5) | 0.20 m/s, the speed cap |
| RPP `lookahead_dist` (`min_` / `max_`) | n/a | 0.6 m (0.3 / 0.9); `use_velocity_scaled_lookahead_dist` false, so the fixed 0.6 m is used |
| RPP `rotate_to_heading_angular_vel`, `max_angular_accel` | n/a (MPPI `wz_max` 1.9) | 0.8 rad/s, 1.0 rad/s^2 |
| RPP `use_rotate_to_heading`, `rotate_to_heading_min_angle` | n/a | true, 0.785 rad (turns in place before moving off when the heading is off by more than that) |
| RPP `allow_reversing` | n/a (MPPI `vx_min` -0.35) | false: the controller never reverses by itself with food on board |
| RPP `use_regulated_linear_velocity_scaling`, `regulated_linear_scaling_min_radius`, `regulated_linear_scaling_min_speed` | n/a | true, 0.9 m, 0.10 m/s (slows in tight curves) |
| RPP `use_cost_regulated_linear_velocity_scaling` | n/a | false: the soft lane mask must not slow the robot |
| RPP `min_approach_linear_velocity`, `approach_velocity_scaling_dist` | n/a | 0.05 m/s, 0.6 m (slows near the goal) |
| RPP `use_collision_detection`, `max_allowed_time_to_collision_up_to_carrot` | n/a | true, 1.0 s |
| RPP `transform_tolerance` | n/a | 0.5 s (the Pi can be late) |
| goal checker `xy_goal_tolerance`, `yaw_goal_tolerance` | see the upstream file | 0.25 m, 0.25 rad (this tolerance is why the robot stops 0.92 to 0.98 m from the dock at the hand-off) |
| BT navigator `bt_loop_duration`, `default_server_timeout` | 10 ms, 20 ms | 50 ms, 1000 ms (with 20 ms the tree gave up with "Timed out while waiting for action server to acknowledge goal" on the busy Pi while driving was fine; simulator on the robot, 2026-11-05) |
| lifecycle manager `bond_timeout` | 4 s (Nav2 default) | **0 since 2026-11-06** (no bond watchdog), set as `BOND_TIMEOUT` in `launch/delivery_stack.launch.py`. *It was 20 s before (a server missed the 4 s heartbeat under load and Nav2 shut itself down).* Why 0: on the real robot at a CPU load of 15 the lifecycle manager logged `CRITICAL FAILURE: SERVER bt_navigator IS DOWN` 0.2 s after the bond was formed, although the timeout was 20 s, and reset all Nav2 nodes (1 of about 6 real stack starts). Why the bond broke so fast is **not understood**. With 0 the mission still polls `is_active` in every leg, and all nodes share one process. Runs since: 0 CRITICAL, no `Creating bond timer`. To undo, set `BOND_TIMEOUT` back to 20.0 and restart the stack |
| velocity smoother `max_velocity` | `[0.26, 0, 1.0]` | `[0.20, 0, 0.8]` |
| velocity smoother `min_velocity` | `[-0.26, 0, -1.0]` | `[-0.10, 0, -0.8]` |
| velocity smoother `max_accel` | `[2.5, 0, 3.2]` | `[0.3, 0, 1.0]` |
| velocity smoother `max_decel` | `[-2.5, 0, -3.2]` | `[-0.5, 0, -1.5]` |
| inflation `inflation_radius` (both costmaps) | 0.45 | 0.35 |
| inflation `cost_scaling_factor` (both costmaps) | 4.0 | 6.0 |
| `filters` lists | none | global: `keepout_filter`; local: `keepout_filter`, `speed_filter` |
| controller_server `speed_limit_topic` | default `speed_limit` | `/speed_limit` |

*Earlier versions of this table listed MPPI `vx_max` 0.5 to 0.20 m/s, `vx_min` -0.35 to -0.10 m/s and `wz_max` 1.9 to 0.8 rad/s. MPPI (2000 samples at 20 Hz) was replaced on 2026-11-05: on the Pi 4 it missed its loop rate all the time and kept the CPU at 100 % in the simulator, and Nav2 then gave up with "Failed to make progress". Regulated Pure Pursuit costs little CPU and follows the planned lane closely. Its behaviour on the real floor is **NOT VERIFIED**.*

**Mission and menu constants changed 2026-11-06 (found by real driving):**

| Constant | Where | Before | Now | Why |
|---|---|---|---|---|
| `GOAL_ANSWER_TIMEOUT` | `delivery_mission.py` | none (waited forever) | 5 s | `goThroughPoses` of `nav2_simple_commander` waited for the goal answer with no time limit, so the mission froze with the stop button dead. `go_through` now sends the goal itself: after 5 s without an answer, or on a stop request, the leg fails the normal way, and an unanswered goal is cancelled by cancelling every goal on the server |
| `RESHOW_PERIOD` | `delivery_core.py` | 5 s | 0.5 s | A press of button 2 wiped the screen for up to 3 s. The mission re-publishes the text this often while it waits for a button; the menu also redraws after the press and after the release |
| Button debounce | `menu_core.py` | none | 0.2 s | A bouncing button could answer `1 = Yes` |
| Button polling | `ros_buttons.py` | every message (about 95 Hz) | every 0.1 s | The idle menu used 33 % of a core |
| OAK-D camera container | `robot/start_stack.sh` | left running | stopped at each stack start (`pkill -INT -f __node:=oakd_container`); `--keep-camera` skips this | The container (not used by the delivery) burns about 100 % of a core even with the camera stopped. It comes back at the next reboot. No installed file changed (MAINTENANCE.md, Known issues). To undo: use `--keep-camera`, or reboot |

Also logged since 2026-11-06: the longest `/odom` gap at the end of each run ("longest /odom gap during the run"): 0.576 s in a stop test, 0.253 s in a home trip. 0.452 s in the final delivery. The load average during a trip was 18 with the camera container running and about 8.6 with it stopped.

**Two settings added 2026-11-06** (found in the simulator, see `sim/README.md`, Results):

| Setting | File | Before | Now | What it does and how to undo it |
|---|---|---|---|---|
| AMCL `alpha1` to `alpha4` | `config/localization_delivery.yaml` | 0.2 | 0.05 | How much odometry noise AMCL assumes. With 0.2 the position estimate fell behind the truth by about 3.7 % of the distance driven along a wall with nothing to fix the position along it (1.38 m after 25 m), which made docking fail in some simulator runs. With 0.05 the largest error was 0.24 to 0.60 m. `alpha5` is not used by the differential model and is unchanged. **A small sample, and the real odometry error is NOT VERIFIED:** if the real robot slips more than the 2 % tested, a higher value may suit it better. To undo, set the four values back to 0.2 and restart the stack. |
| slam_toolbox `distance_variance_penalty` | `config/slam_delivery.yaml` | 0.5 | 0.05 | How much a scan match is penalised for moving away from where the odometry says the robot is. A small value stops the matcher sliding the robot back along a plain wall, so the map does not shrink (section 6). Side effect not tested: a smaller penalty trusts the scan match more. To undo, set it to 0.5 or start mapping with the installed `slam.yaml` (see section 6). |

The lower inflation makes the cost fall off sooner, leaving room for the lane mask to decide where the robot drives. At 0.5 m from a wall the inflation cost is 0 in both versions. Do not raise the speed caps without a new safety check and an entry in MAINTENANCE.md.

**After a map change** (new mapping run, new glass edits): save the map, clean it, run `plan_route.py` again, copy the new route folder to the robot, and restart the stack (`stop_stack.sh`, then `start_stack.sh nav`). Old masks do not fit a new map, because their size and origin are copied from the old one.

---

## 12. Offline tests

From the repo root, on any computer (Python 3.10+; PyYAML for the delivery tests; no robot, no ROS; the config test also needs `bash`, such as Git Bash on Windows):

```bash
python TurtleBot/tests/offline/test_delivery_mission.py
python TurtleBot/tests/offline/test_plan_route.py
python TurtleBot/tests/offline/test_delivery_config.py
python TurtleBot/tests/offline/test_delivery_sim.py
python TurtleBot/tests/offline/test_delivery_deploy.py
```

`python TurtleBot/delivery/tools/verify_all.py` runs all of them and more in one go (section 14).

| Test | Covers |
|---|---|
| `test_delivery_mission.py` | Route file errors, odometry steady rule (same answers as `motion_shapes.py`), button edges, display text, the state machine with a fake robot: delivery, no food, timeouts, retry, holds, alarm, stop |
| `test_plan_route.py` | Planner on synthetic halls: wall distance, glass room keepout, slow zones, mask pixel values, preview page, error cases |
| `test_delivery_config.py` | Nav2 config against upstream (only intended keys differ), filters, speed caps, launch file, shell scripts (`bash -n`, LF endings, `--dry-run`, refusals with fake `ros2`) |
| `test_delivery_sim.py` | The simulator's pure parts: wall follower, map checks, run analysis, the scripts' guards (no ROS). On Windows it uses Git Bash, not the `bash.exe` of WSL in `System32` |
| `test_delivery_deploy.py` | `tools/deploy.py` with fake `ssh` and `scp`: manifest, command order, refusal while a mission runs, rollback, status |

Each prints PASS or FAIL lines and exits non-zero on failure. The GitHub Actions workflow runs the first three on every push [to verify whether it also runs the two new ones]. Passing them says nothing about the real robot.

---

## 13. Not verified yet

*Updated 2026-11-06.* The real robot has not driven any of this. Since 2026-11-05 parts have run in the simulator on the robot's Pi (robot docked, fake base, ROS domain 77); those items are marked with a date below. The original list follows, with nothing removed.

**Verified in the simulator on 2026-11-06 (not on the real floor or lidar):**

| Point | Result |
|---|---|
| `save_map.sh` service names and fields (`save_map`, `serialize_map`, `name.data`, `filename`) | Both calls returned `result=0` on the real slam_toolbox, files written (section 6, step 6) |
| slam_toolbox runs without `/clock` | Yes, it ran and mapped without a `/clock` topic |
| The ROS adapter `RosRobot`, the feedback fields for hold and resume | Ran against Nav2 in the simulator, including a `stall` scenario with hold and resume (exit 0). Not with the real base |
| Whether the launches shut down cleanly on SIGINT, the `pgrep` and `pkill` patterns | The simulator scripts start and stop their own process groups, which does not test `stop_stack.sh`'s patterns on a real run. See the next table for the real run |

**Verified on the real robot on 2026-11-06, on its dock, with no motion (the real base and ROS domain 0):**

| Point | Result |
|---|---|
| The navigation stack runs for 70 minutes next to the real base without stalling `/odom` (ROADMAP TB-25) | Soak test `p0_soak_20261106_095510`: **PASS**. From 10 minutes after the stack started until it stopped (3659 s): `/odom` 20.0 Hz, longest gap 0.091 s, no gap over 0.3 s. The whole 78 minute recording: longest gap 0.257 s, about 20 s after the stack started, with total CPU at 92 %. It starts no new ROS participant while it runs, so the stall a new participant can cause (TB-25) is not part of this test |
| Pi load with the stack on the dock and no goals | Load average mean 6.1, maximum 11.9; 63 to 65 degrees C; the stack's process uses 130 to 146 % of a core. The load while really driving is **NOT VERIFIED** |
| Nav2 comes up on its own on the dock | `start_stack.sh nav` reached `Managed nodes are active` in 27 s with no initial pose sent |
| `delivery_mission.py --dry-run` with the real stack | Exit 0, twice. Both times the first `amcl/get_state` and `bt_navigator/get_state` replies never arrived and the second try answered at once. Before this fix the mission could wait 120 s and refuse with Nav2 fully active (seen once in the simulator) |
| `stop_stack.sh` on a real run | Stopped the stack, `Leftovers: none, all stopped`. The container ends with exit code -6 in its log after the lifecycle manager's shutdown, in every run so far; nothing is left running. Cause not investigated |
| Display: `/hmi/display/message` | The real `turtlebot4_node` cuts the text every 18 characters and does NOT split on newlines (`'Going to food\ncourt'` showed as `'Going to food\ncour'`, `'t'`). Fixed with `core.display_wire`, and read back on `/hmi/display` as `'Going to food'`, `'court'`. What a person sees on the screen was not looked at |
| How long a display message stays | It does not time out: unchanged for over 120 s with no button pressed. It stays after the program ends, until something redraws the screen |
| Chime on `/cmd_audio` | The base has one subscriber and the message was sent. Whether it is audible was not checked |

**Verified on the real robot on 2026-11-06, WITH motion (later the same day; over Wi-Fi, Ethernet cable out, in a room of about 2.5 x 1.8 m with a corridor at home; the robot has NOT been to campus).** Docking was measured with `robot/motion_probe.py` (log `~/robot_code/logs/delivery/motion/first_motion.log`):

| Start | Dock visible at start | Result | Time |
|---|---|---|---|
| 0.13 m after undock, facing away | no | docked | 19.3 s |
| 0.53 m, facing the dock | yes | docked | 23.2 s |
| 1.00 m, facing the dock | yes | docked | 30.0 s |
| 1.39 m, facing the dock | yes | docked | 37.8 s |
| about 1.55 m, facing the dock | yes | docked | 40.3 s |
| 0.97 m, facing away | no | docked | 36.8 s |
| about 2 m, facing away | no | FAILED after 16.0 s, wandered 0.4 m further (status 6) | 16.0 s |
| about 1 m, facing the dock by odometry | no | FAILED after 16.0 s, ended 0.45 m from it with the dock visible | 16.0 s |
| 0.45 m, right after that failure | yes | docked | 23.4 s |
| after 10 s of wall follow, from the menu | not recorded | FAILED, `Dock failed` on the screen | 16 s |

| Point | Result |
|---|---|
| Real Create 3 dock range (was assumed 1.0 m in the simulator) | The dock action fails after 16 s when it does not find the dock; being nearer helps, and a closer second try works. So the mission's retry leg to 0.45 m (`DOCK_RETRY_DISTANCE`) is right, and the planned hand-off distance of 0.7 to 1.1 m is inside the range. The simulator's 1.0 m limit (`sim/fake_base.py`, `DOCK_RANGE`) is on the safe side, not real data. Small sample, one room |
| Undock | Backs about 0.13 m and turns about 180 degrees, 5.6 s. Docked, the robot **faces** the dock: yaw -32 on the dock, 147 after undocking |
| Real wall-follow distance | One 8 s run: nearest return about 0.15 m from the lidar centre, 0.75 m moved. One short run in one room |
| Real mapping with `slam_delivery.yaml` | Map 4.10 x 4.45 m, walls closed. Distances NOT compared with a tape, so the scale is still open |
| First real Nav2 deliveries, 1.1 m route in that room, slowed near the dock | Run 1 (mission by hand, no button): outbound 18 s, waited, inbound 9 s, docked at the first try in 26 s, exit 4, 0 holds, 0 retries. Run 2 (from the menu): same, press too early (inside the 0.5 s ignore window), exit 4. Run 3 (from the menu): full delivery with presses, exit 0. The final run on the final code, from the menu: delivered, exit 0, 96 s, 0 holds, 0 retries, longest /odom gap 0.452 s, no false Nav2 reset, load average about 8.6 during the drive with the camera container stopped (it was 18 before) |
| Stack and trip timing | Stack ready 27 to 70 s after the start; from pressing `Yes` to moving about 1 min 15 s |
| Chime | Heard by Ibrahim, audible (told to us; not measured) |
| Menu on the real robot with simulated presses | Scrolling, confirm and No, Yes, whole delivery, Stop mid-route, Back to the lab, Dock, Undock, EStop on and off, Wall Follow Left (section 9, "The front-panel menu") |
| `/odom` longest gap during a run | 0.576 s in a stop test, 0.253 s in a home trip |

Bugs found by this real driving, all fixed in the code: the mission froze with the stop button dead (no limit on the goal answer, now 5 s); a false Nav2 reset at CPU load 15 (`bond_timeout` now 0, section 11); button 2 wiped the screen for up to 3 s (redraw after press and release, re-show every 0.5 s); the idle menu used 33 % of a core (polling every 0.1 s); the OAK-D container used about 100 % of a core (now stopped at stack start).

*Update 2026-11-06 to the "Still open" paragraph below.* From it, these are now verified (above): the real Create 3 dock range (partly, as measured), the real wall-follow distance (one run), whether a menu redraw hides the prompt (it is re-shown every 0.5 s; how it looks to a person is still open), and whether the chime is audible (heard by Ibrahim). The rest of the paragraph still applies.

**Still open (needs the robot, the floor or people):** the real lidar with glass and cables; the real Create 3 dock range (assumed 1.0 m in the simulator); the real size of the SLAM shrink on the real hall; the real Pi load while driving; whether a menu redraw after a button press hides the prompt (the mission re-sends it every 5 s); the real wall-follow distance of the Create 3; Controller B as emergency stop; buttons 3 and 4 on this robot; the real odometry error for AMCL; whether the chime is loud enough.

**Still NOT verified after 2026-11-06 (needs campus, people or the physical buttons):** the real campus route; the real SLAM scale on a long wall (tape comparison); lidar and glass; driving load over a long route; Wi-Fi `Students` during a run; the Controller B emergency stop in a real run; `/hazard_detection` is not republished; the feel of the PHYSICAL front-panel buttons and how the screen looks to a person; the `Power` menu entry (not pressed on purpose); `Wall Follow Right` from the menu. The 1.1 m home route proves the program flow, not campus behaviour.

Original list (2026-11-03). Each row still applies unless a dated line above says otherwise:

| Point | Where it matters |
|---|---|
| The ROS adapter in `delivery_mission.py` (`RosRobot`) has never run with ROS, rclpy or the TurtleBot4Navigator | Whole mission |
| The Nav2 feedback fields used to resume a leg after a hold (`number_of_poses_remaining`, `current_pose`) | Hold and resume |
| How long the display message stays before the menu redraws it (re-published every 5 s and after each button press) | Prompts |
| The hazard topic: the robot's `create3_republisher` does not republish `/hazard_detection` (ROADMAP TB-25 step 3), so bump, cliff and wheel-drop alarms are probably inactive. The Create 3 itself still stops on bumps and cliffs | Safety |
| The `speed_limit_topic` parameter name of the SpeedFilter (taken from the Nav2 docs, source not checked) | Slow zones |
| slam_toolbox service names and field names used by `save_map.sh` (`save_map`, `serialize_map`, `name.data`, `filename`) | Saving the map |
| The `pgrep` patterns in `stop_stack.sh` and the `pkill` patterns of the soak script find the right processes | Stopping |
| Whether the launches shut down cleanly on SIGINT (the python wrapper restores default SIGINT handling) | `stop_stack.sh` |
| Create 3 wall-follow near glass doors and the glass room; whether 10 s presses of R2/L2 behave as in the source | Phase 1 |
| Controller B as the Create 3 emergency stop on this robot | Safety |
| Pi CPU and temperature with slam_toolbox or Nav2 plus the two filters (*2026-11-06: simulator numbers above; real base NOT VERIFIED; the soak test of section 5 B measures it*) | Phase 0 B |
| MPPI lane tracking quality with the soft lane mask at 0.20 m/s (*2026-11-06: MPPI was replaced by Regulated Pure Pursuit; the same question now applies to the new controller on the real floor, NOT VERIFIED*) | Phase 2 |
| The robot's installed `turtlebot4.yaml` matches upstream (buttons 3 and 4 only scroll; controller mapping) | Phase 0 A6 |
| Nav2 dock and undock timing, audio notes, and whether a brief `/odom` pause while Nav2 drives is harmless (the mission waits 2 s) | Phase 2 |
| macOS and Linux forms of the `fe80::` login and `scp` | Section 4 |
| Offline SLAM on a computer (needs ROS 2 Jazzy) | Fallback |

When you verify an item, add a dated update here and in MAINTENANCE.md; do not delete the old text.

---

## 14. How the checks fit together

From the cheapest, which needs only your computer, to the most expensive, which needs people and the robot. Each step finds a different kind of mistake, and a pass at one step says nothing about the next.

| Step | Where it runs | Command | What it finds | Moves the robot? |
|---|---|---|---|---|
| 1 Offline checks | Your computer, any OS | `python TurtleBot/delivery/tools/verify_all.py` (add `--strict` to count a missing linter as a failure, `--skip-tests` for lint and syntax only, `-v` for all output) | Lint (ruff, yamllint, shellcheck, when installed; a missing tool gives SKIP with the install command), syntax of every script, the link check, and all offline tests (section 12). Changes no file | No |
| 2 Deploy | Your computer to the robot | `python TurtleBot/delivery/tools/deploy.py deploy` (section 4) | A broken copy (checksum) or a script with a syntax error, before it goes live. Rollback is one command | No |
| 3 Parameter check | The robot | `export ROS_DOMAIN_ID=77` and then `python3 ~/robot_code/delivery/sim/ci_check_params.py` (it refuses domain 0; ROS must be set up with `source /etc/turtlebot4/setup.bash`) | The mask files load as expected and every Nav2 server accepts its parameters | No |
| 4 Simulator, delivery | The robot, on the dock | `bash ~/robot_code/delivery/sim/run_e2e.sh <scenario>` (`happy`, `pickup_timeout`, `stall`, `nav_fail`, `dock_retry`) | Configuration, timing and interface mistakes of the real Nav2, AMCL, filters and mission against a fake base. PASS or FAIL with numbers | No (fake base in ROS domain 77) |
| 5 Simulator, mapping | The robot, on the dock | `bash ~/robot_code/delivery/sim/run_mapping.sh` | The real slam_toolbox, `save_map.sh`, planning on a SLAM map, and a delivery on that map; includes the map checks (straightness, position, tilt, ghost wall, glass room position) | No |
| 6 Soak test | The robot, on the dock | `phase0/p0_soak.sh` (section 5 B) | Whether the base stays steady (no `/odom` gap over 0.3 s) with the delivery stack running for 70 minutes, and the Pi load | No |
| 7 Real mapping, then supervised runs | The route, with people | Sections 6, 9 and 10 | Everything the simulator cannot show: the real lidar, glass, floor, wall-follow, dock range | Yes, supervised |

The simulator's rules are in [sim/README.md](sim/README.md): it refuses to start in ROS domain 0 (the real robot's domain), while a mission or stack runs, or while `~/STOP` exists. Results of the runs so far are in [sim/README.md](sim/README.md#results-2026-11-06). Steps 4 and 5 were run on the robot on 2026-11-05 and 2026-11-06; step 6 on the final code and the supervised runs are not done (see the status and the open list in section 13).
