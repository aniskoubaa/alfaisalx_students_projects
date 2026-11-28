# ADR-0003: Mapping runs the tested delivery scripts instead of calling slam_toolbox directly

**Status:** Accepted (2026-11-12)

## Context

The delivery package already had a mapping procedure tested on this robot: `start_stack.sh map` (slam_toolbox with
`slam_delivery.yaml`, the lidar motor, the camera container stopped to free a CPU core), `save_map.sh` (map plus pose
graph, refusing to overwrite) and `stop_stack.sh` (clean SIGINT per launch group). Studio needed the same result from
a button.

## Decision

The bridge's `MappingService` runs those three scripts through a `StackRunner` adapter (`bash <script> args`, its own
session, output to a temporary file so a dropped ssh link cannot kill it with SIGPIPE, a time limit per script). The
service owns a small state machine (idle, starting, mapping, saving, stopping, error) and a 2 s process probe that
notices a mapping started or stopped outside Studio. A save counts only when the map file was rewritten.

## Consequences

- One procedure for people at a terminal and for Studio; fixes to the scripts reach both.
- The scripts start their own ROS processes (the SLAM launch, short service calls when saving), which TB-25 says can
  stall the base. Driving is disarmed and refused while the state is starting, saving or stopping (ADR-0001).
- Studio depends on the delivery package being deployed; the Maps screen says so when the scripts are missing.
- Tests: the state machine with a scripted runner, the real `save_map.sh` and `stop_stack.sh` under the runner with
  stand-ins for `ros2` and `pgrep` (`test_studio_mapping.py`), the browser flow with the simulated robot
  (`test_studio_e2e_maps.py`). Real robot: full cycles on 2026-11-14 (docked) and 2026-11-26 (driving).

## Alternatives considered

- Call `/slam_toolbox/save_map` from the bridge's own node: no extra participants for saving, but a second, untested
  copy of the procedure. Worth revisiting if save-time stalls show up in practice.
- Launch slam_toolbox from the bridge: duplicates `start_stack.sh` and its camera and lidar handling.
