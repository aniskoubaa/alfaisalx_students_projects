# 15 — Next Steps

Written 2026-10-05, finished 15:17 on 05 October 2026, after the stability work in [14](./14-camera-demo-and-remote-access.md).
Companion: [stability report](./raptor-stability-report.html).

## Where the project stands

RAPTOR is an aerial search-and-rescue quadcopter: find people from altitude, say where
they are and what posture they are in, flag visible distress for a human to review, all
offline on a Jetson Orin NX. The **compute side is solid**: models chosen on measured
grounds, a live demo that ran 1080p60 for 45 minutes of tests without a crash, fault
handling proven by injection, every run logged. What does **not** exist yet is almost
everything that touches the aircraft: the flight camera has never been powered, the
Jetson has no mount, no MAVLink link, no ROS 2 nodes, and no data of people lying down.

The risk has moved. It is no longer "do the models work" but "does it work on the real
camera, on the real aircraft, on the people we actually need to find".

## Ordered plan

### Now (days)
1. **24-hour soak** of the bench demo on the live camera (`tests/soak_demo.py --minutes 1440`).
   Settles whether the slow native-memory growth (+1 to +5 MB/min) matters.
2. **Enable zram swap.** The board has none (NVIDIA's first-boot swap service was skipped).
   Costs nothing until needed; removes the out-of-memory-killer risk when a demo and a benchmark overlap.
3. **Commit** this session's work (nothing from 2026-10-05 is committed).

### P1 — unblock the aircraft (1-2 weeks)
4. **Power the A8 mini** (never done) and run the **HDMI + Ethernet simultaneity test**.
   Ten minutes; decides whether the VTX downlink exists at all.
5. **Buy the HDMI capture card** (UVC, USB 3.0; see [13](./13-bill-of-materials.md)) and
   repeat the camera-mode measurement. The Arducam numbers do **not** transfer: different
   optics, a capture-card latency we have never measured.
6. **Mount the Jetson**: second deck on aluminium standoffs above the Pixhawk, inside the
   123 mm prop keep-out ([build view](./raptor-build-view.html)).

### P2 — close Phase 0 and the data gap (1-2 weeks, start now)
7. **MAVROS link** to the Pixhawk 6C, **first rosbag recorded and replayed** (the Phase 0 finish line).
   Decide: may the Jetson write gimbal commands to the flight controller?
8. **Data for people lying down.** The detectors were trained on VisDrone, which has no
   casualties. Evaluate on SARD, HERIDAL, Okutama-Action, C2A, then fine-tune with posture
   classes (upright / sitting / lying). The consent form, flight plan and labelling workflow
   take longer than the code: **start now**.

### P3 — performance and correctness (2-4 weeks)
9. **Aerial pipeline from 34 to 60 FPS.** The GPU-resize idea was tested and rejected (1.07× faster,
   changes counts). Remaining: an INT8 engine (re-check accuracy), or overlapping capture, detection
   and pose in separate threads.
10. **Gravity-aligned posture** from MAVROS attitude. Today a banked turn would read as "lying".
11. **VLM speed**: ~12 s for a full description against a 5 s target. TensorRT Edge-LLM or llama.cpp at 4-bit with a JSON grammar.
12. **Find the native memory growth** (CUDA/TensorRT/allocator) if the 24-hour soak says it matters.

### P4 — the system (1-2 months)
13. **ROS 2 Jazzy nodes**: camera, detector, tracker, event trigger, VLM-on-trigger, geolocated victim report with snapshot.
14. **Operator dashboard**: event log on the Jetson, feed, health, human review of every flag.
15. **Flight tests**, starting tethered, with a known person on the ground, before any search scenario.

## Risks to keep in view

| Risk | Why it matters |
|---|---|
| Detectors have never seen a person lying down from altitude | The core mission. Measured recall on aerial data is a ceiling for urban VisDrone, not for a search |
| Real camera untested | Every FPS and accuracy figure so far is from a webcam or the Arducam |
| The crash reported on 2026-10-05 was never reproduced | Likely the old webcam's USB drops; unproven. The new log will say if it recurs |
| Slow native memory growth, no swap | Harmless for a flight, matters for a demo left running for days |
| Posture rule wrong in a banked turn | Needs the IMU feed before any flight use |
| AGPL (Ultralytics) and non-commercial VisDrone weights | Fine for research; RT-DETRv4-S (Apache-2.0) is the measured fallback |

## What would change this plan

- If the A8 mini cannot output HDMI and Ethernet together: drop the VTX, plan the operator link through the Jetson.
- If the capture card adds large latency: reconsider a direct MIPI/CSI camera.
- If a lying-person evaluation shows low recall: the detector, not the pipeline, becomes the critical path.
