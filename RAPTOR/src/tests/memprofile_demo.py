#!/usr/bin/env python3
"""Where does the live demo's slow memory growth come from?

Every soak run (2026-10-05) showed the demo's resident memory climbing by about
1.5-2.5 MB a minute after warm-up. Over a flight that is nothing; over a demo
left running for days it is gigabytes. This tells the two possible kinds apart:

  * Python objects that are never released (a list or dict that only grows) -
    tracemalloc sees them, and the diff below names the file and line;
  * native memory (CUDA/TensorRT caches, glibc arena fragmentation) - invisible
    to tracemalloc, so the Python heap stays flat while RSS still climbs.

Runs the real demo with tracemalloc on; snapshots at --t1 and --t2 seconds; writes
the 25 biggest growth sites, Python heap size and RSS (anonymous vs file-backed)
at both times, to ~/raptor-results/memprofile_<time>.txt. Use through the soak runner:

    RAPTOR_MEM_T1=180 RAPTOR_MEM_T2=900 soak_demo.py --demo memprofile_demo.py \\
        --name memprofile --minutes 16 -- --mode bench --source <video>
"""
from __future__ import annotations

import os
import sys
import threading
import time
import tracemalloc
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE.parent / "demo"))

T1 = float(os.environ.get("RAPTOR_MEM_T1", "180"))
T2 = float(os.environ.get("RAPTOR_MEM_T2", "900"))
OUT = Path.home() / "raptor-results" / "memprofile_{}.txt".format(datetime.now().strftime("%Y%m%d-%H%M%S"))


def rss_breakdown():
    keys = ("VmRSS", "RssAnon", "RssFile", "RssShmem")
    out = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        k = line.split(":")[0]
        if k in keys:
            out[k] = int(line.split()[1]) // 1024
    return out


def watcher():
    t0 = time.monotonic()
    time.sleep(T1)
    s1, r1, h1 = tracemalloc.take_snapshot(), rss_breakdown(), tracemalloc.get_traced_memory()[0]
    # Written at once, so a run stopped before t2 still leaves its first half.
    # (2026-10-05: a snapshot of a heap traced for 15 min took over a minute; the
    # soak's planned stop came first and nothing was written. Leave a margin.)
    OUT.write_text("t1 = {:.0f} s: RSS {} MB, python heap {:.1f} MB (t2 pending)\n".format(
        time.monotonic() - t0, r1, h1 / 2**20))
    print("memprofile: snapshot 1 taken", flush=True)
    time.sleep(max(0.0, T2 - (time.monotonic() - t0)))
    s2, r2, h2 = tracemalloc.take_snapshot(), rss_breakdown(), tracemalloc.get_traced_memory()[0]
    minutes = (T2 - T1) / 60
    lines = ["memprofile of the live demo, snapshots at {:.0f} s and {:.0f} s ({:.1f} min apart)".format(T1, T2, minutes),
             "",
             "RSS (MB)          at t1   at t2   per minute",
             ]
    for k in r1:
        lines.append("  {:12s} {:7d} {:7d}   {:+.2f}".format(k, r1[k], r2[k], (r2[k] - r1[k]) / minutes))
    lines += ["  {:12s} {:7.1f} {:7.1f}   {:+.2f}".format("python heap", h1 / 2**20, h2 / 2**20,
                                                         (h2 - h1) / 2**20 / minutes),
              "",
              "Top 25 Python allocation sites by growth between the snapshots:"]
    flt = [tracemalloc.Filter(False, tracemalloc.__file__)]
    for st in s2.filter_traces(flt).compare_to(s1.filter_traces(flt), "lineno")[:25]:
        lines.append("  {:+9.1f} KB  {:+7d} blocks  {}".format(st.size_diff / 1024, st.count_diff,
                                                               str(st.traceback[0])[-110:]))
    OUT.write_text("\n".join(lines) + "\n")
    print("memprofile written to", OUT, flush=True)


tracemalloc.start(1)
threading.Thread(target=watcher, name="memprofile", daemon=True).start()

import raptor_live_demo  # noqa: E402  (imported after tracemalloc starts, on purpose)

sys.argv[0] = str(HERE.parent / "demo" / "raptor_live_demo.py")
raise SystemExit(raptor_live_demo.main())
