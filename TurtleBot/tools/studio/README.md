# TurtleBot Studio - technical README

**New to Studio? Start with the short student guide: [INSTALL.md](INSTALL.md).** This README has the full details.

Student guides (version 1.3):

- [First connection](docs/FIRST-CONNECTION.md): the one-time setup over the Ethernet cable.
- [Everyday use](docs/EVERYDAY-USE.md): start, connect, run a program, edit code, quit.
- [Find the robot](docs/FIND-THE-ROBOT.md): when the robot's address has changed.
- [Troubleshooting](docs/TROUBLESHOOTING.md): what you see and what to do.

## Quick start

TurtleBot Studio is the recommended way to work with the lab robot (task [TB-27](../../ROADMAP.md#tb-27-desktop-control-app-for-connecting-file-sync-and-running-programs)). It runs on your own computer, opens in your browser, finds the robot, shows its status, copies and runs programs and has an emergency stop. Nothing is installed on the robot. Built and tested over the Ethernet cable on 2026-10-24 with the robot docked and no motion; the checks still open are listed under [Not verified yet](#not-verified-yet).

1. Install Python 3.10 or newer from python.org. On Windows, tick **Add python.exe to PATH** in the installer. You also need the OpenSSH client (`ssh`), which Windows 10 and 11, macOS and most Linux systems already have.
2. Get this folder (`TurtleBot/tools/studio/`) from the repository.
3. Start it:
   - **Windows:** double-click `Start TurtleBot Studio.cmd`.
   - **macOS and Linux:** in a terminal in this folder, run `bash start-studio.sh`.
   - **Any system:** run `python studio.py` (on Windows `py studio.py`). The program prints an address like `http://127.0.0.1:8765/?token=...` and opens it in your browser. Keep that address private. If port 8765 is busy, the next free port is used.
4. Connect the computer to the robot: join the same Wi-Fi (`Students` or the robot's own `Turtlebot4`), or plug in an Ethernet cable ([HOW-TO-CONNECT.md](../../HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed)).
5. In Studio press **Discover**, pick the robot from the candidates, and press **Connect**.
6. If Studio says **key not set up**, open **Tools, Set up key login**. A terminal window opens; type the robot's `ubuntu` password there (ask the lab maintainer; the app never sees it). Then press **Connect** again.

Try it without a robot: open `web/mock.html` in a browser to see the interface with fake data, or start the app with `python studio.py --fake` for a demo with a simulated robot (it says nothing about real robot behaviour).

### Quick start without Python (version 1.2)

From version 1.2 Studio is also built as a single file per system, so no Python is needed.

1. Download `TurtleBotStudio.exe` (Windows) or the `TurtleBotStudio` binary (macOS, Linux) from the artifacts of the GitHub Actions build "turtlebot-studio-build" (see [Building the app](#building-the-app)).
2. Double-click it (Linux and macOS: see below). A console window opens and shows the address of Studio; your browser opens it and the [setup wizard](#the-setup-wizard) starts on the first run. **Closing the console window stops Studio.**
3. The file is not code-signed, so your system warns you once:
   - **Windows SmartScreen:** click **More info**, then **Run anyway**.
   - **macOS Gatekeeper:** right-click the file and choose **Open**, or remove the quarantine flag in a terminal: `xattr -d com.apple.quarantine TurtleBotStudio`.
   - **Linux:** make it executable first: `chmod +x TurtleBotStudio`, then run `./TurtleBotStudio`.

Running from source (`python studio.py`, steps above) still works and does the same.

## What's new in 1.3

Version 1.3 (2026-10-24) makes Studio easier to install and keep connected. The student guides above describe each part.

| Area | What changed |
|---|---|
| Installer | Windows: `TurtleBotStudio-Setup-1.3.exe` (NSIS, per user, no administrator rights, Start menu and desktop shortcut, uninstall in Apps; the settings folder is kept). macOS: `TurtleBotStudio-macOS.zip` with a `.app`. Linux: the binary plus `install-linux.sh` (add-only, prints how to undo) |
| Own window | Studio opens in its own Edge or Chrome app window, with no console window. Without Edge or Chrome it uses the default browser. Setting **How Studio opens**. A second start opens the window of the running copy (`instance.json` in the config folder) |
| Stopping | **Tools, Quit Studio**. The installed app also stops about 45 s after its last window closes (`--stay-open` keeps it running; from source it stays open unless `--exit-when-closed` is given) |
| Find the robot | **Search the whole network**: checks port 22 on every address of this computer's /24 network(s), reads the neighbour table for Raspberry Pi network cards and confirms the robot by its host key. Only when you press the button |
| Reconnect | When the link drops, Studio reconnects by itself (2 s to 30 s apart, up to 10 minutes), trying the last address and then a quick discovery. It never restarts programs or releases the e-stop. **Stop reconnecting** cancels; the setting **Reconnect by myself** turns it off |
| Diagnostics | **Tools, Copy diagnostics**: version, system, connection, settings summary and the last log lines, with tokens and passwords removed. Copy or save as a file |
| Updates | At most once a day Studio reads `version.json` from this repository on GitHub (no identifiers sent) and shows a banner when a newer version exists. **Tools, Check for updates**; can be switched off in Settings |
| Save | Saving an unchanged file no longer writes a `.bak` copy ("No changes to save") |

## What's new in 1.2

Added 2026-10-24 (S-a to S-d):

- **One file per system (S-a).** `TurtleBotStudio.exe`, or a binary for macOS and Linux, built with PyInstaller. No Python install needed.
- **First-run setup wizard (S-b).** Six steps: ssh present, robot address, robot identity, key, key login, test. See [The setup wizard](#the-setup-wizard).
- **Join any WPA/WPA2-personal network (S-c).** The Wi-Fi tab can put the robot on any such network. You type the Wi-Fi password in Studio and the robot password in the terminal. See [The Wi-Fi tab: join a network](#the-wi-fi-tab-join-a-network).
- **Works with any TurtleBot 4 (S-d).** New settings for the robot's hostname, user, hotspot name and address, cable address and key file, and a list of trusted robots instead of one pinned key. See [Settings](#settings).

## What's new in 1.1

Added 2026-10-24 after the first round of feedback:

- **Programs tab explains every program.** Each of the 21 entries (the 16 examples and 5 templates, listed in `programs.json`) is a card with a plain summary and badges (moves, safe on the dock, needs undock, helper). **What does it do?** shows its arguments, clickable examples, how it stops and notes.
- **Code tab:** write your own program and run it.
- **Wi-Fi tab:** a guide to connecting over Wi-Fi.
- **Charging is shown correctly.** The Create 3 always reports `power_supply_status` 0 (unknown), so Studio now judges charging from the battery current (positive means charging) and shows Charging (A), Full or On battery.
- Motion detection ignores comments and docstrings in a program's code.
- File access on the robot is limited to the home folder (never `~/.ssh`, no `..`, no symlinks out of it).

## Using Studio

Safety rules first:

- **E-STOP** is always visible at the top. Press it, or press **Esc** or **Space**. It sends zero velocity ten times, creates `~/STOP`, stops the motion programs, switches the drive motors off and cancels a dock or undock. A red banner stays until you press **Release e-stop** and confirm.
- Anything that moves the robot (Undock, Dock, motion programs) asks for a confirmation. Read it before you confirm.
- **Stay next to the robot** while it moves, with about 1 m of clear floor, as in the [safety checklist](../../examples/README.md#safety-checklist-before-anything-moves).
- The lidar can stay switched off after an undock (seen on 2026-10-24, [MAINTENANCE.md](../../MAINTENANCE.md#known-issues)). If programs report "no /scan", press **Start lidar motor** on the Dashboard.

Tabs:

| Tab | What it does |
|---|---|
| Dashboard | Live status once a second: battery, docked or not, odometry age and rate, lidar, hazards, Wi-Fi, CPU and temperature, a clock warning, the ROS service. Undock and Dock buttons (with confirmation), **Start lidar motor**, and a health check (13 checks; "robot clock" fails while the clock is wrong) |
| Programs | Lists the programs in `~/robot_code`, runs one with arguments, shows its live log, stops it, or stops all. Motion programs need the confirmation box ticked, otherwise Studio refuses ("motion needs confirmation") |
| Files | Compares a folder on your computer with a folder on the robot (sha1), uploads and downloads, has a dry run, and never deletes without a confirmation. **Sync and run** copies and starts a program in one step |
| Topics | Lists the ROS topics and watches up to four live |
| Wi-Fi | Shows "This computer" and "The robot" and three ways to connect, with a "You are here" marker: **A** the robot's own hotspot `Turtlebot4` (robot at `10.42.0.1`), **B** put the robot on a Wi-Fi network with **Join a Wi-Fi network** (from 1.2; in 1.1 it was **Add <network> to the robot**, this computer's network only), **C** the Ethernet cable. Also lists the networks saved on the robot (**Remove**, except protected netplan entries), the networks the robot can see (empty while it is in hotspot mode) and troubleshooting. Studio remembers the robot's address per network and Discover tries it |
| Code | A file list for `~/robot_code`, **New program** from a template, an editor with line numbers (Tab indents, Ctrl+S saves), **Save to robot**, **Save and Run**, **Stop**, **Revert**, **Open in VS Code**, live output and a "How robot code works" help box |
| Tools | Open a terminal on the robot, set up key login, open the robot in VS Code Remote-SSH (it adds a block to `~/.ssh/config` only after you confirm, and never removes anything), settings and the app log |

### The Wi-Fi tab: join a network

Version 1.2 (2026-10-24) replaces the old "Add to the robot" flow. It can put the robot on any Wi-Fi network, not only the one this computer is on. The old text is kept below under [The Wi-Fi tab: Add to the robot (1.1, history)](#the-wi-fi-tab-add-to-the-robot-11-history).

Supported: **WPA or WPA2 personal** (one shared password). Not supported: WPA2/WPA3 enterprise (802.1X, for example `eduroam`), open networks, WPA3-only networks, and networks that need a login page (captive portal).

How to use it:

1. Open the Wi-Fi tab. Pick a network from **Networks the robot can see** (press **Use**) or type its name. The robot cannot scan while it runs its own hotspot, so in that case type the name (this also covers hidden networks).
2. Type the Wi-Fi password in Studio. Optionally tick **Switch the robot to it now and test it**.
3. Press the add button and confirm. A terminal window opens on your computer. Type the robot's `ubuntu` (sudo) password there, and only that password. Ask the lab maintainer if you do not have it.
4. If you ticked switch now, the robot joins the network with a 45 s timeout. Studio shows the result and the robot's new IP address, and remembers the address so **Discover** finds it.

What happens to the Wi-Fi password:

- It is sent once, through the existing ssh link, to the robot-side helper, which keeps it in memory for at most 3 minutes.
- The helper hands it only to a process of the same user on the robot, over a local socket, and only once. The terminal script reads it from there and passes it straight to the command that saves the profile.
- Studio never writes it to disk and never logs it. The password field is cleared right after sending.
- Without that handoff (older flow, or a script started by hand without the one-time code) the script asks for both passwords in the terminal: first the Wi-Fi password, then the robot password.

The saved profile has autoconnect on, priority 10 and Wi-Fi power saving off (`powersave 2`). Undo, on the robot: `sudo nmcli connection delete "<network name>"` (the **Remove** button does the same for saved networks).

With **switch now and test**:

- The robot tries to join with a 45 s timeout. The job runs as a detached process on the robot, so it survives the ssh connection dropping.
- If it fails (wrong password, out of range), the robot removes the new profile and goes back to the network it was on before. You can then retry with the right password.
- The Ethernet cable is never touched, so a cable connection stays up.
- The robot writes the progress to `/run/turtlebot-studio-wifi.json`. The file holds no secrets (network name, state, IP, previous network).

If your computer was connected through the robot's hotspot, the connection drops when the robot switches. This is expected. Join your computer to the new network and press **Discover**. If the join failed, the robot returns to its previous network, which can take about 1.5 minutes.

Status 2026-10-24: tested only with a stub `nmcli` and in `--fake` mode, not yet on the real robot (see [Not verified yet](#not-verified-yet)).

### The Wi-Fi tab: Add to the robot (1.1, history)

Kept for reference. Version 1.1 behaviour, replaced by the section above in 1.2.

**Add <network> to the robot** opens a terminal window on your computer. There you type two secrets, and Studio never sees either: first the Wi-Fi password of that network, then the robot's `ubuntu` (sudo) password. (Corrected 2026-10-24: this line and the confirm dialog used to give the opposite order; the script asks for the Wi-Fi password first.) The robot stores a NetworkManager profile with priority 10, Wi-Fi power saving off and autoconnect on, and keeps its own hotspot as the fallback. Undo, on the robot: `sudo nmcli connection delete "<network name>"` (the **Remove** button does the same for saved networks). Networks that need a login page (captive portal) or WPA2-Enterprise are **not supported**. Known gap: option B offers to add `Students` even when the robot already has it saved. This flow was run for real on 2026-10-24 (see [Tested on the robot, evening](#evening-session-2026-10-24-home-wi-fi-and-supervised-motion)); the **Remove** flow has not been run for real yet.

**Network name box.** Above the Add button is an editable box, "Network name to add". It is filled in from the laptop's current Wi-Fi and follows the detection until you type in it. The Add button uses whatever the box contains, so check it before you press the button. On Windows 11, `netsh wlan show interfaces` hides the network name unless **Location services** are on ("Network shell commands need location permission"). Studio then falls back to the name of the Windows network profile of the Wi-Fi adapter, marks it as a guess and shows a note. A profile name is usually the network name but can differ, so correct the box if it is wrong.

### The setup wizard

It opens by itself on the first run, and from the **Setup wizard** button (Dashboard connection card and Tools tab) and from connection errors such as "key not set up". If a `settings.json` from an earlier version already has a robot address, the wizard is treated as done. **Skip setup** also marks it done.

| Step | What it does |
|---|---|
| 1 ssh present | Checks for the OpenSSH client. If missing: Windows, Settings, System, Optional features, OpenSSH Client; macOS has it; Linux `sudo apt install openssh-client` |
| 2 Robot address | **Discover**, or type the address; pick a reachable candidate |
| 3 Robot identity | Reads the robot's host key (`ssh-keyscan`) and shows its fingerprint. See below |
| 4 Key | Creates your key for this robot if it is missing and shows its path and fingerprint |
| 5 Key login | **Open terminal**: a terminal opens where you type the robot password once. Studio never sees it |
| 6 Test | Logs in with the key and shows the robot's hostname. Then **Connect** |

**Robot identity.** Every robot has its own host key. Studio only talks to robots whose key it trusts, so nobody can pose as your robot. The fingerprint is a short code for the key (`SHA256:...`).

- The AlfaisalX lab robot's key is built in. Studio then says "known robot" and no check is needed. You can switch the built-in key off in the settings.
- For any other TurtleBot 4, compare the fingerprint Studio shows with the one on the robot. On the robot (screen and keyboard, or an ssh session you already trust) run `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. If both match, tick the box, give the robot a label and press **Trust this robot**. If they differ, do not trust it and ask the lab maintainer.
- Trusted robots are listed in the settings, where you can remove them again.

The robot password is typed only in the terminal window that ssh itself opens, never in the Studio page.

### Settings

Tools, settings. The defaults make the lab robot work without changes; change them for another TurtleBot 4.

| Setting | Default | Meaning |
|---|---|---|
| `robot_hostname` | `turtlebot4` | Name used for discovery as `<name>.local` |
| `robot_user` | `ubuntu` | Login user on the robot |
| `hotspot_ssid` | `Turtlebot4` | Name of the robot's own hotspot (shown in the UI and used when joining it) |
| `hotspot_addr` | `10.42.0.1` | Robot address on its own hotspot |
| `cable_addr` | `192.168.185.3` | Robot address on the Ethernet cable (tried when your computer has a cable address) |
| key file | your `~/.ssh/turtlebot4_ed25519` if present, else one in the config folder | Private key used to log in |
| trusted robots | empty | Robot host keys you trusted in the wizard (key, label, date) |
| built-in lab key | on | Whether the AlfaisalX lab robot's key is trusted |

Studio writes all trusted keys into its own `known_hosts` file under the same alias, and ssh accepts any of them. An older single "trust a different robot key" setting is moved into the trusted list automatically.

### The Code tab

1. Press **New program** and pick a template (table below), or open an existing file.
2. Edit, then **Save to robot**. The save is atomic, keeps one `.bak` copy and warns if the file changed on the robot since you opened it. **Revert** reloads the robot's version.
3. **Save and Run** saves and starts the program. A program that moves the robot needs the motion confirmation. Output appears live; **Stop** ends the program.
4. In the editor, **Esc and Space do not trigger the e-stop** (you are typing). **Ctrl+Shift+E** triggers it everywhere, and the E-STOP button is always clickable.

### Templates

Files in `templates/`. All motion templates cap speed at 0.15 m/s and 1.0 rad/s, have a time limit, refuse to run while the robot is docked, stop on a `~/STOP` file, Ctrl+C or SIGTERM, hold still for 0.3 s of stale odometry and abort at 2 s, stop on a bump, and take `--dry-run` (check and print the plan, never move) and `--yes` (skip the "area clear?" question; needed when run from Studio). Forward motion also uses a lidar stop.

| File | What it does | Moves? | Example arguments | Simulator result |
|---|---|---|---|---|
| `my_first_program.py` | Prints battery, dock state and position for 10 s | No | none | Not applicable |
| `read_lidar.py` | Reads the lidar and prints what it sees | No | none | Not applicable |
| `spin_in_place.py` | Turns on the spot | Yes | `--turns 1 --speed 0.5 --dry-run` | 1 turn: error 0.3 degrees |
| `drive_circle.py` | Drives a circle | Yes | `--radius 0.3 --laps 1 --dry-run` (negative laps = right) | Radius 0.30 m closes within 0.1 cm |
| `drive_forward_and_back.py` | Drives out and returns | Yes | `--distance 0.3 --dry-run` | 0.30 m returns within 0.2 cm |

The simulator results are from the offline tests (`tests/offline/test_studio_templates.py`), not from the real robot. `spin_in_place.py` and `drive_circle.py` (saved as `my_spin_in_place.py` and `my_drive_circle.py`) ran on the real robot on 2026-10-24, over Wi-Fi, with a person next to it and the motion confirmation ticked: spin turned 359 degrees in 14 s; the circle template drove the lap, but its closure figure is not valid (see the evening session below). The other motion templates have not run on the real robot.

Run logs and process ids are kept on the robot in `~/robot_code/logs/` (MAINTENANCE.md R15).

## Building the app

The single-file app is built with PyInstaller. It cannot cross-compile, so build on the system you want the file for.

```
pip install pyinstaller==6.20.0
python packaging/build.py            # build; output in packaging/dist (git-ignored)
python packaging/build.py --smoke    # build, then start the binary with --fake and check that it answers
```

Run these from `TurtleBot/tools/studio/`. On macOS and Linux build the same way on that system. The GitHub Actions workflow `.github/workflows/turtlebot-studio-build.yml` builds all three systems when a tag `studio-v*` is pushed or when started by hand, runs the offline tests and the smoke test, and uploads one artifact per system. There is no release step yet: download the files from the run's artifacts.

From 1.3, `python packaging/build.py --smoke --installer` also builds the Windows installer `packaging/dist/TurtleBotStudio-Setup-<version>.exe` from `packaging/installer.nsi`. It needs NSIS 3 (`makensis`): on PATH, in `Program Files (x86)\NSIS`, or in the electron-builder cache. The smoke test also checks the single-instance start and a clean quit. The workflow installs NSIS with `choco install nsis -y` on Windows and uploads the setup file, the macOS zip, and the Linux binary with `install-linux.sh`.

## Tested on the robot 2026-10-24

Laptop time about 00:45 to 01:15 (UTC+3), over the Ethernet cable, robot docked, **no motion**. The robot's clock was wrong (year 2024), as expected.

Verified:

- Discover found the cable candidate (IPv6 link-local) reachable in 13 ms; the hotspot and `turtlebot4.local` were not reachable from there, as expected. Connect took 7.2 s; the helper reported ROS 2 Jazzy with Fast DDS.
- Status at 1 Hz with real values: battery 96 to 99 %, docked, odometry 20 Hz with age 0.02 s, lidar 7.9 Hz (the motor was still running from an earlier manual start), the robot in access-point mode, the addresses of `eth0`, `usb0` and `wlan0`, power saving for `Students` shown as `disable`, clock year 2024 not synchronised.
- Topics: 133 entries (including hidden ones) listed in 74 ms; `/odom` watched at 2 Hz and unwatched.
- Files and programs: a test script synced to `~/robot_code/studio_test` (dry run, then upload, 0.9 s), listed with sha1, run with a live log, stopped (SIGINT) and reported as exited. A motion run without the confirmation was refused.
- Health check: 13 checks, only "robot clock" failed (expected).
- E-STOP through the API and through the UI button: the wheels were disabled, the red banner showed and all steps reported ok. Release through the confirm dialog enabled the wheels again, cleared the banner and removed `~/STOP`. Three on/off cycles in total (command line once, API once, UI once).
- Cleanup: the test folder and test logs were removed from the robot. The empty folder `~/robot_code/logs/` remains (R15).

### Studio 1.1 (also 2026-10-24, laptop time about 01:30 to 03:00, over the cable, robot docked, no motion)

- The catalog (21 entries) and the Wi-Fi information call (hotspot active; `Students` saved with priority 10 and power saving `disable`) worked; the `describe` call worked.
- Two templates were written to `~/robot_code/studio_test`. `my_first_program.py` ran without confirmation and printed battery 99 %, docked yes and the position each second, exit 0. `spin_in_place.py` was refused without the confirmation; with confirmation and `--dry-run` it printed "docked: True ... dry run: all checks done, nothing was sent to /cmd_vel", exit 0.
- Battery showed charging, 0.57 A, while docked. The test files were removed afterwards.
- A leftover empty log from an earlier Studio run of `drive_test.py` (robot time 2024-10-28) was found and left in place.
- Observation: during `my_first_program.py` at idle on the dock, `/odom` age reached 1.75 s once, a base stall without motion (see ROADMAP TB-25).

Four bugs found and fixed during the first test (version 1.0):

1. The robot-side helper used the multi-threaded rclpy executor and took 97 % of one Pi core. With the single-threaded executor it takes about 23 % of one core (about 6 % of the Pi's total) at status 1 Hz. The target was 10 %, so it was **not met**; the subscriptions to `/odom`, `/wheel_status` and `/scan` alone cost about 11 %.
2. The Create 3 `/e_stop` service answers `success=False` with an empty message even when it works (firmware `I.0.0.FastDDS`). The helper now confirms from `wheels_enabled` in `/wheel_status`.
3. On browser windows narrower than about 900 px the E-STOP button was off-screen. The header now wraps and the E-STOP comes first, full width.
4. A wrong hint "lidar off while docked" was shown when the lidar was running.

Offline tests: `tests/offline/test_studio_bridge.py` (74 checks pass; 2 are POSIX-only and skipped on Windows) and `tests/offline/test_studio_desktop.py` (about 100 checks pass).

### Evening session 2026-10-24: home Wi-Fi and supervised motion

Laptop time from about 04:26 (UTC+3); robot clock correct from about 04:50. Facts are measured on the real robot unless marked as a hypothesis. Change record: MAINTENANCE.md R16 and its runtime table.

Verified:

- **Add to the robot** worked for the network `TP-LINK_Extender_5GHz` with "Switch now" ticked. The robot joined at once (5 GHz, signal 61 %, -60 dBm), and `connection successfully activated` was printed. One `sudo` password typo was retried inside the terminal window. The saved file is root-only (mode 600) with autoconnect on, priority 10 and power saving off.
- After the cable was unplugged, **Discover** found `turtlebot4.local` over Wi-Fi in 233 ms (mDNS works on that home network); the cable and hotspot candidates answered "No answer", as expected. Studio ran over Wi-Fi only; the dashboard stayed live.
- **Undock** and **Dock** through the Dashboard both reported "succeeded (status 4)".
- Programs from the Code tab (**Save and Run**) with the motion confirmation ticked: `my_spin_in_place.py --turns 1 --yes` and `my_drive_circle.py --radius 0.3 --yes`. The first spin was aborted by the program's own safety check ("odometry is stale (none for 2.0 s)") after an `/odom` gap of 7.81 s; the robot stopped as designed. The second spin finished ("turned 359 degrees in total (odometry)", 14 s). The circle template finished in about 22 s. Its message "ended 17.3 cm from the start" is **not valid**: the robot drove over the dock edge and was moved by hand during the lap.
- Timing: `/odom` gaps in these runs were the Create 3 base stalling, not Wi-Fi (no errors or drops, steady signal). Recordings: `tests/logs/2026-10-24_timing_wifi_before_base_restart.jsonl.gz`, `tests/logs/2026-10-24_timing_wifi_after_base_restart.jsonl.gz`, and the program run logs in `tests/logs/2026-10-24_studio_motion_runs.log`. Analysis: [ROADMAP.md, TB-25](../../ROADMAP.md#tb-25-find-why-the-create-3-base-stalls-when-it-starts-moving) and [MAINTENANCE.md, /odom finding](../../MAINTENANCE.md#update-2026-10-24-evening-over-wi-fi).
- The test programs, their `.bak` copies and the run logs were removed from the robot afterwards. `~/robot_code/logs` stays (R15).

Bugs found and fixed in the code during this session (offline test `tests/offline/test_studio_desktop.py`: 0 failures after the changes):

1. Windows 11 hid the Wi-Fi name (Location services off), so Studio said "not on Wi-Fi" while the laptop was on Wi-Fi. Fixed with the profile-name fallback and the editable "Network name to add" box described above.
2. On Windows the Add and Remove terminal window closed at once: the launcher passed `stdin=DEVNULL`, so PowerShell `-NoExit` read end-of-input and exited. Fixed: on Windows no standard handles are passed (POSIX keeps `stdin=DEVNULL`).
3. Add and Remove always failed with "base64: invalid input / bad arguments": `bash <(script) studio-script <args>` makes bash set `$0` to the script file, so the placeholder `studio-script` became `$1`. Fixed by removing the placeholder; the test now checks that `$1` is the network name. Checked on the robot with no input: the script printed the right name and stopped at the password check, "Nothing was changed".
4. The confirm dialog gave the wrong password order (see above). Fixed.

Known gaps seen, not fixed:

- In a narrow window (about 800 px) the confirm dialogs overflow past the right edge.
- **Save and Run** writes a `.bak` copy even when the file is unchanged, so deleting a program leaves `<name>.py.bak` on the robot.
- The **Remove** flow is still not run for real.

Update 2026-10-24 (1.2): the narrow-window dialog overflow is fixed (dialogs now fit narrow windows). The other gaps remain, see [Known gaps](#known-gaps).

## Not verified yet

Updated 2026-10-24, evening: the items "Add to the robot", "Connections over Wi-Fi", "Code tab in a real browser", "Undock and Dock and motion programs through Studio" and "motion templates on the real robot" were verified in the session above and are no longer open (earlier text kept below where still true). Motion was checked only for `spin_in_place` and `drive_circle`.

- The **Open terminal**, **Set up key login** and **Open in VS Code** buttons (they open windows on your computer).
- The **Remove** Wi-Fi flow (it changes the robot's saved networks) and joining the hotspot from Studio. (**Add to the robot** and laptop Wi-Fi detection were verified on 2026-10-24, evening.)
- The motion templates other than `spin_in_place` and `drive_circle` on the real robot (only the simulator and `--dry-run` were run for them).
- macOS and Linux (only Windows was used), and discovery on other computers.
- Connections over the robot's hotspot and over `Students` (the cable and the home network `TP-LINK_Extender_5GHz` have been used).
- Stopping a move with E-STOP while the robot is driving (E-STOP was only tested docked).
- Runs that keep going on the robot after the connection drops (the POSIX path).
- The GitHub Actions run on Linux (the workflow runs both offline test files and `node --check`; no run seen yet).
- The CPU target of 10 % for the robot-side helper (23 % of one core measured).

Added for 1.2 (2026-10-24):

- The new Wi-Fi join flow on the real robot: the secret handoff socket, the `sudo setsid` join job and the fallback to the previous network have run only in tests with a stub `nmcli` and in `--fake` mode.
- `ssh-keyscan` and the test login against a real robot.
- The macOS and Linux builds and the GitHub Actions run.
- The `.exe` on a clean Windows PC without OpenSSH.
- WPA2-enterprise networks are not supported.

Verified on 2026-10-24: the offline tests pass (desktop, bridge, templates, setup, pure). The Windows `.exe` (7.8 MB) was built locally and passed `build.py --smoke`. In `--fake` mode the wizard ran all six steps and a Wi-Fi join showed the new address, with the Wi-Fi password not found in the config folder, the log or the console output.

Added for 1.3 (2026-10-24):

- **Search the whole network**, the automatic reconnect and the update check on real networks. The sweep parsers, the reconnect and the update check ran only against test data, the simulated robot and a local test server; `version.json` returns 404 on GitHub until it is pushed.
- The macOS `.app`, the Linux `install-linux.sh` and the CI jobs.
- What programs on the robot do when the ssh link drops and Studio reconnects.

Verified on 2026-10-25: all six offline test files pass (desktop 140, bridge 112, templates 171, setup 135, upgrades 106, window 69). The installer was built locally and installed silently into a test folder (Start menu and desktop shortcuts, Apps entry, version 1.3). The installed app opened its own Edge app window and stopped by itself 47 s after that window was closed. The silent uninstall removed the program, the shortcuts and the Apps entry and kept the settings folder.

## Known gaps

- No version check or update function yet, and no "copy diagnostics" button. (Done in 1.3.)
- **Save** writes a `.bak` copy even when the file is unchanged. (Fixed in 1.3.)
- The installer and the app are not code-signed, so Windows SmartScreen and macOS Gatekeeper warn on the first start.
- E-STOP during a move is untested.
- The **Remove** Wi-Fi flow has not run for real.

## Technical details

The rest of this file is the technical README.

TurtleBot Studio is a local web application for the lab TurtleBot 4. A small Python program on your computer
(`studio.py`) serves a browser interface and talks to the robot over one SSH connection. Nothing is installed on
the robot: the robot-side helper (`robot_bridge.py`) is streamed over SSH when you connect and ends when you
disconnect.

## Requirements

| Where | Needs |
|---|---|
| Computer | Python 3.10 or newer (standard library only, no `pip install`), the OpenSSH client (`ssh`, `ssh-keygen`), a web browser |
| Windows | OpenSSH Client (an optional Windows feature, normally present: `C:\Windows\System32\OpenSSH\ssh.exe`) |
| macOS / Linux | `ssh` and `ssh-keygen` (normally preinstalled); a terminal program for the "Open terminal" button |
| Robot | TurtleBot 4 (Ubuntu 24.04, ROS 2 Jazzy), reachable on the network. The user `ubuntu` with key login (the app can help set it up) |
| Optional | VS Code with the `code` command on the PATH, for "Open in VS Code" |

## Start it

```
cd TurtleBot/tools/studio
python studio.py                      # Windows: py studio.py
```

The program prints an address like `http://127.0.0.1:8765/?token=...` and opens it in your browser. Keep the
address private: the token in it is what authorises the page. Press Ctrl+C in the terminal to stop (the app
asks the robot-side helper to exit first, then ends SSH).

Options:

| Option | Meaning |
|---|---|
| `--port N` | Port on 127.0.0.1 (default 8765; if it is busy the next free port is used) |
| `--no-browser` | Do not open the browser |
| `--host-override ADDR` | Use this robot address instead of discovery |
| `--fake` | Run `robot_bridge.py --fake` on this computer instead of SSH: a simulated robot for demos, UI work and tests (no robot, no ROS). "Robot files" are then a folder under the config directory |
| `--exit-when-closed` / `--stay-open` | From 1.3: stop, or keep running, about 45 s after the last Studio window closes. The installed app stops by default; run from source it stays open |
| `--version` | Print the version and exit |

Typical first session: press Discover, then Connect. If the app says "key not set up", use Tools, "Set up key
login": a terminal opens, you type the robot password there (the app never sees it), and the public key is
added to the robot. Then press Connect again.

## Architecture

```
 Browser (web/index.html, app.js, style.css)
    |  HTTP + JSON (POST), Server-Sent Events (GET /api/events)
    |  127.0.0.1 only, header X-Studio-Token, Host/Origin checks
    v
 studio.py (this computer)
    |-- Bus:       latest conn/status + last 200 log lines, fan-out to every SSE client (heartbeat 15 s)
    |-- Bridge:    ONE long-lived process, JSON lines on stdin/stdout, request/reply matched by id
    |-- Discovery: probes candidate addresses in parallel threads (TCP port 22), under about 4 s
    |-- Sync:      tar stream over ssh (Python tarfile on this side, tar on the robot)
    |-- Terminal / key setup / VS Code helpers (open a system terminal or VS Code)
    |
    |  ssh -T -o BatchMode=yes ... ubuntu@<robot>  "<BOOT>"        (or, with --fake, a local python process)
    v
 robot_bridge.py (streamed to the robot's python3 at connect time; stdlib + rclpy)
    |-- ROS 2 subscriptions/services/actions, system and network status, program runs (detached),
        e-stop, undock/dock, lidar motor
```

Protocol and endpoint details are in the TurtleBot Studio interface spec (ROADMAP TB-27). In short: the bridge
reads JSON command lines (`{"id":1,"cmd":"ping"}`) and writes one `reply` per command plus unsolicited events
(`hello`, `status`, `msg`, `run_output`, `run_exit`, `action`); the desktop passes every event to the browser
unchanged and adds `conn`, `discover`, `sync` and `log` events.

Source layout:

| File | Content |
|---|---|
| `studio.py` | Entry point and the whole desktop backend: pure helpers (ssh arguments, parsers, sync planning), bridge manager, discovery, sync, HTTP server |
| `robot_bridge.py` | Robot side (separate document) |
| `web/` | The browser interface (plain HTML/CSS/JS, no external assets, works offline) |
| `../../tests/offline/test_studio_desktop.py` | Offline tests of this backend |

## Security model

- The server binds to 127.0.0.1 only. Every `/api` request needs the random per-launch token (header
  `X-Studio-Token`; the event stream accepts `?token=` because browsers cannot set headers on it). Requests
  whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>` are refused (DNS-rebinding guard), and a POST
  with a foreign `Origin` is refused.
- The robot (ssh and sudo) password is never stored, requested, logged or sent by the app. Password login
  happens only inside a system terminal that runs `ssh` itself ("Set up key login", Wi-Fi join).
- Since 1.2 the one secret Studio handles is the Wi-Fi password when you join a network. It goes once through
  the existing ssh link into the robot helper's memory (at most 3 minutes), is handed once to a process of the
  same user over a local socket, and is never written to disk by Studio, never logged and never put in
  command-line arguments or environment variables. The status file `/run/turtlebot-studio-wifi.json` holds no secrets.
- Every ssh call checks the robot's host key: `HostKeyAlias=turtlebot4-lab`, `StrictHostKeyChecking=yes` and
  the app's own `known_hosts` file in the config directory. Since 1.2 that file holds a list of trusted keys:
  the built-in AlfaisalX lab robot key (can be switched off) plus every robot you trusted in the wizard after
  comparing fingerprints. A robot whose key is not in the list is refused. Host keys are public information.
  (Before 1.2 only one key was pinned.)
- Key login uses your existing `~/.ssh/turtlebot4_ed25519` if present, otherwise a key the app creates in the
  config directory (no passphrase, used only for this robot).
- Admin rights (sudo) are never used by the app.
- Motion programs need an explicit confirmation in the interface; the robot side refuses to start a motion
  program without `confirmed`, and while the `~/STOP` file exists. The E-stop button works through the bridge
  and, if that fails, through a separate one-shot SSH command.
- Sync never deletes anything unless you ask for it, preview it with a dry run and confirm. Files are
  extracted without links or paths outside the target folder.
- "Open in VS Code" edits `~/.ssh/config` only after you confirm a preview: it appends one block between the
  marker lines `# >>> TurtleBot Studio >>>` and `# <<< TurtleBot Studio <<<` (a backup `config.studio-backup`
  is made first) and never touches other lines.

## Config directory

| System | Path |
|---|---|
| Windows | `%APPDATA%\TurtleBotStudio` |
| macOS | `~/Library/Application Support/TurtleBotStudio` |
| Linux | `~/.config/turtlebot-studio` |

Contents: `settings.json` (last host, key path, local and remote folder, extra motion files, trusted key; from 1.2 also the settings above and the trusted robots),
`known_hosts` (the trusted keys), `id_ed25519` and `.pub` (only if the app created a key), `studio.log` (no
tokens, no passwords). Deleting the folder resets the app.

From 1.3 also: `instance.json` while Studio runs (process id, port and the session token, so a second start can open the running copy; removed on exit; the folder belongs to your user) and `window/` (the browser profile of Studio's app window).

## Troubleshooting

| Message / symptom | Cause and fix |
|---|---|
| "ssh not found" | Install the OpenSSH client (Windows: Settings, Optional features; Linux: `sudo apt install openssh-client`) |
| "key not set up" | The robot does not know your key yet: Tools, Set up key login, type the password in the terminal that opens, press Connect again |
| "robot key does not match the pinned key" | Different robot, reinstalled robot, or someone in the middle. Ask the lab maintainer. If it is another TurtleBot, add its key in Settings |
| "robot not reachable" | No route or the robot is off. Check the cable or Wi-Fi, press Discover, or type the address. On a cable link without DHCP only the IPv6 link-local address works unless the computer has a 192.168.185.x address |
| Discover finds nothing | The robot hotspot "Turtlebot4" needs your computer on that Wi-Fi (robot is 10.42.0.1). `turtlebot4.local` only resolves where mDNS works |
| Port in use | Another copy is running: close it or use `--port` |
| Page says the interface files are missing | `web/index.html` was not found next to `studio.py` |
| Programs stop when odometry pauses | Known base behaviour (TB-15); the example programs hold still through short pauses |

The log (Tools, app log in the interface, or `studio.log`) shows the last SSH error lines.

## Limitations

- One robot connection at a time; no automatic reconnect (press Connect; the last address is remembered).
- Programs started from the app keep running if the connection drops; stop them from the Programs tab or use E-stop.
- Sync handles regular files only (no symlinks), skips `__pycache__`, `.git`, `logs/`, `*.pyc` and files over
  20 MB, and compares content with SHA-1 (robot side up to 2 MB, larger files by size).
- The fake mode simulates data only; it says nothing about real robot behaviour.
- Tested offline only. Behaviour with the real robot (timing, terminals, VS Code) must be checked on the lab
  robot by a person.
