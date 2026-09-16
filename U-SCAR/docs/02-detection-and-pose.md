# 02 — Detection, Tracking and Posture

This is tier 1 + 2: the part that runs on **every frame**. It answers *is there a
person, which person is it, and what posture are they in.*

## Decision summary

| Question | Choice | One-line reason |
|----------|--------|-----------------|
| Detector family | **Ultralytics YOLO11** | Best accuracy/latency at our scale, first-class TensorRT export, tracking built in, huge community |
| Size | **YOLO11s** primary, **YOLO11n** fallback, **YOLO11m** as accuracy ceiling reference | `s` is the knee of the curve on Orin NX; measure all three |
| Pose | **YOLO11s-pose** (17 COCO keypoints) | Same framework, same export path, gives us posture geometry for free |
| Detector + pose | **One pose model, not two models** | `-pose` already emits person boxes; running a separate detector doubles cost for nothing |
| Precision | **INT8 TensorRT** (calibrated), FP16 as the correctness baseline | 2–3× throughput; must be validated against FP16 mAP, not assumed |
| Tracking | **ByteTrack** | Strong with low-confidence boxes — exactly our aerial small-object case; no re-ID net needed |
| Posture | **Our own small classifier on normalised keypoints** | Geometry problem, not a language problem. See below — this is the one model we should genuinely build ourselves |

## Why YOLO11 (and what we rejected)

**YOLO11 (Ultralytics).** Chosen because:
- Excellent accuracy-per-millisecond in the nano/small range we are forced into.
- `model.export(format="engine", int8=True)` gives a working TensorRT engine without
  us hand-writing plugins — on Jetson this saves weeks.
- Detection, pose, and segmentation share one API and one export path. We get
  keypoints without adopting a second framework.
- ByteTrack/BoT-SORT integrated, so tracking is a config flag rather than a project.
- Very large body of published work on aerial/VisDrone fine-tuning to copy from.

**Licensing caveat, read this:** Ultralytics YOLO (v8/v10/v11) is **AGPL-3.0**. For an
academic project published openly this is fine. If U-SCAR is ever commercialised or
shipped to a third party without source, AGPL is contagious and we would need an
Ultralytics commercial licence or a permissive alternative. Decide this **before** we
build on it, not after. Permissive escape hatches: YOLOX (Apache-2.0), RT-DETR
(Apache-2.0 in the PaddleDetection/HF lineage), or NVIDIA TAO's DetectNet_v2/PeopleNet.

Alternatives considered:

| Option | Why not (for now) |
|--------|-------------------|
| **YOLOv8** | Fine, and more battle-tested, but YOLO11 is the same API with better acc/latency. Keep as fallback if we hit a YOLO11 export bug. |
| **RT-DETR** | Transformer detector, no NMS, Apache-licensed lineage — attractive. But heavier at our input sizes and historically fiddlier to export to TensorRT on Jetson. **Revisit if AGPL becomes a blocker.** |
| **NVIDIA PeopleNet (TAO)** | Purpose-built person detector, DeepStream-native, commercially licensable. Weakness: trained on ground-level/CCTV viewpoints and not easy to fine-tune outside the TAO toolchain. Good backup, poor primary. |
| **Cloud detection API** | Violates the offline constraint. Non-starter. |
| **Training a detector from scratch** | See [05](./05-custom-models-and-data.md) — a bad use of our time. Fine-tuning a pretrained backbone gets us 95% of the benefit for 2% of the effort. |

## Why pose estimation instead of asking the VLM "is he lying down?"

This is worth being explicit about, because it is the design decision students most
often get wrong.

The question *"is this person standing, sitting, crouching or lying down?"* is a
**geometry** question. Given 17 keypoints you can answer it from the angle of the
torso vector (shoulder-midpoint → hip-midpoint) relative to gravity, the vertical
spread of the keypoints, and the hip–knee–ankle angles. That computation is:

- **~0 ms** on top of the pose model we are already running,
- **deterministic and explainable** — we can show the operator *why* it said "lying",
- **stable frame-to-frame**, so we can require N consecutive frames before we trust it,
- and it **cannot hallucinate**.

Asking a 3B VLM the same question costs seconds, gives a different answer on
consecutive frames, and occasionally invents a confident wrong one. Use the VLM for
what only a VLM can do — open-ended description, context, unusual detail — and use
geometry for geometry.

The pose tier is also what **triggers** the VLM. "Lying, immobile for 20 s" is a far
better trigger than "a person appeared", and it is what keeps tier 3 affordable.

## The posture classifier — our own model

Do not hand-tune thresholds forever. The plan:

1. Run YOLO11s-pose over our own recorded flight footage.
2. **Normalise** each person's 17 keypoints: translate to hip-midpoint origin, scale
   by torso length, and — critically — **rotate into a gravity-aligned frame using the
   drone's attitude from MAVROS**, so a banked turn doesn't turn a standing person
   into a "lying" one. This step is the whole trick and is why an off-the-shelf action
   model won't beat us here.
3. Add per-keypoint visibility/confidence as features (occlusion is informative).
4. Train a **small MLP (~2 hidden layers) or gradient-boosted tree** on
   `{standing, sitting, crouching, lying, unknown}`. A few thousand labelled frames is
   enough. The model is <100 KB and runs in microseconds on CPU.
5. Temporal smoothing: majority vote over a ~1 s window + hysteresis, so the label
   doesn't flicker.
6. Add a **motion feature** from the track history (keypoint displacement over 10–30 s).
   "Lying AND immobile" is the high-value signal; "lying AND moving" is much less alarming.

This is a genuinely good student deliverable: small, self-contained, publishable,
and it measurably outperforms both hand-tuned thresholds and a VLM at this specific task.

## Input resolution

Aerial people are *small*. At 640×640 a person at 40 m altitude may be 15–25 px tall,
near the limit of what YOLO's stride-32 head resolves. Options to benchmark:

- **832 or 960 input** instead of 640 — the simplest win, costs roughly linearly in
  pixels.
- **Tiled / sliced inference (SAHI-style)** — split the frame into overlapping tiles,
  run the detector per tile, merge. Big recall gain on tiny objects, big cost multiplier.
  Candidate for a "careful search" mode at low speed, not for continuous flight.
- **Fly lower / zoom the gimbal** — often the cheapest fix and it costs no compute.
  Worth quantifying as an operational recommendation, e.g. "search at 30 m, not 60 m".

Measure all three; the altitude-vs-recall curve is one of the more useful results this
project can produce.

## Implementation path

- Phase A: Ultralytics PyTorch on the Jetson, FP16, 640. Correct but slow. Baseline.
- Phase B: export to TensorRT FP16, then INT8 with a calibration set drawn from **our
  own flight footage** (not COCO — calibration data must match deployment distribution).
- Phase C: measure DLA offload of the detector; if the detector fits DLA with
  acceptable fallback, the GPU is freed for the VLM.
- Phase D: consider NVIDIA **Isaac ROS** (`isaac_ros_yolov8` / NITROS) for zero-copy
  GPU memory between ROS 2 nodes. On Jetson, the CPU-side memcpy between nodes is a
  real cost; NITROS removes it. Adopt only after Phase B works, to avoid debugging two
  things at once.
