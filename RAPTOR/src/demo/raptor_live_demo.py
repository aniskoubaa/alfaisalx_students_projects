#!/usr/bin/env python3
"""RAPTOR live demo - camera -> aerial detector -> pose on crops -> annotated window.

Runs the deployed models (~/raptor-deploy, see src/deploy/deploy_models.py) on the
live camera the way the aircraft would, in two stages:

  tier 1  the aerial-trained detector (YOLO26s on VisDrone, 736x1280) on EVERY
          frame, through the lean TensorRT runner (src/common/trt_yolo.py);
  tier 2  YOLO26s-pose on crops of the detected people, every few frames, for
          people tall enough for keypoints; their posture label is carried
          between pose passes. Smaller people are marked "too small for pose".

    python3 raptor_live_demo.py                       # two-stage, from ~/raptor-deploy
    python3 raptor_live_demo.py --mode pose-only      # one pose model on the whole frame
    python3 raptor_live_demo.py --no-display          # headless, prints to stdout
    python3 raptor_live_demo.py --record out.mp4      # also write a video
    python3 raptor_live_demo.py --source ~/raptor-data/visdrone-person/images/val
                                  # aerial images (or a video file) instead of the camera

Why two stages (docs/02, docs/10): no aerial-trained pose model exists, and the
COCO pose model finds only about a fifth of the people seen from the air.

The aerial detector was trained on drone footage: small people seen from above.
Pointed at someone sitting next to a desk webcam it may see nobody (measured
2026-09-29: 0 people where the COCO pose model found 1). That is the model doing
its job, not a fault. For bench demos with people close to the camera use
--mode pose-only (the "RAPTOR Live Demo (bench)" icon); to show the flight
pipeline without a drone, use --source with aerial images or footage.

Press q or ESC to quit.

POSTURE CAVEAT, read before believing the label on screen: 02-detection-and-pose.md
specifies posture from keypoints rotated into a *gravity-aligned* frame using the
drone's IMU attitude from MAVROS. There is no IMU on this bench, so the estimate
here uses image vertical as a stand-in. That is correct for a static camera and
wrong the moment the aircraft banks - which is exactly why the real system needs
the attitude feed. It is labelled "(no IMU)" on screen so nobody mistakes this
for the flight tier 2.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
import warnings
from collections import deque
from pathlib import Path

# The installed torch wheel has no sm_87 kernels and says so on every CUDA init.
# It is real and documented (README "environment traps"), but it is not news, and
# a wall of red text on every launch teaches people to ignore warnings. Silenced
# here only - the benchmark scripts still surface it.
warnings.filterwarnings("ignore", message=r".*compute capability.*")
warnings.filterwarnings("ignore", message=r".*No published PyTorch CUDA builds.*")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]          # src/<group>/ -> repository root
# Shared helpers (trt_yolo, tegra_sampler) live in src/common. This file's own
# folder is searched too, so a script copied on its own next to them still works.
for _path in (SCRIPT_DIR, SCRIPT_DIR.parent / "common"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

DEPLOY = Path.home() / "raptor-deploy"
DEFAULT_DETECTOR = DEPLOY / "detector" / "visdrone-yolo26s-736x1280.engine"
DEFAULT_POSE = DEPLOY / "pose" / "yolo26s-pose-960.engine"

# COCO keypoint indices used for the torso vector, and the skeleton to draw.
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 5, 6, 11, 12
SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]
KP_CONF_MIN = 0.35

# Colours (BGR). Status palette: green good, amber caution, red alarming.
C_OK = (76, 175, 80)
C_WARN = (0, 180, 240)
C_ALARM = (60, 60, 220)
C_INK = (245, 245, 245)
C_BOX = (235, 170, 40)
C_MUTED = (170, 170, 170)
C_PANEL = (30, 30, 30)

FRAME_BUDGET_MS = 33.0


def midpoint(pts, i, j):
    """Midpoint of two keypoints, or None if either is not confidently visible."""
    if pts is None:
        return None
    try:
        xi, yi, ci = pts[i]
        xj, yj, cj = pts[j]
    except (IndexError, ValueError, TypeError):
        return None
    if ci < KP_CONF_MIN or cj < KP_CONF_MIN:
        return None
    return ((xi + xj) / 2.0, (yi + yj) / 2.0)


def posture_from_keypoints(pts):
    """Angle of the torso vector away from image vertical -> coarse posture.

    Returns (label, degrees_from_vertical). Deliberately coarse: three buckets
    and an explicit 'unknown', rather than a confident guess from keypoints that
    are not actually visible.
    """
    shoulders = midpoint(pts, L_SHOULDER, R_SHOULDER)
    hips = midpoint(pts, L_HIP, R_HIP)
    if shoulders is None or hips is None:
        return "unknown", None

    dx = hips[0] - shoulders[0]
    dy = hips[1] - shoulders[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return "unknown", None

    # 0 deg = torso aligned with image vertical, 90 deg = horizontal.
    deg = abs(math.degrees(math.atan2(abs(dx), abs(dy))))
    if deg < 30:
        return "standing", deg
    if deg > 60:
        return "LYING", deg
    return "leaning/sitting", deg


def posture_colour(label):
    return {"LYING": C_ALARM, "leaning/sitting": C_WARN, "standing": C_OK}.get(label, C_MUTED)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def pose_on_crop(pose_model, frame, box, margin=0.25):
    """Run the pose model on one person's crop; keypoints come back in frame pixels.

    The crop gets 25 % context on each side so limbs at the box edge survive. If
    the pose model finds several people in the crop, the one nearest its centre
    is the one the detector meant.
    """
    h0, w0 = frame.shape[:2]
    x1, y1, x2, y2 = box
    mw, mh = (x2 - x1) * margin, (y2 - y1) * margin
    cx1, cy1 = int(max(0, x1 - mw)), int(max(0, y1 - mh))
    cx2, cy2 = int(min(w0, x2 + mw)), int(min(h0, y2 + mh))
    crop = frame[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return None
    res = pose_model.predict(crop, imgsz=960, conf=0.25, verbose=False)[0]
    if res.keypoints is None or len(res.boxes) == 0:
        return None
    ccx, ccy = (cx2 - cx1) / 2, (cy2 - cy1) / 2
    centres = [((b[0] + b[2]) / 2 - ccx) ** 2 + ((b[1] + b[3]) / 2 - ccy) ** 2
               for b in res.boxes.xyxy.tolist()]
    k = centres.index(min(centres))
    return [(x + cx1, y + cy1, c) for x, y, c in res.keypoints.data[k].tolist()]


def draw_person(frame, box, score, label, deg, kps):
    import cv2

    x1, y1, x2, y2 = (int(v) for v in box)
    col = posture_colour(label) if label not in (None, "small") else C_BOX
    cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
    if kps:
        for a, b in SKELETON:
            if kps[a][2] >= KP_CONF_MIN and kps[b][2] >= KP_CONF_MIN:
                cv2.line(frame, (int(kps[a][0]), int(kps[a][1])), (int(kps[b][0]), int(kps[b][1])),
                         col, 2, cv2.LINE_AA)
        for x, y, c in kps:
            if c >= KP_CONF_MIN:
                cv2.circle(frame, (int(x), int(y)), 3, C_INK, -1, cv2.LINE_AA)
    if label == "small":
        text = "person {:.2f} - too small for pose".format(score)
    elif label:
        text = "{} {}".format(label, "({:.0f} deg)".format(deg) if deg is not None else "")
    else:
        text = "person {:.2f}".format(score)
    cv2.putText(frame, text, (x1, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)


def draw_hud(frame, lines):
    """Small dark panel, top-left, so text stays readable over any scene."""
    import cv2

    pad, lh = 10, 26
    widest = max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0] for t, _ in lines)
    w = widest + pad * 2
    h = lh * len(lines) + pad
    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (8 + w, 8 + h), C_PANEL, -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
    for i, (text, col) in enumerate(lines):
        cv2.putText(frame, text, (8 + pad, 8 + pad + lh * i + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col or C_INK, 1, cv2.LINE_AA)


def mean(values):
    return sum(values) / len(values) if values else 0.0


def can_open_window() -> bool:
    """Can we actually create a GUI window on the current DISPLAY?

    Probed in a subprocess on purpose. When no X session is reachable, Qt does
    not raise - it prints "could not connect to display" and calls abort(), which
    kills the whole process. A try/except here would never run. Paying ~1 s for a
    throwaway child is worth not core-dumping in front of someone who just
    double-clicked an icon.
    """
    import subprocess

    probe = ("import cv2; cv2.namedWindow('probe', cv2.WINDOW_NORMAL); "
             "cv2.destroyAllWindows()")
    try:
        done = subprocess.run([sys.executable, "-c", probe],
                              capture_output=True, timeout=25)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["two-stage", "pose-only"], default="two-stage")
    ap.add_argument("--detector", default=str(DEFAULT_DETECTOR),
                    help="tier-1 engine (Ultralytics export; run by the lean runner)")
    ap.add_argument("--detector-classes", type=int, nargs="+", default=[0, 1],
                    help="detector classes that count as a person (VisDrone: 0 pedestrian, 1 people)")
    ap.add_argument("--pose", default=str(DEFAULT_POSE), help="tier-2 pose engine")
    ap.add_argument("--pose-every", type=int, default=5, help="run pose every N frames")
    ap.add_argument("--pose-max", type=int, default=3, help="at most this many people per pose pass")
    ap.add_argument("--pose-min-height", type=int, default=64,
                    help="people shorter than this (px) get no keypoints - too few pixels")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--source", help="play a folder of images or a video file instead of the camera")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--window-scale", type=float, default=0.6)
    ap.add_argument("--no-display", action="store_true")
    ap.add_argument("--record", help="write the annotated stream to this file")
    ap.add_argument("--max-frames", type=int, default=0, help="0 = run until quit")
    args = ap.parse_args()

    import cv2
    logging.getLogger("ultralytics").setLevel(logging.ERROR)
    from ultralytics import YOLO

    need = [args.pose] + ([args.detector] if args.mode == "two-stage" else [])
    for path in need:
        if not Path(path).exists():
            print("ERROR: model not found: " + path, file=sys.stderr)
            print("Run src/deploy/deploy_models.py first, or pass --detector / --pose.", file=sys.stderr)
            return 2

    images = None
    if args.source and Path(args.source).expanduser().is_dir():
        # A folder of stills, shown one per frame and looped - the aerial pipeline
        # without an aircraft.
        folder = Path(args.source).expanduser()
        images = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        if not images:
            print("ERROR: no images in " + str(folder), file=sys.stderr)
            return 2
        first = cv2.imread(str(images[0]))
        h, w = first.shape[:2]
        cap = None
        print("playing {} images from {}".format(len(images), folder))
    else:
        src = str(Path(args.source).expanduser()) if args.source else args.device
        print("opening " + src + " ...")
        cap = cv2.VideoCapture(src) if args.source else cv2.VideoCapture(src, cv2.CAP_V4L2)
        if not cap.isOpened():
            print("ERROR: could not open " + src, file=sys.stderr)
            if not args.source:
                print("Is the camera plugged in? Check with: v4l2-ctl --list-devices", file=sys.stderr)
            return 2
        if not args.source:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print("source negotiated {}x{}".format(w, h))

    print("loading models (TensorRT engine load takes a few seconds) ...")
    pose_model = YOLO(args.pose)
    detector = None
    if args.mode == "two-stage":
        from trt_yolo import TrtYolo
        detector = TrtYolo(args.detector, classes=args.detector_classes, conf=args.conf)
        print("  tier 1: {} ({}x{}, lean TensorRT)".format(Path(args.detector).name, detector.w, detector.h))
    print("  tier 2: {}".format(Path(args.pose).name))

    sampler = None
    try:
        from tegra_sampler import TegraSampler
        sampler = TegraSampler(interval_ms=1000)
        sampler.start()
    except Exception:  # noqa: BLE001 - telemetry is optional, never fatal
        sampler = None

    writer = None
    if args.record:
        writer = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"mp4v"), 20.0, (w, h))

    win = "RAPTOR - live perception"
    if not args.no_display and not can_open_window():
        print("could not open a window on DISPLAY={}".format(os.environ.get("DISPLAY", "<unset>")),
              file=sys.stderr)
        print("Falling back to headless output. To get the video window, log in on the "
              "Jetson's own monitor and launch it from there - an SSH session has no "
              "access to the console X server.", file=sys.stderr)
        args.no_display = True
    if not args.no_display:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, int(w * args.window_scale), int(h * args.window_scale))

    grab_hist = deque(maxlen=30)
    det_hist = deque(maxlen=30)
    pose_hist = deque(maxlen=10)
    fps_hist = deque(maxlen=30)
    tracked = []            # [box, label, deg, kps] from the last pose pass (two-stage)
    frames = 0
    t_prev = time.perf_counter()
    print("running - press q or ESC in the window to quit")

    try:
        while True:
            t0 = time.perf_counter()
            if images is not None:
                frame = cv2.imread(str(images[frames % len(images)]))
                ok = frame is not None
            else:
                ok, frame = cap.read()
                if not ok and args.source:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)     # loop a video file
                    ok, frame = cap.read()
            if not ok:
                print("frame grab failed; retrying", file=sys.stderr)
                time.sleep(0.05)
                continue
            grab_hist.append((time.perf_counter() - t0) * 1000.0)
            annotated = frame.copy()
            people = []     # (box, score, label, deg, kps)

            if args.mode == "two-stage":
                t1 = time.perf_counter()
                boxes, scores = detector(frame)
                det_hist.append((time.perf_counter() - t1) * 1000.0)

                if frames % args.pose_every == 0:
                    # Pose pass: the largest people first, the rest keep their last label.
                    t2 = time.perf_counter()
                    order = sorted(range(len(boxes)), key=lambda i: -(boxes[i][3] - boxes[i][1]))
                    fresh = []
                    for i in order[: args.pose_max]:
                        if boxes[i][3] - boxes[i][1] < args.pose_min_height:
                            continue
                        kps = pose_on_crop(pose_model, frame, boxes[i])
                        label, deg = posture_from_keypoints(kps) if kps else ("unknown", None)
                        fresh.append([boxes[i].tolist(), label, deg, kps])
                    tracked = fresh
                    pose_hist.append((time.perf_counter() - t2) * 1000.0)

                for b, s in zip(boxes.tolist(), scores.tolist()):
                    if b[3] - b[1] < args.pose_min_height:
                        people.append((b, s, "small", None, None))
                        continue
                    best = max(tracked, key=lambda t: iou(t[0], b), default=None)
                    if best is not None and iou(best[0], b) > 0.3:
                        # Carry the last pose, shifted with the box.
                        dx, dy = b[0] - best[0][0], b[1] - best[0][1]
                        kps = [(x + dx, y + dy, c) for x, y, c in best[3]] if best[3] else None
                        people.append((b, s, best[1], best[2], kps))
                    else:
                        people.append((b, s, None, None, None))
            else:
                t1 = time.perf_counter()
                res = pose_model.predict(frame, imgsz=960, classes=[0], conf=args.conf, verbose=False)[0]
                det_hist.append((time.perf_counter() - t1) * 1000.0)
                kdata = res.keypoints.data.tolist() if res.keypoints is not None else []
                for b, s, kps in zip(res.boxes.xyxy.tolist(), res.boxes.conf.tolist(), kdata):
                    label, deg = posture_from_keypoints(kps)
                    people.append((b, s, label, deg, kps))

            for b, s, label, deg, kps in people:
                draw_person(annotated, b, s, label, deg, kps)

            now = time.perf_counter()
            fps_hist.append(1.0 / max(1e-6, now - t_prev))
            t_prev = now
            frames += 1

            postures = [p[2] for p in people if p[2] not in (None, "small")]
            n_small = sum(1 for p in people if p[2] == "small")
            budget_col = C_OK if mean(det_hist) <= FRAME_BUDGET_MS else C_ALARM
            if args.mode == "two-stage":
                title = "RAPTOR live  |  {} (lean TensorRT)  +  pose on crops every {} frames".format(
                    Path(args.detector).stem, args.pose_every)
                timing = "FPS {:5.1f}   detect {:5.1f} ms   pose pass {:5.1f} ms".format(
                    mean(fps_hist), mean(det_hist), mean(pose_hist))
            else:
                title = "RAPTOR live  |  {} on the whole frame (pose-only mode)".format(Path(args.pose).stem)
                timing = "FPS {:5.1f}   grab {:5.1f} ms   infer {:5.1f} ms".format(
                    mean(fps_hist), mean(grab_hist), mean(det_hist))
            hud = [
                (title, C_INK),
                (timing, budget_col),
                ("people: {}{}{}".format(len(people),
                                         "   posture: " + ", ".join(postures) if postures else "",
                                         "   ({} too small for pose)".format(n_small) if n_small else ""),
                 C_ALARM if "LYING" in postures else C_INK),
            ]
            if sampler:
                s = sampler.summary()
                if s.get("board_power_mean_w"):
                    hud.append(("board {:.1f} W   {:.0f} C".format(
                        s["board_power_mean_w"], s.get("temp_max_c", 0)), C_INK))
            hud.append(("posture is geometric, image-vertical (no IMU) - not flight tier 2", C_WARN))
            draw_hud(annotated, hud)

            if writer is not None:
                # An image folder can mix sizes; a video writer silently drops
                # any frame that is not the size it was opened with.
                writer.write(annotated if annotated.shape[:2] == (h, w) else cv2.resize(annotated, (w, h)))

            if not args.no_display:
                cv2.imshow(win, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            elif frames % 30 == 0:
                print("frame {}: {} person(s), {:.1f} FPS, detect {:.1f} ms{}, postures={}".format(
                    frames, len(people), mean(fps_hist), mean(det_hist),
                    ", pose pass {:.1f} ms".format(mean(pose_hist)) if pose_hist else "", postures))

            if args.max_frames and frames >= args.max_frames:
                break
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        if sampler:
            sampler.stop()
        if cap is not None:
            cap.release()
        if writer is not None:
            writer.release()
        if not args.no_display:
            cv2.destroyAllWindows()

    print("\nstopped after {} frames".format(frames))
    if fps_hist:
        print("last-30-frame average: {:.1f} FPS, detect {:.1f} ms".format(mean(fps_hist), mean(det_hist)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
