# Robot menu

How to change the robot's front-panel menu (the entries on its small screen) from Studio, with the **Robot menu** screen added in Studio 2.1.

Guides: [First connection](FIRST-CONNECTION.md) | [Everyday use](EVERYDAY-USE.md) | [Live view and driving](LIVE-AND-DRIVING.md) | [Maps and routes](MAPS-AND-ROUTES.md) | [Robot menu](ROBOT-MENU.md) | [Find the robot](FIND-THE-ROBOT.md) | [Troubleshooting](TROUBLESHOOTING.md)

> Status (2026-11-12): **NOT VERIFIED on the real robot.** The page was tested offline, in the simulated robot and with automated browser tests. The menu checker and the menu file support of the delivery package are also not deployed on the robot yet. The format and the rules are in the [delivery README, "Your own menu entries"](../../../delivery/README.md#your-own-menu-entries-added-2026-11-12).

## What the page does

The robot's menu is a list on its screen that you move through with the four buttons. The list comes from a file on the robot, `~/robot_code/menu/menu.yaml`. This page edits that file for you, so you do not write YAML by hand. You can:

- hide some of the robot's own entries,
- add entries of your own that start a program on the robot,
- see what the screen will show,
- ask the robot to check the menu, and save it to the robot.

Nothing moves when you save. The robot only reads the new menu.

The robot's own checker is the single judge of what is valid. Studio sends the menu to the robot to be checked and refuses to save a menu the robot does not accept.

## Open the page

1. Connect Studio to the robot.
2. Open **Robot menu** in the left menu. Studio reads the file from the robot.
3. If the robot has no menu file, the page says "The robot shows the standard menu." If the file on the robot is not valid, the page lists the problems the robot found and offers **Start from the standard menu**.

## The robot's own entries

The panel **The robot's own entries** lists them in the robot's order: Go to food court (it reads Back to the lab when the robot is away from the dock), Dock, Undock, EStop, Wall Follow Left, Wall Follow Right, Power, Help.

- Entries marked **Locked** cannot be changed: the trip entry, Dock, EStop and Power. They are always there, in this place, with this name. This is a safety rule.
- The others (Undock, Wall Follow Left, Wall Follow Right, Help) have a box **Show on the robot**. Clear it to hide the entry. Hidden entries are listed under "Hidden" in the preview.

## Add an entry of your own

In **Your own entries** press **Add entry**. You can have at most 8. To change one press **Edit**. To delete one press **Remove** (the program file on the robot is not deleted).

| Field | What to enter |
|---|---|
| Name on the display | The text on the robot's screen. At most 17 characters (the screen holds 18 and the first is the cursor). It must not repeat another entry or a built-in name. A counter shows how many characters you have used |
| Id | A short code: letters a-z, digits and underscore, starting with a letter. Each entry needs a different one. Other entries use it in **Place after** |
| Program | A `.py` (run with python3) or `.sh` (run with bash) file on the robot. Write it as `~/robot_code/...` or relative to `~/robot_code`. It must stay under `~/robot_code` |
| Arguments | Extra values for the program, one per line. They are passed exactly as written, with no shell |
| Ask before starting | The screen asks "1 = Yes / 2 = No" first |
| Moves the robot | Tick this if the program drives the robot. Such a program always asks first, so **Ask before starting** stays on. It is refused while the robot is docked |
| Undocks by itself | Tick this if the program undocks the robot itself (it then also counts as moving). It is then allowed to start while docked |
| Time limit in seconds | The program is stopped when the time is up. The default is 300 |
| Place after | The entry goes right below the one you choose. A hidden built-in entry still marks the place. Nothing can go above the trip entry |

Put the program on the robot first. Studio does not copy it here (use **Files** or **Programs**). A program that moves the robot is your responsibility: keep a person next to the robot and the controller ready.

## Check with the robot

Press **Check with the robot**. Studio sends the menu to the robot's checker without changing the saved file. The preview then says "Checked by the robot" and **The robot accepts this menu**, or **The robot does not accept this menu** with a list under "Problems the robot found". Notes from the robot (warnings) are listed too. Fix the problems and check again. If you change the menu after a check, the page says it must be checked again.

**Show the file** under the buttons shows the exact text Studio will write. It is read only.

## Save to the robot

1. Press **Save to the robot**. It is grey until the robot has accepted the menu you see. The reason is written next to it ("Fix the problems above first.", "The robot has no menu checker yet.").
2. Confirm. The dialog says the robot keeps the old file as `menu.yaml.bak` and shows the new menu the next time it returns to the top menu.
3. The robot writes the new file under a temporary name and renames it, so the menu never reads half a file. The old file stays as `menu.yaml.bak` in `~/robot_code/menu/`. To go back, copy the `.bak` over `menu.yaml`, or use **Start from the standard menu** and save.

The robot does not restart. It looks at the file each time its menu returns to the top (after a message, a result, Back, a finished program, or after it was idle). While a program or a trip is running it does not read the file. **Reload from the robot** brings back the saved menu and drops your unsaved changes (it asks first).

## What happens when an entry starts

The panel **What happens when an entry starts** on the page shows it. In short:

1. Select. The robot refuses with a note when the stop file exists, a delivery is running, the program is missing or outside `~/robot_code`, or a moving program is chosen while docked (unless it undocks itself).
2. If the entry asks first or moves the robot, the screen asks "1 = Yes / 2 = No". A moving program also shows "Robot will move".
3. The program runs on its own. The screen shows its name and "2 = Stop". Button 2 stops it politely first and forcefully if it keeps running. The same happens at the time limit.
4. The result screen says Finished, Failed, Stopped or Timed out, with the exit code. Any button returns to the menu, and it returns by itself after 30 seconds.

## "The robot does not have the menu checker yet"

The page shows this notice when the robot has no `menu_config.py`. Studio then refuses to save a menu. This is by design: Studio never saves a menu that the robot could not check. Fix it by copying the delivery package to the robot with `delivery/tools/deploy.py` ([delivery README, section 4](../../../delivery/README.md#4-connecting-and-copying-the-folder-to-the-robot)), then press **Reload from the robot**.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Could not read the menu from the robot" | Check the connection ([Troubleshooting](TROUBLESHOOTING.md)) and open the page again |
| The robot's menu file is not valid | Read the problems listed, or press **Start from the standard menu** and build the menu again |
| The check says a program is not allowed | The program must be a `.py` or `.sh` file under `~/robot_code` |
| The robot still shows the old menu after saving | Return to the top menu on the robot (button 2, Back). The new file is read then |

Everything on this page is **NOT VERIFIED** on the real robot. After you try it, tell the lab maintainer what you saw.
