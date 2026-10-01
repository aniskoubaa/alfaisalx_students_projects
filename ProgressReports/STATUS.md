# RAPTOR — Current Status

**Last updated: 2026-09-29** (new models deployed; live demo fixed the same afternoon)
Living document. Update it at the end of every session, before closing the laptop.
Progress reports, one per day, each covering only that day's progress:
[2026-09-29](./RAPTOR_Work_Report_2026-09-29.docx) (deployment, dashboard, faster models, live-demo fix),
[2026-09-28](./RAPTOR_Work_Report_2026-09-28.docx) (the work of 17–28 September, including the model re-evaluation),
[2026-09-20 harness revision](./2026-09-20-raptor-harness-revision.md),
[2026-09-16](./RAPTOR_Work_Report_2026-09-16.docx) (design report and daily report, combined).
The separate same-day originals these replaced are kept in `AlfaisalX/ProgressReports-superseded/`, outside the repository.

---

## Where we are

**Phase 0 done on the compute side; Phase 1 not started.** The flight computer is
provisioned, benchmarked, remotely reachable and running a live camera demo. On
2026-09-28 both model choices were re-evaluated against newer candidates and
**replaced on measured grounds**; on 2026-09-29 the new models were **deployed** and
the live demo switched to them; the demo's problems were fixed that afternoon. A tracker and a rule-based
posture check now exist as bench tools (`src/common/`), but no ROS 2 nodes, trigger or victim report. The flight camera has still never been powered.

---

## Current choices

| Tier | Choice | Measured (Orin NX, 25 W) | Where |
|---|---|---|---|
| 1 — detect | **YOLO26s trained on VisDrone**, 736×1280 TensorRT FP16 engine, served by the lean runner (`src/common/trt_yolo.py`) | 42.5 % of people found on held-out aerial test-dev (previous choice: 20.0 %); a tie with RT-DETRv4-S, at a third less GPU compute (11.5 ms). 26.1 ms p95 end to end (31.0 through Ultralytics). AGPL; weights non-commercial (VisDrone). | [docs/10](../RAPTOR/docs/10-detector-benchmark-results.md) |
| 1 — Apache alternative | RT-DETRv4-S trained on VisDrone, 960 px | 42.8 %, 17.1 ms GPU compute, 24.3 ms end to end in a lean runtime. Apache-2.0. | docs/10 |
| 2 — pose | **YOLO26s-pose on crops of each track**, below frame rate | 22.7 ms p95 (yolo11s-pose: 26.5) | [docs/02](../RAPTOR/docs/02-detection-and-pose.md) |
| 3 — describe | **Qwen3-VL-2B-Instruct**, greedy + repetition penalty 1.05 | 100 % valid JSON, 0 injuries invented on 16 uninjured people, first token 0.21 s, 4.1 GB. Full reply ~12 s (target 5 s). | [docs/12](../RAPTOR/docs/12-vlm-benchmark-results.md) |
| Demo (bench) | **YOLO26s-pose 384×640 + ByteTrack + leg-based posture + Qwen3-VL-2B one-word posture check** | 30 FPS at 1080p, 60 at 720p; pose 9.7 ms per frame; VLM 0.4–0.7 s per person, in the background | [docs/14](../RAPTOR/docs/14-camera-demo-and-remote-access.md) |
| Deployed | All six: detector, detector_alt (RT-DETRv4-S), pose, pose_bench (the same pose model as a 384×640 engine, for the demo), vlm, vlm_fallback (Qwen3.5-2B) — verified on the board 2026-09-29. The 2026-09-20 set is kept at `~/raptor-deploy.2026-09-20`. | see `benchmarks/results/deploy_manifest.json` | `~/raptor-deploy` |

---

## Done

- [x] Full design documented — `RAPTOR/docs/01`–`14`, plus the HTML wiring map, build view and explainer
- [x] Jetson identified: **Orin NX 16 GB** on a **Seeed reComputer J401**, JetPack 7.2 / Ubuntu 24.04
- [x] Environment working: `~/raptor-venv`, CUDA torch 2.14, TensorRT 10.16, ultralytics 8.4, transformers 5.17
- [x] **ROS 2 Jazzy** installed and verified (Humble has no Ubuntu 24.04 binaries)
- [x] Clock fixed — the board no longer boots into 1970, including on a cold start
- [x] Internet for the board through the laptop (`src/tools/jetson_internet.sh`)
- [x] Remote access: SSH (key), VNC :5900 (console, 1024×768), RDP :3389 (own session)
- [x] Detector benchmark, round 1 (COCO models, 18 configurations) and round 2 (aerial-trained, 9 configurations, held-out test-dev)
- [x] VLM benchmark, round 1 (2 models) and round 2 (7 models, 16 configurations, truthfulness check)
- [x] First-round models deployed with a provenance manifest; live camera demo with a desktop icon
- [x] Repository reorganised (`docs/ src/ benchmarks/ reports/ assets/`), every file named for what it is
- [x] Model-selection Word report rebuilt: Part A re-evaluation, Part B original — `RAPTOR/reports/`
- [x] **Live demo fixed** (2026-09-29 afternoon): it had counted one person as several, flickered, called a seated person "standing", run at ~17 FPS and "crashed" (the webcam dropped off USB). Now 30 FPS (60 at 720p), steady counts, posture from the legs, a VLM posture check, automatic camera reconnect — see docs/14 and `benchmarks/results/live_demo_fix_2026-09-29.json`

## Next

- [x] **Deployed the new models** (2026-09-29): lean TensorRT runner for the detector, verified manifest, live demo switched to the two-stage pipeline, plus a *bench* icon (pose-only) for people close to the webcam
- [ ] Move the detector's resize onto the GPU (`trt_yolo.py`) and re-measure — most of the 26.1 ms is CPU pre-processing
- [ ] Serve Qwen3-VL-2B through llama.cpp at 4 bits with a JSON grammar; re-measure speed and truthfulness
- [ ] Change the VLM prompt so it stops asserting the posture; drop its confidence field
- [ ] Evaluate on aerial images of **people lying down** (Okutama-Action, NOMAD, SARD, HERIDAL)
- [ ] Run detector + VLM together (E7) — never done
- [ ] Then the **operator dashboard**: event logger on the Jetson → server → feed, event page, health
- [ ] Serve the VLM through **TensorRT Edge-LLM** (INT4, supports Orin NX on JetPack 7.2; NVIDIA lists Qwen3-VL-2B at 58 tok/s) and re-test Qwen3.5-2B (higher counting score) — the full description should drop from ~12 s to a few seconds
- [ ] Aerial posture: fine-tune the aerial detector with posture classes (upright / sitting / lying) on SARD, C2A and Okutama-Action — keypoints are unreliable at altitude
- [ ] Replace the posture rule with a small classifier trained on keypoints with random leg drop-out, if the rule's `legs hidden` cases prove common
- [ ] Commit the afternoon's work — the 10:58 commit holds the morning's; the live-demo fix and the report merge are uncommitted

## Blocked — needs hardware

- [ ] **Camera has never been powered.** Test HDMI + Ethernet video at the same time first (cheap, decides the whole harness)
- [ ] Capture card and VTX not acquired (VTX is optional — buy last)
- [ ] **The Jetson has nowhere to mount** on the X500 V2 top deck — second deck or under-tray plate
- [ ] MAVROS link to the Pixhawk 6C; first rosbag (the Phase 0 finish line)

---

## Architecture (as of 2026-09-20)

```
A8 mini control port --> Pixhawk 6C                     [gimbal pointing]
A8 mini micro-HDMI   --> USB capture card --> Jetson    [perception video, /dev/video0]
A8 mini Ethernet     --> VTX --> operator               [optional downlink]
Pixhawk 6C TELEM1    --> Jetson                         [MAVLink / MAVROS]
```

The Pixhawk owns the gimbal, so the Jetson can only aim the camera by sending a
MAVLink gimbal command — a **write**, which the design currently forbids. Decide
before the gimbal node is written: allow gimbal-only writes, or keep pointing manual.

---

## Environment notes that bite

- **Do not `pip install "numpy<2"`.** The installed CUDA torch is built for NumPy 2; the old advice here would now break it.
- The PyTorch wheel has no sm_87 kernels (runs by JIT) — every PyTorch number is a floor. NVIDIA's Jetson build is the top environment fix.
- Plots cannot be drawn on the board (JetPack matplotlib is NumPy-1); they are drawn on the laptop.
- Ultralytics `val()` ignores `classes` — score aerial models with `src/common/person_scoring.py`.
- Time benchmarks on **real frames**, never synthetic ones.
- Qwen3 VLMs need a repetition penalty under greedy decoding, or they loop.
- Board internet exists only while `jetson_internet.sh` runs on the laptop; while `/etc/apt/apt.conf.d/99proxy` exists, apt needs it.
- Don't `ping` 100.100.100.1 to check the board (carrier-grade NAT range) — use SSH.
- The webcam can drop off USB and come back as `/dev/video1`; plug it into the board directly. The demo finds it by USB path either way.
- ByteTrack needs `lap` in the venv. The board has no internet of its own, so the aarch64 wheel was downloaded on the laptop and copied over (`pip install --no-index`).
- The laptop's USB hub has **one** Ethernet adapter; it cannot bridge the Jetson to the router. A small network switch would.

---

## Hardware

| Component | Spec | Status |
|---|---|---|
| Companion computer | Jetson Orin NX 16 GB, Seeed reComputer J401 | Working, provisioned |
| Flight controller | Pixhawk 6C | In hand, not linked to the Jetson |
| Camera | SIYI A8 mini 4K | Mounted under the nose, **never powered** |
| Camera video (onboard) | micro-HDMI to USB capture card | **Card not acquired** |
| Camera video (downlink) | Ethernet to VTX | Optional, not acquired |
| Airframe | Holybro X500 V2, 10" props | Built; no room for the Jetson on the top deck |
| Test camera | Logitech C922 webcam, USB 2.0 (1080p30 / 720p60 MJPEG) | Used for the live demo; dropped off USB once through the hub (2026-09-29) |

---

## Open questions

| # | Question | Blocks |
|---|---|---|
| 1 | Can HDMI and Ethernet video run at the same time? | The split-video harness |
| 2 | ArduPilot or PX4 on the Pixhawk 6C? | Gimbal control parameters |
| 3 | What does the capture card negotiate? | Detector input sizing |
| 4 | May the Jetson write gimbal commands? | The gimbal node |
| 5 | Where does the Jetson mount? | Buck position, HDMI run, centre of gravity |
| 6 | Is the lean detector runner fast enough? It still resizes on the CPU: 26.1 ms end to end against 11.5 ms of GPU compute | Headroom for tier 2 and the VLM on the same frames |
| 7 | Give the Jetson its own internet (network switch + DHCP fallback profile)? | Faster installs; retires the laptop proxy |
| 8 | 25 W or 40 W in flight? | Endurance vs speed |

Answered since the last update: the carrier board (J401); Qwen3 vs Qwen2.5 (Qwen3-VL-2B wins); the benchmarks folder rename (done). AGPL is still open, but no longer blocking: RT-DETRv4-S is a measured Apache-2.0 alternative within a point of the chosen detector.

---

## Standing caveat

Every figure above came from a run recorded in `RAPTOR/benchmarks/results`. Accuracy is on
**VisDrone**, a public urban aerial dataset with no casualties and nobody lying down, used as a
proxy until RAPTOR has its own footage. The new detectors were trained on it, so their numbers
are a ceiling for this data, not a prediction for a real search.
