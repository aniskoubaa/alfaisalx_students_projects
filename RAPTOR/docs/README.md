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
| 15 | [Next steps](./15-next-steps.md) | Ordered plan from here, risks, and what would change it |
| 13 | [Bill of materials](./13-bill-of-materials.md) | Every part still to buy, with amazon.sa listings, specs that matter, and what is blocked |

### Measured results and platform notes

Written after the first measurements on the flight computer. The raw data is in
[`../benchmarks/`](../benchmarks) and the code that produced it in [`../src/`](../src).

| # | Document | What it covers |
|---|----------|----------------|
| 10 | [Detector benchmark results](./10-detector-benchmark-results.md) | Round 2 (2026-09-28): aerial-trained detectors on a held-out set — YOLO26s on VisDrone chosen, RT-DETRv4-S the Apache alternative. Round 1: YOLO11/YOLOv8/RT-DETR, TensorRT, the ~28 ms framework floor, the recall problem |
| 11 | [Jetson platform setup](./11-jetson-platform-setup.md) | Why Jazzy not Humble, how the board reaches the internet, the clock fix |
| 12 | [VLM benchmark results](./12-vlm-benchmark-results.md) | Round 2 (2026-09-28): 7 models, a truthfulness check — Qwen3-VL-2B chosen, the first pick invents injuries. Round 1: Qwen2.5-VL vs SmolVLM2, with a correction |
| 14 | [Camera, live demo & remote access](./14-camera-demo-and-remote-access.md) | USB 2.0 limits, the model on live frames, the live demo, VNC and RDP |

### Interactive companions

Two HTML pages that sit alongside the numbered docs. Open them in a browser.

| Page | What it is |
|---|---|
| [Wiring map](./raptor-wiring-map.html) | What plugs into what: every connection, the parts list, and the bench build order. |
| [Stability report](./raptor-stability-report.html) | 2026-10-05: camera modes, every test run, what was fixed, open problems, next steps. |
| [Build view](./raptor-build-view.html) | The same harness placed on the airframe &mdash; an interactive 3D model, a to-scale plan view showing the 123 mm prop keep-out, a side elevation of the stack, and per-cable routing. |

## The short version

We run a **three-tier perception stack**, because the three questions we are asked
have very different costs:

1. **"Is there a person?"** — a detector trained on aerial imagery (YOLO26s on
   VisDrone; RT-DETRv4-S if AGPL is ruled out) + tracking, every frame, ~30 FPS.
2. **"What posture are they in?"** — pose keypoints on crops of each tracked person
   (YOLO26s-pose), fed to a small custom classifier (standing / sitting /
   crouching / lying / unknown). Cheap and *deterministic* — we do not ask a
   language model something that geometry answers better.
3. **"What is happening to them / do they look injured?"** — a small
   vision-language model (Qwen3-VL-2B) run **only on triggered events**, not per
   frame. This is the expensive tier, so we spend it deliberately.

Model choices as re-evaluated on 2026-09-28 ([10](./10-detector-benchmark-results.md),
[12](./12-vlm-benchmark-results.md)). Tiers 1 and 2 used to be one pose model; no
aerial-trained pose model exists, so they are now two stages.

The single most important architectural decision in this project is that **tier 3 is
event-driven**. A 3B VLM cannot run at 30 FPS on an Orin NX and does not need to.
Tiers 1–2 decide *when* it is worth spending 3–5 seconds on a description.

Rationale for every model choice is in documents 02, 03 and 05 — including the
alternatives we rejected and why.

## Open questions

These affect the recommendations and need answers from the team:

- ~~**Orin NX 8 GB or 16 GB?**~~ **Answered: 16 GB**, confirmed on the board
  (*Orin NX Engineering Reference Developer Kit Super*, Seeed reComputer J401).
- ~~**Camera model and interface?**~~ **Answered in [01](./01-system-overview.md):** SIYI
  A8 mini over micro-HDMI into a USB capture card. Not yet tested on the bench — the
  live runs in [14](./14-camera-demo-and-remote-access.md) used a USB webcam.
- Do we still own an **Orin Nano** as a bench/dev board? `General Tasks/` records a
  factory reset of "the Jetson Orin Nano" — but that attempt failed, which is also
  what you would expect if it was in fact this Orin NX on its Seeed J401 carrier,
  whose recovery procedure differs from NVIDIA's Orin Nano dev kit. Needs a person to
  check. If a Nano exists, it becomes the "low-spec floor" we validate against.
