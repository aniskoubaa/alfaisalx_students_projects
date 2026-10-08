#!/usr/bin/env python3
"""Run the live demo for a long time and report whether it survives.

The demo runs as a SEPARATE PROCESS, so a crash - a Python exception, a native
abort, a segfault, the kernel's OOM killer - shows up here as an early exit, a
signal and a traceback in the log, instead of taking this script down with it.

Everything the demo prints goes to a log file, with Python's faulthandler on
(a native crash still leaves a stack). Every 2 s the demo's resident memory and
the board's available memory are sampled, so a slow leak shows as a slope even
when the run is too short for it to kill anything.

At the end the demo is sent SIGINT, so its shutdown path is tested too.

    soak_demo.py --name street_bench --minutes 10 -- --mode bench \\
        --source ~/raptor-data/video/stress_street_1080p.mp4
    soak_demo.py --name live_1080p60 --minutes 30 -- --mode bench \\
        --width 1920 --height 1080 --fps 60 --fourcc YUYV

Arguments after `--` go to raptor_live_demo.py (--no-display and --stats are
always added). Writes <out>/<name>_<time>.log and .json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent / "demo" / "raptor_live_demo.py"
ERROR_PATTERNS = re.compile(
    r"Traceback|Error|Exception|Fatal Python error|Segmentation fault|terminate called|"
    r"core dumped|Killed|CUDA error|out of memory|cudaError|\[TRT\].*(ERROR|error)", re.I)
HEARTBEAT = re.compile(r"^frame (\d+): .* ([\d.]+) FPS, infer ([\d.]+) ms")


def desktop_display():
    """DISPLAY and XAUTHORITY of the logged-in user's Xwayland, read from its command line."""
    out = subprocess.run(["ps", "-o", "args=", "-C", "Xwayland"], capture_output=True, text=True).stdout
    m_d, m_a = re.search(r"Xwayland (:\d+)", out), re.search(r"-auth (\S+)", out)
    if not (m_d and m_a):
        raise SystemExit("--with-window: no Xwayland session found (is anyone logged in on the desktop?)")
    return {"DISPLAY": m_d.group(1), "XAUTHORITY": m_a.group(1)}


def rss_mb(pid):
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    return None


def mem_available_mb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024
    return None


def slope_mb_per_min(samples):
    """Least-squares slope of RSS over the second half of the run (after warm-up)."""
    pts = [(t, r) for t, r in samples if r is not None]
    pts = pts[len(pts) // 2:]
    if len(pts) < 5:
        return None
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    mr = sum(r for _, r in pts) / n
    den = sum((t - mt) ** 2 for t, _ in pts)
    return round(60 * sum((t - mt) * (r - mr) for t, r in pts) / den, 2) if den else None


def main():
    argv = sys.argv[1:]
    demo_args = []
    if "--" in argv:
        i = argv.index("--")
        argv, demo_args = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--hang-seconds", type=float, default=120.0,
                    help="no progress line for this long counts as a hang")
    ap.add_argument("--python", default=str(Path.home() / "raptor-venv" / "bin" / "python"))
    ap.add_argument("--with-window", action="store_true",
                    help="open the demo's video window on the logged-in desktop (the way it is really "
                         "used) instead of running headless; DISPLAY/XAUTHORITY are taken from Xwayland")
    ap.add_argument("--demo", default=str(DEMO),
                    help="script to run (default: the live demo; tests/fault_inject_demo.py to inject faults)")
    ap.add_argument("--out", default=str(Path.home() / "raptor-results" / "soak"))
    args = ap.parse_args(argv)

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = out / f"{args.name}_{stamp}.log"
    demo = Path(args.demo)
    demo = demo if demo.is_absolute() else (HERE / demo)
    cmd = [args.python, "-X", "faulthandler", str(demo), "--stats"] + ([] if args.with_window else ["--no-display"])
    cmd += demo_args
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONFAULTHANDLER="1")
    if args.with_window:
        env.update(desktop_display())

    print("soak:", args.name, "for", args.minutes, "min")
    print("cmd :", " ".join(cmd))
    print("log :", log_path)
    t0 = time.monotonic()
    logf = log_path.open("w", buffering=1)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                            bufsize=1)

    state = {"last_progress": time.monotonic(), "frames": 0, "fps": [], "infer": [], "errors": []}

    def pump():
        for line in proc.stdout:
            logf.write(line)
            m = HEARTBEAT.search(line)
            if m:
                state["last_progress"] = time.monotonic()
                state["frames"] = int(m.group(1))
                state["fps"].append(float(m.group(2)))
                state["infer"].append(float(m.group(3)))
            elif (ERROR_PATTERNS.search(line) and not line.lstrip().startswith('"')
                  and len(state["errors"]) < 60):     # skip the demo's own stats JSON keys
                state["errors"].append(line.rstrip()[:300])

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()

    samples, mem_min, hung = [], None, False
    deadline = t0 + args.minutes * 60
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(2.0)
        r, a = rss_mb(proc.pid), mem_available_mb()
        samples.append((time.monotonic() - t0, r))
        mem_min = a if mem_min is None or (a is not None and a < mem_min) else mem_min
        if (not args.with_window and time.monotonic() - state["last_progress"] > args.hang_seconds
                and time.monotonic() - t0 > 90):   # a window run prints no progress lines
            hung = True
            break

    finished_early = proc.poll() is not None
    if not finished_early:
        proc.send_signal(signal.SIGINT)            # graceful stop: tests the shutdown path
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    reader.join(5)
    logf.close()
    elapsed = time.monotonic() - t0

    code = proc.returncode
    stats = None
    text = log_path.read_text(errors="replace")
    m = re.search(r"\{\s*\"mode\".*\}", text, re.S)
    if m:
        try:
            stats = json.loads(m.group(0))
        except ValueError:
            stats = None
    rss = [r for _, r in samples if r is not None]
    fps = sorted(state["fps"])
    crashed = finished_early or hung or (code not in (0, None) and not (code == -signal.SIGINT))
    result = {
        "name": args.name, "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "demo_args": demo_args, "minutes_planned": args.minutes, "minutes_ran": round(elapsed / 60, 2),
        "outcome": "HUNG" if hung else ("CRASHED" if finished_early and code != 0 else
                                        "EXITED EARLY" if finished_early else "SURVIVED"),
        "exit_code": code, "signal": (-code if code is not None and code < 0 else None),
        "frames": (stats or {}).get("frames", state["frames"]),
        "fps_mean": round(sum(fps) / len(fps), 1) if fps else None,
        "fps_p5": fps[len(fps) // 20] if fps else None,
        "infer_ms_mean": round(sum(state["infer"]) / len(state["infer"]), 1) if state["infer"] else None,
        "rss_mb_start": round(rss[min(5, len(rss) - 1)], 0) if rss else None,
        "rss_mb_peak": round(max(rss), 0) if rss else None,
        "rss_mb_end": round(rss[-1], 0) if rss else None,
        "rss_slope_mb_per_min": slope_mb_per_min(samples),
        "board_mem_available_min_mb": round(mem_min, 0) if mem_min else None,
        "error_lines": state["errors"],
        "demo_stats": stats,
        "log": str(log_path),
        "crashed": crashed,
    }
    (out / f"{args.name}_{stamp}.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k not in ("demo_stats", "error_lines")}, indent=1))
    if state["errors"]:
        print("first error lines:")
        for e in state["errors"][:12]:
            print("   ", e)
    return 1 if crashed else 0


if __name__ == "__main__":
    raise SystemExit(main())
