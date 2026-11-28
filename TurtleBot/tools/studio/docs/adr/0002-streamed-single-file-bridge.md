# ADR-0002: The robot side is one file, streamed over ssh at connect time

**Status:** Accepted (2026-10-24)

## Context

Students run Studio on their own laptops and connect to a shared robot. Installing or upgrading software on the robot
needs care (MAINTENANCE.md register, no sudo from Studio), and two laptops with different Studio versions may connect
to the same robot on the same day.

## Decision

`robot_bridge.py` is a single self-contained file (Python standard library plus rclpy, Python 3.8 or newer). At every
connect the desktop sends it over the one ssh connection and the robot's `python3` runs it from memory
(`exec` of the received text). It speaks JSON lines on stdin and stdout: one reply per command (matched by id) plus
unsolicited events.

## Consequences

- Nothing is installed on the robot, and the robot side always matches the desktop that connected.
- The file must stay self-contained: no imports from the repository, no third-party packages. Layers inside the file
  (pure helpers, adapters, services, handlers) replace module boundaries.
- The bridge is a large file. Its layering is documented in DESIGN-MAPPING.md section 2 and guarded by unit tests per
  layer (`test_studio_mapping.py`, `test_studio_routes_unit.py`, `test_studio_menu_unit.py`).

## Alternatives considered

- A ROS 2 package installed on the robot: proper packaging, but versioning against many laptops and an install step.
- A web server on the robot: a second always-on service and a new attack surface on campus Wi-Fi.
