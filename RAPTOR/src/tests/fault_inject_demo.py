#!/usr/bin/env python3
"""Run the real live demo with faults injected, to prove it survives them.

The demo now guards each frame (a failure is logged and the frame skipped) and
its camera thread (a failed read re-opens the camera). A guard that is never
exercised is a guess, so this wrapper makes things fail on purpose, from the
outside - no test hooks live in the production code:

  RAPTOR_FAULT_FRAME_RATE   fraction of frames whose drawing raises (0.01 = 1 %)
  RAPTOR_FAULT_CAMERA_RATE  fraction of camera reads that raise inside the camera thread

Everything else is passed to raptor_live_demo.py unchanged. Use through the soak
runner, which then judges whether the demo survived:

    RAPTOR_FAULT_FRAME_RATE=0.01 soak_demo.py --demo fault_inject_demo.py \\
        --name fault_1pct --minutes 3 -- --mode bench --source <video>

Expected: 1 % -> SURVIVED, about 1 % of frames counted as frame_errors.
          1.0 -> stops after 30 failed frames in a row, exit status non-zero, and says why.
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE.parent / "demo"))

import raptor_live_demo  # noqa: E402

FRAME_RATE = float(os.environ.get("RAPTOR_FAULT_FRAME_RATE", "0"))
CAMERA_RATE = float(os.environ.get("RAPTOR_FAULT_CAMERA_RATE", "0"))
rng = random.Random(1005)


class InjectedFault(RuntimeError):
    pass


if FRAME_RATE > 0:
    real_draw = raptor_live_demo.draw_hud

    def faulty_draw_hud(frame, lines):
        if rng.random() < FRAME_RATE:
            raise InjectedFault("injected per-frame fault (test)")
        return real_draw(frame, lines)

    raptor_live_demo.draw_hud = faulty_draw_hud

if CAMERA_RATE > 0:
    import live_camera

    class FaultyCap:
        def __init__(self, cap):
            self.cap = cap

        def read(self):
            if rng.random() < CAMERA_RATE:
                raise InjectedFault("injected camera-thread fault (test)")
            return self.cap.read()

        def __getattr__(self, name):
            return getattr(self.cap, name)

    real_open = live_camera.LiveCamera._open

    def faulty_open(self):
        cap = real_open(self)
        return FaultyCap(cap) if cap is not None else None

    live_camera.LiveCamera._open = faulty_open

print("fault injection: frame rate {}, camera rate {}".format(FRAME_RATE, CAMERA_RATE), flush=True)
sys.argv[0] = str(HERE.parent / "demo" / "raptor_live_demo.py")
raise SystemExit(raptor_live_demo.main())
