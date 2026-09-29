# RAPTOR code

Everything that runs, grouped by what it is for. Every folder says **where it runs**,
because that is the first thing that trips people up: most of this code runs on the
Jetson, a little of it on the Windows laptop, and they reach each other only over one
Ethernet cable.

```
   Windows laptop                                    Jetson Orin NX 16 GB
   (Wi-Fi, internet)          Ethernet cable         (no Wi-Fi, no internet of its own)
  ┌───────────────────┐   100.100.100.2 ── .1    ┌──────────────────────────────┐
  │ src/tools/        │ ◄──── SSH / VNC / RDP ──►│ src/benchmarks/  src/demo/   │
  │ src/analysis/     │                          │ src/deploy/      src/setup/  │
  │ this git repo     │ ── sync_to_jetson.sh ──► │ ~/raptor/src  (a mirror)     │
  └───────────────────┘                          └──────────────────────────────┘
```

**The repository is the source of truth.** On the board, `~/raptor/src` is a copy of
this folder, refreshed by [`deploy/sync_to_jetson.sh`](deploy/sync_to_jetson.sh). Edit
here and sync — an edit made directly on the board is overwritten by the next sync.

Every script explains itself: run it with `--help`, or read the comment block at the
top of the file.

## I want to…

| Task | Do this |
|---|---|
| **See the model working on the live camera** | Double-click *RAPTOR Live Demo* on the Jetson desktop, or `RAPTOR-Live-Demo.bat` on the laptop — [demo/](demo/README.md) |
| **Connect to the board's screen** | VNC to `100.100.100.1:5900`, or RDP to `:3389` — [setup/](setup/README.md#remote-access) |
| **Give the board internet** (for `apt`, `pip`) | `tools/jetson_internet.sh` on the laptop, and leave it running — [tools/](tools/README.md) |
| **Put my code changes on the board** | `deploy/sync_to_jetson.sh` on the laptop |
| **Benchmark a model** | `benchmarks/bench_detector.py` on the board — [benchmarks/README](../benchmarks/README.md#reproducing-a-result) |
| **Rebuild the charts and Word report** | `analysis/plot_results.py`, then `analysis/generate_report.js`, on the laptop |
| **Set up a freshly flashed board** | Follow [setup/README.md](setup/README.md) top to bottom |

## Every file

### `common/` — shared helpers · *Jetson*
Imported by the benchmarks, the demo and the deployment tool; never run on their own
except as a sanity check.

| File | What it does |
|---|---|
| `collect_env.py` | Captures the environment a measurement ran in — JetPack, CUDA, TensorRT, torch, power mode, clocks, free memory, git commit — so every result row is reproducible. Run it alone to check that CUDA works: `python3 common/collect_env.py`. |
| `tegra_sampler.py` | Runs `tegrastats` in the background during a measurement and summarises board power and temperature. Sampling *throughout* matters: a pipeline that throttles after eight minutes has not passed. |
| `person_scoring.py` | Person mAP and recall for **any** detector, whatever its class list. Ultralytics' `val()` ignores `classes`, so models trained on VisDrone (pedestrian + people + eight vehicle classes) cannot be scored correctly by it. This keeps the person classes, merges them, and scores with Ultralytics' own matching; it agrees with `val()` within 0.5 points on COCO models. |
| `trt_yolo.py` | The lean TensorRT runner the deployed detector is served with: loads an Ultralytics-exported `.engine` directly, letterboxes exactly as Ultralytics does, merges the person classes and runs NMS on the GPU. Same detections, 5 ms less per frame than Ultralytics' pipeline. |

### `benchmarks/` — measurement · *Jetson*
Each run appends one JSON line to `benchmarks/results/`. Method and results:
[benchmarks/README.md](../benchmarks/README.md).

| File | What it measures |
|---|---|
| `bench_detector.py` | Detector latency (mean/p95/max), FPS, GPU memory, power, and optionally person mAP. Can export to TensorRT first (`--export engine --half`). `--imgsz 736,1280` builds a rectangular engine for 16:9 frames; `--classes 0 1 --single-cls` scores VisDrone-trained models through `person_scoring.py`. **Time on real frames** (`--source <image dir>`), never synthetic ones - see docs/10. |
| `bench_rtdetrv4.py` | The same measurement for RT-DETRv4, which Ultralytics cannot load: ONNX, then TensorRT FP16 via trtexec, timed on the same frames and scored with `person_scoring.py`. `--check-yolo` proves the scoring matches `val()`. |
| `bench_lean_yolo.py` | The same measurement for an Ultralytics engine served by the lean runner (`common/trt_yolo.py`) - the deployed path. Its accuracy matching the Ultralytics rows is the check that the runner is correct. |
| `bench_raw_forward.py` | The model's forward pass alone, without Ultralytics' wrapper — how the ~28 ms "framework overhead" floor in docs/10 was proved. |
| `bench_vlm.py` | A vision-language model on person crops: time to first token, tokens/s, memory, and whether its JSON matches the required schema. `--decoding greedy/model` and `--repetition-penalty` matter a lot: Qwen3 models loop under plain greedy decoding. `--model-kwargs` passes model-specific settings (e.g. MiniCPM's `downsample_mode`). |
| `bench_camera.py` | The capture path: negotiated format, achieved frame rate, and optionally the model on live frames. |
| `run_detector_sweep.sh` | The whole detector matrix (models × input sizes) in one go, ~20 minutes. |
| `prepare_visdrone_person.py` | Turns the VisDrone dataset into a single-class *person* set for accuracy tests. One-time. |
| `make_person_crops.py` | Cuts person crops with 30 % context, exactly as the VLM would receive them. One-time. |

### `analysis/` — charts and the report · *laptop*
Matplotlib is broken on the board (a NumPy 1/2 clash), so these run on the laptop.

| File | What it does |
|---|---|
| `plot_results.py` | Results → the four first-round figures in `benchmarks/figures/` and a CSV table (`--before 2026-09-28`). |
| `plot_reeval.py` | The 2026-09-28 re-evaluation figures (5-7): test-dev accuracy against real-frame latency, recall val vs test-dev, and the VLM comparison. |
| `score_vlm_generations.py` | Checks each VLM answer against what the crop really shows: invented injuries, 'lying' when nobody is, ethnicity, prompt numbers copied as if observed. Schema validity says a reply parses; this says whether it is true. |
| `generate_report.js` | Results + figures → `reports/RAPTOR-model-selection-report.docx`. Every number is read from the results, so the report cannot drift from the data. Needs `npm install` once. |
| `package.json` | Declares the one Node dependency (`docx`). |

### `demo/` — the live demo · *Jetson, plus one laptop launcher*
[demo/README.md](demo/README.md) covers what the screen shows and its limits.

| File | What it does |
|---|---|
| `raptor_live_demo.py` | Camera → aerial detector (lean TensorRT) on every frame → pose on crops every fifth frame → window with boxes, keypoints, a posture label and a performance HUD. `--mode pose-only` runs the pose model alone (for people close to a desk camera); `--source` plays aerial images or video. Falls back to text output when there is no display. |
| `launch_demo.sh` | Launcher: checks the venv, engine and camera, explains any problem, then starts the demo. |
| `RAPTOR-Live-Demo.desktop`, `RAPTOR-Live-Demo-Bench.desktop` | The clickable icons on the Jetson desktop: the aerial pipeline, and the pose-only bench demo. |
| `RAPTOR-Live-Demo.bat` | *Laptop.* Runs the demo on the board over SSH and shows its text output. |
| `catch_person.py` | Saves one annotated frame containing a detected person — works headless, over SSH. |

### `deploy/` — putting things on the board · *Jetson / laptop*

| File | Runs on | What it does |
|---|---|---|
| `deploy_models.py` | Jetson | Stages the chosen models under `~/raptor-deploy/`, checks each one loads and runs on the board (through the runtime it will be served by), and writes `MANIFEST.json` recording source, licence, checksum and what it measured. |
| `sync_to_jetson.sh` | laptop | Copies this `src/` folder to `~/raptor/src` on the board. |

### `setup/` — one-time provisioning · *Jetson*
Scripts that change the board's system configuration. Order and details:
[setup/README.md](setup/README.md).

| File | What it sets up |
|---|---|
| `setup_ros2.sh` | ROS 2 **Jazzy** (not Humble — the board runs Ubuntu 24.04). |
| `install_clock_keeper.sh` | Stops the board from booting into 1970 (it has no clock battery). |
| `set_headless_display.sh` | A 1024×768 console with no monitor attached, instead of 640×480. |
| `setup_vnc.sh` | VNC mirroring the console, on port 5900. |
| `setup_rdp.sh` | RDP (TLS-encrypted, its own session), on port 3389. |

### `system/` — configuration files, exactly as installed · *Jetson*
Not scripts: the files the setup scripts copy into the operating system, stored at the
same path they are installed to (`system/etc/…` → `/etc/…`). Keeping them here means a
reflashed board can be restored from git. [system/README.md](system/README.md) lists
each one.

### `tools/` — laptop helpers · *laptop*
[tools/README.md](tools/README.md).

| File | What it does |
|---|---|
| `jetson_internet.sh` | Gives the board internet through the laptop's Wi-Fi. Keep the window open. |
| `laptop_proxy.py` | The small proxy that `jetson_internet.sh` starts. |
| `check_vnc.py` | Logs in to the board's VNC the way a real client does, and reports the desktop size. |
| `check_rdp.py` | Confirms the board's RDP server is genuinely answering. |

## Conventions

- **Line endings.** Everything bound for the Jetson is LF, enforced by
  [`.gitattributes`](../.gitattributes). A script with Windows (CRLF) endings fails on
  the board with `$'\r': command not found`; `sync_to_jetson.sh` also normalises them.
- **Shared imports.** Scripts find `common/` relative to their own location, so they
  work wherever `src/` is copied, as long as the folder structure is kept.
- **Paths on the board.** Code: `~/raptor/src`. Python: `~/raptor-venv`. Large files,
  never in git: `~/raptor-models` (weights), `~/raptor-data` (datasets),
  `~/raptor-vlm` (VLMs), `~/raptor-deploy` (the deployed set), `~/raptor-results`
  (fresh results before they are copied into `benchmarks/results/`).
- **No secrets in git.** VNC and RDP passwords are set on the board by the setup
  scripts and exist only there.
