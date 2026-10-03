import os
import sys

path, ssid = sys.argv[1], sys.argv[2]
psk = sys.stdin.read()

BS = chr(92)


def esc(v):
    v = v.replace(BS, BS + BS).replace('\n', BS + 'n').replace('\t', BS + 't').replace('\r', BS + 'r')
    if v.startswith(' '):
        v = BS + 's' + v[1:]
    return v


content = (
    "[connection]\n"
    f"id={ssid}\n"
    "type=wifi\n"
    "interface-name=wlan0\n"
    "autoconnect=false\n"
    "autoconnect-priority=10\n"
    "\n"
    "[wifi]\n"
    "mode=infrastructure\n"
    f"ssid={ssid}\n"
    "\n"
    "[wifi-security]\n"
    "key-mgmt=wpa-psk\n"
    f"psk={esc(psk)}\n"
    "\n"
    "[ipv4]\n"
    "method=auto\n"
    "\n"
    "[ipv6]\n"
    "method=auto\n"
)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(content)
os.chmod(path, 0o600)
