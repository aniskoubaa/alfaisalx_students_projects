#!/usr/bin/env python3
"""Cut person crops from the aerial proxy set, the way the pipeline would.

03-scene-understanding-vlm.md is explicit that the VLM is never handed the raw
frame: it gets the tracked person's box expanded ~30% for context. These crops
reproduce that, so the VLM benchmark measures the input the real system produces.

Crops are taken largest-first. That is deliberate and it is a limitation: at the
altitudes VisDrone was shot from, most people are 10-30 px tall, and a crop that
small carries almost no describable detail. Taking the largest gives each model
its best case, so a poor score is a genuine model result rather than an artefact
of feeding it mush.

    python3 make_person_crops.py --dataset ~/raptor-data/visdrone-person \
        --split val --count 24 --out ~/raptor-data/person-crops
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, help="root containing images/<split> and labels/<split>")
    ap.add_argument("--split", default="val")
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--margin", type=float, default=0.30, help="context margin, per doc 03")
    ap.add_argument("--min-px", type=int, default=48, help="skip crops shorter than this")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from PIL import Image

    root = Path(args.dataset)
    img_dir = root / "images" / args.split
    lbl_dir = root / "labels" / args.split
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for lbl in sorted(lbl_dir.glob("*.txt")):
        img = next((img_dir / (lbl.stem + ext) for ext in (".jpg", ".png", ".jpeg")
                    if (img_dir / (lbl.stem + ext)).exists()), None)
        if img is None:
            continue
        for line in lbl.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            _cls, cx, cy, w, h = (float(p) for p in parts)
            candidates.append((h * w, img, cx, cy, w, h))

    candidates.sort(key=lambda c: c[0], reverse=True)

    written = 0
    manifest: list[str] = []
    for _area, img_path, cx, cy, w, h in candidates:
        if written >= args.count:
            break
        with Image.open(img_path) as im:
            W, H = im.size
            bw, bh = w * W, h * H
            if bh < args.min_px:
                continue
            mx, my = bw * args.margin, bh * args.margin
            x1 = max(0, int(cx * W - bw / 2 - mx))
            y1 = max(0, int(cy * H - bh / 2 - my))
            x2 = min(W, int(cx * W + bw / 2 + mx))
            y2 = min(H, int(cy * H + bh / 2 + my))
            if x2 - x1 < 8 or y2 - y1 < 8:
                continue
            crop = im.crop((x1, y1, x2, y2)).convert("RGB")
            name = f"crop_{written:03d}_{int(bh)}px.jpg"
            crop.save(out_dir / name, quality=92)
            manifest.append(f"{name},{img_path.name},{int(bw)}x{int(bh)}")
            written += 1

    (out_dir / "manifest.csv").write_text(
        "crop,source_image,person_box_px\n" + "\n".join(manifest) + "\n", encoding="utf-8"
    )
    print(f"wrote {written} crops to {out_dir}")
    if written:
        heights = [int(m.split(",")[-1].split("x")[1]) for m in manifest]
        print(f"person height px: min {min(heights)} / median "
              f"{sorted(heights)[len(heights)//2]} / max {max(heights)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
