# 05 — Custom Models and Data: what to build, what to fine-tune, what to just use

You asked whether designing our own model would be a better approach. The honest answer
is **partly** — and being specific about which parts is what separates a good project
from a wasted semester.

## The three-way verdict

| Component | Build from scratch? | Fine-tune? | Use off the shelf? |
|-----------|--------------------|-----------|--------------------|
| Person detector | **No** | **Yes — this is where our effort pays off** | Start here |
| Pose estimator | **No** | Probably not (maybe late) | **Yes** |
| Posture classifier | **Yes — build it** | — | No good off-the-shelf option for our exact framing |
| Activity / action recognition | Later, maybe | Possible | Start with posture + VLM |
| VLM | **Absolutely not** | Not yet; LoRA later if data allows | **Yes** |

## Why not train a detector from scratch

Training a competitive object detector from random initialisation needs hundreds of
thousands of labelled images, a multi-GPU cluster, and weeks of tuning. The result would
be **worse** than a COCO-pretrained YOLO11 fine-tuned on a few thousand of our own
images, because the pretrained backbone already encodes generic visual features — edges,
textures, human shape priors — that we cannot learn from a small dataset.

This is not a compromise or a shortcut. Transfer learning from a strong pretrained
backbone is what a professional team would also do. The novelty in RAPTOR is not the
detector architecture; it is the **aerial SAR domain adaptation, the gravity-aware
posture reasoning, and the triggered-VLM pipeline**. Spend the effort there.

## Where fine-tuning genuinely pays: the aerial domain gap

COCO is ground-level photographs. Our camera looks down from 30-60 m at an oblique angle
at people who may be prone, partly occluded, thermally camouflaged against dirt, and
15-25 px tall. Off-the-shelf YOLO will **systematically miss prone people from above** —
a person lying down seen from a drone looks nothing like a person in COCO.

That is exactly the failure mode we cannot afford, and exactly what fine-tuning fixes.

### Public datasets to fine-tune on

| Dataset | Why it is relevant |
|---------|--------------------|
| **HERIDAL** | People in wilderness from a UAV, built for SAR. Closest to our mission. |
| **SARD** (Search And Rescue Dataset) | Actors simulating casualties outdoors, filmed by drone — includes lying/injured poses. Very close fit. |
| **Okutama-Action** | Aerial video with **human action labels** (lying, sitting, walking, carrying...). The single best public source for our posture/action tier. |
| **VisDrone** | Large, standard aerial benchmark. Good for general small-person detection and altitude robustness. |
| **UAVDT** | Aerial detection under varied weather/altitude/viewpoint. |
| **TinyPerson** | Explicitly targets tiny person instances. Useful for the high-altitude regime. |
| **Stanford Drone Dataset** | Top-down pedestrians; useful for tracking, less for posture. |

Verify each dataset's licence and any redistribution/ethics terms before use, and record
which ones we used in the model card. Some SAR datasets require an academic request.

### Our own data is still essential

Public data gets us a strong starting point; **our own flight footage over our own
terrain with our own camera** is what closes the last gap. Plan for it:

- Fly deliberate collection missions at **30 / 45 / 60 m**, in morning / midday / late
  light, over the surfaces we actually expect (sand, gravel, asphalt, vegetation).
- Have volunteers pose: standing, walking, sitting, crouching, lying prone, lying supine,
  curled, waving, partly under cover. **Consented volunteers only**, logged — see
  [08](./08-limitations-and-safety.md).
- Record as rosbags, so every frame comes with synchronised GPS, altitude and attitude.
  That metadata is what makes the gravity-aligned posture work possible and it cannot be
  recovered later.
- Label with CVAT or Label Studio. Boxes + posture class; keypoints can be
  pre-annotated by YOLO11-pose and then corrected, which is 5-10x faster than labelling
  from scratch.
- Target on the order of **2,000-5,000 labelled frames** with good diversity. Diversity of
  altitude, lighting, surface and posture matters far more than raw count.

Also use our own footage as the **INT8 calibration set** for TensorRT. Calibrating on COCO
images and deploying on aerial footage is a classic way to silently lose accuracy.

## The model we really should build ourselves: the posture classifier

Detailed in [02](./02-detection-and-pose.md). Recapping why it is the right custom model:

- **The input is already computed** — 17 keypoints from the pose model, free.
- **It is small** — an MLP with a couple of hidden layers, under 100 KB, microseconds to run.
- **It needs data we uniquely have** — the gravity-alignment step uses the drone's IMU
  attitude, so a person seen during a banked turn is not misread as lying down. No public
  model does this, because no public model has our flight data.
- **It is trainable with a few thousand labels** — entirely feasible for a student team.
- **It is explainable** — we can show the operator the keypoints and the torso angle that
  produced the decision. That matters enormously for a system a rescuer must trust.

This is the piece of RAPTOR that is genuinely novel and publishable.

## Activity recognition: start simple, escalate only if needed

"What are they doing" has three levels of ambition:

1. **Posture + motion** (our tier 2). Covers the operationally critical cases: lying and
   immobile, standing and moving, waving. **Start here. It may be enough.**
2. **Short-clip action recognition.** Feed a ~2 s sequence of keypoints into a small
   temporal model (ST-GCN, or a 1D-CNN/GRU over keypoint sequences) to classify
   walking / running / waving / crawling / falling. Cheap, trainable on Okutama-Action
   plus our own data. **Add in phase 3 if posture proves insufficient.**
3. **Open-vocabulary description** (our tier 3, the VLM). Handles everything we did not
   anticipate — "trapped under a collapsed awning", "holding an injured arm". This is why
   the VLM is in the system at all: not to do what the classifier does, but to describe
   what no classifier was trained for.

Note how these complement rather than compete. 1 and 2 are fast, closed-set and reliable;
3 is slow, open-set and fallible. The design gives each the job it is suited to.

## Why not fine-tune the VLM

Not yet:

- **We do not have the data.** LoRA-tuning a VLM for injury description needs thousands of
  image-text pairs with clinically meaningful captions. We would have to write them, and
  we are not qualified to write medical ground truth.
- **Prompting gets us most of the way.** A constrained JSON schema plus a grounded crop
  plus injected context from tiers 1-2 is a large quality gain for zero training.
- **Fine-tuning on a small narrow set would make it confidently wrong.** A VLM tuned on a
  few hundred staged casualty photos will learn our actors' clothing, not injury. That is
  a worse failure than a generic model that says "not visible".

**When to revisit:** if, after collecting real data, we find the base model consistently
misses one specific well-defined visual cue, a small LoRA on that narrow task is
reasonable. Data first, training second.

## Evaluation — decide the metrics before training anything

- **Detector:** precision/recall and mAP@0.5 **broken down by altitude band and by posture**.
  A single aggregate number will hide the prone-person failure that matters most. Track
  **recall at high precision** as the headline: in SAR, a missed person is far worse than a
  false alarm.
- **Posture classifier:** confusion matrix, with particular attention to
  `standing → lying` false positives (cries wolf) and `lying → standing` false negatives
  (misses a casualty). These two errors are not equally bad; weight them accordingly.
- **VLM:** there is no clean automatic metric. Use a **held-out set of ~100 staged scenes
  with human-written reference descriptions** and score on (a) did it mention the injury
  cue we planted, (b) did it invent anything not present (hallucination rate — the number
  we most need to know), (c) did it produce schema-valid JSON.
- **End to end:** on recorded flights, what fraction of planted casualties produced a
  correct victim report with a position within X metres, and how many false victims did
  the operator have to dismiss per flight-hour.
