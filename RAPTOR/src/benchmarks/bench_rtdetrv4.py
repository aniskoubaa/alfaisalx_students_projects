#!/usr/bin/env python3
"""E1 for RT-DETRv4 — the Apache-2.0 detector Ultralytics cannot load.

Doc 02 keeps a permissively licensed detector on the shortlist in case
Ultralytics' AGPL-3.0 becomes a blocker. RT-DETRv4 (github.com/RT-DETRs/RT-DETRv4)
is the one with aerial weights available: dronefreak/visdrone-rtdetrv4-s on
Hugging Face, trained on VisDrone. It needs its own harness, and this is it.

    python3 bench_rtdetrv4.py --repo ~/raptor-ext/RT-DETRv4 \\
        --config ~/raptor-models/aerial/visdrone-rtdetrv4-s/config.yaml \\
        --weights ~/raptor-models/aerial/visdrone-rtdetrv4-s/model.pth \\
        --data ~/raptor-data/visdrone-person/visdrone_person.yaml --classes 0 1

What it does, in order:
  1. exports the model (with its built-in post-processor) to ONNX, then builds a
     TensorRT FP16 engine with trtexec - the deployment path;
  2. times the engine on synthetic frames exactly as bench_detector.py does
     (warm-up discarded, mean/p95, tegrastats), preprocessing and output
     filtering included;
  3. scores the engine on the person dataset with src/common/person_scoring.py
     (Ultralytics' own matching and ap_per_class), so map50 / recall mean what
     they mean in every other detector.jsonl row.

--check-yolo MODEL runs step 3 on an Ultralytics model instead. Its numbers
should land within about a point of bench_detector.py --accuracy for the same
model; if they do, the scoring here is comparable. (Small differences are
expected: Ultralytics val() batches with rectangular letterboxing.)

VisDrone splits people into 'pedestrian' (0) and 'people' (1); --classes 0 1
keeps both and scores them as one 'person' class, matching our labels.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]          # src/<group>/ -> repository root
for _path in (SCRIPT_DIR, SCRIPT_DIR.parent / "common"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import collect_env  # noqa: E402
from bench_detector import percentiles, sha256_file  # noqa: E402
from tegra_sampler import TegraSampler  # noqa: E402
from person_scoring import dataset_images, score, ultralytics_predictor  # noqa: E402


# --------------------------------------------------------------------------- model
def stub_training_only_modules() -> None:
    """RT-DETRv4 imports its training stack at package import time.

    faster_coco_eval, tensorboard, timm and calflops are used only for training,
    evaluation on COCO JSON, and FLOP counting - none of which runs here - and
    none is installed on the board. Placeholders let the model code import
    without adding four packages to the venv.
    """
    class _Anything(types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return type(name, (), {"__init__": lambda self, *a, **k: None})

    for name in ("faster_coco_eval", "faster_coco_eval.core", "faster_coco_eval.core.mask",
                 "calflops", "timm", "torch.utils.tensorboard"):
        try:
            __import__(name)
        except Exception:  # noqa: BLE001 - any import failure means stub it
            sys.modules[name] = _Anything(name)
            # `import a.b.c as x` walks attributes, so each stub must also hang
            # off its parent, not just sit in sys.modules.
            parent, _, child = name.rpartition(".")
            if parent in sys.modules:
                setattr(sys.modules[parent], child, sys.modules[name])


def load_rtdetr(repo: Path, config: Path, weights: Path):
    """Build the deploy-mode model + post-processor exactly as the repo's export does."""
    import torch
    import torch.nn as nn

    stub_training_only_modules()
    sys.path.insert(0, str(repo))
    from engine.core import YAMLConfig  # noqa: E402 - needs the repo on sys.path

    cfg = YAMLConfig(str(config))
    if "HGNetv2" in cfg.yaml_cfg:
        cfg.yaml_cfg["HGNetv2"]["pretrained"] = False   # no download; weights come next
    ckpt = torch.load(str(weights), map_location="cpu", weights_only=False)
    state = ckpt["ema"]["module"] if "ema" in ckpt else ckpt.get("model", ckpt)
    cfg.model.load_state_dict(state)

    class Deploy(nn.Module):
        def __init__(self):
            super().__init__()
            self.model = cfg.model.deploy()
            self.postprocessor = cfg.postprocessor.deploy()

        def forward(self, images, orig_target_sizes):
            return self.postprocessor(self.model(images), orig_target_sizes)

    height, width = cfg.yaml_cfg.get("eval_spatial_size") or [640, 640]
    return Deploy().eval(), (int(height), int(width))


def export_engine(model, hw, onnx_path: Path, engine_path: Path) -> dict:
    """ONNX (static batch 1) -> trtexec FP16. Returns trtexec's own GPU timing."""
    import torch

    h, w = hw
    if not onnx_path.exists():
        data = torch.rand(1, 3, h, w)
        size = torch.tensor([[w, h]])
        with torch.no_grad():
            model(data, size)
            kwargs = dict(input_names=["images", "orig_target_sizes"],
                          output_names=["labels", "boxes", "scores"],
                          opset_version=17, do_constant_folding=True)
            try:        # the TorchScript exporter is what the repo was written for
                torch.onnx.export(model, (data, size), str(onnx_path), dynamo=False, **kwargs)
            except TypeError:
                torch.onnx.export(model, (data, size), str(onnx_path), **kwargs)
        print(f"exported {onnx_path}")
    log = ""
    if not engine_path.exists():
        cmd = ["/usr/src/tensorrt/bin/trtexec", f"--onnx={onnx_path}", "--fp16",
               f"--saveEngine={engine_path}", "--skipInference"]
        print("building engine:", " ".join(cmd))
        t0 = time.perf_counter()
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"engine built in {time.perf_counter() - t0:.0f}s")
    # trtexec's GPU-only timing, for comparison with the end-to-end number below.
    out = subprocess.run(["/usr/src/tensorrt/bin/trtexec", f"--loadEngine={engine_path}",
                          "--iterations=300", "--warmUp=2000"],
                         capture_output=True, text=True).stdout
    log = out
    m = re.search(r"GPU Compute Time: min = ([\d.]+) ms, max = ([\d.]+) ms, mean = ([\d.]+) ms, "
                  r"median = ([\d.]+) ms, percentile\(90%\) = ([\d.]+) ms, percentile\(95%\) = ([\d.]+) ms", log)
    return ({"mean_ms": float(m.group(3)), "p95_ms": float(m.group(6)), "max_ms": float(m.group(2))}
            if m else {"error": "could not parse trtexec output"})


class TrtRunner:
    """Minimal TensorRT 10 runner: torch tensors as I/O buffers, one CUDA stream."""

    def __init__(self, engine_path: Path):
        import tensorrt as trt
        import torch

        self.torch = torch
        logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, "rb") as fh:
            self.engine = trt.Runtime(logger).deserialize_cuda_engine(fh.read())
        self.ctx = self.engine.create_execution_context()
        self.stream = torch.cuda.Stream()
        self.buffers = {}
        dtypes = {trt.float32: torch.float32, trt.float16: torch.float16,
                  trt.int32: torch.int32, trt.int64: torch.int64}
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            shape = tuple(self.engine.get_tensor_shape(name))
            buf = torch.empty(shape, dtype=dtypes[self.engine.get_tensor_dtype(name)], device="cuda")
            self.buffers[name] = buf
            self.ctx.set_tensor_address(name, buf.data_ptr())

    def __call__(self, images, sizes):
        self.buffers["images"].copy_(images)
        self.buffers["orig_target_sizes"].copy_(sizes.to(self.buffers["orig_target_sizes"].dtype))
        self.ctx.execute_async_v3(self.stream.cuda_stream)
        self.stream.synchronize()
        return self.buffers["labels"], self.buffers["boxes"], self.buffers["scores"]


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="RT-DETRv4 source checkout (for the model code)")
    ap.add_argument("--config", help="the checkpoint's config.yaml")
    ap.add_argument("--weights", help="model.pth")
    ap.add_argument("--data", required=True, help="person dataset yaml (its 'val' split is scored)")
    ap.add_argument("--classes", type=int, nargs="+", default=[0, 1],
                    help="model classes that count as person (VisDrone: 0 pedestrian, 1 people)")
    ap.add_argument("--source", default="synthetic",
                    help="'synthetic', or an image directory to time on real frames. Use the "
                         "same directory as the bench_detector.py rows you compare against: "
                         "real frames cost more (resize, more detections) than noise does")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--check-yolo", help="score this Ultralytics model through the same path instead")
    ap.add_argument("--imgsz", type=int, default=960, help="--check-yolo only")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=str(REPO_ROOT / "benchmarks" / "results" / "detector.jsonl"))
    ap.add_argument("--no-tegrastats", action="store_true")
    args = ap.parse_args()

    import numpy as np
    import torch
    from PIL import Image

    images = dataset_images(Path(args.data).expanduser())

    if args.check_yolo:
        from ultralytics import YOLO

        predict = ultralytics_predictor(YOLO(args.check_yolo), args.imgsz, args.classes)
        acc = score(images, predict)
        print(json.dumps({"check_yolo": args.check_yolo, "imgsz": args.imgsz, **acc}))
        return 0

    weights = Path(args.weights).expanduser()
    model, (h, w) = load_rtdetr(Path(args.repo).expanduser(), Path(args.config).expanduser(), weights)
    onnx_path = weights.with_suffix(".onnx")
    engine_path = weights.with_suffix(".engine")
    trtexec_gpu = export_engine(model, (h, w), onnx_path, engine_path)
    del model
    runner = TrtRunner(engine_path)
    keep = torch.tensor(args.classes, device="cuda")

    def infer(frame_u8, orig_w, orig_h):
        """HWC uint8 (already h x w) -> person boxes/scores; everything on the clock."""
        x = torch.from_numpy(frame_u8).cuda().permute(2, 0, 1)[None].float().div_(255)
        labels, boxes, scores = runner(x, torch.tensor([[orig_w, orig_h]], device="cuda"))
        sel = torch.isin(labels[0], keep)
        return boxes[0][sel].float().cpu().numpy(), scores[0][sel].float().cpu().numpy()

    import cv2

    def timed(frame_bgr):
        """A camera frame in, person boxes out: the resize is on the clock, as the
        letterbox is in bench_detector.py's rows."""
        oh, ow = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(frame_bgr, (w, h), interpolation=cv2.INTER_LINEAR),
                           cv2.COLOR_BGR2RGB)
        return infer(rgb, ow, oh)

    # ---- latency: the frames bench_detector.py uses (make_frames), so rows compare
    from bench_detector import make_frames

    for frame in make_frames(args.source, [h, w] if h != w else h, args.warmup):
        timed(frame)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    sampler = None if args.no_tegrastats else TegraSampler()
    if sampler:
        sampler.start()
    lat = []
    wall0 = time.perf_counter()
    for frame in make_frames(args.source, [h, w] if h != w else h, args.frames):
        t0 = time.perf_counter()
        timed(frame)
        torch.cuda.synchronize()
        lat.append((time.perf_counter() - t0) * 1000)
    wall = time.perf_counter() - wall0
    if sampler:
        sampler.stop()

    # ---- accuracy: the engine itself, on real images (resized as in training)
    def predict_engine(p):
        with Image.open(p) as im:
            im = im.convert("RGB")
            ow, oh = im.size
            arr = np.asarray(im.resize((w, h), Image.BILINEAR))
        return infer(arr, ow, oh)

    print(f"scoring {len(images)} images ...")
    acc = score(images, predict_engine)
    acc["dataset"] = args.data

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": "E1",
        "board": "orin-nx-16g",
        "model": weights.parent.name,
        "model_run": str(engine_path),
        "model_sha256_16": sha256_file(weights),
        "precision": "fp16",
        "backend": "engine",
        "harness": "bench_rtdetrv4.py (TensorRT runtime, no Ultralytics)",
        "imgsz": [h, w] if h != w else h,
        "source": args.source,
        "source_is_synthetic": args.source == "synthetic",
        "frames_measured": len(lat),
        "warmup_discarded": args.warmup,
        "latency": percentiles(lat),
        "fps_mean": round(len(lat) / wall, 2),
        "fps_from_mean_latency": round(1000.0 / statistics.fmean(lat), 2),
        "trtexec_gpu_compute": trtexec_gpu,
        "gpu_mem_peak_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        "accuracy": acc,
        "classes_as_person": args.classes,
        "note": args.note,
        "env": collect_env.collect(str(SCRIPT_DIR)),
    }
    if sampler:
        row["tegrastats"] = sampler.summary()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    L = row["latency"]
    print("\n--- result ---")
    print(f"model      {row['model']}  [TensorRT fp16, {h}x{w}]")
    print(f"latency    mean {L['mean_ms']} ms | p95 {L['p95_ms']} ms | max {L['max_ms']} ms  (end to end)")
    print(f"trtexec    {trtexec_gpu}  (GPU compute only)")
    print(f"accuracy   mAP50 {acc['map50']} | mAP50-95 {acc['map50_95']} | P {acc['precision']} | R {acc['recall']}")
    ts = row.get("tegrastats") or {}
    if "board_power_mean_w" in ts:
        print(f"power      {ts['board_power_mean_w']} W mean")
    print(f"appended to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
