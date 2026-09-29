"""Person-detection scoring that works for any detector, whatever its class list.

Why this exists: Ultralytics' val() ignores the `classes` argument. For a COCO
model that does not matter - our dataset has one class (person = 0), so only
COCO class 0 is ever scored. But models trained on VisDrone split people into
'pedestrian' (0) and 'people' (1) next to eight vehicle classes, and there is no
val() setting that scores "0 and 1 as person, nothing else": single_cls=True
turns every car and van into a person too (we measured precision collapsing to
0.25 that way on 2026-09-28).

So this scorer does it explicitly, with Ultralytics' own pieces so the numbers
mean the same as val()'s:
  1. keep only predictions in the person classes, conf >= 0.001 (val()'s floor);
  2. merge them into one class and apply one class-agnostic NMS at IoU 0.7, so a
     person boxed as both 'pedestrian' and 'people' counts once;
  3. match to ground truth with DetectionValidator.match_predictions' greedy rule
     at IoU 0.50:0.95, and summarise with ultralytics.utils.metrics.ap_per_class.
Precision and recall are reported at the max-F1 confidence, as val() does.

Used by bench_detector.py (--single-cls) and bench_rtdetrv4.py. Run
bench_rtdetrv4.py --check-yolo on a COCO model to confirm it lands within about a
point of val() on the same model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

MERGE_NMS_IOU = 0.7
CONF_FLOOR = 0.001


def dataset_images(data_yaml: Path) -> list[Path]:
    """The 'val' split of an Ultralytics dataset yaml."""
    import yaml

    cfg = yaml.safe_load(Path(data_yaml).expanduser().read_text())
    root = Path(cfg.get("path", Path(data_yaml).parent))
    img_dir = root / cfg["val"]
    return sorted(p for p in img_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})


def ground_truth(img_path: Path, w: int, h: int):
    """YOLO label file next to the image -> person boxes, xyxy pixels."""
    import numpy as np

    lbl = Path(str(img_path).replace("/images/", "/labels/")).with_suffix(".txt")
    rows = [l.split() for l in lbl.read_text().splitlines() if l.strip()] if lbl.exists() else []
    boxes = np.array([[float(v) for v in r[1:5]] for r in rows], dtype=np.float32).reshape(-1, 4)
    cx, cy, bw, bh = boxes.T
    return np.stack([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h], 1)


def match(iou, iouv):
    """DetectionValidator.match_predictions (greedy), single class.

    iou is [labels, detections]; returns [detections, len(iouv)] booleans.
    """
    import numpy as np

    correct = np.zeros((iou.shape[1], len(iouv)), dtype=bool)
    for i, thr in enumerate(iouv):
        m = np.array(np.nonzero(iou >= thr)).T          # [label, detection]
        if m.shape[0]:
            if m.shape[0] > 1:
                m = m[iou[m[:, 0], m[:, 1]].argsort()[::-1]]
                m = m[np.unique(m[:, 1], return_index=True)[1]]
                m = m[np.unique(m[:, 0], return_index=True)[1]]
            correct[m[:, 1].astype(int), i] = True
    return correct


def merge_person_boxes(boxes, conf):
    """One class-agnostic NMS over the merged person classes."""
    import numpy as np
    import torch
    from torchvision.ops import nms

    if len(boxes) == 0:
        return boxes, conf
    keep = nms(torch.as_tensor(boxes, dtype=torch.float32),
               torch.as_tensor(conf, dtype=torch.float32), MERGE_NMS_IOU).numpy()
    keep = np.sort(keep)
    return boxes[keep], conf[keep]


def score(images: list[Path], predict: Callable) -> dict:
    """predict(path) -> (xyxy[N,4], conf[N]) in pixels, person classes only."""
    import numpy as np
    import torch
    from PIL import Image
    from ultralytics.utils.metrics import ap_per_class, box_iou

    iouv = np.linspace(0.5, 0.95, 10)
    tps, confs, n_gt = [], [], 0
    for p in images:
        with Image.open(p) as im:
            w, h = im.size
        gt = ground_truth(p, w, h)
        boxes, conf = predict(p)
        keep = conf >= CONF_FLOOR
        boxes, conf = merge_person_boxes(boxes[keep], conf[keep])
        n_gt += len(gt)
        if len(boxes) == 0:
            continue
        if len(gt):
            iou = box_iou(torch.from_numpy(gt), torch.from_numpy(np.ascontiguousarray(boxes))).numpy()
            tps.append(match(iou, iouv))
        else:
            tps.append(np.zeros((len(boxes), len(iouv)), dtype=bool))
        confs.append(conf)
    tp = np.concatenate(tps) if tps else np.zeros((0, 10), dtype=bool)
    conf = np.concatenate(confs) if confs else np.zeros(0)
    res = ap_per_class(tp, conf, np.zeros(len(conf)), np.zeros(n_gt))
    p, r, ap = res[2], res[3], res[5]
    return {"map50": round(float(ap[:, 0].mean()), 4), "map50_95": round(float(ap.mean()), 4),
            "precision": round(float(p.mean()), 4), "recall": round(float(r.mean()), 4),
            "images": len(images), "instances": int(n_gt),
            "scorer": f"person_scoring: person classes merged, agnostic NMS {MERGE_NMS_IOU}"}


def ultralytics_predictor(model, imgsz, classes, device="0", extra: dict | None = None) -> Callable:
    """Wrap an Ultralytics model (weights or engine) as a predict(path) function."""
    def predict(p):
        r = model.predict(str(p), imgsz=imgsz, conf=CONF_FLOOR, iou=0.7, max_det=300,
                          classes=classes, device=device, verbose=False, **(extra or {}))[0]
        return r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()
    return predict
