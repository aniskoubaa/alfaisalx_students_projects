# Delivery launch file

The one ROS 2 launch file that starts the whole navigation stack for a delivery. Used by `robot/start_stack.sh` and the simulator; lab members rarely run it directly.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `delivery_stack.launch.py` | Starts the navigation stack for a delivery in one process, so the robot gets one new ROS participant | robot |

Start it through the wrapper, on the robot (`DIR` holds `map.yaml`, `keepout_mask.yaml`, `speed_mask.yaml` and `route.yaml`):

```bash
bash ~/robot_code/delivery/robot/start_stack.sh nav --route-dir DIR
```

The reasons for one process instead of the stock launch files are in the header of the launch file.

See also: [delivery/README.md, Files](../README.md#3-files).
