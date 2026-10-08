#!/usr/bin/env python3
"""How steady are the demo's detections? Reads a --frame-log JSONL file.

"Consistent" (2026-10-05 request) has to be a number to be checked. Three of them:

  count changes   frames on which the number of people shown differs from the
                  frame before, per 100 frames. Real people entering and leaving
                  cause some; the rest is the detector or tracker wavering;
  flicker         a count that changes and comes straight back within 3 frames
                  (2 -> 3 -> 2). Nobody walks in and out of shot in 50 ms at
                  60 FPS, so this is the jitter a viewer sees, not the scene;
  ID births       new track IDs per 100 frames. A person who keeps their ID is
                  one person; a re-assigned ID looks like someone new arrived.

    analyse_frame_log.py ~/raptor-results/frames_street.jsonl
    analyse_frame_log.py a.jsonl b.jsonl            # side by side
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def analyse(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if not rows:
        return {"file": str(path), "frames": 0}
    n = [r["n"] for r in rows]
    changes = sum(1 for a, b in zip(n, n[1:]) if a != b)
    flicker = 0
    for i in range(1, len(n) - 1):
        if n[i] != n[i - 1]:
            # back to the earlier value within the next 3 frames?
            if any(n[j] == n[i - 1] for j in range(i + 1, min(len(n), i + 4))):
                flicker += 1
    seen, births = set(), 0
    for r in rows:
        for tid in r["ids"]:
            if tid not in seen:
                seen.add(tid)
                births += 1
    ms = sorted(r["ms"] for r in rows)
    per100 = 100.0 / len(rows)
    return {
        "file": Path(path).name,
        "frames": len(rows),
        "people_mean": round(statistics.mean(n), 2),
        "people_max": max(n),
        "count_changes_per_100": round(changes * per100, 2),
        "flicker_per_100": round(flicker * per100, 2),
        "id_births_per_100": round(births * per100, 2),
        "unique_ids": len(seen),
        "infer_ms_mean": round(statistics.mean(ms), 2),
        "infer_ms_p95": ms[int(0.95 * (len(ms) - 1))],
    }


def main():
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    results = [analyse(p) for p in paths]
    keys = [k for k in results[0] if k != "file"]
    width = max(len(r["file"]) for r in results)
    print("{:24s}".format("") + "".join("{:>{w}s}  ".format(r["file"], w=width) for r in results))
    for k in keys:
        print("{:24s}".format(k) + "".join("{:>{w}}  ".format(str(r.get(k)), w=width) for r in results))
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
