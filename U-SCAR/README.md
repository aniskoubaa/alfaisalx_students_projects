# U-SCAR

Quadcopter UAV project combining a drone platform, a camera/gimbal system, and an onboard Jetson Orin Nano running an AI vision pipeline. The Jetson performs object detection on the live camera feed and drives the gimbal to track a selected target.

## Components

- **Drone platform** — frame, power distribution, flight controller, motors, and safety systems.
- **Camera & gimbal** — mounted camera with gimbal control and live video streaming.
- **Jetson Orin Nano** — onboard compute running the object-detection pipeline and gimbal-tracking logic.

## Structure

- [`jetson_orin_nano_benchmarks/`](./jetson_orin_nano_benchmarks) — benchmark scripts and results for evaluating the AI pipeline's performance on the Jetson Orin Nano (inference speed, latency, accuracy) as it's optimized for real-time use.
- [`assets/`](./assets) — photos, diagrams, and logo for the project.

See also [`../General Tasks/`](../General%20Tasks) at the repo root for hardware troubleshooting notes and general task tracking.
