# 04 — ROS 2 Architecture

## Why ROS 2 at all

We could write one Python script that reads frames and runs both models. For a demo
that works. For this project it does not, because:

- **The two tiers have incompatible rates.** 30 Hz detection and 0.2 Hz VLM inference
  in one process means the slow one stalls the fast one unless we hand-roll threading,
  queues and back-pressure. ROS 2 gives us that for free, correctly, with per-topic QoS.
- **We need to record everything.** `rosbag2` records every topic with timestamps, so a
  flight can be replayed offline against a new model. This is the single most valuable
  thing ROS gives a research project — our benchmark suite runs on recorded bags, not
  on re-flights.
- **The flight controller already speaks MAVLink**, and `mavros` is the maintained
  bridge into ROS 2. Detections become geolocatable the moment they share a clock and
  a TF tree with the flight data.
- **Standard message types.** `vision_msgs/Detection2DArray`, `sensor_msgs/Image`,
  `geometry_msgs/PoseStamped` mean rviz2, Foxglove and every existing tool can inspect
  our system without custom viewers.
- Nodes can be restarted independently. Crashing the VLM node must not drop the aircraft's
  perception.

**Version:** JetPack 6.x ships Ubuntu 22.04, which pairs with **ROS 2 Humble** (LTS).
Use Humble unless we have a concrete reason to move; the Jetson container ecosystem and
Isaac ROS target it.

## Node graph

```
 ┌────────────────┐   sensor_msgs/Image        ┌─────────────────────┐
 │ camera_node    │───/raptor/image_raw────────>│ detector_node       │
 │ v4l2 /dev/     │                            │  YOLO11-pose (TRT)  │
 │ video0 via     │                            │  ByteTrack          │
 │ HDMI capture   │                            │  posture classifier │
                                               └──────┬──────────────┘
                                                      │
              /raptor/tracks  (raptor_msgs/TrackArray)  │
                     ┌────────────────────────────────┤
                     │                                │ /raptor/vlm_request
                     ▼                                ▼   (crop + context)
 ┌────────────────────────────┐            ┌─────────────────────────┐
 │ triage_aggregator_node     │            │ vlm_node                │
 │  - fuse tracks + VLM       │<───────────│  Qwen2.5-VL-3B INT4     │
 │  - geolocate               │ /raptor/    │  action server          │
 │  - dedupe across passes    │ descriptions│  bounded job queue     │
 │  - rule-based triage_flag  │            └─────────────────────────┘
 └───────┬────────────────────┘
         │ /raptor/victim_reports (raptor_msgs/VictimReport)
         │
         ├──> rosbag2 recorder        (evidence, replay, benchmarking)
         ├──> foxglove_bridge / rosbridge  ──> ground station UI
         └──> gcs_link_node           (compact summaries over telemetry)

 ┌────────────────┐   /mavros/global_position/global, /mavros/imu/data,
 │ mavros         │   /mavros/local_position/pose  ──> TF tree
 └────────────────┘   (consumed by detector_node for gravity alignment
                       and by triage_aggregator_node for geolocation)
```

## Nodes

### `camera_node`
Publishes `sensor_msgs/Image` (or `CompressedImage` for the downlink) plus
`sensor_msgs/CameraInfo` with real calibrated intrinsics. **Calibrate the camera
properly** — geolocation accuracy depends directly on it.

**Interface: micro-HDMI out of the A8 mini into a USB capture card.** The card presents
itself to the Jetson as a standard UVC device, so the node is `v4l2_camera` or `usb_cam`
reading `/dev/video0` — or a gstreamer pipeline via `gscam` if we need format control.

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext    # confirm 1920x1080 and the pixel format
```

Three things this interface costs us, all of which belong in the benchmark plan:

- **USB bandwidth.** Uncompressed 1080p30 YUYV is roughly 62 MB/s and needs **USB 3.0**. A
  USB 2.0 card will silently fall back to MJPEG, a lower frame rate, or 720p. Check
  `lsusb -t` for the link speed, not just that the device appears.
- **Frames arrive CPU-side.** The RTSP path could hardware-decode straight into GPU memory
  with `nvv4l2decoder`. A capture card hands us host-memory buffers, so there is a copy to
  the GPU on every frame. Measure it; consider `nvvidconv` early in the pipeline.
- **The card adds its own latency**, typically tens to well over a hundred milliseconds on
  cheap hardware, and it is invisible unless deliberately measured.

The camera’s Ethernet port now feeds a **video transmitter** for the ground downlink, not the
Jetson. That means the operator sees the camera directly rather than a stream relayed by the
Jetson — good for link robustness, but the ground picture no longer carries our detection
overlays unless we send them separately over telemetry.

QoS: `SensorDataQoS` (best-effort, depth 1). Dropping a frame is always better than
queueing stale ones.

### `detector_node`
The hot path. Runs the TensorRT YOLO11-pose engine, ByteTrack, and the posture
classifier. Subscribes to the drone attitude so keypoints can be rotated into a
gravity-aligned frame before classification (see [02](./02-detection-and-pose.md)).

Publishes:
- `/raptor/detections` — `vision_msgs/Detection2DArray` (standard, so rviz/Foxglove render it)
- `/raptor/tracks` — `raptor_msgs/TrackArray` (our type: track id, posture, immobility timer, keypoints)
- `/raptor/image_annotated` — optional, throttled to ~5 Hz, for the operator view only

Must hold its frame budget regardless of what any other node is doing.

### `gimbal_node`
Drives the A8 mini over **UART** using the SIYI SDK (UDP is unavailable now that the camera's
Ethernet port feeds the transmitter). Subscribes to a target from the tracker and commands
pitch/yaw to keep a selected person centred; publishes measured gimbal attitude, which the
aggregator needs for pixel-to-ground projection.

Keep this node separate from `detector_node` so a stuck serial port cannot stall perception,
and make it the **single** authority on gimbal pointing — if the optional Pixhawk UART is also
wired, the flight controller supplies attitude data only and must not issue pointing commands.

### `vlm_node`
An **action server**, not a topic subscriber — descriptions are long-running tasks that
should be cancellable and report status. Owns the model, the bounded priority queue, and
the JSON schema validation. Publishes `/raptor/descriptions`.

Runs the model on a separate CUDA stream. If it dies, `detector_node` keeps working and
the system degrades to posture-only reporting, which is still operationally useful.

### `triage_aggregator_node`
The part that turns perception into a product:
- **Geolocation.** Project the person's foot position (or box centre) through the camera
  intrinsics and the TF chain `map → base_link → gimbal → camera_optical`, intersect with
  a ground plane at the terrain height, and emit lat/lon. Flat-earth assumption is fine at
  first; note the error grows with terrain slope and altitude. Publish the uncertainty too.
- **Cross-pass de-duplication.** The same person seen on two passes of the search pattern
  must not become two victims. Match on geodesic distance plus appearance/posture
  consistency; track IDs do not survive occlusion, geolocation does.
- **Rule-based triage flag.** Auditable rules over structured fields — never the VLM's own
  opinion. See [08](./08-limitations-and-safety.md).

### `gcs_link_node`
Telemetry links are narrow. Send compact JSON victim reports and thumbnails, not video.
Retry and queue when the link drops; the report must survive a link outage.

## Custom messages (`raptor_msgs`)

```
# raptor_msgs/Track.msg
uint32                      track_id
vision_msgs/BoundingBox2D   bbox
float32                     detection_confidence
geometry_msgs/Point[]       keypoints          # 17 COCO keypoints, image frame
float32[]                   keypoint_confidence
string                      posture            # standing|sitting|crouching|lying|unknown
float32                     posture_confidence
float32                     immobile_seconds
builtin_interfaces/Time     first_seen
```

```
# raptor_msgs/VictimReport.msg
std_msgs/Header             header
uint32                      victim_id          # stable across passes, not the track id
geographic_msgs/GeoPoint    position
float32                     position_uncertainty_m
string                      posture
float32                     immobile_seconds
string                      description        # VLM free text
string[]                    injury_indicators  # VLM structured field
string                      triage_flag        # rule-derived: OK | REVIEW | URGENT
string                      triage_reason      # which rule fired, in plain words
sensor_msgs/CompressedImage snapshot
builtin_interfaces/Time     last_updated
```

## Practical notes

- **Use a launch file from day one**, with parameters (model paths, thresholds, trigger
  timings) in YAML. Hard-coded constants make benchmarking impossible.
- **Composable nodes / intra-process comms.** Put `camera_node` and `detector_node` in one
  container so frames pass by pointer, not by serialised copy. On Jetson this is a large
  win. NVIDIA **Isaac ROS NITROS** extends the same idea to GPU memory — adopt after the
  basic pipeline works.
- **Record bags on every flight** (all topics except the annotated image). Our benchmark
  suite and our labelled dataset both come out of those bags.
- **One clock.** Make sure the Jetson time is synced with MAVROS time, or every timestamp
  correlation and the geolocation will be subtly wrong.
