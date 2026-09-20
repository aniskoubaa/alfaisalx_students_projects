#!/usr/bin/env python3
"""Sample board power and temperature during a run via `tegrastats`.

06-benchmark-plan.md is explicit that power and thermals are sampled *throughout*
a run, not read once at the end: a pipeline that hits 30 FPS and then throttles
after eight minutes has not passed.

tegrastats output format shifts between L4T releases, so every field here is
parsed with a tolerant regex and simply omitted when absent.
"""
from __future__ import annotations

import re
import shutil
import statistics
import subprocess
import threading

# e.g. "VDD_IN 5231mW/5102mW" or older "VDD_IN 5231/5102"
_RAIL = re.compile(r"\b(VDD[_A-Z0-9]*|VIN[_A-Z0-9]*)\s+(\d+)mW(?:/(\d+)mW)?")
# e.g. "tj@52.5C" / "cpu@51.2C" / "gpu@50C"
_TEMP = re.compile(r"\b([a-z]+)@([\d.]+)C")
# e.g. "GR3D_FREQ 45%" (JetPack 6+) or "GR3D_FREQ 45%@1300"
_GR3D = re.compile(r"GR3D_FREQ\s+(\d+)%")
# e.g. "RAM 4096/15655MB"
_RAM = re.compile(r"RAM\s+(\d+)/(\d+)MB")


class TegraSampler:
    """Run tegrastats in the background and summarise what it saw.

    Usage:
        with TegraSampler() as s:
            ...run the workload...
        stats = s.summary()
    """

    def __init__(self, interval_ms: int = 500, use_sudo: bool = True):
        self.interval_ms = interval_ms
        self.use_sudo = use_sudo
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.power_mw: dict[str, list[int]] = {}
        self.temps_c: dict[str, list[float]] = {}
        self.gpu_util_pct: list[int] = []
        self.ram_used_mb: list[int] = []
        self.error: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "TegraSampler":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    def available(self) -> bool:
        return shutil.which("tegrastats") is not None

    def start(self) -> None:
        if not self.available():
            self.error = "tegrastats not found on PATH"
            return
        cmd = ["tegrastats", "--interval", str(self.interval_ms)]
        if self.use_sudo:
            cmd = ["sudo", "-n", *cmd]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
        except OSError as exc:
            self.error = f"could not start tegrastats: {exc}"
            return
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                try:
                    self._proc.kill()
                except OSError:
                    pass
        if self._thread:
            self._thread.join(timeout=5)

    # -- parsing -----------------------------------------------------------
    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            self._parse(line)

    def _parse(self, line: str) -> None:
        for rail, inst, _avg in _RAIL.findall(line):
            self.power_mw.setdefault(rail, []).append(int(inst))
        for sensor, value in _TEMP.findall(line):
            self.temps_c.setdefault(sensor, []).append(float(value))
        m = _GR3D.search(line)
        if m:
            self.gpu_util_pct.append(int(m.group(1)))
        m = _RAM.search(line)
        if m:
            self.ram_used_mb.append(int(m.group(1)))

    # -- results -----------------------------------------------------------
    @staticmethod
    def _summarise(values: list[float]) -> dict | None:
        if not values:
            return None
        return {
            "mean": round(statistics.fmean(values), 2),
            "max": round(max(values), 2),
            "samples": len(values),
        }

    def summary(self) -> dict:
        """Condense the sampled series into the fields a result row records."""
        out: dict = {"samples": len(self.gpu_util_pct) or None}
        if self.error:
            out["error"] = self.error

        power = {r: self._summarise(v) for r, v in self.power_mw.items()}
        power = {r: s for r, s in power.items() if s}
        if power:
            out["power_mw"] = power
            # VDD_IN is total board power on most Orin carriers; fall back to
            # the largest-mean rail so a renamed rail still reports something.
            total_rail = next(
                (r for r in power if r.upper().startswith("VDD_IN")),
                max(power, key=lambda r: power[r]["mean"]),
            )
            out["board_power_rail"] = total_rail
            out["board_power_mean_w"] = round(power[total_rail]["mean"] / 1000, 2)
            out["board_power_max_w"] = round(power[total_rail]["max"] / 1000, 2)

        temps = {s: self._summarise(v) for s, v in self.temps_c.items()}
        temps = {s: t for s, t in temps.items() if t}
        if temps:
            out["temps_c"] = temps
            hottest = max(temps, key=lambda s: temps[s]["max"])
            out["temp_max_c"] = temps[hottest]["max"]
            out["temp_hottest_sensor"] = hottest

        gpu = self._summarise([float(v) for v in self.gpu_util_pct])
        if gpu:
            out["gpu_util_pct"] = gpu
        ram = self._summarise([float(v) for v in self.ram_used_mb])
        if ram:
            out["ram_used_mb"] = ram
        return out


if __name__ == "__main__":
    import json
    import time

    with TegraSampler() as sampler:
        time.sleep(5)
    print(json.dumps(sampler.summary(), indent=2))
