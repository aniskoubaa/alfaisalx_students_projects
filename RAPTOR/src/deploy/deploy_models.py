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
REPO_ROOT = SCRIPT_DIR.parents[1]          # src/<group>/ -> repository root
# Shared helpers (collect_env, tegra_sampler) live in src/common. This file's own
# folder is searched too, so a script copied on its own next to them still works.
for _path in (SCRIPT_DIR, SCRIPT_DIR.parent / "common"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import collect_env  # noqa: E402

# What the benchmarks selected: the 2026-09-28 re-evaluation, docs/10 and docs/12.
# "artifact" is relative to --models (engines) or --vlm (model folders); "name" is
# what it is called inside the deployment tree when that differs.
SELECTION = {
    "detector": {
        "artifact": "aerial/visdrone-yolo26s-736x1280.engine",
        "role": "tier 1 - person detection on every frame (VisDrone classes 0 pedestrian + 1 people)",
        "why": "ties RT-DETRv4-S on held-out accuracy (VisDrone test-dev recall 42.5 %, mAP 0.452, "
               "against 20.0 % recall for COCO yolo11s) at a third less GPU compute (11.5 ms), which "
               "matters because the VLM shares the GPU. Serve it with src/common/trt_yolo.py "
               "(25.9 ms p95 end to end), not Ultralytics' Python pipeline (31.0 ms)",
        "licence": "AGPL-3.0 (Ultralytics YOLO26); weights trained on VisDrone, CC BY-NC-SA 3.0 - non-commercial",
        "source_url": "https://huggingface.co/dronefreak/visdrone-yolo26s",
        "classes_as_person": [0, 1],
        "match": {"model": "visdrone-yolo26s-736x1280", "backend": "engine",
                  "harness_contains": "lean", "dataset_contains": "testdev"},
        "verify": "lean",
    },
    "detector_alt": {
        "artifact": "aerial/visdrone-rtdetrv4-s/model.engine",
        "name": "visdrone-rtdetrv4-s.engine",
        "role": "tier 1 alternative - the Apache-2.0 detector, if AGPL is ruled out",
        "why": "test-dev recall 42.8 %, mAP 0.439 - a tie with the detector - and 24.3 ms end to "
               "end in its lean runtime, but 17.1 ms of GPU compute",
        "licence": "Apache-2.0 (code and weights); weights trained on VisDrone, CC BY-NC-SA 3.0 - non-commercial",
        "source_url": "https://huggingface.co/dronefreak/visdrone-rtdetrv4-s",
        "classes_as_person": [0, 1],
        "match": {"model": "visdrone-rtdetrv4-s", "dataset_contains": "testdev"},
        "verify": "rtdetr",
    },
    "pose": {
        "artifact": "yolo26s-pose-960.engine",
        "role": "tier 2 - 17 keypoints on crops of each detected person, below frame rate",
        "why": "22.7 ms p95 against 26.5 ms for yolo11s-pose. No aerial-trained pose model "
               "exists, so detection comes from the aerial detector and pose runs on its "
               "crops; keypoints are unreliable below ~32 px of person height",
        "licence": "AGPL-3.0 (Ultralytics YOLO26); COCO weights",
        "match": {"model": "yolo26s-pose-960", "backend": "engine"},
        "verify": "ultralytics",
    },
    "pose_bench": {
        "artifact": "yolo26s-pose-384x640.engine",
        "role": "bench demo - pose on the whole 16:9 webcam frame, for people near the camera",
        "why": "the same YOLO26s-pose weights as tier 2 in a 384x640 engine that fits a 16:9 frame: "
               "17.1 ms per 1080p frame including the tracker, against 35.4 ms for the 960 engine "
               "(live bench, 2026-09-29), so the demo reaches the camera's 30 fps (60 at 720p). "
               "People near a desk camera are large, so the lower resolution costs them nothing",
        "licence": "AGPL-3.0 (Ultralytics YOLO26); COCO weights",
        "match": {"model": "yolo26s-pose-384x640", "backend": "engine"},
        "verify": "ultralytics",
    },
    "vlm": {
        "artifact": "Qwen3-VL-2B-Instruct",
        "role": "tier 3 - event-triggered scene description",
        "why": "the only model tested that was truthful (no injury invented for 16 uninjured "
               "people), 100 % schema-valid, honest about what it cannot see, 0.21 s to first "
               "token and 4.1 GB. The first-round pick, Qwen2.5-VL-3B, reported injuries for 7 of 16",
        "licence": "Apache-2.0",
        "decoding": {"do_sample": False, "repetition_penalty": 1.05,
                     "note": "greedy + 1.05 penalty; plain greedy loops (31 % valid JSON)"},
        "match": {"model": "Qwen3-VL-2B-Instruct", "decoding_mode": "greedy", "repetition_penalty": 1.05},
        "verify": "vlm",
    },
    "vlm_fallback": {
        "artifact": "Qwen3.5-2B",
        "role": "tier 3 fallback",
        "why": "equally truthful on injuries and never repeated the prompt's posture, but "
               "never fills not_visible and is slower (0.30 s first token)",
        "licence": "Apache-2.0",
        "decoding": {"do_sample": False, "repetition_penalty": 1.05},
        "match": {"model": "Qwen3.5-2B", "decoding_mode": "greedy", "repetition_penalty": 1.05},
        "verify": "vlm",
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
        if "harness_contains" in match and match["harness_contains"] not in str(r.get("harness", "")):
            return False
        dec = r.get("decoding") or {}
        if "decoding_mode" in match and dec.get("mode") != match["decoding_mode"]:
            return False
        if "repetition_penalty" in match and dec.get("repetition_penalty") != match["repetition_penalty"]:
            return False
        return True

    hits = [r for r in rows if matches(r)]
    # Prefer the held-out row when one exists: it is the number decisions were made on.
    want = match.get("dataset_contains")
    preferred = [r for r in hits if want and want in str((r.get("accuracy") or {}).get("dataset", ""))]
    return (preferred or hits)[-1] if hits else None


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
        out["accuracy_dataset"] = row["accuracy"].get("dataset")
    if row.get("harness"):
        out["harness"] = row["harness"]
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


def engine_imgsz(path: Path):
    """Input size [h, w] from an Ultralytics .engine's metadata header, or None."""
    try:
        with path.open("rb") as fh:
            n = int.from_bytes(fh.read(4), "little")
            s = json.loads(fh.read(n).decode("utf-8")).get("imgsz")
        return [int(s[0]), int(s[1])] if isinstance(s, (list, tuple)) else [int(s), int(s)]
    except (OSError, ValueError, UnicodeDecodeError, TypeError, IndexError):
        return None


def verify_detector(path: Path, imgsz) -> dict:
    """Load the engine and run one 1080p frame — proves it is usable on this board.

    `imgsz` is an int or [h, w]; a rectangular engine only accepts its own shape.
    """
    try:
        import numpy as np
        from ultralytics import YOLO

        model = YOLO(str(path))
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        model.predict(frame, imgsz=imgsz, verbose=False)
        return {"ok": True, "imgsz": imgsz}
    except Exception as exc:  # noqa: BLE001 - the failure is the result
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def verify_lean(path: Path, classes) -> dict:
    """Load the engine in the lean runtime (src/common/trt_yolo.py) and run a 1080p frame."""
    try:
        import numpy as np
        from trt_yolo import TrtYolo

        det = TrtYolo(path, classes=classes)
        det(np.zeros((1080, 1920, 3), dtype=np.uint8))
        return {"ok": True, "imgsz": [det.h, det.w], "serving": "src/common/trt_yolo.py"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def verify_rtdetr(path: Path) -> dict:
    """Load the RT-DETRv4 engine (plain TensorRT) and run one frame through it."""
    try:
        import torch
        sys.path.insert(0, str(SCRIPT_DIR.parent / "benchmarks"))
        from bench_rtdetrv4 import TrtRunner

        run = TrtRunner(path)
        img = run.buffers["images"]
        run(torch.zeros_like(img), torch.tensor([[img.shape[3], img.shape[2]]], device="cuda"))
        return {"ok": True, "imgsz": list(img.shape[2:]), "serving": "src/benchmarks/bench_rtdetrv4.py TrtRunner"}
    except Exception as exc:  # noqa: BLE001
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
        "selection_basis": "2026-09-28 re-evaluation: docs/10-detector-benchmark-results.md, "
                           "docs/12-vlm-benchmark-results.md",
        "artifacts": {},
        "warnings": [],
    }

    if manifest["board_env"]["board"].get("l4t_version"):
        manifest["warnings"].append(
            "TensorRT engines are tied to this TensorRT version and GPU. They are NOT "
            "portable — re-export after any JetPack upgrade or on a different board.")

    for slot, spec in SELECTION.items():
        art = spec["artifact"]
        name = spec.get("name", Path(art).name)
        src = (models_dir / art) if (models_dir / art).exists() else (vlm_dir / art)
        target_dir = root / slot
        entry: dict = {"role": spec["role"], "why": spec["why"], "source": str(src)}
        for key in ("licence", "source_url", "classes_as_person", "decoding"):
            if key in spec:
                entry[key] = spec[key]

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
            kind = spec.get("verify", "vlm" if src.is_dir() else "ultralytics")
            if kind == "vlm":
                entry["verify"] = verify_vlm(src)
            elif kind == "lean":
                entry["verify"] = verify_lean(src, spec.get("classes_as_person"))
            elif kind == "rtdetr":
                entry["verify"] = verify_rtdetr(src)
            else:
                imgsz = (engine_imgsz(src) if src.suffix == ".engine" else None) \
                    or (entry["measured"] or {}).get("imgsz") or 960
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
