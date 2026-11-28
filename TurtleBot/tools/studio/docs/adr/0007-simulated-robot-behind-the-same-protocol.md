# ADR-0007: A simulated robot speaks the same protocol, so every screen is testable offline

**Status:** Accepted (2026-10-24; mapping added 2026-11-12)

## Context

There is one robot, often away (lab under renovation, at home, on campus), and every new ROS participant on it has a
cost (ADR-0001). Studio still needs development, automated tests in CI and a practice mode for students.

## Decision

`studio.py --fake` starts the same `robot_bridge.py` locally with a `FakeRos` instead of rclpy, behind the identical
JSON-lines protocol. The fake integrates the commanded velocity into a pose, ray-casts a fixed room for the lidar, and
since 2.1 builds a growing occupancy grid (`FakeMapGrid`) from the same ray cast, writes real PGM and YAML files when
saving, and seeds route folders and a menu log. Timings are scaled with `STUDIO_FAKE_MAP_SCALE` for tests. Everything
above the `RosBase`, `StackRunner` and `ProcessProbe` interfaces is the real code.

## Consequences

- Every screen and every bridge command runs in CI and in the browser end-to-end tests without a robot.
- The fake is not the robot: no TB-25 stalls, no Create 3 reverse limit, no real SLAM drift, perfect odometry. Those
  are listed as "not verified" in the README until a real-robot check covers them.
- Differences in the fake must stay small and documented (DESIGN-MAPPING.md section 7).

## Alternatives considered

- A full Gazebo simulation: realistic, but heavy, slow in CI, and not available on student laptops.
- Mocks at the HTTP level: would skip the bridge, where most of the logic and risk is.
