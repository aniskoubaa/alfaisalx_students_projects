# TurtleBot 4 campus food delivery: parts list

Written 2026-11-12 for task [TB-29](../ROADMAP.md#tb-29-campus-food-delivery-along-the-wall-supervised-demo). Nothing here has been bought or fitted. Every item is a proposal for the lab to approve.

## How to read this list

- **Priority.** `Before campus` = needed for the first mapping and supervised runs. `Before demo` = needed for the demo with a vendor and a student ([delivery/README.md, section 10](../delivery/README.md#10-phase-3-demo-checklist)). `Later` = useful, not blocking.
- **Prices** are in SAR, seen on **2026-11-12**. Amazon.sa pages were opened and read on that date. Amazon prices move by a few riyals between page loads and show several sellers, so treat every price as "about" and confirm in the basket. Where a price could not be confirmed, the row says so.
- **Links.** Amazon.sa links opened (HTTP 200) on 2026-11-12. Links marked `blocked` belong to shops that refuse automated requests (noon.com timed out, desertcart.com.sa returned 403): they came from a search result and could not be opened here, so open them yourself. Local shops (Jarir, Extra, electronics shops) were not checked.
- **Nothing was tested on the robot.** The robot was not touched. Specifications below come from seller listings and from the project documents; the sellers' "works on Linux" claims are marketing, not tests on this Pi.

## Already have (from the project documents)

| Item | Where it is mentioned |
|---|---|
| TurtleBot 4 with Raspberry Pi 4, Create 3 base, RPLIDAR, OAK-D camera, charging dock | [README.md](../README.md), [MAINTENANCE.md](../MAINTENANCE.md) |
| TurtleBot 4 controller (the emergency stop button B and the robot-moving buttons) | [delivery/README.md, section 2](../delivery/README.md#2-safety-first) |
| Ethernet cable for the direct link to the robot | [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md) |
| Lab router (Linksys, Wi-Fi `AlfaisalX`) | [MAINTENANCE.md](../MAINTENANCE.md), lab router section |
| Laptop with TurtleBot Studio | [tools/studio/README.md](../tools/studio/README.md) |

Not listed in the documents, so please check before buying: whether the controller has spare batteries or a charging cable with it, and which USB ports of the Pi are already used (lidar, OAK-D camera and possibly others). The second point decides whether a speaker needs a hub (see item 3.3).

## 1. Campus run and mapping

| # | Item | Why it is needed | Specification that matters | Qty | Options (SAR, 2026-11-12) | Priority |
|---|---|---|---|---|---|---|
| 1.1 | Steel tape measure, 10 m | TB-29 "Next steps for the campus trip", step 3: measure one known distance on the floor and the same on the map; a map more than about 3 % short must not be used (the slam_toolbox shrinking finding, [Known issues](../MAINTENANCE.md#known-issues)) | 10 m, metric scale, locking blade. The route is 50 to 100 m, so the tape is only for one check length | 1 | [Total 10 m](https://www.amazon.sa/-/en/Measuring-Reading-Metric-Imperial-Inches/dp/B07ZX9GT79): price not pinned, page and search showed between about 22 and 40. [Finder 10 m](https://www.amazon.sa/-/en/Finder-Retractable-Professional-Measurement-Intensive/dp/B07BT9523K): price not confirmed. [Stanley 10 m](https://www.amazon.sa/-/en/STANLEY-Steel-Closed-Measuring-10Mtr/dp/B0001IW6QC): search result showed about 93 for another Stanley model, this one not confirmed | Before campus |
| 1.2 | Laser distance meter, 40 m (optional upgrade for 1.1) | Measure the whole route and the dock distance in seconds instead of walking a tape along 50 m | 40 m range, 1.5 mm class accuracy is plenty | 1 | [Bosch GLM 40 on desertcart](https://www.desertcart.com.sa/products/48310159-bosch-professional-laser-measure-glm-40-with-memory-function-measuring.md) (`blocked`): about 602 in the search result. A generic 40 m unit was listed on Fruugo at about 99; not opened. Not confirmed | Later |
| 1.3 | Floor markers (masking tape or coloured gaffer tape) to mark the tape-measure points and slow zones | Marks the measured distance for the map check and the ramp and cable zones on the speed mask | Any removable floor tape that the campus allows | 1 roll | Not searched. Any stationery shop | Before campus |

## 2. Carrying food on the robot

The robot's maximum speed is capped at 0.20 m/s with gentle acceleration so food does not spill ([delivery/README.md, section 2](../delivery/README.md#2-safety-first)). Nothing in the project documents says how the food is held on the robot's top plate. These items are proposals to close that gap.

| # | Item | Why it is needed | Specification that matters | Qty | Options (SAR, 2026-11-12) | Priority |
|---|---|---|---|---|---|---|
| 2.1 | Non-slip liner roll (non-adhesive) | Stops a food box sliding on the plastic top plate during starts, stops and ramps | Non-adhesive (leaves no residue on the robot), rubber or PVC grip, cut to the plate size | 1 roll | [Gorilla Grip 12 x 120 in](https://www.amazon.sa/-/en/DripGuard-Non-Adhesive-Protector-Grip-Resistant/dp/B07Z44PVQZ): page showed 121.99 or 258.12, not pinned. [Smart Design Classic Grip 12 in x 10 ft](https://www.amazon.sa/-/en/Smart-Design-Classic-Shelf-Liner/dp/B01LVZ8EGA): price not confirmed. [Thick PVC roll, 1 ft x 30 ft](https://www.amazon.sa/-/en/Drawer-Shelf-Liner-NON-SLIP-WATERPROOF/dp/B08GY6LC1R): several figures shown (51.69, 184.00, 252.74), not pinned | Before campus |
| 2.2 | Insulated food bag or a lidded plastic box with a flat bottom | Gives the vendor one clear place to put the food and keeps a drink or a warm meal stable. A box with a lid also keeps food from spilling in a ramp or a bump | Footprint no wider than the top plate (check it with a tape on the robot; **NOT measured**), low and wide rather than tall (a tall load tips on ramps), light. Keep the total load low: the Create 3 payload limit is quoted by iRobot as about 9 kg, but **this was not checked against the TurtleBot 4 top plate**, so plan on 2 kg or less | 1 | [Insulated delivery bag XL with divider](https://www.amazon.sa/-/en/Insulated-Bags-Food-Delivery-Commercial/dp/B09VXKN188): 352.13 on its page, but 18 in wide, likely too big. [Insulated food delivery bag](https://www.amazon.sa/%D9%85%D8%B9%D8%B2%D9%88%D9%84%D8%A9-%D8%AD%D8%B1%D8%A7%D8%B1%D9%8A%D8%A9%D8%8C-%D8%A7%D9%84%D8%B7%D8%B9%D8%A7%D9%85-%D9%84%D9%84%D8%A8%D9%82%D8%A7%D9%84%D8%A9%D8%8C-%D9%84%D9%84%D9%85%D8%B7%D8%A7%D8%B9%D9%85/dp/B0BBPL2TWK): in stock, price not confirmed (search result showed about 217). A kitchen shop box is cheaper and easier to size: not searched | Before demo |
| 2.3 | Non-slip tray with a raised edge | A rim keeps loose items (a bottle, a bag) from sliding off if there is no box | Raised edge, silicone dots | 1 | [Rectangular non-slip serving tray with handles](https://www.amazon.sa/-/en/Rectangular-Serving-Handles-Silicone-Plastic/dp/B09DRHSL8Z): ships in 9 to 10 days, price not confirmed (search results for similar sets showed 193 to 300, which is high for the use) | Later |
| 2.4 | Hook-and-loop strap roll (reusable) | Holds the box to the top plate and the speaker and its cable to the robot without drilling or glue | Non-adhesive, 12 to 25 mm wide, black | 1 | [Velcro One-Wrap roll, 12 ft x 3/4 in](https://www.amazon.sa/-/en/VELCRO-Brand-ONE-WRAP-Double-Sided-Multi-Purpose/dp/B000078CUB): 50.82 on its page, in stock. [Pack of 50 cable ties plus roll](https://www.amazon.sa/-/en/Pack-Velcro-Cable-Ties-Black/dp/B09PDK65BL): price not confirmed | Before campus |

## 3. Spoken messages

Plan and reasoning: [SPOKEN-MESSAGES.md](SPOKEN-MESSAGES.md). The Create 3 can only play tones on `/cmd_audio`, so speech needs a sound output on the Pi.

| # | Item | Why it is needed | Specification that matters | Qty | Options (SAR, 2026-11-12) | Priority |
|---|---|---|---|---|---|---|
| 3.1 | Small USB-powered speaker with a 3.5 mm cable, or a true USB speaker | Lets the robot say "Your food is here" to the vendor and the student; the chimes alone say nothing about which person should act | Powered from a Pi USB port (5 V, at most a few hundred mA), loud enough for a food court (**NOT tested**), volume knob, short cable. A speaker with a 3.5 mm audio input needs item 3.2 (or the Pi's own 3.5 mm jack) as the sound source; a "true USB" speaker contains its own sound chip and needs nothing else | 1 | [USB mini computer speakers, 3.5 mm TRS, volume control](https://www.amazon.sa/-/en/Computer-Speakers-Desktop-USB-Powered-Adjustment/dp/B0H1HLHW9W): 52.64, in stock. [Aookay USB sound bar](https://www.amazon.sa/-/en/Computer-Portable-Speakers-Bar-Plug-Compatible/dp/B08TQB798P): 99.95, in stock. [Small PC speakers, 3.5 mm Aux, USB powered](https://www.amazon.sa/-/en/Computer-Speakers-Powered-Desktop-Soundbar/dp/B08C2F61FN): 192.00, ships in 9 to 10 days. Quantum QHM611 on desertcart (`blocked`): about 43 in a search result, not confirmed | Before demo |
| 3.2 | USB sound adapter (USB to 3.5 mm) | A class-compliant USB audio device works on Ubuntu without a driver and is a better sound source than the Pi's own jack (the Pi jack is shared with video and is often noisy) | USB Audio Class, "no driver", bus-powered, one 3.5 mm output. Avoid models that need software | 1 | [UGREEN USB sound card, aluminium](https://www.amazon.sa/-/en/UGREEN-Aluminum-External-Compatible-Raspberry/dp/B087T5H3MQ): listing names Raspberry Pi 4, the price could not be pinned (the page showed 18.99, 99.99 and 140.00 for different offers). [UGREEN 2-in-1 sound card](https://www.amazon.sa/-/en/UGREEN-External-Adapter-adapter-Compatible/dp/B016CU2PEU): price not pinned (27.98 and 99.99 shown). [Noon listing](https://www.noon.com/saudi-en/usb-external-sound-card-audio-adapter-2-in-1-usb-to-3-5-mm-jack-audio-adapter-aluminum-stereo-compatible-with-windows-mac-ps5-linux-pc-laptops-desktops-silver/N46345022A/p/) (`blocked`). Budget about SAR 30 to 60 | Before demo |
| 3.3 | Short USB 2.0 extension cable, right angle (or a small powered USB hub if no port is free) | Lets the speaker sit where the sound is not muffled without a cable hanging across the lidar. Whether a free USB port exists is **NOT known** | USB 2.0 A male to A female, 0.5 to 1 m, right angle. Do not put a bulky hub on a robot that already has the lidar and the camera on USB 3 | 1 | [USBGear 3 ft right angle](https://www.amazon.sa/-/en/USBGear-White-Extension-Cable-Female/dp/B01N63UBWR): 33.96, in stock. [Amazon Basics 1 m extension](https://www.amazon.sa/-/en/Amazon-Basics-Extension-Female-Adapter/dp/B00NH11R3I): price not pinned (about 31 to 38 shown) | Before demo |

## 4. Power and spares

| # | Item | Why it is needed | Specification that matters | Qty | Options (SAR, 2026-11-12) | Priority |
|---|---|---|---|---|---|---|
| 4.1 | Spare microSD card with a copy of the robot's disk image | Known issues: 240 package upgrades by themselves (2026-10-24), clock steps, a kernel change. A copy of a working card is the fast way back if an update or a power loss damages the card | 64 GB, high endurance (the Pi writes logs all day), A1 or better. A copy needs a card reader on the laptop (not in this list) | 1 | [SanDisk High Endurance 64 GB with adapter](https://www.amazon.sa/-/en/SanDisk-Endurance-MicroSDXC-Adapter-Monitoring/dp/B07P3D6Y5B): 90.00, in stock ([SanDisk page](https://www.sandisk.com/ar-sa/products/memory-cards/microsd-cards/sandisk-high-endurance-uhs-i-microsd)). [SanDisk Max Endurance 64 GB](https://www.amazon.sa/-/en/SanDisk-ENDURANCE-microSDXC-Adapter-security/dp/B084CJ96GT): 202.00 (more than needed). A third Saudi reseller (sa.tilga.com) listed about 100: not opened here | Before demo |
| 4.2 | Spare USB cable for the RPLIDAR and the camera | Known issue: the lidar was "not detected" on 2026-10-03 and the fix was a loose USB cable reseated by hand. A spare identical cable shortens any repeat | Same connector type as the robot's current lidar cable (**not checked**, check which cable the lidar uses before ordering) | 1 | Not searched, because the connector type is not known | Before campus |
| 4.3 | Power bank, 10 000 mAh, USB-C 20 W (contingency) | Only if the Pi's USB ports cannot feed the speaker (power budget not measured) or for the laptop and phone during a long walk | USB-C PD 20 W, with a USB-A port | 1 | [Anker PowerCore Slim 10K PD](https://www.amazon.sa/-/en/Anker-Portable-10000mAh-Delivery-PowerCore/dp/B08LH26PFT): 154.90, in stock. [Noon listing](https://www.noon.com/saudi-en/power-bank-usb-c-portable-charger-10000mah-with-20w-power-delivery-523-power-bank-powercore-slim-10k-pd-for-iphone-14-series-iphone-13-series-s20-pixel-4-and-more-black/N53372759A/p/) (`blocked`) | Later |
| 4.4 | Spare Create 3 or robot battery | Not proposed: the project documents give no battery limit as a problem (the mission refuses below its minimum battery), and a battery is expensive. Revisit after the first campus run shows the real use per round trip | | 0 | | Later |

## 5. Safety

| # | Item | Why it is needed | Specification that matters | Qty | Options (SAR, 2026-11-12) | Priority |
|---|---|---|---|---|---|---|
| 5.1 | High-visibility vest for the person walking behind the robot | A supervised run needs the follower to be recognisable as the robot's operator to the vendor, guards and passers-by; the route is crowded outside quiet hours | Fluorescent, reflective strips, adjustable | 1 to 2 (follower and a spare) | [Orange safety vest, reflective straps](https://www.amazon.sa/-/en/Visibility-Clothing-Reflective-Construction-Traffic/dp/B0DFWJWM68): 25.19, in stock (page said 2 left). [A-Safety vest, 21 colours](https://www.amazon.sa/-/en/SAFETY-Visibility-Reflective-Pockets-X-Small/dp/B0BB6L7CP7): 178.51 | Before campus |
| 5.2 | Printed sign "Robot in operation, please keep clear" on the robot or the follower's back | The lidar does not see glass or cables; people should know the robot is supervised and may stop | A4, laminated or in a plastic sleeve. The wording needs the lab's and the campus' approval (**to be decided**) | 1 | Print shop on campus. Not searched | Before demo |
| 5.3 | Flashing LED beacon for the robot (USB or clip-on) | Makes the robot visible in a crowded corridor | A bicycle rear light is the cheapest reliable one: red, clip, own battery (so it does not draw from the Pi), flashing mode | 1 | [Smart bike tail light, USB rechargeable](https://www.amazon.sa/-/en/Flashing-Warning-Rechargeable-Ultra-Bright-Bicycle/dp/B0F7XF4NRF): 130.76, in stock | Later |

The software emergency layers are the controller button B, Studio's E-STOP and `~/STOP` ([section 2](../delivery/README.md#2-safety-first)). There is no hardware emergency stop for the Pi, and nothing in this list proposes one.

## 6. Nice to have

| # | Item | Why | Priority |
|---|---|---|---|
| 6.1 | Small mobile Wi-Fi router or phone hotspot for the campus trip | Known issues: the robot drops off the campus Wi-Fi `Students` and `turtlebot4.local` fails. A private network that the lab controls removes a variable. Not a parts-list buy: a lab decision (see [TB-21](../ROADMAP.md#tb-21-decide-the-robots-network-students-or-the-lab-router)) | Later |
| 6.2 | Cable tidy: spare hook-and-loop ties, a small bag for the controller, a charger for the controller | Charge and carry the controller; "charge the controller first" is a precondition in section 6 | Later |
| 6.3 | Second speaker of the same model | Spare, and a way to test two placements (food court and lab are different noise levels) | Later |

## Suggested first purchase

The smallest set that unblocks the first campus mapping run and the spoken messages test. Totals use only prices that were confirmed on a page on 2026-11-12; items with no confirmed price are shown separately.

| Item | SAR |
|---|---|
| 3.1 USB mini speaker (B0H1HLHW9W) | 52.64 |
| 5.1 Safety vest, 1 piece (B0DFWJWM68) | 25.19 |
| 2.4 Hook-and-loop roll (B000078CUB) | 50.82 |
| 4.1 SanDisk High Endurance 64 GB (B07P3D6Y5B) | 90.00 |
| 3.3 USB right-angle extension (B01N63UBWR) | 33.96 |
| Confirmed total | 252.61 |
| Not confirmed, budget: 1.1 tape measure about 25 to 40, 3.2 USB sound adapter about 30 to 60, 2.1 non-slip liner about 50 to 120 | about 105 to 220 |

Estimated total for the first purchase: about SAR 360 to 470 including VAT, before delivery fees. Prices are the Amazon.sa prices seen on 2026-11-12 and have not been confirmed at checkout.

## Not verified

- No listed speaker or adapter was tested on this Raspberry Pi with Ubuntu 24.04; "plug and play on Linux" is seller text.
- The robot's free USB ports, the USB power budget, the top plate dimensions and its payload limit were not measured. They decide items 2.2, 3.1 and 3.3.
- Stock and delivery times to Riyadh were read from listings and may differ at checkout.
- noon.com and desertcart.com.sa links could not be opened by the tools used here.
- Local shops (Jarir, Extra, electronics shops) were not checked and could be cheaper.
