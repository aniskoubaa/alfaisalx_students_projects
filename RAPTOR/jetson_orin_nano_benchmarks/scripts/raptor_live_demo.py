#!/usr/bin/env python3
"""RAPTOR live demo - camera -> TensorRT pose engine -> annotated window.

Runs the deployed tier 1+2 model on the live camera and draws what the aircraft
would see: person boxes, 17 COCO keypoints, a geometric posture estimate, and a
HUD carrying the numbers that matter (frame budget, FPS, board power).

    python3 raptor_live_demo.py                      # defaults to ~/raptor-deploy
    python3 raptor_live_demo.py --no-display         # headless, prints to stdout
    python3 raptor_live_demo.py --record out.mp4     # also write a video

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
sys.path.insert(0, str(SCRIPT_DIR))

# COCO keypoint indices used for the torso vector.
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 5, 6, 11, 12
KP_CONF_MIN = 0.35

# Colours (BGR). Status palette: green good, amber caution, red alarming.
C_OK = (76, 175, 80)
C_WARN = (0, 180, 240)
C_ALARM = (60, 60, 220)
C_INK = (245, 245, 245)
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
    ap.add_argument("--model", default=str(Path.home() / "raptor-deploy/pose/yolo11s-pose.engine"))
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--window-scale", type=float, default=0.6)
    ap.add_argument("--no-display", action="store_true")
    ap.add_argument("--record", help="write the annotated stream to this file")
    ap.add_argument("--max-frames", type=int, default=0, help="0 = run until quit")
    args = ap.parse_args()

    import cv2
    logging.getLogger("ultralytics").setLevel(logging.ERROR)
    from ultralytics import YOLO

    if not Path(args.model).exists():
        print("ERROR: model not found: " + args.model, file=sys.stderr)
        print("Run deploy_models.py first, or pass --model.", file=sys.stderr)
        return 2

    print("opening " + args.device + " ...")
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        print("ERROR: could not open " + args.device, file=sys.stderr)
        print("Is the camera plugged in? Check with: v4l2-ctl --list-devices", file=sys.stderr)
        return 2
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print("camera negotiated {}x{}".format(w, h))

    print("loading " + Path(args.model).name + " (TensorRT engine load takes a few seconds) ...")
    model = YOLO(args.model)

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

    win = "RAPTOR - live perception (tier 1+2)"
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
    infer_hist = deque(maxlen=30)
    fps_hist = deque(maxlen=30)
    frames = 0
    t_prev = time.perf_counter()
    print("running - press q or ESC in the window to quit")

    try:
        while True:
            t0 = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                print("frame grab failed; retrying", file=sys.stderr)
                time.sleep(0.05)
                continue
            grab_ms = (time.perf_counter() - t0) * 1000.0

            t1 = time.perf_counter()
            res = model.predict(frame, imgsz=args.imgsz, classes=[0],
                                conf=args.conf, verbose=False)
            infer_ms = (time.perf_counter() - t1) * 1000.0

            annotated = res[0].plot()
            people = len(res[0].boxes)

            postures = []
            kp = res[0].keypoints
            if kp is not None and kp.data is not None:
                for person_kp in kp.data:
                    as_list = person_kp.tolist()
                    label, deg = posture_from_keypoints(as_list)
                    postures.append(label)
                    if deg is not None:
                        sh = midpoint(as_list, L_SHOULDER, R_SHOULDER)
                        if sh:
                            if label == "LYING":
                                col = C_ALARM
                            elif label == "leaning/sitting":
                                col = C_WARN
                            else:
                                col = C_OK
                            cv2.putText(annotated,
                                        "{} ({:.0f} deg)".format(label, deg),
                                        (int(sh[0]) - 40, max(20, int(sh[1]) - 40)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2, cv2.LINE_AA)

            now = time.perf_counter()
            fps = 1.0 / max(1e-6, now - t_prev)
            t_prev = now
            grab_hist.append(grab_ms)
            infer_hist.append(infer_ms)
            fps_hist.append(fps)
            frames += 1

            budget_col = C_OK if mean(infer_hist) <= FRAME_BUDGET_MS else C_ALARM
            alarming = any(p == "LYING" for p in postures)

            hud = [
                ("RAPTOR live  |  {}  @{}  TensorRT FP16".format(
                    Path(args.model).name, args.imgsz), C_INK),
                ("FPS {:5.1f}   grab {:5.1f} ms   infer {:5.1f} ms".format(
                    mean(fps_hist), mean(grab_hist), mean(infer_hist)), budget_col),
                ("people: {}".format(people)
                 + ("   posture: " + ", ".join(postures) if postures else ""),
                 C_ALARM if alarming else C_INK),
            ]
            if sampler:
                s = sampler.summary()
                if s.get("board_power_mean_w"):
                    hud.append(("board {:.1f} W   {:.0f} C".format(
                        s["board_power_mean_w"], s.get("temp_max_c", 0)), C_INK))
            hud.append(("posture is geometric, image-vertical (no IMU) - not flight tier 2", C_WARN))
            draw_hud(annotated, hud)

            if writer is not None:
                writer.write(annotated)

            if not args.no_display:
                cv2.imshow(win, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            elif frames % 30 == 0:
                print("frame {}: {} person(s), {:.1f} FPS, infer {:.1f} ms, postures={}".format(
                    frames, people, mean(fps_hist), mean(infer_hist), postures))

            if args.max_frames and frames >= args.max_frames:
                break
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        if sampler:
            sampler.stop()
        cap.release()
        if writer is not None:
            writer.release()
        if not args.no_display:
            cv2.destroyAllWindows()

    print("\nstopped after {} frames".format(frames))
    if fps_hist:
        print("last-30-frame average: {:.1f} FPS, infer {:.1f} ms".format(
            mean(fps_hist), mean(infer_hist)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
