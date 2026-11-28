"""Run: the record of one started program, and the state of the fake Wi-Fi used in demos and tests.
It starts nothing by itself."""
from .base import *  # bundle: skip


# ======================================================================= runs
class Run:
    def __init__(self, run_id, name, pid, log_path, path, started_wall, motion, proc=None):
        self.run_id, self.name, self.pid, self.log, self.path = run_id, name, pid, log_path, path
        self.started_wall, self.motion, self.proc = started_wall, bool(motion), proc
        self.offset = 0
        self.pending = ""
        self.exit_sent = False
        self.code = None
        self.needle = os.path.basename(path)

    def info(self, alive):
        return {"run_id": self.run_id, "name": self.name, "pid": self.pid, "alive": alive,
                "started_wall": self.started_wall, "motion": self.motion, "log": self.log, "code": self.code}


FAKE_HOTSPOT = "netplan-wlan0-Turtlebot4"
# (ssid, security as nmcli prints it, signal %, channel)
FAKE_SCAN = [("HomeNet", "WPA2", 70, "6"), ("Students", "WPA2", 55, "11"), ("eduroam", "WPA2 802.1X", 48, "36"),
             ("CafeFree", "--", 40, "1"), ("FailNet", "WPA2", 30, "3"), ("PhoneHotspot", "WPA2 WPA3", 62, "9")]
try:
    FAKE_WIFI_SCALE = max(0.0, float(os.environ.get("STUDIO_FAKE_WIFI_SCALE", "1")))  # tests may speed the simulation up
except ValueError:
    FAKE_WIFI_SCALE = 1.0


def fake_wifi_state():
    """The fake robot is a client of HomeNet; Students is saved but out of reach; the hotspot profile exists."""
    return {"cur": "HomeNet", "ip": "192.168.50.12", "n": 0, "join": None,
            "saved": [{"name": "HomeNet", "ssid": "HomeNet", "mode": "infrastructure", "autoconnect": True, "priority": 10,
                       "powersave": "default"},
                      {"name": "Students", "ssid": "Students", "mode": "infrastructure", "autoconnect": True, "priority": 10,
                       "powersave": "disable"},
                      {"name": FAKE_HOTSPOT, "ssid": "Turtlebot4", "mode": "ap", "autoconnect": True, "priority": 0,
                       "powersave": "default"}]}
