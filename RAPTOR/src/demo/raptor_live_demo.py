#!/usr/bin/env python3
"""RAPTOR live demo - camera -> people -> tracks -> posture -> annotated window.

Two modes:

  bench   (default) for people near a desk webcam. The COCO pose model on the
          whole frame finds each person and their 17 keypoints; a tracker holds
          one steady box per person; posture comes from the legs, smoothed over
          time; and the VLM double-checks each person's posture about once a
          second in the background.
  aerial  the flight pipeline: the aerial-trained detector (YOLO26s on VisDrone)
          on every frame, the tracker, and pose on crops of each tracked person
          every few frames. Meant for footage from altitude (--source). Pointed
          at a room, it misses people close to the camera and mistakes chairs
          for seated people (measured 2026-09-29) - not what it was trained for.

    python3 raptor_live_demo.py                        # bench, camera found automatically
    python3 raptor_live_demo.py --mode aerial --source ~/raptor-data/visdrone-person/images/val
    python3 raptor_live_demo.py --no-vlm               # without the VLM check
    python3 raptor_live_demo.py --no-display --max-frames 300 --stats
    python3 raptor_live_demo.py --record out.mp4

Press q or ESC to quit.

What changed on 2026-09-29, and why (each measured on the bench camera, see
docs/14): one seated person was counted as 0 to 5 people, labelled "standing",
and the video ran at ~17 FPS.
  * duplicates and flicker   -> person_tracker.py: nested boxes removed, ByteTrack,
                                a person is shown after 3 frames and held through
                                short misses;
  * sitting called standing  -> posture.py: posture from the legs, not the torso
                                alone; "legs hidden" instead of a guess; a vote
                                over recent frames; plus the VLM check;
  * 17 FPS                   -> live_camera.py: JPEG decoding (22 ms per 1080p
                                frame) moved off the inference loop; the
                                camera's low-light frame-rate drop switched off;
                                the HUD blends only its own panel; a smaller
                                pose engine (384x640) for the bench;
  * "crashed"                -> the webcam dropped off USB and came back as
                                /dev/video1; the camera is now found by its USB
                                path and re-opened automatically. A second copy
                                of the demo can no longer fight the first for it.

POSTURE CAVEAT: angles are measured against image vertical. Right for a fixed
camera, wrong once an aircraft banks - the flight version needs the IMU attitude
(docs/02). The HUD says so.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from collections import Counter, deque
from pathlib import Path

# The installed torch wheel has no sm_87 kernels and says so on every CUDA init.
# Real and documented (README "environment traps"), but not news; silenced here
# only - the benchmark scripts still surface it.
warnings.filterwarnings("ignore", message=r".*compute capability.*")
warnings.filterwarnings("ignore", message=r".*No published PyTorch CUDA builds.*")

SCRIPT_DIR = Path(__file__).resolve().parent
# Shared helpers live in src/common. This file's own folder is searched too, so a
# script copied on its own next to them still works.
for _path in (SCRIPT_DIR, SCRIPT_DIR.parent / "common"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from posture import (KP_CONF_MIN, LYING, SITTING, STANDING, UNKNOWN,  # noqa: E402
                     PostureVote, posture_from_keypoints)

HOME = Path.home()
DEPLOY = HOME / "raptor-deploy"
DEFAULT_DETECTOR = DEPLOY / "detector" / "visdrone-yolo26s-736x1280.engine"
DEFAULT_POSE = DEPLOY / "pose" / "yolo26s-pose-960.engine"
# Smaller engine of the same model for the bench (people are large there).
BENCH_POSE = DEPLOY / "pose_bench" / "yolo26s-pose-384x640.engine"
DEFAULT_VLM = DEPLOY / "vlm" / "Qwen3-VL-2B-Instruct"
LOCK_FILE = "/tmp/raptor_live_demo.lock"

SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]

# Colours (BGR). Status palette: green good, amber caution, red alarming.
C_OK = (76, 175, 80)
C_WARN = (0, 180, 240)
C_ALARM = (60, 60, 220)
C_INK = (245, 245, 245)
C_BOX = (235, 170, 40)
C_MUTED = (170, 170, 170)
C_PANEL = (30, 30, 30)
FRAME_BUDGET_MS = 33.0


def posture_colour(label):
    return {LYING: C_ALARM, "lying": C_ALARM, SITTING: C_WARN, STANDING: C_OK}.get(label, C_MUTED)


def engine_imgsz(path):
    """Input size [h, w] stored in an Ultralytics .engine's metadata header, or None."""
    try:
        with open(path, "rb") as f:
            n = int.from_bytes(f.read(4), "little")
            meta = json.loads(f.read(n).decode("utf-8"))
        s = meta.get("imgsz")
        return [int(s[0]), int(s[1])] if isinstance(s, (list, tuple)) else [int(s), int(s)]
    except (OSError, ValueError, UnicodeDecodeError, TypeError, KeyError, IndexError):
        return None


def crop(frame, box, margin):
    h0, w0 = frame.shape[:2]
    x1, y1, x2, y2 = box
    mw, mh = (x2 - x1) * margin, (y2 - y1) * margin
    cx1, cy1 = int(max(0, x1 - mw)), int(max(0, y1 - mh))
    cx2, cy2 = int(min(w0, x2 + mw)), int(min(h0, y2 + mh))
    return frame[cy1:cy2, cx1:cx2], cx1, cy1


def pose_on_crop(pose_model, imgsz, frame, box):
    """Keypoints (frame pixels) of the person the detector boxed, or None.

    The crop gets 25 % context on each side so limbs at the box edge survive; if
    the pose model finds several people in it, the one nearest the centre is the
    one the detector meant.
    """
    c, ox, oy = crop(frame, box, 0.25)
    if c.size == 0:
        return None
    res = pose_model.predict(c, imgsz=imgsz, conf=0.25, verbose=False)[0]
    if res.keypoints is None or len(res.boxes) == 0:
        return None
    ccx, ccy = c.shape[1] / 2, c.shape[0] / 2
    d = [((b[0] + b[2]) / 2 - ccx) ** 2 + ((b[1] + b[3]) / 2 - ccy) ** 2 for b in res.boxes.xyxy.tolist()]
    k = d.index(min(d))
    return [(x + ox, y + oy, s) for x, y, s in res.keypoints.data[k].tolist()]


def draw_person(frame, box, text, colour, kps, held):
    import cv2

    x1, y1, x2, y2 = (int(v) for v in box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 1 if held else 2)
    if kps is not None and not held:
        for a, b in SKELETON:
            if kps[a][2] >= KP_CONF_MIN and kps[b][2] >= KP_CONF_MIN:
                cv2.line(frame, (int(kps[a][0]), int(kps[a][1])), (int(kps[b][0]), int(kps[b][1])),
                         colour, 2, cv2.LINE_AA)
        for x, y, c in kps:
            if c >= KP_CONF_MIN:
                cv2.circle(frame, (int(x), int(y)), 3, C_INK, -1, cv2.LINE_AA)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    ty = max(th + 6, y1 - 6)
    cv2.rectangle(frame, (x1, ty - th - 5), (x1 + tw + 6, ty + 4), C_PANEL, -1)
    cv2.putText(frame, text, (x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2, cv2.LINE_AA)


def draw_hud(frame, lines):
    """Dark panel, top-left. Only the panel's own pixels are blended - blending
    the whole 1080p frame cost several milliseconds per frame."""
    import cv2

    pad, lh = 10, 26
    widest = max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0] for t, _ in lines)
    x2 = min(frame.shape[1], 8 + widest + pad * 2)
    y2 = min(frame.shape[0], 8 + lh * len(lines) + pad)
    roi = frame[8:y2, 8:x2]
    roi[:] = (roi * 0.35 + C_PANEL[0] * 0.65).astype(roi.dtype)
    for i, (text, col) in enumerate(lines):
        cv2.putText(frame, text, (8 + pad, 8 + pad + lh * i + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col or C_INK, 1, cv2.LINE_AA)


def mean(values):
    return sum(values) / len(values) if values else 0.0


def can_open_window() -> bool:
    """Can we create a GUI window on the current DISPLAY?

    Probed in a subprocess on purpose: with no reachable X server, Qt prints
    "could not connect to display" and calls abort(), killing the process - a
    try/except would never run.
    """
    import subprocess

    probe = "import cv2; cv2.namedWindow('probe', cv2.WINDOW_NORMAL); cv2.destroyAllWindows()"
    try:
        return subprocess.run([sys.executable, "-c", probe], capture_output=True, timeout=25).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def single_instance():
    """Hold an exclusive lock for the life of the process; None if another demo has it.

    Two copies (a double double-click) fight over the one camera: the second
    gets no frames and looks frozen, the first stutters.
    """
    import fcntl

    f = open(LOCK_FILE, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.write(str(os.getpid()))
    f.flush()
    return f


class FileSource:
    """A folder of images (looped, one per frame) or a video file (looped),
    with the same read() as LiveCamera."""

    def __init__(self, path):
        import cv2

        self.cv2 = cv2
        p = Path(path).expanduser()
        self.images = None
        self.cap = None
        if p.is_dir():
            self.images = sorted(q for q in p.iterdir() if q.suffix.lower() in (".jpg", ".jpeg", ".png"))
            if not self.images:
                raise SystemExit("ERROR: no images in " + str(p))
            h, w = cv2.imread(str(self.images[0])).shape[:2]
        else:
            self.cap = cv2.VideoCapture(str(p))
            if not self.cap.isOpened():
                raise SystemExit("ERROR: could not open " + str(p))
            w, h = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.size = (w, h)
        self.status, self.reconnects, self.device = "ok", 0, str(p)
        self.n = 0

    def start(self, timeout=0):
        return True

    def read(self, last_seq=0, timeout=1.0):
        if self.images is not None:
            frame = self.cv2.imread(str(self.images[self.n % len(self.images)]))
        else:
            ok, frame = self.cap.read()
            if not ok:
                self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
        self.n += 1
        return frame, self.n

    def stop(self):
        if self.cap is not None:
            self.cap.release()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["bench", "aerial", "pose-only", "two-stage"], default="bench",
                    help="bench (people near the camera) or aerial (the flight pipeline). "
                         "pose-only and two-stage are the old names.")
    ap.add_argument("--detector", default=str(DEFAULT_DETECTOR), help="aerial mode: tier-1 engine (lean runner)")
    ap.add_argument("--detector-classes", type=int, nargs="+", default=[0, 1],
                    help="aerial mode: classes that count as a person (VisDrone: 0 pedestrian, 1 people)")
    ap.add_argument("--pose", help="pose engine (default: the 384x640 engine for bench if deployed, else the 960 one)")
    ap.add_argument("--pose-every", type=int, default=5, help="aerial mode: pose on crops every N frames")
    ap.add_argument("--pose-max", type=int, default=3, help="aerial mode: at most this many people per pose pass")
    ap.add_argument("--pose-min-height", type=int, default=64,
                    help="aerial mode: people shorter than this (px) get no keypoints")
    ap.add_argument("--vlm", default=str(DEFAULT_VLM), help="VLM for the posture double-check")
    ap.add_argument("--no-vlm", action="store_true", help="do not load the VLM")
    ap.add_argument("--vlm-every", type=float, default=1.0, help="seconds between VLM questions")
    ap.add_argument("--device", default="auto", help="camera node, or auto (first USB camera)")
    ap.add_argument("--source", help="play a folder of images or a video file instead of the camera")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--focus", type=int, default=None,
                    help="lock the camera's focus here (C922: 0 far ... 250 near) instead of autofocus")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--window-scale", type=float, default=0.6)
    ap.add_argument("--no-display", action="store_true")
    ap.add_argument("--record", help="write the annotated stream to this file")
    ap.add_argument("--max-frames", type=int, default=0, help="0 = run until quit")
    ap.add_argument("--stats", action="store_true", help="print a JSON summary on exit (counts, postures, FPS)")
    args = ap.parse_args()
    mode = {"pose-only": "bench", "two-stage": "aerial"}.get(args.mode, args.mode)

    import cv2
    import numpy as np
    logging.getLogger("ultralytics").setLevel(logging.ERROR)
    from ultralytics import YOLO
    from person_tracker import PersonTracker

    pose_path = args.pose or str(BENCH_POSE if mode == "bench" and BENCH_POSE.exists() else DEFAULT_POSE)
    need = [pose_path] + ([args.detector] if mode == "aerial" else [])
    for path in need:
        if not Path(path).exists():
            print("ERROR: model not found: " + path, file=sys.stderr)
            print("Run src/deploy/deploy_models.py first, or pass --detector / --pose.", file=sys.stderr)
            return 2

    lock = None
    if not args.source:
        lock = single_instance()
        if lock is None:
            print("ERROR: the RAPTOR demo is already running (it holds the camera).", file=sys.stderr)
            print("Close its window first - or look for it behind other windows.", file=sys.stderr)
            return 3

    if args.source:
        src = FileSource(args.source)
        print("playing " + src.device)
    else:
        from live_camera import LiveCamera
        src = LiveCamera(args.device, args.width, args.height, args.fourcc, args.fps, focus=args.focus)
        print("looking for the camera ...")
        if not src.start(timeout=10):
            print("ERROR: no frames from any camera ({}).".format(src.status), file=sys.stderr)
            print("Is it plugged in? Check with: v4l2-ctl --list-devices", file=sys.stderr)
            src.stop()
            return 2
        print("camera {} at {}x{}".format(src.device, *src.size))
    w, h = src.size

    print("loading models (TensorRT engine load takes a few seconds) ...")
    pose_model = YOLO(pose_path, task="pose")
    pose_imgsz = engine_imgsz(pose_path) or [960, 960]
    detector = None
    if mode == "aerial":
        from trt_yolo import TrtYolo
        detector = TrtYolo(args.detector, classes=args.detector_classes, conf=args.conf)
        print("  detector: {} ({}x{}, lean TensorRT)".format(Path(args.detector).name, detector.w, detector.h))
    print("  pose    : {} ({}x{})".format(Path(pose_path).name, *pose_imgsz))
    tracker = PersonTracker()
    votes = PostureVote(window=7)
    vlm = None
    if not args.no_vlm and Path(args.vlm).exists():
        from vlm_posture import VlmPosture
        vlm = VlmPosture(args.vlm)
        print("  VLM     : {} (loading in the background)".format(Path(args.vlm).name))

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
        print("could not open a window on DISPLAY={}".format(os.environ.get("DISPLAY", "<unset>")), file=sys.stderr)
        print("Falling back to headless output. For the video window, launch from the "
              "Jetson's own desktop (or VNC) - an SSH session cannot reach it.", file=sys.stderr)
        args.no_display = True
    dw, dh = int(w * args.window_scale), int(h * args.window_scale)
    if not args.no_display:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, dw, dh)

    infer_hist, pose_hist, fps_hist = deque(maxlen=30), deque(maxlen=10), deque(maxlen=30)
    kps_of = {}                 # track id -> (keypoints, box they were measured in)
    stats = {"counts": Counter(), "changes": 0, "postures": Counter(), "vlm": Counter(), "fps": []}
    last_count, last_vlm_t = None, 0.0
    frames, seq = 0, 0
    t_prev = time.perf_counter()
    print("running - press q or ESC in the window to quit")

    try:
        while True:
            frame, new_seq = src.read(seq, timeout=1.0)
            if frame is None:
                if not args.no_display:     # keep the window alive and say why it is still
                    blank = np.full((dh, dw, 3), 20, np.uint8)
                    cv2.putText(blank, src.status, (20, dh // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, C_WARN, 2)
                    cv2.imshow(win, blank)
                    if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                        break
                continue
            seq = new_seq

            t1 = time.perf_counter()
            if mode == "bench":
                res = pose_model.predict(frame, imgsz=pose_imgsz, classes=[0], conf=args.conf, iou=0.5,
                                         verbose=False)[0]
                boxes = res.boxes.xyxy.cpu().numpy()
                scores = res.boxes.conf.cpu().numpy()
                kps_all = res.keypoints.data.cpu().numpy() if res.keypoints is not None else None
                tracks = tracker.update(boxes, scores)
                for t in tracks:
                    if t.det_index is not None and kps_all is not None:
                        k = kps_all[t.det_index].tolist()
                        kps_of[t.id] = (k, t.box)
                        votes.add(t.id, posture_from_keypoints(k)[0])
            else:
                boxes, scores = detector(frame)
                tracks = tracker.update(boxes, scores)
                if frames % args.pose_every == 0:
                    t2 = time.perf_counter()
                    live = [t for t in tracks if t.det_index is not None
                            and t.box[3] - t.box[1] >= args.pose_min_height]
                    for t in sorted(live, key=lambda t: -(t.box[3] - t.box[1]))[: args.pose_max]:
                        k = pose_on_crop(pose_model, pose_imgsz, frame, t.box)
                        if k:
                            kps_of[t.id] = (k, t.box)
                        votes.add(t.id, posture_from_keypoints(k)[0] if k else UNKNOWN)
                    pose_hist.append((time.perf_counter() - t2) * 1000.0)
            infer_hist.append((time.perf_counter() - t1) * 1000.0)

            live_ids = {t.id for t in tracks}
            votes.forget(live_ids)
            for k in [k for k in kps_of if k not in live_ids]:
                del kps_of[k]

            # VLM: one person per question, the one whose answer is oldest, and
            # only people whose torso is in view (an arm alone gets a guess).
            if vlm is not None:
                vlm.forget(live_ids)
                now = time.monotonic()
                if vlm.ready and not vlm.busy and now - last_vlm_t >= args.vlm_every:
                    cands = [t for t in tracks if t.det_index is not None
                             and votes.get(t.id) not in (None, UNKNOWN)]
                    cands.sort(key=lambda t: vlm.answers.get(t.id, ("", 0.0))[1])
                    for t in cands:
                        c, _, _ = crop(frame, t.box, 0.15)
                        if vlm.submit(t.id, c):
                            last_vlm_t = now
                            break

            annotated = frame
            n_lying = 0
            shown = []
            for t in tracks:
                geo = votes.get(t.id)
                word = vlm.answer(t.id) if vlm is not None else None
                if mode == "aerial" and t.box[3] - t.box[1] < args.pose_min_height:
                    text, colour = "#{} person - too small for pose".format(t.id), C_BOX
                else:
                    text = "#{} {}{}".format(t.id, geo or "person", " | VLM: " + word if word else "")
                    lying = geo == LYING or word == "lying"
                    n_lying += lying
                    colour = C_ALARM if lying else posture_colour(word or geo)
                k, kbox = kps_of.get(t.id, (None, None))
                if k is not None and kbox is not None and kbox != t.box:
                    dx, dy = t.box[0] - kbox[0], t.box[1] - kbox[1]      # carry keypoints with the box
                    k = [(x + dx, y + dy, s) for x, y, s in k]
                draw_person(annotated, t.box, text, colour, k, held=t.det_index is None)
                shown.append((geo, word))
                stats["postures"][geo or "none"] += 1
                if word:
                    stats["vlm"][word] += 1

            now = time.perf_counter()
            fps_hist.append(1.0 / max(1e-6, now - t_prev))
            t_prev = now
            frames += 1
            n = len(tracks)
            stats["counts"][n] += 1
            if last_count is not None and n != last_count:
                stats["changes"] += 1
            last_count = n

            if mode == "bench":
                title = "RAPTOR live  |  bench: {} + tracker + VLM check".format(Path(pose_path).stem)
                timing = "FPS {:5.1f}   pose {:5.1f} ms".format(mean(fps_hist), mean(infer_hist))
            else:
                title = "RAPTOR live  |  aerial: {} + tracker + pose every {} frames".format(
                    Path(args.detector).stem, args.pose_every)
                timing = "FPS {:5.1f}   detect+track {:5.1f} ms   pose pass {:5.1f} ms".format(
                    mean(fps_hist), mean(infer_hist), mean(pose_hist))
            hud = [(title, C_INK),
                   (timing, C_OK if mean(infer_hist) <= FRAME_BUDGET_MS else C_ALARM),
                   ("people: {}{}".format(n, "   LYING: {}".format(n_lying) if n_lying else ""),
                    C_ALARM if n_lying else C_INK)]
            if vlm is not None:
                lat = [a[2] for a in vlm.answers.values()]
                if not vlm.ready:
                    vlm_line = vlm.state
                elif lat:
                    vlm_line = "VLM posture check: {:.2f} s per person".format(mean(lat))
                else:
                    vlm_line = "VLM posture check: ready"
                hud.append((vlm_line, C_INK))
            if src.status != "ok" or src.reconnects:
                hud.append(("camera: {}  (reconnected {}x)".format(src.status, src.reconnects), C_WARN))
            if sampler:
                s = sampler.summary()
                if s.get("board_power_mean_w"):
                    hud.append(("board {:.1f} W   {:.0f} C".format(s["board_power_mean_w"], s.get("temp_max_c", 0)),
                                C_INK))
            hud.append(("posture uses image vertical (no IMU) - bench only, not flight", C_WARN))
            draw_hud(annotated, hud)

            if writer is not None:
                writer.write(annotated if annotated.shape[:2] == (h, w) else cv2.resize(annotated, (w, h)))
            if not args.no_display:
                disp = annotated if args.window_scale >= 1 else cv2.resize(annotated, (dw, dh))
                cv2.imshow(win, disp)
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                    break
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            elif frames % 30 == 0:
                print("frame {}: {} people {}, {:.1f} FPS, infer {:.1f} ms".format(
                    frames, n, shown, mean(fps_hist), mean(infer_hist)))
            if frames > 30:
                stats["fps"].append(fps_hist[-1])
            if args.max_frames and frames >= args.max_frames:
                break
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        vlm_done = True
        if sampler:
            sampler.stop()
        if vlm is not None:
            vlm_done = vlm.stop()
        src.stop()
        if writer is not None:
            writer.release()
        if not args.no_display:
            cv2.destroyAllWindows()

    print("\nstopped after {} frames".format(frames))
    if fps_hist:
        print("last-30-frame average: {:.1f} FPS, inference {:.1f} ms".format(mean(fps_hist), mean(infer_hist)))
    if args.stats:
        fps = sorted(stats["fps"])
        print(json.dumps({
            "mode": mode, "pose_engine": Path(pose_path).name, "frames": frames,
            "fps_mean": round(mean(fps), 1), "fps_p5": round(fps[len(fps) // 20], 1) if fps else None,
            "infer_ms_last30": round(mean(infer_hist), 1),
            "people_count_frames": dict(sorted(stats["counts"].items())),
            "people_count_changes": stats["changes"],
            "posture_labels": dict(stats["postures"]), "vlm_answers": dict(stats["vlm"]),
            "vlm_seconds": round(mean([a[2] for a in vlm.answers.values()]), 2) if vlm and vlm.answers else None,
            "camera": getattr(src, "device", None), "camera_reconnects": src.reconnects,
        }, indent=1))
    if not vlm_done:
        # The VLM thread is still inside the model (quit while it was loading).
        # A normal interpreter exit would abort with a core dump; everything of
        # ours is already closed, so leave directly.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
