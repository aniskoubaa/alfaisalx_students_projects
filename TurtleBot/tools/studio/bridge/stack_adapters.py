"""ServiceError and the adapters that start and stop the mapping stack and look for running processes,
each as a real version and a fake one for tests. Nothing here decides what to do; services call it."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .mapping_helpers import *  # bundle: skip
from .ros_fake import *  # bundle: skip


# ======================================================================= mapping: adapters and services (Studio 2.1)
START_TIMEOUT_S, SAVE_TIMEOUT_S, STOP_TIMEOUT_S = 120.0, 200.0, 90.0       # the delivery scripts, see DESIGN-MAPPING.md
MAP_SCRIPTS = ("start_stack.sh", "save_map.sh", "stop_stack.sh")


class ServiceError(Exception):
    """A refusal of a service (bad name, wrong state, ...). extra goes into the reply (for example exists=True)."""

    def __init__(self, msg, **extra):
        Exception.__init__(self, msg)
        self.extra = extra


class StackRunner:
    """Runs one of the delivery scripts and waits for it: run(script, args, timeout) -> (ok, output text)."""

    def scripts_ok(self):
        raise NotImplementedError

    def missing_scripts(self):
        return []

    def run(self, script, args, timeout):
        raise NotImplementedError


class RealStackRunner(StackRunner):
    """bash <delivery>/robot/<script> args, cwd = home, output captured. Delivery folder: ~/robot_code/delivery, or the
    environment variable STUDIO_DELIVERY_DIR. STUDIO_BASH names another bash (tests on Windows use Git Bash, because
    the bash.exe found first there is the WSL launcher)."""

    def __init__(self, home):
        self.home = home
        self.delivery = os.environ.get("STUDIO_DELIVERY_DIR") or os.path.join(home, "robot_code", "delivery")
        self.bash = os.environ.get("STUDIO_BASH") or "bash"

    def script_path(self, script):
        return os.path.join(self.delivery, "robot", script)

    def missing_scripts(self):
        return [s for s in MAP_SCRIPTS if not os.path.isfile(self.script_path(s))]

    def scripts_ok(self):
        return not self.missing_scripts()

    def run(self, script, args, timeout):
        """Run the script with its output in a temporary FILE, not a pipe: when the bridge (the ssh link) dies in the
        middle of stop_stack.sh or save_map.sh, the script's next echo must not get SIGPIPE and die half way. On posix
        the script has its own session, so no SIGHUP reaches it either. Returns (exit code 0, last 64 KB of output)."""
        argv = [self.bash, self.script_path(script)] + [str(a) for a in args]
        kw = {"start_new_session": True} if os.name == "posix" else {}
        try:
            out_f = tempfile.TemporaryFile()
        except OSError as e:
            return False, "cannot run %s: %s" % (script, e)
        try:
            try:
                p = subprocess.Popen(argv, cwd=self.home, stdin=subprocess.DEVNULL, stdout=out_f,
                                     stderr=subprocess.STDOUT, **kw)
            except OSError as e:
                return False, "cannot run %s: %s" % (script, e)
            timed_out = False
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    if os.name == "posix":
                        os.killpg(p.pid, signal.SIGTERM)
                    else:
                        p.kill()
                except OSError:
                    pass
                try:
                    p.wait(timeout=5)
                except Exception:
                    pass
            text = self._read_tail(out_f)
            if timed_out:
                return False, text + "\n%s timed out after %d s" % (script, timeout)
            return p.returncode == 0, text
        finally:
            try:
                out_f.close()
            except OSError:
                pass

    @staticmethod
    def _read_tail(f, max_bytes=65536):
        try:
            f.flush()
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", "replace")
        except (OSError, ValueError):
            return ""


class FakeStackRunner(StackRunner):
    """No processes: timers (starting 1.5 s, saving 1 s, stopping 1 s, times STUDIO_FAKE_MAP_SCALE) and a FakeMapGrid
    that saves real files."""

    def __init__(self, ros, scale=None):
        self.scale = fake_map_scale() if scale is None else scale
        self.ros = ros
        self.grid = getattr(ros, "map_grid", None) or FakeMapGrid(self.scale)
        self.slam_running = False

    def scripts_ok(self):
        return True

    def _pose(self):
        try:
            p = self.ros.pose_data()
            return p["x"], p["y"], p["yaw"]
        except Exception:
            return 0.0, 0.0, 0.0

    def run(self, script, args, timeout):
        args = [str(a) for a in args]
        if script == "start_stack.sh":
            time.sleep(1.5 * self.scale)
            if "map" not in args:
                return False, "ERROR: give a mode: map or nav"
            self.slam_running = True
            self.grid.begin(self._pose)
            return True, "fake: slam started"
        if script == "save_map.sh":
            time.sleep(1.0 * self.scale)
            if not self.slam_running:
                return False, "ERROR: the fake mapping is not running"
            prefix = next((a for a in args if not a.startswith("-")), "")
            if not prefix:
                return False, "ERROR: give the output path prefix"
            if os.path.exists(prefix + ".yaml") and "--force" not in args:
                return False, "ERROR: %s.yaml exists (use --force to overwrite)" % prefix
            self.grid.save(prefix)
            return True, "fake: saved %s" % prefix
        if script == "stop_stack.sh":
            time.sleep(1.0 * self.scale)
            was = self.slam_running
            self.slam_running = False
            self.grid.end()
            self.grid.reset()
            return True, "slam: sending SIGINT (fake)" if was else "slam: not running"
        return False, "unknown script %s" % script


class ProcessProbe:
    def running(self, pattern):
        raise NotImplementedError


def probe_regex(pattern):
    """The pgrep -f regex for a pattern. A launch file (*.launch.py) only counts when `ros2 launch` runs it: a plain
    name would also match any shell or log command that mentions it (seen on the robot on 2026-11-14, when a shell
    command of another login made mapping_start refuse with "a navigation stack is running" for one probe)."""
    if pattern.endswith(".launch.py"):
        return r"ros2 launch .*" + re.escape(pattern)
    return pattern


class RealProcessProbe(ProcessProbe):
    def running(self, pattern):
        return bool((run_cmd(["pgrep", "-f", probe_regex(pattern)], timeout=3.0) or "").split())


class FakeProcessProbe(ProcessProbe):
    def __init__(self, runner):
        self.runner = runner

    def running(self, pattern):
        return pattern == SLAM_PATTERN and bool(self.runner.slam_running)
