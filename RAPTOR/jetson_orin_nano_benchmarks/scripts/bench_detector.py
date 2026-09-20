#!/usr/bin/env python3
"""E1/E2/E4 — detector latency, throughput, power and memory on the Jetson.

Implements the detector sweep from 06-benchmark-plan.md. One invocation = one
configuration = one JSON line appended to results/.

    # latency only, needs no dataset
    python3 bench_detector.py --model yolo11n-pose.pt --imgsz 640 --frames 300

    # against recorded footage
    python3 bench_detector.py --model yolo11s.pt --source ../videos/flight01.mp4

    # TensorRT FP16
    python3 bench_detector.py --model yolo11s-pose.pt --export engine --half

Reported numbers follow the plan's rules: the first --warmup inferences are
discarded, and p95 is reported alongside the mean because a pipeline that
averages 25 ms but spikes to 60 ms drops frames when the scene is busiest.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import collect_env  # noqa: E402
from tegra_sampler import TegraSampler  # noqa: E402


def sha256_file(path: Path, limit_mb: int = 512) -> str:
    """Hash a weights file so a result row identifies the exact model."""
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    read = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
            read += len(chunk)
            if read > limit_mb * 1024 * 1024:
                break
    return h.hexdigest()[:16]


def make_frames(source: str, imgsz: int, count: int):
    """Yield BGR frames from a video, an image directory, or synthetic noise.

    Synthetic frames exist so latency can be characterised before any flight
    footage has been recorded. They are valid for timing but say nothing about
    accuracy, and results are tagged accordingly.
    """
    import numpy as np

    if source == "synthetic":
        rng = np.random.default_rng(0)
        base = rng.integers(0, 255, (imgsz, imgsz, 3), dtype=np.uint8)
        for _ in range(count):
            yield base
        return

    import cv2

    path = Path(source)
    if path.is_dir():
        exts = {".jpg", ".jpeg", ".png", ".bmp"}
        files = sorted(p for p in path.iterdir() if p.suffix.lower() in exts)
        if not files:
            raise SystemExit(f"no images found in {path}")
        for i in range(count):
            img = cv2.imread(str(files[i % len(files)]))
            if img is not None:
                yield img
        return

    if not path.is_file():
        raise SystemExit(f"source not found: {path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"could not open video: {path}")
    emitted = 0
    try:
        while emitted < count:
            ok, frame = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop shorter clips
                ok, frame = cap.read()
                if not ok:
                    break
            yield frame
            emitted += 1
    finally:
        cap.release()


def percentiles(values: list[float]) -> dict:
    """Latency distribution. p95 is the number the frame budget is judged on."""
    ordered = sorted(values)

    def pct(p: float) -> float:
        if not ordered:
            return float("nan")
        idx = min(len(ordered) - 1, max(0, int(round(p / 100 * (len(ordered) - 1)))))
        return ordered[idx]

    return {
        "mean_ms": round(statistics.fmean(ordered), 3),
        "stdev_ms": round(statistics.stdev(ordered), 3) if len(ordered) > 1 else 0.0,
        "min_ms": round(ordered[0], 3),
        "p50_ms": round(pct(50), 3),
        "p95_ms": round(pct(95), 3),
        "p99_ms": round(pct(99), 3),
        "max_ms": round(ordered[-1], 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="weights: yolo11n.pt, yolo11s-pose.pt, path/to/x.engine")
    ap.add_argument("--imgsz", type=int, default=640, help="inference size (640/832/960)")
    ap.add_argument("--source", default="synthetic", help="'synthetic', a video file, or an image dir")
    ap.add_argument("--frames", type=int, default=300, help="measured frames (after warm-up)")
    ap.add_argument("--warmup", type=int, default=50, help="discarded inferences (plan requires ~50)")
    ap.add_argument("--device", default="0", help="'0' for GPU, 'cpu', or 'dla:0'")
    ap.add_argument("--half", action="store_true", help="FP16")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--classes", type=int, nargs="*",
                    help="restrict to these class ids (COCO person is 0) — matches how "
                         "RAPTOR runs, and is required when validating an 80-class model "
                         "against a single-class dataset")
    ap.add_argument("--export", choices=["engine", "onnx"], help="export before benchmarking")
    ap.add_argument("--int8", action="store_true", help="INT8 export (needs --data for calibration)")
    ap.add_argument("--data", help="calibration/val dataset yaml")
    ap.add_argument("--accuracy", action="store_true", help="also run val() for mAP (requires --data)")
    ap.add_argument("--board", default="orin-nx-16g", help="recorded so NX and Nano rows are comparable")
    ap.add_argument("--note", default="", help="free-text label for this run")
    ap.add_argument("--out", default=str(SCRIPT_DIR.parent / "results" / "detector.jsonl"))
    ap.add_argument("--no-tegrastats", action="store_true")
    args = ap.parse_args()

    import torch
    from ultralytics import YOLO

    def load_model(weights):
        """RT-DETR needs its own class; everything else goes through YOLO().

        Doc 02 keeps RT-DETR on the shortlist as the permissive-licence escape
        hatch if Ultralytics' AGPL ever becomes a blocker, so it has to be
        benchmarkable by the same harness.
        """
        if 'rtdetr' in Path(str(weights)).name.lower():
            from ultralytics import RTDETR
            return RTDETR(weights)
        return YOLO(weights)

    # Ultralytics logs a deprecation line on *every* predict() call, which buries
    # the result. We only want failures from it.
    logging.getLogger("ultralytics").setLevel(logging.ERROR)

    # val() calls check_font(), which imports matplotlib. The venv is built with
    # --system-site-packages (09-jetson-environment.md requires it for the CUDA
    # stack), so it picks up JetPack's matplotlib — compiled against NumPy 1.x
    # while this venv has NumPy 2.x, which raises
    # "numpy.core.multiarray failed to import" and kills validation.
    # The font is only used to draw labels on plots we don't generate, so stub it
    # rather than disturb the board's packages.
    try:
        from ultralytics.utils import checks as _uchecks
        from ultralytics.data import utils as _udata

        _uchecks.check_font = lambda *_a, **_k: None
        _udata.check_font = lambda *_a, **_k: None
    except Exception as exc:  # noqa: BLE001 - stubbing is best-effort
        print(f"note: could not stub check_font ({exc})", file=sys.stderr)

    # 8.4 renamed the FP16 switch from half= to quantize=. Probe once rather than
    # pinning a version, so this keeps working either side of the rename.
    sig = inspect.signature(YOLO.predict)
    use_quantize = "quantize" in sig.parameters
    precision_kwargs: dict = {}
    if args.half:
        precision_kwargs = {"quantize": "fp16"} if use_quantize else {"half": True}
    if args.classes:
        precision_kwargs["classes"] = args.classes

    env = collect_env.collect(str(SCRIPT_DIR))
    if not env["stack"].get("cuda_available") and args.device != "cpu":
        print("WARNING: torch reports CUDA unavailable — this will be a CPU run.", file=sys.stderr)
        print("         09-jetson-environment.md: a CPU-only torch looks fine and runs at a few FPS.", file=sys.stderr)

    model_arg = args.model
    if args.export:
        print(f"exporting {args.model} -> {args.export} (half={args.half}, int8={args.int8})")
        exporter = load_model(args.model)
        export_kwargs = {"format": args.export, "imgsz": args.imgsz, "half": args.half}
        if args.int8:
            if not args.data:
                raise SystemExit("--int8 requires --data (calibration must use our own footage, not COCO)")
            export_kwargs.update({"int8": True, "data": args.data, "half": False})
        t0 = time.perf_counter()
        model_arg = exporter.export(**export_kwargs)
        print(f"export took {time.perf_counter() - t0:.1f}s -> {model_arg}")

    model = load_model(model_arg)

    # Warm-up: discarded, because the first inferences include lazy CUDA context
    # creation, kernel autotuning and TensorRT engine deserialisation.
    print(f"warming up ({args.warmup} inferences)...")
    for frame in make_frames(args.source, args.imgsz, args.warmup):
        model.predict(frame, imgsz=args.imgsz, device=args.device,
                      conf=args.conf, verbose=False, **precision_kwargs)

    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()

    latencies: list[float] = []
    detections: list[int] = []
    # Ultralytics reports its own preprocess/inference/postprocess split. Wall
    # clock that barely moves between model sizes means the cost is not in
    # inference, and this is what shows where it actually is.
    stage_ms: dict[str, list[float]] = {"preprocess": [], "inference": [], "postprocess": []}
    sampler = None if args.no_tegrastats else TegraSampler()
    if sampler:
        sampler.start()

    print(f"measuring {args.frames} frames...")
    wall_start = time.perf_counter()
    for frame in make_frames(args.source, args.imgsz, args.frames):
        t0 = time.perf_counter()
        results = model.predict(frame, imgsz=args.imgsz, device=args.device,
                                conf=args.conf, verbose=False, **precision_kwargs)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        latencies.append((time.perf_counter() - t0) * 1000.0)
        try:
            detections.append(len(results[0].boxes))
        except (IndexError, AttributeError, TypeError):
            detections.append(0)
        try:
            for stage, value in (results[0].speed or {}).items():
                if stage in stage_ms and value is not None:
                    stage_ms[stage].append(float(value))
        except (IndexError, AttributeError, TypeError):
            pass
    wall = time.perf_counter() - wall_start

    if sampler:
        sampler.stop()

    if not latencies:
        raise SystemExit("no frames were measured")

    row: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": "E1",
        "board": args.board,
        "model": str(args.model),
        "model_run": str(model_arg),
        "model_sha256_16": sha256_file(Path(model_arg) if Path(str(model_arg)).exists() else Path(args.model)),
        "precision": "int8" if args.int8 else ("fp16" if args.half else "fp32"),
        "backend": Path(str(model_arg)).suffix.lstrip(".") or "pt",
        "imgsz": args.imgsz,
        "device": args.device,
        "source": args.source,
        "source_is_synthetic": args.source == "synthetic",
        "frames_measured": len(latencies),
        "warmup_discarded": args.warmup,
        "latency": percentiles(latencies),
        "fps_mean": round(len(latencies) / wall, 2),
        "fps_from_mean_latency": round(1000.0 / statistics.fmean(latencies), 2),
        "detections_per_frame_mean": round(statistics.fmean(detections), 2) if detections else None,
        "note": args.note,
        "env": env,
    }

    stage_means = {k: round(statistics.fmean(v), 3) for k, v in stage_ms.items() if v}
    if stage_means:
        row["stage_ms_mean"] = stage_means
        row["stage_overhead_ms"] = round(
            row["latency"]["mean_ms"] - sum(stage_means.values()), 3)

    if torch.cuda.is_available():
        row["gpu_mem_peak_mb"] = round(torch.cuda.max_memory_allocated() / 1024**2, 1)

    if sampler:
        row["tegrastats"] = sampler.summary()

    if args.accuracy:
        if not args.data:
            raise SystemExit("--accuracy requires --data")
        print("running validation for mAP...")
        val_kwargs = {"data": args.data, "imgsz": args.imgsz, "device": args.device,
                      "verbose": False, "plots": False}
        if args.classes:
            val_kwargs["classes"] = args.classes
        val_kwargs.update({k: v for k, v in precision_kwargs.items() if k != "classes"})
        metrics = load_model(model_arg).val(**val_kwargs)
        try:
            row["accuracy"] = {
                "dataset": args.data,
                "map50": round(float(metrics.box.map50), 4),
                "map50_95": round(float(metrics.box.map), 4),
                "precision": round(float(metrics.box.mp), 4),
                "recall": round(float(metrics.box.mr), 4),
            }
        except AttributeError as exc:
            row["accuracy"] = {"dataset": args.data, "error": str(exc)}

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    lat = row["latency"]
    print("\n--- result ---")
    print(f"model      {row['model']}  [{row['backend']}, {row['precision']}, imgsz={row['imgsz']}]")
    print(f"latency    mean {lat['mean_ms']} ms | p95 {lat['p95_ms']} ms | max {lat['max_ms']} ms")
    print(f"throughput {row['fps_mean']} FPS")
    if stage_means:
        print(f"stages     pre {stage_means.get('preprocess', 0)} ms | "
              f"infer {stage_means.get('inference', 0)} ms | "
              f"post {stage_means.get('postprocess', 0)} ms | "
              f"unaccounted {row['stage_overhead_ms']} ms")
    if "gpu_mem_peak_mb" in row:
        print(f"gpu mem    {row['gpu_mem_peak_mb']} MB peak")
    tstats = row.get("tegrastats") or {}
    if "board_power_mean_w" in tstats:
        print(f"power      {tstats['board_power_mean_w']} W mean / {tstats['board_power_max_w']} W max "
              f"({tstats.get('board_power_rail')})")
    if "temp_max_c" in tstats:
        print(f"temp       {tstats['temp_max_c']} C max ({tstats.get('temp_hottest_sensor')})")
    acc = row.get("accuracy") or {}
    if "map50" in acc:
        print(f"accuracy   mAP50 {acc['map50']} | mAP50-95 {acc['map50_95']} | "
              f"P {acc['precision']} | R {acc['recall']}")
    budget = 33.0
    verdict = "WITHIN" if lat["p95_ms"] <= budget else "OVER"
    print(f"frame budget (33 ms hard limit): p95 is {verdict}")
    print(f"appended to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
