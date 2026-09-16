# 07 — Roadmap

Phases are ordered so that **something demonstrable exists at the end of each one**, and
so that we are never debugging two new things at once. Durations are rough and assume a
small student team working part-time.

---

## Phase 0 — Foundations (1-2 weeks)

Get the board into a known-good state and the workflow in place.

- [ ] Flash **JetPack 6.x**, confirm CUDA / cuDNN / TensorRT versions, record them.
- [ ] Install **ROS 2 Humble**; `talker`/`listener` working.
- [ ] Set up `jetson-containers`, confirm a CUDA container runs.
- [ ] Bring up the camera in ROS 2; `/raptor/image_raw` visible in rviz2 or Foxglove.
- [ ] Bring up `mavros`; GPS, attitude and altitude arriving as ROS topics.
- [ ] Verify Jetson clock is synced with flight-controller time.
- [ ] Record a first rosbag and replay it.
- [ ] Set up `jtop`/`tegrastats` logging and confirm we can read power and temperature.

**Done when:** we can record a bag containing camera + GPS + attitude, and replay it.

---

## Phase 1 — Detection baseline (2-3 weeks)

- [ ] Run stock YOLO11 (PyTorch, FP16) on the Jetson against recorded video.
- [ ] Wrap it as `detector_node`, publishing `vision_msgs/Detection2DArray`.
- [ ] Add ByteTrack; stable track IDs across frames.
- [ ] Export to **TensorRT FP16**, then **INT8** calibrated on our own footage.
- [ ] Run experiments **E1 and E2** from [06](./06-benchmark-plan.md).

**Done when:** persons are detected and tracked at >= 25 FPS sustained, numbers recorded
in `results/`, and we know the FP16-vs-INT8 accuracy cost.

---

## Phase 2 — Data collection (runs in parallel from Phase 1 onward)

The long pole. Start early; everything downstream waits on it.

- [ ] Write and get approval for a **consent form** for volunteers (see [08](./08-limitations-and-safety.md)).
- [ ] Fly structured collection missions: 30/45/60 m, three lighting conditions, several
      surfaces, all target postures including prone and partly occluded.
- [ ] Label ~2,000-5,000 frames (boxes + posture; keypoints pre-annotated, then corrected).
- [ ] Build train/val/test splits **split by flight, not by frame** — frames from one
      flight are highly correlated and a random split will massively overstate accuracy.
- [ ] Assemble a held-out set of ~100 staged scenes with human-written reference
      descriptions for VLM evaluation (E6).

**Done when:** a versioned, documented dataset exists with an honest, flight-level split.

---

## Phase 3 — Pose and posture (2-3 weeks)

- [ ] Swap in **YOLO11-pose**; keypoints published per track.
- [ ] Implement gravity-aligned keypoint normalisation using MAVROS attitude.
- [ ] Train the **posture classifier** on our labelled data.
- [ ] Add temporal smoothing, hysteresis, and the immobility timer.
- [ ] Evaluate: confusion matrix, with `standing -> lying` and `lying -> standing` errors
      reported separately.
- [ ] Run **E3** (altitude vs. recall).

**Done when:** posture is reported per track, stable, and demonstrably better than a
hand-tuned threshold baseline. **This is the first genuinely novel result.**

---

## Phase 4 — VLM integration (3-4 weeks)

- [ ] Get one VLM generating text on the Jetson, offline, in isolation.
- [ ] Run the **E5** sweep; pick the model and serving stack on measured data.
- [ ] Implement `vlm_node` as an action server with the bounded priority queue.
- [ ] Implement the trigger logic from [03](./03-scene-understanding-vlm.md).
- [ ] Add the constrained JSON schema and validation.
- [ ] Run **E6** (quality and hallucination) and **E7** (contention).

**Done when:** a triggered description appears within the latency budget while the
detector holds >= 25 FPS, and we can state our hallucination rate as a number.

---

## Phase 5 — Triage, geolocation and the operator view (3-4 weeks)

- [ ] `triage_aggregator_node`: fuse tracks and descriptions into `VictimReport`.
- [ ] Pixel-to-ground geolocation via the TF chain; publish lat/lon + uncertainty.
- [ ] Cross-pass de-duplication.
- [ ] Rule-based `triage_flag` with a human-readable `triage_reason`.
- [ ] Ground-station view: map with victim pins, snapshot, description, and a
      **one-click "this is wrong" dismissal** that is logged as training feedback.
- [ ] `gcs_link_node` with queue-and-retry over a degraded link.

**Done when:** a full flight produces a map of victim reports an operator can actually work from.

---

## Phase 6 — Field validation and hardening (ongoing)

- [ ] Run **E8** end-to-end on real flights with planted volunteers.
- [ ] Thermal and power soak tests at flight duration.
- [ ] Failure behaviour: what happens when the VLM node dies, the camera drops, the link
      goes, the SD card fills. Each should degrade, not crash.
- [ ] Watchdog and auto-restart for perception nodes.
- [ ] Write the model card and the honest limitations section.

---

## Milestones worth demoing

| Milestone | Demo |
|-----------|------|
| M1 (end of Phase 1) | Live person detection and tracking from the drone camera at 30 FPS |
| M2 (end of Phase 3) | Screen showing "Person 3: LYING, immobile 24 s" from a real flight |
| M3 (end of Phase 4) | Full pipeline: detect -> flag posture -> auto-generate a description onboard |
| M4 (end of Phase 5) | Map with geolocated victim pins, snapshots and descriptions |

## Biggest risks, and what we do about them

| Risk | Mitigation |
|------|-----------|
| **Data collection slips** and blocks Phases 3-5 | Start Phase 2 in parallel with Phase 1. Use public datasets (HERIDAL, SARD, Okutama-Action) as an interim bridge. |
| VLM does not fit / is too slow on our SKU | Fallback ladder already defined: Qwen2.5-VL-3B -> VILA-3B -> SmolVLM2. Confirm the board's memory size **now**. |
| Detector and VLM contend for GPU | E7 is scheduled specifically to find this early; DLA offload is the planned mitigation. |
| Thermal throttling in the airframe | Measure in Phase 1, not after integration. May force a lower `nvpmodel` mode or a duty-cycled VLM. |
| Prone people missed from altitude | The reason Phase 2 fine-tuning data is non-negotiable; E3 gives the operational altitude limit. |
| Scope creep into autonomy / path planning | Out of scope. RAPTOR perceives and reports; the flight controller flies. Say no. |
