# 14 — Camera, Live Demo and Remote Access

Measured 2026-09-20. Raw row:
[`results/camera.jsonl`](../benchmarks/results/camera.jsonl).
Annotated frame:
[`figures/live_person_detection.jpg`](../benchmarks/figures/live_person_detection.jpg).

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

Log in on the board's own monitor and double-click one of the two icons on the
desktop. Both run `~/raptor/src/demo/launch_demo.sh`; the source is in
[`src/demo/`](../src/demo/README.md).

| Icon | What runs | Use it for |
|---|---|---|
| **RAPTOR Live Demo** | **Bench mode** (the default since the 2026-09-29 fix, below). YOLO26s-pose (384×640 engine) on the whole frame, a tracker that keeps one steady box per person, posture from the legs, and the VLM (Qwen3-VL-2B) double-checking each person's posture about once a second. | People in a room, near the webcam. |
| **RAPTOR Live Demo (aerial model)** | `--mode aerial`: the flight pipeline. The aerial detector (YOLO26s on VisDrone, 736×1280, lean TensorRT runner) on every frame, the same tracker, and YOLO26s-pose on crops of each person every fifth frame (people at least 64 px tall). | Showing the flight pipeline on a scene seen from above, or on aerial footage with `--source`. |

**Why the aerial model is not the default.** It is trained on small people seen
from a drone. Indoors it misses people close to the camera and mistakes chairs for
seated people (VisDrone's *people* class means people who are not walking, and
from above an empty chair looks like one). That is the model doing what it was
trained for, not a fault - but it is the wrong model for a desk demo.

To show the flight pipeline without an aircraft, play aerial images or a video
through it:

```bash
~/raptor-venv/bin/python ~/raptor/src/demo/raptor_live_demo.py --mode aerial \
    --source ~/raptor-data/visdrone-person/images/val
```

![The deployed two-stage pipeline on a VisDrone frame](../benchmarks/figures/live_two_stage_demo.jpg)

*The aerial detector finds four people. Pose on the nearest one's crop gives the
skeleton and "standing (11°)". The HUD shows both stages' timings and board power.*

The window shows person boxes, keypoints where there are enough pixels for them, a
posture label, and a HUD with frame rate, detection and pose timings, board power
and temperature. The launcher runs in a terminal deliberately, so a failure is
readable rather than a window that flashes and vanishes. It preflights the venv,
the engines the mode needs, a USB camera (found by its USB path, not as
`/dev/video0`) and that no other copy is running, and explains what to do for each.

### From the laptop — text output

Double-click **RAPTOR Live Demo.bat** on the Windows desktop. It checks the board
is reachable and the camera present, then streams detections, postures and
timings. Video frames stay on the Jetson.

**An SSH session cannot open a window on the board's console.** Until someone logs
in locally, the X server belongs to GDM and a remote process has no credentials
for it. The demo detects this and falls back to text rather than crashing — a
subprocess probe is used, because Qt calls `abort()` on a failed display
connection rather than raising something catchable.

Measured on the bench camera:

- **2026-09-20, single pose model:** ~24 FPS, 21.6 ms inference.
- **2026-09-29 morning, two-stage pipeline:** ~24 FPS on an empty scene, 20.8 ms
  detection per 1080p frame; about 17 FPS with people in view.
- **2026-09-29 after the fix, bench mode:** 30 FPS at 1080p (the camera's maximum),
  60 FPS at 720p; 43 FPS at 720p with the VLM check running. Aerial mode: 30 FPS.
- **On VisDrone images:** 27 FPS, 25 ms detection, and 28–50 ms per pose pass.

On the webcam the camera sets the frame rate, not the models: the C922 gives at
most 30 fps at 1080p and 60 fps at 720p (`--width 1280 --height 720 --fps 60`).

### 2026-09-29: why the first live demo misbehaved, and the fix

Reported after the first run of the two-stage demo: it crashed, counted one person
as several, flickered, ran at about 17 FPS, and called a seated person "standing".
Each was reproduced on the bench camera and traced to a cause. Most were code, not
models. Raw numbers: `benchmarks/results/live_demo_fix_2026-09-29.json`.

| Symptom | Cause (measured) | Fix |
|---|---|---|
| "Crashed" | The webcam dropped off USB (`dmesg`: *usb 1-2.3: USB disconnect*) and came back as `/dev/video1`; the demo only knew `/dev/video0`. Two copies of the demo were also running at once, fighting over the camera. | `src/common/live_camera.py` finds the camera by its USB path and re-opens it by itself; one copy at a time (a lock). Plug the camera straight into the board, not through a hub. |
| One person counted as several, flickering | The aerial detector, on a room: 0 to 5 "people" per frame for two real people, the count changing on 65 of 149 frames. It boxed the seated man's head and body separately, an empty chair, and his reflection. The COCO pose model also returned the same man twice (whole body and upper body, IoU 0.66, under the 0.7 threshold). Nothing remembered people between frames. | Bench mode uses the COCO pose model, not the aerial detector. `src/common/person_tracker.py` removes nested and overlapping boxes, tracks with ByteTrack, shows a person only after 3 frames and holds them through short misses. After: 1 to 7 count changes in 400 frames, with people really coming and going. |
| Seated person labelled "standing" | The rule looked only at the torso: upright torso = standing. The legs decide sitting vs standing. Every label the old rule gave the seated man (191) was "standing". | `src/common/posture.py`: sitting when the thigh is near horizontal (side view) or the knee barely below the hip (front view); "upright, legs hidden" instead of a guess when the knees are not visible; a vote over the last 7 estimates. Plus the VLM check. |
| About 17 FPS | Serial loop: decoding each 1080p JPEG took 22 ms on the CPU, then 22 ms detection, then pose passes. The camera was also set to slow down in dim light (`exposure_dynamic_framerate=1`). | Capture and decoding on their own thread; the dim-light slow-down switched off; a 384×640 pose engine (9.7 ms per frame against 19.6 ms at 960); only the HUD panel blended. |

The VLM check asks Qwen3-VL-2B one question about one person's crop - standing,
sitting or lying, one word - in a background thread, so the video never waits.
It takes about 0.7 s per answer while the video runs (0.41 s alone), and said
"sitting" for the seated man on every check. With only an arm in view its answer
is a guess, so it is asked only about people whose torso is visible. It slows the
video briefly when it runs (lowest 5 % of frames: 15 FPS at 1080p); `--no-vlm`
turns it off.

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

## Remote access: VNC to the console

`x11vnc` mirrors the **console display** so the board can be driven from the
laptop, including running the demo and watching its video window.

| Field | Value |
|---|---|
| Protocol | VNC |
| Host | `100.100.100.1` |
| Port | `5900` (display `:0`) |
| Password | stored in `/etc/x11vnc.pass` |

Change the password with `sudo x11vnc -storepasswd <new> /etc/x11vnc.pass`, then
`sudo systemctl restart x11vnc`.

### Why it mirrors `:0` rather than serving a virtual desktop

GDM on this board runs **X11**, not Wayland (`WaylandEnable=false` in
`/etc/gdm3/custom.conf`), so the real screen can be captured. You get the actual
console — the login screen, then the desktop — and anything started there. A
TigerVNC virtual desktop would have been a second, disconnected session instead.

Had the board been on Wayland, none of this would work: classic VNC servers
cannot capture a Wayland compositor, and GNOME 46 dropped VNC from
`gnome-remote-desktop` in favour of RDP.

### The Xauthority problem, and why there is a wrapper script

x11vnc must authenticate to the X server. The obvious `-auth guess` **fails here**:

```
xauth: unable to generate an authority file name
-auth guess: failed for display=':0'
```

Two causes. A systemd service has no `HOME`, so `xauth` cannot even construct a
filename; and the greeter's authority file is owned by `gdm` in a location the
guesser does not find.

`/usr/local/sbin/raptor-x11vnc-start` fixes both: it sets `HOME`, then reads the
authority path **straight off the running Xorg command line**, which is always
authoritative:

```
$ ps -eo args | grep '[X]org'
/usr/lib/xorg/Xorg vt1 -displayfd 3 -auth /run/user/121/gdm/Xauthority ...
```

This matters beyond first setup: **the authority file changes when someone logs
in**, because the greeter session is replaced. The unit uses `Restart=always`, so
x11vnc dies with the old X server, restarts, re-derives the new display and
authority, and the VNC session follows you from the login screen into the desktop.

### Security

The traffic is **unencrypted** and a VNC password is weak protection. Acceptable
on the direct point-to-point cable to the laptop, which is the current setup. If
this board ever joins a shared network, bind x11vnc to localhost and reach it
through an SSH tunnel instead.

### Two things that broke, and why

**1. Authentication failed from every client.** The server log was unambiguous:

```
rfbProcessClientSecurityType: executing handler for type 2
rfbAuthProcessClientMessage: password check failed
```

The client connected and negotiated correctly; only the password was rejected.
Cause: **VNC authentication is DES-based and uses only the first 8 bytes of the
password.** A generated 12-character password creates a mismatch between what
`x11vnc -storepasswd` derives and what the client sends. Any VNC password here
should be **8 characters or fewer** — longer ones are not "more secure", they are
ambiguous.

**2. The console was 640×480.** With `HDMI-0 disconnected` and no monitor, the
Tegra driver starts X at 640×480 — smaller than the demo window, so the desktop
was technically reachable and practically useless.

`/etc/X11/xorg.conf` now declares a `ConnectedMonitor` and an explicit screen, and
the console comes up at **1024×768**. Note what did *not* work: an explicit
1920×1080 modeline, even with `UseEdid false` and every `ModeValidation` check
disabled. The Tegra display stack falls back to a built-in mode without a real
EDID to negotiate against. Reaching 1080p headless would mean supplying a
**synthetic EDID blob** via `CustomEDID` — worth doing if the extra pixels matter,
but 1024×768 is sufficient and the demo window is scaled to 0.5 to fit it.

`src/setup/set_headless_display.sh` applies this, **backs up the original
`xorg.conf`, and rolls back automatically** if X does not return at a usable
resolution — a broken Xorg config on a board reachable only over SSH would
otherwise leave no desktop at all.

## 2026-10-05: a USB 3 camera at 1080p60, and the crash hunt

Asked for: change to the new camera and run it at high resolution and high frame
rate; test on **video**, not only images, because the demo "sometimes crashes if
something shows up suddenly"; and if it keeps crashing, change the model. Every
number below was measured on the board that day. Raw results:
[`results/soak_2026-10-05/`](../benchmarks/results/soak_2026-10-05/_summary.json) (and the [stability report](./raptor-stability-report.html)).

### The new camera: Arducam B0498

The C922 has been replaced by an **Arducam B0498** (8.3 MP, USB 3). It is on the
USB 3 bus at **5000M** - the C922 was stuck on USB 2 at 480M. It offers
**uncompressed YUYV only; it has no MJPG mode at all.**

| Mode | Driver delivers | Through the demo's capture thread | CPU for capture |
|---|---|---|---|
| 1280×720 @ 90 | 90.03 fps | 90.0 fps | 122 % of a core, 13.5 ms/frame |
| **1920×1080 @ 60** | **60.03 fps** | **60.0 fps** | **111 % of a core, 18.4 ms/frame** |
| 1920×1080 @ 30 | 30.34 fps | 30.0 fps | 55 % |
| 3840×2160 @ 15 | 15.01 fps | 15.0 fps | 66 %, 43.9 ms/frame |

**1080p60 is the setting**: full HD at twice the C922's rate, sustained by the
capture thread on about one of the board's eight cores. 4K is available but only at
15 fps. Auto-exposure did not lower the frame rate in the lab's lighting; in a dark
room it may - watch the HUD.

What changed in the code (`common/live_camera.py`, `demo/raptor_live_demo.py`):

- `--fourcc auto` (the new default) chooses by the camera's USB link: **YUYV on
  USB 3** (no decoding - the C922's 1080p MJPEG cost 22 ms per frame to decode),
  MJPG on USB 2, where uncompressed 1080p does not fit. The old default asked for
  MJPG, which this camera silently ignored.
- `--fps 60` is the new default; a camera that cannot do 60 at the chosen size
  gives the nearest rate it has (the C922 at 1080p: 30).
- The demo prints and logs what was actually negotiated:
  `camera /dev/video0 - 1920x1080 YUYV @60.0 fps`.

**Bench mode on the live camera: 59.9 FPS at 1080p60**, worst 5 % of frames also
59.9 - the pipeline keeps up with the camera. Pose inference 11.6-12.3 ms a frame.

### Looking for the crash

Evidence first, from the board as it was found:

- The demo had been running for **5 days 20 hours**. Its peak memory was
  **10.2 GB** (`VmHWM`) on a 15.6 GB board with **no swap**.
- The kernel log for the previous 7 days had **no** out-of-memory kills, segfaults
  or GPU faults - only the old C922 dropping off USB on 29 September.
- The demo wrote only to a terminal on the Jetson's screen. **There was no log**,
  so whatever happened left no trace.

Two crash causes looked likely from reading the code, and both fire exactly when a
new person appears. **Neither reproduced** (`tests/repro_crashes.py`):

| Suspect | Test | Result |
|---|---|---|
| The VLM thread adds a new person's answer to a dict while the main loop iterates it (`dictionary changed size during iteration`) | Writer thread hammering the dict against the demo's exact access pattern | 0 errors in 38,750 iterations |
| A zero-height box at the frame edge makes ByteTrack divide by zero, and `int(nan)` crashes the drawing | Zero-height, zero-width, one-pixel and inverted boxes through the tracker | No exception, no NaN |

They are not claimed as the cause. The real crash was then hunted on video built for
it (`tests/make_stress_videos.py`, 1080p): an **empty** version of each scene cut
straight to a crowd, crowd/empty alternating **every frame**, jump cuts where people
teleport, and a sudden brightness flash.

### What was fixed, and the proof each fix works

These are definite defects, fixed whether or not they were *your* crash:

| Defect | Fix | Proof (fault injection, `tests/fault_inject_demo.py`) |
|---|---|---|
| Any exception while processing one frame ended the whole demo | Each frame is guarded: the full traceback is logged, the frame skipped, the count shown on the HUD. **30 failures in a row** stop the demo and say why - a broken system must not hide behind the guard | 1 % of frames made to fail: **survived**, 82 errors in 8,366 frames (0.98 %), still 59.8 FPS. Every frame made to fail: stopped after exactly 30, exit status 1, with the message |
| An exception inside the camera thread killed the thread silently; the demo then froze on its last status, which looks like a crash | The thread catches it, logs it, releases the camera and re-opens it | 0.5 % of live camera reads made to fail: **survived**, 27 thread errors, 27 automatic re-opens, frames kept coming at 59.1 FPS |
| No log | `launch_demo.sh` logs every run to `~/raptor-results/demo-logs/` (newest 20 kept), with Python's fault handler on, so even a native crash leaves a stack | - |
| The FPS statistics list grew by one entry per frame, forever | A bounded histogram | - |

### Long runs on video and live

`tests/soak_demo.py` runs the demo as a separate process, so a crash is an exit code
and a traceback rather than the test dying with it; memory is sampled every 2 s.

| Run | Code | Length | Frames | Outcome | FPS (mean / worst 5 %) |
|---|---|---|---|---|---|
| Street stress video, bench + VLM | before | 3 min | 6,563 | survived | 52.4 / 40.6 |
| Aerial stress video, aerial + VLM | before | 3 min | 3,753 | survived | 31.0 / 22.0 |
| Live camera 1080p60, bench + VLM | before | 7 min | 22,983 | survived (stopped by me) | 59.9 / 59.9 |
| Street stress video, bench + **VLM answering 3,006 times** | after | 16 min | 22,023 | **survived, 0 errors** | (profiler on) |
| Aerial stress video, aerial + VLM | after | 12 min | 9,484 | **survived, 0 errors** | (profiler on) |
| Live camera 1080p60 **with the real video window**, bench + VLM | after | 3 min | 7,064 | **survived, 0 errors**, memory +1 MB/min | about 44 (window drawing costs ~15 FPS) |

**No run crashed, before or after the fixes.** That has to be said plainly: the
crash you saw was not reproduced on this camera, on video built to provoke it, or
in about 45 minutes of running. The most likely explanation is the one
already documented for 29 September - the C922 dropping off USB, which this USB 3
camera has not done - but that is an inference, not a proof. What *has* changed is
that a crash can no longer pass unrecorded: if it happens again, the log in
`~/raptor-results/demo-logs/` will say where.

### Memory

Soak runs showed resident memory creeping up by a few MB a minute after warm-up. Under `tracemalloc` (aerial run, minutes 2 to 8) the **Python heap grew only 0.19 MB/min while total memory grew 43 MB/min**: the growth is **native memory** (CUDA/TensorRT/allocator), not Python objects, so no leaking list or dict explains it. The profiler slows everything, so 43 MB/min overstates it; unprofiled runs measured +1 to +5 MB/min. The source is **not found**. At 5 MB/min a demo left running would take about 20 hours to use another 6 GB, so a 24-hour soak is the next test.

The 10.2 GB peak is the VLM loading: its weights pass through memory at about twice
their 4.1 GB size, then the demo settles near 6.5 GB. The board never had less than
4.7 GB available during any test. But it has **no swap**: NVIDIA's first-boot swap
service (`nvfb-swapfile.service`, `ConditionFirstBoot=yes`) was skipped on this
board's first boot, so the swap JetPack intends it to have was never created. With
one demo running that is fine; with the demo plus another large job (a benchmark, a
second VLM) the out-of-memory killer becomes possible. Compressed RAM swap (zram)
would cost nothing until needed - recommended, not applied.

### Are the detections steady? And should the model change?

`--frame-log` writes one line per frame; `tests/analyse_frame_log.py` turns it into
numbers. **Flicker** is a people-count that jumps and comes straight back within 3
frames - nobody walks in and out of shot in 50 ms, so it is jitter, not the scene.
On real continuous video (`vtest.avi`, 795 frames, a street from an elevated camera,
5-10 people in view):

| | Bench pipeline | Aerial, **YOLO26s** (deployed) | Aerial, RT-DETRv4-S |
|---|---|---|---|
| People seen per frame (mean / max) | 1.2 / 4 | 6.2 / 10 | 6.3 / 9 |
| Flicker per 100 frames | 0.25 | **0.88** | 1.38 |
| New track IDs per 100 frames | 2.6 | **3.8** | 4.2 |
| Aerial pipeline on 1080p video (FPS mean / worst 5 %) | - | **33.7** / 18 | 25.4 / 17 |

- **Keep YOLO26s.** The deployed Apache-2.0 alternative, RT-DETRv4-S (now runnable in
  the demo through `common/trt_rtdetr.py`), finds the same people but flickers about
  57 % more, re-assigns IDs more often, and is a third slower. No model fault was
  found anywhere, so the condition for changing models was never met - this
  comparison is the check that the current one is the right one.
- **The bench pipeline misses people seen from above** (1.2 per frame against 6.2).
  That is the bench model doing what it is for - people close to a desk camera - but
  it means the bench icon must never be used to judge detection from altitude.

### The flight pipeline is not yet at 60 FPS

Bench mode keeps up with the camera; **aerial mode reaches 33.7 FPS** on 1080p
frames, the detector taking about 20 ms of each ~30 ms frame. Moving the detector's
resize onto the GPU - the standing next step in STATUS - was built and measured
(`tests/check_trt_yolo_gpu.py`): **1.07× faster** (21.2 → 19.8 ms), and it changed the
people count on 12.7 % of frames, because borderline boxes near the confidence
threshold flip on sub-pixel differences. Not adopted; the CPU path stays the
default. The CPU resize was not the bottleneck it was assumed to be. The remaining
routes to 60 FPS are an INT8 engine (needs calibration and a re-check of accuracy)
or overlapping capture, detection and pose in separate threads.

### Running it now

Nothing changes on the desktop icons. Under the hood the demo now asks for 1080p at
60 fps in the best format the camera offers, guards every frame, and logs every run.

```bash
# the stress tests, as run on 2026-10-05
cd ~/raptor/src/tests
~/raptor-venv/bin/python make_stress_videos.py            # once
~/raptor-venv/bin/python soak_demo.py --name street --minutes 15 -- \
    --mode bench --source ~/raptor-data/video/stress_street_1080p.mp4
~/raptor-venv/bin/python soak_demo.py --name live --minutes 15 --with-window -- --mode bench
```
