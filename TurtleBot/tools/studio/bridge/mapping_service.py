"""MappingService: starts, saves and stops mapping, one state at a time, and keeps its status.
It does not list or rename saved maps (see map_library.py)."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .mapping_helpers import *  # bundle: skip
from .stack_adapters import *  # bundle: skip


def yaml_stamp(path):
    """(mtime_ns, size) of a file, or None when it does not exist. Taken before a save to see if it was rewritten."""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def yaml_rewritten(before, after):
    """True when the file written by a save is new: it did not exist before, or its modification time moved forward.
    `before` is the stamp (or None, absent) taken before the script ran."""
    if after is None:
        return False
    if before is None:
        return True
    return after[0] > before[0]


class MappingService:
    """Mapping state machine (DESIGN-MAPPING.md section 4): idle, starting, mapping, saving, stopping, error.
    start, save and stop reply at once and finish in their own thread; a probe (every probe_period s) finds a SLAM that
    was started or stopped outside Studio. emit(dict) gets a `mapping` event on every change. Thread-safe."""

    def __init__(self, runner, probe, maps_dir, emit, disarm=None, probe_period=2.0, start_timeout=START_TIMEOUT_S,
                 save_timeout=SAVE_TIMEOUT_S, stop_timeout=STOP_TIMEOUT_S, seen_wait=15.0, gone_wait=10.0,
                 clock=time.time, map_reset=None):
        self.runner, self.probe, self.maps_dir, self.emit, self.disarm = runner, probe, maps_dir, emit, disarm
        self.probe_period, self.clock = probe_period, clock
        self.map_reset = map_reset              # called when a session starts or has ended: forget the old map
        self.start_timeout, self.save_timeout, self.stop_timeout = start_timeout, save_timeout, stop_timeout
        self.seen_wait, self.gone_wait = seen_wait, gone_wait
        self.lock = threading.Lock()
        self.state = "idle"
        self.since = clock()
        self.last_error = None
        self.last_saved = None
        self.unsaved = False
        self.other_stack = None
        self.saving_name = None
        self.gen = 0
        self._stop = threading.Event()
        self._probe_thread = None

    # ---- state
    def _info(self):
        return {"state": self.state, "since": round(self.since, 3), "last_error": self.last_error,
                "last_saved": self.last_saved, "unsaved": self.unsaved, "scripts_ok": bool(self.runner.scripts_ok()),
                "other_stack": self.other_stack, "maps_dir": self.maps_dir}

    def status(self):
        with self.lock:
            return self._info()

    def busy_name(self):
        """Name of the map that is being saved right now, or None."""
        with self.lock:
            return self.saving_name if self.state == "saving" else None

    def _emit(self, result=None):
        ev = dict(self._info(), ev="mapping")
        if result is not None:
            ev["result"] = result
        try:
            self.emit(ev)
        except Exception as e:
            log("mapping emit:", repr(e))

    def _go(self, state, result=None, **fields):
        """Enter a state (lock held), set fields, emit one event."""
        self.state = state
        self.since = self.clock()
        self.gen += 1
        for k, v in fields.items():
            setattr(self, k, v)
        if state in ("starting", "idle") and self.map_reset:
            try:
                self.map_reset()
            except Exception as e:
                log("mapping map_reset:", repr(e))
        self._emit(result)

    def _disarm(self, why):
        if self.disarm:
            try:
                self.disarm(why)
            except Exception as e:
                log("mapping disarm:", repr(e))

    def _script(self, script, args, timeout):
        try:
            return self.runner.run(script, args, timeout)
        except Exception as e:
            return False, "%s failed: %s: %s" % (script, type(e).__name__, e)

    def _wait_for(self, cond, secs):
        end = time.monotonic() + secs
        while True:
            if cond():
                return True
            if time.monotonic() >= end or self._stop.wait(min(0.2, max(0.01, secs / 5.0))):
                return bool(cond())

    # ---- probe
    def probe_once(self):
        """Look at the processes once: adopts a SLAM started outside Studio, reports one that vanished."""
        with self.lock:
            g = self.gen
        slam, other = detect_stack(self.probe.running)
        with self.lock:
            changed = other != self.other_stack
            self.other_stack = other
            if self.gen == g:
                if self.state == "idle" and slam:
                    self._go("mapping", unsaved=True, last_error=None)
                    return
                if self.state == "mapping" and not slam:
                    self._go("error", last_error="The mapping process is no longer running. It stopped or crashed; "
                                                 "the unsaved map is lost.")
                    return
            if changed:
                self._emit()

    def start_probe(self):
        self.probe_once()

        def loop():
            while not self._stop.wait(self.probe_period):
                try:
                    self.probe_once()
                except Exception as e:
                    log("mapping probe:", repr(e))
        self._probe_thread = threading.Thread(target=loop, name="mapprobe", daemon=True)
        self._probe_thread.start()

    def close(self):
        """Stop the probe thread. A running SLAM is left alone (mapping survives a Studio disconnect)."""
        self._stop.set()

    # ---- commands
    def start(self, keep_camera=False):
        self.probe_once()
        with self.lock:
            if self.state != "idle":
                raise ServiceError({"mapping": "Mapping is already running.", "error": "Mapping is in an error state. "
                                    "Reset it or stop it first."}.get(self.state, "Mapping is busy (%s). Wait until it "
                                                                                  "is done." % self.state))
            if self.other_stack:
                raise ServiceError("A navigation stack is running (%s). Stop it first." % self.other_stack,
                                   other_stack=self.other_stack)
            if not self.runner.scripts_ok():
                miss = ", ".join(self.runner.missing_scripts()) or "delivery scripts"
                raise ServiceError("The delivery scripts are missing on the robot (%s). Deploy them first." % miss,
                                   scripts_missing=True)
            self._go("starting", last_error=None)
            info = self._info()
        self._disarm("mapping is starting")
        threading.Thread(target=self._run_start, args=(bool(keep_camera),), name="mapstart", daemon=True).start()
        return info

    def _run_start(self, keep_camera):
        ok, out = self._script("start_stack.sh", ["map"] + (["--keep-camera"] if keep_camera else []), self.start_timeout)
        tail = tail_lines(out)
        err = None
        if ok:
            ok = self._wait_for(lambda: self.probe.running(SLAM_PATTERN), self.seen_wait)
            if not ok:
                err = "The start script finished but the SLAM process is not running."
        else:
            err = (tail[-1] if tail else "start_stack.sh failed")
        with self.lock:
            if ok:
                self._go("mapping", {"op": "start", "ok": True, "output_tail": tail}, unsaved=True, last_error=None)
            else:
                self._go("error", {"op": "start", "ok": False, "error": err, "output_tail": tail}, last_error=err)

    def save(self, name, overwrite=False):
        if not valid_map_name(name):
            raise ServiceError("Bad map name. Use 1 to 48 letters, digits, _ or -, starting with a letter or digit.")
        prefix = os.path.join(self.maps_dir, name)
        with self.lock:
            if self.state != "mapping":
                raise ServiceError("Saving needs a running mapping session (state: %s)." % self.state)
            if os.path.exists(prefix + ".yaml") and not overwrite:
                raise ServiceError("A map named %s already exists." % name, exists=True)
            before = yaml_stamp(prefix + ".yaml")
            self._go("saving", saving_name=name)
            info = self._info()
        self._disarm("mapping is saving")
        threading.Thread(target=self._run_save, args=(name, prefix, bool(overwrite), before), name="mapsave",
                         daemon=True).start()
        return info

    def _run_save(self, name, prefix, overwrite, before=None):
        ok, out = self._script("save_map.sh", [prefix] + (["--force"] if overwrite else []), self.save_timeout)
        tail = tail_lines(out)
        if ok and not os.path.isfile(prefix + ".yaml"):
            ok = False
            tail.append("the script finished but %s.yaml was not written" % name)
        elif ok and before is not None and not yaml_rewritten(before, yaml_stamp(prefix + ".yaml")):
            ok = False
            tail.append("the map file was not rewritten")
        with self.lock:
            if ok:
                self._go("mapping", {"op": "save", "ok": True, "name": name, "output_tail": tail},
                         last_saved={"name": name, "t": round(self.clock(), 3)}, unsaved=False, last_error=None,
                         saving_name=None)
            else:
                err = tail[-1] if tail else "save_map.sh failed"
                self._go("mapping", {"op": "save", "ok": False, "name": name, "error": err, "output_tail": tail},
                         last_error=err, saving_name=None)

    def stop(self):
        with self.lock:
            if self.state not in ("mapping", "error"):
                raise ServiceError("Mapping cannot be stopped now (state: %s)." % self.state)
            self._go("stopping")
            info = self._info()
        self._disarm("mapping is stopping")
        threading.Thread(target=self._run_stop, name="mapstop", daemon=True).start()
        return info

    def _run_stop(self):
        ok, out = self._script("stop_stack.sh", [], self.stop_timeout)
        tail = tail_lines(out)
        gone = self._wait_for(lambda: not self.probe.running(SLAM_PATTERN), self.gone_wait)
        with self.lock:
            if ok and gone:
                self._go("idle", {"op": "stop", "ok": True, "output_tail": tail}, unsaved=False, last_error=None)
            else:
                err = "The mapping process is still running after the stop script." if ok else \
                    (tail[-1] if tail else "stop_stack.sh failed")
                self._go("error", {"op": "stop", "ok": False, "error": err, "output_tail": tail}, last_error=err)

    def reset(self):
        """Leave the error state: idle or mapping again, from the processes."""
        slam = bool(self.probe.running(SLAM_PATTERN))
        with self.lock:
            if self.state == "error":
                self._go("mapping" if slam else "idle", last_error=None, unsaved=slam)
            return self._info()
