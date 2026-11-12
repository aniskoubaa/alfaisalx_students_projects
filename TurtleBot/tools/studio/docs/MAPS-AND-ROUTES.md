# Maps and routes

How to map a place from Studio, look after the saved maps, and put a planned route on the robot. These are the **Maps** and **Routes** screens added in Studio 2.1.

Guides: [First connection](FIRST-CONNECTION.md) | [Everyday use](EVERYDAY-USE.md) | [Live view and driving](LIVE-AND-DRIVING.md) | [Maps and routes](MAPS-AND-ROUTES.md) | [Robot menu](ROBOT-MENU.md) | [Find the robot](FIND-THE-ROBOT.md) | [Troubleshooting](TROUBLESHOOTING.md)

> Status (2026-11-12): **Studio 2.1 has not been tried on the real robot yet (NOT VERIFIED).** It was tested offline, in the simulated robot (`--fake`) and with automated browser tests. Everything below describes what the screens do and what the design expects of the robot. Until a person has run it on the real robot, stay next to the robot and be ready to press **E-STOP**. The open checks are in the README under [Not verified yet](../README.md#studio-21-added-2026-11-12). The design is in [DESIGN-MAPPING.md](DESIGN-MAPPING.md).

## Safety

1. A person stays next to the robot the whole time it is mapping, with the controller in hand.
2. The **E-STOP** button is at the top right of every screen. **Esc** or **Space** does the same (not while you type in a text box).
3. Driving is switched off by Studio while mapping starts, while a map is being saved and while mapping stops. Starting a new robot program can stall the robot's wheels for several seconds, so Studio does not let you drive then. Wait for the state to say **Mapping** again.
4. Leaving the **Maps** screen switches driving off.
5. Nothing on the Maps or Routes screens moves the robot by itself. Studio never undocks or docks the robot for you here. You do that on **Overview** or with the controller.
6. Read the [safety checklist](../../../examples/README.md#safety-checklist-before-anything-moves) before the robot moves.

## What you need

- Studio connected to the robot ([Everyday use](EVERYDAY-USE.md)).
- The delivery package on the robot. It holds the scripts that Studio runs for mapping. It is copied with `delivery/tools/deploy.py` (see [delivery README, section 4](../../../delivery/README.md#4-connecting-and-copying-the-folder-to-the-robot)). Without it the Maps screen says the mapping scripts are missing.
- A battery that is not low, and the robot docked to begin with.

## Map a place from Studio

The procedure is the one in the [delivery README, section 6](../../../delivery/README.md#6-phase-1-map-the-route-by-wall-following). Studio runs the same scripts, so you do not need a terminal on the robot.

1. Open Studio and press **Connect** (see [Everyday use](EVERYDAY-USE.md)).
2. Open **Maps** in the left menu. At the top of the map you see the state and four buttons: **Start mapping**, **Save map**, **Stop mapping** and **Clear error**. Only the buttons that make sense in the current state are enabled. Point at a grey button to read why it is off.
3. Press **Start mapping**. The state changes as follows:

   | State on screen | What it means | What you do |
   |---|---|---|
   | Not mapping | Nothing is running | Press **Start mapping** |
   | Starting mapping… | The robot is starting the mapping program. Driving is off | Wait. It takes a while |
   | Mapping | The map is being built. The grid grows on the screen | Drive and save |
   | Saving the map… | The map is being written on the robot. Driving is off | Wait |
   | Stopping… | The mapping program is shutting down. Driving is off | Wait |
   | Error | Something failed. The message after "Last error" says what | Read the message, then **Clear error** or **Stop mapping** |

   **Start mapping** stays grey when a navigation program is running on the robot ("A navigation program is running ... Stop it first") or when the scripts are missing.
4. Wait for **Mapping**.
5. Undock the robot: open **Overview**, press **Undock** and confirm. Check that the robot is clear of the dock. Then return to **Maps**. (Driving is not possible while docked.)
6. Drive. Two ways:
   - The drive panel next to the map. Arm it with the confirmation, then use the stick or the W/A/S/D and arrow keys. The rules are the same as on **Live**: see [Live view and driving](LIVE-AND-DRIVING.md).
   - The robot's controller. For a long wall: **R2** follows the wall on the right, **L2** on the left. Each press runs for only about 10 seconds, so press again about every 10 seconds while you walk behind the robot. [to verify on this robot, see the delivery README]
7. Watch the map. The blue disc is the robot, the orange dots are what the lidar sees now. Black cells are walls and obstacles, white cells are free space, grey is not mapped yet. Zoom with the buttons or the mouse wheel. **Following robot** keeps the robot in the centre. **Free view** leaves the map where you put it.
8. Mapping advice, in short (details in the delivery README, section 6):
   - **Glass.** The lidar does not see glass, so the robot may turn into a glass room or hit a glass door. Press **E-STOP** before it does. Then drive across the opening by hand, keeping at least 0.6 m from the wall, and carry on.
   - **Close the loop.** Drive back along the same wall to where you started, so the mapping program sees the start again. This makes the map more accurate.
   - Drive slowly. A person who walks through the map leaves marks on it.
9. Press **Save map**. Type a name (letters, digits, hyphens and underscores, up to 48 characters, no spaces; Studio suggests one with the date and time) and press **Save map** in the dialog. The state shows **Saving the map…** and then **Mapping** again. The line "Last saved map" shows the name. If the name exists, Studio asks "Replace the map?" Choose **Replace map** only when you mean to overwrite.
10. Dock the robot (**Overview**, **Dock**, or the controller).
11. Press **Stop mapping**. If the map is not saved, Studio asks "This map is not saved. Stop and lose it?" Choose **Keep mapping** and save first, unless you really want to throw it away. The state shows **Stopping…** and then **Not mapping**.

You can save several times in one session, with different names, for example before and after a risky stretch.

## Manage saved maps

Under the map, the **Saved maps** table lists every map on the robot, newest first. **Refresh** reads the list again.

| What | How |
|---|---|
| Preview | Click the map's name. A picture of the saved map appears |
| Rename | **Rename** in the row, type the new name, confirm. An existing name is refused |
| Download | **Download** in the row. Your browser saves a zip with the map's files (image, settings, graph and data) |
| Delete | **Delete** in the row. A red dialog says the files will be removed from the robot and that this cannot be undone. Download the map first if you may need it again |

A map is four files on the robot: the image (`.pgm`), the settings (`.yaml`), and the graph and data files (`.posegraph`, `.data`). Keep all four together. The last two let a later session continue the same map. The **Files** column shows if one is missing.

## Check the map scale against one measured distance

Do this before you plan a route on a map. The mapping program can shrink the map along a long plain wall.

1. Measure one known distance on the floor with a tape or a measuring wheel, for example from the dock to the far end of a room.
2. Measure the same two points on the map (download the map and use an image editor, and the resolution in the `.yaml` file).
3. If the map is more than about 3 % shorter than the floor, do not plan on it. Map again.

The full steps are in the [delivery README, section 6, step 7](../../../delivery/README.md#6-phase-1-map-the-route-by-wall-following). Whether the real campus map keeps its scale is **NOT VERIFIED**.

## Plan a route on a computer

Studio does not plan routes. You make the route folder on your computer with `delivery/tools/plan_route.py`, from the saved map: see [delivery README, section 8](../../../delivery/README.md#8-plan-the-route-on-your-computer). Clean the map first if needed (section 7 there). The result is a folder with the four files the robot needs: `route.yaml`, `map.yaml`, `keepout_mask.yaml` and `speed_mask.yaml` (plus the pictures and `preview.html`). Open `preview.html` and check the plan before you go on.

## Put a route on the robot

1. Open **Routes** in the left menu.
2. In **Upload a route**, press **Choose a route folder** and pick the planned folder. Studio says how many files it found and whether all four route files are there. Files inside subfolders are ignored. The files must be under 32 MB together.
3. Check the name in **Name on the robot** (letters, digits, hyphens and underscores). Studio suggests one from the folder name. The name must be new: an existing name is refused, so choose another.
4. Press **Upload**. Nothing moves. The route appears in **Routes on the robot**. The status says **Ready** or "Incomplete: missing ...".

## Change the current route

The front-panel menu and the next trip use the route that **current** points to. The line "Current route" shows it.

1. In the table, press **Use this route** in the row of the route you want. It is grey when the route is incomplete, already current, or when a trip or the navigation program is running ("A trip is running. Wait until it has finished.").
2. A dialog names the old and the new route and says nothing moves now. Press **Use this route** to confirm.
3. Check that the line "Current route" shows the new name.

## Read the trip status

**Trip status** (on the Routes screen, refreshed every 5 seconds) shows three lines: whether the front-panel menu is running, whether a trip is running, and whether the navigation program is running. Below them are the last lines of the robot's menu log. It is read only.

**Trips are started from the robot's front panel (its screen and buttons), not from Studio.** See the [delivery README, section 9](../../../delivery/README.md#the-front-panel-menu-added-2026-11-06).

## If something goes wrong

| What you see | What to do |
|---|---|
| State **Error** and a "Last error" line | Read the text. Press **Clear error**: Studio asks the robot what is really running and shows **Mapping** or **Not mapping**. If the mapping program is still running and you want to end it, press **Stop mapping** |
| The map does not grow | The lidar motor is normally off while the robot is docked. Undock the robot, or start the lidar on **Overview**. Then drive a little |
| The save says the name exists | Choose another name, or accept "Replace map" if you want to overwrite |
| "The mapping scripts are missing on the robot" | The delivery package is not on the robot. Copy it with `delivery/tools/deploy.py` ([delivery README, section 4](../../../delivery/README.md#4-connecting-and-copying-the-folder-to-the-robot)), then reconnect |
| **Start mapping** is grey and names a navigation program | A navigation stack is running. Stop it (delivery README, section 9) and try again |
| Driving is grey on Maps | The robot is starting, saving or stopping mapping, or the connection is down. Wait |
| Upload says a file is missing | The folder must hold `route.yaml`, `map.yaml`, `keepout_mask.yaml` and `speed_mask.yaml` directly, not in a subfolder. Run the planner again |
| Anything else | [Troubleshooting](TROUBLESHOOTING.md), or ask the lab maintainer |
