#!/usr/bin/env python3
"""Which camera modes does the demo's own capture path sustain?

`v4l2-ctl --stream-mmap` measures the driver alone. The demo reads through
src/common/live_camera.py (OpenCV, with a YUYV->BGR conversion per frame on the
camera thread), so this measures THAT: frames delivered per second to the caller,
and how much of one CPU core the camera thread burns to deliver them.

Written for the Arducam B0498 (USB 3, YUYV only - it has no MJPG), 2026-10-05.

    ~/raptor-venv/bin/python bench_live_camera_modes.py
    ~/raptor-venv/bin/python bench_live_camera_modes.py --modes 1920x1080@60 3840x2160@15
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))


def process_cpu_seconds():
    """CPU seconds used so far by this whole process.

    Python 3.12 does not pass threading.Thread names to the OS, so the camera
    thread cannot be picked out of /proc by name. While measuring, the main
    thread only sleeps, so the process total is the camera thread's cost.
    """
    return time.process_time()


def measure(mode, seconds):
    import cv2  # noqa: F401 - LiveCamera imports it; fail here if it is missing
    from live_camera import LiveCamera

    size, fps = mode.split("@")
    w, h = (int(v) for v in size.split("x"))
    cam = LiveCamera("auto", w, h, "YUYV", int(fps))
    if not cam.start(timeout=10):
        cam.stop()
        return {"mode": mode, "error": cam.status}
    time.sleep(1.0)                          # let the stream settle
    seq0, cpu0, t0 = cam._seq, process_cpu_seconds(), time.monotonic()
    time.sleep(seconds)
    seq1, cpu1, t1 = cam._seq, process_cpu_seconds(), time.monotonic()
    got = cam.size
    cam.stop()
    dt = t1 - t0
    return {"mode": mode, "negotiated": "{}x{}".format(*got),
            "fps_delivered": round((seq1 - seq0) / dt, 2),
            "capture_cpu_pct_of_one_core": round(100 * (cpu1 - cpu0) / dt, 1),
            "ms_cpu_per_frame": round(1000 * (cpu1 - cpu0) / max(1, seq1 - seq0), 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", nargs="+",
                    default=["1280x720@90", "1280x720@60", "1920x1080@60", "1920x1080@30", "3840x2160@15"])
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--out", default=str(Path.home() / "raptor-results" / "camera_modes_2026-10-05.json"))
    args = ap.parse_args()

    rows = []
    for m in args.modes:
        r = measure(m, args.seconds)
        rows.append(r)
        print(json.dumps(r))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                          "camera": "Arducam B0498 (USB3, YUYV)", "rows": rows}, indent=1))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
