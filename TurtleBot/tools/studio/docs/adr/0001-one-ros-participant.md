# ADR-0001: Every Studio feature on the robot shares one ROS participant

**Status:** Accepted (2026-10-24, extended to mapping on 2026-11-12)

## Context

On this robot every new ROS 2 participant (a node in a new process, including each `ros2` command line call) can stall
the Create 3 base topics for up to about 12 s while discovery runs (ROADMAP task TB-25). A stall during a drive means
old velocity commands or no odometry. On 2026-10-24 a multi-threaded executor also cost about 97 % of a Pi 4 core for
the same subscriptions that a single-threaded one served at about 11 %.

## Decision

Studio keeps exactly one ROS participant on the robot per connection: the node inside `robot_bridge.py`. Status,
lidar and pose streams, manual driving, actions (dock, undock), and since 2.1 the `/map` and `/pose` subscriptions
all live on that node. New subscriptions are added to it lazily (the map subscriptions on the first `map_on`), never
in a new process. The executor is single threaded; callbacks only store raw bytes, and decoding happens on the stream
tick that needs it.

## Consequences

- Connecting Studio costs one discovery event, not one per feature.
- Features that cannot avoid new processes say so and block driving while they run: starting, saving and stopping a
  map run the delivery scripts (ADR-0003), and the bridge refuses to arm driving in those states.
- Tests: `test_studio_bridge.py` and `test_studio_v2_backend.py` (streams and driving), `test_studio_mapping.py`
  (lazy map subscriptions, driving refused while mapping changes state). Real robot: subscriptions created on
  2026-11-14 without error.

## Alternatives considered

- One node per feature: simpler code, but a base stall each time a screen opens.
- `ros2` command line calls from the desktop: no robot-side code, but every call is a new participant.
- A multi-threaded executor: easier concurrency, measured as too expensive on the Pi.
