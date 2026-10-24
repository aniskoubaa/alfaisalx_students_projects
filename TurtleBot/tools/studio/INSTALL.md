# Install TurtleBot Studio

TurtleBot Studio is a small app for working with the lab's TurtleBot 4 from your own computer. It finds the robot, shows its status, copies and runs your programs, and has an emergency stop. It runs on your computer and opens in your web browser. Nothing is installed on the robot.

This page is the short version for students. The full details are in the [technical README](README.md).

> **Status (version 1.3):** the version 1.3 features are tested offline and in the simulated robot only. Real-robot checks are listed in the README under [Not verified yet](README.md#not-verified-yet). If a step fails, tell the lab maintainer and use the [Python version](#option-b-run-it-with-python) in the meantime.

## Guides

- [First connection](docs/FIRST-CONNECTION.md): the one-time setup over the Ethernet cable. Read this first.
- [Everyday use](docs/EVERYDAY-USE.md): start, connect, run a program, edit code, quit.
- [Find the robot](docs/FIND-THE-ROBOT.md): when the robot's address has changed.
- [Troubleshooting](docs/TROUBLESHOOTING.md): what you see and what to do.

(Earlier status note, version 1.2, 2026-10-24: the setup wizard and the Wi-Fi join were new and had not run on the real robot. The macOS and Linux files were untested.)

## What you need

- A computer with Windows 10 or 11, macOS, or Linux.
- The OpenSSH client. Windows 10 and 11, macOS and most Linux systems already have it. To check, open a terminal and run `ssh -V`. It should print a version.
- The robot's `ubuntu` password, from the lab maintainer. You type it once, in a terminal window, to set up key login. Studio never sees it.
- The robot switched on and near you.

## 1. Get the app

### Option A: download the ready-made app (no Python needed)

1. Sign in to GitHub and open the [TurtleBot Studio build](https://github.com/aniskoubaa/alfaisalx_students_projects/actions/workflows/turtlebot-studio-build.yml) runs.
2. Open the newest run with a green tick. Scroll down to **Artifacts**.
3. Download the one for your system. Artifacts come as a `.zip` file; unzip it.

| System | What to download | What it is |
|---|---|---|
| Windows (recommended) | The installer `TurtleBotStudio-Setup-1.3.exe` | Installs for your user only, no administrator rights. Adds a Start menu entry and a desktop shortcut. Studio opens in its own window, with no console window |
| Windows (no install) | The single file `TurtleBotStudio.exe` | Run it from any folder |
| macOS | The zip with the `TurtleBotStudio` app | Unzip and open the `.app` |
| Linux | The `TurtleBotStudio` binary and `install-linux.sh` | The script copies the binary to `~/.local/bin` and adds a menu entry. It prints how to undo it |

Windows installer: double-click `TurtleBotStudio-Setup-1.3.exe`, follow the pages, and leave **Launch TurtleBot Studio** ticked on the last page. To uninstall, use **Settings, Apps** and remove **TurtleBot Studio**. Uninstalling keeps your settings folder (see [Reset or remove Studio](#reset-or-remove-studio)), so your login key and robot list stay.

GitHub keeps these files for 90 days. If there is no run, or no artifacts, ask the lab maintainer or use option B.

### Option B: run it with Python

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** in the installer.
2. Get the folder `TurtleBot/tools/studio/` from this repository: clone the repository, or use **Code, Download ZIP** on GitHub and unzip it.
3. No `pip install` is needed.

## 2. Start it

| System | Option A (download) | Option B (Python) |
|---|---|---|
| Windows | Start menu or desktop shortcut **TurtleBot Studio** (installer), or double-click `TurtleBotStudio.exe` | Double-click `Start TurtleBot Studio.cmd` |
| macOS | Open the `.app` (or, for the plain binary, in a terminal: `chmod +x TurtleBotStudio`, then `./TurtleBotStudio`) | In a terminal in that folder: `bash start-studio.sh` |
| Linux | The menu entry added by `install-linux.sh`, or in a terminal: `chmod +x TurtleBotStudio`, then `./TurtleBotStudio` | In a terminal in that folder: `bash start-studio.sh` |

The first time, your system may warn you because the file is not signed:

- **Windows:** "Windows protected your PC". Click **More info**, then **Run anyway**.
- **macOS:** "cannot be opened because the developer cannot be verified". Right-click the file and choose **Open**, or run `xattr -d com.apple.quarantine TurtleBotStudio` once.

Version 1.3 opens Studio in its own window (Edge or Chrome in app mode when installed, otherwise your default browser). There is no console window in the installed and downloaded apps. Closing the window ends Studio after about 45 seconds; **Tools, Quit Studio** ends it at once. When you run it with Python, a console window is used and closing it stops Studio. The address contains a private token. Do not share it.

To try Studio without a robot, start it with `--fake` (for example `TurtleBotStudio.exe --fake` in a terminal, or `python studio.py --fake`). It shows a simulated robot.

## 3. Connect your computer to the robot

Pick one:

- **Same Wi-Fi:** your computer and the robot are on the same network, for example the lab Wi-Fi.
- **The robot's own Wi-Fi:** join the network `Turtlebot4` (the robot is then at `10.42.0.1`).
- **Ethernet cable:** plug a cable between your computer and the robot. See [Connect with an Ethernet cable](../../HOW-TO-CONNECT.md#connect-with-an-ethernet-cable-no-wi-fi-needed).

## 4. Follow the setup wizard

The wizard opens by itself the first time. It has six steps:

1. **ssh present:** checks for the OpenSSH client.
2. **Robot address:** press **Discover** and pick the robot, or type its address.
3. **Robot identity:** shows the robot's fingerprint. The lab robot is built in and shows "known robot". For any other robot, compare the fingerprint with the robot as described in [Robot identity](README.md#the-setup-wizard), or ask the lab maintainer.
4. **Key:** Studio creates a login key for you.
5. **Key login:** press **Open terminal**. In the terminal window, type the robot's `ubuntu` password. Type it only there, never in the Studio page.
6. **Test:** Studio logs in with your key and shows the robot's name. Press **Connect**.

Next time you start Studio, press **Discover**, then **Connect**. You do not need the password again, except when you add a Wi-Fi network to the robot.

## 5. Before anything moves

- **E-STOP** is always at the top of the page. You can also press **Esc** or **Space**.
- Studio asks you to confirm anything that moves the robot. Read the message before you confirm.
- Stay next to the robot, with about 1 m of clear floor around it. Read the [safety checklist](../../examples/README.md#safety-checklist-before-anything-moves) first.

## If something goes wrong

| What you see | What to do |
|---|---|
| "ssh not found" | Windows: Settings, System, Optional features, add **OpenSSH Client**. Linux: `sudo apt install openssh-client` |
| "key not set up" | Open the **Setup wizard** button and repeat steps 4 to 6 |
| "robot key does not match" | Stop and ask the lab maintainer. It may be a different or reinstalled robot |
| Discover finds nothing | Check that the robot is on and that you did step 3. Type the address yourself if you know it |
| "Port in use" | Studio is already running. Use the window that is already open, or close the other copy |
| The window does not open | Start Studio again: a second start opens the window of the copy that is already running. If it still does not appear, open **Tools, Settings**, set **How Studio opens** to **A tab in my web browser**, and start it again. Errors are written to `studio.log` in the settings folder |

More problems and fixes: [Troubleshooting](README.md#troubleshooting).

## Reset or remove Studio

Studio keeps its settings and your login key in one folder:

| System | Folder |
|---|---|
| Windows | `%APPDATA%\TurtleBotStudio` |
| macOS | `~/Library/Application Support/TurtleBotStudio` |
| Linux | `~/.config/turtlebot-studio` |

Delete that folder to start again from the wizard. To remove Studio completely, delete the folder and the app file (or the `studio` folder). Your own programs and Wi-Fi networks you added stay on the robot, and so does your public key in `~/.ssh/authorized_keys`; the lab maintainer can remove it.
