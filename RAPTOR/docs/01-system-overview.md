# 01 — System Overview

## Mission

RAPTOR is a search-and-rescue-style UAV. It flies a search pattern over an area and,
for every person it finds, produces a **victim report**:

```
person_id      : 7
position       : 24.7136 N, 46.6753 E  (±  ~4 m, projected from pixel + GPS + attitude)
first_seen     : 2026-09-16T14:02:11Z
posture        : lying          (confidence 0.91, stable for 38 s)
motion         : none detected in last 30 s
description    : "An adult in a light shirt lying face-down on gravel, left arm
                  extended, not moving. Dark staining visible on the right leg."
triage_flag    : REVIEW — prolonged immobility + non-upright posture
snapshot       : frame_0412_person7.jpg
```

That report goes to a human operator. **The system never makes a medical call on its
own** — see [08 — Limitations & safety](./08-limitations-and-safety.md).

## Hardware

| Part | Confirmed spec |
|------|----------------|
| Airframe | Quadcopter, existing |
| Flight controller | **Pixhawk 6C** — MAVLink to the Jetson over TELEM1 (MAVROS, read-only) |
| Companion computer | **Jetson Orin NX 16 GB** (confirmed 2026-09-16) |
| Camera | **SIYI A8 mini 4K**, 3-axis gimbal, 95 g |
| Camera optics | Sony 1/1.7″ 8 MP, f/2.8, **81° horizontal / 93° diagonal FOV** |
| Camera video — onboard | **Micro-HDMI → USB capture card → Jetson**, appearing as `/dev/video0` |
| Camera video — downlink | **Ethernet → video transmitter → ground station** |
| Camera power | 11–25.2 V (3S–6S), 5 W average / 12 W peak, own branch off the battery |
| Gimbal control | **SIYI SDK over UART** to the Jetson (the Ethernet port is taken by the transmitter) |
| Stream resolution | **1080p maximum** for any live output; 4K is SD-card recording only |
| Link | Telemetry to the Jetson; video downlink direct from the camera |

### Two things to verify before committing to this

1. **Can HDMI and Ethernet video run at the same time?** The manual describes the video
   output port as a *switch* (“switch video output mode to HDMI under the Gimbal Config
   page”, and “HDMI / CVBS video output is changed to dynamic switch”). If selecting HDMI
   disables the Ethernet RTSP stream, the split architecture above does not work and we
   must either keep everything on Ethernet through a switch, or accept a downlink fed from
   the Jetson instead of the camera. **Test this first — it is cheap and it decides the
   whole harness.**
2. **Gimbal control has moved to UART.** It previously shared the Ethernet link with video.
   With Ethernet handed to the transmitter, the Jetson must drive the gimbal over the
   camera’s UART control port instead. The A8 mini supports the SIYI SDK over UART, so this
   works — but it is a wiring change, not a free swap.

Full harness wiring, including the four ways to damage hardware, is in
[`raptor-wiring-map.html`](./raptor-wiring-map.html).

### Why the Orin NX is the right board here

The Orin NX is the smallest NVIDIA module that can realistically host *both* a
real-time detector and a generative VLM at the same time:

- **~70 TOPS (8 GB) / ~100 TOPS (16 GB)** INT8, 1024-core Ampere GPU with tensor cores.
- **102.4 GB/s memory bandwidth** — this, not TOPS, is usually what limits token
  generation speed on a VLM. It is roughly 1.5× the Orin Nano's.
- **16 GB unified memory** on the larger SKU. CPU and GPU share it, so a quantised
  3B VLM (~2.5–3.5 GB) and a TensorRT detector (~0.5 GB) and ROS 2 all coexist with
  headroom. On the 8 GB SKU this gets tight and forces a smaller VLM.
- **2× NVDLA accelerators.** These matter more than people expect for us: the
  detector can potentially be offloaded to DLA, leaving the GPU free for the VLM.
  That is a benchmark item, not an assumption — see [06](./06-benchmark-plan.md).
- Runs **JetPack 6.x** → Ubuntu 22.04 → **ROS 2 Humble** natively, with CUDA 12,
  TensorRT 10 and the `jetson-containers` ecosystem.

The Orin Nano would work for tiers 1–2 but is a poor host for the VLM: less bandwidth,
less memory, fewer TOPS. If we own one, it becomes the dev/bench board and the
"degraded mode" target, not the flight computer.

## Hard constraints that shape every decision

1. **Power and thermals.** The Jetson runs off the drone's battery. Every watt spent
   on compute is flight time lost. We will characterise the pipeline at `nvpmodel`
   10 W / 15 W / 25 W / MAXN and pick the lowest mode that meets the frame budget.
   Airflow inside the airframe is also limited — sustained MAXN may thermally throttle.
2. **No reliable network link.** The drone may be out of range or in a disaster area
   with no infrastructure. Therefore **everything must run onboard**. This is the
   reason we do not use a cloud API model — see [03](./03-scene-understanding-vlm.md).
3. **Aerial viewpoint.** The camera looks down from altitude at an oblique angle.
   People are small, foreshortened, and often partly occluded. This is a genuine
   domain gap from the ground-level imagery most models are trained on, and it is the
   main reason we will fine-tune — see [05](./05-custom-models-and-data.md).
4. **Latency is not the binding constraint; coverage is.** A 4-second description is
   fine. Missing a person entirely is not. The system is tuned for **recall**.

## End-to-end data flow

```
                    ┌──────────────────────────────────────────────┐
  Camera ──HDMI────>│ capture node   (USB capture card, /dev/video0)│
   (also Ethernet   │                                              │
    → video TX      │                                              │
    → ground)       │                                              │
                    └───────────────┬──────────────────────────────┘
                                    │ image
                    ┌───────────────▼──────────────────────────────┐
   TIER 1 + 2       │ detector node                                │
   every frame      │  YOLO11 (person) + YOLO11-pose (keypoints)   │
   ~30 FPS          │  ByteTrack  -> stable person_id              │
                    │  posture classifier -> standing/lying/...    │
                    └───────────────┬──────────────────────────────┘
                                    │ tracked people + postures
                    ┌───────────────▼──────────────────────────────┐
                    │ trigger logic                                │
                    │  new track? posture==lying? immobile 20 s?   │
                    │  operator asked? -> enqueue VLM job          │
                    └───────────────┬──────────────────────────────┘
                                    │ cropped image + structured context
                    ┌───────────────▼──────────────────────────────┐
   TIER 3           │ VLM node   (Qwen2.5-VL-3B class, INT4)       │
   event-driven     │  -> free-text description + injury cues      │
   ~0.2–0.3 Hz      └───────────────┬──────────────────────────────┘
                                    │
   MAVROS (GPS, ──────────────────> │ triage aggregator            │
   attitude, alt)                   │  fuse, geolocate, dedupe     │
                                    └───────────────┬──────────────┘
                                                    │
                            rosbag2 (evidence)  +  downlink to operator GCS
```

Tiers 1–2 and tier 3 run in **separate ROS 2 nodes on separate CUDA streams**, so a
slow VLM inference can never stall the detector. Full node graph in
[04 — ROS 2 architecture](./04-ros2-architecture.md).
