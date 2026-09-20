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
| 10 | [Detector benchmark results](./docs/10-detector-benchmark-results.md) — **measured** on the Orin NX: E1 sweep, TensorRT, the recall problem |
| 11 | [ROS 2 install notes](./docs/11-ros2-install-notes.md) — why **Jazzy**, not Humble, on this board |
| 12 | [VLM benchmark results](./docs/12-vlm-benchmark-results.md) — **measured**: Qwen2.5-VL vs SmolVLM2, and a safety finding |
| 14 | [Capture path & first live run](./docs/14-camera-and-live-pipeline.md) — **measured**: USB 2.0 limits, camera → TensorRT end to end |

Start with [`docs/README.md`](./docs/README.md) for the short version.

Two interactive pages sit alongside them: the
[wiring map](./docs/raptor-wiring-map.html) (what plugs into what) and the
[build view](./docs/raptor-build-view.html) (a 3D model of the X500 V2 with every cable routed,
plus to-scale plan and elevation drawings).

## Repository structure

- [`docs/`](./docs) — design documentation and decision rationale
- [`jetson_orin_nano_benchmarks/`](./jetson_orin_nano_benchmarks) — benchmark scripts and
  results (see the naming note in [06](./docs/06-benchmark-plan.md); the flight computer
  is an Orin **NX**)
- [`assets/`](./assets) — photos, diagrams, logo

See also [`../General Tasks/`](../General%20Tasks) at the repo root for hardware
troubleshooting notes.

## Status

Design phase, with the **first measurements now taken on the flight computer**
(2026-09-20) — see [10 — Detector benchmark results](./docs/10-detector-benchmark-results.md).

Headline: `yolo11s @ 960` in TensorRT FP16 runs at **25.9 ms p95** on the Orin NX,
inside the 33 ms budget, and TensorRT costs **zero accuracy** versus PyTorch. But
the best measured **person recall on aerial imagery is 0.36** with off-the-shelf
COCO weights — which makes Phase 2 data collection the critical path rather than a
parallel activity.

On tier 3, **Qwen2.5-VL-3B** is confirmed as the primary VLM on measured grounds
(88% vs 0% schema-valid output against SmolVLM2). The unconstrained fallback model
volunteered a person's inferred race, gender and eye colour from an aerial crop —
the exact identity inference [08](./docs/08-limitations-and-safety.md) rules out —
which makes grammar-constrained decoding a **safety control**, not an optimisation.
See [12](./docs/12-vlm-benchmark-results.md).

**Deployed on the board** at `~/raptor-deploy/`, each artifact verified by loading
and running it, with a provenance manifest recording source, SHA, build
environment and measured performance:

| Slot | Artifact | Measured |
|---|---|---|
| tier 1+2 | `yolo11s-pose.engine` @960 FP16 | 26.5 ms p95, 34.4 FPS, 14.5 W |
| tier 1 (detect-only) | `yolo11s.engine` @960 FP16 | 25.9 ms p95, mAP50 0.369, 12.6 W |
| tier 3 | `Qwen2.5-VL-3B-Instruct` | 0.76 s TTFT p95, 88% schema-valid, 19.2 W |
| tier 3 fallback | `SmolVLM2-2.2B-Instruct` | see [12](./docs/12-vlm-benchmark-results.md) — **do not run without a decoding grammar** |

**The board is provisioned and running.** ROS 2 **Jazzy** (195 packages, DDS
pub/sub verified, `vision_msgs` present — Jazzy not Humble because the board is
Ubuntu 24.04), a clock that survives reboots, and network access; see
[11](./docs/11-ros2-install-notes.md).

**Live demo, clickable.** A camera runs through the deployed TensorRT pose engine
at **~24 FPS**, drawing boxes, 17 keypoints and a posture label. Double-click
**RAPTOR Live Demo** on the Jetson desktop for the video window, or the
`.bat` on the laptop desktop for text output — see
[14](./docs/14-camera-and-live-pipeline.md).

**No pipeline code exists yet.** These are characterised, deployed, demonstrable
components — not a perception system. No detector node, tracker, posture
classifier, trigger logic or victim report; that is roadmap phases 1–5. The
flight camera (A8 mini + HDMI capture card) has still never been tested — the
bench camera is a USB webcam on a USB 2.0 port.
