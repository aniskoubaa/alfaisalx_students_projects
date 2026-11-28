# Robot setup scripts

Copies of the admin scripts installed on the lab TurtleBot 4. Used by the lab maintainer, not for everyday work.

**These scripts change the robot** (Wi-Fi profile, clock, system services). Each change is recorded in the [change register in MAINTENANCE.md](../MAINTENANCE.md#change-register) with what was changed, how to verify it and how to undo it, and the scripts are described in [Admin scripts](../MAINTENANCE.md#admin-scripts). Read those before running anything. Most need `sudo` on the robot, which asks for the robot password: ask the lab maintainer. Do not run `root-setup.sh` or `fix-ros.sh` again: they reinstall the clock fix.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `start.sh`, `controller.sh`, `write_keyfile.py` | Move the robot to the "Students" Wi-Fi with a test phase and automatic undo | robot (root) |
| `root-setup.sh` | One-time admin setup: clock fix, avahi limit, reboot | robot (root) |
| `fix-ros.sh` | Reinstalls the clock fix and starts ROS after it, restarts the robot software | robot (root) |
| `undo-clock.sh` | Removes the clock fix and its start-order rule | robot (root) |
| `tb4-https-time`, `tb4-https-time.service`, `tb4-https-time.timer`, `10-wait-for-clock.conf` | The clock fix: sets the clock from an HTTPS header, with the rule that ROS starts after it | robot (root) |
| `lidar-restart/` | Service that restarts the lidar motor after an undock (own `install.sh` and `uninstall.sh`) | robot (root) |
| `wifi-retry/` | Timer that retries saved Wi-Fi while the robot sits on its own hotspot (own `install.sh` and `uninstall.sh`) | robot (root) |

Run on the robot, as listed for each script in the Admin scripts table, for example:

```bash
sudo bash /home/ubuntu/wifi-switch/start.sh
```

The two subfolders have their own README with install, verify and undo steps: [lidar-restart](lidar-restart/README.md), [wifi-retry](wifi-retry/README.md).

See also: [MAINTENANCE.md, Admin scripts](../MAINTENANCE.md#admin-scripts) and [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md).
