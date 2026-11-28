"""BridgeError, the hello message and main(): reads the mode from the environment, builds the Bridge and
runs the command loop."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .ros_base import *  # bundle: skip
from .ros_real import *  # bundle: skip
from .ros_fake import *  # bundle: skip
from .bridge_core import *  # bundle: skip


class BridgeError(Exception):
    def __init__(self, msg, **extra):
        Exception.__init__(self, msg)
        self.extra = extra


MAPPING_BUSY_TEXT = {"starting": "Mapping is starting; driving is blocked until it is ready.",
                     "saving": "Mapping is saving the map; driving is blocked until it is done.",
                     "stopping": "Mapping is stopping; driving is blocked until it is done."}


# ======================================================================= main
def hello(ros, fake, home):
    return {"ev": "hello", "version": VERSION, "bridge": "robot_bridge", "hostname": "fake-turtlebot4" if fake else socket.gethostname(),
            "ros": bool(ros.available) and not fake, "ros_distro": os.environ.get("ROS_DISTRO"),
            "rmw": os.environ.get("RMW_IMPLEMENTATION"), "domain": os.environ.get("ROS_DOMAIN_ID", "0"),
            "python": sys.version.split()[0], "pid": os.getpid(), "fake": bool(fake), "home": home,
            "ros_error": ros.error}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TurtleBot Studio robot bridge")
    ap.add_argument("--fake", action="store_true", help="no ROS, simulated data")
    ns, _ = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
    fake = ns.fake or os.environ.get("STUDIO_BRIDGE_FAKE", "") not in ("", "0")
    home = os.environ.get("STUDIO_BRIDGE_HOME") or (tempfile.mkdtemp(prefix="studio_fake_") if fake else os.path.expanduser("~"))
    stdin = sys.stdin.buffer
    stop = threading.Event()
    writer = Writer(sys.stdout.buffer, on_broken=stop.set)
    ros = FakeRos() if fake else RosReal()
    bridge = Bridge(ros, writer, home, fake)
    bridge.stop = stop
    for s in ("SIGTERM", "SIGINT", "SIGHUP"):
        if hasattr(signal, s):
            try:
                signal.signal(getattr(signal, s), lambda *a: stop.set())
            except (ValueError, OSError):
                pass
    ros.start(writer.emit)
    writer.emit(hello(ros, fake, home))
    bridge.start_threads()

    def reader():
        try:
            while not stop.is_set():
                line = stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line.decode("utf-8", errors="replace"))
                    if not isinstance(cmd, dict):
                        raise ValueError("not an object")
                except ValueError as e:
                    log("bad command line:", e)
                    continue
                threading.Thread(target=bridge.handle, args=(cmd,), daemon=True, name="cmd").start()
        except Exception as e:
            log("reader stopped:", repr(e))
        stop.set()
    threading.Thread(target=reader, daemon=True, name="stdin").start()
    try:
        while not stop.wait(0.25):
            pass
    finally:
        # user programs started with "run" are detached and keep running; only our own threads stop
        bridge.status_period = None
        bridge.mapping.close()          # only the probe thread: a running SLAM keeps running (the next bridge finds it)
        try:
            bridge.teleop_disarm("bridge ended")
        except Exception:
            pass
        t = threading.Thread(target=ros.shutdown, daemon=True)
        t.start()
        t.join(1.0)
        writer.close(0.5)
        try:
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    main()
