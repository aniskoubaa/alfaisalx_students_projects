# RAPTOR — Jetson Orin NX Software Documentation

Design documents for the onboard compute side of RAPTOR: a quadcopter that searches
for people, works out **where they are, what posture they are in, and whether they
show signs of injury**, and reports that to a ground operator.

The airframe and flight controller already exist. Everything documented here runs on
the **Jetson Orin NX** carried by the drone.

## Read in this order

| # | Document | What it covers |
|---|----------|----------------|
| 01 | [System overview](./01-system-overview.md) | Mission, hardware, constraints, end-to-end data flow |
| 02 | [Detection & pose](./02-detection-and-pose.md) | Which YOLO, why, tracking, posture classification |
| 03 | [Scene understanding (VLM)](./03-scene-understanding-vlm.md) | Which vision-language model, why, prompting, triggering |
| 04 | [ROS 2 architecture](./04-ros2-architecture.md) | Node graph, topics, message types, MAVROS bridge |
| 05 | [Custom models & data](./05-custom-models-and-data.md) | Build vs. fine-tune vs. buy, datasets, what we should train ourselves |
| 06 | [Benchmark plan](./06-benchmark-plan.md) | What we measure, how, and the numbers we must hit |
| 07 | [Roadmap](./07-roadmap.md) | Phases, milestones, definition of done |
| 08 | [Limitations & safety](./08-limitations-and-safety.md) | What this system is not, human-in-the-loop, privacy |
| 09 | [Jetson environment](./09-jetson-environment.md) | Venv, PEP 668, CUDA torch, board commands |

## The short version

We run a **three-tier perception stack**, because the three questions we are asked
have very different costs:

1. **"Is there a person?"** — YOLO11 detection + tracking, every frame, ~30 FPS.
   Cheap, reliable, well-understood.
2. **"What posture are they in?"** — YOLO11-pose keypoints fed to a small custom
   classifier (standing / sitting / crouching / lying / unknown). Still cheap,
   still every frame, and *deterministic* — we do not ask a language model
   something that geometry answers better.
3. **"What is happening to them / do they look injured?"** — a small
   vision-language model (Qwen2.5-VL-3B class) run **only on triggered events**,
   not per frame. This is the expensive tier, so we spend it deliberately.

The single most important architectural decision in this project is that **tier 3 is
event-driven**. A 3B VLM cannot run at 30 FPS on an Orin NX and does not need to.
Tiers 1–2 decide *when* it is worth spending 3–5 seconds on a description.

Rationale for every model choice is in documents 02, 03 and 05 — including the
alternatives we rejected and why.

## Open questions

These affect the recommendations and need answers from the team:

- **Orin NX 8 GB or 16 GB?** This changes the VLM choice materially. The docs assume
  16 GB and give an 8 GB fallback path.
- **Camera model and interface** (CSI/MIPI vs. USB vs. IP/RTSP)? This decides the
  capture node and whether we get zero-copy into the GPU.
- Do we still own an **Orin Nano** as a bench/dev board? (`General Tasks/` suggests
  yes.) If so it becomes the "low-spec floor" we validate against.
