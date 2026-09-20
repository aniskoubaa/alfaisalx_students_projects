---
title: RAPTOR harness revision — control/video split, optional downlink
tags: [raptor, wiring, harness, pixhawk, siyi-a8-mini, jetson, vtx]
---

# What this session changed

Rewrote `RAPTOR/docs/raptor-wiring-map.html` from three new sources: a handwritten harness
sketch, a handwritten nine-item components list, and five bench photographs of the actual
aircraft now in `RAPTOR/imgs/`.

The page was previously built around a guess at the topology. It is now built around what was
drawn and what is physically on the airframe, with the parts of it that are still inference
marked as such.

# The architectural decision

The camera's three ports now do three clearly separated jobs, and this is the change that
matters most:

| Port | Goes to | Job | Status |
|---|---|---|---|
| Control port | Pixhawk 6C | **Pointing** the gimbal | required |
| micro-HDMI | Capture card → Jetson | **Seeing** — the perception feed | required |
| Ethernet | VTX → ground station | **Showing** — the operator's picture | optional |

**Why the Pixhawk owns the gimbal.** It already has the attitude solution and the pilot's stick
input. Putting pointing on the flight controller keeps the mount under one authority and avoids
the Jetson and the operator fighting over it.

**Why the VTX is now optional.** Nothing in the perception path needs it. The Jetson's video
arrives over HDMI and never leaves the aircraft, so the downlink can be added, deferred, or
dropped entirely without touching anything else. This also means the VTX should be bought
*last*.

**Why the camera gets its own battery branch.** An earlier reading of the sketch had the camera
powered from the VTX. That was reversed for two reasons: SIYI explicitly advises powering the
gimbal straight off the pack rather than through a PDB or air unit, and — more decisively — if
the VTX is optional, nothing required may depend on it for power.

# The consequence nobody has decided yet

Handing the gimbal to the Pixhawk means **the Jetson can no longer point the camera directly**.
To aim it, the perception stack must send a MAVLink gimbal command to the flight controller over
TELEM1 and let the FC act on it.

That is a **write**, and the design docs currently state that the Jetson reads telemetry and
never writes. Two ways out, and one must be chosen before the gimbal node is written:

1. The Jetson may write gimbal commands only — never anything that affects flight; or
2. Pointing stays entirely manual, and the Jetson watches wherever the pilot aims.

This is unresolved and is now flagged on the wiring page.

# What the photographs confirmed

Read off `RAPTOR/imgs/img1–5.jpeg`. All of this is now recorded in an "airframe, as built"
section on the wiring page.

- **Frame: Holybro X500 V2** — 500 mm quad, carbon tube arms, 10" props. Arm clamps and motor
  mounts have been swapped for blue 3D-printed parts. Stock prop size is 1045 — see the
  correction in the second pass below; the first pass misread the parts list as "10, 4S".
- **Pixhawk 6C** mounted centre of the top deck. Ports legible in the photo: POWER1, POWER2,
  GPS1, GPS2, TELEM2, TELEM3, CAN1, CAN2, I2C, USB, DSM, SBUS OUT, PPM/SBUS RC, PWM MAIN and AUX.
- **Holybro M9N** GPS on a mast, with the arming switch and fix LED in the dome.
- **RadioMaster R86C** receiver, 2.4 GHz V2, S.Bus and PWM out, CH1–CH6. Only six channels —
  they need budgeting before any are promised to a gimbal axis.
- **SIYI A8 mini is already mounted**, under the nose on a four-ball damped plate. Its breakout
  connector is loose; nothing is plugged in. Mounted is not the same as powered — it still has
  never been powered.
- **Battery lead is EC5 with an EC5-to-XT60 adapter** already fitted, so XT60 is the junction
  standard downstream and XT30 suits the camera and Jetson branches.

# New problem found: the Jetson has nowhere to go

The X500 V2 top deck is roughly 180 × 180 mm, and in the photos the Pixhawk and the R86C already
occupy most of it. An Orin NX on a carrier, plus a capture card, plus a USB hub, plus cabling,
will not fit in what is left.

This is not cosmetic. It decides the buck converter's position, the length of the micro-HDMI run
from the damped nose plate, and the centre of gravity. Likely answers are a second deck above the
FC or a plate slung under the battery tray. **Resolve it before buying the VTX.**

# Parts list, as recorded

Nine items, with item 5's ink correction preserved on the page: **"adjustable volt meter" was
struck out and replaced with a DC–DC buck converter.** That correction is load-bearing — a volt
meter measures voltage and passes it through unchanged, so a Jetson wired behind one still sees
full pack voltage.

# Still unanswered

1. Which **carrier board** is the Orin NX on? Sets the buck output — 5, 12 or 19 V.
2. **Where does the Jetson physically mount?** See above.
3. **ArduPilot or PX4** on the 6C? Decides the camera control port's protocol and mount parameters.
4. Can the A8 mini output **HDMI and Ethernet simultaneously**? The manual calls video output a
   switchable mode. If it cannot, the downlink option does not exist and no VTX should be bought.
   The required path is unaffected either way — this is the cheapest high-value test available.
5. Is the **Jetson allowed to write** gimbal commands?

# Files touched

- `RAPTOR/docs/raptor-wiring-map.html` — rewritten: new diagram, new "two paths to the picture"
  section, new "airframe, as built" section, parts list, 13-link connection table, 8-step bench
  order. Added a doctype, charset and viewport meta, which the file previously lacked.
- `ProgressReports/2026-09-20-raptor-harness-revision.md` — this note.

`RAPTOR/imgs/` is untracked in git. It should be committed if these photos are the reference for
the build.

# Caveat that still stands

Nothing on the *harness* side has been measured. The camera has still never been powered, every
height and cable length in the build view is an estimate, and no harness figure belongs in a
report as a finding until it comes off the actual aircraft.

This is narrower than it was: detector and VLM benchmarks have since been run on the Orin NX and
are recorded in `RAPTOR/docs/10-detector-benchmark-results.md` and `12-vlm-benchmark-results.md`.
Those numbers are measured. The ones on this page are not.

# Second pass: control/video split and the build view

After the first rewrite, three corrections came in and a second page was built.

## Corrections applied

1. **Gimbal control moved to the Pixhawk.** The A8 mini's **control port** goes to the flight
   controller, not the Jetson. The FC has the attitude solution and the pilot's sticks, so it owns
   the mount.
2. **The Jetson's video path is HDMI only** — micro-HDMI into the capture card, over USB 3.0.
3. **The VTX/Ethernet downlink is now explicitly optional**, an alternative way to get a picture to
   a ground station or handheld controller. Nothing required depends on it.
4. **Props are Holybro 1045 V2 — 10" diameter, 4.5" pitch.** The handwritten "10 45" was the size
   code, not a 4S cell count. This was recorded wrongly in the first pass and is now fixed
   everywhere.

## The keep-out number, and what it settles

A 1045 prop is 254 mm across. With motors 250 mm from centre, the props' inner edge is at
**250 - 127 = 123 mm**. That circle is the constraint on the whole build:

- Inside 123 mm you may stack **as tall as you like** — the props never pass over it.
- Outside it, at prop height, nothing may exist.

This resolves the "the Jetson has nowhere to go" problem raised earlier. A typical Orin NX carrier
is about 130 x 120 mm, whose furthest corner is **88.5 mm** from centre — clearing the keep-out by
about 35 mm. So **a second deck on standoffs above the Pixhawk works.** The cost is centre of
gravity and prop wash over the heatsink, not clearance.

Adjacent prop tips are about 100 mm apart, so the props are nowhere near each other.

## New file: RAPTOR/docs/raptor-build-view.html

A companion to the wiring map that puts the harness on the airframe:

- **Interactive 3D model** of the X500 V2 (three.js from a CDN) — orbit, zoom, iso/top/front/side
  presets, and power / data / frame layer toggles. Every part is clickable; cables are drawn as
  coloured tubes following their actual routes. Mounted parts are solid, proposed parts are ghosted.
- **Plan view, to scale** — prop discs, the 123 mm keep-out circle, and the proposed Jetson
  footprint inside it.
- **Side elevation** — deck order and heights, the prop disc, and the 178 mm vertical micro-HDMI run.
- **Cable schedule** — 13 runs with routes and rough-cut lengths, generated from the same data as
  the 3D model so the two cannot drift apart.
- **Assembly order** — mechanical, then power, then data.

The two SVG drawings are generated from a script rather than hand-drawn, so the geometry is exact.
If three.js cannot load (no network on the bench), the 3D canvas stays blank but the drawings and
the cable schedule still work — that is the part you actually need while wiring, and the page says so.

Linked from `RAPTOR/README.md`, `RAPTOR/docs/README.md` and `ProgressReports/STATUS.md`.

## New thing to decide

The micro-HDMI run crosses the vibration isolators: from the camera hanging below the frame up to a
capture card on a deck above the Pixhawk. It must not stiffen the dampers, and it must tolerate the
gimbal panning underneath. Leave a service loop at the gimbal end and anchor the cable to the frame
**above** the dampers, never across them.
