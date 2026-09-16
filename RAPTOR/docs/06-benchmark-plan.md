# 06 — Benchmark Plan

This document defines what the existing
[`jetson_orin_nano_benchmarks/`](../jetson_orin_nano_benchmarks) folder should actually
contain. (Note the folder name says "nano" while the flight computer is an Orin **NX** —
see the naming note at the bottom.)

**Rule: no number in any document, presentation or report is allowed unless it came out of
a run recorded here.** Everything below is a measurement target, not a claim.

## Performance budget (targets to hit, not results)

| Stage | Target | Hard limit |
|-------|--------|------------|
| Camera capture | 30 FPS | — |
| Detector + pose + track + posture | <= 25 ms/frame | 33 ms (else we drop frames) |
| Posture classifier | <= 1 ms | — |
| VLM time-to-first-token | <= 1.5 s | 3 s |
| VLM full description (~60 tokens) | <= 5 s | 10 s |
| End-to-end: person enters frame -> victim report at GCS | <= 10 s | 20 s |
| Total Jetson board power | <= 20 W sustained | 25 W |
| Sustained SoC temperature | no thermal throttling over a 20 min run | — |

The power and thermal rows are as important as the latency rows. A pipeline that hits
30 FPS at MAXN and then throttles after eight minutes of flight has not passed.

## Experiment matrix

### E1 — Detector sweep
Vary: model (`yolo11n`, `yolo11s`, `yolo11m`; detect vs. pose) x precision
(FP32, FP16, INT8) x input size (640, 832, 960) x device (GPU, DLA) x power mode
(10 W, 15 W, 25 W, MAXN, with and without `jetson_clocks`).

Record: mean and **p95** latency, FPS, peak GPU/CPU memory, board power, SoC temperature,
mAP@0.5 and recall on our held-out aerial validation set.

p95 matters more than the mean — a pipeline that averages 25 ms but spikes to 60 ms drops
frames exactly when the scene is busiest.

### E2 — INT8 accuracy validation
The one experiment people skip. Compare FP16 vs INT8 mAP **broken down by posture and
altitude band**. If INT8 costs more than ~1-2 mAP, or if it disproportionately hurts
prone-person recall, it is not worth the speed. Calibrate on our own footage, not COCO.

### E3 — Altitude vs. recall curve
Recall vs. flight altitude (20/30/40/50/60 m), per posture, at fixed input size.

**Known optics as of 2026-09-16:** the SIYI A8 mini is **81° HFOV**, giving a focal length
of ~1124 px across a 1920 px frame. The geometric prediction is therefore:

| Altitude | Standing (1.7 m) | Prone from overhead (0.45 m) | Ground swath |
|---|---|---|---|
| 20 m | 96 px | 25 px | 34 m |
| 25 m | 76 px | 20 px | 43 m |
| 30 m | 64 px | 17 px | 51 m |
| 40 m | 48 px | 13 px | 68 m |
| 60 m | 32 px | 8 px | 103 m |

Against a practical detection floor of ~20 px, **a prone casualty falls below it at roughly
25 m**. If that holds in measurement it is the single most important operational number this
project produces — and it argues for flying lower than the coverage-optimal altitude, or for
tiled inference (E4). Confirm against the *streamed* resolution, which may be below 1920 px.

Deliverable: an **operational recommendation** — "search at <= X m for reliable detection
of prone casualties". This is one of the most useful outputs of the whole project and
costs only flight time.

### E4 — Tiled (SAHI-style) inference
Full-frame vs. 2x2 and 3x3 overlapping tiles. Measure the recall gain on small/prone
targets against the latency multiplier. Decide whether a slow "careful search" mode is
worth having.

### E5 — VLM sweep
Vary: model (Qwen2.5-VL-3B, VILA-1.5-3B, SmolVLM2, Moondream2) x quantisation
(INT4/AWQ, INT8, FP16) x serving stack (llama.cpp, NanoLLM, MLC) x crop resolution.

Record: time-to-first-token, tokens/s, total latency for a 60-token report, peak memory,
power, **JSON schema validity rate**, and quality scores from E6.

### E6 — VLM quality and hallucination
Held-out set of ~100 staged scenes with human-written reference descriptions.
Score each generation on:
- **Cue recall** — did it mention the injury indicator we deliberately planted?
- **Hallucination rate** — did it assert anything not present in the image? *This is the
  headline safety number.* Report it prominently, including in any demo.
- **Schema validity** — fraction of outputs that parse against our JSON schema.
- **Usefulness** — blind human rating, 1-5, by someone who did not write the prompt.

### E7 — Contention test
The experiment that decides the architecture. Run the detector and the VLM
**simultaneously**, as they will run in flight, and measure the detector's p95 latency
with the VLM idle vs. mid-inference. Repeat with the detector on GPU and on DLA.

If the detector degrades badly under VLM load, DLA offload (or a smaller VLM, or
time-slicing) stops being an optimisation and becomes a requirement.

### E8 — End-to-end on recorded flights
Replay rosbags from real flights with planted volunteers. Report:
- fraction of planted casualties that produced a victim report,
- geolocation error (median and p95, in metres),
- false victim reports per flight-hour,
- duplicate victims per flight (de-duplication quality),
- time from first appearance to report at the GCS.

## How to run it

- **Benchmark from rosbags, not from live flights.** Record once, replay many times.
  Every model change is then evaluated on identical input, which is the only way to
  compare fairly.
- Every run writes one JSON line to `results/` with: git commit, model file + hash,
  precision, input size, `nvpmodel` mode, `jetson_clocks` state, JetPack/TensorRT version,
  ambient temperature, bag name, and all measured values. Without the environment fields
  the numbers are unreproducible and therefore worthless.
- **Discard the first ~50 inferences** of every run (warm-up) and run for at least
  20 minutes for any thermal claim.
- Sample power with `tegrastats` (or `jtop`) throughout the run, not once at the end.
- Pin the analysis: a small script turns `results/*.jsonl` into the plots that go in the
  report, so no one is hand-copying numbers into slides.

## Suggested folder layout

```
jetson_orin_nano_benchmarks/     # see naming note below
  scripts/
    bench_detector.py            # E1, E2, E4
    bench_vlm.py                 # E5
    bench_contention.py          # E7
    replay_bag_e2e.py            # E8
    collect_env.sh               # JetPack/TRT versions, nvpmodel, clocks -> JSON
    plot_results.py              # results/*.jsonl -> figures/
  models/                        # git-ignored (weights, engines)
  videos/                        # git-ignored (bags, recorded footage)
  results/                       # committed - JSONL, small and diffable
  figures/                       # committed - generated plots
  README.md
```

Keep `results/` in git. It is small, it is the actual scientific output of the project,
and a diff showing an FPS regression after a code change is exactly the feedback we want.

## Naming note

The folder is called `jetson_orin_nano_benchmarks` but the flight computer is an Orin
**NX**. Since `General Tasks/` suggests we also have an Orin Nano, the cleanest fix is to
keep one benchmark tree and record the **board** as a field in every result row, so
NX and Nano numbers are directly comparable. Renaming the folder to
`jetson_benchmarks/` would make that clearer — worth doing before there is much in it.
