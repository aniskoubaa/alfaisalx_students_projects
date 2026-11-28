"""Bridge commands for Wi-Fi: information, the password hand-over, the join status, and the fake
Wi-Fi and fake battery used by demos and tests."""
from .base import *  # bundle: skip
from .path_describe import *  # bundle: skip
from .wifi_join import *  # bundle: skip
from .run_state import *  # bundle: skip


class WifiMixin:
    def h_wifi_info(self, c):
        if self.fake:
            return self.fake_wifi_info()
        return collect_wifi()

    def h_wifi_secret_put(self, c):
        """Studio hands over a Wi-Fi password once; the on-robot script fetches it from here (abstract unix socket)."""
        if not self.fake and not sys.platform.startswith("linux"):
            raise BridgeError("the Wi-Fi password handoff needs the Linux robot (abstract unix sockets)")
        try:
            ttl = self.secrets.put(c.get("nonce"), c.get("psk"), c.get("ttl", 180), serve=not self.fake)
        except ValueError as e:
            raise BridgeError(str(e))
        except OSError as e:
            raise BridgeError("cannot open the local socket (%s)" % type(e).__name__)
        except Exception as e:  # never let an exception text travel: it could quote the password
            raise BridgeError("internal error (%s)" % type(e).__name__)
        return {"state": "waiting", "ttl": ttl}

    def h_wifi_secret_drop(self, c):
        self.secrets.drop(c.get("nonce"))
        return {}

    def h_wifi_join_status(self, c):
        nonce = c.get("nonce")
        if nonce is not None and not (isinstance(nonce, str) and NONCE_RE.fullmatch(nonce)):
            raise BridgeError("bad nonce")
        with self.fw_lock:
            join = dict(self.fw["join"]) if self.fake and self.fw["join"] else None
        if not self.fake:
            join = read_join_status()
        return {"secret": self.secrets.state(nonce) if nonce else "none", "join": join}

    # ---- fake Wi-Fi (demo and tests): the robot sits on HomeNet; wifi_fake_add simulates fetch, save and join
    def fake_net(self):
        with self.fw_lock:
            ap = self.fw["cur"] == FAKE_HOTSPOT
            ps = next((x["powersave"] for x in self.fw["saved"] if x["name"] == self.fw["cur"]), "default")
            return {"wifi_mode": "ap" if ap else "client", "ssid": self.fw["cur"], "signal_dbm": None if ap else -55.0,
                    "link_quality": None if ap else 70,
                    "addresses": {"eth0": "192.168.185.3", "wlan0": self.fw["ip"], "usb0": "192.168.186.3"},
                    "wlan0_ip": self.fw["ip"], "powersave": ps, "powersave_students": ps}

    def fake_wifi_info(self):
        with self.fw_lock:
            cur, ip = self.fw["cur"], self.fw["ip"]
            saved = [dict(x, active=(x["name"] == cur)) for x in self.fw["saved"]]
            ap = cur == FAKE_HOTSPOT
            ps = next((x["powersave"] for x in saved if x["name"] == cur), "default")
            wlan = {"state": "connected", "connection": cur, "mode": "ap" if ap else "infrastructure", "ssid": cur, "ip": ip,
                    "signal_dbm": None if ap else -55.0, "powersave": ps}
        res = {"fake": True, "wlan0": wlan, "saved": saved, "scan": []}
        if ap:
            res["scan_note"] = "the robot cannot scan while it runs its hotspot"
        else:
            res["scan"] = [{"ssid": n, "signal": sig, "security": sec, "chan": ch} for n, sec, sig, ch in
                           sorted(FAKE_SCAN, key=lambda x: -x[2])]
        return res

    def h_fake_battery(self, c):
        """Fake robot only (tests): fix the battery percent, or null to go back to the slowly draining value."""
        if not self.fake:
            raise BridgeError("only available in fake mode")
        v = c.get("percent")
        if v is None:
            self.ros.battery_override = None
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
            raise BridgeError("percent must be 0 to 100 or null")
        else:
            self.ros.battery_override = float(v)
        return {"percent": self.ros.battery_override}

    def h_wifi_fake_add(self, c):
        if not self.fake:
            raise BridgeError("only available in fake mode")
        nonce, ssid = c.get("nonce"), c.get("ssid")
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise BridgeError("bad nonce")
        if not isinstance(ssid, str) or not ssid or len(ssid.encode("utf-8")) > 32:
            raise BridgeError("bad ssid")
        threading.Thread(target=self._fake_wifi_job, args=(nonce, ssid, bool(c.get("connect_now"))), name="fakewifi",
                         daemon=True).start()
        return {"simulated": True}

    def _fake_wifi_job(self, nonce, ssid, connect_now):
        scale = FAKE_WIFI_SCALE
        time.sleep(1.0 * scale)  # the "terminal" asks the bridge for the password
        psk = self.secrets.take(nonce)
        if psk is None:
            return
        with self.fw_lock:
            prev = self.fw["cur"]
            if not any(x["name"] == ssid for x in self.fw["saved"]):
                self.fw["saved"].append({"name": ssid, "ssid": ssid, "mode": "infrastructure", "autoconnect": True,
                                         "priority": 10, "powersave": "disable"})
            if connect_now:
                self.fw["join"] = {"state": "joining", "ssid": ssid, "prev": prev, "t": int(time.time())}
        if not connect_now:
            return
        time.sleep(2.0 * scale)
        with self.fw_lock:
            if ssid == "FailNet" or psk == "wrongpass1":
                self.fw["saved"] = [x for x in self.fw["saved"] if x["name"] != ssid]
                self.fw["join"] = {"state": "failed", "ssid": ssid, "reason": "could not join (wrong password or out of range)",
                                   "fallback": prev, "fallback_ok": True, "removed": True, "t": int(time.time())}
            else:
                self.fw["n"] += 1
                self.fw["cur"], self.fw["ip"] = ssid, "192.168.50.%d" % (20 + self.fw["n"])
                self.fw["join"] = {"state": "joined", "ssid": ssid, "ip": self.fw["ip"], "prev": prev, "t": int(time.time())}
        self.slow = dict(self.slow, net=self.fake_net())
