# Jetson Benchmarks

Measurement suite for the RAPTOR perception stack, run on the **flight computer
itself** — a Jetson Orin NX 16 GB (Seeed reComputer J401).

> **Naming:** the folder still says `orin_nano`, but every run records the board
> as a field (`board`) in its result row, which is the fix
> [06-benchmark-plan.md](../docs/06-benchmark-plan.md#naming-note) recommends so
> NX and Nano numbers stay directly comparable.

## The rule

> No number in any document, presentation or report is allowed unless it came out
> of a run recorded in `results/`.

Every row carries its full environment — L4T/JetPack version, CUDA, TensorRT,
torch, `nvpmodel` mode, `jetson_clocks` state, board, free memory, git commit —
because without those fields the numbers are unreproducible and therefore worthless.

## Layout

```
scripts/
  collect_env.py              environment capture, imported by every benchmark
  tegra_sampler.py            power/temperature sampling via tegrastats
  bench_detector.py           E1/E2/E4 — detector latency, power, memory, mAP
  bench_raw_forward.py        forward-pass only, framework overhead isolated
  bench_vlm.py                E5 — VLM TTFT, tokens/s, memory, schema validity
  prepare_visdrone_person.py  VisDrone -> single-class person dataset
  make_person_crops.py        person crops with 30% context, as the VLM receives them
  plot_results.py             results/*.jsonl -> figures/
  run_e1_sweep.sh             the E1 matrix in one invocation
  deploy_models.py            stage the selected models + provenance manifest
  generate_report.js          results/*.jsonl -> the Word selection report
  raptor_live_demo.py         live camera -> pose engine -> annotated window
  raptor-live-demo.sh         launcher (Jetson desktop)
  RAPTOR-Live-Demo.desktop    clickable icon, installed to ~/Desktop
  RAPTOR-Live-Demo.bat        clickable launcher for the Windows laptop
models/   git-ignored   weights and TensorRT engines
data/     git-ignored   datasets and crops
results/  committed     JSONL, one line per run — the scientific output
figures/  committed     generated plots
```

## Running

Everything runs inside the project venv, which must be created with
`--system-site-packages` (see [09](../docs/09-jetson-environment.md)):

```bash
source ~/raptor-venv/bin/activate

# environment sanity — cuda_available must be true
python3 scripts/collect_env.py

# one configuration
python3 scripts/bench_detector.py --model models/yolo11s.pt --imgsz 960 \
    --source data/visdrone-person/images/val --half --classes 0 \
    --accuracy --data data/visdrone-person/visdrone_person.yaml

# the whole E1 matrix
./scripts/run_e1_sweep.sh

# figures (matplotlib is broken on the board — see below; plot on a laptop)
python3 scripts/plot_results.py --results results/detector.jsonl --out figures

# stage the selected models and prove each one loads and runs
python3 scripts/deploy_models.py --root ~/raptor-deploy --models ~/raptor-models \
    --vlm ~/raptor-vlm --results ~/raptor-results --verify

# the Word report (needs node + the docx package, run off-board)
NODE_PATH=<where docx lives> node scripts/generate_report.js \
    --results results --figures figures --out ../RAPTOR-model-selection-report.docx
```

**TensorRT engines are not portable.** An `.engine` is tied to the TensorRT
version, the GPU architecture and often the exact board. Re-export after any
JetPack upgrade, and never copy an engine between machines — `deploy_models.py`
records the build environment in the manifest so a stale engine is detectable.

## Environment traps found the hard way

**0. The `--system-site-packages` / NumPy 2 clash — the pattern behind traps 1 and 3.**
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

## Datasets

RAPTOR has no flight footage yet, so accuracy is measured against **VisDrone-DET
val**, collapsed to a single `person` class (`pedestrian` + `people`):
548 images, 13,969 person boxes, ~25 people per image.

[05-custom-models-and-data.md](../docs/05-custom-models-and-data.md) lists VisDrone
as a relevant public aerial set, and [07](../docs/07-roadmap.md) sanctions public
data as an interim bridge. It is still a **proxy**: VisDrone is urban, shot over
roads and squares, with no casualties and no prone figures in wilderness. Every
accuracy number here must be labelled as proxy data and must never be presented as
RAPTOR's own performance.

## What is measured, and what is not

Measured: latency (mean/p50/p95/p99/max), FPS, peak GPU memory, board power and
temperature sampled throughout the run, person mAP@0.5, mAP@0.5:0.95, precision,
recall, and — for the VLM — time-to-first-token, tokens/s and JSON schema validity.

Not measured, and not inferrable from anything here:

- **Pose/keypoint accuracy** — VisDrone has no keypoint labels.
- **Posture classification accuracy** — the classifier does not exist yet, and its
  gravity-alignment step needs IMU attitude we can only get from our own rosbags.
- **E6 VLM cue-recall and hallucination rate** — needs the held-out set of ~100
  staged scenes with human-written references. Schema validity is measured;
  description *correctness* is not.
- **Altitude-vs-recall (E3)** — needs our own flights at known altitudes.
- **Thermal sustain** — runs here are minutes, not the 20 minutes any thermal
  claim requires.


## The live demo

Two ways to run the deployed tier 1+2 model on the live camera:

**On the Jetson** (full video window) — log in on the board's own monitor and
double-click **RAPTOR Live Demo** on the desktop. Shows boxes, 17 keypoints, a
posture label per person, and a HUD with FPS, grab/inference split, board power
and temperature.

**From the laptop** (text output) — double-click **RAPTOR Live Demo.bat** on the
Windows desktop. It checks the board is reachable and the camera present, then
streams detections, postures and timings. The video window is not forwarded; the
frames stay on the Jetson.

Measured on the bench camera: **~24 FPS end-to-end, 21.6 ms inference**.

Two honest limits on what the demo shows:

- **The posture label is not flight tier 2.** [02](../docs/02-detection-and-pose.md)
  specifies keypoints rotated into a *gravity-aligned* frame using IMU attitude
  from MAVROS. There is no IMU on the bench, so the demo uses image vertical -
  correct for a static camera, wrong the moment the aircraft banks. The screen
  says `(no IMU)` for exactly this reason.
- **An SSH session cannot open the window.** The console X server belongs to GDM
  until someone logs in, so a remote run falls back to headless output rather
  than crashing. That is expected, not a fault.
