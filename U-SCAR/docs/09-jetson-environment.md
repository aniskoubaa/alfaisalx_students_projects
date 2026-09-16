# 09 — Jetson Environment Setup

Practical notes for the Orin NX. Things that cost time the first time and should not cost
it twice.

## Python environment

**The project venv is `~/raptor-venv`.** Activate it before any Python work:

```bash
source ~/raptor-venv/bin/activate
```

It was created with:

```bash
python3 -m venv --system-site-packages ~/raptor-venv
```

### Why `--system-site-packages` is mandatory here

JetPack installs **CUDA-enabled PyTorch, TensorRT, cuDNN and OpenCV** into the *system*
site-packages. Those builds are NVIDIA's, compiled for this board — and they **cannot be
reinstalled from PyPI**, because the PyPI `torch` wheel for aarch64 is CPU-only.

A venv created without the flag is sealed off from all of that. Everything imports, nothing
errors, and the GPU is silently never used. The flag lets the venv see JetPack's packages
while still keeping our own installs isolated.

### The `externally-managed-environment` error

JetPack 6 is Ubuntu 22.04, which enforces **PEP 668**: `pip install` into the system Python
is blocked so pip cannot break apt-managed packages. The venv above is the fix.

**Do not use `--break-system-packages`.** It works, and it is how people corrupt a JetPack
install. Reflashing costs an afternoon.

## What does not survive a reboot

| Lost | Restore with |
|---|---|
| Venv activation | `source ~/raptor-venv/bin/activate` |
| `jetson_clocks` | `sudo jetson_clocks` — never persists, by design |
| Static IP for the camera | `sudo ip addr add 192.168.144.30/24 dev eth0`, or a netplan entry |

`nvpmodel -m 0` **does** persist — the power mode is saved across reboots.

Downloaded model weights (`.pt`, `.engine`) are ordinary files and persist. Nothing about
the model needs re-installing; only the shell environment needs re-entering.

Back-to-work sequence after a reboot:

```bash
source ~/raptor-venv/bin/activate
sudo ip addr add 192.168.144.30/24 dev eth0
sudo jetson_clocks                     # benchmarking runs only
```

To auto-activate the venv in every shell, append `source ~/raptor-venv/bin/activate` to
`~/.bashrc`.

**Autostart on boot** — launching perception automatically when the aircraft powers up — is
a `systemd` unit, and it belongs in Phase 5–6. When we get there the thing to autostart is
the ROS 2 launch file for the whole node graph, not YOLO on its own.

## Installing packages that depend on PyTorch

Ultralytics lists `torch` as a dependency, so pip may quietly replace the CUDA build with a
CPU wheel. **Check before and after, every time:**

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Expected: `True`. If installing something flipped it to `False`, pip swapped your torch —
reinstall NVIDIA's Jetson wheel before going further. A CPU-only torch will appear to work
and run the detector at a few frames per second.

## Verifying Ultralytics actually uses the GPU

After `pip install ultralytics`, run these in order. Do not skip step 1.

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
yolo checks                              # versions, CUDA status, selected device
```

`torch.cuda.is_available()` must print `True` and `yolo checks` must name the GPU, not
`cpu`. If either fails, stop and reinstall NVIDIA's Jetson PyTorch wheel — a CPU-only torch
runs the detector at a few frames per second while appearing to work correctly.

Then a real inference and a baseline measurement:

```bash
yolo predict model=yolo11n-pose.pt source='https://ultralytics.com/images/bus.jpg'
# output lands in runs/pose/predict/ — confirm boxes AND keypoints are drawn

sudo nvpmodel -m 0
sudo jetson_clocks
yolo benchmark model=yolo11n-pose.pt imgsz=640
```

Use the **pose** weights, not plain detect — tier 2 needs the keypoints
(see [02 — Detection & pose](./02-detection-and-pose.md)).

Record the benchmark result. It is the FP16 PyTorch baseline that every later optimisation
is measured against (experiment E1 in [06](./06-benchmark-plan.md)). Run `sudo tegrastats`
in a second terminal throughout — power and thermals matter as much as FPS.

Then export and compare:

```bash
yolo export model=yolo11n-pose.pt format=engine half=True
```

**Do not attempt INT8 yet.** It needs calibration images from our own aerial footage.
Calibrating on COCO and deploying on drone imagery silently loses accuracy.

### `yolo` is a command, not a service

Every `yolo` invocation is one-shot: it loads weights, runs, and exits. Nothing persists in
the background, and there is nothing to "start" after a reboot beyond activating the venv.
The startup cost is paid on every call.

This is why the production system is a **long-running ROS 2 node** that loads the model once
and then processes frames continuously, rather than repeated CLI calls. See
[04 — ROS 2 architecture](./04-ros2-architecture.md).

## Containers — the alternative worth considering

NVIDIA's [`jetson-containers`](https://github.com/dusty-nv/jetson-containers) (dusty-nv)
ships L4T images with CUDA-correct PyTorch, TensorRT and OpenCV already in place, which
removes this entire class of problem.

We will want it by Phase 4 for the VLM anyway (see
[03 — Scene understanding](./03-scene-understanding-vlm.md)), so adopting it early is
reasonable. The venv above is the lighter path for Phases 0–1.

## Useful commands on the Jetson

```bash
free -h                  # memory — confirms the 16 GB SKU
sudo tegrastats          # live CPU/GPU/EMC load, power, temperature
jtop                     # nicer: adds per-process GPU use, power mode, fan
sudo nvpmodel -q         # current power mode
sudo nvpmodel -m 0       # MAXN
sudo jetson_clocks       # pin clocks to maximum (benchmarking only)
```

Install `jtop` with `sudo pip3 install jetson-stats`, then reboot. It is the tool the
benchmark plan assumes for power and thermal sampling.

### Process inspection

```bash
ps aux --sort=-%mem | head -15   # biggest memory consumers
pgrep -a python                  # find our nodes by command line
sudo lsof -i :8554               # what is holding the RTSP port
sudo fuser -v /dev/video0        # what is holding a video device
```

The last two are the ones that save time when the camera stream will not open.

## Networking for the camera

```bash
sudo ip addr add 192.168.144.30/24 dev eth0
ping 192.168.144.25
```

`.30` is SIYI's own documented example for a host on this subnet. Avoid `.20`, which SIYI
reserves for its handheld ground station. Full harness detail in
[`uscar-wiring-map.html`](./uscar-wiring-map.html).

Note this `ip addr add` does not survive a reboot. Make it permanent with a netplan entry
once the bring-up is stable.
