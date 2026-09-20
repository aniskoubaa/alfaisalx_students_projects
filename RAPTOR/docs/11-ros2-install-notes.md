# 11 — ROS 2 on this board: Jazzy, not Humble

**Status: installed and verified, 2026-09-20.** ROS 2 **Jazzy** `ros-base`,
195 packages, plus `vision_msgs` and colcon.

Verified functionally, not just by package list:

```
$ ros2 topic pub /raptor_selftest std_msgs/msg/String '{data: raptor-ok}'
$ ros2 topic echo --once /raptor_selftest
data: raptor-ok                      # round-tripped over DDS
$ ros2 interface show vision_msgs/msg/Detection2DArray
# A list of 2D detections, for a multi-object 2D detector.
```

`vision_msgs/Detection2DArray` is the `detector_node` output type specified in
[04](./04-ros2-architecture.md), and `rosbag2` is present — the latter matters
more than it looks, because the whole benchmark methodology depends on recording
a flight once and replaying it against every future model.

## The version decision

[04-ros2-architecture.md](./04-ros2-architecture.md) and
[07-roadmap.md](./07-roadmap.md) both specify **ROS 2 Humble**, on the stated
assumption that "JetPack 6.x ships Ubuntu 22.04, which pairs with ROS 2 Humble".

That assumption does not hold for this board:

```
$ lsb_release -d
Ubuntu 24.04.4 LTS
$ head -1 /etc/nv_tegra_release
# R39 (release), REVISION: 2.0 ...        -> JetPack 7.2
```

ROS 2 distributions are tied to an Ubuntu LTS. Humble targets 22.04; **Jazzy**
targets 24.04. There are no Humble binaries for 24.04, so using it would mean
building the entire tree from source and maintaining it against ABI drift — weeks
of work, indefinitely, for no benefit.

**Recommendation: install ROS 2 Jazzy**, and update docs 04 and 07 to match.

### What this costs us

The one real consequence is **NVIDIA Isaac ROS**, which targets Humble. Doc 02
lists `isaac_ros_yolov8` / NITROS as Phase D, for zero-copy GPU memory between
nodes. On a Jazzy host that becomes a **container** decision rather than a native
install — which is a reasonable place for it anyway, and doc 09 already
anticipates adopting `jetson-containers` by Phase 4.

Do not downgrade the whole board to reach Isaac ROS. Run it in a container if and
when the contention measurements (E7) show it is needed.

### The alternative, for completeness

Running Humble in a container on this host is possible and keeps Isaac ROS
available. It costs the usual container overheads — device passthrough for
`/dev/video0` and the serial gimbal link, and care with DDS discovery across the
container boundary. Worth revisiting only if Isaac ROS becomes a hard requirement.

## How it was installed

Follow the **official Jazzy Ubuntu install guide** if you ever need to repeat
this from scratch — the apt repository key and its packaging have changed twice
in recent years, and a stale copy here would be worse than no copy:

<https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html>

**One deviation worth knowing about.** The repository is configured over
`http://`, not `https://`:

```
deb [arch=arm64 signed-by=...] http://packages.ros.org/ros2/ubuntu noble main
```

This network **intercepts TLS** to `packages.ros.org` — `curl` reports
`SEC_E_WRONG_PRINCIPAL` (the certificate is for the wrong principal) while plain
HTTP returns 200 normally. GitHub's HTTPS is unaffected, so it is host-specific
meddling rather than a broken link.

Using HTTP here is **not** a weakening of security. Apt's integrity model is the
GPG signature on the repository metadata, which is verified exactly as normal;
TLS would only add transport privacy about *which* packages are being fetched.
This is why Debian and Ubuntu archives served plain HTTP for years. If the TLS
interception is ever removed, switch the line back to `https://`.

Two project-specific choices:

- Install **`ros-jazzy-ros-base`**, not `desktop`. The flight computer is
  headless; rviz belongs on the ground station. A desktop install pulls in GUI
  dependencies that will never be used in flight.
- Also install `ros-dev-tools` (colcon, rosdep) — the node graph in doc 04 needs
  a workspace to build `raptor_msgs`.

Verify with the standard smoke test in two shells:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run demo_nodes_cpp talker
# and
ros2 run demo_nodes_py listener
```

### One trap specific to this board

Do **not** blindly add `source /opt/ros/jazzy/setup.bash` to `~/.bashrc` next to
the `~/raptor-venv` activation from [09](./09-jetson-environment.md). ROS ships its
own Python packages and prepends them to `PYTHONPATH`; combined with the venv's
`--system-site-packages`, that is a third way for the NumPy 1.x/2.x conflict
already documented in the
[benchmark README](../jetson_orin_nano_benchmarks/README.md) to reappear. Source
one or the other deliberately, per shell, until the interaction has been tested.

## Networking: how the board gets online

The Jetson has **no Wi-Fi hardware** — `ip -br link` shows only `enP8p1s0`
(Ethernet), `can0`, `docker0` and unused USB gadget interfaces. It reaches the
world only through the point-to-point Ethernet link to the laptop:

```
laptop  100.100.100.2  <---- Ethernet ---->  100.100.100.1  Jetson
```

Getting packages onto it took unpicking **four independent faults**, which is why
it resisted for so long. Recorded here so the next person does not repeat it:

| # | Fault | Evidence |
|---|-------|----------|
| 1 | No Wi-Fi hardware | only Ethernet in `ip -br link` |
| 2 | Default route pointed at **itself** (`100.100.100.1`) | a no-op; nothing could route |
| 3 | Host firewall dropped inbound connections to a laptop-side proxy | proxy `LISTENING` on `0.0.0.0:3128`, Jetson `curl` timed out |
| 4 | Network **intercepts TLS** to `packages.ros.org` | `SEC_E_WRONG_PRINCIPAL`; plain HTTP returns 200; GitHub HTTPS fine |

### The arrangement that works

A small HTTP/CONNECT proxy runs on the laptop, and an **SSH reverse port-forward**
carries it to the Jetson:

```bash
# on the laptop, alongside the proxy on 127.0.0.1:3128
ssh -i ~/.ssh/claude_nx -N -R 3128:127.0.0.1:3128 alfaisal-x-nx@100.100.100.1
```

The Jetson then reaches the proxy at **its own loopback address**, so fault 3
disappears entirely — the connection is outbound from the laptop and the firewall
never sees an inbound request. apt is pointed at it:

```
# /etc/apt/apt.conf.d/99proxy
Acquire::http::Proxy "http://127.0.0.1:3128";
Acquire::https::Proxy "http://127.0.0.1:3128";
```

Verify with `curl -x http://127.0.0.1:3128 -o /dev/null -w '%{http_code}'
http://packages.ros.org/ros2/ubuntu/dists/noble/Release` — expect `200`.

### This is temporary, and that is the problem

**The tunnel lives inside an interactive session. When it ends, the board is
offline again.** For a permanent route, configure NAT on the laptop once, in an
elevated PowerShell:

```powershell
Set-NetIPInterface -InterfaceAlias "Wi-Fi" -Forwarding Enabled
Set-NetIPInterface -InterfaceAlias "Ethernet 4" -Forwarding Enabled
New-NetNat -Name JetsonNat -InternalIPInterfaceAddressPrefix 100.100.100.0/24
```

then on the Jetson:

```bash
sudo ip route replace default via 100.100.100.2 dev enP8p1s0
sudo resolvectl dns enP8p1s0 1.1.1.1
```

Avoid Internet Connection Sharing — it renumbers the link to `192.168.137.x` and
the Jetson's static address would stop responding.

### A trap in the addressing itself

`100.100.100.0/24` sits **inside** `100.64.0.0/10`, the carrier-grade NAT range,
and this ISP puts the laptop's Wi-Fi in that same range. So when the Ethernet
cable is out, traffic to `100.100.100.1` routes to the *internet* and an unrelated
ISP device answers — a `ping` appears to succeed against a board that is not even
plugged in. **Trust an SSH check, not a ping** (the difference is visible in the
TTL: 64 for the directly-attached board, ~54 for the impostor).

Renumbering the point-to-point link to something private such as
`192.168.100.0/24` would remove this hazard permanently, and is worth doing.

## The clock

**Fixed, 2026-09-20.** The board used to come up at **1970-01-01** on every boot:
the RTC was not holding time, and NTP could not sync because there was no route to
the internet. Benchmark rows recorded before the fix carry 1970 timestamps.

[04](./04-ros2-architecture.md) is explicit that a wrong clock silently corrupts
timestamp correlation and therefore geolocation. A system that timestamps evidence
cannot have a clock that resets, so this was fixed in three layers:

1. System time set from the laptop.
2. Written into the RTC with `hwclock -w`, which now reads back correctly.
3. A **`raptor-clock-keeper`** systemd service and timer, enabled at boot, which
   restores a monotonic time floor on startup and persists it every ten minutes:

```bash
$ systemctl is-enabled raptor-clock-keeper.service raptor-clock-keeper-save.timer
enabled
enabled
$ cat /var/lib/raptor-clock-keeper/timestamp
2026-09-20 14:04:18
```

The service only ever moves the clock **forward** to the last known good time — it
does not pretend to be accurate. Real time still comes from NTP when networked, or
from the flight controller's GPS time, either of which will step it on. What it
guarantees is that a 1970 timestamp can no longer reach a rosbag.

A proper RTC coin cell on the carrier board, or a boot-time sync from GPS, remains
the right long-term answer and belongs on the Phase 0 checklist.
