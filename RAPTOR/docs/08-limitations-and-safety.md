# 08 — Limitations, Safety and Responsible Use

This document exists because RAPTOR points a camera and an AI model at injured people.
Getting this section right is part of the engineering, not paperwork around it.

## What RAPTOR is

A **search aid**. It helps a human operator find people faster and prioritise where to
look, over an area too large to search by eye.

## What RAPTOR is not

- **Not a medical device and not a triage system.** It does not diagnose, does not assess
  severity, and must never be described as doing so — not in the UI, not in a paper, not
  in a demo. A VLM saying "dark staining on the leg" is an observation about pixels, not
  a finding of haemorrhage.
- **Not a decision maker.** Every victim report is a recommendation to a human, who
  decides what happens.
- **Not a surveillance tool.** See the privacy section below.
- **Not a substitute for a trained rescuer.** It finds candidates; people rescue people.

## Known failure modes, stated plainly

| Failure | Why it happens | What we do |
|---------|---------------|-----------|
| **Missed person (false negative)** — the worst one | Small targets, occlusion by vegetation/debris, prone pose from above, low contrast against terrain, motion blur | Fine-tune on aerial SAR data; tune for recall over precision; publish the altitude-vs-recall curve so operators know the limits; never present a clear map as "area confirmed empty" |
| **VLM hallucination** | Generative models assert plausible detail that is not in the image — especially on small, blurry crops | Constrained JSON schema; explicit `not_visible` field; prompt forbids speculation; hallucination rate measured (E6) and reported; snapshot always shown alongside text so the operator checks |
| **Posture misclassification during manoeuvres** | A banked turn rotates the image; a standing person can look horizontal | Gravity-aligned normalisation using IMU attitude; temporal smoothing; hysteresis |
| **Geolocation error** | Terrain slope, uncalibrated intrinsics, GPS error, gimbal angle error | Publish an uncertainty radius, never a bare point; calibrate properly; show the error circle on the map |
| **Duplicate victims** | Multiple passes over the same person | Geodesic de-duplication; operator can merge |
| **Demographic performance gaps** | Detection and description quality can vary with skin tone, clothing, body size, and with children vs. adults | Deliberately diversify collected data; **report per-group performance, do not hide it in an aggregate number** |
| **Degraded conditions** | Dust, rain, low light, smoke | Characterise and document the envelope; do not claim performance we have not measured |
| **Automation bias** | Operators trusting the system more than it deserves | Always show the snapshot; surface confidence and uncertainty; make dismissal one click; train operators on the failure modes above |

## The triage flag is rule-based, deliberately

The VLM produces observations. The `triage_flag` is computed by explicit rules over
structured fields, for example:

```
URGENT  if posture == lying AND immobile_seconds > 60 AND injury_indicators non-empty
REVIEW  if posture == lying AND immobile_seconds > 30
REVIEW  if injury_indicators non-empty
OK      otherwise
```

Every flag carries a `triage_reason` in plain words ("lying, no movement for 71 s,
possible staining reported"). This is a deliberate design choice:

- an operator can see **why** and disagree,
- behaviour is reproducible and auditable after an incident,
- a model update cannot silently change the escalation policy,
- responsibility for the rules sits with the team, in a file, reviewable — not inside
  a black box.

These thresholds are **placeholders**. They must be reviewed with someone who has actual
SAR or emergency-medicine experience before any real use.

## Privacy and data handling

A drone that detects and describes people is a privacy-sensitive system regardless of
intent.

- **Consent for all collection flights.** Volunteers sign a written consent form covering
  what is recorded, how long it is kept, who sees it, and whether it may be published.
  Keep the signed forms with the dataset.
- **Do not fly over uninvolved people** during development. Use a closed area with
  permission from the property owner and the university.
- **Know the rules before flying.** Saudi UAV operation is regulated by **GACA**;
  registration, permitted zones, altitude limits and operator licensing apply, and
  campus/facility permission is separate from that. Check current requirements before
  every flight campaign — do not rely on what was true last semester.
- **Retention.** Define a retention period for flight footage and delete on schedule.
  Do not accumulate recordings of identifiable people indefinitely because storage is cheap.
- **Publication.** Blur or crop faces in any image used in a paper, poster or demo unless
  the volunteer explicitly consented to that specific use.
- **No identity inference.** The system does not attempt face recognition, re-identification
  across flights, or demographic labelling of individuals. Track IDs are per-flight and
  are not identities. This is a design boundary, not an oversight — do not add it later
  "because it would be easy".

## Scope boundary

RAPTOR **perceives and reports**. It does not fly the aircraft, plan paths, or command the
flight controller. The Jetson reads telemetry from MAVROS; it does not write control
commands to it. Keeping this boundary means a perception bug can never become a flight
safety incident, and it should be enforced in code (read-only MAVROS usage), not just by
convention.

## Model card

Before the project is presented or released, write a short model card covering: training
data sources and licences, collection conditions, measured performance broken down by
altitude and posture, known demographic gaps, measured hallucination rate, intended use,
and explicitly out-of-scope uses. If we cannot fill in a row honestly, that is the finding.
