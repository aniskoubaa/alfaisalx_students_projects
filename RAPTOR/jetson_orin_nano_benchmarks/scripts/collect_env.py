#!/usr/bin/env python3
"""Capture the exact environment a benchmark ran in.

06-benchmark-plan.md requires every result row to carry its environment, because
without it the numbers are unreproducible and therefore worthless. This module is
imported by the benchmark scripts and can also be run standalone:

    python3 collect_env.py            # pretty JSON to stdout
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command, returning stripped stdout or '' on any failure."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def board_info() -> dict:
    """Identify the Jetson module and L4T release."""
    rel = _read("/etc/nv_tegra_release")
    info: dict = {"l4t_release_raw": rel.splitlines()[0] if rel else ""}

    m = re.search(r"# R(\d+) \(release\), REVISION: ([\d.]+)", rel)
    if m:
        major, rev = m.group(1), m.group(2)
        info["l4t_version"] = f"{major}.{rev}"
        # L4T -> JetPack generation. R35=JP5, R36=JP6, R38/R39=JP7.
        info["jetpack_generation"] = {
            "35": "6" if False else "5",
            "36": "6",
            "38": "7",
            "39": "7",
        }.get(major, "unknown")

    # Seeed/NVIDIA images record the image name as a comment line.
    m = re.search(r"# Seeed Image Name (.+)", rel)
    if m:
        info["image_name"] = m.group(1).strip()

    model = _read("/proc/device-tree/model").replace("\x00", "")
    if model:
        info["device_tree_model"] = model

    info["hostname"] = platform.node()
    info["kernel"] = platform.release()
    info["arch"] = platform.machine()

    os_rel = _read("/etc/os-release")
    m = re.search(r'PRETTY_NAME="([^"]+)"', os_rel)
    if m:
        info["os"] = m.group(1)
    return info


def power_state() -> dict:
    """nvpmodel mode and whether jetson_clocks is pinning clocks."""
    state: dict = {}
    q = _run(["nvpmodel", "-q"]) or _run(["sudo", "-n", "nvpmodel", "-q"])
    if q:
        m = re.search(r"NV Power Mode:\s*(\S+)", q)
        if m:
            state["nvpmodel_name"] = m.group(1)
        nums = re.findall(r"^\s*(\d+)\s*$", q, re.MULTILINE)
        if nums:
            state["nvpmodel_mode"] = int(nums[-1])

    # jetson_clocks --show is verbose; the useful signal is whether the GPU min
    # and max frequencies have been pinned together.
    show = _run(["sudo", "-n", "jetson_clocks", "--show"], timeout=20)
    if show:
        m = re.search(r"GPU MinFreq=(\d+)\s+MaxFreq=(\d+)", show)
        if m:
            state["gpu_min_freq"] = int(m.group(1))
            state["gpu_max_freq"] = int(m.group(2))
            state["jetson_clocks_pinned"] = m.group(1) == m.group(2)
    return state


def python_stack() -> dict:
    """Versions of everything that can change a benchmark number."""
    stack: dict = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "in_venv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
    }

    def ver(mod: str, attr: str = "__version__") -> str | None:
        try:
            m = __import__(mod)
            return str(getattr(m, attr, "unknown"))
        except Exception:  # noqa: BLE001 - a missing package is data, not an error
            return None

    for name in ("torch", "torchvision", "ultralytics", "tensorrt", "cv2", "numpy", "onnx"):
        v = ver(name)
        if v is not None:
            stack[name] = v

    try:
        import torch

        stack["cuda_available"] = bool(torch.cuda.is_available())
        stack["torch_cuda_version"] = torch.version.cuda
        if torch.cuda.is_available():
            stack["gpu_name"] = torch.cuda.get_device_name(0)
            cap = torch.cuda.get_device_capability(0)
            stack["gpu_capability"] = f"{cap[0]}.{cap[1]}"
    except Exception as exc:  # noqa: BLE001
        stack["torch_error"] = str(exc)

    return stack


def resources() -> dict:
    """Memory and free disk — both bound what models we can even load."""
    res: dict = {}
    meminfo = _read("/proc/meminfo")
    m = re.search(r"MemTotal:\s+(\d+) kB", meminfo)
    if m:
        res["mem_total_gb"] = round(int(m.group(1)) / 1024 / 1024, 2)
    m = re.search(r"MemAvailable:\s+(\d+) kB", meminfo)
    if m:
        res["mem_available_gb"] = round(int(m.group(1)) / 1024 / 1024, 2)
    try:
        usage = shutil.disk_usage("/")
        res["disk_free_gb"] = round(usage.free / 1024**3, 2)
    except OSError:
        pass
    res["cpu_count"] = os.cpu_count()
    return res


def git_commit(repo_dir: str | None = None) -> str:
    """Commit the benchmark code was at, so a result can be traced to code."""
    cwd = repo_dir or os.path.dirname(os.path.abspath(__file__))
    return _run(["git", "-C", cwd, "rev-parse", "--short", "HEAD"]) or "unknown"


def collect(repo_dir: str | None = None) -> dict:
    return {
        "board": board_info(),
        "power": power_state(),
        "stack": python_stack(),
        "resources": resources(),
        "git_commit": git_commit(repo_dir),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, sort_keys=True))
