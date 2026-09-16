# U-SCAR — Current Status

**Last updated: 2026-09-16**
Living document. Update it at the end of every session, before closing the laptop.
For the full design argument see the
[2026-09-16 progress report](./2026-09-16-uscar-jetson-perception-design.md).

---

## Where we are

**Phase 0 — Foundations.** Design is complete and documented. Environment bring-up on the
Jetson has started. No pipeline code written yet, and the camera has never been powered.

---

## Done

- [x] Full design documented — `U-SCAR/docs/01`–`09`, plus two interactive HTML explainers
- [x] Hardware identified and specified (see table below)
- [x] A8 mini User Manual v1.10 read; voltages, RTSP paths and optics verified against it
- [x] Jetson confirmed as the **16 GB** SKU, which settles the VLM choice
- [x] Python venv created: `~/raptor-venv`, with `--system-site-packages`
- [x] `externally-managed-environment` (PEP 668) resolved
- [x] Everything pushed to `main` on GitHub

## In progress — blocked

- [ ] **`pip install ultralytics` fails: numpy and scipy not installed.** See "Current blocker" below.
- [ ] **Camera has never been powered.** Waiting on a 12 V bench supply. Nothing about the
      camera has been tested — no ping, no stream, no decode.

## Not started

- [ ] Flash / verify JetPack 6.x; record CUDA, TensorRT, cuDNN versions
- [ ] Install ROS 2 Humble
- [ ] Camera node publishing `/uscar/image_raw`
- [ ] MAVROS link to the Pixhawk 6C
- [ ] First rosbag recorded and replayed — **this is the Phase 0 finish line**

---

## Current blocker

`pip install ultralytics` reported **numpy and scipy not installed**.

Diagnose first — the venv may be sealed off from JetPack's packages:

```bash
grep system-site ~/raptor-venv/pyvenv.cfg      # must read: include-system-site-packages = true
```

If it reads `false`, recreate the venv with `--system-site-packages`. That flag is what lets
it see JetPack's CUDA PyTorch, TensorRT and OpenCV, none of which can be reinstalled from
PyPI on aarch64.

Then:

```bash
source ~/raptor-venv/bin/activate
pip install "numpy<2" scipy
python -c "import torch, numpy; print(torch.__version__, numpy.__version__, torch.cuda.is_available())"
```

**Pin numpy below 2.0.** NVIDIA's Jetson PyTorch wheels are built against numpy 1.x, and
numpy 2.0 changed the C ABI — installing numpy 2 is a common way to silently break CUDA
torch on this board. Relax the pin only after confirming the installed torch supports it.

`torch.cuda.is_available()` must print `True`. If it does not, stop and fix that before
anything else; a CPU-only torch runs the detector at a few frames per second while appearing
to work.

---

## Next command to run

```bash
source ~/raptor-venv/bin/activate
grep system-site ~/raptor-venv/pyvenv.cfg
pip install "numpy<2" scipy
python -c "import torch, numpy; print(torch.__version__, numpy.__version__, torch.cuda.is_available())"
yolo checks
```

After that succeeds, the first real measurement:

```bash
sudo nvpmodel -m 0 && sudo jetson_clocks
yolo benchmark model=yolo11n-pose.pt imgsz=640      # run tegrastats in a second terminal
```

That is the FP16 PyTorch baseline for experiment E1. **It has not been measured yet.**

---

## Hardware

| Component | Spec | Status |
|---|---|---|
| Companion computer | Jetson Orin NX **16 GB** | In hand, booting |
| Flight controller | Pixhawk 6C | In hand, not yet linked to the Jetson |
| Camera | SIYI A8 mini 4K, 81° H FOV | In hand, **never powered** |
| Camera video | `rtsp://192.168.144.25:8554/video1` | Untested |
| Camera power | 11–25.2 V (3S–6S), 5 W avg / 12 W peak | **Blocked — no supply yet** |
| Jetson network | `192.168.144.30/24` on `eth0` | Not configured |

Full harness: [`U-SCAR/docs/uscar-wiring-map.html`](../U-SCAR/docs/uscar-wiring-map.html)

---

## Open questions

| # | Question | Blocks |
|---|---|---|
| 1 | Which **carrier board** is the Orin NX on? | Regulator voltage — 5 V, 12 V or 19 V |
| 2 | **ArduPilot or PX4** on the Pixhawk 6C? | Optional gimbal UART parameters |
| 3 | Actual **streamed** resolution and frame rate over RTSP | Altitude table; detector input sizing |
| 4 | H.264 or H.265 on the stream? | GStreamer pipeline elements |
| 5 | Is **AGPL-3.0** (Ultralytics) acceptable for this project? | Whether we build on YOLO11 at all |
| 6 | Rename `jetson_orin_nano_benchmarks/`? | Flight computer is an NX |
| 7 | What does "raptor" refer to (venv name)? | Nothing — just naming consistency |

---

## Things that can proceed without the camera

Worth doing while waiting on the power supply:

1. Fix the numpy/scipy blocker and get `yolo checks` passing.
2. Measure the FP16 baseline.
3. Install ROS 2 Humble; verify `talker`/`listener`.
4. Wire the Pixhawk 6C TELEM1 to the Jetson and bring up MAVROS.
5. **Start data-collection planning** — the consent form, flight plan and labelling workflow
   are the long pole for Phases 3–5 and take longer than the code.

---

## Standing caveat

**Every performance figure in these documents is a target, not a measurement.** Nothing has
been benchmarked yet. The altitude table — prone casualties falling below the detection floor
at ~25 m — is geometry, not data, and experiment E3 exists to confirm or refute it. No figure
from these docs belongs in a report or presentation as a finding until it comes out of a
recorded run.
