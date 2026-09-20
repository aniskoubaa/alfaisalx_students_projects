#!/usr/bin/env bash
# RAPTOR live demo launcher.
#
# Double-clicked from the desktop, so it must explain itself when something is
# wrong rather than flashing a terminal and vanishing. Every failure path prints
# what to do and waits for a keypress.

VENV="$HOME/raptor-venv"
DEMO="$HOME/raptor-bench-scripts/raptor_live_demo.py"
MODEL="$HOME/raptor-deploy/pose/yolo11s-pose.engine"

hold() {
    echo
    echo "Press Enter to close this window."
    read -r _
}

clear
cat <<'BANNER'
 ____      _    ____ _____ ___  ____
|  _ \    / \  |  _ \_   _/ _ \|  _ \    live perception demo
| |_) |  / _ \ | |_) || || | | | |_) |   tier 1 + 2: detect + pose + posture
|  _ <  / ___ \|  __/ | || |_| |  _ <
|_| \_\/_/   \_\_|    |_| \___/|_| \_\
BANNER
echo

# --- preflight, with actionable messages -------------------------------------
if [ ! -d "$VENV" ]; then
    echo "ERROR: project venv missing at $VENV"
    echo "  See docs/09-jetson-environment.md to recreate it."
    hold; exit 1
fi

if [ ! -f "$DEMO" ]; then
    echo "ERROR: demo script missing at $DEMO"
    hold; exit 1
fi

if [ ! -f "$MODEL" ]; then
    echo "ERROR: TensorRT engine missing at $MODEL"
    echo "  Rebuild it with:"
    echo "    $VENV/bin/python ~/raptor-bench-scripts/bench_detector.py \\"
    echo "        --model ~/raptor-models/yolo11s-pose.pt --imgsz 960 --export engine --half"
    hold; exit 1
fi

if [ ! -e /dev/video0 ]; then
    echo "ERROR: no camera at /dev/video0"
    echo "  Plug the camera in, then check:  v4l2-ctl --list-devices"
    echo "  Prefer a USB 3.0 port - on USB 2.0, 1080p uncompressed drops to 5 fps."
    hold; exit 1
fi

# A double-click from the file manager usually inherits DISPLAY; a terminal over
# SSH does not. Default to the local seat rather than failing obscurely.
export DISPLAY="${DISPLAY:-:0}"

echo "camera : $(v4l2-ctl --list-devices 2>/dev/null | head -1)"
echo "model  : $(basename "$MODEL")"
echo "display: $DISPLAY"
echo
echo "Starting. The window takes a few seconds to appear while TensorRT loads."
echo "Press  q  or  ESC  in the video window to stop."
echo

"$VENV/bin/python" "$DEMO" --model "$MODEL" "$@"
status=$?

echo
if [ $status -ne 0 ]; then
    echo "The demo exited with status $status (see the error above)."
else
    echo "Demo finished."
fi
hold
exit $status
