# AlfaisalX Weekly Progress Report (RAPTOR)

**For:** Dr. Anis Koubaa
**From:** Ibrahim Daoud (RA, AlfaisalX lab)
**Period:** 29 September to 10 October 2026
**Sources:** [ProgressReports/STATUS.md](STATUS.md), [RAPTOR/docs/15-next-steps.md](../RAPTOR/docs/15-next-steps.md), the [stability report](../RAPTOR/docs/raptor-stability-report.html) and the repository history (commits of 1 and 8 October)

## What was achieved

- Deployed the new models on the Jetson Orin NX (29 September). The aerial-trained YOLO26s detector finds 42.5 % of people on held-out aerial test images, against 20.0 % for the previous model, at 26.1 ms (p95) end to end. RT-DETRv4-S (Apache-2.0) is kept as a measured alternative. All six models (detection, pose, description and fallbacks) were verified on the board.
- Fixed the live demo. It now runs at 30 FPS at 1080p (60 at 720p), with steady person counts (tracking), posture from the legs, a VLM posture check and automatic camera reconnect.
- Switched to a new USB 3 test camera (Arducam), which runs the demo at 1080p and 60 fps (5 October).
- Ran a stability campaign (5 October). The reported crash "when something appears suddenly" did not happen in 6 real runs of 3 to 16 minutes. Two weak points found in the code were fixed: a single bad frame, or a camera-thread error, ended the demo, and nothing was logged. Fault-injection tests confirm the fixes.
- Committed the stability report, the test tools and the next-steps plan to the shared GitHub repository (8 October).

## Challenges faced

- Memory on the board grows slowly (+1 to +5 MB per minute), and the board has no swap, so long runs are at risk until this is checked.
- The aerial pipeline runs at 34 FPS, not 60, and a full VLM description takes about 12 s against a 5 s target.
- The flight camera (A8 mini) has still never been powered, the HDMI capture card is not bought yet, and the Jetson has no mount on the airframe.

## Main outcome / deliverable

The compute side is solid: the models are chosen on measured results and deployed, and the live demo ran at 1080p60 for 45 minutes of tests without a crash. Everything is documented in the repository. The remaining risk is on the aircraft side: the camera, the mount and the link to the flight controller.

## Plan for next week

1. Run a 24-hour soak test and enable swap on the board.
2. Power the flight camera and test HDMI and Ethernet video together, then buy the HDMI capture card.
3. Mount the Jetson on the airframe and start the MAVROS link to the Pixhawk.
4. Start evaluating data of people lying down (SARD, HERIDAL, Okutama-Action).
