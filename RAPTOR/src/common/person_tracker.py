"""One box per person, held steady across frames: de-duplication + ByteTrack.

Why this exists (2026-09-29, measured on the bench camera): without it, one
seated person was reported as 0 to 5 people from frame to frame. Two causes:

  * nested duplicates - the detector returns the whole person AND the upper body
    (IoU ~0.66, under the 0.7 NMS threshold, so both survive);
  * no memory - a person missed for one frame vanishes, and a one-frame false
    positive (a chair, a drone motor) appears as a new person.

`PersonTracker.update()` removes nested and heavily overlapping boxes, feeds the
rest to Ultralytics' ByteTrack, shows a track only after it has been seen in
`min_hits` frames, and keeps showing it for `hold_frames` frames after a miss.
The people count on screen is the number of confirmed tracks.
"""
from __future__ import annotations

import numpy as np


def suppress_duplicates(xyxy, scores, iou_thr=0.5, contain_thr=0.85):
    """Indices of boxes to keep, best score first.

    A box is dropped if it overlaps a better one by IoU > iou_thr, or if more
    than contain_thr of the smaller of the two lies inside the other (an upper
    body inside a whole body, a head inside a person).
    """
    xyxy = np.asarray(xyxy, dtype=np.float32).reshape(-1, 4)
    scores = np.asarray(scores, dtype=np.float32).reshape(-1)
    areas = np.clip(xyxy[:, 2] - xyxy[:, 0], 0, None) * np.clip(xyxy[:, 3] - xyxy[:, 1], 0, None)
    keep = []
    for i in np.argsort(-scores):
        dup = False
        for j in keep:
            ix = max(0.0, min(xyxy[i, 2], xyxy[j, 2]) - max(xyxy[i, 0], xyxy[j, 0]))
            iy = max(0.0, min(xyxy[i, 3], xyxy[j, 3]) - max(xyxy[i, 1], xyxy[j, 1]))
            inter = ix * iy
            if inter <= 0:
                continue
            union = areas[i] + areas[j] - inter
            small = min(areas[i], areas[j])
            if (union > 0 and inter / union > iou_thr) or (small > 0 and inter / small > contain_thr):
                dup = True
                break
        if not dup:
            keep.append(int(i))
    return keep


class _Detections:
    """The minimal Results-like object Ultralytics' BYTETracker accepts."""

    def __init__(self, xyxy, conf):
        self.xyxy = np.asarray(xyxy, dtype=np.float32).reshape(-1, 4)
        self.conf = np.asarray(conf, dtype=np.float32).reshape(-1)
        self.cls = np.zeros(len(self.conf), dtype=np.float32)

    @property
    def xywh(self):
        b = self.xyxy
        return np.stack([(b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2,
                         b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]], axis=1)

    def __len__(self):
        return len(self.conf)

    def __getitem__(self, idx):
        return _Detections(self.xyxy[idx], self.conf[idx])


class Track:
    __slots__ = ("id", "box", "score", "det_index", "hits", "missed")

    def __init__(self, tid):
        self.id, self.box, self.score, self.det_index, self.hits, self.missed = tid, None, 0.0, None, 0, 0


class PersonTracker:
    """De-duplicate, track, confirm, hold. See the module docstring."""

    def __init__(self, min_hits=3, hold_frames=10, iou_thr=0.5, contain_thr=0.85,
                 track_buffer=30, high_thresh=0.35, new_track_thresh=0.4):
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import IterableSimpleNamespace

        cfg = IterableSimpleNamespace(
            tracker_type="bytetrack", track_high_thresh=high_thresh, track_low_thresh=0.1,
            new_track_thresh=new_track_thresh, track_buffer=track_buffer, match_thresh=0.8,
            fuse_score=True)
        self.bt = BYTETracker(cfg)
        self.min_hits, self.hold_frames = min_hits, hold_frames
        self.iou_thr, self.contain_thr = iou_thr, contain_thr
        self.tracks: dict[int, Track] = {}

    def update(self, xyxy, scores):
        """Feed one frame's detections; return the tracks to show.

        Each returned Track has .id, .box (x1, y1, x2, y2), .score, and
        .det_index - the index into THIS frame's input detections, or None when
        the track is being held through a miss.
        """
        xyxy = np.asarray(xyxy, dtype=np.float32).reshape(-1, 4)
        scores = np.asarray(scores, dtype=np.float32).reshape(-1)
        keep = suppress_duplicates(xyxy, scores, self.iou_thr, self.contain_thr) if len(scores) else []
        dets = _Detections(xyxy[keep], scores[keep]) if keep else _Detections(np.zeros((0, 4)), np.zeros(0))
        out = self.bt.update(dets)      # called on empty frames too, so lost tracks age

        seen = set()
        for row in out:
            x1, y1, x2, y2, tid, score = row[:6]
            idx = int(row[-1])
            tid = int(tid)
            t = self.tracks.get(tid) or Track(tid)
            t.box, t.score = (float(x1), float(y1), float(x2), float(y2)), float(score)
            t.det_index = keep[idx] if 0 <= idx < len(keep) else None
            t.hits += 1
            t.missed = 0
            self.tracks[tid] = t
            seen.add(tid)
        for tid in list(self.tracks):
            if tid in seen:
                continue
            t = self.tracks[tid]
            t.missed += 1
            t.det_index = None
            if t.missed > self.hold_frames:
                del self.tracks[tid]
        return [t for t in self.tracks.values() if t.hits >= self.min_hits]
