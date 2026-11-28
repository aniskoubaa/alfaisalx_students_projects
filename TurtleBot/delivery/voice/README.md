# Voice player for the campus delivery (TB-29)

A small separate program that follows the delivery mission's event file (`delivery_*.jsonl` in `~/robot_code/logs`) and plays prerecorded WAV clips: English, then Arabic, for each moment (arrival at the food court, food here, thank you, help). Design and reasons: [docs/reference/spoken-messages.md](../../docs/reference/spoken-messages.md), sections 3 to 8.

It is plain Python (standard library and PyYAML). It creates **no ROS node** and imports nothing from ROS, and it never changes the mission, so it cannot stall the base (TB-25). If it crashes or is stopped, the delivery carries on.

## Files

| File | Purpose |
|---|---|
| `voice_player.py` | The player. Follows the newest event file, maps events to phrases, plays clips one at a time |
| `phrases.example.yaml` | Phrase list (English and draft Arabic text, clip file names) and the event rules. Copy it to `~/robot_code/voice/phrases.yaml` |
| `make_clips.py` | Laptop tool: renders the clips with a text-to-speech command, or writes placeholder WAV files. Downloads nothing |
| `voice-player.service` | systemd user unit (not installed anywhere) |
| `../../tests/offline/test_delivery_voice.py` | Offline tests (no robot, no sound card) |

## Make the clips (laptop)

```
cd TurtleBot/delivery/voice
python make_clips.py --placeholder                  # short beeps: tests the whole chain before real voices exist
python make_clips.py --tts-cmd "piper --model en_US-lessac-medium.onnx --output_file {out}" --lang en --force
```

`--tts-cmd` is a template: `{out}` is the output file, `{lang}` the language, and `{text}` (if present) the text; without `{text}` the text goes to the command's standard input (Piper style). Existing clips are kept unless `--force` is given. Use `--dry-run` to list what would be written. Listen to every clip. Clips go in `clips/en/` and `clips/ar/` next to the phrase file.

## Try it without a speaker (dry run against a stored event file)

```
python voice_player.py --config phrases.example.yaml --log-dir <folder with a delivery_*.jsonl> --from-start --dry-run --once
```

It prints which clip would play for each event. Without `--from-start` the player starts at the end of the newest file (history is not replayed) and plays only what is written from then on; a new file for the next trip is read from its first line. Add `--dry-run` to any run to play nothing.

## Run it on the robot (after the clips are copied to `~/robot_code/voice/clips/`)

```
python3 ~/robot_code/delivery/voice/voice_player.py --config ~/robot_code/voice/phrases.yaml --dry-run     # first, no sound
python3 ~/robot_code/delivery/voice/voice_player.py --config ~/robot_code/voice/phrases.yaml               # then for real
```

Options: `--device plughw:0,0` (the sound device for `aplay -D`, also settable as `device:` in the phrase file), `--player-cmd "<command with {file} and {device}>"`, `--log-dir`, `--repeat-gap` (default 8 s: the same phrase is not repeated within this time), `--silent`. Ctrl+C or SIGTERM ends it cleanly.

Which player it uses (the first one installed): `aplay -q -D <device> <file>`, then `ffplay -nodisp -autoexit -loglevel quiet <file>`. **ffplay has no device option**, so `--device` is ignored with ffplay and the system default output is used. `--player-cmd` overrides the choice. On the robot checked on 2026-11-14 `aplay` was not installed and `ffplay` was, so ffplay works without any install. Optional, run by a person on the robot (it needs sudo): `sudo apt install alsa-utils`, which provides `aplay` and `aplay -l` to choose a sound device.

Silent switch: create the file `~/robot_code/voice/SILENT` to make the player log only (`touch` to mute, `rm` to unmute, no restart needed), or start it with `--silent`. A missing clip, a missing player or a player error is logged as a warning and never stops the player.

## Install the unit later (not done)

The unit changes the robot's configuration, so it needs a row in the MAINTENANCE.md change register with verify and undo steps first. Then, as the robot user:

```
mkdir -p ~/.config/systemd/user && cp ~/robot_code/delivery/voice/voice-player.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now voice-player.service
```

Undo: `systemctl --user disable --now voice-player.service` and delete the copied file. Whether it starts at boot without a login depends on `loginctl enable-linger` (the menu unit has the same question).

## NOT verified

- Nothing was run on the robot; the tests use a fake clock and a fake player.
- No speaker is connected yet (the Pi's 3.5 mm jack is the only sound card seen), so loudness and clarity at the food court are unknown.
- Sound device names and the exact `aplay` or `ffplay` behaviour with the real card (ffplay opens a short-lived process per clip; its start time and CPU cost were not measured).
- The Arabic lines are drafts: a native speaker must review or record them before use.
- Voice licences (Piper voices and the voice data have their own terms): do not publish clips outside the lab before they are checked.
- Two plan items have no event yet: the repeat of the food request after 60 s (the mission writes no event for it) and a line for a home trip that docks without a handover. See the notes at the end of `phrases.example.yaml`.
