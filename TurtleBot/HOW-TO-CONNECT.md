# Connecting to the TurtleBot 4

This guide shows how to reach the lab's TurtleBot 4 from your own computer (Windows, macOS or Linux), log in, write and run code on it, and turn it off safely. It is written for any lab member, including people who have not used SSH or ROS 2 before. Every command works from a fresh computer; nothing depends on a particular laptop. Facts that can change are dated (most were checked on 2026-10-03). Since 2026-10-04 the robot has been dropping off the Wi-Fi: if it answers only sometimes, see [Troubleshooting](#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found) (updated 2026-10-10).

**Shortcut (added 2026-10-04):** the [connect tool](tools/connect/README.md) does steps 2 and 4 and the key setup for you: `TurtleBotConnect.exe` on Windows, `connect-turtlebot.sh` on macOS and Linux. You still need to join the right Wi-Fi (step 3) and know the passwords. This guide explains what the tool does, and works without it.

What the tool offers (version 1.1.0, described 2026-10-10): a numbered menu with 1 Connect (opens a robot terminal), 2 Find the robot (the last address that worked, `turtlebot4.local`, `10.42.0.1`, or an address you type), 3 Set up key login (once per computer), 4 Robot status (read only), 5 Open in VS Code, 6 Add a `turtlebot4` shortcut to your SSH config (it backs the file up first), 7 EMERGENCY stop of the motion programs (creates `~/STOP` and stops the example programs), 8 Copy a file to the robot, and 9 Fix "host key changed". It only talks to a device that presents the lab robot's ED25519 host key (the fingerprint in [Step 4](#what-you-will-see)), so a stale campus address that now belongs to another device is refused before any password prompt. After a robot reinstall, `--trust-new-host-key` lets it accept the new key, and a maintainer must then update the pinned key. The Windows program needs no installation (Windows 10 or 11) but is not code-signed: on the first run SmartScreen warns, choose **More info**, then **Run anyway**, or build it from its source with `build.cmd`, which uses the C# compiler that comes with Windows. As of 2026-10-10 the tool has not yet been used with the real robot ([ROADMAP.md, TB-23](ROADMAP.md#tb-23-first-robot-run-of-the-new-programs-and-the-connect-tool)).

For a beginner's overview of the robot's hardware and ROS 2, read the [TurtleBot 4 field guide](turtlebot4-field-guide.html). For what has been changed on the robot, and how to verify or undo it, see [MAINTENANCE.md](MAINTENANCE.md).

**Contents**

1. [At a glance](#at-a-glance)
2. [Before you start](#before-you-start)
3. [Step 1: Turn the robot on](#step-1-turn-the-robot-on)
4. [Step 2: Find out which network the robot is on, and its address](#step-2-find-out-which-network-the-robot-is-on-and-its-address)
5. [Step 3: Connect your computer to the same network](#step-3-connect-your-computer-to-the-same-network)
6. [Step 4: Open a terminal and connect](#step-4-open-a-terminal-and-connect)
7. [Recommended: log in with a key instead of a password](#recommended-log-in-with-a-key-instead-of-a-password)
8. [Write and run code](#write-and-run-code)
9. [Turning the robot off](#turning-the-robot-off)
10. [Troubleshooting](#troubleshooting)
11. [Known issues](#known-issues)
12. [Developer quick reference](#developer-quick-reference)
13. [Optional: save a shortcut in your SSH config](#optional-save-a-shortcut-in-your-ssh-config)
14. [Remote desktop](#remote-desktop)
15. [Admin tasks](#admin-tasks)
16. [Related documents](#related-documents)

## At a glance

| Item | Value |
|---|---|
| Robot | TurtleBot 4 **Standard** (OLED display and buttons on top): a Raspberry Pi 4 on top of an iRobot Create 3 base |
| Software | TurtleBot 4 image 2.0.2, Ubuntu 24.04.1 Server (no desktop), ROS 2 Jazzy |
| ROS 2 middleware | Fast DDS, `ROS_DOMAIN_ID` 0 |
| Login | User `ubuntu`, hostname `turtlebot4` |
| Normal network | University Wi-Fi `Students`. Robot address from DHCP, shown on the display (starts with `10.87.`). Also reachable as `turtlebot4.local`, but since 2026-10-04 the name has failed now and then on campus: if it does, use the address on the display. |
| Fallback network | The robot's own Wi-Fi `Turtlebot4` (5 GHz). Robot address is always `10.42.0.1`. No internet. |
| Lab router (added 2026-10-10) | A lab Wi-Fi network (Linksys router, `192.168.1.x`) was set up on 2026-10-05. **The robot is not on it**; moving it there is a proposal ([ROADMAP.md, TB-21](ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router)). |
| Code folder on the robot | `~/robot_code`. As of 2026-10-10 it holds copies of `hello_robot.py`, `scan_test.py`, `clearance_check.py`, `drive_test.py`, `motion_test.sh` and `motion_shapes.py` from [`examples/`](examples/); the newer programs must be copied first ([examples/README.md](examples/README.md#copy-the-files-to-the-robot)) |
| Official manual | https://turtlebot.github.io/turtlebot4-user-manual/ |

## Before you start

You need:

- A computer with Wi-Fi and an SSH client. Windows 10 and 11, macOS and most Linux systems already include `ssh`.
- The Wi-Fi password for the network the robot is on:
  - `Students`: the shared university Wi-Fi password.
  - `Turtlebot4` (the robot's own Wi-Fi): the factory default from the TurtleBot 4 user manual, unless the lab changed it. Ask the lab maintainer.
- The password of the robot's `ubuntu` account: the factory default from the TurtleBot 4 user manual, unless the lab changed it. Ask the lab maintainer. After you set up [key login](#recommended-log-in-with-a-key-instead-of-a-password) you only need it for admin tasks.
- Optional: [VS Code](https://code.visualstudio.com/) with Microsoft's "Remote - SSH" extension, for editing code on the robot.
- Before running anything that moves the robot: about 1 m of clear floor around the dock.

Passwords are never written in this repository. Do not add any.

## Step 1: Turn the robot on

1. Place the robot on its charging dock. It powers on by itself.
2. Wait about 2 minutes. When the robot is ready it plays a chime and its address appears on the display.

If nothing appears after a few minutes, see [Troubleshooting](#troubleshooting).

## Step 2: Find out which network the robot is on, and its address

The robot has two network modes. It uses the university `Students` Wi-Fi when that network is in range (NetworkManager profile priority 10) and falls back to its own access point (priority 0) otherwise. The address on the display tells you which mode is active.

| | University Wi-Fi (normal) | Robot's own Wi-Fi (fallback) |
|---|---|---|
| Display shows | `10.87.x.x` | `10.42.0.1` |
| Network (SSID) your computer must join | `Students` (WPA2-Personal, one shared password) | `Turtlebot4` (5 GHz) |
| Robot address | Assigned by DHCP and can change. It was `10.87.10.205` (subnet `10.87.0.0/18`) on 2026-10-03. | Always `10.42.0.1` |
| Your computer's address | From the university network | `10.42.0.x`, given by the robot |
| Internet on your computer | Yes | No (see [Step 3](#step-3-connect-your-computer-to-the-same-network) for workarounds) |
| Internet on the robot | HTTPS only (time servers and ping are blocked) | None |

Ways to find the robot's address in university mode (most useful first):

1. **Read the robot's display.** It always shows the current address.
2. **Use the name `turtlebot4.local`** instead of an address. This uses mDNS (the robot runs avahi) and works out of the box on Windows 10 and later, macOS and most Linux systems. It also works on the robot's own Wi-Fi. As of 2026-10-03 avahi on the robot is limited to `wlan0`, so the name returns only the Wi-Fi address. On 2026-10-04 the name failed to resolve now and then on the campus Wi-Fi (mDNS is unreliable there), so if it fails, use the display address (method 1).
3. **From a computer with ROS 2 Jazzy on the same network** (Fast DDS, `ROS_DOMAIN_ID` 0):

   ```bash
   ros2 topic echo --once /ip
   ```

   Running ROS 2 on a laptop against the robot over campus Wi-Fi had not been tested as of 2026-10-03 (still untested on 2026-10-10), so treat this method as unverified.
4. **If you already have a shell on the robot:**

   ```bash
   hostname -I
   ```

Other campus networks (`AU-Students`, WPA2-Enterprise, and `AU-Students-WIFI`, open with a login page) are not configured on the robot. Whether a computer on those networks can reach the robot has not been tested, so use `Students`.

## Step 3: Connect your computer to the same network

### If the robot is on the university Wi-Fi (`10.87.x.x`)

Join `Students` on your computer as you normally would. Nothing else is needed: devices on `Students` can reach each other.

### If the robot is on its own Wi-Fi (`10.42.0.1`)

1. Join the Wi-Fi network `Turtlebot4` and type its password.
2. On Windows, a box may ask for an 8-digit PIN from the router label. That is a WPS screen, not the robot's password. Click **Connect using a security key instead** and type the password.
3. Your computer gets a `10.42.0.x` address. This network has no internet.
4. With a single Wi-Fi card, your computer loses internet while it is on `Turtlebot4`. To keep internet, give your computer a second connection: a second (USB) Wi-Fi adapter, wired Ethernet, or USB tethering from a phone. Join `Turtlebot4` on one connection and keep the other for internet.
5. When you finish, reconnect to your normal network.

## Step 4: Open a terminal and connect

### Open a terminal

| System | How to open a terminal |
|---|---|
| Windows 10 or 11 | Open the Start menu, type `PowerShell` (or `Terminal` on Windows 11) and press Enter. If you later see "ssh is not recognized", add **OpenSSH Client** under **Optional features** in Windows Settings. |
| macOS | Press Cmd+Space, type `Terminal` and press Enter. |
| Linux | Press Ctrl+Alt+T (Ubuntu), or open **Terminal** from the applications menu. |

### Connect

The command is the same on all three systems. Use the name:

```bash
ssh ubuntu@turtlebot4.local
```

Or use the address from the display. On the robot's own Wi-Fi:

```bash
ssh ubuntu@10.42.0.1
```

On the university Wi-Fi, replace the example address with the one on the display:

```bash
ssh ubuntu@10.87.10.205
```

On the campus Wi-Fi the address is the more reliable choice: since 2026-10-04 the name has failed now and then. If the connection works for a moment and then drops, see [The robot answers only sometimes](#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found).

### What you will see

1. **The first time** you connect with a given name or address, SSH asks whether to trust the robot:

   ```text
   The authenticity of host 'turtlebot4.local (10.87.10.205)' can't be established.
   ED25519 key fingerprint is SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4.
   Are you sure you want to continue connecting (yes/no/[fingerprint])?
   ```

   Check that the fingerprint is exactly `SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4` (the lab robot's key, recorded 2026-10-04; the same for every name and address of the robot). If it matches, type `yes` and press Enter. If it does not match, type `no`: you have reached a different device (campus addresses change) or the robot was reinstalled. Ask the lab maintainer before typing any password. A maintainer can read the current value on the robot with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, and must update it here after a reinstall.
2. **The password prompt** (`ubuntu@turtlebot4.local's password:`). Type the `ubuntu` password and press Enter. Nothing appears on screen while you type; that is normal.
3. **The robot's prompt**, `ubuntu@turtlebot4:~$`. Every command you type now runs on the robot. ROS 2 is loaded automatically in the robot's interactive shells, so `ros2` commands work straight away. A quick check (ROS 2 command-line calls take 30 to 60 s on the Pi):

   ```bash
   ros2 topic list
   ```

### Log out

```bash
exit
```

(Ctrl+D does the same.) Programs you started normally in that session stop when you log out or when the connection drops. For long or moving tasks, [run them detached](#moving-the-robot-run-motion-scripts-detached).

## Recommended: log in with a key instead of a password

An SSH key lets your computer log in without the password, which also makes VS Code much smoother. Do this once per computer. You need the `ubuntu` password one last time, in step 2.

### 1. Create a key just for the robot

At the passphrase prompt, press Enter twice for no passphrase, or set one (you will then type the passphrase instead of the robot password).

Linux and macOS:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/turtlebot4_ed25519
```

Windows (PowerShell):

```powershell
mkdir -Force $env:USERPROFILE\.ssh
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\turtlebot4_ed25519
```

On Windows, write `$env:USERPROFILE` rather than `~` in `ssh-keygen` and `type` commands: Windows PowerShell does not expand `~` for them.

### 2. Install the public key on the robot

Linux and macOS:

```bash
ssh-copy-id -i ~/.ssh/turtlebot4_ed25519.pub ubuntu@turtlebot4.local
```

Windows has no `ssh-copy-id`. Instead:

1. Print your public key:

   ```powershell
   type $env:USERPROFILE\.ssh\turtlebot4_ed25519.pub
   ```

   It is one line that starts with `ssh-ed25519`. Select the whole line and copy it.
2. Run this command, replacing `PASTE-KEY-HERE` with the line you copied (keep the single quotes around it):

   ```powershell
   ssh ubuntu@turtlebot4.local "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo 'PASTE-KEY-HERE' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
   ```

   Pasting the key avoids a Windows line-ending problem that piping the file into `ssh` would cause.

If `turtlebot4.local` does not work, use the address from the display in these commands.

### 3. Log in with the key

Linux and macOS:

```bash
ssh -i ~/.ssh/turtlebot4_ed25519 ubuntu@turtlebot4.local
```

Windows (PowerShell):

```powershell
ssh -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 ubuntu@turtlebot4.local
```

If no password is asked for, the key works. To avoid typing `-i ...` every time, [save a shortcut in your SSH config](#optional-save-a-shortcut-in-your-ssh-config).

Keep the private key file (the one without `.pub`) on your own computer only, and never commit it to a repository. To remove your access later, delete your key's line from `~/.ssh/authorized_keys` on the robot.

## Write and run code

The `ubuntu` account is shared by everyone who uses the robot. Keep your own work in a clearly named folder and do not change other people's files.

### Option A: VS Code Remote-SSH (recommended for editing)

1. Install VS Code and Microsoft's **Remote - SSH** extension.
2. Add these recommended user settings (press F1, choose **Preferences: Open User Settings (JSON)**, and add the two lines inside the outer braces, with a comma after the entry before them if there is one):

   ```json
   "remote.SSH.localServerDownload": "always",
   "remote.SSH.connectTimeout": 30
   ```

   The first makes your computer download the VS Code server and copy it to the robot, so the robot does not need internet access itself. The second gives slow campus Wi-Fi more time.
3. Press F1 (Cmd+Shift+P on macOS), choose **Remote-SSH: Connect to Host...** and type:

   ```text
   ubuntu@turtlebot4.local
   ```

   (or `ubuntu@` followed by the address on the display). If you saved the [SSH config shortcut](#optional-save-a-shortcut-in-your-ssh-config), pick `turtlebot4` from the list or from the Remote Explorer side bar instead.
4. If VS Code asks for the platform of the remote host, choose **Linux**. Without a key, it asks for the `ubuntu` password (sometimes more than once).
5. The first connection downloads about 200 MB and installs the VS Code server on the robot (about 600 MB once unpacked, in `~/.vscode-server`). On campus Wi-Fi this can take about 10 minutes. Later connections take seconds.
6. Choose **File > Open Folder** and open `/home/ubuntu/robot_code`. **Terminal > New Terminal** (Ctrl+`) opens a terminal that runs on the robot.

If the robot runs short of disk space, `~/.vscode-server` is safe to delete; VS Code installs it again on the next connection.

### Option B: write code on your computer and copy it

Copy one file into `~/robot_code` on the robot:

```bash
scp myfile.py ubuntu@turtlebot4.local:robot_code/
```

Copy a whole folder:

```bash
scp -r myproject ubuntu@turtlebot4.local:robot_code/
```

Add `-i` and your key path as with `ssh`, or use the [SSH config shortcut](#optional-save-a-shortcut-in-your-ssh-config). Copying from your computer always works, even while the robot's clock is wrong.

### Option C: Git on the robot

On the university Wi-Fi the robot can reach GitHub over HTTPS, so `git clone https://github.com/...` can work. However, as of 2026-10-03 the robot's clock is often wrong (see [Known issues](#known-issues)), and then `git`, `pip` and `apt` fail with certificate errors such as "not yet valid". If that happens, use Option A or B. On the robot's own Wi-Fi there is no internet at all.

### Run the examples

Copies of the six programs in the table below are in `~/robot_code` on the robot (`motion_shapes.py` may be an older version than the repository's). The newer programs in [`examples/`](examples/) (`health_check.py`, `sensor_report.py` and others) were not on the robot as of 2026-10-10; copy them first as described in [examples/README.md](examples/README.md#copy-the-files-to-the-robot). In a terminal on the robot:

```bash
cd ~/robot_code
python3 hello_robot.py
```

ROS programs are slow to start on the Raspberry Pi: allow 10 to 20 s before deciding a program does nothing, and 30 to 60 s for `ros2` command-line calls.

| Example | What it does | When it works |
|---|---|---|
| `hello_robot.py` | Shows a text message on the robot's display and turns the light ring green for 5 s. Edit `MESSAGE` at the top to change the text. | Any time, including on the dock. Does not move the robot. |
| `scan_test.py` | Prints the distance to the nearest object the lidar sees, until you press Ctrl+C. | Only off the dock: the robot powers the lidar down while docked. Needs a working lidar (see [Known issues](#known-issues)). |
| `clearance_check.py` | Takes one lidar scan and prints the nearest object within ±30° of straight ahead. Exit code 0 if the way is clear, 1 if something is closer than the limit, 2 if no scan arrived. Run as `python3 clearance_check.py 0.6` (limit in metres; 0.6 if left out). | Off the dock, with a working lidar. Does not move the robot. |
| `drive_test.py` | Drives forward 20 cm at 0.1 m/s, then stops. | Off the dock, with about 1 m clear in front. **It moves the robot.** |
| `motion_test.sh` | Full movement test: undocks, checks the way ahead with `clearance_check.py`, drives forward 20 cm only if it is clear, spins 360° with the built-in `rotate_angle` action, then docks again. | Start on the dock, with space around it. **It moves the robot.** Run it detached (below). |
| `motion_shapes.py` | Drives a square, triangle, 360° rotation, back-and-forth or figure eight using odometry, and stops for obstacles in front, bumps, stalls, timeouts or a `~/STOP` file. Speed capped at 0.15 m/s. | Off the dock, 1 m clear all round. **It moves the robot.** Dry run first, then run it detached. Full instructions: [examples/README.md](examples/README.md). |

Status on 2026-10-03: `motion_test.sh` undocked, spun and docked successfully (docking needed a re-send after the SSH session dropped). The forward drive was skipped because there was no lidar data.

Status on 2026-10-04: the lidar works again, and `motion_shapes.py` drove a square, a 360° rotation, a back-and-forth run and (after a second odometry fix) a triangle; a figure eight aborted on a 2.0 s odometry gap with the robot held still (results in [docs/test-results.html](docs/test-results.html)). `motion_test.sh` has not been rerun yet.

Status on 2026-10-10: no robot runs since 2026-10-04. Since the afternoon of 2026-10-04 the robot has not been reachable reliably over Wi-Fi ([Troubleshooting](#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found)). Moving tests are run supervised, in short batches, with a person next to the robot. Step-by-step instructions for every example, including how to stop the robot, are in [examples/README.md](examples/README.md); how `motion_shapes.py` works is in [docs/motion-program-design.html](docs/motion-program-design.html).

When you write your own scripts: ROS is loaded automatically only in interactive shells. A script started in another way (for example `ssh ubuntu@turtlebot4.local "bash myscript.sh"`) should begin with `source /etc/turtlebot4/setup.bash`, as `motion_test.sh` does. The [Developer quick reference](#developer-quick-reference) lists the topics and actions.

### Moving the robot: run motion scripts detached

While the robot moves, it can briefly drop off the campus Wi-Fi as it switches between access points. That ends your SSH session, and a running `ros2 action send_goal` is cancelled, so the move is left unfinished. (This happened on 2026-10-03 just as docking started.)

So run motion scripts detached on the robot. They keep going if SSH drops:

```bash
setsid nohup bash ~/robot_code/motion_test.sh > ~/robot_code/motion.log 2>&1 &
```

Watch the progress:

```bash
tail -f ~/robot_code/motion.log
```

Press Ctrl+C to stop watching; the script keeps running. Running the script inside `tmux` is another option.

If the robot is left off its dock, send it home the same way:

```bash
setsid nohup ros2 action send_goal /dock irobot_create_msgs/action/Dock "{}" > ~/robot_code/dock.log 2>&1 &
```

## Turning the robot off

Leaving the robot on its dock is fine: it is designed to sit there charging.

To power it off completely (the procedure used successfully on 2026-10-03):

1. In an SSH session on the robot, shut down the Raspberry Pi. It asks for the `ubuntu` password, and your SSH session ends.

   ```bash
   sudo poweroff
   ```

2. Wait about 20 s.
3. Lift the robot off the dock.
4. Press and hold the base's power button (the centre of the light ring) for about 7 to 10 s, until the light ring turns off.

Always shut down the Pi before cutting power, so its SD card is not damaged. The official procedure is in the "powering off" steps of the [TurtleBot 4 user manual](https://turtlebot.github.io/turtlebot4-user-manual/). To turn the robot on again, place it on the dock ([Step 1](#step-1-turn-the-robot-on)).

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Display stays blank, or no chime after a few minutes | The robot is off or still starting | Make sure it sits properly on the dock, then wait 2 minutes. |
| Display shows `10.42.0.1` | `Students` was not available, so the robot fell back to its own Wi-Fi | Join `Turtlebot4` ([Step 3](#step-3-connect-your-computer-to-the-same-network)) and run `ssh ubuntu@10.42.0.1`. |
| `Could not resolve hostname turtlebot4.local`, or the name hangs | mDNS is not working on your computer or network (on the campus Wi-Fi it has failed now and then since 2026-10-04), or your computer is on a different network | Connect by the address on the display instead, for example `ssh ubuntu@10.87.10.205`. Check that your computer is on `Students`. See [below](#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found). |
| `Connection timed out` or `No route to host` | Your computer and the robot are on different networks, the robot is still starting, or the robot has dropped off the Wi-Fi (seen on 2026-10-04 and 2026-10-05) | Check both are on the same network (other campus networks were not tested). Put the robot back on the dock and wait 2 minutes. If it still fails, see [below](#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found). |
| SSH works for a few seconds or a minute, then freezes or times out; the robot answers only sometimes | The robot drops off the Wi-Fi. Likely cause: Wi-Fi power saving on the robot (not confirmed; fix proposed, not applied as of 2026-10-10) | Connect by the display address and retry; keep sessions short and run long jobs detached. Details [below](#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found). |
| Windows asks for an 8-digit PIN when joining `Turtlebot4` | That is the WPS screen | Click **Connect using a security key instead** and type the Wi-Fi password. |
| No internet while joined to `Turtlebot4` | The robot's Wi-Fi has no internet | Use a second connection for internet (USB Wi-Fi adapter, Ethernet or phone tethering). |
| After leaving `Turtlebot4`, downloads fail with `ENOTFOUND` | Your computer still uses the robot (`10.42.0.1`) as its DNS server | Make sure the adapter shows Disconnected from `Turtlebot4`, then try again. |
| `Permission denied` | Wrong password, or your key is not installed | Retype the password (nothing shows while typing). Repeat the [key setup](#recommended-log-in-with-a-key-instead-of-a-password). Ask the lab maintainer if the password was changed. |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` | The robot was reinstalled, or that address now belongs to another device | Confirm with the lab maintainer, then remove the old entry with `ssh-keygen -R turtlebot4.local` (or the address) and connect again. |
| The name reaches a different robot | Another TurtleBot 4 with the default hostname is on the same network | Connect by the address on this robot's display. |
| VS Code times out on the first connection | The first connection downloads about 200 MB over slow Wi-Fi | Add the [recommended settings](#option-a-vs-code-remote-ssh-recommended-for-editing) and try again; allow about 10 minutes. |
| SSH drops while the robot moves; the robot stops mid-task | Wi-Fi roaming between campus access points | Run motion scripts [detached](#moving-the-robot-run-motion-scripts-detached). Send the dock command again if needed. |
| A ROS program prints nothing for a while | ROS starts slowly on the Pi | Wait 10 to 20 s (30 to 60 s for `ros2` command-line calls). |
| `hello_robot.py` says it could not find the robot screen or light ring | The robot software has not finished starting | Wait a minute and run it again. |
| `scan_test.py` or `clearance_check.py` get no data | The robot is on the dock (lidar powered down), or the lidar is not detected | Undock first. See [Known issues](#known-issues). |
| `/dock_status` or `/battery_state` stop arriving; dock and undock commands time out | The Create 3 base application is stuck | [Restart the base application](#restart-the-create-3-base-application). |
| `git`, `pip` or `apt` fail with certificate or "not yet valid" errors | The robot's clock is wrong | Copy code from your computer (VS Code or `scp`). See [Known issues](#known-issues). |

### The robot answers only sometimes, drops off the Wi-Fi, or `turtlebot4.local` is not found

Added 2026-10-10. **What was seen.** On 2026-10-04 (about 15:42 robot time) the robot answered SSH once after being switched on, then dropped off the network and did not come back during about 25 minutes. On 2026-10-05 SSH by address and by key worked for about a minute, then the robot answered only in short windows of about 10 to 40 s. The laptop's Wi-Fi was fine the whole time, so the problem is on the robot's side. `turtlebot4.local` also failed to resolve now and then. The likely cause is Wi-Fi power saving on the robot; this is a diagnosis, not confirmed, and the proposed fix had **not been applied** as of 2026-10-10. Full record: [MAINTENANCE.md](MAINTENANCE.md#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05) and [docs/network-and-connectivity.html](docs/network-and-connectivity.html).

**What you can do:**

1. **Check your own connection first.** On `Students`, open any website. If that fails too, the problem is on your side; fix that first.
2. **Use the address on the robot's display, not the name.** For example `ssh ubuntu@10.87.10.205` on `Students`; read the current address on the display, because it can change. The name depends on mDNS, which is unreliable on the campus Wi-Fi.
3. **Retry.** The robot answers in short windows, so a connection that timed out can work a few seconds later. The loops below reconnect until you log out normally. ssh exits with code 255 when it cannot connect or the connection is lost, and `ServerAliveInterval=10` makes it notice a dead connection after about 30 s (three missed replies). Set up [key login](#recommended-log-in-with-a-key-instead-of-a-password) first, so you do not type the password at every attempt. Replace the example address with the one on the display; press Ctrl+C to stop trying.

   macOS and Linux (also Git Bash on Windows):

   ```bash
   while true; do ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; [ $? -ne 255 ] && break; sleep 5; done
   ```

   Windows PowerShell:

   ```powershell
   while ($true) { ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; if ($LASTEXITCODE -ne 255) { break }; Start-Sleep 5 }
   ```

4. **Keep sessions short and run long jobs detached** ([Moving the robot](#moving-the-robot-run-motion-scripts-detached)), so a drop does not stop your program. Copy files one at a time with `scp` and check they arrived.
5. **Use the robot's own Wi-Fi when it is on it.** When the display shows `10.42.0.1`, join `Turtlebot4` ([Step 3](#step-3-connect-your-computer-to-the-same-network)). To keep internet at the same time, your computer needs a second Wi-Fi adapter (or Ethernet, or phone tethering).
6. **If nothing answers for several minutes,** put the robot on its dock, check that the display shows an address, and tell the lab maintainer. Do not change the robot's Wi-Fi settings yourself.

**What an admin can do** (needs the `ubuntu` password, so a person who knows it):

- Apply and verify the proposed fix, which turns Wi-Fi power saving off in the robot's `Students` profile. Commands, verify and undo: [MAINTENANCE.md](MAINTENANCE.md#incident-robot-drops-off-the-wi-fi-2026-10-04-and-2026-10-05); task and acceptance test: [ROADMAP.md, TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving).
- Decide whether the robot should use the lab router instead, with a fixed address and no campus roaming ([ROADMAP.md, TB-21](ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router)). This is a proposal: as of 2026-10-10 the robot is **not** on the lab router, so do not look for it there.
- Record any change in [MAINTENANCE.md](MAINTENANCE.md) with verify and undo steps.

### Restart the Create 3 base application

Check whether the base (the round part with the wheels) is answering. In a terminal on the robot:

```bash
timeout 60 ros2 topic echo --once /dock_status
```

If nothing prints, restart the base application first, before trying anything else:

```bash
curl -X POST http://192.168.186.2/api/restart-app
```

Wait for the chime (about a minute), then run the check again.

- This is the same as the **Restart Application** button on the base's own web page, `http://192.168.186.2` (port 80; port 8080 does not answer). The page is reachable only from the robot, not from your computer.
- Background: the base only talks to ROS when the Pi's clock and the base's clock agree. Restarting the base application makes it re-sync its clock from the Pi. Details are in [MAINTENANCE.md](MAINTENANCE.md).
- On 2026-10-03 this fixed a stuck base. Restarting `turtlebot4.service` alone had not.

## Known issues

As of 2026-10-10 (current status and full details in [MAINTENANCE.md](MAINTENANCE.md)):

- **The robot drops off the Wi-Fi (since 2026-10-04).** It answers SSH only for short periods. Fix proposed, not applied. Connect by the display address and retry: see [Troubleshooting](#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found).
- **`turtlebot4.local` is unreliable on the campus Wi-Fi (since 2026-10-04).** Use the address on the robot's display.
- **Lidar: fixed on 2026-10-04.** From 2026-10-03 to 2026-10-04 the lidar was not detected on USB because its USB cable was loose; reseating it fixed it. It was on USB again after a later power-on that day. If `/scan` is silent, first check that the robot is off the dock (the lidar is switched off on the dock), then that `ls /dev/RPLIDAR` works. The diagnosis is in [docs/LIDAR-FINDINGS.md](docs/LIDAR-FINDINGS.md).
- **`/odom` can pause for up to about 1 s when the wheels start moving** (found on 2026-10-04). If your program stops when odometry is late, allow for this; `motion_shapes.py` holds still and waits.
- **The robot's clock can be wrong.** The campus network blocks internet time servers (NTP), so the robot has no internet time source (on 2026-10-03 it said October 2024). Until the clock is right, `git`, `pip` and `apt` can fail with certificate errors; copy code from your computer instead. A clock fix installed on 2026-10-03 caused the Create 3 base to stop talking to ROS, and its removal is planned. Do not change the robot's clock by a large amount while ROS is running.

## Developer quick reference

Middleware: Fast DDS, `ROS_DOMAIN_ID` 0. Check any topic's type on the robot with `ros2 topic info <topic>`.

| Topic | Type | Notes |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/TwistStamped` | Not `Twist`. An unstamped variant, `/cmd_vel_unstamped`, also exists. See `drive_test.py`. |
| `/scan` | `sensor_msgs/msg/LaserScan` | Subscribe with `qos_profile_sensor_data`, or no messages arrive. No data while docked. |
| `/odom` | `nav_msgs/msg/Odometry` | Wheel odometry |
| `/battery_state` | `sensor_msgs/msg/BatteryState` | |
| `/dock_status` | `irobot_create_msgs/msg/DockStatus` | Field `is_docked` |
| `/ip` | `std_msgs/msg/String` | The robot's current IP address |
| `/hmi/display/message` | `std_msgs/msg/String` | Shows text on the display. See `hello_robot.py`. |
| `/cmd_lightring` | `irobot_create_msgs/msg/LightringLeds` | Six LEDs; set `override_system` to take control. See `hello_robot.py`. |

| Action | Type | Example goal |
|---|---|---|
| `/undock` | `irobot_create_msgs/action/Undock` | `"{}"` |
| `/dock` | `irobot_create_msgs/action/Dock` | `"{}"` |
| `/rotate_angle` | `irobot_create_msgs/action/RotateAngle` | `"{angle: 6.283, max_rotation_speed: 0.6}"` (one full turn) |

The other Create 3 actions are listed by `ros2 action list`. Useful commands on the robot:

```bash
ros2 topic list
ros2 topic info /cmd_vel
timeout 60 ros2 topic echo --once /battery_state
ros2 action list
ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}"
ros2 action send_goal /rotate_angle irobot_create_msgs/action/RotateAngle "{angle: 6.283, max_rotation_speed: 0.6}"
```

In Python, subscribe to the lidar like this (from `scan_test.py`):

```python
from rclpy.qos import qos_profile_sensor_data
self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
```

## Optional: save a shortcut in your SSH config

An SSH config file lets you type `ssh turtlebot4` instead of the full command, and makes the robot appear in VS Code's Remote Explorer. This is a convenience on your own computer; the robot does not need it.

The file is `~/.ssh/config` on macOS and Linux, and `C:\Users\<your user>\.ssh\config` on Windows (no file extension). The easiest way to open or create it is in VS Code: press F1, choose **Remote-SSH: Open SSH Configuration File...**, and pick the file in your user folder. Add:

```text
Host turtlebot4
    HostName turtlebot4.local
    User ubuntu
    IdentityFile ~/.ssh/turtlebot4_ed25519

Host turtlebot4-ap
    HostName 10.42.0.1
    User ubuntu
    IdentityFile ~/.ssh/turtlebot4_ed25519
```

`~` works inside this file on Windows too. Leave out the `IdentityFile` lines if you did not create a key. Then:

```bash
ssh turtlebot4
```

```bash
scp myfile.py turtlebot4:robot_code/
```

Use `turtlebot4-ap` when you want the fixed address on the robot's own Wi-Fi (`turtlebot4` works there too). If the name does not resolve, change `HostName` to the address on the display.

## Remote desktop

Remote desktop (RDP or VNC) is not set up. The robot runs Ubuntu Server with no desktop, and adding one would take memory and CPU the robot needs (the camera alone already uses about one CPU core). VS Code Remote-SSH gives a full editor without it. For viewing sensor data, the preferred direction is to run RViz or Foxglove on your own computer rather than on the robot. A remote desktop option is evaluated in [ROADMAP.md](ROADMAP.md).

## Admin tasks

Anything that uses `sudo` (shutting down, changing Wi-Fi, installing packages) asks for the `ubuntu` password, which a person must type. Wi-Fi changes over SSH need it too. Configuration changes to the shared robot are recorded in [MAINTENANCE.md](MAINTENANCE.md), together with the admin scripts in [`setup/`](setup/) and how to undo each change. Read it before changing anything, and record your own changes there.

Open admin work on the network (2026-10-10): the Wi-Fi power-saving fix ([ROADMAP.md, TB-20](ROADMAP.md#tb-20-fix-the-robot-wi-fi-drops-wi-fi-power-saving)), the decision on the robot's network ([TB-21](ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router)) and securing the lab router ([TB-22](ROADMAP.md#tb-22-secure-the-lab-router)). These are proposals; nothing was changed on the robot for them.

## Related documents

| Document | What it is for |
|---|---|
| [README.md](README.md) | Index of this folder |
| [MAINTENANCE.md](MAINTENANCE.md) | Configuration record: every change made to the robot (with verify and undo steps), the incident report about the clock and the Create 3 base, known issues, the admin scripts, and the original author's laptop-specific setup |
| [ROADMAP.md](ROADMAP.md) | Plan for the next iterations, including remote desktop |
| [turtlebot4-field-guide.html](turtlebot4-field-guide.html) | Beginner overview of the TurtleBot 4 hardware and ROS 2 (open it in a browser) |
| [TurtleBot4 - connect to university Wi-Fi.txt](../General%20Tasks/TurtleBot4%20-%20connect%20to%20university%20Wi-Fi.txt) | Step-by-step log of the 2026-10-03 setup, including what failed |
| [TurtleBot4 - lidar check and motion programs.txt](../General%20Tasks/TurtleBot4%20-%20lidar%20check%20and%20motion%20programs.txt) | Log of the 2026-10-04 lidar check and motion program work, including what failed |
| [TurtleBot4 - network and connectivity.txt](../General%20Tasks/TurtleBot4%20-%20network%20and%20connectivity.txt) | Log of the Wi-Fi drops, the lab router and the repository incident (2026-10-04 evening to 2026-10-10), including what failed |
| [examples/README.md](examples/README.md) | How to run the example programs safely, including `motion_shapes.py` |
| [docs/index.html](docs/index.html) | Illustrated pages: lidar diagnosis, motion program design, test results, network and connectivity |
| [docs/network-and-connectivity.html](docs/network-and-connectivity.html) | The networks around the robot, the Wi-Fi drops of 2026-10-04 and 2026-10-05, workarounds, and the lab router proposal. Markdown version: [docs/NETWORK-FINDINGS.md](docs/NETWORK-FINDINGS.md) |
| [TurtleBot 4 user manual](https://turtlebot.github.io/turtlebot4-user-manual/) | Official documentation: setup, specifications, power on and off, tutorials |
