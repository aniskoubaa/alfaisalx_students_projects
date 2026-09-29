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

1. **"Is there a person?"** — a detector trained on aerial imagery (YOLO26s on
   VisDrone) + ByteTrack, every frame, ~30 FPS.
2. **"What posture?"** — pose keypoints on crops of each tracked person
   (YOLO26s-pose), gravity-aligned using the drone's own IMU attitude, fed to a small
   custom classifier: standing / sitting / crouching / lying / unknown.
   Deterministic, explainable, effectively free.
3. **"What is happening to them?"** — a small vision-language model (Qwen3-VL-2B)
   run **only when tiers 1-2 trigger it** — a new person, a posture that became
   alarming, prolonged immobility, or an operator request.

(Model choices as re-evaluated on 2026-09-28; see docs 10 and 12.)

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
| 10 | [Detector benchmark results](./docs/10-detector-benchmark-results.md) — **measured** on the Orin NX: two rounds; aerial-trained detectors more than double recall on held-out images |
| 11 | [Jetson platform setup](./docs/11-jetson-platform-setup.md) — ROS 2 **Jazzy** (not Humble), how the board gets online, the clock fix |
| 12 | [VLM benchmark results](./docs/12-vlm-benchmark-results.md) — **measured**: two rounds, 7 models, a truthfulness check — and which ones invent injuries |
| 13 | [Bill of materials](./docs/13-bill-of-materials.md) — every part still to buy, with listings and the specs that matter |
| 14 | [Camera, live demo & remote access](./docs/14-camera-demo-and-remote-access.md) — **measured**: USB 2.0 limits, camera → TensorRT end to end; the desktop demo; VNC and RDP |

Start with [`docs/README.md`](./docs/README.md) for the short version.

Two interactive pages sit alongside them: the
[wiring map](./docs/raptor-wiring-map.html) (what plugs into what) and the
[build view](./docs/raptor-build-view.html) (a 3D model of the X500 V2 with every cable routed,
plus to-scale plan and elevation drawings).

## Repository structure

```
RAPTOR/
├── docs/          design documents (01–09), measured results (10, 12, 14),
│                  platform notes (11), bill of materials (13), interactive HTML pages
├── src/           all code, grouped by purpose — start at src/README.md
│   ├── benchmarks/    measure models on the Jetson
│   ├── analysis/      turn results into charts and the Word report (laptop)
│   ├── demo/          the live camera demo and its launchers
│   ├── deploy/        stage models on the board; sync this repo to it
│   ├── setup/         one-time provisioning of the board
│   ├── system/        OS config files, exactly as installed on the board
│   ├── tools/         laptop helpers: internet for the board, access checks
│   └── common/        shared helpers
├── benchmarks/    recorded results (JSONL) and figures — the scientific output
├── reports/       RAPTOR-model-selection-report.docx, generated from benchmarks/
└── assets/        photos (including the bench build) and diagrams
```

**Where does it run?** Most code runs on the **Jetson Orin NX** (`100.100.100.1`);
`src/analysis/` and `src/tools/` run on the **laptop**. The board holds a copy of
`src/` at `~/raptor/src`, refreshed from this repo with
[`src/deploy/sync_to_jetson.sh`](./src/deploy/sync_to_jetson.sh) — the repository is
the source of truth. The [code map](./src/README.md) lists every file.

Model weights, TensorRT engines and datasets are **not** in git — they are large and
regenerable, and live on the board under `~/raptor-models`, `~/raptor-data`,
`~/raptor-vlm` and `~/raptor-deploy`.

See also [`../General Tasks/`](../General%20Tasks) at the repo root for hardware
troubleshooting notes.

## Quick start

| I want to… | |
|---|---|
| see the model on the live camera | double-click **RAPTOR Live Demo** on the Jetson desktop — [src/demo](./src/demo/README.md) |
| connect to the board | VNC `100.100.100.1:5900` or RDP `:3389` — [src/setup](./src/setup/README.md#remote-access) |
| give the board internet | run `src/tools/jetson_internet.sh` on the laptop — [src/tools](./src/tools/README.md) |
| rebuild a freshly flashed board | [src/setup/README.md](./src/setup/README.md), top to bottom |
| read the results | [docs 10](./docs/10-detector-benchmark-results.md), [12](./docs/12-vlm-benchmark-results.md), [14](./docs/14-camera-demo-and-remote-access.md), or the [Word report](./reports/RAPTOR-model-selection-report.docx) |

## Status

**Re-evaluated 2026-09-28** — both model choices were tested against newer
candidates on the flight computer and replaced on measured grounds:

- **Detector: YOLO26s trained on VisDrone**, as a 736×1280 engine, finds
  **42.5 %** of people on held-out aerial images, against 20.0 % for the
  first-round pick, and is the lightest network at that accuracy (11.5 ms of GPU
  compute). RT-DETRv4-S (42.8 %, Apache-2.0) is the alternative if AGPL is ruled
  out ([10](./docs/10-detector-benchmark-results.md)).
- **VLM: Qwen3-VL-2B** (greedy + repetition penalty 1.05) is 100 % schema-valid and
  invented no injuries on 16 uninjured people. The first-round pick, Qwen2.5-VL-3B,
  reported injuries for 7 of them ([12](./docs/12-vlm-benchmark-results.md)).
- Full write-up: Part A of the [Word report](./reports/RAPTOR-model-selection-report.docx).

**Deployed on the board 2026-09-29** at `~/raptor-deploy/`, each artifact loaded and
run on the board, with a provenance manifest recording source, licence, checksum and
measured performance ([`deploy_manifest.json`](./benchmarks/results/deploy_manifest.json)):

| Slot | Artifact | Measured |
|---|---|---|
| tier 1 — detector | `visdrone-yolo26s-736x1280.engine`, lean TensorRT runner | 26.1 ms p95, test-dev recall 0.425 |
| tier 1 — Apache alternative | `visdrone-rtdetrv4-s.engine` | 24.3 ms p95, test-dev recall 0.428 |
| tier 2 — pose on crops | `yolo26s-pose-960.engine` | 22.7 ms p95 |
| tier 3 — VLM | `Qwen3-VL-2B-Instruct`, greedy + repetition penalty 1.05 | 0.21 s first token, 100 % valid JSON |
| tier 3 — fallback | `Qwen3.5-2B`, same decoding | 0.30 s first token, 100 % valid JSON |

The previous set is kept at `~/raptor-deploy.2026-09-20`.

### First measurements (2026-09-20)

Design phase, with the **first measurements taken on the flight computer**
(2026-09-20) — see [10 — Detector benchmark results](./docs/10-detector-benchmark-results.md).

Headline: `yolo11s @ 960` in TensorRT FP16 runs at **25.9 ms p95** on the Orin NX,
inside the 33 ms budget, and TensorRT costs **zero accuracy** versus PyTorch. But
the best measured **person recall on aerial imagery is 0.36** with off-the-shelf
COCO weights — which makes Phase 2 data collection the critical path rather than a
parallel activity.

On tier 3, **Qwen2.5-VL-3B** was confirmed as the primary VLM on measured grounds
(88% vs 0% schema-valid output against SmolVLM2) — *superseded 2026-09-28: it also
invents injuries, which the first round missed; see above*. The unconstrained fallback model
volunteered a person's inferred race, gender and eye colour from an aerial crop —
the exact identity inference [08](./docs/08-limitations-and-safety.md) rules out —
which makes grammar-constrained decoding a **safety control**, not an optimisation.
See [12](./docs/12-vlm-benchmark-results.md).

**Deployed on 2026-09-20** (replaced on 2026-09-29; kept at
`~/raptor-deploy.2026-09-20`, manifest in
[`deploy_manifest_2026-09-20.json`](./benchmarks/results/deploy_manifest_2026-09-20.json)):

| Slot | Artifact | Measured |
|---|---|---|
| tier 1+2 | `yolo11s-pose.engine` @960 FP16 | 26.5 ms p95, 34.4 FPS, 14.5 W |
| tier 1 (detect-only) | `yolo11s.engine` @960 FP16 | 25.9 ms p95, mAP50 0.369, 12.6 W |
| tier 3 | `Qwen2.5-VL-3B-Instruct` | 0.76 s TTFT p95, 88% schema-valid, 19.2 W |
| tier 3 fallback | `SmolVLM2-2.2B-Instruct` | see [12](./docs/12-vlm-benchmark-results.md) — **do not run without a decoding grammar** |

**The board is provisioned and running.** ROS 2 **Jazzy** (195 packages, DDS
pub/sub verified, `vision_msgs` present — Jazzy not Humble because the board is
Ubuntu 24.04), a clock that survives reboots, and network access; see
[11](./docs/11-jetson-platform-setup.md).

**Live demo, clickable.** Double-click **RAPTOR Live Demo** on the Jetson desktop:
the camera runs through the deployed two-stage pipeline — the aerial detector on
every frame, pose and posture on crops of each person — at the webcam's ~24 FPS.
The aerial detector is trained on people seen from above and may not see someone
sitting next to the webcam; **RAPTOR Live Demo (bench)** runs the pose model alone
for that. `--source <folder or video>` plays aerial footage through the real
pipeline. The `.bat` on the laptop desktop gives text output — see
[14](./docs/14-camera-demo-and-remote-access.md).

**No pipeline code exists yet.** These are characterised, deployed, demonstrable
components — not a perception system. No detector node, tracker, posture
classifier, trigger logic or victim report; that is roadmap phases 1–5. The
flight camera (A8 mini + HDMI capture card) has still never been tested — the
bench camera is a USB webcam on a USB 2.0 port.
