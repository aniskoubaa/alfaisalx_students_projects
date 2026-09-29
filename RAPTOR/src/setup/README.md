# setup/ — provisioning the Jetson

One-time scripts that configure the board's operating system. They **run on the
Jetson**, from the synced copy of this repo (`~/raptor/src/setup/`). Each one
explains itself in the comment block at the top — read it before running.

The files they install live in [`../system/`](../system/README.md), at the same path
they end up at on the board, so the configuration is version-controlled and a
reflashed board can be restored from git.

## Setting up a freshly flashed board, in order

Assumes JetPack 7.2 (Ubuntu 24.04) on the Orin NX, the Ethernet cable to the laptop
(board `100.100.100.1`, laptop `100.100.100.2`), and SSH access for `alfaisal-x-nx`.
Several scripts use `sudo`; the board was set up with passwordless sudo for that
user.

| Step | On | Command | Why |
|---|---|---|---|
| 1 | laptop | `src/tools/jetson_internet.sh` — leave it running | The board has no Wi-Fi; steps 3–6 download packages. |
| 2 | laptop | `src/deploy/sync_to_jetson.sh` | Puts this code at `~/raptor/src` on the board. |
| 3 | Jetson | `sudo bash install_clock_keeper.sh` | No clock battery → boots into 1970 without it. Do this first so everything after is timestamped correctly. |
| 4 | Jetson | Create `~/raptor-venv` — see [docs/09](../../docs/09-jetson-environment.md) | Python environment; must use `--system-site-packages`. |
| 5 | Jetson | `bash setup_ros2.sh` | ROS 2 Jazzy. ~10–15 min. |
| 6 | Jetson | `sudo bash set_headless_display.sh` | Usable resolution with no monitor. Run while nobody is logged in to the desktop. |
| 7 | Jetson | `sudo bash setup_vnc.sh` | Remote view of the console. Prints the password. |
| 8 | Jetson | `sudo bash setup_rdp.sh` | Encrypted remote desktop. Prints the password. |
| 9 | Jetson | benchmarks + `src/deploy/deploy_models.py` | Builds the TensorRT engines and stages the models — see [benchmarks/README](../../benchmarks/README.md). |
| 10 | Jetson | `cp ~/raptor/src/demo/RAPTOR-Live-Demo.desktop ~/Desktop/ && gio set ~/Desktop/RAPTOR-Live-Demo.desktop metadata::trusted true` | The clickable demo icon. |

Every script is safe to re-run: each checks what is already in place.

## Remote access

Two ways in, deliberately — they do different jobs.

| | VNC | RDP |
|---|---|---|
| Set up by | `setup_vnc.sh` | `setup_rdp.sh` |
| Address | `100.100.100.1`, port **5900** | `100.100.100.1`, port **3389** |
| What you see | the **physical console** — login screen, then the desktop | a **new** session of its own |
| Resolution | 1024×768 (fixed by the headless display config) | negotiated by your client |
| Encrypted | **no** | yes (TLS) |
| Credentials | VNC password, **8 characters max** | RDP username + password — **not** your Linux login |
| Change password | `sudo x11vnc -storepasswd <new> /etc/x11vnc.pass` | `sudo grdctl --system rdp set-credentials <user> <pass>` |

Use VNC when you need to see what is actually on the board's screen; RDP for
comfortable work. Both are fine on the direct cable to the laptop. If the board ever
joins a shared network, keep RDP and put VNC behind an SSH tunnel.

To test either one from the laptop before opening a client:
`python src/tools/check_vnc.py --password <pw>` and `python src/tools/check_rdp.py`.

### Problems already hit, and what they looked like

- **VNC: `password check failed`** with a 12-character password. VNC only uses the
  first 8 characters. `setup_vnc.sh` now refuses anything longer.
- **VNC: service "active" but nothing listening on 5900.** `x11vnc -auth guess` cannot
  find the X authority under systemd. Fixed by `raptor-x11vnc-start`, which reads it
  from the running Xorg process.
- **VNC: a 640×480 desktop.** No monitor attached. Fixed by `set_headless_display.sh`.
- **RDP: every connection reset; log says `Credentials are not set, denying client`.**
  System RDP needs its own credentials set with `grdctl`. `setup_rdp.sh` now does it.
