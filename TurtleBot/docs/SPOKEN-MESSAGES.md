# TurtleBot 4 spoken messages: plan for the campus delivery

Written 2026-11-12 for task [TB-29](../ROADMAP.md#tb-29-campus-food-delivery-along-the-wall-supervised-demo). This is a plan only. No code was changed, nothing was installed and the robot was not touched, so **everything below is NOT VERIFIED on the robot**. Hardware to buy: [PARTS-LIST.md, section 3](PARTS-LIST.md#3-spoken-messages).

## 1. The problem

The delivery shows text on the robot's 18-character screen and plays four chimes (`start`, `arrive`, `thanks`, `alarm`) through the Create 3 on `/cmd_audio`, which can only play tones ([delivery/README.md, section 9](../delivery/README.md#9-phase-2-supervised-runs)). A vendor in a noisy food court may not look at a small screen, and a chime does not say what to do. The wish: short spoken lines in English and Arabic, for example "Your food is here".

Constraints from the project documents:

- The Pi 4 already runs Nav2. The load average was about 8.6 during a trip on 2026-11-06 (it was 18 with the camera container running). Speech must add almost nothing.
- TB-25: every new ROS participant can stall the Create 3 base for seconds. The speech part must not create any ROS node, publisher or subscriber during a run.
- Offline: the campus Wi-Fi is unreliable ("Students" drops, mDNS fails), so no cloud service at run time.
- Supervised demo, short phrases only (about 5 to 8 lines in two languages).

## 2. Options compared

CPU, memory and quality figures for Piper and espeak-ng on a Pi 4 are **estimates from general experience, not measured here**. File sizes and licences were read from the sources on 2026-11-12.

| Option | CPU and memory on a Pi 4 | Install size | Offline | Quality | Licence |
|---|---|---|---|---|---|
| A. Prerecorded clips (WAV files, played with `aplay`) | Almost none: no synthesis, one short `aplay` process per line (estimate) | About 100 to 300 KB per clip at 22.05 kHz mono (a 2 to 3 s line is about 90 to 130 KB); about 2 MB for ten clips in two languages | Yes | As good as the clip source: a human recording is best, especially for Arabic; a neural voice rendered once on a laptop is good | The clip source decides (see the licence notes under Piper and for a human recording, the speaker's consent) |
| B. espeak-ng (formant synthesiser) | Very low, a fraction of a second per line (estimate); a few MB of memory | Package plus data, a few MB to about 20 MB depending on how many languages are installed | Yes | Clearly robotic. English is understandable. Arabic is available as `ar` but is rough, because text without diacritics is pronounced by simple rules | GPL-3.0 |
| C. Piper (offline neural voices, ONNX) | Higher: loads a model of about 63 MB and synthesises on the CPU. On a Pi 4 it is usually faster than real time for the medium voices, but it would compete with Nav2 for cores (estimate, **measure it**). Memory about 200 to 400 MB while loaded (estimate) | Each voice is a single `.onnx` file of about 63 MB plus a small `.json` file; the Piper package and onnxruntime add roughly 100 to 200 MB | Yes | Natural, much better than espeak-ng. Arabic quality depends on the voice (one voice only, see below) | Piper code: MIT for the original `rhasspy/piper` repository (archived since 2025-08-26), GPL-3.0 for its active successor `OHF-Voice/piper1-gpl`. **Each voice has its own licence, and some are restrictive**: the English Lessac voice is under the Edinburgh Blizzard 2013 licence, the Arabic voice's model card only says "See URL" and its source repository declares no licence. Check before using clips outside the lab |
| D. Piper (or another neural voice) run only on a laptop to make clips, then option A on the robot | Same as A on the robot; the neural cost is paid once, offline, on a laptop | Same as A | Yes | Neural quality, with the chance to listen to every line and re-render | As Piper's voice licences |
| E. Cloud text-to-speech (any online service) | Almost none on the robot, but needs internet at run time | None | **No** | Good | Service terms. Rejected for run time: the campus Wi-Fi drops (TB-10, Known issues) and a delivery cannot wait for a web request. Could be used on a laptop to make clips if its terms allow it |
| F. Other offline engines (for example sherpa-onnx, Meta MMS text-to-speech, Coqui TTS) | Similar to Piper or heavier | 100 MB and up | Yes | Varies; MMS has an Arabic voice | Varies; MMS models are non-commercial licence in the source I recall (**not checked**). Not pursued: more setup, nothing Piper does not cover for a fixed phrase list |

### Piper voices that exist (read from the voice repository on 2026-11-12)

The voices are in the `rhasspy/piper-voices` repository. Sizes below are the `.onnx` file sizes reported by the repository.

| Language | Voice | Quality levels | `.onnx` size | Notes |
|---|---|---|---|---|
| Arabic (Jordan), `ar_JO` | `kareem` (one male speaker) | low, medium | 63.2 MB each (63,201,294 bytes) | The only Arabic Piper voice in the repository. Fine-tuned from the English Lessac voice. Training data from a public repository whose licence is not stated |
| English (US) | `lessac` | low, medium (and others) | 63.2 MB each | Trained on the Blizzard 2013 data; licence page linked from the model card |
| English (US) | `amy` | low, medium | 63.1 MB, 63.2 MB | Mycroft Mimic3 data, "See URL" |
| English (GB) | `alba` | medium | 63.2 MB | |

Model cards: [Arabic kareem medium](https://huggingface.co/rhasspy/piper-voices/blob/main/ar/ar_JO/kareem/medium/MODEL_CARD), [Lessac medium](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD). Project pages: [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) (Python package `piper-tts`, version 1.8.0 on PyPI when checked), [espeak-ng](https://github.com/espeak-ng/espeak-ng). The Piper Arabic voice is a male Jordanian-dialect voice reading text that normally needs diacritics for correct pronunciation; **how it sounds was not listened to**.

## 3. Recommendation

**Use prerecorded clips (options A and D): render each phrase once on a laptop, review the audio, and keep the WAV files on the robot. A person with Arabic should check or record the Arabic lines.**

Why:

- The phrase list is fixed and short, so run-time synthesis buys nothing.
- It keeps the Pi's CPU and memory untouched. With the load at about 8.6 and the OAK-D container already using a core, adding a neural model on the Pi would risk the Nav2 timing for no benefit.
- Quality is chosen offline by a person: wrong Arabic pronunciation is found at the desk, not in front of the vendor. A human recording of the Arabic lines is the best result, and it avoids the unclear Arabic voice licence.
- Nothing new to install on the robot except an audio player (the `alsa-utils` package, which provides `aplay`, may already be present; **not checked**).

Fallback if a line must contain a changing value (a battery level or a name): espeak-ng for that line only, with a short English template. Not needed for the current texts.

Rejected: Piper on the robot (CPU and memory cost, licence questions, nothing gained for fixed lines), cloud (needs internet), MMS and Coqui (heavier, more setup).

## 4. Proposed phrases (draft, for review)

The Arabic is a draft written for a native speaker to correct. English lines are short on purpose: the food court is noisy.

| Moment (mission event) | English | Arabic (draft) | Notes |
|---|---|---|---|
| Leaves the dock for the food court (chime `start`) | "Going to the food court." | "ذاهب إلى ساحة الطعام." | Optional; fine to leave silent |
| Arrives at the food court, shows `Food placed?` (event `show`, text starts `Food placed?`) | "I am here for the food. Please put it in the box, then press button 1." | "أنا هنا لاستلام الطعام. ضع الطعام في الصندوق ثم اضغط الزر الأول." | Spoken once on arrival and once more after 60 s if nothing was pressed |
| Food accepted (chime `thanks` after the button) | "Thank you." | "شكراً لك." | |
| Arrives at the lab, shows `Your food is here` (event `show`) | "Your food is here. Please take it, then press button 1." | "طلبك وصل. تفضل بأخذه ثم اضغط الزر الأول." | The display text already says "Your food is here" |
| Handover done (chime `thanks`) | "Thank you. Going to the dock." | "شكراً لك. سأعود إلى المحطة." | |
| Alarm (chime `alarm`, text `NEED HELP`) | "I need help." | "أحتاج إلى مساعدة." | Speak once; the person walking behind the robot is the real responder |

Button 1 is used in every line because the screen text says `Press button 1`; buttons 3 and 4 still work ([delivery/README.md, section 1](../delivery/README.md#1-what-this-is)).

Volume: the robot should not startle people. Start low and let the person in charge raise it with the speaker's own knob (parts list 3.1).

## 5. Integration point

The mission already writes every event twice: a text log and a **JSON Lines file** `delivery_<date>_<time>.jsonl` in the log folder (`--log-dir`, default `~/robot_code/logs`; [delivery_mission.py](../delivery/delivery_mission.py) docstring and `open_log`). Each line holds the run id, time, `event` and `detail`. In [delivery_core.py](../delivery/delivery_core.py) the events that matter are:

- `show`, with the display text (lines joined with ` | `). It is emitted only when the text changes, so it does not repeat every 0.5 s.
- `chime`, with the kind (`start`, `arrive`, `thanks`, `alarm`).
- `alarm`, with the reason.

**Proposed design (not built):** a small separate program, the "voice player", that:

1. Finds the newest `delivery_*.jsonl` file and follows it as it grows (plain file reading, polling every 0.2 s).
2. Maps events to clips: `show` text starting `Food placed?` and `Your food is here` to the arrival lines, `chime thanks` to the thank-you lines, `chime alarm` to the help line.
3. Plays the clip with `aplay` on the chosen sound device, one clip at a time, in English then Arabic, and never repeats a line within a few seconds.
4. Has a "silent" switch (a file `~/NO-VOICE`, like `~/STOP`) so a person can turn it off.

Why this fits the constraints:

- **No ROS.** The player is plain Python (standard library) plus `aplay`. It makes no ROS node, so it cannot stall the base (TB-25), and it can start before or after the mission.
- **No change to the mission.** The mission is untouched; the player only reads the event file. If the player crashes, the delivery continues.
- **Same event source as the chimes**, so speech and chimes stay in step. The chimes stay as they are.
- The player and the menu's mission start use the same log folder only if the menu starts the mission with the default `--log-dir`; **this was not checked**, so the player should take the folder as an option.

Who starts it is open: a line in `robot/start_stack.sh` (the stack is started once per run, [section 9](../delivery/README.md#9-phase-2-supervised-runs)), or a service. A service changes the robot's configuration and would need a row in the [MAINTENANCE.md change register](../MAINTENANCE.md) with verify and undo steps. The menu files belong to the menu work, so they are not touched by this plan.

## 6. Hardware

See [PARTS-LIST.md, section 3](PARTS-LIST.md#3-spoken-messages): a small USB-powered speaker, a USB sound adapter, and a short right-angle USB extension. Open questions that only a look at the robot can answer: which USB ports are free, whether the Pi can power the speaker next to the lidar and camera, where the speaker can sit. Ubuntu's `aplay -l` on the robot lists the sound cards; a first test can use the Pi's own 3.5 mm jack with a speaker on hand, before anything is bought.

## 7. Test plan

All steps are **NOT YET DONE**. Steps 1 to 3 need no robot.

1. **Laptop, offline.** Make the clips: write the lines (section 4), render them with Piper (English Lessac medium; Arabic Kareem medium) or record them, listen to each one. A person with Arabic marks each Arabic line as correct or not. Store the files in a folder, with a text file stating where each came from and under which licence.
2. **Laptop, player logic.** Replay a stored event file from a real delivery log (for example from `delivery/sim/` runs) through the player with `aplay` replaced by a print: check the line chosen for each event, that no event plays twice, and that the silent switch works. This is an offline test, like the tests in [section 12 of the delivery README](../delivery/README.md#12-offline-tests).
3. **Laptop, speaker.** Play the clips on the speaker and sound adapter from the parts list on a laptop to check loudness and clarity.
4. **Robot, docked, no motion.** With the stack not running, plug the adapter and speaker into a free USB port, run `aplay -l`, and play one clip. Record the load average before and during (read-only). The robot stays docked.
5. **Robot, docked, with the simulator.** Run the simulator in `delivery/sim/` (as on 2026-11-06) with the player following its event file, and record the load average with and without the player. The expected result is no visible change; the test is whether that holds. Do not add `ros2` commands during this test (TB-25).
6. **Real robot, supervised.** One run along the home test route with a person next to the robot: do the lines come at the right moments, and is the speaker audible at 1 to 2 m? Keep the controller button B ready.
7. **Food court trip.** Measure the background noise at the food court (a phone sound meter is enough) and the distance at which the line is understood. Adjust volume and the placement of the speaker. Ask the vendor whether the line was clear.
8. **Before the demo.** Tell the vendor and the student that the robot speaks and what it will say.

Pass criteria: no extra load visible in `top` at the 1-second level, no new gap in `/odom` compared with a run without the player (TB-25 recorder), the right line at each event, and a person who does not know the project understands the line at the food court.

## 8. Not verified

- Everything in this plan, on the robot.
- Piper's speed and memory on the Pi 4 next to Nav2 (estimates only).
- How the Arabic Piper voice sounds, and whether the Arabic lines are correct (drafted, not reviewed by a native speaker).
- The licences of the voice data. Do not publish the clips outside the lab before they are checked.
- Whether the menu's mission start writes its event file to the default log folder.
- Whether `aplay` is installed and which sound devices Ubuntu 24.04 on this Pi lists for the chosen adapter.
