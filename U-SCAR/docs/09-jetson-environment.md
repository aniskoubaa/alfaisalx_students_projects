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

## Installing packages that depend on PyTorch

Ultralytics lists `torch` as a dependency, so pip may quietly replace the CUDA build with a
CPU wheel. **Check before and after, every time:**

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Expected: `True`. If installing something flipped it to `False`, pip swapped your torch —
reinstall NVIDIA's Jetson wheel before going further. A CPU-only torch will appear to work
and run the detector at a few frames per second.

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
