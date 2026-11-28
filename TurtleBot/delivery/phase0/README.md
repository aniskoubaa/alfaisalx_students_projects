# Phase 0 checks (no motion)

Scripts for the delivery Phase 0: check the robot and soak it before it moves. Run them on the robot, docked, by a lab member who has the maintainer's OK for the soak.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `p0_checks.sh` | Part A: read-only checks A1 to A9. Changes nothing, does not move the robot | robot |
| `p0_soak.sh` | Part B: soak test with mapping and navigation running, robot docked, no goals sent. Writes files under `~/robot_code/logs/delivery/` | robot |

Run Part A on the robot (5 to 10 minutes; `--dry-run` prints the commands only):

```bash
bash ~/robot_code/delivery/phase0/p0_checks.sh --dry-run
```

Part B should be started detached so a dropped ssh session does not end it; the exact command and the options `--baseline` and `--soak` are in the header of `p0_soak.sh`. The report of Part A is written to `~/robot_code/logs/delivery/`.

See also: [delivery/README.md, Phase 0](../README.md#5-phase-0-no-motion).
