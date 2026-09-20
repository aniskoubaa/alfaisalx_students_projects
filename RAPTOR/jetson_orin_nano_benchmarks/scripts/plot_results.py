#!/usr/bin/env python3
"""results/*.jsonl -> figures/*.png

06-benchmark-plan.md requires the analysis to be a script, so nobody hand-copies
numbers into slides and every figure can be regenerated from the raw rows.

    python3 plot_results.py --results ../results/detector.jsonl --out ../figures

Colour follows the validated categorical palette (slots 1-3, which clear the
all-pairs CVD and normal-vision floors). Slot 3 sits below 3:1 against the light
surface, so every mark carries a direct label - the documented relief.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

# --- design tokens -------------------------------------------------------
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
CRITICAL = "#d03b3b"          # status colour, reserved - used only for the budget line
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]   # slots 1-3, all-pairs validated
MARKERS = {"yolo11n": "o", "yolo11s": "s", "yolo11m": "^"}

FRAME_BUDGET_MS = 33.0        # hard limit from the performance budget
POWER_BUDGET_W = 20.0         # sustained board power target


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "font.size": 10,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "axes.titlecolor": INK_PRIMARY,
        "axes.titlesize": 12,
        "axes.titleweight": "semibold",
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRIDLINE,
        "grid.linewidth": 0.8,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.labelcolor": INK_SECONDARY,
        "ytick.labelcolor": INK_SECONDARY,
        "legend.frameon": False,
        "figure.dpi": 160,
    })


def despine(ax) -> None:
    """Recessive chrome: keep the baseline, drop the box."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.grid(axis="x", visible=False)


def load(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def model_name(row: dict) -> str:
    return Path(row.get("model", "")).name.replace(".pt", "")


def is_pose(row: dict) -> bool:
    return "-pose" in model_name(row)


def family(row: dict) -> str:
    return model_name(row).replace("-pose", "")


def size_color(imgsz: int, sizes: list[int]) -> str:
    return SERIES[sizes.index(imgsz) % len(SERIES)]


# --- figures -------------------------------------------------------------
def fig_accuracy_vs_latency(rows: list[dict], out: Path) -> Path | None:
    """The decision chart: accuracy bought per millisecond."""
    pts = [r for r in rows if r.get("accuracy", {}).get("map50") is not None]
    if not pts:
        return None

    sizes = sorted({r["imgsz"] for r in pts})
    fig, ax = plt.subplots(figsize=(7.2, 4.6))

    # Label placement alternates above/below in x order, which keeps neighbouring
    # points from writing over each other in the dense in-budget cluster.
    for i, r in enumerate(sorted(pts, key=lambda r: r["latency"]["p95_ms"])):
        ax.scatter(
            r["latency"]["p95_ms"], r["accuracy"]["map50"],
            s=110, color=size_color(r["imgsz"], sizes),
            marker=MARKERS.get(family(r), "o"),
            edgecolor=SURFACE, linewidth=1.6, zorder=3,
        )
        # Direct label on every mark - the relief the palette WARN requires.
        # The backend is part of the label: the same weights appear twice, as
        # PyTorch and as a TensorRT engine, and they are not the same result.
        tag = " TRT" if r.get("backend") == "engine" else ""
        # Adjacent points in x get labels pointing opposite ways, vertically and
        # horizontally. With eleven configurations inside a 12 ms band, labels
        # that all trail right will overprint each other.
        # Four placements rather than two: yolo11s @960 appears twice at the same
        # accuracy (PyTorch and TensorRT), so a two-way alternation still puts
        # both labels on the same line.
        dx, dy, ha = [(9, 6, "left"), (-9, -13, "right"),
                      (9, -13, "left"), (-9, 6, "right")][i % 4]
        ax.annotate(
            f"{model_name(r)} @{r['imgsz']}{tag}",
            (r["latency"]["p95_ms"], r["accuracy"]["map50"]),
            textcoords="offset points", xytext=(dx, dy), ha=ha,
            fontsize=8, color=INK_SECONDARY,
        )

    ax.axvline(FRAME_BUDGET_MS, color=CRITICAL, linewidth=1.4, linestyle="--", zorder=2)
    ax.annotate("33 ms frame budget", (FRAME_BUDGET_MS, ax.get_ylim()[1]),
                textcoords="offset points", xytext=(-6, -12), ha="right",
                fontsize=8.5, color=CRITICAL)

    handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=8,
                          color=size_color(s, sizes), label=f"{s} px")
               for s in sizes]
    ax.legend(handles=handles, title="Input size", loc="lower right",
              title_fontsize=9, fontsize=9, labelcolor=INK_SECONDARY)

    ax.set_xlabel("p95 latency per frame (ms, log scale)  -  lower is better")
    ax.set_ylabel("person mAP@0.5  (VisDrone proxy)")
    ax.set_title("Accuracy bought per millisecond, Orin NX @ 25 W")
    # Latency spans ~5x once RT-DETR is included; on a linear axis the whole
    # in-budget cluster collapses into the left tenth of the plot. Log keeps both
    # the cluster and the outlier readable, and the axis is labelled as such.
    if max(r["latency"]["p95_ms"] for r in pts) / min(r["latency"]["p95_ms"] for r in pts) > 2:
        ax.set_xscale("log")
        ax.set_xticks([25, 30, 40, 60, 80, 120])
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.minorticks_off()
    # Room on the right so the rightmost direct label is not clipped.
    ax.margins(x=0.14)
    despine(ax)
    fig.tight_layout()
    path = out / "fig1_accuracy_vs_latency.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_latency_by_config(rows: list[dict], out: Path) -> Path | None:
    """Dot plot: does each configuration fit the frame budget?

    Deliberately NOT a bar chart. Every configuration lands between 28 and 35 ms,
    and a bar chart must start at zero — which renders that whole range as bars of
    near-identical height, hiding the only thing the reader needs to see. Truncating
    a bar axis to fix that would be a lie about magnitude. A dot encodes position
    rather than magnitude, so a non-zero axis is legitimate here.
    """
    if not rows:
        return None
    sizes = sorted({r["imgsz"] for r in rows})

    entries = []
    for r in rows:
        tag = " TRT" if r.get("backend") == "engine" else ""
        entries.append((f"{model_name(r)} @{r['imgsz']}{tag}", r["latency"]["p95_ms"], r["imgsz"]))
    entries.sort(key=lambda e: e[1])

    labels = [e[0] for e in entries]
    values = [e[1] for e in entries]
    colors = [size_color(e[2], sizes) for e in entries]

    fig, ax = plt.subplots(figsize=(7.4, max(3.2, 0.40 * len(entries) + 1.5)))
    ys = range(len(entries))

    # Leader line from the axis to the dot: gives the eye a path without
    # implying magnitude-from-zero the way a bar would.
    for y, v, c in zip(ys, values, colors):
        ax.plot([min(values) - 0.6, v], [y, y], color=GRIDLINE, linewidth=1.0, zorder=2)
        ax.plot(v, y, marker="o", markersize=9, color=c,
                markeredgecolor=SURFACE, markeredgewidth=1.6, zorder=3)
        ax.annotate(f"{v:.1f}", (v, y), textcoords="offset points", xytext=(11, -3),
                    fontsize=8.5, color=INK_SECONDARY)

    ax.axvline(FRAME_BUDGET_MS, color=CRITICAL, linewidth=1.4, linestyle="--", zorder=4)
    # Anchored in axes coordinates so it cannot be clipped off the top.
    ax.annotate("33 ms hard limit", xy=(FRAME_BUDGET_MS, 1.0),
                xycoords=("data", "axes fraction"),
                textcoords="offset points", xytext=(6, -12), ha="left",
                fontsize=8.5, color=CRITICAL)

    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels, fontsize=9)
    wide = max(values) / min(values) > 2
    if wide:
        ax.set_xscale("log")
        ax.set_xlim(min(values) * 0.92, max(values) * 1.35)
        ax.set_xticks([25, 30, 40, 60, 80, 120])
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.minorticks_off()
    else:
        ax.set_xlim(min(values) - 0.8, max(max(values), FRAME_BUDGET_MS) + 2.2)
    ax.set_xlabel("p95 latency per frame (ms, log scale)" if wide
                  else "p95 latency per frame (ms)")
    ax.set_title("Per-frame cost against the frame budget")

    handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=8,
                          color=size_color(s, sizes), label=f"{s} px") for s in sizes]
    ax.legend(handles=handles, title="Input size", loc="lower right",
              title_fontsize=9, fontsize=9, labelcolor=INK_SECONDARY)

    ax.grid(axis="y", visible=False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    path = out / "fig2_latency_by_config.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_recall(rows: list[dict], out: Path) -> Path | None:
    """Recall is the headline metric: in SAR a missed person outweighs a false alarm."""
    pts = [r for r in rows if r.get("accuracy", {}).get("recall") is not None]
    if not pts:
        return None
    pts.sort(key=lambda r: r["accuracy"]["recall"])

    labels = [f"{model_name(r)} @{r['imgsz']}" for r in pts]
    values = [r["accuracy"]["recall"] for r in pts]

    fig, ax = plt.subplots(figsize=(7.2, max(3.0, 0.42 * len(pts) + 1.4)))
    bars = ax.barh(labels, values, color=SERIES[0], height=0.62, zorder=3)
    ax.bar_label(bars, fmt="%.3f", padding=4, fontsize=8.5, color=INK_SECONDARY)

    ax.set_xlabel("person recall  (VisDrone proxy, COCO-pretrained, no fine-tuning)")
    ax.set_title("Recall - the metric that decides whether a casualty is found")
    ax.set_xlim(0, max(values) * 1.25)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    path = out / "fig3_recall.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_power(rows: list[dict], out: Path) -> Path | None:
    """Power is a flight-time cost, and a budget row in its own right."""
    pts = [r for r in rows if (r.get("tegrastats") or {}).get("board_power_mean_w")]
    if not pts:
        return None
    sizes = sorted({r["imgsz"] for r in pts})
    pts.sort(key=lambda r: r["tegrastats"]["board_power_mean_w"])

    labels = [f"{model_name(r)} @{r['imgsz']}" for r in pts]
    values = [r["tegrastats"]["board_power_mean_w"] for r in pts]
    colors = [size_color(r["imgsz"], sizes) for r in pts]

    fig, ax = plt.subplots(figsize=(7.2, max(3.0, 0.42 * len(pts) + 1.4)))
    bars = ax.barh(labels, values, color=colors, height=0.62, zorder=3)
    ax.bar_label(bars, fmt="%.1f W", padding=4, fontsize=8.5, color=INK_SECONDARY)

    ax.axvline(POWER_BUDGET_W, color=CRITICAL, linewidth=1.4, linestyle="--", zorder=4)
    ax.annotate("20 W sustained target", xy=(POWER_BUDGET_W, 1.0),
                xycoords=("data", "axes fraction"),
                textcoords="offset points", xytext=(6, -12), ha="left",
                fontsize=8.5, color=CRITICAL)

    handles = [plt.Line2D([], [], marker="s", linestyle="", markersize=8,
                          color=size_color(s, sizes), label=f"{s} px") for s in sizes]
    ax.legend(handles=handles, title="Input size", loc="lower right",
              title_fontsize=9, fontsize=9, labelcolor=INK_SECONDARY)

    ax.set_xlabel("mean board power during inference (W, VDD_IN)")
    ax.set_title("Board power - every watt is flight time")
    ax.set_xlim(0, max(max(values), POWER_BUDGET_W) * 1.3)
    ax.grid(axis="y", visible=False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    path = out / "fig4_power.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def write_table(rows: list[dict], out: Path) -> Path:
    """The table view - required relief for the sub-3:1 palette slot, and the
    artifact a reader can check every figure against."""
    header = ["model", "task", "imgsz", "precision", "backend",
              "mean_ms", "p95_ms", "fps", "mAP50", "mAP50-95", "recall",
              "power_W", "temp_C", "gpu_mem_MB"]
    lines = [",".join(header)]
    for r in sorted(rows, key=lambda r: (model_name(r), r.get("imgsz", 0))):
        acc = r.get("accuracy") or {}
        ts = r.get("tegrastats") or {}
        lines.append(",".join(str(x) for x in [
            model_name(r),
            "pose" if is_pose(r) else "detect",
            r.get("imgsz", ""),
            r.get("precision", ""),
            r.get("backend", ""),
            r["latency"]["mean_ms"], r["latency"]["p95_ms"], r.get("fps_mean", ""),
            acc.get("map50", ""), acc.get("map50_95", ""), acc.get("recall", ""),
            ts.get("board_power_mean_w", ""), ts.get("temp_max_c", ""),
            r.get("gpu_mem_peak_mb", ""),
        ]))
    path = out / "results_table.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    style()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_rows = load([Path(p) for p in args.results])
    if not all_rows:
        raise SystemExit("no result rows found")

    # Synthetic-frame runs measure latency with no real detections, so their NMS
    # and postprocess cost is unrepresentative. They are valid on their own terms
    # but must not share an axis with runs over real imagery.
    rows = [r for r in all_rows if not r.get("source_is_synthetic")]
    dropped = len(all_rows) - len(rows)
    print(f"loaded {len(all_rows)} result rows"
          + (f" ({dropped} synthetic-source rows excluded from comparison)" if dropped else ""))
    if not rows:
        raise SystemExit("all rows were synthetic-source; nothing comparable to plot")

    for fn in (fig_accuracy_vs_latency, fig_latency_by_config, fig_recall, fig_power):
        path = fn(rows, out)
        print(f"  {'wrote ' + str(path) if path else 'skipped ' + fn.__name__ + ' (no data)'}")
    print(f"  wrote {write_table(rows, out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
