---
title: RAPTOR — bill of materials and sourcing
tags: [raptor, bom, parts, sourcing, amazon-sa]
---

# Bill of materials

Everything still needed to finish the RAPTOR build, with amazon.sa listings found on
**2026-09-20**. Companion to [the wiring map](./raptor-wiring-map.html) and
[the build view](./raptor-build-view.html).

## Read this before you order

**These links came from searching amazon.sa, not from opening each page.** Amazon blocks
automated page fetches, so I could not read a single product page directly — which means
**I have not verified price, stock, seller, or delivery for any item here.** Prices and
availability change daily, and I cannot see your cart or what ships to your address.

So treat every link as *"this product looked like it matches the spec"*, not *"this is the
best deal"*. **Open the page and check it yourself before ordering** — in particular confirm
the connector type, the current rating, and that the listing still describes what the title
claims. Where I say "best value" or "the safe choice", that is a judgement about the
**product**, not about today's price.

Each item below lists **what it must satisfy**. That matters more than which listing you pick:
a cheaper part that meets the spec is fine, an expensive one that misses it is not.

Three items are **deliberately not orderable yet**. They are in their own section at the
bottom with the reason.

---

# Order now — nothing is blocking these

## 1. Micro-HDMI to HDMI cable

Camera out to capture card in.

**Must be:** **micro-HDMI (Type D)**, not mini-HDMI. Short — 1 m is plenty, and slack is the
enemy on an airframe. Thin and flexible, because this cable crosses the gimbal's vibration
dampers.

| Option | Note |
|---|---|
| [UGREEN Micro HDMI to HDMI](https://www.amazon.sa/-/en/UGREEN-Micro-Adapter-Cable-Speed/dp/B06WW3LPWL) | Sensible default |
| [Amazon Basics Micro-HDMI to HDMI, 2 m](https://amazon.sa/-/en/AmazonBasics-High-Speed-Micro-HDMI-HDMI-Cable/dp/B014I8U33I) | Cheap, a bit long |
| [Cable Matters micro-HDMI adapter, 2-pack, 15 cm](https://www.amazon.sa/-/en/Cable-Matters-Adapter-Support-Raspberry/dp/B00JDRHQ58) | **Worth considering** — a short pigtail adapter plus a normal HDMI cable gives better strain relief at the camera, and a spare |

> **Careful:** several listings that come up in this search are **mini**-HDMI, including two
> Amazon Basics ones. The A8 mini is micro. They are different connectors and the wrong one
> will not seat.

## 2. HDMI capture card

**Must be:** **UVC class** (so it appears as `/dev/video0` with no driver) and a genuine
**USB 3.0** device. On USB 2.0 it will silently drop to MJPEG, 720p or a lower frame rate
instead of erroring — which is the worst possible failure mode, because it looks like it works.

| Option | Note |
|---|---|
| [Magewell USB Capture HDMI Gen2](https://www.amazon.sa/-/en/Magewell-USB-Capture-HDMI-Gen2/dp/B07NVTKDX3) | **The safe choice.** Magewell is the one brand with a reliable Linux/Jetson track record. Expensive |
| [Magewell USB3.0 HDMI (older model)](https://www.amazon.sa/-/en/Magewell-USB3-0-Video-Capture-Device/dp/B00I16VQOY) | Same family, cheaper |
| [StarTech UVCHDCAP](https://www.amazon.sa/dp/B07D698K5D) | Explicitly advertises UVC and Linux |
| [Tobo USB 3.0 to HDMI](https://www.amazon.sa/-/en/Tobo-Compatible-Streaming-Teaching-Conference/dp/B08HS8793B) | Budget; claims UVC + Linux |
| [VIXLW USB 3.0 with loop-out](https://www.amazon.sa/-/en/VIXLW-Capture-Loop-Out-Streaming-Compatible/dp/B0D8L4CS6V) | Budget; loop-out is not useful to us |

> **My recommendation:** pay for the Magewell. This part sits in the perception path — if it
> drops frames intermittently at altitude you will spend weeks blaming the detector. The
> budget cards are worth trying only if you are willing to run the `lsusb -t` / `v4l2-ctl`
> check properly and return it if it fails.

**Acceptance test:** `lsusb -t` must read **5000M**, and `v4l2-ctl -d /dev/video0
--list-formats-ext` must offer an uncompressed format at 1080p30.

## 3. microSD cards — buy two, and they are not the same card

These two jobs want different cards. Do not buy two of one.

| Job | Card type | Option |
|---|---|---|
| **A8 mini onboard recording** — continuous video writes | **High-endurance**, video-rated | [SanDisk High Endurance 128 GB](https://www.amazon.sa/-/en/SanDisk-Endurance-MicroSDXC-Adapter-Monitoring/dp/B07NY23WBG) or [MAX Endurance 128 GB](https://www.amazon.sa/-/en/SanDisk-ENDURANCE-microSDXC-Adapter-security/dp/B084CJ9T2R) |
| **Jetson boot media** (only if your module boots from microSD, not eMMC) | **A2 app-performance**, high random IOPS | [SanDisk Extreme PRO 128 GB A2](https://www.amazon.sa/-/en/SanDisk-Extreme-microSDXC-RescuePRO-Performance/dp/B09X7DNF6G) |

Endurance cards are tuned for sequential video and are *slow at random I/O* — a poor boot
disk. A2 cards are the reverse. Using one for the other's job works, badly.

> Onboard recording is the **only** way to get real 4K out of the A8 mini. Every live output
> caps at 1080p.

## 4. XT60 / XT30 connectors and wire

The pack lead is EC5 with an XT60 adapter already fitted, so **XT60 is the junction standard**
and XT30 suits the lower-current branches (camera, Jetson).

| Option | Note |
|---|---|
| [FPVDrone 52-piece kit — XT60 + 14 AWG silicone wire + heatshrink](https://www.amazon.sa/-/en/FPVDrone-Connector-Adapters-Silicone-Battery/dp/B082CVS6HC) | **Best value** — covers connectors, wire and shrink in one order |
| [XT60 10 pairs with heatshrink](https://www.amazon.sa/-/en/Connectors-XT-60-Female-Bullet-Shrink/dp/B07DVDKL42) | Connectors only |
| [Finware XT60 10 pairs](https://www.amazon.sa/-/en/Finware-Female-Bullet-Connectors-Battery/dp/B01ETROGP4) | Connectors only |
| [GTIWUNG XT30 with 16 AWG pigtails](https://www.amazon.sa/-/en/GTIWUNG-Connector-Silicone-Female-Battery/dp/B0CKZ1N86B) | **XT30 — get these too**, pre-wired pigtails save soldering |

## 5. Pixhawk 6C looms

You need JST-GH 1.25 mm cables for POWER1, TELEM1 (to the Jetson), the camera control port,
GPS1 and PPM/SBUS RC. Buy a kit — individual looms cost more and you will want spares.

| Option | Note |
|---|---|
| [XUGERIP GH1.25 kit, 180 pcs — lists Pixhawk 6C](https://www.amazon.sa/-/en/XUGERIP-GH-Dupont-Pre-Crimped-JST/dp/B0CW6J3NXM) | Explicitly for the 6C |
| [elechawk GH1.25 to Dupont, 6C/6X](https://www.amazon.sa/-/en/elechawk-Pre-Crimped-Connectors-Compatible-Pixhawk4/dp/B0CLD7S5VC) | Good if you need to break out to Dupont |
| [GH1.25 to GH1.25 pre-crimped kit](https://www.amazon.sa/-/en/Crimped-Connector-Compatible-Silicone-Controller/dp/B0GKSMDLF1) | GH-to-GH, closest to stock looms |

**Check the Pixhawk box first.** A 6C normally ships with a power module and a loom set. From
the bench photos you already have wiring on the aircraft, so you may only need spares. Only if
the power module is genuinely missing:
[PM02-style with XT60 and GH connector](https://www.amazon.sa/-/en/Pixhawk4-PXFmini-Pixracer-Quadcopter-Connector/dp/B07PHRS4C4)
· [PM07 with 5 V UBEC](https://www.amazon.sa/-/en/Management-Module-Output-Pixhawk-Controller/dp/B09NCBZJTF).

## 6. Propellers — 1045 (10″ × 4.5″)

**Must be:** 1045 size, supplied as **matched CW + CCW pairs** (often sold as "1045 and
1045R"). You need 4 fitted plus at least 4 spare.

| Option | Note |
|---|---|
| [XYWHPGV 1045 self-locking, 4 pairs](https://www.amazon.sa/-/en/XYWHPGV-Propellers-10x4-5-Self-locking-Quadcopter/dp/B0CQLPBFBF) | 8 props, CW/CCW |
| [XEBRAD 1045, 5 pairs](https://www.amazon.sa/-/en/XEBRAD-5pair-Propellers-propeller-Propeller/dp/B0DSFNGB3X) | Most spares per order |
| [uxcell 1045 nylon, 5 pairs with adapter rings](https://www.amazon.sa/dp/B07PYNBQGX) | Includes bore adapter rings |
| [XYWHPGV 1045, 2 pairs with adapter rings](https://www.amazon.sa/-/en/XYWHPGV-Propellers-10x4-5-Quadcopter-Adapter/dp/B0CT5PH1G4) | Smallest quantity |

> **These are generic F450/F550-class 1045s, not genuine Holybro parts.** Before ordering,
> check how your props currently attach — the X500 V2 uses self-tightening hubs on 2216-class
> motors, and a generic prop may need the right **adapter ring** for the shaft bore, or may not
> self-tighten at all. If in doubt, buy genuine Holybro 1045 V2 from a drone dealer instead
> (see the last section). A prop that unscrews in flight is not a place to save money.

## 7. USB hub — read the warning

**Must be:** USB 3.0, and **airborne-compatible**.

> **The gotcha:** almost every "powered USB hub" on Amazon is a *desktop* hub with a 5 V mains
> wall adapter. That is useless on a drone. What you want is either a **bus-powered** hub, or
> one with an **auxiliary 5 V input** you can feed from the buck converter.

| Option | Note |
|---|---|
| [ORICO 4-port USB 3.0 with extra power input (no adapter included)](https://www.amazon.sa/-/en/Aluminum-Splitter-Desktop-Monitors-Desks-Black/dp/B09289CSMN) | **Best fit** — the aux power port is exactly what you want to feed from the buck |
| [UGREEN 4-port USB 3.0, slim, bus-powered](https://amazon.sa/-/en/UGREEN-Splitter-Aluminum-Extension-Compatible/dp/B07VKNWJ67) | Light and simple, if the capture card's draw allows |
| [4-port slim aluminium, bus-powered](https://www.amazon.sa/-/en/4-Port-Aluminum-Expander-Portable-Splitter/dp/B08DTP76YR) | Budget alternative |

You may not need a hub at all — it depends on how many USB 3.0 ports the carrier board exposes,
which is still unknown. Consider deferring this one item until the carrier arrives.

## 8. Multimeter

Not on the handwritten list, but **step 04 of the bench build order does not work without
one**: you must meter the buck converter's output *before* the Jetson is ever plugged into it.
This is the step that destroys a Jetson.

| Option | Note |
|---|---|
| [ANENG Q1 True-RMS](https://www.amazon.sa/-/en/True-RMS-Digital-Multimeter-Capacitance-Voltage/dp/B09XLFWC2R) | Cheap and adequate for this |
| [RICHMETERS RM409B True-RMS](https://www.amazon.sa/-/en/RICHMETERS-True-RMS-Digital-Multimeter-Temperature/dp/B08S78CFTV) | Good value |
| [BSIDE ADM92 pocket](https://www.amazon.sa/-/en/BSIDE-Multimeter-Auto-Ranging-Temperature-Capacitance/dp/B07F5DJYQ6) | Compact, fits a field kit |
| [Fluke 179](https://www.amazon.sa/-/en/Fluke-179-True-Digital-Multimeter/dp/B00012Z0V6) | If the lab budget stretches — it will outlive the project |

For this job any of them is fine. DC volts to 30 V is all you strictly need.

## 9. Standoffs for the second deck

The [build view](./raptor-build-view.html) puts deck 2 at **125 mm**, with the top plate at
**55 mm** — so you need roughly **70 mm** of standoff.

| Option | Note |
|---|---|
| [Creative-Idea 360 pcs M2/M2.5/M3 nylon assortment](https://www.amazon.sa/-/en/Creative-Idea-Assortment-Computers-Replace-Fastener/dp/B07WSCZ2KH) | Widest range of lengths to stack |
| [Aexit M3 hex spacer + screw + nut kit, 120 pcs](https://www.amazon.sa/-/en/Aexit-Spacers-Assortment-creamy-white-45ry504qf183/dp/B07DW25V23) | M3 only, includes hardware |
| [Aexit M3 × 18 mm nylon, 100 pcs](https://www.amazon.sa/-/en/Aexit-Electrical-equipment-Standoff-70ry876qf562/dp/B07L7JD532) | Stack four for ~72 mm |

> **A 70 mm nylon standoff carrying a Jetson will flex**, and flex on a flight controller deck
> means vibration the FC has to filter out. Prefer **aluminium** standoffs at this height, or
> shorten the deck. Nylon is fine for the short stacks lower down. This is also why step 07 of
> the build order says to check the FC's vibration logs before fitting props.

You will also need a plate for deck 2 — 3 mm carbon or acrylic, cut to about
**140 × 140 mm**. That is a laser-cutter / workshop job, not an Amazon one.

---

# Do not order yet

## 10. DC-DC buck converter — blocked on one unknown

**This is the part most likely to be bought wrong.** Its output voltage depends entirely on
which carrier board the Orin NX is on — commonly **5 V, 12 V or 19 V** — and that is still an
open question in [STATUS.md](../../ProgressReports/STATUS.md).

**Must be:** adjustable, input rated well above 16.8 V pack voltage, and — critically — able to
supply the Orin NX at its highest `nvpmodel` mode **plus headroom**. Synchronous, not a bare
LM2596.

| Option | Note |
|---|---|
| [DROK adjustable 5 A with LCD, 2-pack](https://www.amazon.sa/-/en/DROK-Adjustable-Converter-Transformer-Protective/dp/B0CXT83GV6) | LCD lets you set the voltage before connecting anything |
| [Adjustable 5 A with LED display, CC/CV](https://www.amazon.sa/-/en/Converter-Voltage-Regulator-1-2V-32V-Reducer/dp/B0D674QM3C) | Current limit is a useful safety net |
| [D-PLANET 5 A adjustable, 4-pack](https://www.amazon.sa/dp/B079N9BFZC) | Cheap, spares included |

> **Do not buy the 2 A LM2596 modules** that dominate this search — for example
> [this LM2596 2 A listing](https://www.amazon.sa/-/en/LM2596-Converter-4-0-40V-1-25-37V-Voltmeter%EF%BC%882pcs%EF%BC%89/dp/B085WC5G8N).
> They cannot feed an Orin NX and will brown out under load, which looks like random Jetson
> reboots rather than an obvious power fault.
>
> **And remember why item 5 was crossed out on the handwritten list:** a "volt meter" module
> *measures* voltage and passes it through unchanged. It will not protect the Jetson.

**Unblock it by:** identifying the carrier board, reading its input spec, then ordering.

## 11. USB-TTL serial adapter — only if needed

Needed only if the carrier board does not expose a usable 3.3 V UART for the Pixhawk TELEM1
link. Decide after the carrier arrives.

**Must be: 3.3 V logic.** A 5 V adapter on a Pixhawk TELEM port can damage the flight
controller.

| Option | Note |
|---|---|
| [DSD TECH SH-U09B3, CP2102N](https://www.amazon.sa/-/en/DSD-TECH-SH-U09B3-Adapter-CP2102N/dp/B09KXT6W46) | Selectable levels, good build |
| [Coolwell CP2102, 3.3 V](https://www.amazon.sa/-/en/Coolwell-Communication-Converter-Compatible-Connector/dp/B09F6CZBYT) | Explicitly 3.3 V |
| [HiLetgo CP2102](https://www.amazon.sa/-/en/HiLetgo-CP2102-Converter-Adapter-Downloader/dp/B00LODGRV8) | Cheapest; check the jumper is set to 3.3 V |

## 12. VTX air unit — not sold on amazon.sa, and gated on a test

**I searched and it is not there.** amazon.sa returns consumer drones and generic
HDMI-over-Ethernet extenders, none of which are a SIYI air unit. Source it from SIYI directly,
AliExpress, or a regional drone dealer.

**More importantly, do not buy it yet regardless.** The downlink is
[optional](./raptor-build-view.html), and whether it is even possible depends on an untested
question: **can the A8 mini output HDMI and Ethernet at the same time?** The manual describes
video output as a *switchable mode*. If it cannot, there is nothing for a VTX to receive.

That test costs ten minutes and no money — enable HDMI output, confirm the capture card sees a
picture, then check whether `rtsp://192.168.144.25:8554/video1` still opens. **Run it before
spending anything here.**

---

# Also needed, probably already in the lab

Not worth ordering if the workshop has them: soldering iron and solder, heat gun, wire
strippers, zip ties, Velcro battery straps, cable sleeving, and a **bench power supply**
(12 V, 2 A current limit) for step 01 of the build order. The bench supply is the single most
useful item on this list for not destroying hardware — borrow one if you must.

---

# Quick order summary

| # | Item | Qty | Status |
|---|---|---|---|
| 1 | Micro-HDMI (Type D) to HDMI cable | 1 + spare | Order now |
| 2 | UVC USB 3.0 capture card | 1 | Order now |
| 3 | microSD — high-endurance | 1 | Order now |
| 3b | microSD — A2 app-performance | 1 | Order now |
| 4 | XT60 kit + 14 AWG silicone wire + heatshrink | 1 kit | Order now |
| 4b | XT30 pigtails | 1 set | Order now |
| 5 | JST-GH 1.25 loom kit | 1 kit | Order now |
| 6 | 1045 props, CW/CCW | 4 + 4 spare | Order now — **check hub fit first** |
| 7 | USB 3.0 hub with aux power input | 1 | Order now, or defer to carrier |
| 8 | Multimeter | 1 | Order now |
| 9 | M3 standoffs (prefer aluminium at 70 mm) | 1 kit | Order now |
| 9b | Deck 2 plate, ~140 × 140 mm | 1 | Workshop, not Amazon |
| 10 | DC-DC buck converter | 1 | **Blocked** — carrier voltage unknown |
| 11 | USB-TTL 3.3 V adapter | 0 or 1 | **Decide after carrier arrives** |
| 12 | VTX air unit | 0 or 1 | **Not on amazon.sa**, and gated on the HDMI/Ethernet test |

---

*Links gathered from amazon.sa search results on 2026-09-20; product pages could not be opened
to confirm price or stock. Verify on the page before ordering. Nothing in this list has been
bought, received or fit-checked.*
