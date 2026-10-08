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
| **Check the demo survives hours of use, and people appearing suddenly** | `tests/soak_demo.py` on the board — [tests/](#tests--does-the-demo-survive--jetson) |
| **Find out why the demo stopped** | Read the newest log in `~/raptor-results/demo-logs/` on the board — every launch is logged since 2026-10-05 |
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
| `trt_yolo.py` | The lean TensorRT runner the deployed detector is served with: loads an Ultralytics-exported `.engine` directly, letterboxes exactly as Ultralytics does, merges the person classes and runs NMS on the GPU. Same detections, 5 ms less per frame than Ultralytics' pipeline. `gpu_preprocess=True` does the resize on the GPU instead; measured 2026-10-05 at only 1.07× faster on 1080p and it changes borderline detections, so it is off by default. |
| `trt_rtdetr.py` | The same call for the RT-DETRv4 engine (the Apache-2.0 alternative detector), so the demo can run either: `--detector ~/raptor-deploy/detector_alt/visdrone-rtdetrv4-s.engine`. The demo tells the two engine kinds apart by Ultralytics' metadata header. |
| `live_camera.py` | The USB camera on its own thread: always the newest frame, decoding off the inference loop, found by its USB path (not `/dev/video0`) and re-opened by itself if it drops off USB or its thread hits an error. `fourcc="auto"` picks uncompressed YUYV on a USB 3 camera and MJPG on USB 2, and the negotiated mode is reported. Added 2026-09-29; hardened 2026-10-05 for the Arducam B0498 (1080p60). |
| `person_tracker.py` | One steady box per person: removes nested and overlapping duplicates, tracks with Ultralytics' ByteTrack, confirms a person after 3 frames and holds them through short misses. The people count is the number of confirmed tracks. Needs `lap` in the venv. |
| `posture.py` | Coarse posture from COCO keypoints, decided by the legs (thigh angle, knee drop), with `upright, legs hidden` instead of a guess and a per-person vote over recent frames. Image vertical, not gravity - bench only until the IMU attitude is wired in. |
| `vlm_posture.py` | Asks the deployed VLM one word about one person's crop (standing / sitting / lying) on a background thread, ~0.4-0.7 s per answer, so the video never waits. |

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
| `bench_live_camera_modes.py` | Frames per second each camera mode really delivers through the demo's own capture thread (`common/live_camera.py`), and the CPU that costs. |
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
| `raptor_live_demo.py` | Camera → people → tracks → posture → window with boxes, ids, keypoints, posture, the VLM's answer and a performance HUD. Default **bench** mode: the pose model on the whole frame, for people in a room. `--mode aerial`: the flight pipeline (aerial detector on every frame, pose on crops). `--source` plays images or video; `--stats` prints a summary; `--frame-log` writes one line per frame for steadiness checks. A failure inside one frame is logged and the frame skipped; 30 in a row stop the demo with the reason. Falls back to text output when there is no display. |
| `launch_demo.sh` | Launcher: checks the venv, the engines, a USB camera and that no other copy is running, explains any problem, then starts the demo. Every run is logged to `~/raptor-results/demo-logs/` (newest 20 kept). |
| `RAPTOR-Live-Demo.desktop`, `RAPTOR-Live-Demo-Aerial.desktop` | The clickable icons on the Jetson desktop: the bench demo, and the aerial pipeline. |
| `RAPTOR-Live-Demo.bat` | *Laptop.* Runs the demo on the board over SSH and shows its text output. |
| `catch_person.py` | Saves one annotated frame containing a detected person — works headless, over SSH. |

### `deploy/` — putting things on the board · *Jetson / laptop*

| File | Runs on | What it does |
|---|---|---|
| `deploy_models.py` | Jetson | Stages the chosen models under `~/raptor-deploy/`, checks each one loads and runs on the board (through the runtime it will be served by), and writes `MANIFEST.json` recording source, licence, checksum and what it measured. |
| `sync_to_jetson.sh` | laptop | Copies this `src/` folder to `~/raptor/src` on the board. |

### `tests/` — does the demo survive? · *Jetson*
Added 2026-10-05, after reports that the demo "crashes if something shows up
suddenly". Every earlier test had used still images or a calm room. Results:
[docs/14](../docs/14-camera-demo-and-remote-access.md#2026-10-05-a-usb-3-camera-at-1080p60-and-the-crash-hunt).

| File | What it does |
|---|---|
| `soak_demo.py` | Runs the demo **as a separate process** for as long as you say, so a crash shows up as an exit and a traceback in the log rather than killing the test. Samples memory every 2 s, flags hangs, stops the demo with Ctrl-C at the end so shutdown is tested too. `--with-window` opens the real video window on the logged-in desktop. |
| `make_stress_videos.py` | Builds 1080p videos in which people appear **suddenly**: an empty scene cut to a crowd, frame-by-frame flicker, jump cuts, a brightness flash. From `vtest.avi` (OpenCV's pedestrian clip) and VisDrone images. |
| `fault_inject_demo.py` | The real demo with failures injected from outside - a fraction of frames, or of camera reads, raise. Proves the guards work instead of assuming it. |
| `memprofile_demo.py` | The real demo under `tracemalloc`: whether slow memory growth is Python objects (named by file and line) or native memory. |
| `analyse_frame_log.py` | Steadiness from a `--frame-log`: people-count changes, flicker (a count that jumps and comes straight back), and new track IDs, per 100 frames. |
| `check_trt_yolo_gpu.py` | Does GPU pre-processing change the detector's output, and how much faster is it? (Answer, 2026-10-05: yes slightly, and barely.) |
| `repro_crashes.py` | Drives two suspected crash paths with no camera or model - a VLM thread race and degenerate boxes. Neither reproduced; kept as a regression check. |

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
