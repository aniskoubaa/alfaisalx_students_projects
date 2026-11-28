# Studio 2.2: easier to use, easier to read

Status: design, 2026-11-28. Builds on Studio 2.1.1.

## Why

Ibrahim found Studio hard to use, even though the features he needed already existed. He could change the robot's
menu, write his own program and run shapes, but he could not find his way to them. When `motion_shapes.py` failed
on 2026-11-26, the cause was an empty arguments box, and nothing on screen said so (fixed in 2.1.1). He also wants
the code to be simple to read, and the architecture written down with diagrams.

## What the review found

The interface was reviewed with the simulated robot (`studio.py --fake`) against
[Nielsen's ten usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/). Each finding names
the heuristic it breaks.

| # | Finding | Heuristic |
|---|---|---|
| F1 | After connecting, Overview is a wall of numbers (odometry rate, memory, throttling). Nothing says what you can do next. | Recognition rather than recall; aesthetic and minimalist design |
| F2 | The sidebar is 13 items in unlabelled groups, with jargon: Live, Topics, Tools, Charts. | Match between system and the real world |
| F3 | Programs and Code are two screens over the same robot folder. Programs' empty state says "make one in the Code screen" but has no button; a program card cannot open its code. | Recognition rather than recall; user control |
| F4 | Before connecting there are four ways in (Connect, Discover, Setup wizard, Search the whole network) and no hint which to use. | Help users recognise, diagnose and recover; minimalist design |
| F5 | Code screen: the arguments box suggests `--turns 1` for every program, even for programs with no `--turns` option. Save and run on an unchanged file says "No changes to save" although it does run. The output is below the fold. | Visibility of system status; error prevention |
| F6 | New program: after Create succeeds, the dialog briefly shows "already exists on the robot, replace it?" before it closes. | Visibility of system status; consistency |
| F7 | Top bar icons (command list, side panel, own window) have no visible label. | Recognition rather than recall |
| F8 | A moving program can be confirmed while the robot sits on its dock; the dialog does not say it must undock first. | Error prevention |

## What changes in the interface

1. **Home: "What do you want to do?"** (F1). The Overview screen becomes Home. Once connected, it opens with
   six large task buttons, each with one line of explanation:
   - Drive the robot
   - Run a program
   - Write your own program
   - Make a map
   - Change the robot's menu
   - Copy a folder to the robot

   If the robot is docked, a line above the buttons says so, with an Undock button. The detailed status cards
   stay below, under a heading "Robot status".
2. **Sidebar in labelled groups, in plain words** (F2):
   - **Use the robot:** Home, Drive, Programs, Maps, Routes
   - **Make your own:** Code, Robot menu, Files
   - **Check on it:** Charts, Logs, Topics
   - **Set up:** Wi-Fi, Settings and help

   Paths do not change (`#/live` stays `#/live`), so old links and tests keep working. Only the labels change:
   Live becomes Drive, Overview becomes Home, Tools becomes Settings and help.
3. **Programs and Code link to each other** (F3). Every program card gets an "Edit code" button that opens the
   file in Code. The Programs empty state gets "New program" and "Copy a folder" buttons. A "Run" button next to
   each file in Code's list goes to the same run flow as Programs.
4. **One obvious way to connect** (F4). Before connecting, one primary button: **Connect** if an address is
   known, otherwise **Find my robot** (Discover). Setup wizard and Search the whole network move under "Other
   ways to connect".
5. **Code screen tells the truth** (F5). The arguments placeholder shows the selected program's own example,
   from the catalog or the "Run it on the robot:" line of its docstring, and otherwise says "Optional". Save and
   run on an unchanged file says "Running <name>". After a run starts, the output panel scrolls into view.
6. **New program closes cleanly** (F6). The "already exists" warning is not shown once Create has succeeded.
7. **Labelled top bar** (F7). Every icon button has a tooltip and an accessible name.
8. **Docked warning** (F8). The movement confirmation says "The robot is on its dock. Undock it first" and
   offers Undock, when the dock status says docked.

## What changes in the code

See [ADR-0008](adr/0008-small-source-modules-joined-into-single-files.md). The source of `robot_bridge.py` and
`studio.py` moves into the small modules of `bridge/` and `desktop/`. `bundle.py` joins them back into the same
two files, so nothing changes at run time. The two large classes are split by feature into mixins.

[CODE-MAP.md](CODE-MAP.md) says which file to open for which job.

## What changes in the docs

[ARCHITECTURE.md](ARCHITECTURE.md) gets diagrams GitHub draws directly on the page (Mermaid), arranged by the
C4 model:

- the system in its context;
- the three running parts (browser interface, desktop app, robot bridge) and how they talk;
- the modules inside each part;
- sequence diagrams for connect, running a program, E-STOP, mapping and saving the robot menu;
- state diagrams for the connection and for mapping.

## Not in this change

- Renaming the robot's built-in menu entries: the robot's menu checker fixes them (ADR-0005).
- Merging Programs and Code into one screen: linking them fixes the problem at a fraction of the risk.
- Changes to what runs on the robot.

## How it is checked

- Every existing offline test, vitest suite and browser test passes unchanged, apart from tests that look for a
  renamed label, which are updated to the new label.
- `python bundle.py --check` passes. The joined files compile to the same code as before the split: every function
  and method body is unchanged, only moved.
- New vitest tests cover the Home task buttons, the placeholder rule and the docked warning.
