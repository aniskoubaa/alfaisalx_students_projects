# Delivery configuration

Nav2, AMCL and slam_toolbox settings for the delivery robot. Used by whoever tunes the delivery project; the robot reads them through `robot/start_stack.sh`.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `nav2_delivery.yaml` | Nav2 parameters for delivery: the upstream TurtleBot 4 file with changes marked `# delivery:` | robot (read by Nav2); checked on laptop and CI |
| `localization_delivery.yaml` | AMCL and map server settings; `use_sim_time` is false (the installed file says true) | robot; base file for `tools/make_localization_params.py` |
| `slam_delivery.yaml` | slam_toolbox settings for mapping the route | robot (`start_stack.sh map`) |
| `delivery_through_poses_bt.xml` | Behavior tree for NavigateThroughPoses: a copy of the installed tree with three marked "DELIVERY CHANGE" edits | robot (path passed by `delivery_mission.py`) |
| `upstream/turtlebot4_nav2_jazzy.yaml` | Unmodified upstream Nav2 file, kept to compare against `nav2_delivery.yaml` | reference only |

Check the files without a robot (needs `bash`, PyYAML):

```bash
python TurtleBot/tests/offline/test_delivery_config.py
```

See also: [delivery/README.md, Files](../README.md#3-files) and [Tuning](../README.md#11-tuning).
