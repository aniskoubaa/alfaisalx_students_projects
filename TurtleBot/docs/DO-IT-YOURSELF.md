# Do it yourself: use the TurtleBot 4 on your own

> **Interactive version** (OS switcher, copy buttons, command builder, troubleshooting finder): [do-it-yourself.html](do-it-yourself.html). Download the repository and open it in a browser; GitHub shows HTML only as source. This Markdown page has the same steps and commands. Back to the [docs index](index.html).

Use the lab's TurtleBot 4 on your own, from a fresh Windows, macOS or Linux computer, with no AI help. Eleven steps: power on, Wi-Fi, SSH, your code, sensors, driving, stopping, power off, and your first program. Facts as of 2026-10-10. Full background: [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md).

Commands that differ by system are given twice: a PowerShell block for Windows and a Terminal block for macOS and Linux. Commands marked **Not yet tested on this robot** follow the official definitions but have not been run on this robot. Replace the example address `10.87.10.205` with the address shown on the robot's display (the interactive version does this for you).

## Before you start

You need a computer with Wi-Fi and an SSH client (Windows 10 and 11, macOS and most Linux systems already have `ssh`), the Wi-Fi password for the network the robot is on, and the robot's `ubuntu` password. Ask the lab maintainer for both passwords; they are never written in this repository. Optional: [VS Code](https://code.visualstudio.com/) with the Remote - SSH extension.

**Five safety rules for anything that moves**

- Speed never above **0.15 m/s**. The page's command builder cannot go higher.
- About **1 m of clear floor** all round the robot: no cables, bags, feet or table legs, no stairs or drop-offs.
- **A person stands next to the robot** the whole time it moves.
- To stop the robot at any moment: **pick it up**. The wheels stop when it is lifted. Other ways are in [step 9](#step-9-stop-the-robot-safely).
- Wi-Fi can drop while the robot drives. Long or moving jobs are safer [run detached](../HOW-TO-CONNECT.md#moving-the-robot-run-motion-scripts-detached).

**Contents**

1. [Step 1: Turn the robot on and read its address](#step-1-turn-the-robot-on-and-read-its-address)
2. [Step 2: Join the right Wi-Fi](#step-2-join-the-right-wi-fi)
3. [Step 3: Connect over SSH](#step-3-connect-over-ssh)
4. [Step 4: Optional: log in with a key (one time per computer)](#step-4-optional-log-in-with-a-key-one-time-per-computer)
5. [Step 5: Get your code onto the robot](#step-5-get-your-code-onto-the-robot)
6. [Step 6: Run a program](#step-6-run-a-program)
7. [Step 7: Look at the sensors](#step-7-look-at-the-sensors)
8. [Step 8: Undock, drive, rotate and dock](#step-8-undock-drive-rotate-and-dock)
9. [Step 9: Stop the robot safely](#step-9-stop-the-robot-safely)
10. [Step 10: Turn the robot off safely](#step-10-turn-the-robot-off-safely)
11. [Step 11: Write your first program](#step-11-write-your-first-program)
12. [Command builder: drive and rotate](#command-builder-drive-and-rotate)
13. [Troubleshooting](#troubleshooting)

## Step 1: Turn the robot on and read its address

Place the robot on its charging dock. The dock must be plugged into power. The robot switches on by itself.

Wait about 2 minutes. When the robot is ready it plays a chime and its **address** appears on the OLED display on top.

| The display shows | Which Wi-Fi your computer joins | Address you use |
|---|---|---|
| `10.87.x.x` (for example `10.87.10.205`) | `Students` (the university Wi-Fi) | The address on the display. It comes from DHCP and can change, so read it again each day. |
| `10.42.0.1` | `Turtlebot4` (the robot's own Wi-Fi, 5 GHz) | Always `10.42.0.1`. This network has no internet. |

Write the address down, then type it into the **Robot address** box at the top of this page. Every command below then contains your address.

> **If it stays blank.** Nothing on the display or no chime after a few minutes: check that the robot sits properly on the dock, wait 2 more minutes, and then tell the lab maintainer.

## Step 2: Join the right Wi-Fi

- **Display shows `10.87.x.x`:** join `Students` on your computer as you normally would (one shared university password). Nothing else is needed.
- **Display shows `10.42.0.1`:** join `Turtlebot4` and type its password. Your computer gets a `10.42.0.x` address.

Ask the lab maintainer for the passwords. They are never written in this repository.

- On Windows, a box may ask for an 8-digit PIN. That is a WPS screen, not the password: click **Connect using a security key instead**.
- `Turtlebot4` has no internet. With one Wi-Fi card your computer loses internet while it is joined; to keep internet, use a second connection (USB Wi-Fi adapter, Ethernet or phone tethering).
- When you finish, reconnect to your normal network.

Details: [Step 3 in HOW-TO-CONNECT](../HOW-TO-CONNECT.md#step-3-connect-your-computer-to-the-same-network).

## Step 3: Connect over SSH

#### Open a terminal

| System | How |
|---|---|
| Windows 10 or 11 | Start menu, type `PowerShell` (or `Terminal` on Windows 11), press Enter. If you later see "ssh is not recognized", add **OpenSSH Client** under **Optional features** in Windows Settings. |
| macOS | Press Cmd+Space, type `Terminal`, press Enter. |
| Linux | Press Ctrl+Alt+T (Ubuntu) or open **Terminal** from the applications menu. |

#### Connect by the address

Use the address from the display. It is the same command on all three systems:

**On your computer (any system):**

```bash
ssh ubuntu@10.87.10.205
```

The name `turtlebot4.local` also exists, but on the campus Wi-Fi it has failed now and then since 2026-10-04. Use the address first, and the name only as a second try:

**On your computer (any system):**

```bash
ssh ubuntu@turtlebot4.local
```

On the robot's own Wi-Fi the address is always `10.42.0.1`:

**On your computer (any system):**

```bash
ssh ubuntu@10.42.0.1
```

#### The first time: the fingerprint question

The first time you connect to a name or address, SSH asks whether to trust the robot. It looks like this:

What you see:

```text
The authenticity of host 'turtlebot4.local (10.87.10.205)' can't be established.
ED25519 key fingerprint is SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Compare the fingerprint on your screen, character by character, with this one (the lab robot's key, recorded 2026-10-04, the same for every name and address of the robot):

**Expected fingerprint:**

```text
SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4
```

Compare it with the expected line above. If it is exactly the same, type `yes`.

- **It matches:** type `yes` and press Enter.
- **It does not match:** type `no`. You reached a different device (campus addresses change) or the robot was reinstalled. Ask the lab maintainer before typing any password.

#### Password and prompt

SSH asks for the `ubuntu` password. Type it and press Enter. Nothing appears while you type; that is normal. Ask the lab maintainer for the password.

When the prompt reads `ubuntu@turtlebot4:~$`, you are on the robot: every command you type now runs there. To leave:

**On the robot (after `ssh`):**

```bash
exit
```

#### When it does not answer: retry

Since 2026-10-04 the robot sometimes drops off the campus Wi-Fi and answers only in short windows of 10 to 40 seconds. Check your own Wi-Fi first (open any website), use the display address, and retry. This loop reconnects until you log out normally (ssh exits with code 255 when it cannot connect). Press Ctrl+C to stop trying. Set up [key login](#step-4-optional-log-in-with-a-key-one-time-per-computer) first so you do not type the password at every attempt.

**On your computer, macOS or Linux (Terminal):**

```bash
while true; do ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; [ $? -ne 255 ] && break; sleep 5; done
```

**On your computer, Windows (PowerShell):**

```powershell
while ($true) { ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; if ($LASTEXITCODE -ne 255) { break }; Start-Sleep 5 }
```

If nothing answers for several minutes, put the robot on its dock, check that the display shows an address, and tell the lab maintainer. Do not change the robot's Wi-Fi settings yourself. More: [HOW-TO-CONNECT, the robot answers only sometimes](../HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found), or use the [troubleshooting finder](#troubleshooting) below.

## Step 4: Optional: log in with a key (one time per computer)

An SSH key lets your computer log in without the password, which also makes VS Code and `scp` much smoother. You need the `ubuntu` password one last time, in part 2.

#### 1. Create a key just for the robot

At the passphrase prompt press Enter twice for no passphrase, or set one.

**On your computer, macOS or Linux (Terminal):**

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/turtlebot4_ed25519
```

**On your computer, Windows (PowerShell):**

```powershell
mkdir -Force $env:USERPROFILE\.ssh
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\turtlebot4_ed25519
```

**Windows:** On Windows write `$env:USERPROFILE` rather than `~` in these commands: Windows PowerShell does not expand `~` for them.

#### 2. Put the public key on the robot

**On your computer, macOS or Linux (Terminal):**

```bash
ssh-copy-id -i ~/.ssh/turtlebot4_ed25519.pub ubuntu@10.87.10.205
```

**Windows:** Windows has no `ssh-copy-id`. First print the public key. It is one line starting with `ssh-ed25519`; select it and copy it:

**On your computer, Windows (PowerShell):**

```powershell
type $env:USERPROFILE\.ssh\turtlebot4_ed25519.pub
```

**Windows:** Then run this, replacing `PASTE-KEY-HERE` with the line you copied (keep the single quotes):

**On your computer, Windows (PowerShell):**

```powershell
ssh ubuntu@10.87.10.205 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo 'PASTE-KEY-HERE' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

#### 3. Log in with the key

**On your computer, macOS or Linux (Terminal):**

```bash
ssh -i ~/.ssh/turtlebot4_ed25519 ubuntu@10.87.10.205
```

**On your computer, Windows (PowerShell):**

```powershell
ssh -i $env:USERPROFILE\.ssh\turtlebot4_ed25519 ubuntu@10.87.10.205
```

If no password is asked for, the key works. Keep the private key file (the one without `.pub`) on your own computer only and never commit it to a repository. To avoid typing `-i ...`, [save a shortcut in your SSH config](../HOW-TO-CONNECT.md#optional-save-a-shortcut-in-your-ssh-config).

> **Optional shortcut.** The [connect tool](../tools/connect/README.md) does the key setup and more with a menu: `TurtleBotConnect.exe` on Windows (double-click; SmartScreen warns because it is not code-signed: **More info**, then **Run anyway**) and `connect-turtlebot.sh` on macOS and Linux. It is an optional shortcut. As of 2026-10-10 it has been tested against a simulated robot only, not yet with the real robot. It refuses any device that does not present the lab robot's host key.

## Step 5: Get your code onto the robot

The `ubuntu` account is shared by everyone. Keep your work in a clearly named file or folder inside `~/robot_code` and do not change other people's files. Pick one of three ways.

#### A. VS Code Remote-SSH (best for editing)

1. Install [VS Code](https://code.visualstudio.com/) and Microsoft's **Remote - SSH** extension.
2. Press F1, choose **Preferences: Open User Settings (JSON)** and add these two lines inside the outer braces (with a comma after the entry before them):

**VS Code user settings:**

```json
"remote.SSH.localServerDownload": "always",
"remote.SSH.connectTimeout": 30
```

1. Press F1 (Cmd+Shift+P on macOS), choose **Remote-SSH: Connect to Host...** and type the line below. If it asks for the platform choose **Linux**; without a key it asks for the password.

**Host to type in VS Code:**

```text
ubuntu@10.87.10.205
```

1. The first connection downloads about 200 MB and can take about 10 minutes on campus Wi-Fi. Later ones take seconds.
2. Choose **File > Open Folder**, open `/home/ubuntu/robot_code`, and use **Terminal > New Terminal** (Ctrl+`) for a terminal that runs on the robot.

#### B. Write on your computer, copy with scp

Run these in a normal terminal on your computer (not inside an SSH session). They work the same on all three systems. One file:

**On your computer (any system):**

```bash
scp myfile.py ubuntu@10.87.10.205:robot_code/
```

A whole folder:

**On your computer (any system):**

```bash
scp -r myproject ubuntu@10.87.10.205:robot_code/
```

Add `-i` and your key path as with `ssh` if you made a key. Copying from your computer works even while the robot's clock is wrong. If a copy stops halfway, connect by the display address and copy again. Check what arrived (on the robot):

**On the robot (after `ssh`):**

```bash
ls -l ~/robot_code
```

#### C. Edit on the robot with nano

Good for a quick change. Log in over SSH, then:

**On the robot (after `ssh`):**

```bash
cd ~/robot_code
nano myfile.py
```

- Type or paste your code. Ctrl+O then Enter saves, Ctrl+X leaves nano.

> **Git on the robot.** Do not use `git clone`, `pip` or `apt` on the robot unless you must. Its clock is often wrong and they then fail with certificate errors ("not yet valid"). Copy from your computer instead. See [Known issues](../HOW-TO-CONNECT.md#known-issues).

## Step 6: Run a program

Log in to the robot first (step 3). Then run a program with `python3`. `hello_robot.py` is safe: it shows a text message on the robot's display and turns the light ring green for 5 seconds. It does not move the robot and works on the dock.

**On the robot (after `ssh`):**

```bash
cd ~/robot_code
python3 hello_robot.py
```

> **Be patient.** ROS programs start slowly on the Raspberry Pi. Wait **10 to 20 seconds** before deciding a program does nothing, and **30 to 60 seconds** for `ros2` command-line calls.

#### Shell scripts need one extra line

ROS 2 is loaded automatically in the robot's interactive shells (the one you get after `ssh`). A script started another way does not have it, so start every script with `source /etc/turtlebot4/setup.bash`. Example `myscript.sh`:

**myscript.sh:**

```bash
#!/bin/bash
source /etc/turtlebot4/setup.bash
ros2 topic list
```

**On the robot (after `ssh`):**

```bash
bash myscript.sh
```

Other programs in `~/robot_code` and what they do: [examples/README.md](../examples/README.md). Newer ones must be copied first ([how](../examples/README.md#copy-the-files-to-the-robot)).

## Step 7: Look at the sensors

These commands only read. They are safe at any time. Run them on the robot.

#### What topics exist

**On the robot (after `ssh`):**

```bash
ros2 topic list
```

#### Battery

**On the robot (after `ssh`):**

```bash
timeout 60 ros2 topic echo --once /battery_state
```

#### Dock status

Look for `is_docked: true` or `false`, and `dock_visible`.

**On the robot (after `ssh`):**

```bash
timeout 60 ros2 topic echo --once /dock_status
```

If nothing prints for a minute, the Create 3 base is stuck: see [Restart the base application](../HOW-TO-CONNECT.md#restart-the-create-3-base-application).

#### Lidar: one line

The lidar is switched off while the robot is on the dock, so undock first (step 8) and wait a few seconds. Then this prints the distance to the nearest object until you press Ctrl+C:

**On the robot (after `ssh`):**

```bash
python3 ~/robot_code/scan_test.py
```

For everything else about the lidar see the [lidar guide](lidar-guide.html) ([Markdown version](LIDAR-GUIDE.md)).

## Step 8: Undock, drive, rotate and dock

> **Safety first.** **This moves the robot.** Before every motion: about 1 m of clear floor all round; a person next to the robot; you know how to stop it ([step 9](#step-9-stop-the-robot-safely)); speed at or below 0.15 m/s. The full checklist is in [examples/README.md](../examples/README.md#safety-checklist-before-anything-moves).

Run the commands on the robot, one at a time, and wait for each to finish (they can take up to a minute). Commands marked "not yet tested on this robot" follow the official Create 3 definitions but have not been run on this robot; try them with extra care.

#### 1. Undock

The robot backs out of the dock and then turns 180 degrees. It fails if it is already undocked. Verified on this robot (2026-10-04).

**On the robot (after `ssh`):**

```bash
ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}"
```

If Wi-Fi may drop, send it detached so it is not cancelled, then read the log (look for `SUCCEEDED`):

**On the robot (after `ssh`):**

```bash
setsid nohup ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}" > ~/robot_code/undock.log 2>&1 &
cat ~/robot_code/undock.log
```

#### 2. Drive by hand, slowly

This publishes a forward speed of 0.1 m/s ten times a second until you press **Ctrl+C**. Be ready to press it. `/cmd_vel` takes `TwistStamped`, not `Twist`.

**On the robot (after `ssh`):**

> Not yet tested on this robot.

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/TwistStamped "{twist: {linear: {x: 0.1}}}"
```

Then send one stop message:

**On the robot (after `ssh`):**

> Not yet tested on this robot.

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/TwistStamped "{}"
```

#### 3. Drive a set distance

`distance` is in metres and `max_translation_speed` in m/s. Keep the distance small and the speed at or below 0.15. Use the [command builder](#command-builder-drive-and-rotate) to make the line for any value.

**On the robot (after `ssh`):**

> Not yet tested on this robot.

```bash
ros2 action send_goal /drive_distance irobot_create_msgs/action/DriveDistance "{distance: 0.2, max_translation_speed: 0.1}"
```

#### 4. Rotate

The angle is in **radians**; positive turns left (counter-clockwise), negative turns right. 3.14159 is a half turn. Verified on this robot (2026-10-04).

**On the robot (after `ssh`):**

```bash
ros2 action send_goal /rotate_angle irobot_create_msgs/action/RotateAngle "{angle: 3.14159, max_rotation_speed: 0.5}"
```

A quarter turn to the left is 1.5708 rad. The [command builder](#command-builder-drive-and-rotate) converts degrees to radians for you.

#### 5. Dock

The robot searches for the dock nearby, aligns and drives on. It fails if it is too far from the dock or already docked, and it cannot find a dock that is not plugged into power. If it is far away, carry it to a spot in front of the dock first. Verified on this robot (2026-10-03).

**On the robot (after `ssh`):**

```bash
ros2 action send_goal /dock irobot_create_msgs/action/Dock "{}"
```

Or detached:

**On the robot (after `ssh`):**

```bash
setsid nohup ros2 action send_goal /dock irobot_create_msgs/action/Dock "{}" > ~/robot_code/dock.log 2>&1 &
cat ~/robot_code/dock.log
```

Check the result (`is_docked: true` means it is on the dock):

**On the robot (after `ssh`):**

```bash
timeout 60 ros2 topic echo --once /dock_status
```

## Step 9: Stop the robot safely

Use whichever is fastest. **Picking the robot up always works**: the Create 3 stops its wheels when lifted.

- **Pick it up.** The wheels stop (wheel drop).
- **Ctrl+C** in the terminal where the command or program runs. For `ros2 topic pub` this stops publishing; follow with the stop message below.
- **The base's power button** also stops everything.
- **The stop message** (zero speed), from any terminal on the robot:

**On the robot (after `ssh`):**

> Not yet tested on this robot.

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/TwistStamped "{}"
```

- **The STOP file**, for the example motion programs (such as `motion_shapes.py`). From any other terminal on the robot (log in again if SSH dropped):

**On the robot (after `ssh`):**

```bash
touch ~/STOP
```

Delete it afterwards, or the next run refuses to start:

**On the robot (after `ssh`):**

```bash
rm ~/STOP
```

- **The stop signal**, for `motion_shapes.py`:

**On the robot (after `ssh`):**

```bash
pkill -INT -f motion_shapes.py
```

- **Connect tool, option 7 (EMERGENCY stop)**: does the STOP file and the stop signals for you. Not yet tested with the real robot.

> **Know what each one stops.** The `~/STOP` file and `pkill` only affect the example motion programs. Your own program (step 11) stops with Ctrl+C or by lifting the robot. If SSH has dropped, log in again, then use the STOP file or the stop message. Run longer motions [detached](../HOW-TO-CONNECT.md#moving-the-robot-run-motion-scripts-detached) so a Wi-Fi drop does not leave them half done.

More: [examples/README.md, How to stop the robot](../examples/README.md#how-to-stop-the-robot).

## Step 10: Turn the robot off safely

Leaving the robot on its dock is fine: it is designed to sit there charging. To switch it off completely (the procedure used successfully on 2026-10-03):

1. In an SSH session on the robot, shut down the Raspberry Pi. It asks for the `ubuntu` password and your SSH session ends.

**On the robot (after `ssh`):**

```bash
sudo poweroff
```

1. Wait about 20 seconds.
2. Lift the robot off the dock.
3. Press and hold the base's power button (the centre of the light ring) for about 7 to 10 seconds, until the light ring turns off.

> **Order matters.** Always shut down the Pi (`sudo poweroff`) before cutting power, so its SD card is not damaged. To turn the robot on again, place it on the dock (step 1). Details: [HOW-TO-CONNECT, turning the robot off](../HOW-TO-CONNECT.md#turning-the-robot-off).

## Step 11: Write your first program

This tiny program drives the robot forward at 0.1 m/s for 2 seconds (about 20 cm) and then stops. It is based on [`examples/drive_test.py`](../examples/drive_test.py), which was run on this robot; this copy adds comments, a speed cap and two log lines and has **not itself been run on this robot yet**.

**my_first_drive.py:**

> Not yet tested on this robot.

```python
#!/usr/bin/env python3
"""my_first_drive.py: drive forward slowly for 2 seconds, then stop.

MOVES THE ROBOT. Undock first and clear about 1 m of floor in front of it.
Based on examples/drive_test.py (this copy has not been run on the robot yet).
Stop it at any time with Ctrl+C or by lifting the robot.
"""
import rclpy                                # the ROS 2 Python library
from rclpy.node import Node                 # a Node is one ROS 2 program
from geometry_msgs.msg import TwistStamped  # a speed message WITH a time stamp

# --- Settings you can change -----------------------------------------------
SPEED = 0.1          # forward speed in metres per second
DRIVE_TIME = 2.0     # how long to drive, in seconds
RATE = 10            # how many speed messages to send per second
# ---------------------------------------------------------------------------

# Lab safety rule: never faster than 0.15 m/s. This line enforces it.
SPEED = min(SPEED, 0.15)


class MyFirstDrive(Node):
    def __init__(self):
        super().__init__('my_first_drive')    # the name of this node
        # On this robot /cmd_vel takes TwistStamped, NOT Twist.
        self.pub = self.create_publisher(TwistStamped, '/cmd_vel', 10)
        self.ticks = 0                         # how many messages sent so far
        # Call self.tick() RATE times per second.
        self.create_timer(1.0 / RATE, self.tick)
        self.get_logger().info('driving forward for %.1f s' % DRIVE_TIME)

    def tick(self):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()  # stamp = now
        msg.header.frame_id = 'base_link'                   # the robot's body
        if self.ticks < DRIVE_TIME * RATE:
            msg.twist.linear.x = SPEED         # forward; everything else stays 0
        # After DRIVE_TIME the message stays all zeros, which means "stop".
        self.pub.publish(msg)
        self.ticks += 1
        # Keep sending zeros for 5 more ticks (0.5 s), then finish.
        if self.ticks >= DRIVE_TIME * RATE + 5:
            raise SystemExit


def main():
    rclpy.init()
    node = MyFirstDrive()
    try:
        rclpy.spin(node)                       # run until SystemExit or Ctrl+C
    except (SystemExit, KeyboardInterrupt):
        pass
    node.pub.publish(TwistStamped())           # last message: all zeros = stop
    node.get_logger().info('done')
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
```

#### Put it on the robot

Easiest: on the robot, `nano my_first_drive.py` (step 5, option C) and paste the code. Or save it on your computer as `my_first_drive.py` (the page has a Save button) and copy it from the folder it is in:

**On your computer (any system):**

```bash
scp my_first_drive.py ubuntu@10.87.10.205:robot_code/
```

#### Run it

1. Undock the robot (step 8, part 1) and wait a few seconds.
2. Check 1 m of clear floor in front and stand next to the robot.
3. Run it on the robot:

**On the robot (after `ssh`):**

```bash
cd ~/robot_code
python3 my_first_drive.py
```

Wait 10 to 20 seconds for ROS to start. Then the robot rolls forward for about 2 seconds, stops, and the program prints `done` and exits. Ctrl+C stops it earlier. Afterwards dock the robot (step 8, part 5).

Ideas: change `DRIVE_TIME`, then try `msg.twist.angular.z` instead of `linear.x` to turn on the spot. Keep `SPEED` at or below 0.15.

## Command builder: drive and rotate

The interactive page has sliders; here is the rule. Run the result **on the robot**, after undocking, with the safety rules above.

Drive a distance, with `distance` between 0.05 and 0.5 m and `max_translation_speed` between 0.05 and 0.15 m/s (never above 0.15). Not yet tested on this robot:

```bash
ros2 action send_goal /drive_distance irobot_create_msgs/action/DriveDistance "{distance: 0.2, max_translation_speed: 0.1}"
```

Rotate, with `angle` in **radians** (degrees x 0.0174533; positive is left, negative is right; between -180 and 180 degrees) and `max_rotation_speed` in rad/s (0.5 is verified on this robot):

```bash
ros2 action send_goal /rotate_angle irobot_create_msgs/action/RotateAngle "{angle: 1.5708, max_rotation_speed: 0.5}"
```

| Degrees | Radians |
|---|---|
| 45 | 0.7854 |
| 90 (quarter turn left) | 1.5708 |
| 180 (half turn, verified) | 3.14159 |
| -90 (quarter turn right) | -1.5708 |
| -180 | -3.14159 |

## Troubleshooting

Same answers as the table in [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md#troubleshooting).

### No answer: connection timed out, no route to host, or it works then freezes

**Likely cause.** Your computer and the robot are on different networks, the robot is still starting, or the robot dropped off the Wi-Fi (seen on 2026-10-04 and 2026-10-05; likely Wi-Fi power saving on the robot, not confirmed, fix not applied as of 2026-10-10).

**What to do.**

Check both are on the same network (`Students` for a `10.87.x.x` display, `Turtlebot4` for `10.42.0.1`) and that your own Wi-Fi works. Put the robot back on the dock and wait 2 minutes. Connect by the **display address**, not the name, and retry with the loop. Keep sessions short and run long jobs detached.

**On your computer, macOS or Linux (Terminal):**

```bash
while true; do ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; [ $? -ne 255 ] && break; sleep 5; done
```

**On your computer, Windows (PowerShell):**

```powershell
while ($true) { ssh -o ConnectTimeout=5 -o ServerAliveInterval=10 ubuntu@10.87.10.205; if ($LASTEXITCODE -ne 255) { break }; Start-Sleep 5 }
```

If nothing answers for several minutes, tell the lab maintainer. Do not change the robot's Wi-Fi. [Full details](../HOW-TO-CONNECT.md#the-robot-answers-only-sometimes-drops-off-the-wi-fi-or-turtlebot4local-is-not-found).

### `turtlebot4.local` is not found (Could not resolve hostname)

**Likely cause.** mDNS is not working on your computer or network. On the campus Wi-Fi it has failed now and then since 2026-10-04. Or your computer is on a different network.

**What to do.**

Connect by the address on the robot's display instead, and check your computer is on `Students`:

**On your computer (any system):**

```bash
ssh ubuntu@10.87.10.205
```

### Permission denied

**Likely cause.** Wrong password (nothing shows while you type), or your key is not installed on the robot.

**What to do.**

Retype the password slowly. Repeat the [key setup](#step-4-optional-log-in-with-a-key-one-time-per-computer) if you use a key. Ask the lab maintainer if the password was changed. Never write the password into the repository.

### WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!

**Likely cause.** The robot was reinstalled, or that address now belongs to another device (campus addresses change).

**What to do.**

Do not ignore it. Check with the lab maintainer first (the correct fingerprint is `SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4`). Only after they confirm, remove the old entry and connect again:

**On your computer (any system):**

```bash
ssh-keygen -R 10.87.10.205
```

Use the same command with `turtlebot4.local` if that is what you typed.

### `ros2: command not found`

**Likely cause.** ROS 2 is loaded only in the robot's interactive shells. You are either on your own computer instead of the robot (the prompt must read `ubuntu@turtlebot4:~$`), or in a script or shell that did not load it.

**What to do.**

Log in to the robot first (step 3). In a script, or if the command is still not found, load ROS first:

**On the robot (after `ssh`):**

```bash
source /etc/turtlebot4/setup.bash
```

### No /scan (lidar data)

**Likely cause.** The robot is on the dock: the lidar is switched off there to save power. Or the lidar was not detected on USB.

**What to do.**

Undock (step 8), wait a few seconds, and try again. If it is still silent, check the lidar USB device (this lists `/dev/RPLIDAR` when it is detected):

**On the robot (after `ssh`):**

```bash
ls /dev/RPLIDAR
```

More: [lidar guide](lidar-guide.html) and [Known issues](../HOW-TO-CONNECT.md#known-issues).

### The robot does not move

**Likely cause.** Common reasons: it is still on the dock; your program publishes `Twist` instead of `TwistStamped` (on this robot `/cmd_vel` takes `TwistStamped` with `header.stamp` set to now); a stale `~/STOP` file makes the example programs refuse to start; or the Create 3 base is stuck.

**What to do.**

Check the dock state (`is_docked: true` means undock first, step 8):

**On the robot (after `ssh`):**

```bash
timeout 60 ros2 topic echo --once /dock_status
```

Remove a leftover stop file:

**On the robot (after `ssh`):**

```bash
rm ~/STOP
```

If `/dock_status` prints nothing, restart the base application, wait for the chime (about a minute) and check again:

**On the robot (after `ssh`):**

```bash
curl -X POST http://192.168.186.2/api/restart-app
```

Also wait: ROS programs need 10 to 20 s to start. [Restart details](../HOW-TO-CONNECT.md#restart-the-create-3-base-application).

---

Back to the [docs index](index.html). Interactive version: [do-it-yourself.html](do-it-yourself.html). Lidar in depth: [LIDAR-GUIDE.md](LIDAR-GUIDE.md) ([HTML](lidar-guide.html)). Connection details: [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md). Example programs: [examples/README.md](../examples/README.md). Optional connect tool: [tools/connect](../tools/connect/README.md).
