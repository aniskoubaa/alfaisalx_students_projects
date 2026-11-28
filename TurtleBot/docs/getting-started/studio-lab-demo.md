# TurtleBot Studio 2.1: quick guide for a lab demo

A short path from "I have a laptop" to "the robot ran the delivery demo from its front panel". It takes the steps in order and points to the detailed guides for depth.

Interactive version with a progress checklist, a screen tour and a symptom finder: [studio-lab-demo.html](studio-lab-demo.html) (open it from your downloaded copy of the repository; GitHub does not render HTML pages).

Detailed guides: [Download](../../Download/README.md) | [First connection](../../tools/studio/docs/FIRST-CONNECTION.md) | [Everyday use](../../tools/studio/docs/EVERYDAY-USE.md) | [Live view and driving](../../tools/studio/docs/LIVE-AND-DRIVING.md) | [Maps and routes](../../tools/studio/docs/MAPS-AND-ROUTES.md) | [Robot menu](../../tools/studio/docs/ROBOT-MENU.md) | [Troubleshooting](../../tools/studio/docs/TROUBLESHOOTING.md) | [Delivery README](../../delivery/README.md) | [How to connect](../../HOW-TO-CONNECT.md)

> Status (2026-11-25): written from the repository docs and a lab check on 2026-11-25. Each step says what was verified on the real robot and what was not. In short: connecting over campus Wi-Fi and the front-panel menu were checked; mapping while driving, route upload, a trip in the lab and the campus were **not** done yet. See [What is verified](#what-is-verified-and-what-is-not).

## Safety rules (read first)

1. **Unplug the Ethernet cable before the robot moves.** The robot must never drive with the cable plugged in.
2. A person stands next to the robot for the whole time it moves, with the **E-STOP** within reach. In Studio the E-STOP is at the top right of every screen. **Esc** or **Space** does the same (not while you type in a text box).
3. Clear about 1 m of floor around the robot. Go through the [safety checklist](../../examples/README.md#safety-checklist-before-anything-moves) before anything moves.
4. Glass is invisible to the lidar. Keep the robot away from glass doors and glass rooms, and press E-STOP before it reaches one.
5. Battery above 40 % for a trip (the route's start limit). Studio refuses to drive below 10 %.
6. Stay clear of lunch hours when you map or run a trip in the corridor.

## 1. Install Studio

1. Download the installer: [Download page](../../Download/README.md), or directly from GitHub: <https://github.com/aniskoubaa/alfaisalx_students_projects/raw/main/TurtleBot/Download/TurtleBotStudio-Setup-2.1.1.exe> (Windows 10 and 11, 8.9 MB, no administrator rights).
2. Open the file. Windows may say "Windows protected your PC" because the app is not signed by a company. Click **More info**, then **Run anyway**.
3. Click **Next**, **Install**, **Finish**. Studio opens. You get a desktop shortcut and Start menu entries: **TurtleBot Studio**, and **TurtleBot Studio (simulated robot)**, a practice copy with a pretend robot where nothing real moves.

macOS and Linux: there is no ready-made file yet. Use the Python version, [INSTALL.md option B](../../tools/studio/INSTALL.md#option-b-run-it-with-python).

Not verified: the 2.1 installer on a clean computer.

## 2. Connect over campus Wi-Fi

1. Switch the robot on. It joins the campus Wi-Fi **Students** by itself and shows its address on its screen (it starts with `10.87.`). The address comes from DHCP and can change, so read it from the screen each time. Example from 2026-11-25: `10.87.11.67`.
2. Put your laptop on the **same network** (Students).
3. Start Studio. On **Overview** press **Discover**, pick the robot, press **Connect**. If it is not listed, type the address from the robot's screen. More help: [Find the robot](../../tools/studio/docs/FIND-THE-ROBOT.md). The name `turtlebot4.local` sometimes fails on campus; use the address.
4. First time on a computer: Studio needs a login key for that computer. Follow the setup wizard once, as written in [First connection](../../tools/studio/docs/FIRST-CONNECTION.md). It uses the Ethernet cable for the one-time setup and asks for the robot's password in a terminal window. For the password, see [How to connect](../../HOW-TO-CONNECT.md) or ask the lab maintainer. Then unplug the cable.

Verified 2026-11-25: the robot joined Students at boot, and a laptop on the same network reached it by Wi-Fi with no cable. Not verified: the one-time key setup over Wi-Fi without the cable (the guide uses the cable).

## 3. Tour of Studio's screens

The menu is on the left. The top bar shows the connection, battery, Wi-Fi signal and the E-STOP. Screenshots in the guides come from the simulated robot, for example the [Overview screen](../../tools/studio/docs/img/v2-overview.png).

| Screen | What it shows | Use it to |
|---|---|---|
| Overview | Battery, docked or not, lidar, Wi-Fi, CPU, temperature | Connect, **Undock**, **Dock**, start the lidar motor, run the health check |
| Live | Lidar map, the robot's path | Drive by hand (arm first; 0.15 m/s default, 0.30 m/s max, stops 0.3 s after the last command) |
| Maps | A map being built; saved maps | **Start mapping**, **Save map**, **Stop mapping**; preview, rename, download, delete maps |
| Routes | Routes on the robot, the current route, trip status | Upload a planned route folder, **Use this route** |
| Robot menu | The entries on the robot's front panel | Hide built-in entries, add your own program entries, check and save |
| Programs | The lab's example programs | Run one and read its live log |
| Code | An editor | Write and run your own program on the robot |
| Files | Folders on your computer and the robot | Copy files to the robot and back |
| Charts | Battery, speed, CPU, temperature, Wi-Fi over 5 to 30 minutes | See trends |
| Logs | The robot's service log (read only) | Look for errors |
| Wi-Fi | Where the computer and the robot are connected | Put the robot on another network |
| Topics | ROS topics | Watch up to four live |
| Tools | Terminal on the robot, setup wizard, diagnostics, Settings | Open a terminal on the robot, copy diagnostics |

Studio refuses to drive when the robot is docked, under e-stop, while a motion program runs, or with the battery below 10 %. Details: [Everyday use](../../tools/studio/docs/EVERYDAY-USE.md#3-the-layout), [Live view and driving](../../tools/studio/docs/LIVE-AND-DRIVING.md).

## 4. Map a room

Detail: [Maps and routes](../../tools/studio/docs/MAPS-AND-ROUTES.md#map-a-place-from-studio) and [delivery README section 6](../../delivery/README.md#6-phase-1-map-the-route-by-wall-following).

Needs: Studio connected; the delivery package on the robot (it is there; it is copied with `delivery/tools/deploy.py`); the robot docked at the start; no navigation program running (otherwise **Start mapping** is grey).

1. Open **Maps**. Press **Start mapping**. Wait for the state **Mapping** (6 to 10 s on 2026-11-14).
2. Undock: open **Overview**, press **Undock**, confirm. Check the robot is clear of the dock. Go back to **Maps**.
3. Drive slowly with the drive panel (arm it first), or with the robot's controller. Keep the cable unplugged and a person beside the robot.
4. Close the loop: drive back along the same wall to where you started. This makes the map more accurate.
5. Press **Save map**, type a name (letters, digits, hyphens, underscores, no spaces), confirm. It takes about 18 s.
6. Dock the robot (**Overview**, **Dock**, or the controller).
7. Press **Stop mapping** and answer the question (keep mapping if the map is not saved yet).

Starting mapping stops the robot's camera container until the next reboot. This is a known side effect.

Verified on the real robot 2026-11-14 (robot docked, not driven): start, live map, save, stop, preview, download, rename, delete. **Not verified: mapping while driving.** Check the map scale against one measured distance before you plan a route on it: if the map is more than about 3 % shorter than the floor, map again.

## 5. Plan a route on the computer

Studio does not plan routes. You do it on your computer with `TurtleBot/delivery/tools/plan_route.py`. Detail: [delivery README section 8](../../delivery/README.md#8-plan-the-route-on-your-computer).

1. In **Maps**, download your saved map (a zip). Unzip it.
2. You need Python 3.10 or newer and PyYAML: `python -m pip install pyyaml` (use `python3` on macOS and Linux).
3. From the repository root, read the map's size and origin:

   ```
   python TurtleBot/delivery/tools/plan_route.py --map <your-map>.yaml --info
   ```

4. Copy [route_spec.example.yaml](../../delivery/tools/route_spec.example.yaml), replace the made-up numbers (dock pose, goal, glass keep-out lines), then run:

   ```
   python TurtleBot/delivery/tools/plan_route.py --map <your-map>.yaml --spec my_spec.yaml --out my_route
   ```

5. Open `my_route/preview.html` in a browser and read every warning. The folder must hold `route.yaml`, `map.yaml`, `keepout_mask.yaml` and `speed_mask.yaml`.

Not verified: this flow with a map made by driving in the lab.

## 6. Put the route on the robot

1. Open **Routes**. In **Upload a route** press **Choose a route folder** and pick the folder from step 5.
2. Check **Name on the robot** (letters, digits, hyphens, underscores; it must be new; `current` is reserved). Press **Upload**. Nothing moves.
3. In **Routes on the robot**, press **Use this route** in the row of your route and confirm. The line **Current route** must show your route.

Important: the current route on the robot is `home`, a 1.1 m test route made in a room at home. Change it to your lab route before any trip in the lab, or the robot will try to drive the home route. `Use this route` is refused while a trip or the navigation program runs.

Not verified: route upload, and **Use this route** with a route other than the one already current.

## 7. Start the navigation program (not done by Studio)

A trip needs the navigation stack (Nav2 with the map and masks) running on the robot first. **Studio 2.1 cannot start it.** Studio can start mapping, and its **Routes** screen shows whether the navigation program is running (Trip status), but you start navigation from a terminal on the robot, as in [delivery README section 9](../../delivery/README.md#9-phase-2-supervised-runs).

1. The robot must be **on the dock**, battery above 40 %.
2. Open a terminal on the robot: in Studio open **Tools** and use the button that opens a terminal on the robot. Or, from a terminal on your computer, `ssh ubuntu@<address on the robot's screen>`; this needs the key from the first connection or the robot's password (see [How to connect](../../HOW-TO-CONNECT.md)).
3. On the robot, check first, then start (replace `my_route` with the name you uploaded):

   ```bash
   bash ~/robot_code/delivery/robot/start_stack.sh nav --route-dir ~/robot_code/routes/my_route --dry-run
   bash ~/robot_code/delivery/robot/start_stack.sh nav --route-dir ~/robot_code/routes/my_route
   ```

4. Wait about 2 minutes, then check it is up:

   ```bash
   grep -i "Managed nodes are active" ~/robot_code/logs/delivery/latest/stack.log | tail
   ```

   If the line does not appear, run `bash ~/robot_code/delivery/robot/stop_stack.sh` and read the log.

5. When you are finished, stop it: `bash ~/robot_code/delivery/robot/stop_stack.sh`.

Whether a stack started from a terminal keeps running if you close that terminal: [to verify]. Keep the terminal open during the demo.

## 8. Run the delivery demo from the robot's front panel

Do this with the cable unplugged, the robot on the dock, the navigation program running (step 7), and a person ready to walk behind the robot with the E-STOP or controller at hand.

| Button | In the menu |
|---|---|
| 1 | Select the highlighted entry |
| 2 | Back. While a trip runs it is **Stop** |
| 3 | Up |
| 4 | Down |

1. On the robot's screen the first entry is `>Go to food court` when the robot is docked. The list also has Dock, Undock, EStop, Wall Follow Left, Wall Follow Right, Power and Help. The `Hello demo` entry (a 20 s countdown that never moves) is also in the list.
2. Select **Go to food court** (button 1). Answer `1 = Yes / 2 = No` with button 1. The first movement comes about 1 min 15 s later (measured at home, 2026-11-06).
3. The screen shows the status and `2 = Stop`. Walk behind the robot. Press button 2 at any time to stop.
4. At the food court the screen asks `Food placed?`. Press button 1 for **Back to the lab**.
5. At the lab it shows `Your food is here`. Press button 1 for **Done, thank you**. The robot docks.
6. If the screen says `Not on the map`, the navigation program is not running. If it says `No route saved`, the current route folder has no `route.yaml`.

Verified at home (2026-11-06, a 1.1 m route): a whole delivery, Stop, Back to the lab, and the physical buttons. The menu service was active at boot on 2026-11-25. **Not verified: a trip on a lab or campus route.** Selecting `Hello demo` on the screen is also not tested yet.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Windows protected your PC" | **More info**, then **Run anyway** |
| Discover finds nothing | Check both are on Students. Type the address from the robot's screen |
| `turtlebot4.local` fails | Use the address from the screen |
| "key not set up" | Run the setup wizard once ([First connection](../../tools/studio/docs/FIRST-CONNECTION.md)) |
| The robot offers its own Wi-Fi `Turtlebot4` | It could not find Students. Join `Turtlebot4` from your computer; the robot is at `10.42.0.1` |
| **Start mapping** is grey | A navigation program is running, or the mapping scripts are missing. Stop it with `stop_stack.sh`, or copy the delivery package with `deploy.py` |
| Driving is grey | The robot is docked, e-stopped, starting or saving a map, or the battery is under 10 %. Undock first on **Overview** |
| The map does not grow | The lidar motor is off while docked. Undock or start the lidar on **Overview**, then drive a little |
| Upload says a file is missing | The route folder needs the four files directly inside it, not in a subfolder. Run the planner again |
| **Use this route** is grey | The route is incomplete, already current, or a trip or navigation program is running |
| Screen says `Not on the map` | Start the navigation program (step 7) and wait about 2 minutes |
| Screen says `No route saved` | Make your route current (step 6) |
| Anything else | [Troubleshooting](../../tools/studio/docs/TROUBLESHOOTING.md), or ask the lab maintainer |

## What is verified and what is not

Verified on the real robot:

- 2026-11-25: robot joins Students by itself, laptop on Students reaches it by Wi-Fi, the robot has internet, the front-panel menu service runs after boot, the robot runs delivery release `20261114T124530Z-7388942`.
- 2026-11-14 (docked, not driven): Studio 2.1 start mapping, live map, save, stop, preview, download, rename, delete; **Use this route** with the route already current.
- 2026-11-06 (home, 1.1 m route): a whole delivery from the front panel, Stop, Back to the lab, physical buttons.

Not verified yet:

- Mapping while driving from Studio, in the lab or on campus.
- Route upload from Studio, and **Use this route** with a different route.
- A trip in the lab or on campus. Map scale on long walls and localization on campus.
- Selecting `Hello demo` on the screen.
- The 2.1 installer on a clean computer, and macOS and Linux.
- Starting the navigation program from Studio: not possible in 2.1, only from a terminal on the robot.

Sources: [Studio README, "Tested on the robot 2026-11-14 (2.1)"](../../tools/studio/README.md#tested-on-the-robot-2026-11-14-21), [delivery README section 13](../../delivery/README.md#13-not-verified-yet).
