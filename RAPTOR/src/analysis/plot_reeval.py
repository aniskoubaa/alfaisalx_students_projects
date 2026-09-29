#!/usr/bin/env python3
"""Figures for the 2026-09-28 model re-evaluation (docs/10 and docs/12, part A of the report).

Runs ON THE LAPTOP, from the repository root:

    python src/analysis/plot_reeval.py

Reads benchmarks/results/detector.jsonl, vlm.jsonl and vlm_content_scores.csv (from
score_vlm_generations.py) and writes, into benchmarks/figures/:

  fig5_reeval_detectors.png   held-out test-dev mAP@0.5 against real-frame p95 latency
  fig6_reeval_recall.png      recall on VisDrone val vs test-dev, per detector
  fig7_reeval_vlm.png         VLMs: schema validity, invented injuries, TTFT, memory
  reeval_detectors.csv        the joined table the figures are drawn from

Only rows from 2026-09-28 are used. Latency comes from the rows timed on the 200
real VisDrone val frames (the method of every earlier row); accuracy from the val
and test-dev rows. Rows for VisDrone-trained models scored by val() before the
person_scoring fix are excluded: val() ignores `classes`, so they counted cars as
people (see src/common/person_scoring.py).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_results import (BASELINE, CRITICAL, FRAME_BUDGET_MS, GRIDLINE, INK_MUTED,  # noqa: E402
                          INK_SECONDARY, SERIES, SURFACE, despine, load, model_name,
                          size_label, style)

DAYS = ("2026-09-28", "2026-09-29")   # the re-evaluation, and the next day's lean-runner rows
REPO = Path(__file__).resolve().parents[2]
RES = REPO / "benchmarks" / "results"
FIG = REPO / "benchmarks" / "figures"

# Plain-language names; the file stems are precise but unreadable in a chart.
NAMES = {
    "yolo11s": "yolo11s COCO", "yolo11s-1280": "yolo11s COCO",
    "yolo26s-960": "YOLO26s COCO",
    "visdrone-yolo26s-960": "YOLO26s VisDrone", "visdrone-yolo26s-1280": "YOLO26s VisDrone",
    "visdrone-yolo26s-736x1280": "YOLO26s VisDrone",
    "visdrone-yolo26n-1280": "YOLO26n VisDrone",
    "sih-aerial-person-1280": "aerial-person 11n",
    "visdrone-rtdetrv4-s": "RT-DETRv4-S VisDrone",
}


# Label offsets (points) per configuration. The cluster at 24-27 ms is dense, so
# an automatic alternation overprints; these were placed by eye.
LABEL_POS = {
    "visdrone-rtdetrv4-s@960": (8, 6, "left"),
    "visdrone-yolo26s-960@960": (8, -13, "left"),
    "yolo11s@960": (-8, -12, "right"),
    "yolo26s-960@960": (8, -2, "left"),
    "visdrone-yolo26s-736x1280@736x1280": (-8, 8, "right"),
    "visdrone-yolo26s-736x1280@736x1280 lean": (8, 8, "left"),
    "visdrone-yolo26n-1280@1280": (-8, 7, "right"),
    "sih-aerial-person-1280@1280": (-8, -4, "right"),
    "yolo11s-1280@1280": (-8, -13, "right"),
    "visdrone-yolo26s-1280@1280": (-8, 8, "right"),
}


def base(row: dict) -> str:
    return model_name(row).replace(".engine", "")


def valid(row: dict) -> bool:
    acc = row.get("accuracy") or {}
    if not acc or acc.get("map50") is None:
        return False
    # VisDrone-trained models are only valid through person_scoring.
    if "visdrone" in base(row) and "scorer" not in acc:
        return False
    return True


def is_testdev(row: dict) -> bool:
    return "testdev" in str((row.get("accuracy") or {}).get("dataset", ""))


def join_detectors(rows: list[dict]) -> list[dict]:
    """One entry per configuration: real-frame latency + val and test-dev accuracy."""
    day = [r for r in rows if r.get("timestamp", "")[:10] in DAYS]
    cfgs: dict[str, dict] = {}
    for r in day:
        # The same engine served two ways (Ultralytics vs the lean runner) is two
        # configurations: same accuracy, different latency.
        lean = "lean" in str(r.get("harness", ""))
        key = f"{base(r)}@{size_label(r)}" + (" lean" if lean else "")
        c = cfgs.setdefault(key, {"key": key, "model": base(r), "imgsz": size_label(r),
                                  "name": NAMES.get(base(r), base(r)) + (" (lean runtime)" if lean else "")})
        if not r.get("source_is_synthetic"):
            c["p95_ms"] = r["latency"]["p95_ms"]
            c["power_w"] = (r.get("tegrastats") or {}).get("board_power_mean_w")
        if valid(r):
            tag = "td" if is_testdev(r) else "val"
            c[f"{tag}_map50"] = r["accuracy"]["map50"]
            c[f"{tag}_recall"] = r["accuracy"]["recall"]
            c[f"{tag}_precision"] = r["accuracy"]["precision"]
    # The rectangular engine run through Ultralytics is timed only; its accuracy is
    # the same engine's, measured through the lean runner (2026-09-29) - or, before
    # that existed, the 1280 square rows'.
    for c in cfgs.values():
        if c["imgsz"] == "736x1280" and not c["key"].endswith(" lean") and "td_recall" not in c:
            same = cfgs.get(c["key"] + " lean", {})
            src, note = (same, "same engine, lean runner") if "td_recall" in same else (
                cfgs.get(f"{c['model'].replace('-736x1280', '-1280')}@1280", {}), "1280 square rows")
            for k in ("val_map50", "val_recall", "val_precision", "td_map50", "td_recall", "td_precision"):
                if k in src:
                    c[k] = src[k]
            c["accuracy_from"] = note
    return [c for c in cfgs.values() if "pose" not in c["model"]]


def fig_detectors(cfgs: list[dict]) -> Path | None:
    pts = [c for c in cfgs if "p95_ms" in c and "td_map50" in c]
    if not pts:
        return None
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    aerial = SERIES[1]
    for i, c in enumerate(sorted(pts, key=lambda c: c["p95_ms"])):
        colour = aerial if "VisDrone" in c["name"] or "aerial" in c["name"] else SERIES[0]
        ax.scatter(c["p95_ms"], c["td_map50"], s=110, color=colour,
                   edgecolor=SURFACE, linewidth=1.6, zorder=3)
        dx, dy, ha = LABEL_POS.get(c["key"]) or \
            [(9, 5, "left"), (9, -12, "left"), (-9, 5, "right"), (-9, -12, "right")][i % 4]
        ax.annotate(f"{c['name']} @{c['imgsz']}", (c["p95_ms"], c["td_map50"]),
                    textcoords="offset points", xytext=(dx, dy), ha=ha,
                    fontsize=8, color=INK_SECONDARY)
    ax.axvline(FRAME_BUDGET_MS, color=CRITICAL, linewidth=1.4, linestyle="--", zorder=2)
    ax.annotate("33 ms frame budget", xy=(FRAME_BUDGET_MS, 1.0), xycoords=("data", "axes fraction"),
                textcoords="offset points", xytext=(-6, -12), ha="right", fontsize=8.5, color=CRITICAL)
    handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=8, color=SERIES[0],
                          label="COCO-pretrained"),
               plt.Line2D([], [], marker="o", linestyle="", markersize=8, color=aerial,
                          label="trained on aerial (VisDrone)")]
    ax.legend(handles=handles, loc="lower right", fontsize=9, labelcolor=INK_SECONDARY)
    ax.set_xlabel("p95 latency per frame on real VisDrone frames (ms) - lower is better")
    ax.set_ylabel("person mAP@0.5 on VisDrone test-dev (held out)")
    ax.set_title("Aerial training doubles accuracy at the same cost - Orin NX @ 25 W")
    ax.set_ylim(0, max(c["td_map50"] for c in pts) * 1.2)
    ax.margins(x=0.12)
    despine(ax)
    fig.tight_layout()
    path = FIG / "fig5_reeval_detectors.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_recall(cfgs: list[dict]) -> Path | None:
    """Dumbbell: val recall (hollow) -> test-dev recall (solid). The gap is how
    optimistic our usual val set is - most of all for models tuned on it."""
    pts = [c for c in cfgs if "td_recall" in c and "val_recall" in c and "accuracy_from" not in c]
    if not pts:
        return None
    pts.sort(key=lambda c: c["td_recall"])
    fig, ax = plt.subplots(figsize=(7.4, max(3.0, 0.5 * len(pts) + 1.4)))
    for y, c in enumerate(pts):
        ax.plot([c["td_recall"], c["val_recall"]], [y, y], color=GRIDLINE, linewidth=2.2, zorder=2)
        ax.plot(c["val_recall"], y, marker="o", markersize=9, markerfacecolor=SURFACE,
                markeredgecolor=INK_MUTED, markeredgewidth=1.6, zorder=3)
        ax.plot(c["td_recall"], y, marker="o", markersize=9, color=SERIES[0],
                markeredgecolor=SURFACE, markeredgewidth=1.6, zorder=4)
        ax.annotate(f"{c['td_recall']:.2f}", (c["td_recall"], y), textcoords="offset points",
                    xytext=(-8, -3), ha="right", fontsize=8.5, color=INK_SECONDARY)
    ax.set_yticks(range(len(pts)))
    ax.set_yticklabels([f"{c['name']} @{c['imgsz']}" for c in pts], fontsize=9)
    handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=8, color=SERIES[0],
                          label="test-dev (held out)"),
               plt.Line2D([], [], marker="o", linestyle="", markersize=8, markerfacecolor=SURFACE,
                          markeredgecolor=INK_MUTED, label="val (our usual set)")]
    ax.legend(handles=handles, loc="lower right", fontsize=9, labelcolor=INK_SECONDARY)
    ax.set_xlabel("person recall - share of people found")
    ax.set_title("Recall: the metric that decides whether a casualty is found")
    ax.set_xlim(0, 0.8)
    ax.grid(axis="y", visible=False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    fig.tight_layout()
    path = FIG / "fig6_reeval_recall.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def vlm_rows() -> list[dict]:
    """vlm.jsonl rows from the day, joined to their content scores by generations file."""
    scores = {}
    p = RES / "vlm_content_scores.csv"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                scores[r["file"]] = r
    out = []
    for line in (RES / "vlm.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("timestamp", "")[:10] not in DAYS or r.get("crops") != 16:
            continue
        gen = Path(r.get("generations_file", "")).name
        s = scores.get(gen)
        if not s:
            continue
        # Rows written before bench_vlm.py recorded decoding ran greedy - the
        # harness default then.
        d = r.get("decoding") or {"mode": "greedy"}
        mode = "greedy" if d.get("mode") == "greedy" else ("shipped" if d.get("do_sample") else "shipped = greedy")
        if d.get("repetition_penalty") not in (None, 1.0) and mode == "greedy":
            mode = "greedy+rep"
        if (r.get("model_kwargs") or {}).get("downsample_mode") == "4x":
            mode += " 4x"
        name = r["model"].replace("-Instruct", "").replace("-HF", "").replace("InternVL3_5", "InternVL3.5")
        out.append({"label": f"{name} ({mode})", "pick": name == "Qwen3-VL-2B" and mode == "greedy+rep",
                    "schema": r["schema_valid_rate"] * 100, "injury": int(s["false_injury"]),
                    "lying": int(s["said_lying"]), "nv": int(s.get("not_visible_used") or 0), "ttft": r["ttft_s"]["p95"],
                    "mem": r["gpu_mem_peak_mb"] / 1000, "tps": r.get("tokens_per_s_mean")})
    return out


def fig_vlm(rows: list[dict]) -> Path | None:
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: (r["injury"], -r["schema"], r["lying"]), reverse=True)
    labels = [r["label"] for r in rows]
    panels = [("schema", "valid JSON (%)", "{:.0f}", 100),
              ("injury", "injury reported (of 16)", "{:d}", None),
              ("lying", "said 'lying' (of 16)", "{:d}", None),
              ("nv", "flags what it cannot see (of 16)", "{:d}", 16),
              ("ttft", "first token p95 (s)", "{:.2f}", None),
              ("mem", "peak GPU memory (GB)", "{:.1f}", None)]
    fig, axes = plt.subplots(1, len(panels), figsize=(15.5, max(3.2, 0.42 * len(rows) + 1.6)),
                             sharey=True)
    for ax, (key, title, f, xmax) in zip(axes, panels):
        vals = [r[key] for r in rows]
        colour = CRITICAL if key == "injury" else SERIES[0]
        bars = ax.barh(range(len(rows)), vals, color=colour, height=0.62, zorder=3)
        ax.bar_label(bars, labels=[f.format(v) for v in vals], padding=3, fontsize=8,
                     color=INK_SECONDARY)
        ax.set_title(title, fontsize=10)
        ax.set_xlim(0, (xmax or max(vals + [1])) * 1.3)
        ax.grid(axis="y", visible=False)
        ax.tick_params(axis="x", labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_yticks(range(len(rows)))
    axes[0].set_yticklabels(labels, fontsize=8.5)
    for tick, r in zip(axes[0].get_yticklabels(), rows):
        if r.get("pick"):
            tick.set_fontweight("bold")   # the recommended configuration
    fig.suptitle("Vision-language models on 16 person crops - nobody in them is injured or lying down",
                 fontsize=12, fontweight="semibold")
    fig.tight_layout()
    path = FIG / "fig7_reeval_vlm.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> int:
    style()
    FIG.mkdir(parents=True, exist_ok=True)
    cfgs = join_detectors(load([RES / "detector.jsonl"]))
    table = FIG / "reeval_detectors.csv"
    cols = ["key", "name", "imgsz", "p95_ms", "power_w", "val_map50", "val_recall",
            "val_precision", "td_map50", "td_recall", "td_precision", "accuracy_from"]
    with table.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(cfgs, key=lambda c: c.get("p95_ms", 0)))
    print(f"wrote {table} ({len(cfgs)} configurations)")
    for fn, arg in ((fig_detectors, cfgs), (fig_recall, cfgs), (fig_vlm, vlm_rows())):
        path = fn(arg)
        print(f"  {'wrote ' + str(path) if path else 'skipped ' + fn.__name__ + ' (no data)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
