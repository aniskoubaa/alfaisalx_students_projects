#!/usr/bin/env python3
"""Turn VisDrone-DET into a single-class *person* detection set.

Why this dataset: RAPTOR has no flight footage yet (the project is pre-data), but
detector accuracy cannot be compared on synthetic frames. 07-roadmap.md already
sanctions public aerial datasets as an interim bridge. VisDrone is drone-captured
from altitude, so people are small and foreshortened — the property that actually
stresses a detector here. It is urban rather than wilderness, so it is a *proxy*
and every number derived from it must be labelled as such.

VisDrone annotation line:
    x,y,w,h,score,category,truncation,occlusion
with category 1 = pedestrian (upright) and 2 = people (other postures). RAPTOR
cares about "is there a human", so both collapse to class 0.

    python3 prepare_visdrone_person.py --zip visdrone-val.zip --out ./visdrone-person
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

# VisDrone category ids that are a human being.
PERSON_CATEGORIES = {1, 2}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def convert_annotation(ann_path: Path, img_w: int, img_h: int) -> list[str]:
    """VisDrone box list -> YOLO lines, person only, normalised xywh."""
    lines: list[str] = []
    for raw in ann_path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip().rstrip(",")
        if not raw:
            continue
        parts = raw.split(",")
        if len(parts) < 6:
            continue
        try:
            x, y, w, h = (int(float(p)) for p in parts[:4])
            score = int(float(parts[4]))
            category = int(float(parts[5]))
        except ValueError:
            continue

        # score==0 marks a region the dataset says to ignore.
        if score == 0 or category not in PERSON_CATEGORIES:
            continue
        if w <= 0 or h <= 0:
            continue

        # Clip to the image: VisDrone boxes occasionally run past the edge.
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(img_w, x + w), min(img_h, y + h)
        if x2 <= x1 or y2 <= y1:
            continue

        cx = (x1 + x2) / 2 / img_w
        cy = (y1 + y2) / 2 / img_h
        nw = (x2 - x1) / img_w
        nh = (y2 - y1) / img_h
        lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", required=True, help="VisDrone2019-DET-*.zip")
    ap.add_argument("--out", required=True, help="output dataset root")
    ap.add_argument("--split", default="val", help="split name used in the yaml")
    ap.add_argument("--limit", type=int, default=0, help="cap image count (0 = all)")
    args = ap.parse_args()

    from PIL import Image

    out_root = Path(args.out).resolve()
    work = out_root / "_raw"
    img_out = out_root / "images" / args.split
    lbl_out = out_root / "labels" / args.split
    for d in (img_out, lbl_out):
        d.mkdir(parents=True, exist_ok=True)

    if not work.exists():
        print(f"extracting {args.zip} ...")
        with zipfile.ZipFile(args.zip) as zf:
            zf.extractall(work)

    img_dirs = sorted(p for p in work.rglob("images") if p.is_dir())
    ann_dirs = sorted(p for p in work.rglob("annotations") if p.is_dir())
    if not img_dirs or not ann_dirs:
        raise SystemExit(f"could not find images/ and annotations/ under {work}")
    img_dir, ann_dir = img_dirs[0], ann_dirs[0]

    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if args.limit:
        images = images[: args.limit]

    kept_imgs = 0
    kept_boxes = 0
    empty_imgs = 0
    for img_path in images:
        ann_path = ann_dir / (img_path.stem + ".txt")
        if not ann_path.exists():
            continue
        try:
            with Image.open(img_path) as im:
                w, h = im.size
        except OSError:
            continue

        lines = convert_annotation(ann_path, w, h)
        # Images with no people are still valid negatives and are kept: a
        # detector that invents people over empty ground is a real failure mode.
        if not lines:
            empty_imgs += 1

        target_img = img_out / img_path.name
        if not target_img.exists():
            target_img.write_bytes(img_path.read_bytes())
        (lbl_out / (img_path.stem + ".txt")).write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        kept_imgs += 1
        kept_boxes += len(lines)

    yaml_path = out_root / "visdrone_person.yaml"
    yaml_path.write_text(
        "# VisDrone-DET collapsed to a single 'person' class (pedestrian + people).\n"
        "# Interim proxy for RAPTOR's own aerial data - see 06-benchmark-plan.md.\n"
        f"path: {out_root.as_posix()}\n"
        f"train: images/{args.split}\n"
        f"val: images/{args.split}\n"
        "names:\n"
        "  0: person\n",
        encoding="utf-8",
    )

    print(f"images written   : {kept_imgs}")
    print(f"person boxes     : {kept_boxes}")
    print(f"images w/o people: {empty_imgs}")
    print(f"mean boxes/image : {kept_boxes / kept_imgs:.1f}" if kept_imgs else "")
    print(f"dataset yaml     : {yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
