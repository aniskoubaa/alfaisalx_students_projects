#!/usr/bin/env bash
# RAPTOR live demo launcher.
#
# Runs ON THE JETSON. Started by double-clicking RAPTOR-Live-Demo.desktop, so it
# must explain itself when something is wrong rather than flashing a terminal and
# vanishing. Every failure path prints what to do and waits for a keypress.
#
# Checks, in order: venv present, demo script present, both TensorRT engines
# present (aerial detector + pose), camera present - then launches
# raptor_live_demo.py from this same folder, in its two-stage mode.

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
VENV="$HOME/raptor-venv"
DEMO="$HERE/raptor_live_demo.py"
DETECTOR="$HOME/raptor-deploy/detector/visdrone-yolo26s-736x1280.engine"
POSE="$HOME/raptor-deploy/pose/yolo26s-pose-960.engine"

hold() {
    echo
    echo "Press Enter to close this window."
    read -r _
}

clear
cat <<'BANNER'
 ____      _    ____ _____ ___  ____
|  _ \    / \  |  _ \_   _/ _ \|  _ \    live perception demo
| |_) |  / _ \ | |_) || || | | | |_) |   tier 1: aerial detector, every frame
|  _ <  / ___ \|  __/ | || |_| |  _ <    tier 2: pose + posture on crops
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

for ENGINE in "$DETECTOR" "$POSE"; do
    if [ ! -e "$ENGINE" ]; then
        echo "ERROR: TensorRT engine missing at $ENGINE"
        echo "  Stage the deployed set with:"
        echo "    $VENV/bin/python ~/raptor/src/deploy/deploy_models.py --root ~/raptor-deploy \\"
        echo "        --models ~/raptor-models --vlm ~/raptor-vlm --results ~/raptor-results --verify"
        hold; exit 1
    fi
done

if [ ! -e /dev/video0 ]; then
    echo "ERROR: no camera at /dev/video0"
    echo "  Plug the camera in, then check:  v4l2-ctl --list-devices"
    echo "  Prefer a USB 3.0 port - on USB 2.0, 1080p uncompressed drops to 5 fps."
    hold; exit 1
fi

# A double-click from the file manager usually inherits DISPLAY; a terminal over
# SSH does not. Default to the local seat rather than failing obscurely.
export DISPLAY="${DISPLAY:-:0}"

# Name the device actually opened. (`--list-devices | head -1` reported the
# board's built-in CSI interface, not the USB camera on /dev/video0.)
echo "camera : $(v4l2-ctl -d /dev/video0 --info 2>/dev/null | sed -n 's/.*Card type *: *//p')"
echo "tier 1 : $(basename "$DETECTOR")  (aerial-trained, lean TensorRT)"
echo "tier 2 : $(basename "$POSE")  (on crops)"
echo "display: $DISPLAY"
echo
echo "Starting. The window takes a few seconds to appear while TensorRT loads."
echo "Press  q  or  ESC  in the video window to stop."
echo

# Console is 1024x768 headless (no EDID to negotiate 1080p), so scale the
# window to fit rather than opening one wider than the screen.
"$VENV/bin/python" "$DEMO" --window-scale 0.5 "$@"
status=$?

echo
if [ $status -ne 0 ]; then
    echo "The demo exited with status $status (see the error above)."
else
    echo "Demo finished."
fi
hold
exit $status
