#!/usr/bin/env python3
"""E1 for a YOLO engine served by the lean TensorRT runner (src/common/trt_yolo.py).

The deployment path the second round recommends: the same .engine that
bench_detector.py times through Ultralytics, run directly. Timed on the same real
frames, scored with person_scoring.py - so the row compares with every other one.

    python3 bench_lean_yolo.py --engine ~/raptor-models/aerial/visdrone-yolo26s-736x1280.engine \\
        --classes 0 1 --source ~/raptor-data/visdrone-person/images/val --frames 200 \\
        --data ~/raptor-data/visdrone-person/visdrone_person.yaml

The accuracy should match the Ultralytics rows for the same weights: that is the
check that the lean runner resizes, filters and suppresses exactly as they do.
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
REPO_ROOT = SCRIPT_DIR.parents[1]          # src/<group>/ -> repository root
for _path in (SCRIPT_DIR, SCRIPT_DIR.parent / "common"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import collect_env  # noqa: E402
from bench_detector import make_frames, percentiles, sha256_file  # noqa: E402
from person_scoring import dataset_images, score  # noqa: E402
from tegra_sampler import TegraSampler  # noqa: E402
from trt_yolo import TrtYolo  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", required=True, help="Ultralytics-exported .engine")
    ap.add_argument("--classes", type=int, nargs="+", default=[0], help="class ids that count as person")
    ap.add_argument("--source", required=True, help="image directory to time on (real frames)")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--conf", type=float, default=0.25, help="threshold used while timing")
    ap.add_argument("--data", help="dataset yaml to score (its 'val' split)")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=str(REPO_ROOT / "benchmarks" / "results" / "detector.jsonl"))
    args = ap.parse_args()

    import cv2
    import torch

    det = TrtYolo(args.engine, classes=args.classes, conf=args.conf)
    imgsz = [det.h, det.w] if det.h != det.w else det.h

    # Timing: frames from disk outside the clock, as bench_detector.py does.
    for frame in make_frames(args.source, imgsz, args.warmup):
        det(frame)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    sampler = TegraSampler()
    sampler.start()
    lat, dets = [], []
    wall0 = time.perf_counter()
    for frame in make_frames(args.source, imgsz, args.frames):
        t0 = time.perf_counter()
        boxes, _ = det(frame)
        lat.append((time.perf_counter() - t0) * 1000)
        dets.append(len(boxes))
    wall = time.perf_counter() - wall0
    sampler.stop()

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": "E1",
        "board": "orin-nx-16g",
        "model": Path(args.engine).stem,
        "model_run": str(Path(args.engine).expanduser()),
        "model_sha256_16": sha256_file(Path(args.engine).expanduser()),
        "precision": "fp16",
        "backend": "engine",
        "harness": "lean TensorRT runtime (src/common/trt_yolo.py)",
        "imgsz": imgsz,
        "source": args.source,
        "source_is_synthetic": False,
        "frames_measured": len(lat),
        "warmup_discarded": args.warmup,
        "latency": percentiles(lat),
        "fps_mean": round(len(lat) / wall, 2),
        "fps_from_mean_latency": round(1000.0 / statistics.fmean(lat), 2),
        "detections_per_frame_mean": round(statistics.fmean(dets), 2),
        "gpu_mem_peak_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "classes_as_person": args.classes,
        "tegrastats": sampler.summary(),
        "note": args.note,
        "env": collect_env.collect(str(SCRIPT_DIR)),
    }
    if args.data:
        print("scoring ...")
        predict = lambda p: det(cv2.imread(str(p)), conf=0.001)  # noqa: E731 - val()'s floor
        row["accuracy"] = {"dataset": args.data, **score(dataset_images(Path(args.data)), predict)}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    L = row["latency"]
    print("\n--- result ---")
    print(f"model      {row['model']}  [lean TensorRT, fp16, imgsz={imgsz}]")
    print(f"latency    mean {L['mean_ms']} ms | p95 {L['p95_ms']} ms | max {L['max_ms']} ms  (end to end)")
    if "accuracy" in row:
        a = row["accuracy"]
        print(f"accuracy   mAP50 {a['map50']} | mAP50-95 {a['map50_95']} | P {a['precision']} | R {a['recall']}")
    print(f"power      {row['tegrastats'].get('board_power_mean_w')} W mean")
    print(f"appended to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
