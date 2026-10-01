# demo/ — the live demo

Runs the deployed models (`~/raptor-deploy`) on the live camera. Two modes:

- **Bench** (the default, and the **RAPTOR Live Demo** icon) — for people in a room.
  YOLO26s-pose (384×640 engine) on the whole frame finds each person and their 17
  keypoints; a tracker keeps one steady box per person; posture comes from the legs,
  smoothed over time; and the VLM (Qwen3-VL-2B) double-checks each person's posture
  about once a second in the background.
- **Aerial** (`--mode aerial`, the **RAPTOR Live Demo (aerial model)** icon) — the
  flight pipeline. The aerial-trained detector (YOLO26s on VisDrone, 736×1280, lean
  TensorRT runner in `src/common/trt_yolo.py`) on every frame, the same tracker, and
  YOLO26s-pose on crops of each person every fifth frame (people ≥ 64 px tall).

The screen shows one box per person with an id, keypoints, a posture label and the
VLM's answer, and a HUD with frame rate, timings, the people count, board power and
temperature. Measured on the bench camera (2026-09-29): **30 FPS at 1080p** (the
camera's maximum), **60 FPS at 720p**, 43 FPS at 720p with the VLM check running
([docs/14](../../docs/14-camera-demo-and-remote-access.md)).

**Use the aerial mode on aerial scenes only.** It is trained on small people seen
from a drone. In a room it misses people close to the camera and mistakes empty
chairs for seated people. To show the flight pipeline without an aircraft, play
aerial images or a video with `--source`.

## Running it

**On the Jetson — video window.** Log in on the board's own screen, or over VNC
(`100.100.100.1:5900`), and double-click **RAPTOR Live Demo** (bench) or **RAPTOR
Live Demo (aerial model)**. Press `q` or `Esc` in the video window to stop.

**From the laptop — text only.** Double-click `RAPTOR-Live-Demo.bat`. It checks the
board is reachable and the camera present, then streams people, postures and
timings. The video stays on the Jetson.

**From a terminal on the board:**

```bash
source ~/raptor-venv/bin/activate
python3 ~/raptor/src/demo/raptor_live_demo.py              # bench, window
python3 ~/raptor/src/demo/raptor_live_demo.py --width 1280 --height 720 --fps 60   # 60 FPS
python3 ~/raptor/src/demo/raptor_live_demo.py --no-vlm     # without the VLM check
python3 ~/raptor/src/demo/raptor_live_demo.py --no-display --max-frames 300 --stats   # text + summary
python3 ~/raptor/src/demo/raptor_live_demo.py --record out.mp4
python3 ~/raptor/src/demo/raptor_live_demo.py --mode aerial --source ~/raptor-data/visdrone-person/images/val
python3 ~/raptor/src/demo/catch_person.py                  # save one annotated frame
```

The old mode names still work: `--mode pose-only` is bench, `--mode two-stage` is aerial.

## Files

| File | Runs on | What it is |
|---|---|---|
| `raptor_live_demo.py` | Jetson | The demo itself. The camera, tracking, posture and VLM parts live in `src/common/` (`live_camera.py`, `person_tracker.py`, `posture.py`, `vlm_posture.py`) so the flight pipeline can reuse them. |
| `launch_demo.sh` | Jetson | What the desktop icons run: checks the venv, the engines the mode needs, a USB camera, and that no other copy is running; explains any problem in plain words, then starts the demo. Extra arguments are passed through. |
| `RAPTOR-Live-Demo.desktop` | Jetson | The bench icon. Install: `cp RAPTOR-Live-Demo.desktop ~/Desktop/ && gio set ~/Desktop/RAPTOR-Live-Demo.desktop metadata::trusted true` |
| `RAPTOR-Live-Demo-Aerial.desktop` | Jetson | The icon for `--mode aerial`. Install the same way. |
| `RAPTOR-Live-Demo.bat` | laptop | Runs the demo over SSH and shows its output. Copy it to the Windows desktop. |
| `catch_person.py` | Jetson | Waits for a person to appear and saves that frame, annotated. Headless. |

## What the screen does *not* tell you

**The posture label is not the flight tier 2.** [docs/02](../../docs/02-detection-and-pose.md)
specifies posture from keypoints rotated into a *gravity-aligned* frame using the
drone's attitude from the flight controller. There is no flight controller on the
bench, so the demo measures angles against the *image* vertical instead — correct
for a camera that does not move, wrong the moment the aircraft banks. The HUD says
so. The rule (`src/common/posture.py`) looks at the legs, because the torso alone
cannot tell sitting from standing — the first demo called a seated person
"standing" for exactly that reason:

| Keypoints | Label |
|---|---|
| torso more than 60° from vertical | `LYING` (drawn in red) |
| thigh more than 50° from vertical (side view), or knee less than 0.45 torso lengths below the hip (front view) | `sitting` |
| hip–knee–ankle angle under 120° | `crouching` |
| thigh vertical and long, torso upright | `standing` |
| torso upright, knees not visible (desk, table, frame edge) | `upright, legs hidden` — not a guess |
| shoulders or hips not visible | `unknown` |

Each person's label is the majority of their last 7 estimates, so a single bad
frame does not flip it.

**The VLM's word is a second opinion, not ground truth.** It is asked about one
person at a time, only when their torso is visible (with only an arm in view it
guessed). It answered in 0.4–0.7 s and agreed with what people were doing in every
check on 2026-09-29, but no small VLM has a published posture benchmark, and one
2025 study found VLMs confuse *fallen* with *lying down*. When the two disagree,
believe neither and look.

**A person on screen is a confirmed track.** A detection must persist for 3 frames
before it is drawn, and a person missed for a few frames is held (thin box) rather
than dropped. That removed the flicker and most false people, at the cost of a
tenth of a second before someone new appears.

## If it does not start

The launcher explains most problems itself. The usual ones:

- **"could not open a window"** — it was started from SSH, which cannot draw on the
  board's screen. It carries on in text mode. Use VNC to see the window.
- **"no USB camera found"** — plug the camera in, **directly into the board** if you
  can. On 2026-09-29 the webcam dropped off USB through the hub; the demo now finds
  it again by itself (the HUD shows *camera lost - reconnecting*).
- **"already running"** — another copy holds the camera. Find its window, or close it.
- **"TensorRT engine missing"** — the launcher prints the command that rebuilds it.
- **Zero people detected** — check where the camera is pointing, and the mode: the
  aerial model rarely sees people close to the camera.
- **Frame rate low in dim light** — the webcam may slow its own frame rate to expose
  longer (`exposure_dynamic_framerate=1`). The demo switches this off when it opens
  the camera; the image may be darker as a result.
