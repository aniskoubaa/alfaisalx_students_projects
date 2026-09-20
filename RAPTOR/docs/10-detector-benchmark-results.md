# 10 — Detector Benchmark Results (first round)

Measured on the flight computer, 2026-09-20. Raw rows:
[`results/detector.jsonl`](../jetson_orin_nano_benchmarks/results/detector.jsonl) and
[`results/raw_forward.jsonl`](../jetson_orin_nano_benchmarks/results/raw_forward.jsonl).
Figures: [`figures/`](../jetson_orin_nano_benchmarks/figures).

This is experiment **E1** from [06](./06-benchmark-plan.md), plus a TensorRT data
point from Phase B of [02](./02-detection-and-pose.md). E2 (INT8), E3 (altitude),
E4 (tiling), E7 (contention) and E8 (end-to-end) are **not** done — see
[§ What this does not tell us](#what-this-does-not-tell-us).

## Conditions

| | |
|---|---|
| Board | Jetson Orin NX 16 GB (Seeed reComputer J401) |
| Software | JetPack 7.2 / L4T 39.2.0, **Ubuntu 24.04.4**, CUDA 13.0, TensorRT 10.16.2 |
| Stack | torch 2.14.0+cu130, ultralytics 8.4.154 |
| Power mode | **25 W** (`nvpmodel` mode 3), `jetson_clocks` **not** pinned |
| Precision | FP16 throughout |
| Data | VisDrone-DET val, single `person` class — 548 images, 13,969 boxes, ~25 people/image |
| Protocol | 50 warm-up inferences discarded, 200 frames measured, `tegrastats` sampled throughout |

**The board runs Ubuntu 24.04, not 22.04.** [04](./04-ros2-architecture.md) and
[07](./07-roadmap.md) both assume JetPack 6.x and ROS 2 Humble. Humble has no
24.04 binaries; **Jazzy** is the correct pairing for this image. That also means
NVIDIA Isaac ROS (Humble-targeted) becomes a container decision rather than a
native install — relevant to Phase D in [02](./02-detection-and-pose.md).

## Detection results

| Model | Input | Backend | p95 ms | FPS | mAP@0.5 | mAP@0.5:0.95 | Precision | Recall | Power W | Peak GPU MB |
|---|---|---|---|---|---|---|---|---|---|---|
| yolo11n | 640 | PyTorch | 29.1 | 29.9 | 0.159 | 0.057 | 0.434 | 0.180 | 8.4 | 44 |
| yolo11s | 640 | PyTorch | 29.2 | 29.5 | 0.247 | 0.095 | 0.480 | 0.268 | 9.8 | 64 |
| yolo11n | 832 | PyTorch | 29.7 | 29.4 | 0.233 | 0.089 | 0.470 | 0.250 | 9.4 | 49 |
| yolo11s | 832 | PyTorch | 29.9 | 28.8 | 0.326 | 0.136 | 0.540 | 0.327 | 12.1 | 71 |
| yolo11n | 960 | PyTorch | 30.1 | 29.5 | 0.268 | 0.109 | 0.481 | 0.283 | 10.2 | 52 |
| yolo11s | 960 | PyTorch | 30.4 | 29.2 | 0.369 | 0.158 | 0.563 | 0.361 | 13.3 | 77 |
| yolo11m | 640 | PyTorch | **34.7** ✗ | 25.5 | 0.307 | 0.125 | 0.573 | 0.300 | 12.7 | 95 |
| **yolo11s** | **960** | **TensorRT** | **25.9** | **30.1** | **0.369** | **0.159** | 0.558 | **0.363** | 12.6 | 98 |

✗ = exceeds the 33 ms hard limit.

### Pose models (latency only)

VisDrone has no keypoint labels, so these carry no accuracy figure. They are here
because tier 2 needs keypoints and [02](./02-detection-and-pose.md) specifies
**one pose model rather than a separate detector** — so pose latency, not detect
latency, is what the frame budget must actually accommodate.

| Model | Input | p95 ms | Power W | In budget |
|---|---|---|---|---|
| yolo11n-pose | 640 | 31.7 | 8.6 | yes |
| yolo11n-pose | 832 | 32.2 | 9.6 | yes |
| yolo11s-pose | 640 | 32.3 | 10.0 | yes |
| yolo11s-pose | 960 | 32.8 | 13.5 | yes |
| yolo11n-pose | 960 | 32.9 | 10.2 | yes |
| yolo11s-pose | 832 | **33.0** | 12.2 | **marginal** |
| **yolo11s-pose** | **960** | **26.5 (TensorRT)** | 14.5 | **yes, with 6.5 ms spare** |

**Every pose configuration sits within 1 ms of the hard limit in PyTorch.** Tier 2
has no headroom at all on that stack, and that is before ByteTrack, the posture
classifier, or anything else shares the board.

TensorRT fixes it. The same weights, same input size:

| yolo11s-pose @960 | PyTorch | TensorRT | change |
|---|---|---|---|
| mean latency | 30.2 ms | **20.4 ms** | −32% |
| p95 latency | 32.8 ms | **26.5 ms** | −19% |
| headroom to 33 ms | 0.2 ms | **6.5 ms** | 32× more |
| power | 13.5 W | 14.5 W | +1 W |

Stage breakdown for the TensorRT engine: **preprocess 3.3 ms, inference 12.7 ms,
postprocess 3.5 ms**. Inference is now only 62% of the frame cost — a third of the
budget goes on Python-side image handling and NMS. That is the strongest argument
yet for composable nodes and zero-copy (NITROS) in
[04](./04-ros2-architecture.md): the next big win is not a faster model.

## Three findings

### 1. Resolution beats capacity

yolo11s @ 960 beats yolo11m @ 640 on **accuracy (0.369 vs 0.307), latency
(30.4 vs 34.7 ms) and power (13.3 vs 12.7 W is a near tie, but yolo11m misses the
budget)**. yolo11m is dominated and should leave the shortlist for this input
regime.

This is what [02](./02-detection-and-pose.md) predicted: when targets are 15–25 px
tall, the limit is pixels on target, not model capacity. Going from 640 to 960
raised yolo11s mAP from 0.247 to 0.369 — a **49% relative gain for ~1 ms**.

### 2. The measured latency was framework overhead, not compute

Across the PyTorch sweep, p95 moved 29.1 → 30.4 ms while mAP went 0.159 → 0.369
and power went 8.4 → 13.3 W. Power rising while wall-clock stands still means the
GPU is doing much more work in the same elapsed time.

Timing `forward()` alone, with Ultralytics' `predict()` wrapper removed:

| Model | Input | Forward-only mean ms | Power W |
|---|---|---|---|
| yolo11n | 640 | 28.2 | 9.6 |
| yolo11n | 960 | 28.5 | 13.0 |
| yolo11s | 640 | 28.3 | 12.4 |
| yolo11s | 960 | **27.7** | **21.7** |
| yolo11m | 640 | 36.0 | 18.4 |
| yolo11m | 960 | 54.5 | 23.0 |

The small models sit on a **~28 ms floor** irrespective of input size, while
yolo11m scales normally. That is the signature of being **CPU kernel-launch
bound**: PyTorch eager mode dispatches hundreds of small CUDA kernels per forward,
and Orin's CPU cannot issue them faster than that.

TensorRT confirms it — the same weights, same precision, same input:

| | PyTorch | TensorRT | change |
|---|---|---|---|
| mean latency | 28.8 ms | **24.2 ms** | −16% |
| p95 latency | 30.4 ms | **25.9 ms** | −15% |
| mAP@0.5 | 0.3687 | **0.3687** | none |
| recall | 0.361 | 0.363 | none |
| power | 13.3 W | 12.6 W | −5% |

Two things follow. **FP16 TensorRT export costs zero accuracy here** — worth
knowing before anyone spends time worrying about it. And the gain is 15%, not 3×,
which means once inference is fused the remaining cost is Python-side
preprocessing and NMS. That is the argument for composable nodes and zero-copy
(NITROS) in [04](./04-ros2-architecture.md), now with a number attached.

> Note the power column in the forward-only table: yolo11s @ 960 draws **21.7 W**
> when the framework stops throttling it — over the 20 W sustained target from
> [06](./06-benchmark-plan.md). The comfortable power figures in the main table
> are partly an artefact of the GPU idling between kernel launches. Power must be
> re-measured once the pipeline is efficient.

### 3. Recall is the problem, and it is worse than the latency story

The best configuration measured **recall 0.363**. An off-the-shelf COCO-pretrained
detector finds roughly **one in three** annotated people in aerial imagery. The
weakest configuration (yolo11n @ 640) finds fewer than one in five.

[05](./05-custom-models-and-data.md) names recall at high precision as the headline
metric, because in SAR a missed person is far worse than a false alarm. By that
measure none of these models is fit for deployment yet.

This is not a defect in YOLO; it is the aerial domain gap, quantified. It makes
Phase 2 data collection the **critical path**, not a parallel activity. Two
mitigations cost no compute at all:

- **Fly lower.** Detection scales with pixels on target.
- **Never report a searched area as confirmed clear.** Measured recall does not
  support that claim, and an operator who believes it stops searching too early.

## Alternative architectures

[02](./02-detection-and-pose.md) keeps two non-YOLO11 options on the shortlist:
**YOLOv8** as the battle-tested fallback, and **RT-DETR** as the escape hatch if
Ultralytics' AGPL licence ever becomes a blocker. Both were measured.

| Model | Input | Backend | p95 ms | mAP@0.5 | Recall | Power W | In budget |
|---|---|---|---|---|---|---|---|
| yolov8s | 640 | PyTorch | 23.5 | 0.228 | 0.246 | 10.6 | yes |
| yolov8s | 960 | PyTorch | **25.2** | 0.355 | 0.352 | 14.4 | yes |
| yolo11s | 960 | PyTorch | 30.4 | 0.369 | 0.361 | 13.3 | yes |
| yolo11s | 960 | TensorRT | 25.9 | 0.369 | 0.363 | 12.6 | yes |
| **rtdetr-l** | 960 | PyTorch | **110.7** ✗ | **0.431** | **0.410** | 17.8 | **no** |

### YOLOv8 is faster than YOLO11 here — and that corroborates finding 2

yolov8s @ 960 ran at **25.2 ms p95 in plain PyTorch** — matching yolo11s *in
TensorRT* (25.9 ms) — for 0.355 mAP against 0.369. YOLO11 is the more accurate
architecture per parameter, but on this board it is also the slower one, because
YOLO11's C3k2/C2PSA blocks decompose into more individual CUDA kernels than
YOLOv8's simpler graph. When the bottleneck is kernel dispatch rather than
arithmetic, graph complexity costs wall-clock directly.

Practical consequence: **YOLOv8s is a credible PyTorch-only fallback** if the
TensorRT export path ever fights us, at a cost of about 4% relative mAP.

(Caveat: the YOLO11 sweep and the YOLOv8 runs were separate invocations. The gap
is large and consistent across both input sizes, but a single interleaved re-run
would remove any doubt about drift.)

### RT-DETR is the most accurate model tested, and far too slow

rtdetr-l @ 960 produced **mAP@0.5 0.431 and recall 0.410** — comfortably the best
of anything measured, roughly **17% better mAP and 13% better recall** than
yolo11s @ 960. It is also **110.7 ms p95**, more than three times the hard limit.

Unlike the YOLO models, RT-DETR is genuinely compute-bound: its stage breakdown is
**99.7 ms of inference** against 6.8 ms preprocess and 1.7 ms postprocess. There is
no framework overhead to reclaim here; the work is real.

Three things follow:

- **Accuracy headroom exists.** The aerial recall ceiling in finding 3 is a
  property of these small models, not of the task. A larger model finds
  meaningfully more people.
- **RT-DETR is a candidate for a "careful search" mode**, not for continuous
  flight. [02](./02-detection-and-pose.md) already contemplates a slow, high-recall
  mode for tiled inference; ~9 FPS is plausible for a deliberate hover-and-scan
  over a suspected location, and it would find more casualties than the fast path.
- **The licence escape hatch costs speed, not accuracy.** If AGPL ever forces the
  move to RT-DETR (Apache-licensed lineage), the sacrifice is throughput. That
  reframes the licensing decision usefully — and TensorRT plus INT8 has not yet
  been tried on it.

**Known issue:** `rtdetr-l @ 640` failed during validation with
`RuntimeError: Expected all tensors to be on the same device, but found at least
two devices, cuda:0 and cpu` — an Ultralytics RT-DETR validator bug, not a board
problem. The 960 run completed normally. Not chased further; recorded here so the
gap in the results table is explained rather than mysterious.

## What this does not tell us

- **Nothing about prone casualties specifically.** VisDrone is urban — roads,
  squares, car parks. It contains no casualties and essentially no prone figures.
  The failure mode RAPTOR most needs to measure is precisely the one this dataset
  cannot measure. HERIDAL and SARD are the right next datasets.
- **Nothing about pose or posture accuracy** — no keypoint labels, and the posture
  classifier does not exist yet.
- **Nothing about thermals.** Runs were minutes; any thermal claim needs 20 minutes
  minimum. Peak observed was 67 °C during the TensorRT run, with no throttling seen.
- **Nothing about contention (E7).** The detector and VLM have not yet run
  simultaneously, which is the experiment that decides whether DLA offload is
  required.
- **Nothing about INT8 (E2).** Deliberately not attempted: calibration must use our
  own aerial footage, and calibrating on COCO or VisDrone and deploying on our
  imagery is a documented way to lose accuracy silently.

## Two environment defects found

**1. PyTorch has no kernels for this GPU.** `torch 2.14.0+cu130` is the generic
PyPI aarch64 wheel, built for compute capabilities 8.0/9.0/10.0/11.0/12.0. Orin is
**8.7**. It works — CUDA JIT-compiles PTX for sm_87 — but these are not NVIDIA's
sm_87-tuned kernels. **Every number in this document is a floor.** Installing
NVIDIA's Jetson build for JetPack 7 and re-running is the highest-value fix
outstanding.

**2. The board clock reads 1970-01-01.** No RTC battery, and no NTP because the
Jetson has no network route. Every result row in this round carries a 1970
timestamp. [04](./04-ros2-architecture.md) warns that a wrong clock silently
corrupts timestamp correlation and geolocation — fix this before recording any
rosbag. A temporary fix from a networked machine on the same link:

```bash
ssh alfaisal-x-nx@100.100.100.1 "sudo date -u -s '$(date -u +'%Y-%m-%d %H:%M:%S')'"
```

## Recommendation, and what is deployed

**`yolo11s-pose @ 960, FP16, TensorRT`** is the tier-1+2 model — it emits person
boxes *and* the 17 keypoints tier 2 needs, at 26.5 ms p95 with 6.5 ms of headroom.
Per [02](./02-detection-and-pose.md), running a separate detector alongside it
would double the cost for nothing.

**`yolo11s @ 960, FP16, TensorRT`** is deployed alongside it as the detection-only
baseline, for A/B work and for a degraded mode where keypoints are not needed.

Both are staged under `~/raptor-deploy/` on the board with a provenance manifest
(`MANIFEST.json`) recording source weights, SHA, build environment, and the
measured numbers above. Each was verified by loading and running it after staging.
Regenerate with `scripts/deploy_models.py --verify`.

> **Engines are not portable.** A `.engine` is tied to this TensorRT version and
> GPU. Re-export after any JetPack upgrade; never copy one between boards.

Next, in order:

1. Install NVIDIA's sm_87 PyTorch build and re-run — everything here is a floor.
2. Fix the board clock before any rosbag is recorded.
3. Attack preprocess + NMS, not the model: they are now 38% of the frame budget.
4. Re-measure inside a long-running ROS 2 node rather than per-process runs.
5. Run the power-mode sweep (10/15/25/40 W). The board supports **40 W** and
   MAXN_SUPER; everything here was measured at 25 W, and the delta decides whether
   the extra watts are worth the endurance cost.
6. Start Phase 2 collection flights. Finding 3 is the justification.
