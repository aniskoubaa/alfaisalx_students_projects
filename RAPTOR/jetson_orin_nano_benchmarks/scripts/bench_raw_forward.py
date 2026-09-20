#!/usr/bin/env python3
"""Isolate pure GPU inference from framework overhead.

The E1 sweep produced near-identical wall-clock latency for yolo11n and yolo11s
across 640/832/960, while board power rose from ~8 W to ~13 W. Power scaling with
flat latency means the GPU is doing more work in the same elapsed time — i.e. the
measurement is dominated by a fixed per-call cost, not by inference.

This script removes Ultralytics' predict() wrapper entirely and times only
`model.forward()` on a pre-made GPU tensor. The difference between the two is the
overhead budget a long-running ROS 2 node can reclaim (04-ros2-architecture.md:
the production system loads the model once and streams frames, rather than paying
CLI-style setup per frame).

    python3 bench_raw_forward.py --model ~/raptor-models/yolo11s.pt --imgsz 960
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import collect_env  # noqa: E402
from tegra_sampler import TegraSampler  # noqa: E402


def percentiles(values: list[float]) -> dict:
    ordered = sorted(values)

    def pct(p: float) -> float:
        idx = min(len(ordered) - 1, max(0, int(round(p / 100 * (len(ordered) - 1)))))
        return ordered[idx]

    return {
        "mean_ms": round(statistics.fmean(ordered), 3),
        "p50_ms": round(pct(50), 3),
        "p95_ms": round(pct(95), 3),
        "max_ms": round(ordered[-1], 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--half", action="store_true")
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--board", default="orin-nx-16g")
    ap.add_argument("--out", default=str(SCRIPT_DIR.parent / "results" / "raw_forward.jsonl"))
    ap.add_argument("--no-tegrastats", action="store_true")
    args = ap.parse_args()

    import torch
    from ultralytics import YOLO

    env = collect_env.collect(str(SCRIPT_DIR))
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable — this experiment is meaningless on CPU")

    net = YOLO(args.model).model.to("cuda:0").eval()
    dtype = torch.float16 if args.half else torch.float32
    if args.half:
        net = net.half()

    x = torch.randn(args.batch, 3, args.imgsz, args.imgsz, device="cuda:0", dtype=dtype)

    with torch.inference_mode():
        for _ in range(args.warmup):
            net(x)
        torch.cuda.synchronize()

        torch.cuda.reset_peak_memory_stats()
        sampler = None if args.no_tegrastats else TegraSampler()
        if sampler:
            sampler.start()

        times: list[float] = []
        for _ in range(args.iters):
            t0 = time.perf_counter()
            net(x)
            torch.cuda.synchronize()
            times.append((time.perf_counter() - t0) * 1000.0)

        if sampler:
            sampler.stop()

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": "E1-raw-forward",
        "board": args.board,
        "model": Path(args.model).name,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "precision": "fp16" if args.half else "fp32",
        "iters": args.iters,
        "latency": percentiles(times),
        "fps_from_mean": round(1000.0 / statistics.fmean(times), 2),
        "gpu_mem_peak_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "env": env,
    }
    if sampler:
        row["tegrastats"] = sampler.summary()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    print(f"{row['model']} @ {args.imgsz} [{row['precision']}, batch {args.batch}]")
    print(f"  forward only: mean {row['latency']['mean_ms']} ms | "
          f"p95 {row['latency']['p95_ms']} ms -> {row['fps_from_mean']} FPS")
    print(f"  gpu mem     : {row['gpu_mem_peak_mb']} MB")
    ts = row.get("tegrastats") or {}
    if "board_power_mean_w" in ts:
        print(f"  power       : {ts['board_power_mean_w']} W mean")
    print(f"  appended to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
