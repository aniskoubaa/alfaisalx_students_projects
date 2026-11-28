# Architecture decision records (TurtleBot Studio)

An architecture decision record (ADR) explains one design decision: the situation, the choice, and what it costs. They
are short on purpose. Read them before changing the parts they describe, and add a new record instead of rewriting an
old one when a decision changes (mark the old one "Superseded by ADR-NNNN").

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-one-ros-participant.md) | Every Studio feature on the robot shares one ROS participant | Accepted (2026-10-24, extended 2026-11-12) |
| [0002](0002-streamed-single-file-bridge.md) | The robot side is one file, streamed over ssh at connect time | Accepted (2026-10-24) |
| [0003](0003-mapping-runs-the-delivery-scripts.md) | Mapping runs the tested delivery scripts instead of calling slam_toolbox directly | Accepted (2026-11-12) |
| [0004](0004-maps-as-png-on-the-desktop.md) | The desktop turns occupancy grids into PNG; the browser gets small events | Accepted (2026-11-12, replace rule 2026-11-14) |
| [0005](0005-robot-owned-menu-validation.md) | The robot's own checker is the only validator of the menu file | Accepted (2026-11-12) |
| [0006](0006-atomic-writes-no-silent-overwrite.md) | Every write on the robot is atomic and never overwrites without an explicit request | Accepted (2026-11-14) |
| [0007](0007-simulated-robot-behind-the-same-protocol.md) | A simulated robot speaks the same protocol, so every screen is testable offline | Accepted (2026-10-24, mapping 2026-11-12) |
| [0008](0008-small-source-modules-joined-into-single-files.md) | The two single files are built from small source modules by `bundle.py` | Accepted (2026-11-28) |

Format (one page each): **Status**, **Context**, **Decision**, **Consequences**, **Alternatives considered**. Copy
[template.md](template.md) for a new record and give it the next number.

Related: [DESIGN-MAPPING.md](../DESIGN-MAPPING.md) (the contract of the 2.1 features), [TESTING.md](../TESTING.md)
(how each layer is tested), [Studio README](../../README.md#architecture).
