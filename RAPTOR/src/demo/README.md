# demo/ — the live demo

Runs the deployed models (`~/raptor-deploy`, since 2026-09-29) on the live camera in two
stages, the way the aircraft would:

- **Tier 1, on every frame:** the aerial-trained detector (YOLO26s on VisDrone,
  736×1280), run by the lean TensorRT runner in `src/common/trt_yolo.py`.
- **Tier 2, every fifth frame:** YOLO26s-pose on crops of each person tall enough for
  keypoints (≥ 64 px). The resulting posture label is carried between pose passes.

The screen shows a box per person, keypoints and a posture label where there are
enough pixels, and a HUD with frame rate, detection and pose timings, board power and
temperature. Measured on the bench camera: **~24 FPS, 20.8 ms detection** per 1080p
frame ([docs/14](../../docs/14-camera-demo-and-remote-access.md)).

**The aerial detector may not see someone next to the desk webcam.** It is trained on
small people seen from above. For close-up bench demos use `--mode pose-only` (the
**RAPTOR Live Demo (bench)** icon). To show the real pipeline without an aircraft,
play aerial images or a video with `--source`.

## Running it

**On the Jetson — video window.** Log in on the board's own screen, or over VNC
(`100.100.100.1:5900`), and double-click **RAPTOR Live Demo** (the aerial pipeline) or
**RAPTOR Live Demo (bench)** (the pose model alone, for people close to the camera).
Press `q` or `Esc` in the video window to stop.

**From the laptop — text only.** Double-click `RAPTOR-Live-Demo.bat`. It checks the
board is reachable and the camera present, then streams detections, postures and
timings. The video stays on the Jetson.

**From a terminal on the board:**

```bash
source ~/raptor-venv/bin/activate
python3 ~/raptor/src/demo/raptor_live_demo.py              # window
python3 ~/raptor/src/demo/raptor_live_demo.py --no-display # text only, works over SSH
python3 ~/raptor/src/demo/raptor_live_demo.py --record out.mp4
python3 ~/raptor/src/demo/raptor_live_demo.py --mode pose-only   # bench / close-up
python3 ~/raptor/src/demo/raptor_live_demo.py --source ~/raptor-data/visdrone-person/images/val
python3 ~/raptor/src/demo/catch_person.py                  # save one annotated frame
```

## Files

| File | Runs on | What it is |
|---|---|---|
| `raptor_live_demo.py` | Jetson | The demo itself. |
| `launch_demo.sh` | Jetson | What the desktop icons run: checks the venv, both engines and the camera, explains any problem in plain words, then starts the demo. Extra arguments are passed through. |
| `RAPTOR-Live-Demo.desktop` | Jetson | The icon for the aerial pipeline. Install: `cp RAPTOR-Live-Demo.desktop ~/Desktop/ && gio set ~/Desktop/RAPTOR-Live-Demo.desktop metadata::trusted true` |
| `RAPTOR-Live-Demo-Bench.desktop` | Jetson | The icon for `--mode pose-only`. Install the same way. |
| `RAPTOR-Live-Demo.bat` | laptop | Runs the demo over SSH and shows its output. Copy it to the Windows desktop. |
| `catch_person.py` | Jetson | Waits for a person to appear and saves that frame, annotated. Headless. |

## What the screen does *not* tell you

**The posture label is not the flight tier 2.** [docs/02](../../docs/02-detection-and-pose.md)
specifies posture from keypoints rotated into a *gravity-aligned* frame using the
drone's attitude from the flight controller. There is no flight controller on the
bench, so the demo measures the torso's angle against the *image* vertical instead —
correct for a camera that does not move, wrong the moment the aircraft banks, when a
standing person would read as lying. The screen says `(no IMU)` for exactly this
reason. The classifier is deliberately coarse and answers `unknown` rather than
guessing when the shoulders or hips are not confidently visible:

| Torso angle from vertical | Label |
|---|---|
| under 30° | `standing` |
| 30°–60° | `leaning/sitting` |
| over 60° | `LYING` (drawn in red) |
| shoulders or hips not visible | `unknown` |

**A detection is not a person count.** The first live capture detected a *hand*
entering the frame as a person at 0.78 confidence — reasonable for a pose model
inferring a body from one limb, and a preview of the false positives the triage rules
in [docs/08](../../docs/08-limitations-and-safety.md) have to absorb.

**27 FPS here is not the hardware limit.** The demo grabs a frame, then runs the
model, one after the other, so the frame time is their sum. In the real system,
capture and inference run as separate ROS 2 nodes and overlap; inference alone has
headroom for about 45 FPS, and the camera tops out at 30.

## If it does not start

The launcher explains most problems itself. The usual ones:

- **"could not open a window"** — it was started from SSH, which cannot draw on the
  board's screen. It carries on in text mode. Use VNC to see the window.
- **"no camera at /dev/video0"** — plug the camera in. Prefer a **USB 3.0** port: on
  USB 2.0, uncompressed 1080p drops to 5 fps.
- **"TensorRT engine missing"** — the launcher prints the command that rebuilds it.
- **Zero people detected** — check where the camera is pointing.
- **Frame rate drops to ~15 FPS in dim light** — not a software fault. The USB webcam
  is allowed to slow its own frame rate to expose longer (`exposure_dynamic_framerate=1`);
  measured, a frame grab went from 14 ms to 39 ms with inference unchanged. To force
  full rate at the cost of a darker image:
  `v4l2-ctl -d /dev/video0 -c exposure_dynamic_framerate=0`.
