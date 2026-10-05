# TurtleBot Connect

A small tool that opens a terminal on the lab's TurtleBot 4 with one double-click on Windows, or one command on macOS and Linux. It does the steps in [HOW-TO-CONNECT.md](../../HOW-TO-CONNECT.md) for you: it finds the robot, opens an SSH session, sets up key login, shows the robot's status, stops the motion programs in an emergency, copies files and fixes a changed host key.

It uses the `ssh` that is already on your computer, and ssh asks for any password itself. The tool never stores, reads or sends a password.

| File | What it is |
|---|---|
| `TurtleBotConnect.exe` | The Windows program (double-click it) |
| `TurtleBotConnect.exe.sha256` | SHA-256 checksum of the exe, to check your download |
| `TurtleBotConnect.cs` | Source code of the exe (one C# file, no dependencies) |
| `build.cmd` | Builds the exe from the source with the compiler that ships with Windows |
| `connect-turtlebot.sh` | The same tool for macOS and Linux (bash script) |

Status on 2026-10-04: every menu option and command was tested on Windows 11 and in bash (Git Bash, and Ubuntu 24.04 under WSL) against a simulated robot: a stand-in for `ssh` that runs the robot-side commands in Ubuntu's bash, and a stand-in for VS Code's `code` command. It has not yet been used with the real robot, which was switched off that day, and it has not been run on a Mac.

## Windows

### Download

1. On GitHub, open [`TurtleBotConnect.exe`](TurtleBotConnect.exe) in this folder and click **Download raw file** (the download arrow at the top right of the file view).
2. If your browser warns that the file "is not commonly downloaded", choose **Keep**.
3. Optional but recommended: [check the SHA-256](#check-the-download-sha-256).
4. Move the file anywhere you like, for example your Desktop.

### First run

1. Double-click `TurtleBotConnect.exe`.
2. Windows may show a blue box, **"Windows protected your PC"**. That is Microsoft Defender SmartScreen: it appears for programs that are not signed with a paid code-signing certificate, which this lab tool is not. Click **More info**, then **Run anyway**. You only need to do this once.
   - To avoid the box completely, either right-click the file, choose **Properties**, tick **Unblock** and click **OK** before the first run, or [build the program yourself](#build-it-yourself).
   - On Windows 11 with **Smart App Control** turned on, unsigned programs can be blocked with no "Run anyway" button. Use the plain `ssh` commands in [HOW-TO-CONNECT.md](../../HOW-TO-CONNECT.md) instead.
3. A window with a numbered menu opens. Join the robot's network first (see [Step 3 of HOW-TO-CONNECT.md](../../HOW-TO-CONNECT.md#step-3-connect-your-computer-to-the-same-network)), then:
   - type `1` and press Enter to open a terminal on the robot. Type the robot's `ubuntu` password when asked (ask the lab maintainer; nothing shows while you type).
   - type `3` once, to set up key login, so you no longer need the password.

`ssh` must be installed. Windows 10 and 11 include it. If the tool says it is missing, add **OpenSSH Client** under **Settings > System > Optional features**, or run this in PowerShell opened with **Run as administrator**:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

### Check the download (SHA-256)

The file `TurtleBotConnect.exe.sha256` holds the checksum of the exe in this folder. Compute the checksum of your download and compare the two; capital or small letters do not matter.

| Where | Command |
|---|---|
| PowerShell | `Get-FileHash .\TurtleBotConnect.exe -Algorithm SHA256` |
| Command Prompt | `certutil -hashfile TurtleBotConnect.exe SHA256` |
| macOS | `shasum -a 256 TurtleBotConnect.exe` |
| Linux | `sha256sum TurtleBotConnect.exe` |

If they differ, do not run the file. Download it again or build it yourself.

### Build it yourself

You need nothing beyond Windows 10 or 11.

1. Download `TurtleBotConnect.cs` and `build.cmd` into one folder (or clone the repository).
2. Double-click `build.cmd`, or run it from a terminal (`build.cmd /nopause` never waits for a key).
3. It compiles `TurtleBotConnect.exe` with the .NET Framework 4 compiler (`%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`) and writes its checksum to `TurtleBotConnect.exe.sha256`.

A program you build yourself was not downloaded from the internet, so SmartScreen does not ask about it. Your checksum will differ from the one in the repository: the compiler writes the build time and a random ID into every build, so no two builds are byte-identical.

## The menu

The program looks for the robot when an option needs it. It tries, at the same time, the last address that worked, `turtlebot4.local` (the robot on the university `Students` Wi-Fi) and `10.42.0.1` (the robot's own `Turtlebot4` Wi-Fi). The search takes at most about 6 seconds. If nothing answers, it lists your computer's network addresses, says what to check, and lets you type the address shown on the robot's display.

| Option | What it does | The command it runs (simplified) |
|---|---|---|
| 1 Connect | Opens a terminal on the robot in the same window. Type `exit` to come back to the menu. | `ssh -t ubuntu@<robot>` (with your key if you have one) |
| 2 Find the robot | Searches again, for example after you changed Wi-Fi | none (checks port 22) |
| 3 Set up key login | One time per computer. Creates your key `~/.ssh/turtlebot4_ed25519` if you have none (it asks whether to protect it with a passphrase), adds the public key to the robot (type the robot password one last time), then checks that key login works | `ssh-keygen -t ed25519 ...`, then `ssh ubuntu@<robot> "... >> ~/.ssh/authorized_keys"` |
| 4 Robot status | Read only. Name, uptime, Wi-Fi address, whether `turtlebot4.service` runs, whether the lidar USB device `/dev/RPLIDAR` exists, battery % and whether the robot is on its dock. The battery and dock part asks ROS and can take up to a minute. | `ssh ubuntu@<robot> "<status commands>"` |
| 5 Open in VS Code | Opens `~/robot_code` on the robot in VS Code. Needs VS Code with Microsoft's **Remote - SSH** extension. Without key login (3) and the shortcut (6), VS Code asks for the password, sometimes several times. | `code --remote ssh-remote+ubuntu@<robot> /home/ubuntu/robot_code` |
| 6 SSH config shortcut | Adds a `Host turtlebot4` block to your SSH config, so `ssh turtlebot4` and `scp file turtlebot4:robot_code/` work and VS Code lists the robot. Backs the file up first, only appends, and does nothing if a `Host turtlebot4` entry already exists. | appends to `~/.ssh/config` |
| 7 EMERGENCY stop | Creates `~/STOP` on the robot and stops `motion_shapes.py`, `more_shapes.py`, `wall_approach.py`, `keep_distance.py`, `campaign.sh` and running `ros2 action send_goal` commands. A running motion program stops the wheels within a second. `~/STOP` then blocks new runs until someone types `rm ~/STOP` on the robot. | `ssh ubuntu@<robot> "touch ~/STOP; pkill ..."` |
| 8 Copy a file | Copies a file or folder from your computer into `~/robot_code` on the robot. You can drag the file onto the window. | `scp <file> ubuntu@<robot>:robot_code/` |
| 9 Fix "host key changed" | For the warning `REMOTE HOST IDENTIFICATION HAS CHANGED`. Explains when this is expected, asks you to type `yes`, then forgets the old identity. **Ask the lab maintainer first**: the warning can also mean a device is pretending to be the robot. | `ssh-keygen -R <robot>` |
| 0 Exit | | |

The dimmed line under each action shows the command being run, so you can learn the plain `ssh` commands from [HOW-TO-CONNECT.md](../../HOW-TO-CONNECT.md).

**Safety:** if the robot is heading for danger, pick it up. The Create 3 base stops its wheels when lifted. Option 7 is for stopping programs; it is no substitute for staying next to the robot.

## Command line

The menu appears when you start the program without arguments. For scripts and quick use:

| Command | What it does |
|---|---|
| `TurtleBotConnect.exe connect [address]` | Find the robot (or use the address) and open a terminal |
| `TurtleBotConnect.exe find` | Look for the robot and print its address |
| `TurtleBotConnect.exe status [address]` | Print the robot's status (read only) |
| `TurtleBotConnect.exe stop [address]` | Emergency stop of the motion programs |
| `TurtleBotConnect.exe setup-key [address]` | Set up key login |
| `--host <address>` | Use this robot name or address instead of searching |
| `--user <name>` | Log in as another user (default `ubuntu`) |
| `--key <path>` | Use another private key file (default `~/.ssh/turtlebot4_ed25519`) |
| `--help`, `--version` | Show help or the version (1.0.0) |

On macOS and Linux, use `./connect-turtlebot.sh` with the same commands and options.

Exit codes: `0` OK, `1` robot not found, `2` ssh missing or a usage error, anything else is the exit code of `ssh` (`255` means ssh could not connect or log in).

## macOS and Linux

1. On GitHub, open [`connect-turtlebot.sh`](connect-turtlebot.sh) and click **Download raw file**.
2. In Terminal, go to the folder where it was saved and make it executable, once:

   ```bash
   cd ~/Downloads
   chmod +x connect-turtlebot.sh
   ```

3. Run it:

   ```bash
   ./connect-turtlebot.sh
   ```

   (`bash connect-turtlebot.sh` works too, without `chmod`.)

It shows the same menu and accepts the same commands as the Windows program. It needs `ssh` (included in macOS and most Linux systems) and works with the old bash 3.2 that macOS ships. For option 5 the `code` command must be installed: on macOS, open VS Code, press Cmd+Shift+P and run **Shell Command: Install 'code' command in PATH**. To drop a file for option 8, drag it from Finder onto the Terminal window.

## Privacy and security

- **No passwords are stored.** The robot password, and your key's passphrase if you set one, are typed only into ssh's own prompt. The tool never sees or saves them, and never puts them on a command line. The repository contains no passwords; keep it that way.
- **Your private key stays on your computer.** Each lab member creates their own key with option 3; never share or copy key files, and never commit them. A key without a passphrase is convenient, but anyone who copies the file can log in to the robot. A passphrase protects it at the cost of typing the passphrase at each login.
- **New robots are trusted automatically.** The tool runs ssh with `StrictHostKeyChecking=accept-new`: the first connection to a name or address saves the robot's identity without the usual yes/no question, and a later change is refused with a warning (option 9). On a shared network a device could, in theory, pretend to be the robot at that first contact. To check, compare the fingerprint the lab maintainer gets on the robot (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`) with the one your computer saved (`ssh-keygen -l -F turtlebot4.local`, or the address you used).
- **The Windows program is not code-signed.** Check its SHA-256, or build it yourself from the source in this folder.

What the tool writes:

| What | Where | When |
|---|---|---|
| The last robot address that answered | Windows: `%APPDATA%\TurtleBotConnect\last_host.txt`. macOS and Linux: `~/.config/turtlebot-connect/last_host.txt` | Whenever the robot answers |
| Your key pair | `~/.ssh/turtlebot4_ed25519` and `~/.ssh/turtlebot4_ed25519.pub` (Windows: `%USERPROFILE%\.ssh\...`) | Option 3, only if the key does not exist yet |
| A `Host turtlebot4` block, and a backup of your previous file | `~/.ssh/config` and `~/.ssh/config.bak-<date>-<time>` | Option 6 only |
| The robot's identity | `~/.ssh/known_hosts` (written by ssh itself) | First connection to each name or address |
| Removal of one identity, keeping the old file | `~/.ssh/known_hosts`, `~/.ssh/known_hosts.old` (by ssh-keygen) | Option 9, after you type `yes` |
| One line with your public key | `~/.ssh/authorized_keys` on the robot | Option 3 |
| The stop file | `~/STOP` on the robot | Option 7 |

Option 4 (status) changes nothing on the robot.

## Troubleshooting

| Symptom | What to do |
|---|---|
| "Windows protected your PC" | Click **More info**, then **Run anyway**. Or tick **Unblock** in the file's Properties, or [build it yourself](#build-it-yourself). |
| The browser blocks the download | Choose **Keep** (Edge: **...** > **Keep** > **Keep anyway**). Then [check the SHA-256](#check-the-download-sha-256). |
| "ssh (the OpenSSH Client) was not found" | Add **OpenSSH Client** under **Settings > System > Optional features**, or run `Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0` in an administrator PowerShell. |
| "The robot did not answer" | Follow the steps it prints: the robot is on and has chimed (about 2 minutes after it starts), your computer is on the same Wi-Fi (`Students` for a `10.87.x.x` display, `Turtlebot4` for `10.42.0.1`), or type the address from the display. See [HOW-TO-CONNECT.md, Troubleshooting](../../HOW-TO-CONNECT.md#troubleshooting). |
| `Permission denied` | Wrong password (nothing shows while you type), or your key is not on the robot yet: run option 3. |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` | Ask the lab maintainer whether the robot was reinstalled or its address changed, then use option 9. |
| Status says "ROS did not answer" | The robot started less than 2 minutes ago, or the Create 3 base is stuck: see [Restart the Create 3 base application](../../HOW-TO-CONNECT.md#restart-the-create-3-base-application). |
| A motion program says `REFUSING: /home/ubuntu/STOP exists` | Option 7 left the stop file. When it is safe, log in and type `rm ~/STOP`. |
| VS Code asks for the password again and again | Run option 3 (key login), then option 6 (shortcut), then option 5 again. Check that the **Remote - SSH** extension is installed. |
| VS Code (option 5) says VS Code was not found | Install VS Code. On macOS, also install the `code` command (see [macOS and Linux](#macos-and-linux)). |
| `bad interpreter: /usr/bin/env: bash^M` or `$'\r': command not found` (macOS, Linux) | The script got Windows line endings. Fix it with `sed -i.bak 's/\r$//' connect-turtlebot.sh`, or download it again with **Download raw file**. |
| `permission denied: ./connect-turtlebot.sh` | Run `chmod +x connect-turtlebot.sh` once, or start it with `bash connect-turtlebot.sh`. |
| `build.cmd` says the compiler was not found | Turn on **.NET Framework 4.8 Advanced Services** under **Turn Windows features on or off**. |

## Remove everything it created

Do the robot part first, while your key still logs you in.

1. **On the robot:** log in, open `~/.ssh/authorized_keys` (for example `nano ~/.ssh/authorized_keys`) and delete the line with your key. Option 3 prints which line that is: it ends with `turtlebot4-<your user>@<your computer>` if the tool added it.
2. **Windows (PowerShell):**

   ```powershell
   Remove-Item -Recurse "$env:APPDATA\TurtleBotConnect"
   Remove-Item "$env:USERPROFILE\.ssh\turtlebot4_ed25519", "$env:USERPROFILE\.ssh\turtlebot4_ed25519.pub"
   ```

   **macOS and Linux:**

   ```bash
   rm -r ~/.config/turtlebot-connect
   rm ~/.ssh/turtlebot4_ed25519 ~/.ssh/turtlebot4_ed25519.pub
   ```

3. **SSH config (only if you used option 6):** open `~/.ssh/config` (Windows: `%USERPROFILE%\.ssh\config`) in a text editor and delete the `Host turtlebot4` block, or put back the `config.bak-<date>-<time>` backup if you have not changed the file since. Delete the backups you no longer need.
4. **Optional:** forget the robot's identity with `ssh-keygen -R turtlebot4.local` (and the same for any address you used).
5. Delete `TurtleBotConnect.exe` or `connect-turtlebot.sh`.

Only delete a key file called `turtlebot4_ed25519` if it was created for the robot. Your other SSH keys are never touched.

## For maintainers

- `TurtleBotConnect.cs` must stay C# 5 (no `$"..."`, `?.`, `nameof`, tuples or `=>` members) so that the compiler built into Windows can build it. After changing it, run `build.cmd` and commit the `.cs`, `.exe` and `.exe.sha256` together.
- The remote status and stop commands are identical in `TurtleBotConnect.cs` (`StatusScript`, `StopCommand`) and `connect-turtlebot.sh` (`STATUS_SCRIPT`, `STOP_COMMAND`). Change both, and keep double quotes out of them: the Windows program passes each one as a single quoted argument.
- In the stop command, the patterns are written like `'motion_shape[s].py'`. They match the same programs as `motion_shapes.py`, but not the robot's shell that runs the command, whose own command line contains the pattern. Without the brackets, `pkill -TERM -f campaign.sh` kills that shell (tested on 2026-10-04 with Ubuntu's bash 5.2 and procps): the command stops halfway and a running `ros2 action send_goal` is not stopped.
- Hidden test options: `--ssh-config <path>` (option 6 writes to this file instead of `~/.ssh/config`) and `--known-hosts <path>` (option 9 edits this file).
- `.gitattributes` keeps `connect-turtlebot.sh` at LF line endings and `build.cmd` at CRLF. Git on Windows does not record the executable bit; set it once with `git update-index --chmod=+x TurtleBot/tools/connect/connect-turtlebot.sh`.

Back to [HOW-TO-CONNECT.md](../../HOW-TO-CONNECT.md).
