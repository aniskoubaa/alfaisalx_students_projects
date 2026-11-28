# Delivery scripts that run on the robot

Shell and Python programs for the delivery project. Run them on the robot after a deploy, with `source /etc/turtlebot4/setup.bash` for the Python ones. Most are for the lab members running mapping and supervised tests. None uses sudo.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `start_stack.sh` | Starts mapping (`map`) or navigation (`nav --route-dir DIR`), detached, with logs | robot |
| `stop_stack.sh` | Stops what `start_stack.sh` started, with SIGINT and no SIGKILL | robot |
| `save_map.sh` | Saves the map slam_toolbox is building, plus its pose graph | robot |
| `install_menu.sh` | Installs, removes or checks the front-panel menu as a systemd user service | robot |
| `delivery-menu.service` | The systemd unit that `install_menu.sh` installs | robot |
| `motion_probe.py` | Short supervised motion steps (status, scan, undock, dock, drive). Moves the robot | robot |
| `press_buttons.py` | Presses the front-panel buttons from software and prints the screen. Button 1 can start motion | robot |

Main command, on the robot (see the header of each file for all options; `--dry-run` shows the steps and changes nothing):

```bash
bash ~/robot_code/delivery/robot/start_stack.sh map --dry-run
```

Scripts that move the robot need a person next to it with the controller (button B is the emergency stop).

See also: [delivery/README.md, Connecting](../README.md#4-connecting-and-copying-the-folder-to-the-robot) and [Files](../README.md#3-files).
