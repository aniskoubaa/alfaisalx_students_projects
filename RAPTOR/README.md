# RAPTOR

A search-and-rescue quadcopter that finds people from the air and reports **where they
are, what posture they are in, and whether they show visible signs of injury** to a
ground operator.

The airframe, flight controller, camera and gimbal already exist. The work documented
here is the **onboard compute**: a **Jetson Orin NX** running a YOLO-based detection and
pose pipeline, a small vision-language model for scene description, and ROS 2 to tie it
together — all of it offline, on the aircraft, with no network dependency.

## How it works

A three-tier perception stack, because the three questions cost very different amounts:

1. **"Is there a person?"** — YOLO11 detection + ByteTrack, every frame, ~30 FPS.
2. **"What posture?"** — YOLO11-pose keypoints, gravity-aligned using the drone's own
   IMU attitude, fed to a small custom classifier: standing / sitting / crouching /
   lying / unknown. Deterministic, explainable, effectively free.
3. **"What is happening to them?"** — a quantised ~3B vision-language model
   (Qwen2.5-VL class) run **only when tiers 1-2 trigger it** — a new person, a posture
   that became alarming, prolonged immobility, or an operator request.

The output is a geolocated victim report with a snapshot, a posture, a description, and
a **rule-based** triage flag that a human reviews. The system never makes a medical call.

## Documentation

Full design docs, with the rationale behind every model choice, are in
[`docs/`](./docs):

| # | Document |
|---|----------|
| 01 | [System overview](./docs/01-system-overview.md) — mission, hardware, constraints, data flow |
| 02 | [Detection & pose](./docs/02-detection-and-pose.md) — which YOLO and why |
| 03 | [Scene understanding (VLM)](./docs/03-scene-understanding-vlm.md) — which model and why |
| 04 | [ROS 2 architecture](./docs/04-ros2-architecture.md) — nodes, topics, messages |
| 05 | [Custom models & data](./docs/05-custom-models-and-data.md) — build vs. fine-tune vs. use |
| 06 | [Benchmark plan](./docs/06-benchmark-plan.md) — what we measure and how |
| 07 | [Roadmap](./docs/07-roadmap.md) — phases and milestones |
| 08 | [Limitations & safety](./docs/08-limitations-and-safety.md) — what this is not |
| 09 | [Jetson environment](./docs/09-jetson-environment.md) — venv, PEP 668, CUDA torch, board commands |

Start with [`docs/README.md`](./docs/README.md) for the short version.

## Repository structure

- [`docs/`](./docs) — design documentation and decision rationale
- [`jetson_orin_nano_benchmarks/`](./jetson_orin_nano_benchmarks) — benchmark scripts and
  results (see the naming note in [06](./docs/06-benchmark-plan.md); the flight computer
  is an Orin **NX**)
- [`assets/`](./assets) — photos, diagrams, logo

See also [`../General Tasks/`](../General%20Tasks) at the repo root for hardware
troubleshooting notes.

## Status

Design phase. No pipeline code has been written yet — Phase 0 in
[the roadmap](./docs/07-roadmap.md) is the next step.
