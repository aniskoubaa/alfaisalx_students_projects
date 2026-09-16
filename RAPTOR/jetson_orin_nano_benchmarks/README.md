# Jetson Orin Nano Benchmarks

Benchmarking area for running and evaluating the object-detection pipeline directly on the Jetson Orin Nano — first against recorded video, then optimized for real-time performance.

## Suggested layout

- `scripts/` — benchmark/runner scripts (e.g. FPS, latency, and accuracy measurement)
- `models/` — model weights and configs (git-ignored by default — keep large weight files out of git; use Git LFS or external storage if versioning is needed)
- `videos/` — sample/recorded input video used for benchmarking (git-ignored by default)
- `results/` — benchmark logs/output (e.g. CSV/JSON of FPS, latency, mAP per model/config)

## What to track

- Model/framework version (e.g. YOLO variant, TensorRT engine, precision — FP32/FP16/INT8)
- Input resolution and video source
- Inference latency (ms) and throughput (FPS)
- Power mode / clocks (`nvpmodel`, `jetson_clocks`) used during the run
- Detection accuracy vs. the baseline (non-optimized) pipeline
