# 13 — Capture Path and First Live Run

Measured 2026-09-20. Raw row:
[`results/camera.jsonl`](../jetson_orin_nano_benchmarks/results/camera.jsonl).
Annotated frame:
[`figures/live_person_detection.jpg`](../jetson_orin_nano_benchmarks/figures/live_person_detection.jpg).

This is experiment **E3b** from [06](./06-benchmark-plan.md), plus the first
end-to-end run of the deployed model on live frames.

## What is actually attached

**Not the flight camera.** The device on the bench is a **Logitech C922 Pro
Stream Webcam** on USB, not the SIYI A8 mini through an HDMI capture card. It is
a perfectly good stand-in for developing the pipeline, but it means:

- the **HDMI → capture-card path in [01](./01-system-overview.md) and
  [04](./04-ros2-architecture.md) remains unverified**, including the open
  question of whether the A8 mini can output HDMI and Ethernet video at the same
  time — [06](./06-benchmark-plan.md) calls that "cheap and it decides the whole
  harness";
- the optics are wrong for [06](./06-benchmark-plan.md)'s altitude table, which
  assumes the A8 mini's 81° HFOV across 1920 px;
- glass-to-`/dev/video0` latency measured here says nothing about the capture
  card, which is where the tens-to-hundreds of milliseconds would hide.

## The USB link is 2.0, and it matters

```
Bus 001 ... 480M   <- C922 is here, behind a USB2.0 hub
Bus 002 ... 10000M <- USB 3.0 bus, idle
```

[09](./09-jetson-environment.md) warns that a USB 2.0 link degrades silently
rather than failing. Measured, on this device:

| 1920×1080 | Max frame rate |
|---|---|
| **YUYV** (uncompressed) | **5 fps** |
| **MJPG** (compressed) | **30 fps** |

So the trade named in doc 09 — "YUYV costs USB bandwidth, MJPEG costs a decode" —
is not theoretical here: uncompressed 1080p is simply unavailable at frame rate.
**There is an idle USB 3.0 bus on this board.** Moving the camera to it is the
first thing to try before accepting MJPEG.

## First live run: camera → deployed TensorRT pose engine

`yolo11s-pose.engine` @960 FP16, from `~/raptor-deploy/`, on live 1080p MJPG:

| | |
|---|---|
| Negotiated format | 1920×1080 MJPG @30 (as requested) |
| Frame grab | 14.1 ms mean / 15.0 ms p95 |
| Inference | 23.0 ms mean / 25.0 ms p95 |
| **End-to-end** | **26.9 FPS, 0 dropped of 150** |
| Board power | 12.1 W |

Detection was confirmed visually: a person at **0.78 confidence with all 17 COCO
keypoints**, which is exactly the input tier 2's posture classifier consumes.

### The 27 FPS is an artefact of the test loop, not a ceiling

Grab (14.1 ms) and inference (23.0 ms) run **serially** in this benchmark, so the
frame period is their sum. In the architecture [04](./04-ros2-architecture.md)
specifies — `camera_node` and `detector_node` as separate nodes — they pipeline,
and the rate is set by the slower stage alone:

- inference at 23.0 ms → ~43 FPS of headroom
- capture capped at 30 FPS by the device

So **30 FPS is reachable** on this hardware once capture and inference overlap.
This is a concrete argument for composable nodes with intra-process transport,
and a reason not to read 26.9 FPS as a hardware limit.

### One honest oddity

The 0.78-confidence detection was of a **hand** entering frame, not a whole
person. A pose model inferring a body from one visible limb is reasonable
behaviour, but it is a preview of the false-positive class that
[08](./08-limitations-and-safety.md)'s triage rules must absorb — and a reminder
that a bare detection count is not a victim count.

## What to do next on the capture path

1. **Move the camera to the USB 3.0 bus** and re-measure; uncompressed YUYV at
   1080p30 may become available, removing the MJPEG decode entirely.
2. **Get the real hardware on the bench** — A8 mini plus capture card — and
   re-run this experiment. Nothing above transfers to it.
3. **Test the HDMI/Ethernet simultaneity question** from
   [01](./01-system-overview.md). It is cheap and it decides the harness.
4. **Measure glass-to-`/dev/video0` latency** against a millisecond timer on a
   monitor, once the capture card is present. It is invisible otherwise.
5. **Re-measure with capture and inference pipelined**, not serial, to confirm
   the 30 FPS claim above rather than inferring it.

## Running it: the live demo

Two launchers exist so the pipeline can be shown without a command line.

### On the Jetson — full video window

Log in on the board's own monitor and double-click **RAPTOR Live Demo** on the
desktop (`~/Desktop/RAPTOR-Live-Demo.desktop` → `~/raptor-live-demo.sh`).

The window shows person boxes, the 17 keypoints, a posture label per person, and
a HUD with frame rate, the grab/inference split, board power and temperature. The
launcher runs in a terminal deliberately, so a failure is readable rather than a
window that flashes and vanishes; it preflights the venv, the engine, and
`/dev/video0` and explains what to do for each.

### From the laptop — text output

Double-click **RAPTOR Live Demo.bat** on the Windows desktop. It checks the board
is reachable and the camera present, then streams detections, postures and
timings. Video frames stay on the Jetson.

**An SSH session cannot open a window on the board's console.** Until someone logs
in locally, the X server belongs to GDM and a remote process has no credentials
for it. The demo detects this and falls back to text rather than crashing — a
subprocess probe is used, because Qt calls `abort()` on a failed display
connection rather than raising something catchable.

Measured on the bench camera: **~24 FPS, 21.6 ms inference**.

### The posture label is not flight tier 2

[02](./02-detection-and-pose.md) specifies posture from keypoints rotated into a
**gravity-aligned** frame using the drone's IMU attitude from MAVROS. There is no
IMU on the bench, so the demo uses image vertical instead. That is correct for a
fixed camera and **wrong the moment the aircraft banks** — a standing person in a
banked turn would read as "lying". The screen carries `(no IMU)` for exactly this
reason, and the on-board version must not ship without the attitude feed.

The geometry itself is verified:

| Input | Result |
|---|---|
| Upright torso | `standing` (0°) |
| Horizontal torso | `LYING` (88°) |
| 45° lean | `leaning/sitting` (45°) |
| Hips below confidence threshold | `unknown` — not a guess |

That last row is the important one: the classifier declines to answer when the
keypoints it needs are not visible, rather than inventing a posture from
whatever is in frame.
