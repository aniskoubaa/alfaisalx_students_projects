"""Coarse posture from COCO-17 keypoints, plus per-person smoothing over time.

Why this exists (2026-09-29): the first live demo judged posture from the torso
angle alone, so anyone sitting upright - back straight, legs under a desk - was
labelled "standing". Sitting and standing differ in the LEGS, not the torso:

  * side view, seated:  the thigh (hip -> knee) is near horizontal;
  * front view, seated: the thigh points at the camera, so the knee appears only
    a little below the hip (foreshortened) - short relative to the torso;
  * standing:           the thigh is near vertical and about as long as the torso.

When the knees are not visible (desk, table, crop edge), the keypoints cannot
tell sitting from standing, and the label says so ("upright, legs hidden")
instead of guessing. The VLM check in the live demo answers those cases.

Angles are measured against IMAGE vertical. That is right for a fixed camera and
wrong once an aircraft banks: the flight version must rotate keypoints into a
gravity-aligned frame with the IMU attitude first (docs/02).
"""
from __future__ import annotations

import math
from collections import Counter, deque

KP_CONF_MIN = 0.35
NOSE, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 0, 5, 6, 11, 12
L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 13, 14, 15, 16

STANDING = "standing"
SITTING = "sitting"
LYING = "LYING"
LEANING = "leaning"
UPRIGHT_LEGS_HIDDEN = "upright, legs hidden"
UNKNOWN = "unknown"

# Thresholds, in degrees from image vertical and in torso lengths.
TORSO_LYING_DEG = 60        # torso more horizontal than this -> lying
TORSO_UPRIGHT_DEG = 30      # torso more vertical than this -> upright
THIGH_SITTING_DEG = 50      # thigh more horizontal than this -> sitting (side view)
KNEE_DROP_SITTING = 0.45    # knee less than this many torso lengths below the hip -> sitting (front view)
KNEE_BENT_DEG = 120         # hip-knee-ankle angle below this -> knees bent (crouch / kneel)


def _pt(pts, i):
    """(x, y) of keypoint i if confidently visible, else None."""
    try:
        x, y, c = pts[i]
    except (IndexError, ValueError, TypeError):
        return None
    return (x, y) if c >= KP_CONF_MIN else None


def _mid(pts, i, j):
    a, b = _pt(pts, i), _pt(pts, j)
    if a and b:
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return a or b          # one side is enough for a coarse estimate


def _deg_from_vertical(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None
    return math.degrees(math.atan2(abs(dx), abs(dy)))


def _joint_angle(a, b, c):
    """Angle at b between b->a and b->c, in degrees (180 = straight)."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n < 1e-6:
        return None
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))
    return math.degrees(math.acos(cos))


def posture_from_keypoints(pts):
    """Return (label, torso_deg_from_vertical or None, reason).

    `pts` is 17 (x, y, conf) triples in image pixels. The reason is a short
    string saying which evidence decided the label, for the HUD and for debugging.
    """
    if not pts:
        return UNKNOWN, None, "no keypoints"
    shoulders = _mid(pts, L_SHOULDER, R_SHOULDER)
    hips = _mid(pts, L_HIP, R_HIP)
    if shoulders is None or hips is None:
        return UNKNOWN, None, "shoulders or hips not visible"
    torso_deg = _deg_from_vertical(shoulders, hips)
    torso_len = math.dist(shoulders, hips)
    if torso_deg is None or torso_len < 1.0:
        return UNKNOWN, None, "torso too small"
    if torso_deg > TORSO_LYING_DEG:
        return LYING, torso_deg, "torso horizontal"

    legs = []
    for hip_i, knee_i, ankle_i in ((L_HIP, L_KNEE, L_ANKLE), (R_HIP, R_KNEE, R_ANKLE)):
        hip, knee = _pt(pts, hip_i), _pt(pts, knee_i)
        if hip and knee:
            legs.append((hip, knee, _pt(pts, ankle_i)))
    if not legs:
        if torso_deg < TORSO_UPRIGHT_DEG:
            return UPRIGHT_LEGS_HIDDEN, torso_deg, "knees not visible"
        return LEANING, torso_deg, "torso tilted, knees not visible"

    thigh_deg = max(_deg_from_vertical(h, k) or 0.0 for h, k, _ in legs)
    knee_drop = min((k[1] - h[1]) / torso_len for h, k, _ in legs)
    if thigh_deg > THIGH_SITTING_DEG:
        return SITTING, torso_deg, "thigh {:.0f} deg from vertical".format(thigh_deg)
    if knee_drop < KNEE_DROP_SITTING:
        return SITTING, torso_deg, "knee {:.2f} torso below hip".format(knee_drop)
    bends = [_joint_angle(h, k, a) for h, k, a in legs if a]
    bends = [b for b in bends if b is not None]
    if bends and min(bends) < KNEE_BENT_DEG:
        return "crouching", torso_deg, "knee bent {:.0f} deg".format(min(bends))
    if torso_deg >= TORSO_UPRIGHT_DEG:
        return LEANING, torso_deg, "torso {:.0f} deg, legs straight".format(torso_deg)
    return STANDING, torso_deg, "thigh vertical, knee {:.2f} torso below hip".format(knee_drop)


class PostureVote:
    """Majority vote over each person's last few posture estimates.

    A single frame's keypoints jitter; a label that flips every frame is worse
    than useless on screen. Keyed by tracker id. 'unknown' only wins when
    nothing else has been seen.
    """

    def __init__(self, window=7):
        self.window = window
        self.hist: dict[int, deque] = {}

    def add(self, track_id, label):
        self.hist.setdefault(track_id, deque(maxlen=self.window)).append(label)

    def get(self, track_id):
        h = self.hist.get(track_id)
        if not h:
            return None
        known = [x for x in h if x != UNKNOWN]
        return Counter(known or h).most_common(1)[0][0]

    def forget(self, live_ids):
        for k in [k for k in self.hist if k not in live_ids]:
            del self.hist[k]
