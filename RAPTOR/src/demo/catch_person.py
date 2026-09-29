#!/usr/bin/env python3
"""Capture one annotated frame that proves the live pipeline really detects people.

Runs ON THE JETSON, in ~/raptor-venv:

    python catch_person.py                                  # defaults below
    python catch_person.py --out ~/person.jpg --max-frames 600 --good-enough 0.8

Reads the camera, runs the deployed TensorRT pose engine on each frame, and keeps
the frame with the most confident person detection - drawn with boxes and the 17
keypoints - stopping early once one is confident enough. Step into view (or point
the camera at someone) while it runs.

Why this exists alongside raptor_live_demo.py: the demo shows a live window, which
needs a display. This works headless, over SSH, and leaves behind an image file
you can inspect - it is how the first live detection in docs/14 was captured.

Exit status is 0 if a person was found and saved, 1 if not, 2 if the camera or
model could not be opened.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=str(Path.home() / "raptor-deploy/pose/yolo26s-pose-960.engine"))
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--out", default=str(Path.home() / "raptor-results/person_detected.jpg"))
    ap.add_argument("--max-frames", type=int, default=300, help="give up after this many frames")
    ap.add_argument("--conf", type=float, default=0.35, help="minimum confidence to count as a person")
    ap.add_argument("--good-enough", type=float, default=0.75, help="stop early at this confidence")
    ap.add_argument("--imgsz", type=int, default=960, help="must match the size the engine was built for")
    args = ap.parse_args()

    import cv2
    logging.getLogger("ultralytics").setLevel(logging.ERROR)
    from ultralytics import YOLO

    if not Path(args.model).exists():
        print(f"model not found: {args.model}", file=sys.stderr)
        return 2
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"could not open {args.device} - is the camera plugged in?", file=sys.stderr)
        return 2
    # MJPG before the size: on a USB 2.0 link, uncompressed 1080p only reaches 5 fps.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    model = YOLO(args.model)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    best_conf, best_n, saved = 0.0, 0, False
    try:
        for i in range(args.max_frames):
            ok, frame = cap.read()
            if not ok:
                continue
            res = model.predict(frame, imgsz=args.imgsz, classes=[0], conf=args.conf, verbose=False)
            boxes = res[0].boxes
            if len(boxes) == 0:
                continue
            conf = float(boxes.conf.max())
            kp = res[0].keypoints
            n_kp = int(kp.data.shape[1]) if kp is not None and kp.data is not None else 0
            print(f"frame {i}: {len(boxes)} person(s), top confidence {conf:.2f}, {n_kp} keypoints",
                  flush=True)
            if conf > best_conf:
                best_conf, best_n = conf, len(boxes)
                cv2.imwrite(args.out, res[0].plot())
                saved = True
            if conf >= args.good_enough:
                break
    finally:
        cap.release()

    if saved:
        print(f"saved {args.out}: {best_n} person(s), best confidence {best_conf:.2f}")
        return 0
    print(f"no person detected in {args.max_frames} frames - is anyone in view?")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
