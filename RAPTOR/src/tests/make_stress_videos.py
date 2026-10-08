#!/usr/bin/env python3
"""Build videos where people appear SUDDENLY, to stress the live demo.

Reported 2026-10-05: "sometimes, if something shows up suddenly, it crashes".
Every earlier test of the demo used still images or a calm room, so the case
was never exercised. These videos make it repeatable. Each one is 1920x1080
(the Arducam B0498's 60 FPS mode) and is built from:

  * an EMPTY version of the scene - the per-pixel median of the clip for the
    street video (walkers vanish, the street stays), or a heavy blur of the
    aerial image (the scene's colours stay, no person survives as a shape);
  * hard cuts from empty to crowded and back;
  * flicker - alternating empty / crowded EVERY frame;
  * jump cuts - every frame from a different moment, so people teleport;
  * a sudden brightness flash (a light switched on, auto-exposure catching up).

    ~/raptor-venv/bin/python make_stress_videos.py \\
        --street ~/raptor-data/video/vtest.avi \\
        --aerial ~/raptor-data/visdrone-person/images/val \\
        --out ~/raptor-data/video

Writes stress_street_1080p.mp4 and stress_aerial_1080p.mp4 (MPEG-4, 30 fps).
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

W, H = 1920, 1080


def to_1080p(img):
    """Centre-crop to 16:9, then resize to 1920x1080 - no stretching."""
    import cv2

    h, w = img.shape[:2]
    if w / h > W / H:
        nw = int(h * W / H)
        x = (w - nw) // 2
        img = img[:, x:x + nw]
    else:
        nh = int(w * H / W)
        y = (h - nh) // 2
        img = img[y:y + nh]
    return cv2.resize(img, (W, H), interpolation=cv2.INTER_LINEAR)


def flash(img, k):
    """Frame k of a 12-frame flash: blown out at once, then exposure recovering."""
    import numpy as np

    gain = 3.2 - 2.2 * min(1.0, k / 11)
    return np.clip(img.astype(np.float32) * gain + 40 * (1 - k / 11), 0, 255).astype(np.uint8)


def writer(path):
    import cv2

    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (W, H))
    if not w.isOpened():
        raise SystemExit("cannot write " + str(path))
    return w


def street(src, out, rng):
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(src))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(to_1080p(f))
    if not frames:
        raise SystemExit("no frames in " + str(src))
    sample = np.stack(frames[:: max(1, len(frames) // 60)])
    empty = np.median(sample, axis=0).astype(np.uint8)        # walkers vanish
    n = len(frames)

    seq = []                                                  # (label, frame)
    seq += [("empty", empty)] * 60
    seq += [("walk", f) for f in frames[0:150]]
    seq += [("empty", empty)] * 30
    seq += [("cut-in", f) for f in frames[400:500]]           # crowd appears at once
    for i in range(90):                                       # flicker every frame
        seq.append(("flicker", frames[300 + i] if i % 2 else empty))
    for _ in range(120):                                      # jump cuts
        seq.append(("jump", frames[rng.randrange(n)]))
    seq += [("flash", flash(frames[620], k)) for k in range(12)]
    seq += [("empty", empty)] * 30
    seq += [("walk", f) for f in frames[600:n]]

    w = writer(out)
    for _, f in seq:
        w.write(f)
    w.release()
    return len(seq)


def aerial(src_dir, out, rng, count=40):
    import cv2

    imgs = sorted(p for p in Path(src_dir).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not imgs:
        raise SystemExit("no images in " + str(src_dir))
    pick = rng.sample(imgs, min(count, len(imgs)))
    scenes = []
    for p in pick:
        im = cv2.imread(str(p))
        if im is None:
            continue
        sharp = to_1080p(im)
        empty = cv2.GaussianBlur(sharp, (0, 0), 25)           # colours stay, people do not
        scenes.append((sharp, empty))

    w = writer(out)
    total = 0
    for i, (sharp, empty) in enumerate(scenes):
        frames = [empty] * 15 + [sharp] * 20                  # empty, then everyone at once
        frames += [sharp if k % 2 else empty for k in range(10)]   # flicker
        if i % 8 == 7:
            frames += [flash(sharp, k) for k in range(12)]
        for f in frames:
            w.write(f)
        total += len(frames)
    for _ in range(90):                                       # jump cuts between scenes
        w.write(scenes[rng.randrange(len(scenes))][0])
        total += 1
    w.release()
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--street", default=str(Path.home() / "raptor-data/video/vtest.avi"))
    ap.add_argument("--aerial", default=str(Path.home() / "raptor-data/visdrone-person/images/val"))
    ap.add_argument("--out", default=str(Path.home() / "raptor-data/video"))
    ap.add_argument("--seed", type=int, default=20261005)
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    n = street(Path(args.street).expanduser(), out / "stress_street_1080p.mp4", rng)
    print("stress_street_1080p.mp4: {} frames".format(n))
    n = aerial(Path(args.aerial).expanduser(), out / "stress_aerial_1080p.mp4", rng)
    print("stress_aerial_1080p.mp4: {} frames".format(n))


if __name__ == "__main__":
    main()
