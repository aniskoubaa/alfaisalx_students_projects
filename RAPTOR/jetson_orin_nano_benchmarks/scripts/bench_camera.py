#!/usr/bin/env python3
"""E3b — characterise the capture path, and run the deployed model on live frames.

06-benchmark-plan.md asks for this because a capture device "just works" right up
until it silently gives you 5 fps or 720p instead of failing. What matters is the
*negotiated* format and the *achieved* frame rate, not what the device advertises.

    # capture only
    python3 bench_camera.py --device /dev/video0 --width 1920 --height 1080 --fourcc MJPG

    # capture + the deployed pose engine, end to end
    python3 bench_camera.py --model ~/raptor-deploy/pose/yolo11s-pose.engine \\
        --imgsz 960 --save-annotated ~/raptor-results/live_frame.jpg

Reported separately: time to grab a frame, and time to infer on it. Conflating
them hides which half is the bottleneck.
"""
from __future__ import annotations

import argparse
import json
import logging
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
    if not values:
        return {}
    ordered = sorted(values)

    def pct(p: float) -> float:
        idx = min(len(ordered) - 1, max(0, int(round(p / 100 * (len(ordered) - 1)))))
        return ordered[idx]

    return {
        "mean_ms": round(statistics.fmean(ordered), 2),
        "p50_ms": round(pct(50), 2),
        "p95_ms": round(pct(95), 2),
        "max_ms": round(ordered[-1], 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fourcc", default="MJPG", help="MJPG or YUYV")
    ap.add_argument("--fps-request", type=int, default=30)
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--model", help="optional: run this model on the live frames")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--classes", type=int, nargs="*", default=[0])
    ap.add_argument("--save-annotated", help="write one annotated frame here")
    ap.add_argument("--board", default="orin-nx-16g")
    ap.add_argument("--out", default=str(SCRIPT_DIR.parent / "results" / "camera.jsonl"))
    ap.add_argument("--no-tegrastats", action="store_true")
    args = ap.parse_args()

    import cv2

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise SystemExit(f"could not open {args.device}")

    # Order matters: set FOURCC before the frame size, or V4L2 may negotiate a
    # different pixel format and quietly cap the frame rate.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps_request)

    def fourcc_str(value: float) -> str:
        v = int(value)
        return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))

    negotiated = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fourcc": fourcc_str(cap.get(cv2.CAP_PROP_FOURCC)),
        "fps_reported": cap.get(cv2.CAP_PROP_FPS),
    }
    print(f"requested {args.width}x{args.height} {args.fourcc} @{args.fps_request}")
    print(f"negotiated {negotiated['width']}x{negotiated['height']} "
          f"{negotiated['fourcc']} @{negotiated['fps_reported']}")
    if (negotiated["width"], negotiated["height"]) != (args.width, args.height):
        print("WARNING: device did not accept the requested resolution", file=sys.stderr)
    if negotiated["fourcc"] != args.fourcc:
        print("WARNING: device did not accept the requested pixel format", file=sys.stderr)

    model = None
    if args.model:
        logging.getLogger("ultralytics").setLevel(logging.ERROR)
        from ultralytics import YOLO
        model = YOLO(args.model)

    for _ in range(args.warmup):
        ok, frame = cap.read()
        if ok and model is not None:
            model.predict(frame, imgsz=args.imgsz, classes=args.classes, verbose=False)

    grab_ms: list[float] = []
    infer_ms: list[float] = []
    detections: list[int] = []
    dropped = 0
    last_frame = None
    last_result = None

    sampler = None if args.no_tegrastats else TegraSampler()
    if sampler:
        sampler.start()

    wall_start = time.perf_counter()
    for _ in range(args.frames):
        t0 = time.perf_counter()
        ok, frame = cap.read()
        grab_ms.append((time.perf_counter() - t0) * 1000.0)
        if not ok or frame is None:
            dropped += 1
            continue
        last_frame = frame
        if model is not None:
            t1 = time.perf_counter()
            res = model.predict(frame, imgsz=args.imgsz, classes=args.classes, verbose=False)
            infer_ms.append((time.perf_counter() - t1) * 1000.0)
            last_result = res
            try:
                detections.append(len(res[0].boxes))
            except (IndexError, AttributeError, TypeError):
                detections.append(0)
    wall = time.perf_counter() - wall_start

    if sampler:
        sampler.stop()
    cap.release()

    achieved_fps = round((args.frames - dropped) / wall, 2)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": "E3b",
        "board": args.board,
        "device": args.device,
        "requested": {"width": args.width, "height": args.height,
                      "fourcc": args.fourcc, "fps": args.fps_request},
        "negotiated": negotiated,
        "frames_requested": args.frames,
        "frames_dropped": dropped,
        "achieved_fps_end_to_end": achieved_fps,
        "grab": percentiles(grab_ms),
        "model": Path(args.model).name if args.model else None,
        "imgsz": args.imgsz if args.model else None,
        "infer": percentiles(infer_ms) if infer_ms else None,
        "detections_per_frame_mean": round(statistics.fmean(detections), 2) if detections else None,
        "env": collect_env.collect(str(SCRIPT_DIR)),
    }
    if sampler:
        row["tegrastats"] = sampler.summary()

    if args.save_annotated and last_result is not None:
        out_img = Path(args.save_annotated)
        out_img.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_img), last_result[0].plot())
        row["annotated_frame"] = str(out_img)
    elif args.save_annotated and last_frame is not None:
        out_img = Path(args.save_annotated)
        out_img.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_img), last_frame)
        row["annotated_frame"] = str(out_img)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    print("\n--- result ---")
    print(f"negotiated  {negotiated['width']}x{negotiated['height']} {negotiated['fourcc']}")
    print(f"grab        mean {row['grab'].get('mean_ms')} ms | p95 {row['grab'].get('p95_ms')} ms")
    if row["infer"]:
        print(f"infer       mean {row['infer']['mean_ms']} ms | p95 {row['infer']['p95_ms']} ms")
        print(f"detections  {row['detections_per_frame_mean']} per frame (class {args.classes})")
    print(f"end-to-end  {achieved_fps} FPS, {dropped} dropped of {args.frames}")
    ts = row.get("tegrastats") or {}
    if "board_power_mean_w" in ts:
        print(f"power       {ts['board_power_mean_w']} W mean")
    print(f"appended to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
