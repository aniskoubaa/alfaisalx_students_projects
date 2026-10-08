#!/usr/bin/env python3
"""Reproduce the live demo's "crashes when something suddenly appears".

Two candidate causes, both found by reading the code and both of which fire only
when a NEW person enters the scene. Each is driven here deterministically, with
no camera and no models, so a fix can be proven rather than hoped for.

  A. Thread race in vlm_posture.VlmPosture.answers.
     The VLM thread adds a NEW key the first time it answers about a new person,
     while the main loop iterates the same dict (forget(), and the HUD's
     answers.values()). Python raises
         RuntimeError: dictionary changed size during iteration
     The writer here runs much faster than the real VLM (~2 answers/s) to make a
     rare event happen in seconds; the access pattern is the demo's exactly.

  B. Degenerate boxes through the tracker.
     A detection clamped at the frame edge can have zero height or width (a
     person stepping in from the edge). ByteTrack divides by the height for its
     aspect ratio; any NaN/inf that reaches draw_person() hits int(nan).

    ~/raptor-venv/bin/python ~/raptor/src/tests/repro_crashes.py

Exit status 0 only if neither failure occurs.
"""
from __future__ import annotations

import math
import sys
import threading
import time
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent / "common", HERE.parent / "demo"):
    sys.path.insert(0, str(p))


def race_vlm_answers(seconds=5.0):
    """A: hammer VlmPosture.answers from a writer thread, as the VLM thread does."""
    import vlm_posture

    # An instance without its model thread: only the shared dict is under test.
    vlm = object.__new__(vlm_posture.VlmPosture)
    vlm.answers = {}
    if hasattr(vlm_posture.VlmPosture, "record"):        # the fixed version keeps a lock
        vlm._answers_lock = threading.Lock()
    stop = threading.Event()
    errors = {"main": 0, "kinds": set()}

    def writer():                       # the VLM thread: a new person, then another
        tid = 0
        while not stop.is_set():
            tid += 1
            rec = getattr(vlm, "record", None)
            if rec is not None:
                rec(tid, "standing", 0.4)
            else:
                vlm.answers[tid] = ("standing", time.monotonic(), 0.4)

    th = threading.Thread(target=writer, daemon=True)
    th.start()
    t_end = time.monotonic() + seconds
    loops = 0
    while time.monotonic() < t_end:
        loops += 1
        try:
            live = set(range(max(0, loops - 50), loops))
            vlm.forget(live)                                   # main loop, every frame
            lat = getattr(vlm, "latencies", None)
            vals = lat() if lat else [a[2] for a in vlm.answers.values()]   # the HUD line
            _ = sum(vals)
        except RuntimeError as e:
            errors["main"] += 1
            errors["kinds"].add(str(e))
    stop.set()
    th.join(1)
    return {"loops": loops, "errors": errors["main"], "kinds": sorted(errors["kinds"])}


def degenerate_boxes():
    """B: feed zero-height / zero-width / inverted boxes through PersonTracker."""
    import numpy as np
    from person_tracker import PersonTracker

    results = {}
    cases = {
        "zero_height_at_bottom_edge": [1700, 1080, 1800, 1080],
        "zero_width_at_right_edge": [1920, 500, 1920, 700],
        "one_pixel_tall": [100, 1079, 400, 1080],
        "inverted": [500, 600, 400, 500],
    }
    normal = [800, 300, 1000, 800]
    for name, bad in cases.items():
        tr = PersonTracker()
        out = {"exception": None, "nonfinite_box": False}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # a normal person for a while, then the degenerate one appears
                for _ in range(5):
                    tr.update(np.array([normal], np.float32), np.array([0.9], np.float32))
                for _ in range(12):
                    tracks = tr.update(np.array([normal, bad], np.float32), np.array([0.9, 0.8], np.float32))
                    for t in tracks:
                        if not all(math.isfinite(v) for v in t.box):
                            out["nonfinite_box"] = True
                            int(t.box[0])     # what draw_person() does
        except Exception as e:  # noqa: BLE001 - recording the failure is the point
            out["exception"] = "{}: {}".format(type(e).__name__, str(e)[:120])
        results[name] = out
    return results


def main():
    print("A. VLM answers dict, writer thread vs main loop (5 s) ...")
    a = race_vlm_answers()
    print("   loops {loops}, RuntimeErrors {errors}  {kinds}".format(**a))

    print("B. degenerate detections through the tracker ...")
    b = degenerate_boxes()
    for name, r in b.items():
        print("   {:28s} exception={!s:60s} nonfinite={}".format(name, r["exception"], r["nonfinite_box"]))

    failed = a["errors"] > 0 or any(r["exception"] or r["nonfinite_box"] for r in b.values())
    print("\nRESULT:", "FAIL - crash paths reproduced" if failed else "PASS - no crash path triggered")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
