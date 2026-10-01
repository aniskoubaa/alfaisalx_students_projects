#!/usr/bin/env bash
# RAPTOR live demo launcher.
#
# Runs ON THE JETSON. Started by double-clicking a RAPTOR desktop icon, so it
# must explain itself when something is wrong rather than flashing a terminal and
# vanishing. Every failure path prints what to do and waits for a keypress.
#
# Checks, in order: venv present, demo script present, the engines the chosen
# mode needs, a USB camera present, and no other copy already running - then
# launches raptor_live_demo.py from this same folder. Arguments are passed
# through: no arguments = bench mode; "--mode aerial" = the flight pipeline.

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
VENV="$HOME/raptor-venv"
DEMO="$HERE/raptor_live_demo.py"
DETECTOR="$HOME/raptor-deploy/detector/visdrone-yolo26s-736x1280.engine"
POSE="$HOME/raptor-deploy/pose/yolo26s-pose-960.engine"
BENCH_POSE="$HOME/raptor-deploy/pose_bench/yolo26s-pose-384x640.engine"
VLM="$HOME/raptor-deploy/vlm/Qwen3-VL-2B-Instruct"
LOCK=/tmp/raptor_live_demo.lock

hold() {
    echo
    echo "Press Enter to close this window."
    read -r _
}

MODE=bench
case " $* " in
    *" --mode aerial "*|*" --mode two-stage "*|*" --mode=aerial "*|*" --mode=two-stage "*) MODE=aerial ;;
esac

clear
cat <<'BANNER'
 ____      _    ____ _____ ___  ____
|  _ \    / \  |  _ \_   _/ _ \|  _ \    live perception demo
| |_) |  / _ \ | |_) || || | | | |_) |
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

NEED="$POSE"
[ "$MODE" = aerial ] && NEED="$DETECTOR $POSE"
for ENGINE in $NEED; do
    if [ ! -e "$ENGINE" ]; then
        echo "ERROR: TensorRT engine missing at $ENGINE"
        echo "  Stage the deployed set with:"
        echo "    $VENV/bin/python ~/raptor/src/deploy/deploy_models.py --root ~/raptor-deploy \\"
        echo "        --models ~/raptor-models --vlm ~/raptor-vlm --results ~/raptor-results --verify"
        hold; exit 1
    fi
done

# The camera is found by its USB path: after a USB drop-out it can come back as
# /dev/video1 instead of /dev/video0 (seen 2026-09-29).
CAM=""
for LINK in /dev/v4l/by-id/*-video-index0 /dev/v4l/by-path/*usb*-video-index0; do
    [ -e "$LINK" ] && CAM="$(readlink -f "$LINK")" && break
done
if [ -z "$CAM" ]; then
    echo "ERROR: no USB camera found."
    echo "  Plug the camera in (directly into the board if you can, not through a hub),"
    echo "  then check:  v4l2-ctl --list-devices"
    hold; exit 1
fi

# One copy at a time: a second one gets no frames from the camera and looks frozen.
if ! flock -n "$LOCK" true 2>/dev/null; then
    echo "The RAPTOR demo is already running - it holds the camera."
    echo "  Look for its window (it may be behind this one), or close it and try again."
    hold; exit 1
fi

# A double-click from the file manager usually inherits DISPLAY; a terminal over
# SSH does not. Default to the local seat rather than failing obscurely.
export DISPLAY="${DISPLAY:-:0}"

echo "camera : $(v4l2-ctl -d "$CAM" --info 2>/dev/null | sed -n 's/.*Card type *: *//p')  ($CAM)"
if [ "$MODE" = aerial ]; then
    echo "mode   : AERIAL - the flight pipeline: aerial detector on every frame, pose on crops"
    echo "         Trained on people seen from a drone. Indoors it misses people close to"
    echo "         the camera and can mistake chairs for seated people - use the bench icon."
else
    echo "mode   : BENCH - pose model on the whole frame, tracker, posture from the legs"
    echo "pose   : $(basename "$([ -e "$BENCH_POSE" ] && echo "$BENCH_POSE" || echo "$POSE")")"
    [ -d "$VLM" ] && echo "VLM    : $(basename "$VLM") checks each person's posture (loads in ~10 s)"
fi
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
