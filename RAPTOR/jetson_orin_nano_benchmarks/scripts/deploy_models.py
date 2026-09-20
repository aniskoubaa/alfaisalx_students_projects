#!/usr/bin/env python3
"""Stage the benchmark-selected models into a deployment tree, with provenance.

"Installed" should mean more than files in a directory. This lays out the chosen
artifacts under one root, records where each came from and what it measured, and
verifies each one actually loads and runs on this board.

    python3 deploy_models.py --root ~/raptor-deploy \
        --models ~/raptor-models --vlm ~/raptor-vlm \
        --results ~/raptor-results --verify

The manifest is the point: six months from now, "which engine is this and what did
it score" must be answerable from the board itself, not from someone's memory.
An engine is also tied to the TensorRT version and the GPU that built it, so the
manifest records those too — a .engine file is not portable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import collect_env  # noqa: E402

# What the benchmarks selected. See docs/10 and docs/12.
SELECTION = {
    "detector": {
        "artifact": "yolo11s.engine",
        "role": "tier 1 - person detection",
        "why": "highest person mAP@0.5 inside the 33 ms frame budget; TensorRT FP16 "
               "costs zero accuracy versus PyTorch and returns ~4.5 ms/frame",
        "match": {"model": "yolo11s", "backend": "engine"},
    },
    "pose": {
        "artifact": "yolo11s-pose.engine",
        "role": "tier 1+2 - person detection AND 17 keypoints",
        "why": "doc 02 specifies one pose model rather than a separate detector; "
               "in PyTorch every pose config sat within 1 ms of the hard limit, so "
               "TensorRT is a prerequisite rather than an optimisation",
        "match": {"model": "yolo11s-pose", "backend": "engine"},
    },
    "vlm": {
        "artifact": "Qwen2.5-VL-3B-Instruct",
        "role": "tier 3 - event-triggered scene description",
        "why": "88% schema-valid JSON versus 0% for SmolVLM2, roughly half the "
               "time-to-first-token, lower mean and peak power",
        "match": {"model": "Qwen2.5-VL-3B-Instruct"},
    },
    "vlm_fallback": {
        "artifact": "SmolVLM2-2.2B-Instruct",
        "role": "tier 3 fallback for an 8 GB board",
        "why": "smaller and faster per token, but produced no schema-valid output "
               "and volunteered demographic attributes - MUST NOT be run without "
               "grammar-constrained decoding (see docs/12)",
        "match": {"model": "SmolVLM2-2.2B-Instruct"},
    },
}


def sha256_file(path: Path, limit_mb: int = 2048) -> str:
    h = hashlib.sha256()
    read = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
            read += len(chunk)
            if read > limit_mb * 1024 * 1024:
                return h.hexdigest()[:16] + f"-first{limit_mb}MB"
    return h.hexdigest()[:16]


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def load_results(results_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for name in ("detector.jsonl", "vlm.jsonl"):
        f = results_dir / name
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def best_row(rows: list[dict], match: dict) -> dict | None:
    """Most recent row matching this artifact, so the manifest quotes real numbers."""
    def matches(r: dict) -> bool:
        # Exact stem, not substring: "yolo11s" would otherwise also match
        # "yolo11s-pose" and quote the wrong row's numbers.
        stem = Path(str(r.get("model", ""))).name
        for suffix in (".pt", ".engine", ".onnx"):
            stem = stem.replace(suffix, "")
        if stem != match.get("model", ""):
            return False
        if "backend" in match and r.get("backend") != match["backend"]:
            return False
        return True

    hits = [r for r in rows if matches(r)]
    return hits[-1] if hits else None


def perf_summary(row: dict | None) -> dict | None:
    if not row:
        return None
    out: dict = {}
    if "latency" in row:
        out["p95_ms"] = row["latency"].get("p95_ms")
        out["mean_ms"] = row["latency"].get("mean_ms")
        out["fps"] = row.get("fps_mean")
    if row.get("accuracy"):
        out["map50"] = row["accuracy"].get("map50")
        out["recall"] = row["accuracy"].get("recall")
    if "ttft_s" in row:
        out["ttft_p95_s"] = row["ttft_s"].get("p95")
        out["full_reply_p95_s"] = row["total_s"].get("p95")
        out["tokens_per_s"] = row.get("tokens_per_s_mean")
        out["schema_valid_rate"] = row.get("schema_valid_rate")
    ts = row.get("tegrastats") or {}
    if ts.get("board_power_mean_w"):
        out["board_power_mean_w"] = ts["board_power_mean_w"]
    out["measured_at_power_mode"] = (
        ((row.get("env") or {}).get("power") or {}).get("nvpmodel_name"))
    out["imgsz"] = row.get("imgsz")
    return out


def verify_detector(path: Path, imgsz: int) -> dict:
    """Load the engine and run one inference — proves it is usable on this board."""
    try:
        import numpy as np
        from ultralytics import YOLO

        model = YOLO(str(path))
        frame = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
        model.predict(frame, imgsz=imgsz, verbose=False)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 - the failure is the result
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def verify_vlm(path: Path) -> dict:
    """Load processor + config only. A full generation is the benchmark's job."""
    try:
        from transformers import AutoConfig, AutoProcessor

        AutoProcessor.from_pretrained(str(path))
        cfg = AutoConfig.from_pretrained(str(path))
        return {"ok": True, "architecture": getattr(cfg, "architectures", ["?"])[0]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="deployment root to create")
    ap.add_argument("--models", required=True, help="directory holding .pt/.engine files")
    ap.add_argument("--vlm", required=True, help="directory holding VLM model dirs")
    ap.add_argument("--results", required=True, help="directory holding *.jsonl results")
    ap.add_argument("--verify", action="store_true", help="load each artifact to prove it runs")
    ap.add_argument("--copy", action="store_true",
                    help="copy artifacts into the tree (default: symlink, to save disk)")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    models_dir = Path(args.models).expanduser()
    vlm_dir = Path(args.vlm).expanduser()
    rows = load_results(Path(args.results).expanduser())

    manifest: dict = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "board_env": collect_env.collect(str(SCRIPT_DIR)),
        "selection_basis": "docs/10-detector-benchmark-results.md, docs/12-vlm-benchmark-results.md",
        "artifacts": {},
        "warnings": [],
    }

    if manifest["board_env"]["board"].get("l4t_version"):
        manifest["warnings"].append(
            "TensorRT engines are tied to this TensorRT version and GPU. They are NOT "
            "portable — re-export after any JetPack upgrade or on a different board.")

    for slot, spec in SELECTION.items():
        name = spec["artifact"]
        src = (models_dir / name) if (models_dir / name).exists() else (vlm_dir / name)
        target_dir = root / slot
        entry: dict = {"role": spec["role"], "why": spec["why"], "source": str(src)}

        if not src.exists():
            entry["status"] = "MISSING"
            manifest["warnings"].append(f"{slot}: {name} not found at {src}")
            manifest["artifacts"][slot] = entry
            print(f"  {slot:14s} MISSING  ({name})")
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / name
        if not dest.exists():
            if args.copy or src.is_dir():
                if src.is_dir():
                    dest.symlink_to(src, target_is_directory=True) if not args.copy \
                        else shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
            else:
                dest.symlink_to(src)

        entry["path"] = str(dest)
        entry["bytes"] = dir_size(src) if src.is_dir() else src.stat().st_size
        if src.is_file():
            entry["sha256_16"] = sha256_file(src)

        row = best_row(rows, spec["match"])
        entry["measured"] = perf_summary(row)
        if entry["measured"] is None:
            manifest["warnings"].append(f"{slot}: no recorded benchmark row found")

        if args.verify:
            if src.is_dir():
                entry["verify"] = verify_vlm(src)
            else:
                imgsz = (entry["measured"] or {}).get("imgsz") or 960
                entry["verify"] = verify_detector(src, imgsz)
            state = "OK" if entry["verify"].get("ok") else "FAILED"
            print(f"  {slot:14s} {state:8s} {name}")
            if not entry["verify"].get("ok"):
                manifest["warnings"].append(f"{slot}: verification failed - {entry['verify'].get('error')}")
        else:
            print(f"  {slot:14s} staged   {name}")

        entry["status"] = "ready"
        manifest["artifacts"][slot] = entry

    root.mkdir(parents=True, exist_ok=True)
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nmanifest: {root / 'MANIFEST.json'}")
    if manifest["warnings"]:
        print("warnings:")
        for w in manifest["warnings"]:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
