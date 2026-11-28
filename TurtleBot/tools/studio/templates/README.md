# Studio program templates

Starter programs offered by the Studio Code tab ("New program"). Students copy one, edit the constants at the top and run it on the robot.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `my_first_program.py` | Prints battery, dock state and position every second. Does not move the robot | robot; simulator test in CI |
| `read_lidar.py` | Prints the nearest object ahead, left, right and behind. Does not move the robot; undock first | robot; simulator test in CI |
| `spin_in_place.py` | Turns on the spot. Moves the robot | robot; simulator test in CI |
| `drive_circle.py` | Drives a circle of a chosen radius. Moves the robot | robot; simulator test in CI |
| `drive_forward_and_back.py` | Drives out, turns round and returns. Moves the robot | robot; simulator test in CI |

Motion templates need an undocked robot, a person next to it, and accept `--dry-run` (checks only, never moves). On the robot, for example:

```bash
python3 spin_in_place.py --turns 1 --dry-run
```

Test them without a robot, from the repo root: `python TurtleBot/tests/offline/test_studio_templates.py`.

See also: [Studio README, Templates](../README.md#templates).
