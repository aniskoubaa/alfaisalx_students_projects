# U-SCAR — Onboard Perception Design

**Progress report · 2026-09-16**
Author: Majd Awad · Project: U-SCAR · Phase: design (no pipeline code yet)

---

## 1. Summary

This session took U-SCAR from a one-paragraph README to a complete, argued design for the
onboard compute stack, and resolved the hardware unknowns that were blocking it.

**What the system does.** U-SCAR is a search-and-rescue quadcopter. For every person it
finds it produces a geolocated victim report carrying a snapshot, a posture, a free-text
description, and a triage flag for a human operator to review.

**The core decision.** The three questions the system must answer — *is someone there*,
*what posture are they in*, *what is happening to them* — cost wildly different amounts of
compute. So they get three tiers, and the expensive one is gated:

| Tier | Question | Method | Rate |
|---|---|---|---|
| 1 | Is there a person? | YOLO11-pose + ByteTrack, TensorRT INT8 | every frame, ~30 fps |
| 2 | What posture? | Gravity-aligned keypoint classifier (ours) | every frame, <1 ms |
| 3 | What is happening? | Qwen2.5-VL-3B at INT4, **event-triggered** | ~0.2 Hz |

A 3B VLM on an Orin NX produces tens of tokens per second — seconds per description. It
cannot run at frame rate and does not need to. Tiers 1–2 decide when spending those seconds
is worth it. **This gating is the single decision the whole architecture depends on.**

**Status.** Design complete and documented. Hardware identified and specified. No pipeline
code written. Phase 0 (flash, ROS 2, camera and MAVROS publishing) is the next step and is
currently blocked only on a 12 V bench power supply for the camera.

---

## 2. Hardware — confirmed this session

| Component | Confirmed spec | How confirmed |
|---|---|---|
| Companion computer | **Jetson Orin NX 16 GB** | `free -h` reported 15Gi |
| Flight controller | **Pixhawk 6C** | Stated by team |
| Camera | **SIYI A8 mini 4K**, 3-axis gimbal, 95 g | Stated by team |
| Camera optics | Sony 1/1.7″ 8 MP, f/2.8, **81° H / 93° D FOV** | A8 mini User Manual v1.10 |
| Camera video path | **RTSP over Ethernet** — `rtsp://192.168.144.25:8554/video1` | Manual v1.10, p.62 |
| Camera power | **11–25.2 V (3S–6S)**, 5 W avg / 12 W peak | Manual v1.10, p.16 |
| Camera USB-C | **Firmware upgrade only** — not power, not video | Manual + empty `dmesg` on the Jetson |
| Gimbal control | SIYI SDK over UDP, same Ethernet link | Manual v1.10 |
| Recording | 4K @ 25 fps H.265 to microSD (zoom disabled in 4K) | Manual v1.10, p.17 |

The 16 GB board settles the model choice: **Qwen2.5-VL-3B at INT4 fits comfortably**
alongside the TensorRT engines and ROS 2. The 8 GB fallback ladder is not needed.

### Harness

Every device taps the battery in parallel. Nothing routes through the Pixhawk.

```
LiPo main lead (XT60) ─┬─> power module ──(6-pin JST-GH)──> Pixhawk POWER1   [5 V + sensing]
                       ├─> ESCs / motors                                     [pack voltage]
                       ├─> SIYI A8 mini power cable                          [11–25.2 V, own branch]
                       └─> DC regulator ─────────────────> Jetson Orin NX    [carrier-dependent]

LiPo balance lead (5-pin JST-XH) ──> charger only. Never a power source.

Data:  A8 mini ──Ethernet──> Jetson        [RTSP video + gimbal UDP, one cable]
       Pixhawk TELEM1 ──────> Jetson        [MAVLink / MAVROS, read-only]
       A8 mini UART ────────> TELEM2        [optional: attitude feed + photo EXIF geotag]
```

Interactive version: [`U-SCAR/docs/uscar-wiring-map.html`](../U-SCAR/docs/uscar-wiring-map.html)

---

## 3. Design decisions and rationale

### 3.1 Detector — YOLO11-pose

One pose model rather than a detector plus a pose model: the `-pose` variant already emits
person boxes, so running both would double the cost for nothing. ByteTrack for identity
because it keeps low-confidence boxes alive, which is exactly the regime small aerial
targets live in. TensorRT INT8, calibrated on our own footage rather than COCO.

**Rejected:** YOLOv8 (superseded), RT-DETR (heavier at our input sizes, fiddlier to export —
but the fallback if licensing forces it), NVIDIA PeopleNet (ground-level viewpoint bias),
any cloud API (violates the offline constraint).

**Open licensing risk:** Ultralytics YOLO is AGPL-3.0. Acceptable for an open academic
project, contagious if U-SCAR ships to a third party without source. This must be decided
before code is built on it.

### 3.2 Posture — a small model we build ourselves

Posture is a geometry question and gets a geometric answer: the torso vector from 17 COCO
keypoints. Deterministic, explainable to an operator, effectively free, and it cannot
hallucinate. Asking a VLM the same question costs seconds and sometimes invents an answer.

The non-obvious part is **gravity alignment**. During a banked turn the whole image rotates,
so a standing person's torso reads as horizontal and a naive classifier raises a false
casualty. We rotate keypoints into a gravity-aligned frame using the Pixhawk's own roll
estimate, arriving over MAVROS, before classifying.

No public model does this, because no public model has our IMU stream. A two-layer MLP on
normalised keypoints, under 100 KB, trainable on a few thousand labelled frames.
**This is the genuinely novel and publishable component of the project.**

### 3.3 Scene understanding — a VLM, not an LLM

A text-only LLM cannot see the camera; the best it could do is paraphrase YOLO's labels,
which adds nothing. The value — *dark staining on the trouser leg*, *an arm bent
unnaturally*, *trapped under debris* — lives in pixels no detector describes.

**Chosen:** Qwen2.5-VL-3B-Instruct at INT4. Fits in ~2–2.5 GB, best-in-class small model for
fine visual detail, real region grounding so it can be pointed at *our* detected person, and
native dynamic resolution so small crops are not squashed to a fixed size.
*Action required: verify the specific checkpoint's licence — the family is not uniformly Apache.*

**Fallbacks:** VILA-1.5-3B (NVIDIA-optimised for Jetson), SmolVLM2 (Apache, tiny),
Moondream2. **Rejected:** cloud APIs (no link in a disaster area), LLaVA-1.6 7B (poor
size-to-quality trade), Florence-2 as primary (not instruction-following).

**Two rules keep it honest:** ground it — send the person crop with a 30 % context margin
plus the structured facts tiers 1–2 already established; and constrain it — grammar-forced
JSON against a fixed schema, including a `not_visible` field so uncertainty has somewhere to
go other than invention.

### 3.4 Build, fine-tune, or use

| Component | Verdict |
|---|---|
| Person detector | **Fine-tune.** COCO-pretrained backbone on aerial SAR data. Training from scratch would be strictly worse and cost a semester. |
| Pose estimator | **Use off the shelf.** |
| Posture classifier | **Build it.** Needs our IMU-derived gravity alignment; nothing public has that. |
| Action recognition | **Defer.** Posture + motion may already cover the critical cases. |
| VLM | **Use off the shelf.** We lack the data to fine-tune, and a LoRA on a few hundred staged casualties would learn our volunteers' clothing, not injury. |

Fine-tuning the detector is not optional: stock YOLO trained on ground-level photographs
systematically misses **prone people seen from above**, which is the exact failure we can
least afford. Candidate datasets: HERIDAL, SARD, Okutama-Action, VisDrone, TinyPerson.

### 3.5 ROS 2

Five nodes on Humble: `camera_node`, `detector_node`, `vlm_node`, `triage_aggregator_node`,
`mavros`. The detector and VLM are separate nodes on separate CUDA streams, so a four-second
inference cannot stall perception — and if the VLM node dies, the system degrades to
posture-only reporting rather than going blind.

Recording every topic to `rosbag2` on every flight is what makes the rest tractable:
benchmarks replay identical bags instead of demanding new flights, and the same bags become
the labelled dataset, complete with the synchronised GPS and attitude the posture classifier
depends on — which cannot be recovered afterwards.

---

## 4. Key finding: the altitude ceiling is lower than assumed

The A8 mini's **81° horizontal FOV** gives a focal length of ~1124 px across a 1920 px frame.
Geometric prediction, nadir view, no zoom:

| Altitude | Standing (1.7 m) | Prone from overhead (0.45 m) | Ground swath |
|---|---|---|---|
| 20 m | 96 px | 25 px | 34 m |
| 25 m | 76 px | **20 px** | 43 m |
| 30 m | 64 px | 17 px | 51 m |
| 40 m | 48 px | 13 px | 68 m |
| 60 m | 32 px | 8 px | 103 m |

Against a practical detection floor of ~20 px, **a prone casualty falls below it at roughly
25 m**. The wide lens buys coverage and costs pixels.

If this holds in measurement it is the most operationally important number the project will
produce, and it forces a choice: fly lower than the coverage-optimal altitude, or adopt
tiled inference (experiment E4). It must be confirmed against the *streamed* resolution,
which may be below 1920 px.

*Note: earlier drafts of the design docs assumed a 60° FOV. Those figures were corrected on
2026-09-16 once the manual was consulted. The real optics make the problem harder, not easier.*

---

## 5. Deliverables produced

| File | Contents |
|---|---|
| `U-SCAR/docs/README.md` | Index and short version |
| `U-SCAR/docs/01-system-overview.md` | Mission, hardware, constraints, data flow |
| `U-SCAR/docs/02-detection-and-pose.md` | Detector and posture choices, rejected alternatives |
| `U-SCAR/docs/03-scene-understanding-vlm.md` | VLM selection, prompting, output schema |
| `U-SCAR/docs/04-ros2-architecture.md` | Node graph, topics, custom messages |
| `U-SCAR/docs/05-custom-models-and-data.md` | Build vs. fine-tune vs. use; datasets; evaluation |
| `U-SCAR/docs/06-benchmark-plan.md` | Experiments E1–E8, performance budget, method |
| `U-SCAR/docs/07-roadmap.md` | Phases 0–6, milestones, risks |
| `U-SCAR/docs/08-limitations-and-safety.md` | Failure modes, privacy, GACA, model card |
| `U-SCAR/docs/uscar-explainer.html` | Animated explainer — live pipeline sim, interactive figures |
| `U-SCAR/docs/uscar-wiring-map.html` | Interactive harness diagram and connector reference |

---

## 6. Open questions

| # | Question | Blocks |
|---|---|---|
| 1 | Which **carrier board** is the Orin NX on? | Regulator output voltage — 5 V, 12 V or 19 V |
| 2 | **ArduPilot or PX4** on the Pixhawk 6C? | The optional gimbal UART parameters |
| 3 | Actual **streamed** resolution and frame rate over RTSP | The altitude table above; detector input sizing |
| 4 | H.264 or H.265 on the stream? | GStreamer pipeline elements |
| 5 | Is the **AGPL-3.0** licence on Ultralytics acceptable? | Whether we build on YOLO11 at all |
| 6 | Rename `jetson_orin_nano_benchmarks/`? | Flight computer is an NX; a Nano also exists as a bench board |

---

## 7. Next steps — Phase 0

Blocked on one purchase: a **bench DC supply** (12 V, 2 A limit). Current limiting means a
wiring mistake trips the supply instead of destroying the camera.

1. Power the camera alone. Confirm the three-axis self-test sweep and a **solid green** LED.
   *(Yellow blinking = input under 10 V.)*
2. `sudo ip addr add 192.168.144.30/24 dev eth0`, then `ping 192.168.144.25`.
3. `ffplay rtsp://192.168.144.25:8554/video1` — record the true resolution and frame rate.
4. Prove hardware decode: a GStreamer pipeline using `nvv4l2decoder`.
5. Flash JetPack 6.x; record CUDA / TensorRT / cuDNN versions.
6. Install ROS 2 Humble; `talker`/`listener`.
7. Pixhawk TELEM1 → Jetson; bring up MAVROS; confirm GPS and attitude as topics.
8. Sync the Jetson clock to flight-controller time.
9. Record a rosbag and replay it. **This is the Phase 0 finish line.**

Steps 5–8 need no camera and can start immediately.

**Python environment:** the project venv is **`~/raptor-venv`**, created with
`python3 -m venv --system-site-packages ~/raptor-venv`. The flag is mandatory — JetPack's
CUDA PyTorch, TensorRT and OpenCV live in the system site-packages and cannot be reinstalled
from PyPI on aarch64, so a sealed venv silently loses GPU acceleration. Details in
[`docs/09-jetson-environment.md`](../U-SCAR/docs/09-jetson-environment.md).

**Start data collection planning in parallel.** It is the long pole for Phases 3–5: the
consent form, the flight plan across three altitudes and three lighting conditions, and the
labelling workflow all take longer than the code.

---

## 8. Scope boundary

U-SCAR **perceives and reports**. It does not fly the aircraft, plan paths, or command the
flight controller — the Jetson reads telemetry from MAVROS and never writes control commands.
Enforced in code, so a perception bug can never become a flight safety incident.

The system is a **search aid**, not a medical device and not a triage system. The VLM
produces observations; the triage flag is computed by explicit, auditable rules over
structured fields, each carrying a plain-words reason. A human decides what happens.
Placeholder thresholds need review by someone with real SAR or emergency-medicine experience
before any operational use. Full treatment in `docs/08-limitations-and-safety.md`.

---

*Every performance figure in the design documents is a target, not a measurement. The
benchmark plan exists to replace them; until it does, none of them belongs in a report as a
finding.*
