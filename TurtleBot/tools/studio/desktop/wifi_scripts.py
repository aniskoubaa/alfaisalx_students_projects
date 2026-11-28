"""Script texts that run on the robot to save, join, fetch and remove a Wi-Fi network.
They are sent as text; nothing here runs on the laptop.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip


PROTECTED_CONNECTIONS = ('netplan-wlan0-Turtlebot4', 'netplan-eth0', 'netplan-usb0')
TEMPLATE_NAME_RE = re.compile(r'^[A-Za-z0-9_\-]{1,80}\.(py|sh)$')

# Runs as root on the robot (via sudo python3 -c). Port of TurtleBot/setup/write_keyfile.py; the password arrives on
# stdin only. O_EXCL: never overwrites an existing profile.
KEYFILE_WRITER = r'''import os
import sys

path, ssid = sys.argv[1], sys.argv[2]
psk = sys.stdin.buffer.read().decode('utf-8')
BS = chr(92)


def esc(v):
    v = v.replace(BS, BS + BS).replace(chr(10), BS + 'n').replace(chr(9), BS + 't').replace(chr(13), BS + 'r')
    if v.startswith(' '):
        v = BS + 's' + v[1:]
    if v.endswith(' '):
        v = v[:-1] + BS + 's'
    return v


content = (
    "[connection]\n"
    "id=" + esc(ssid) + "\n"
    "type=wifi\n"
    "interface-name=wlan0\n"
    "autoconnect=true\n"
    "autoconnect-priority=10\n"
    "\n"
    "[wifi]\n"
    "mode=infrastructure\n"
    "ssid=" + esc(ssid) + "\n"
    "powersave=2\n"
    "\n"
    "[wifi-security]\n"
    "key-mgmt=wpa-psk\n"
    "psk=" + esc(psk) + "\n"
    "\n"
    "[ipv4]\n"
    "method=auto\n"
    "\n"
    "[ipv6]\n"
    "method=auto\n"
)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8', newline=chr(10)) as f:
    f.write(content)
os.chmod(path, 0o600)
'''

# Runs as the normal robot user: asks the Studio bridge (abstract unix socket, same machine) for the Wi-Fi password that
# Studio sent it a moment ago and writes it to stdout. argv[1] = nonce. The bridge only answers its own user (SO_PEERCRED);
# this side checks the same, so another local user cannot pose as the bridge and feed in a password.
WIFI_FETCH = r'''import os
import socket
import struct
import sys

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect('\0turtlebot-studio-wifi-' + sys.argv[1])
if struct.unpack('3I', s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3I')))[1] != os.getuid():
    sys.exit(3)
data = b''
while True:
    c = s.recv(256)
    if not c:
        break
    data += c
sys.stdout.buffer.write(data)
'''

# Runs as root, detached (setsid), started by the Wi-Fi add script. $1 = SSID (= connection id), $2 = nmcli wait seconds,
# $3 = status file (JSON, no secrets). Never touches eth0. On failure the profile it was asked to bring up is deleted
# (so the user can retry with the right password) and the network that was active before is brought back.
WIFI_JOIN_SCRIPT = r'''ssid=$1
wait=${2:-45}
status=${3:-/run/turtlebot-studio-wifi.json}
jesc() { printf '%s' "$1" | LC_ALL=C sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/\\t/g' | LC_ALL=C tr -d '\000-\037'; }
js() { printf '"%s"' "$(jesc "$1")"; }
put() {
    tmp="$status.tmp.$$"
    printf '{%s}\n' "$1" > "$tmp" && chmod 644 "$tmp" && mv -f "$tmp" "$status"
}
now() { date +%s; }
prev=$(nmcli -g GENERAL.CONNECTION device show wlan0 2>/dev/null | head -n 1)
if [ "$prev" = "--" ]; then prev=""; fi
put "\"state\":\"joining\",\"ssid\":$(js "$ssid"),\"prev\":$(js "$prev"),\"t\":$(now)"
reason="could not join (wrong password or out of range)"
if nmcli --wait "$wait" connection up id "$ssid" >/dev/null 2>&1; then
    addr=""
    n=0
    while [ "$n" -lt 20 ]; do
        addr=$(ip -4 -o addr show dev wlan0 2>/dev/null | awk '{print $4}' | head -n 1 | cut -d/ -f1)
        if [ -n "$addr" ]; then break; fi
        sleep 1
        n=$((n + 1))
    done
    if [ -n "$addr" ]; then
        put "\"state\":\"joined\",\"ssid\":$(js "$ssid"),\"ip\":$(js "$addr"),\"prev\":$(js "$prev"),\"t\":$(now)"
        exit 0
    fi
    reason="joined but got no IP address"
fi
nmcli connection down id "$ssid" >/dev/null 2>&1
removed=false
if [ "${ssid#netplan-}" = "$ssid" ] && nmcli connection delete id "$ssid" >/dev/null 2>&1; then removed=true; fi
fb=false
if [ -n "$prev" ] && [ "$prev" != "$ssid" ]; then
    if nmcli --wait 30 connection up id "$prev" >/dev/null 2>&1; then fb=true; fi
fi
put "\"state\":\"failed\",\"ssid\":$(js "$ssid"),\"reason\":$(js "$reason"),\"fallback\":$(js "$prev"),\"fallback_ok\":$fb,\"removed\":$removed,\"t\":$(now)"
exit 1
'''

# Robot-side script (bash). Arguments: $1 = base64(ssid UTF-8), $2 = safe file name, $3 = 1|0 connect now,
# $4 = nonce (optional), $5 = join timeout in seconds (optional, default 45).
# With a nonce the Wi-Fi password comes from Studio's bridge (memory to memory on this robot, see WIFI_FETCH) and the
# only thing typed here is the robot (sudo) password. Without a nonce the Wi-Fi password is read with read -rs. Either way
# it reaches the keyfile writer through a pipe from a shell builtin (never argv, environment or a file).
WIFI_ADD_SCRIPT = r'''#!/bin/bash
# TurtleBot Studio: save a Wi-Fi network on this robot (run in a terminal on the robot).
ssid=$(printf '%s' "$1" | base64 -d) || { echo "bad arguments"; exit 2; }
fname=$2
connect_now=$3
nonce=$4
join_wait=${5:-45}
file="/etc/NetworkManager/system-connections/$fname.nmconnection"
status_file=/run/turtlebot-studio-wifi.json
WRITER=$(cat <<'STUDIO_PY_EOF'
@@WRITER@@
STUDIO_PY_EOF
)
FETCH=$(cat <<'STUDIO_FETCH_EOF'
@@FETCH@@
STUDIO_FETCH_EOF
)
JOIN=$(cat <<'STUDIO_JOIN_EOF'
@@JOIN@@
STUDIO_JOIN_EOF
)
wait_enter() { echo; echo "Press Enter to close."; read -r _ignored || true; }
echo "== TurtleBot Studio: add a Wi-Fi network to this robot =="
echo "Network name (SSID): $ssid"
echo "This will, as the administrator (sudo):"
echo "  1. write the saved network to $file (readable by root only)"
echo "  2. set autoconnect on, priority 10, Wi-Fi power save off"
echo "  3. reload NetworkManager's connection files"
if [ "$connect_now" = "1" ]; then
    echo "  4. switch the robot to it and test it (if that fails the profile is removed again and the"
    echo "     robot goes back to the network it is on now)"
fi
echo "Nothing else is changed. The cable connection is never touched."
echo
if nmcli -g NAME connection show 2>/dev/null | grep -qxF -- "$ssid"; then
    echo "A saved network called this already exists on the robot. Nothing was changed."
    echo "To replace it, remove it first (Studio, Wi-Fi tab, Remove)."
    wait_enter; exit 1
fi
if [ -n "$nonce" ]; then
    echo "The Wi-Fi password was typed in Studio. Now sudo asks for the ROBOT password (the ubuntu user's), hidden."
    sudo -v || { echo "sudo failed. Nothing was changed."; wait_enter; exit 1; }
    pw=$(python3 -c "$FETCH" "$nonce") || { echo "Could not get the Wi-Fi password from Studio (it is kept for 3 minutes only,"; echo "and Studio must stay connected). Nothing was changed."; unset pw; wait_enter; exit 1; }
else
    printf 'Wi-Fi password for %s (typing is hidden): ' "$ssid"
    IFS= read -rs pw
    echo
fi
n=$(printf '%s' "$pw" | LC_ALL=C wc -c | tr -d ' ')
if [ "$n" -eq 64 ] && printf '%s' "$pw" | grep -qE '^[0-9A-Fa-f]{64}$'; then :
elif [ "$n" -lt 8 ] || [ "$n" -gt 63 ]; then
    echo "A WPA password has 8 to 63 characters. Nothing was changed."
    unset pw; wait_enter; exit 1
fi
if [ -z "$nonce" ]; then
    echo "Now sudo asks for the ROBOT password (the ubuntu user's), also hidden."
    sudo -v || { echo "sudo failed. Nothing was changed."; unset pw; wait_enter; exit 1; }
fi
if ! printf '%s' "$pw" | sudo python3 -c "$WRITER" "$file" "$ssid"; then
    echo "Writing the network failed. Nothing was changed (an existing file is never overwritten)."
    unset pw; wait_enter; exit 1
fi
unset pw
sudo nmcli connection reload || echo "reload failed"
echo
echo "Saved. NetworkManager reports (autoconnect, power save):"
nmcli -g connection.autoconnect,802-11-wireless.powersave connection show id "$ssid"
echo
echo "To undo:   sudo nmcli connection delete id $(printf '%q' "$ssid")"
if [ "$connect_now" = "1" ]; then
    echo
    sudo rm -f -- "$status_file"
    sudo setsid -f bash -c "$JOIN" studio-join "$ssid" "$join_wait" "$status_file" </dev/null >/dev/null 2>&1
    echo "The robot is switching to '$ssid' now (up to $join_wait s). This connection may drop: that is expected"
    echo "if you are on the robot's own hotspot. If the join fails the profile is removed and the robot returns"
    echo "to its previous network within about 1.5 minutes. Studio shows the result."
fi
wait_enter
'''

WIFI_REMOVE_SCRIPT = r'''#!/bin/bash
# TurtleBot Studio: remove a saved Wi-Fi network from this robot. $1 = base64(connection name).
name=$(printf '%s' "$1" | base64 -d) || { echo "bad arguments"; exit 2; }
wait_enter() { echo; echo "Press Enter to close."; read -r _ignored || true; }
case "$name" in
    netplan-wlan0-Turtlebot4|netplan-eth0|netplan-usb0)
        echo "'$name' is the robot's own hotspot / cable link. Not removed."; wait_enter; exit 1;;
esac
t=$(nmcli -g connection.type connection show id "$name" 2>/dev/null)
if [ "$t" != "802-11-wireless" ]; then
    echo "'$name' is not a saved Wi-Fi network on this robot. Nothing was changed."; wait_enter; exit 1
fi
echo "== TurtleBot Studio: remove the saved Wi-Fi network '$name' from this robot =="
if nmcli -g GENERAL.STATE connection show id "$name" 2>/dev/null | grep -q activated; then
    echo "WARNING: this network is in use now. Removing it can drop your connection."
fi
echo "Command: sudo nmcli connection delete id $(printf '%q' "$name")"
sudo nmcli connection delete id "$name"
echo "exit code: $?"
wait_enter
'''
