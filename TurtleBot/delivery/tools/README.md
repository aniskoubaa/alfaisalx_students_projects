# Delivery tools (laptop)

Tools for the delivery project that run on your own computer (Windows, macOS or Linux) and do not move the robot, except `deploy.py`, which copies files to it.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `deploy.py` | Packs `TurtleBot/delivery` and deploys it to the robot as a numbered release, with `status` and `rollback` | laptop (uses `ssh` and `scp`) |
| `plan_route.py` | Plans a wall-hugging route on a saved map and writes the route, masks and a preview | laptop |
| `route_spec.example.yaml` | Example input for `plan_route.py` (made-up numbers for the test hall) | laptop |
| `make_localization_params.py` | Writes the AMCL settings for one route, with the dock pose as initial pose | robot (called by `start_stack.sh`) |
| `verify_all.py` | One command that runs lint, syntax checks, the link check and the offline tests | laptop, CI |

Main command, from the repo root:

```bash
python TurtleBot/delivery/tools/verify_all.py
```

Other commands: `python TurtleBot/delivery/tools/deploy.py deploy --dry-run` (shows every step, changes nothing) and `python TurtleBot/delivery/tools/plan_route.py --map my_map.yaml --info`. Options for each are in the header of the file.

See also: [delivery/README.md, Copy the folder to the robot](../README.md#4-connecting-and-copying-the-folder-to-the-robot) and [Offline tests](../README.md#12-offline-tests).
