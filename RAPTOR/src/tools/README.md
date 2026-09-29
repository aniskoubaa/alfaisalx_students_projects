# tools/ — helpers that run on the laptop

Run these on the Windows laptop, in **Git Bash** for the `.sh` files. They assume
the board at `100.100.100.1` and the SSH key `~/.ssh/claude_nx`; override with the
`JETSON` and `KEY` environment variables if yours differ.

| File | What it does |
|---|---|
| `jetson_internet.sh` | Gives the Jetson internet through the laptop's Wi-Fi. Leave the window open. |
| `laptop_proxy.py` | The small HTTP proxy that `jetson_internet.sh` starts for you. |
| `check_vnc.py` | Logs in to the board's VNC the way a real client does. `pip install pycryptodome` once. |
| `check_rdp.py` | Confirms the board's RDP server is genuinely answering. No dependencies. |

## Giving the Jetson internet

The board has **no Wi-Fi hardware**. Its only network is the Ethernet cable to the
laptop, with no route beyond it.

```bash
./jetson_internet.sh
```

It starts the proxy on the laptop, opens an SSH tunnel so the Jetson's own
`127.0.0.1:3128` leads to that proxy, and checks the board can reach the ROS
package server. apt on the board uses it automatically (via
`/etc/apt/apt.conf.d/99proxy`); for pip or curl, add
`https_proxy=http://127.0.0.1:3128` in front of the command.

**Internet access lasts only while this window is open.** Close it and the board is
offline again — that is by design, but it catches people out mid-install. A
permanent route needs NAT set up on the laptop once; see
[docs/11](../../docs/11-jetson-platform-setup.md#networking-how-the-board-gets-online).

Two things about this network that explain odd failures:

- **It intercepts TLS to some hosts.** `https://packages.ros.org` fails with
  `SEC_E_WRONG_PRINCIPAL` while plain HTTP works. That is why the ROS repository is
  configured over `http://` (apt verifies packages by GPG signature, so this is safe).
- **Do not trust `ping` to tell you the board is up.** The board's address,
  `100.100.100.1`, lies inside `100.64.0.0/10` — the carrier-grade NAT range this
  ISP puts the laptop's Wi-Fi in. With the Ethernet cable out, a ping can be answered
  by an unrelated host on the internet. Check with SSH instead; or look at the TTL —
  **64** is the board, around **54** is an impostor.

## Checking remote access before opening a client

```bash
python check_vnc.py --password <vnc-password>
python check_rdp.py
```

Each reports exactly what failed — unreachable, wrong password, missing credentials,
640×480 desktop — with the fix. Passwords are never stored or printed.
