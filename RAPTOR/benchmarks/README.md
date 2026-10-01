# Benchmarks — results and method

Measurements of the RAPTOR perception stack, taken on the **flight computer
itself**: a Jetson Orin NX 16 GB (Seeed reComputer J401), JetPack 7.2, at 25 W.

This folder holds the **data**. The code that produced it is in
[`src/benchmarks/`](../src/benchmarks) (runs on the Jetson) and
[`src/analysis/`](../src/analysis) (runs on the laptop) — see the
[code map](../src/README.md). What the numbers *mean* is written up in
[docs 10](../docs/10-detector-benchmark-results.md),
[12](../docs/12-vlm-benchmark-results.md) and
[14](../docs/14-camera-demo-and-remote-access.md).

## The rule

> No number in any document, presentation or report is allowed unless it came out
> of a run recorded in `results/`.

Every row carries its full environment — L4T/JetPack version, CUDA, TensorRT,
torch, `nvpmodel` mode, `jetson_clocks` state, board, free memory, git commit —
because without those fields the numbers are unreproducible and therefore worthless.
([06 — Benchmark plan](../docs/06-benchmark-plan.md) sets this rule.)

## What is here

| File | Experiment | Produced by |
|---|---|---|
| `results/detector.jsonl` | E1/E2/E4 — detector latency, FPS, power, memory, person mAP (val and, from 2026-09-28, test-dev) | `src/benchmarks/bench_detector.py`, `run_detector_sweep.sh`, `bench_rtdetrv4.py` |
| `results/raw_forward.jsonl` | E1 — forward pass only, framework overhead isolated | `src/benchmarks/bench_raw_forward.py` |
| `results/vlm.jsonl` | E5 — VLM time-to-first-token, tokens/s, memory, schema validity | `src/benchmarks/bench_vlm.py` |
| `results/vlm_outputs_*.json` | E5 — the VLMs' raw answers, one file per run (`generations_file` in each `vlm.jsonl` row names it) | `src/benchmarks/bench_vlm.py --save-generations` |
| `results/vlm_content_scores.csv` | whether those answers are **true**: invented injuries, false 'lying', ethnicity, copied prompt numbers | `src/analysis/score_vlm_generations.py` |
| `results/camera.jsonl` | E3b — capture path, and the model on live frames | `src/benchmarks/bench_camera.py` |
| `results/deploy_manifest.json` | what is deployed on the board now (2026-09-29), with provenance; `deploy_manifest_2026-09-20.json` is the first set | `src/deploy/deploy_models.py` |
| `results/live_demo_fix_2026-09-29.json` | the live demo's problems measured before the fix (counts per frame, posture labels, decode and inference times, camera settings) and the demo after it (FPS, count stability, VLM answers) | `src/demo/raptor_live_demo.py --stats`; diagnostic runs on the bench camera |
| `results/gpu_compute.jsonl` | GPU compute alone per engine (`trtexec`), to compare networks across harnesses | `trtexec`; `bench_rtdetrv4.py` |
| `figures/fig1–fig4*.png`, `results_table.csv` | first round (2026-09-20) charts | `src/analysis/plot_results.py --before 2026-09-28` |
| `figures/fig5–fig7*.png`, `reeval_detectors.csv` | second round (2026-09-28): test-dev accuracy vs real-frame latency, recall val vs test-dev, the VLM comparison | `src/analysis/plot_reeval.py` |
| `figures/live_person_detection.jpg` | first live detection through the first deployed engine (2026-09-20) | `src/demo/catch_person.py` |
| `figures/live_two_stage_demo.jpg` | the deployed two-stage pipeline on a VisDrone frame (2026-09-29) | `src/demo/raptor_live_demo.py --source` |

The Word report is built from these files by `src/analysis/generate_report.js`
and lives in [`reports/`](../reports).

**Two row flags added on 2026-09-28.** `accuracy_invalid` holds the accuracy of
three rows scored before the `person_scoring` fix (trap 4 below) - kept, never
plotted. `precision_label_corrected` marks engine re-runs that were labelled fp32
only because `--half` was not passed; the engines are FP16.

**One caveat on timestamps:** rows recorded before 2026-09-20 carry a **1970**
timestamp. The board had no working clock then; it has since been fixed
([docs/11 — The clock](../docs/11-jetson-platform-setup.md#the-clock)). The order of
rows within each file is still the order the runs happened.

## Reproducing a result

On the Jetson, in the project venv (see [09](../docs/09-jetson-environment.md)):

```bash
source ~/raptor-venv/bin/activate
cd ~/raptor/src                       # the repo's src/, copied by src/deploy/sync_to_jetson.sh

python3 common/collect_env.py         # sanity: cuda_available must be true

# one configuration
python3 benchmarks/bench_detector.py --model ~/raptor-models/yolo11s.pt --imgsz 960 \
    --source ~/raptor-data/visdrone-person/images/val --half --classes 0 \
    --accuracy --data ~/raptor-data/visdrone-person/visdrone_person.yaml

./benchmarks/run_detector_sweep.sh          # the whole E1 matrix (~20 minutes)

# a VisDrone-trained model: both person classes, scored by person_scoring.py
python3 benchmarks/bench_detector.py --model ~/raptor-models/aerial/visdrone-yolo26s-960.pt     --imgsz 960 --export engine --half --classes 0 1 --single-cls     --source ~/raptor-data/visdrone-person/images/val --frames 200     --accuracy --data ~/raptor-data/visdrone-person-testdev/visdrone_person.yaml

# RT-DETRv4 (Ultralytics cannot load it)
python3 benchmarks/bench_rtdetrv4.py --repo ~/raptor-ext/RT-DETRv4     --config ~/raptor-models/aerial/visdrone-rtdetrv4-s/config.yaml     --weights ~/raptor-models/aerial/visdrone-rtdetrv4-s/model.pth --classes 0 1     --source ~/raptor-data/visdrone-person/images/val --frames 200     --data ~/raptor-data/visdrone-person/visdrone_person.yaml

# a VLM - Qwen3 models need the repetition penalty, see docs/12
python3 benchmarks/bench_vlm.py --model ~/raptor-vlm/Qwen3-VL-2B-Instruct     --crops ~/raptor-data/person-crops --limit 16 --decoding greedy --repetition-penalty 1.05     --save-generations ~/raptor-results/vlm_outputs_qwen3vl2b_greedyrep.json
```

**Always time on real frames** (`--source <image dir>`). Synthetic frames skip the
resize and the post-processing of real detections: a square 1280 engine measured
28 ms on noise and 39 ms on real frames.

Then copy the JSONL back into `benchmarks/results/` and, on the laptop:

```bash
python src/analysis/plot_results.py --results benchmarks/results/detector.jsonl --out benchmarks/figures --before 2026-09-28
python src/analysis/score_vlm_generations.py --csv benchmarks/results/vlm_content_scores.csv benchmarks/results/vlm_outputs_*.json
python src/analysis/plot_reeval.py
cd src/analysis && npm install && node generate_report.js
```

**Hold the power mode fixed** when comparing models — everything above was
measured at 25 W (`nvpmodel` mode 3). The board also offers 10 W, 15 W, 40 W and
MAXN_SUPER; a sweep across them is still to do.

**TensorRT engines are not portable.** An `.engine` is tied to the TensorRT
version, the GPU architecture and often the exact board. Re-export after any
JetPack upgrade, and never copy an engine between machines.

## Environment traps found the hard way

**0. The `--system-site-packages` / NumPy 2 clash — the pattern behind traps 1 and 2.**
The venv needs `--system-site-packages` to see JetPack's CUDA stack, but that also
exposes every apt-installed Python package. Those were built against **NumPy 1.x**,
while the venv carries **NumPy 2.5.3**. Any apt package that touches the NumPy C API
or removed aliases breaks on import. Two have bitten so far; assume there are more.
The fix is always the same: `pip install` a NumPy-2-era build **into the venv**, so
it shadows the system copy. Never `--break-system-packages` the system one.

**1. `val()` dies with `numpy.core.multiarray failed to import`.**
Ultralytics' `check_det_dataset()` calls `check_font()`, which imports matplotlib —
JetPack's NumPy-1 build. `bench_detector.py` stubs `check_font` rather than
disturbing the board's packages. The same clash means **plots must be generated
off-board**.

**2. `transformers` dies with `cannot import name 'Inf' from 'numpy'`.**
`transformers` imports scipy for its detection-loss utilities, and the system scipy
(1.11.4) uses `numpy.Inf`, which NumPy 2 removed in favour of `numpy.inf`. Fixed by
installing scipy 1.18+ into the venv.

**3. The installed PyTorch has no kernels for this GPU.**
`torch 2.14.0+cu130` is the generic PyPI aarch64 wheel, built for compute
capabilities 8.0/9.0/10.0/11.0/12.0. Orin is **8.7**, so torch prints
`No published PyTorch CUDA builds for release 2.14.0+cu130 support this GPU`.
It still runs — CUDA falls back to JIT-compiling PTX for sm_87 — and results are
valid, but they are **not** what NVIDIA's sm_87-tuned Jetson build would give.
Every number produced on this stack should be read as a *floor*. Replacing this
wheel with NVIDIA's Jetson build is the single highest-value environment fix
outstanding.

**4. Ultralytics `val()` ignores `classes`.**
Harmless for COCO models against our one-class set: only class 0 is ever scored.
Wrong for models trained on VisDrone, which split people into two classes beside
eight vehicle classes. `single_cls=True` then scores every car as a person; we saw
precision 0.25 instead of 0.73. `src/common/person_scoring.py` does it properly and
matches `val()` within 0.5 points where `val()` is right.

**5. Synthetic frames under-time real work by a third.** See *Always time on real
frames* above.

## Datasets

RAPTOR has no flight footage yet, so accuracy is measured against **VisDrone-DET
val**, collapsed to a single `person` class (`pedestrian` + `people`):
548 images, 13,969 person boxes, ~25 people per image. Built with
`src/benchmarks/prepare_visdrone_person.py`.

Since 2026-09-28 accuracy is also measured on **VisDrone-DET test-dev**, built the
same way: 1,610 images, 27,382 person boxes, 343 images with nobody in them. The
VisDrone-trained checkpoints were selected on val by their authors, so for them
**test-dev is the only held-out number**, and it is the one decisions are made on.

For the VLMs, `~/raptor-data/person-crops` holds **16 person crops** cut from
VisDrone val with 30 % context (`make_person_crops.py`). Their ground truth was
set by eye on 2026-09-28: 13 people standing or walking, 3 sitting, **nobody lying
and nobody visibly injured**. It is in `score_vlm_generations.py`.

[05](../docs/05-custom-models-and-data.md) lists VisDrone as a relevant public aerial
set, and [07](../docs/07-roadmap.md) sanctions public data as an interim bridge. It
is still a **proxy**: VisDrone is urban, shot over roads and squares, with no
casualties and no prone figures in wilderness. Every accuracy number here must be
labelled as proxy data and never presented as RAPTOR's own performance.

## What is measured, and what is not

Measured: latency (mean/p50/p95/p99/max), FPS, peak GPU memory, board power and
temperature sampled throughout the run, person mAP@0.5, mAP@0.5:0.95, precision,
recall, and — for the VLM — time-to-first-token, tokens/s and JSON schema validity.

Not measured, and not inferrable from anything here:

- **Pose/keypoint accuracy** — VisDrone has no keypoint labels.
- **Posture classification accuracy** — the classifier does not exist yet, and its
  gravity-alignment step needs IMU attitude we can only get from our own rosbags.
- **E6 VLM cue-recall and hallucination rate** — needs the held-out set of ~100
  staged scenes with human-written references. What *is* measured since
  2026-09-28 is a floor check: on 16 crops of uninjured, upright people, does a
  model **invent** an injury or a lying posture? That catches the dangerous
  failure. It says nothing about whether a model notices a real injury, because
  there are none in the set.
- **Altitude-vs-recall (E3)** — needs our own flights at known altitudes.
- **E7 contention** — detector and VLM have never yet run at the same time.
- **Thermal sustain** — runs here are minutes, not the 20 minutes any thermal
  claim requires.
