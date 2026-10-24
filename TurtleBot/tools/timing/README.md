# Timing recorder and analyzer

Two small tools to find out **where position updates stop** on the lab TurtleBot 4 and **what else happened at that moment**.

- `record_timing.py` runs on the robot. It listens to the robot's ROS topics and, in a side thread, samples CPU load, network counters, ping to the Create 3 base, Wi-Fi state and the system journal. Everything goes into one JSON Lines file.
- `analyze_timing.py` runs anywhere (any OS, Python 3.10 or newer, standard library only). It finds the gaps in each topic and prints, for each gap, what coincided with it: motion start, high CPU, base ping loss, network events.

Background: the Create 3 base pauses `/odom` for 0.4 to 1.0 s when the wheels start (ROADMAP TB-15), and on 2026-10-04 a 2.0 s gap aborted a figure eight. The robot also dropped off Wi-Fi on 2026-10-04/05. The recorder tells these causes apart.

## Tested on the robot 2026-10-24

A first version ran for 300 s on the lab robot during a supervised motion test (33,324 records) and worked. Its own CPU cost was **44 % of one core** on the Raspberry Pi 4, with every topic deserialised in Python. That is too much for a tool that measures stalls. Since then:

- high-rate topics (`/odom`, `/imu`, `/tf`, `/scan`, `/wheel_status`, `/battery_state`) are subscribed raw: only the header stamp is read from the first bytes of the serialized (CDR) message, and nothing else is deserialised. `/cmd_vel` and `/dock_status` (low rate, and their fields are wanted) are still deserialised;
- `--light` records only `/odom`, `/cmd_vel`, `/dock_status` plus system and ping, with a 0.5 s system period;
- `/dock_status` now stores `is_docked` and `dock_visible`, so an undock is visible.

CPU cost after the change, measured on the robot on 2026-10-24 (40 s runs, robot docked, lidar spinning, Ethernet connection; the number includes the `ping` child processes):

| Mode | Topics recorded | Own CPU use |
|---|---|---|
| Full (default) | `/odom`, `/imu`, `/tf`, `/scan`, `/wheel_status`, `/battery_state`, `/dock_status`, `/cmd_vel` | **50 % of one core** (about 12 % of the Pi's four cores) |
| `--light` | `/odom`, `/dock_status`, `/cmd_vel` | **20 % of one core** (about 5 % of the Pi) |

Reading raw messages did not lower the cost of the full mode; most of it is the Python ROS client handling about 110 messages a second, plus the system sampler and `ping`. Neither run found a gap. Use `--light` when you are chasing stalls and only need `/odom`. Use the full mode when you want to see whether other base topics stall at the same time.

Worked example: the real recording of that test is stored in the repository as `../../tests/logs/2026-10-24_timing_motion.jsonl.gz`. The analyzer reads `.gz` files directly:

```
python analyze_timing.py ../../tests/logs/2026-10-24_timing_motion.jsonl.gz
```

It groups the 28 gaps into 8 events; the drive began at 176.50 s (`/cmd_vel` non-zero) and every base topic stalled about 2 s later, with header stamps stopping too and the ping RTT to the base rising from 0.5 ms to 27 ms. That file predates the `is_docked` field, so its undock at about 33.7 s is not labelled as a motion start.

## What the recorder does and does not do

- It is **read only**. It only subscribes; it never publishes (so it cannot send `/cmd_vel` or move the robot), changes no setting, needs no `sudo`, and writes only the output file (default `/tmp/timing.jsonl`).
- It records, per message, the topic, the **monotonic** receive time, the wall-clock receive time and the header stamp (if the message has one). For `/cmd_vel` it also records `linear.x` and `angular.z`, so the start of a motion is visible. Topics: `/odom`, `/imu`, `/tf`, `/scan`, `/dock_status`, `/battery_state`, `/wheel_vels`, `/wheel_status`, `/cmd_vel`; those that do not exist are skipped (and picked up later if they appear, for example `/scan` after undocking). `/cmd_vel` may be `TwistStamped` or `Twist`; either is handled. `/dock_status` also stores `docked` and `visible`.
- Every 0.2 s (`--period`): load average, CPU % total and per core, CPU % of the ROS processes (matched by command line), errors and drops for `eth0`, `usb0`, `wlan0`, link state, Wi-Fi link/level/noise, SoC temperature. Every 5 s: `vcgencmd get_throttled` if available. Every 1 s: one ping to the base `192.168.186.2` (and to any `--ping-extra` host). The NetworkManager journal and Wi-Fi/USB/link kernel messages are followed when they can be read without root; otherwise this is skipped and a `note` record says so.
- The robot's wall clock can be years wrong. All correlation uses the **monotonic** clock; the header record stores the offset between the two clocks.
- The file is flushed every second, so a run that is killed still leaves its data. Ctrl+C, SIGTERM, SIGHUP (ssh dropped) and `--duration` all end the run cleanly. At the end the recorder prints its own CPU use; expect a small number (a few percent of one core, mostly from `/tf` and `/scan` deserialisation). If it is large on your setup, use `--light` (three topics) or `--no-ros` (system only).

## Run it

Replace `<user>@<robot>` with how you normally reach the robot (see `../../HOW-TO-CONNECT.md`). The robot needs no installation: the script is sent over ssh, or copied once.

### macOS / Linux

```bash
# 10 minutes, script piped over ssh (nothing is installed on the robot)
ssh <user>@<robot> 'source /etc/turtlebot4/setup.bash && python3 - --duration 600 --out /tmp/timing.jsonl' < record_timing.py

# fetch the result and analyze it
scp <user>@<robot>:/tmp/timing.jsonl .
python3 analyze_timing.py timing.jsonl --csv gaps.csv --html timeline.html
```

### Windows PowerShell

PowerShell has no `<` redirection, so pipe the file into ssh:

```powershell
Get-Content -Raw .\record_timing.py | ssh <user>@<robot> 'source /etc/turtlebot4/setup.bash && python3 - --duration 600 --out /tmp/timing.jsonl'

scp <user>@<robot>:/tmp/timing.jsonl .
python .\analyze_timing.py .\timing.jsonl --csv gaps.csv --html timeline.html
```

Use `scp` to fetch the file. Do not use `ssh ... cat file > timing.jsonl` in Windows PowerShell 5.1: its `>` re-encodes the text as UTF-16.

### Direct Ethernet cable, IPv6 link-local (no IPv4 setup needed)

When the laptop is plugged into the robot's Ethernet port and has no address in the robot's subnet, the robot is still reachable through its IPv6 link-local address. The address starts with `fe80::` and must be followed by `%` and the laptop's interface (a name such as `eth0` or `en7` on Linux and macOS, the interface index on Windows, see `Get-NetAdapter` or `netsh interface ipv6 show interfaces`).

```bash
# macOS / Linux (interface name after %)
ssh -i ~/.ssh/<key> "<user>@fe80::<robot-link-local-address>%<interface>" 'source /etc/turtlebot4/setup.bash && python3 - --duration 600 --out /tmp/timing.jsonl' < record_timing.py
scp -i ~/.ssh/<key> "<user>@[fe80::<robot-link-local-address>%<interface>]:/tmp/timing.jsonl" .
```

```powershell
# Windows PowerShell (interface index after %)
Get-Content -Raw .\record_timing.py | ssh -i $HOME\.ssh\<key> "<user>@fe80::<robot-link-local-address>%<index>" 'source /etc/turtlebot4/setup.bash && python3 - --duration 600 --out /tmp/timing.jsonl'
scp -i $HOME\.ssh\<key> "<user>@[fe80::<robot-link-local-address>%<index>]:/tmp/timing.jsonl" .
```

To find the robot's link-local address: `ping -6 ff02::1%<interface>` and look at the replies, or read it on the robot with `ip -6 addr show eth0`.

### Copy the script instead of piping it

```bash
scp record_timing.py <user>@<robot>:/tmp/
ssh <user>@<robot>
source /etc/turtlebot4/setup.bash
python3 /tmp/record_timing.py --duration 600 --out /tmp/timing.jsonl
```

For a recording longer than your ssh session, start it detached on the robot: `nohup python3 /tmp/record_timing.py --duration 3600 --out /tmp/timing.jsonl > /tmp/timing.log 2>&1 &`. Stop it with `pkill -f record_timing.py` (a clean stop).

### Useful options

| Option | Meaning |
| --- | --- |
| `--duration S` | seconds to record, `0` = until Ctrl+C (default 600) |
| `--out FILE` | output file (default `/tmp/timing.jsonl`); an existing file is not overwritten unless `--overwrite` |
| `--period S` | system sampling period (default 0.2, minimum 0.05) |
| `--ping-extra HOST` | also ping this host, repeatable (for example the laptop or the Wi-Fi gateway) |
| `--light` | only `/odom`, `/cmd_vel`, `/dock_status` plus system and ping; system period 0.5 s unless `--period` is given |
| `--no-ping`, `--no-journal`, `--no-ros` | switch a part off |
| `--topic NAME` | record one more topic, repeatable |

## Run it beside a motion test

The recorder only listens, so it can run in a second terminal while someone else runs a supervised motion test (for example `motion_shapes.py`, started by that person with its own `--dry-run` first and `--yes` when they are satisfied).

1. Terminal 1 (recorder): start it about 15 s before the test, with a duration that covers the whole test plus 15 s.
2. Terminal 2: the person running the test does their usual steps. Nothing about the test changes.
3. After the test ends, the recorder stops by itself, or press Ctrl+C. Then fetch and analyze the file.

The motion start is taken from `/cmd_vel`, so the test program's own commands appear in the report. For a baseline, also record 10 minutes with the robot idle and off the dock, and compare the number of gaps.

## Read the report

```
python analyze_timing.py timing.jsonl [--min-gap 0.25] [--window 0.5] [--motion-window 3.0] [--group-within 0.25] [--csv gaps.csv] [--html timeline.html]
```

The input may be a `.jsonl` or a `.jsonl.gz` file.

**Topic table**: message count, rate, median and maximum inter-arrival time, and the gap threshold, which is max(3 x median, `--min-gap`). `/cmd_vel` is listed but not checked for gaps.

**`/odom` line**: how many gaps exceed 0.3 s (the motion programs hold still) and 2.0 s (they abort).

**Events**: gaps of different topics that start within `--group-within` seconds (default 0.25) of each other are one event, because they usually have one cause. An event whose topics are all from the base is titled `base stall: /odom /tf /imu ...`, and the per-topic gaps are listed below it. A single-topic gap is `gap: /imu`. CSV rows stay per gap, with an `event` column.

**Each event**: start in seconds since the recording began (robot monotonic clock), length, and:

- **stamps**: compares the header-stamp gap with the receive gap of the same two messages.
  - `publisher stopped`: the stamp gap is about as long as the receive gap, so nothing was produced (for `/odom`: the base itself paused).
  - `delivery delayed`: the stamp gap is small but the receive gap is large, so the messages were produced on time and arrived late (network, DDS, or a busy Pi).
  - `unclear`: in between. `no stamp`: the topic has no header.
- **cpu**: highest total and per-core CPU in a window of `--window` seconds around the gap, load average, the busiest ROS process, temperature.
- **network**: error and drop counters that grew, and link state changes on `eth0`, `usb0`, `wlan0`.
- **ping**: pings to the base in the window, how many were lost, worst RTT against the median.
- **event**: NetworkManager and kernel lines in the window.
- **motion**: whether a motion start came within `--motion-window` seconds (default 3.0) before the stall: `/cmd_vel` going from zero to non-zero, or `/dock_status` `is_docked` going from true to false (undock). A drive can start a second or two before the stall (2.0 s on 2026-10-24).
- **verdict**: one line per coincidence found (`coincides with motion start`, `robot commanded to move (/cmd_vel non-zero) at gap start` (its own line), `coincides with CPU > 90%`, `coincides with base ping loss`, `other topics stalled too`, and so on), or `no correlate found`.

How to use the verdicts:

- Only `/odom` stalls, `publisher stopped`, at motion start: the known Create 3 pause (TB-15). Keep the hold-still logic.
- Several topics stall together, with high CPU or `delivery delayed`: the Pi or the DDS delivery was busy; look at the top process.
- Stall together with base ping loss or `usb0` changes: the Pi-to-base link.
- Stall together with a Wi-Fi event on a run over Wi-Fi: the wireless link (TB-20).
- `no correlate found`: nothing measured explains it; the cause is probably inside the base.

`--csv` writes one row per gap. `--html` writes one self-contained page (inline SVG, no scripts, no downloads): one row per topic with red marks for gaps, green for `/cmd_vel` non-zero, CPU total, lost pings and events. Hover a mark for details.

## Limitations

- Receive times are taken in the recorder's Python callbacks. If the recorder itself is starved of CPU, a delay can look like a gap; the recorder's own CPU use is printed and stored in the footer record. Header stamps (from the sender's clock) help to tell the two apart.
- Sampling is every 0.2 s by default, so a CPU spike shorter than that can be missed. The `/proc` CPU percentages are averages over each sample.
- `/tf` has several publishers, so its header stamp (first transform) is only a rough guide; judge `/tf` by receive times.
- `/scan` does not exist while the robot is docked (the lidar is off), and `/dock_status`, `/battery_state` are slow topics; their gap threshold is adapted to their own median.
- Journal and kernel messages need the user to be allowed to read them; without that, correlation with Wi-Fi events is not possible and only ping and counters remain. In access-point mode `/proc/net/wireless` has no signal data.
- Ping measures the Pi-to-base link, not the base's internal state. A base that is busy but reachable can still pause `/odom`.
- The recorder cannot see inside the Create 3 base. A gap with `publisher stopped` and no correlate is evidence for the base, not proof.
- The raw-subscription version (stamps read from the CDR bytes) is covered by offline tests with hand-built little and big endian messages in `../../tests/offline/test_timing.py`, but has not run on the robot yet.
