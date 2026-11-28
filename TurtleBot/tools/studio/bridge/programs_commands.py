"""Bridge commands that start, watch and stop programs on the robot (runs), including the monitor
thread and the output pump."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .wifi_join import *  # bundle: skip
from .run_state import *  # bundle: skip


class ProgramsMixin:
    # ---- runs
    def _unique_log(self, name):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        base = "%s_%s" % (stamp, re.sub(r"[^A-Za-z0-9_.-]", "_", name))
        path, i = os.path.join(self.logdir, base + ".log"), 1
        while os.path.exists(path):
            i += 1
            path = os.path.join(self.logdir, "%s_%d.log" % (base, i))
        return path

    def h_run(self, c):
        rel = str(c.get("path", ""))
        args = c.get("args") or []
        if not isinstance(args, list) or any((not isinstance(a, str)) or "\0" in a for a in args):
            raise BridgeError("args must be a list of strings")
        motion = bool(c.get("motion"))
        if motion and not c.get("confirmed"):
            raise BridgeError("motion needs confirmation")
        if motion and os.path.exists(self.stop_file):
            raise BridgeError("e-stop/STOP file present: release first")
        d, full = self.resolve_file(c.get("dir"), rel)
        if not os.path.isfile(full):
            raise BridgeError("file not found in %s: %s" % (d, rel))
        ext = os.path.splitext(full)[1].lower()
        if ext == ".py":
            argv = [sys.executable or "python3", "-u", full]
        elif ext == ".sh":
            argv = [shutil.which("bash") or "bash", full]
        else:
            raise BridgeError("only .py and .sh files can be run")
        os.makedirs(self.logdir, exist_ok=True)
        name = os.path.basename(full)
        log_path = self._unique_log(name)
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        # Studio asked the person to confirm this moving program (a `confirmed` motion run is the only way to get here
        # with motion set), so tell the program: the one-program-per-shape wrappers then skip their terminal "area clear?"
        # question, which cannot be answered here (stdin is closed). Never inherited: removed first, set only now.
        env.pop(MOTION_CONFIRMED_ENV, None)
        if motion:
            env[MOTION_CONFIRMED_ENV] = "1"
        kw = {}
        if os.name == "posix":
            kw["start_new_session"] = True
        else:
            kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        with open(log_path, "ab") as lf:
            try:
                proc = subprocess.Popen(argv + args, cwd=os.path.dirname(full), env=env, stdin=subprocess.DEVNULL,
                                        stdout=lf, stderr=subprocess.STDOUT, **kw)
            except OSError as e:
                raise BridgeError("cannot start: %s" % e)
        run_id = os.path.basename(log_path)[:-4]
        run = Run(run_id, name, proc.pid, log_path, full, time.time(), motion, proc)
        try:
            with open(log_path + ".pid", "w") as f:
                json.dump({"run_id": run_id, "pid": proc.pid, "name": name, "path": full, "motion": motion,
                           "started_wall": run.started_wall, "args": args}, f)
        except OSError as e:
            log("pid file:", e)
        with self.runs_lock:
            self.runs[run_id] = run
        return {"run_id": run_id, "pid": proc.pid, "log": log_path}

    def rediscover(self):
        try:
            names = [n for n in os.listdir(self.logdir) if n.endswith(".log.pid")]
        except OSError:
            return
        names.sort(key=lambda n: os.path.getmtime(os.path.join(self.logdir, n)), reverse=True)
        for n in names[:20]:
            try:
                with open(os.path.join(self.logdir, n)) as f:
                    j = json.load(f)
                run_id = str(j["run_id"])
                if run_id in self.runs:
                    continue
                lp = os.path.join(self.logdir, n[:-4])
                r = Run(run_id, j.get("name", run_id), int(j["pid"]), lp, j.get("path", j.get("name", "")),
                        j.get("started_wall"), j.get("motion"))
                try:
                    r.offset = os.path.getsize(lp)
                except OSError:
                    pass
                r.exit_sent = True          # no history re-emit; set back below if still alive
                if self.run_alive(r):
                    r.exit_sent = False
                with self.runs_lock:
                    self.runs[run_id] = r
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def run_alive(self, r):
        if r.proc is not None:
            return r.proc.poll() is None
        return pid_alive(r.pid, r.needle)

    def h_runs(self, c):
        self.rediscover()
        with self.runs_lock:
            return {"runs": [r.info(self.run_alive(r)) for r in self.runs.values()]}

    def _signal_run(self, r, sig):
        try:
            if os.name == "posix":
                s = getattr(signal, sig)
                try:
                    pg = os.getpgid(r.pid)
                except OSError:
                    return
                if pg == r.pid:
                    os.killpg(pg, s)
                else:
                    os.kill(r.pid, s)
            elif r.proc is not None:
                if sig == "SIGINT":
                    r.proc.send_signal(signal.CTRL_BREAK_EVENT)
                elif sig == "SIGTERM":
                    r.proc.terminate()
                else:
                    r.proc.kill()
        except (OSError, ValueError) as e:
            log("signal", sig, r.run_id, e)

    def stop_run(self, r, waits=(3.0, 2.0, 2.0)):
        """SIGINT to the process group, wait 3 s, SIGTERM, wait 2 s, SIGKILL."""
        if not self.run_alive(r):
            return "already_exited"
        for sig, wait in zip(("SIGINT", "SIGTERM", "SIGKILL"), waits):
            self._signal_run(r, sig)
            end = time.monotonic() + wait
            while time.monotonic() < end:
                if not self.run_alive(r):
                    return sig
                time.sleep(0.05)
        return "SIGKILL" if not self.run_alive(r) else "SIGKILL_failed"

    def stop_many(self, runs):
        how, threads = {}, []
        for r in runs:
            t = threading.Thread(target=lambda r=r: how.__setitem__(r.run_id, self.stop_run(r)), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(8.0)
        return how

    def h_stop(self, c):
        rid = c.get("run_id")
        with self.runs_lock:
            if rid == "all":
                targets = [r for r in self.runs.values() if self.run_alive(r)]
            elif rid in self.runs:
                targets = [self.runs[rid]]
            else:
                raise BridgeError("no such run: %s" % rid)
        how = self.stop_many(targets)
        return {"stopped": list(how), "how": how}

    def _run_monitor(self):
        while not self.stop.is_set():
            with self.runs_lock:
                active = [r for r in self.runs.values() if not r.exit_sent]
            for r in active:
                try:
                    self._pump(r)
                except Exception as e:
                    log("run monitor:", repr(e))
            self.stop.wait(0.3 if active else 1.0)

    def _pump(self, r):
        alive = self.run_alive(r)
        data = b""
        try:
            with open(r.log, "rb") as f:
                f.seek(r.offset)
                data = f.read(256 * 1024)
                r.offset += len(data)
        except OSError:
            pass
        text = r.pending + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        r.pending = lines.pop()             # incomplete last line waits for its newline
        if not alive and not data:
            if r.pending:
                lines.append(r.pending)
                r.pending = ""
        for i in range(0, len(lines), 200):
            self.emit({"ev": "run_output", "run_id": r.run_id, "lines": [l.rstrip("\r") for l in lines[i:i + 200]]})
        if not alive and not data and not r.pending:
            r.code = r.proc.returncode if r.proc is not None else None
            r.exit_sent = True
            self.emit({"ev": "run_exit", "run_id": r.run_id, "code": r.code})
