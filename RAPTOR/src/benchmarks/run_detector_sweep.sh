#!/usr/bin/env bash
# E1 detector sweep from 06-benchmark-plan.md.
#
# Holds the power mode fixed (models must be compared under identical
# conditions) and varies model x task x input size. Detection models also get an
# accuracy pass against the VisDrone person proxy set; pose models do not,
# because that set has no keypoint labels.
#
# Runs ON THE JETSON, inside ~/raptor-venv. Every path below can be overridden
# with an environment variable of the same name, e.g.
#
#   ./run_detector_sweep.sh                                  # defaults below
#   FRAMES=100 ./run_detector_sweep.sh /tmp/quick.jsonl      # shorter run, other file
#
# Data layout it expects on the board (outside the repo - weights and datasets
# are too large for git):
#   ~/raptor-models/        yolo11*.pt weights
#   ~/raptor-data/          VisDrone person set (prepare_visdrone_person.py)
#   ~/raptor-results/       where the JSONL lands unless an argument is given
set -u

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

PY="${PY:-$HOME/raptor-venv/bin/python}"
BENCH="${BENCH:-$HERE/bench_detector.py}"
MODELS="${MODELS:-$HOME/raptor-models}"
DATA="${DATA:-$HOME/raptor-data/visdrone-person/visdrone_person.yaml}"
IMAGES="${IMAGES:-$HOME/raptor-data/visdrone-person/images/val}"
OUT="${1:-$HOME/raptor-results/detector.jsonl}"
FRAMES="${FRAMES:-200}"
WARMUP="${WARMUP:-50}"

echo "=== E1 sweep ==="
echo "power mode: $(sudo -n nvpmodel -q 2>/dev/null | grep -i 'power mode' || echo unknown)"
echo "results   : $OUT"
echo

run() {
  local model="$1" imgsz="$2" extra="${3:-}"
  local name
  name="$(basename "$model" .pt)"
  echo "--- $name @ ${imgsz} ${extra} ---"
  # shellcheck disable=SC2086
  "$PY" "$BENCH" \
    --model "$MODELS/$model" \
    --imgsz "$imgsz" \
    --source "$IMAGES" \
    --frames "$FRAMES" \
    --warmup "$WARMUP" \
    --half \
    --classes 0 \
    --board orin-nx-16g \
    --out "$OUT" \
    --note "e1-sweep" \
    $extra 2>&1 | grep -vE "UserWarning|_warn_unsupported_code|^- [0-9]+\.[0-9]+ which|^The following list|^No published PyTorch"
  echo
}

# Detection models: latency + person mAP on the aerial proxy set.
for imgsz in 640 832 960; do
  for model in yolo11n.pt yolo11s.pt; do
    run "$model" "$imgsz" "--accuracy --data $DATA"
  done
done

# The accuracy ceiling reference, at the base size only.
run yolo11m.pt 640 "--accuracy --data $DATA"

# Pose models: latency only. Tier 2 needs keypoints, and the plan's own
# recommendation is one pose model rather than a separate detector.
for imgsz in 640 832 960; do
  for model in yolo11n-pose.pt yolo11s-pose.pt; do
    run "$model" "$imgsz"
  done
done

echo "=== sweep complete ==="
wc -l "$OUT"
