#!/usr/bin/env python3
"""Does GPU pre-processing in trt_yolo.py change the detections? And how much faster is it?

The lean runner's CPU letterbox is a copy of Ultralytics' (cv2 resize + pad), so
its detections match Ultralytics'. The GPU path resizes with torch bilinear
instead of cv2 - same sampling grid, but not bit-identical pixels. This runs both
paths of ONE engine on the same real frames and compares them box by box.

    ~/raptor-venv/bin/python check_trt_yolo_gpu.py
    ~/raptor-venv/bin/python check_trt_yolo_gpu.py --source ~/raptor-data/video/stress_aerial_1080p.mp4

Pass criteria (printed): the same number of people on >= 98 % of frames, and
matched boxes overlapping at IoU >= 0.95 on average.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def match(ba, bb):
    """Greedy best-IoU matching. Returns (matched IoUs, unmatched count)."""
    used, ious = set(), []
    for a in ba:
        best, bj = 0.0, None
        for j, b in enumerate(bb):
            if j not in used:
                v = iou(a, b)
                if v > best:
                    best, bj = v, j
        if bj is not None and best > 0.3:
            used.add(bj)
            ious.append(best)
    return ious, (len(ba) - len(ious)) + (len(bb) - len(used))


def frames_from(source, n):
    import cv2

    cap = cv2.VideoCapture(str(source))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or n
    out = []
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i * total / n))
        ok, f = cap.read()
        if ok:
            out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", default=str(Path.home() / "raptor-deploy/detector/visdrone-yolo26s-736x1280.engine"))
    ap.add_argument("--source", default=str(Path.home() / "raptor-data/video/stress_aerial_1080p.mp4"))
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--out", default=str(Path.home() / "raptor-results" / "trt_yolo_gpu_check_2026-10-05.json"))
    args = ap.parse_args()

    import torch
    from trt_yolo import TrtYolo

    det = TrtYolo(args.engine, classes=[0, 1], conf=args.conf)
    frames = frames_from(args.source, args.frames)
    print("{} frames of {}x{} from {}".format(len(frames), frames[0].shape[1], frames[0].shape[0], args.source))

    for _ in range(10):                                   # warm both paths
        det.gpu_preprocess = False
        det(frames[0])
        det.gpu_preprocess = True
        det(frames[0])

    timing = {"cpu": [], "gpu": []}
    same_count, ious, unmatched, people = 0, [], 0, 0
    for f in frames:
        res = {}
        for path in ("cpu", "gpu"):
            det.gpu_preprocess = path == "gpu"
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            res[path] = det(f)
            timing[path].append((time.perf_counter() - t0) * 1000)
        bc, bg = res["cpu"][0].tolist(), res["gpu"][0].tolist()
        people += len(bc)
        same_count += len(bc) == len(bg)
        m, u = match(bc, bg)
        ious += m
        unmatched += u

    def summ(v):
        v = sorted(v)
        return {"mean_ms": round(statistics.mean(v), 2), "p95_ms": round(v[int(0.95 * (len(v) - 1))], 2)}

    result = {
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": Path(args.engine).name, "source": args.source, "frames": len(frames),
        "frame_size": "{}x{}".format(frames[0].shape[1], frames[0].shape[0]),
        "people_cpu_path": people,
        "same_count_pct": round(100 * same_count / len(frames), 1),
        "matched_iou_mean": round(statistics.mean(ious), 4) if ious else None,
        "matched_iou_min": round(min(ious), 4) if ious else None,
        "unmatched_boxes": unmatched,
        "cpu_preprocess": summ(timing["cpu"]),
        "gpu_preprocess": summ(timing["gpu"]),
    }
    result["speedup"] = round(result["cpu_preprocess"]["mean_ms"] / result["gpu_preprocess"]["mean_ms"], 2)
    result["pass"] = result["same_count_pct"] >= 98.0 and (result["matched_iou_mean"] or 0) >= 0.95
    Path(args.out).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
