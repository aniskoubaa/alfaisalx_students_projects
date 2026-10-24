# Troubleshooting

Find what you see in the left column, then do what is on the right.

Guides: [First connection](FIRST-CONNECTION.md) | [Everyday use](EVERYDAY-USE.md) | [Find the robot](FIND-THE-ROBOT.md) | [Troubleshooting](TROUBLESHOOTING.md)

> Status: version 1.3 was tested offline and against the simulated robot only. Open real-robot checks: README [Not verified yet](../README.md#not-verified-yet).

## Ask for help with one click

1. Press **Copy diagnostics** in the Tools tab (or next to a connection error).
2. Press **Copy**, or **Save as file** (`studio-diagnostics.txt`).
3. Send the text to the lab maintainer.

The text has the Studio version, your system, the connection state and the last log lines. Studio removes tokens, passwords and keys from it before you see it. Read it once before you send it.

## Install and start

| What you see | What to do |
|---|---|
| Windows: "Windows protected your PC" | Click **More info**, then **Run anyway**. The file is not code-signed |
| macOS: "cannot be opened because the developer cannot be verified" | Right-click the app and choose **Open**. Or run `xattr -d com.apple.quarantine <file>` once |
| Linux: "permission denied" | `chmod +x TurtleBotStudio`, then run it |
| "Port in use" | Studio is already running. Use the window that is already open |
| The page does not open | Start Studio again; it opens the window of the running copy. If you run it from a terminal, copy the address it prints into your browser |
| "ssh not found" | Windows: Settings, System, Optional features, add **OpenSSH Client**. macOS has it. Linux: `sudo apt install openssh-client` |
| Studio stopped on its own | The installed app quits about 45 seconds after its last window closes. Start it again |
| Update banner appears | A newer version exists. Press **How to update** |

## Finding the robot

| What you see | What to do |
|---|---|
| Discover finds nothing | Check that the robot is on, and that your computer is on the same Wi-Fi or on the cable. Read the address on the robot's screen and type it. Or press **Search the whole network**. See [Find the robot](FIND-THE-ROBOT.md) |
| `turtlebot4.local` does not work | Normal on some networks. Use the address on the robot's screen |
| The robot address changed | Read the new one on the robot's screen, or search the whole network |
| Search the whole network finds only "Other device with ssh" | The robot may be on another network, or the network blocks device-to-device traffic. Use the address on the screen, or the cable |
| The robot is on its own Wi-Fi `Turtlebot4` | Join that network from your computer. The robot is at `10.42.0.1` |
| Nothing works | Use the cable. It needs no Wi-Fi ([First connection](FIRST-CONNECTION.md)) |

## Connecting

| What you see | What to do |
|---|---|
| "key not set up" | Do the [first connection](FIRST-CONNECTION.md) on this computer, or open the **Setup wizard** and repeat steps 4 to 6 |
| "robot key does not match" | Stop. It may be a different or reinstalled robot, or another device at the same address. Ask the lab maintainer. Do not trust it just to get in |
| "robot not reachable" | No route, or the robot is off. Check the cable or the Wi-Fi and press Discover. On the cable, wait about 20 seconds after plugging in |
| The terminal window asks for a password and nothing appears as you type | Normal. Type the robot password and press Enter |
| "Permission denied" after the password | The password is wrong. Ask the lab maintainer for it. Do not guess repeatedly |
| The connection drops now and then | Studio reconnects by itself and shows a banner. If the Wi-Fi keeps dropping, use the cable, or ask the lab maintainer |
| "gave up reconnecting after 10 minutes" | The robot is off, out of range or on another address. Find it again ([Find the robot](FIND-THE-ROBOT.md)) and press **Connect** |

## Putting the robot on Wi-Fi

| What you see | What to do |
|---|---|
| Join fails | Check the network name and password. The robot returns to its previous network by itself, which can take about 1.5 minutes. Try again |
| The network is not in the list | The robot cannot scan while it runs its own hotspot. Type the name |
| Network not supported | Studio supports WPA or WPA2 personal only. It does not support enterprise networks (for example `eduroam`), open networks, WPA3-only networks or networks with a login page |
| Your computer lost the connection after the robot switched | Expected if you were using the robot's hotspot. Join your computer to the new network and press **Discover** |

## Running programs

| What you see | What to do |
|---|---|
| "motion needs confirmation" | Tick the motion confirmation. Read the warning first |
| "no /scan" | Press **Start lidar motor** on the Dashboard |
| The robot does not move | Check that it is undocked and that no red e-stop banner is showing. If there is one, press **Release e-stop** only when it is safe |
| The program stops when the odometry pauses | Known base behaviour. See [Known issues](../../../MAINTENANCE.md#known-issues) |
| The robot clock is wrong | The robot has no internet on the cable, so its clock can drift. The health check flags it |

## Start over

Delete Studio's settings folder to run the wizard again. The folder is listed in [INSTALL.md](../INSTALL.md#reset-or-remove-studio). Your key on the robot stays until the lab maintainer removes it.

More technical detail: [README, Troubleshooting](../README.md#troubleshooting).
