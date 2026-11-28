"""The Bridge class: it keeps the shared state, sends events, dispatches commands to the handlers and
starts the threads. The handlers themselves live in the *_commands.py modules, as mixin classes."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .wifi_join import *  # bundle: skip
from .ros_base import *  # bundle: skip
from .run_state import *  # bundle: skip
from .stack_adapters import *  # bundle: skip
from .mapping_service import *  # bundle: skip
from .map_library import *  # bundle: skip
from .route_library import *  # bundle: skip
from .menu_service import *  # bundle: skip
from .commands_basic import *  # bundle: skip
from .files_commands import *  # bundle: skip
from .wifi_commands import *  # bundle: skip
from .programs_commands import *  # bundle: skip
from .estop_commands import *  # bundle: skip
from .streams_commands import *  # bundle: skip
from .teleop_commands import *  # bundle: skip
from .service_commands import *  # bundle: skip
from .system_commands import *  # bundle: skip
from .telemetry_commands import *  # bundle: skip


class Bridge(BasicCommandsMixin, FilesMixin, WifiMixin, ProgramsMixin, EstopMixin, StreamsMixin, TeleopMixin, ServiceHandlersMixin, SystemMixin, TelemetryMixin):
    def __init__(self, ros, writer, home, fake):
        self.ros, self.writer, self.home, self.fake = ros, writer, home, fake
        self.stop = threading.Event()
        self.runs = collections.OrderedDict()
        self.runs_lock = threading.Lock()
        self.run_counter = 0
        self.watches = {}
        self.watch_counter = 0
        self.watch_lock = threading.Lock()
        self.status_period = None
        self.status_wake = threading.Event()
        self.estop_on = None
        self.estop_app = False
        self.estop_t = 0.0
        self.slow = {"net": {}, "clock_synced": None, "ros_service": "unknown", "throttled": None}
        self.cpu_prev = None
        self.logdir = os.path.join(home, "robot_code", "logs")
        self.stop_file = os.path.join(home, "STOP")
        self.t0 = time.monotonic()
        self.secrets = WifiSecrets()
        self.fw_lock = threading.Lock()
        self.fw = fake_wifi_state()
        # Studio 2.0: manual driving + streams
        self.tele_lock = threading.Lock()
        self.tele = {"armed": False, "last_cmd": 0.0, "last_move": 0.0, "zeroed": True, "seq": -1,
                     "max_linear": TELEOP_MAX_LINEAR, "max_angular": TELEOP_MAX_ANGULAR, "armed_t": 0.0}
        self.status_estop = None            # estop.on of the newest status (None = unknown)
        self.streams = {"scan": None, "pose": None, "map": None}      # name -> {"period", "next", "max_points", "last_seq"} while on
        self.stream_lock = threading.Lock()
        self.map_seq = 0
        # Studio 2.1: mapping (the delivery scripts, or timers in fake mode) and the map library
        self.maps_dir = os.path.join(home, "robot_code", "maps")
        if fake:
            self.runner = FakeStackRunner(ros)
            self.probe = FakeProcessProbe(self.runner)
        else:
            self.runner = RealStackRunner(home)
            self.probe = RealProcessProbe()
        self.mapping = MappingService(self.runner, self.probe, self.maps_dir, self.emit,
                                      disarm=lambda why: self.teleop_disarm(why), map_reset=self._map_reset)
        self.maps = MapLibrary(self.maps_dir, self.mapping.busy_name)
        if fake:
            self.trip_probe = FakeTripProbe()
            self.routes = RouteLibrary(home, True, self.trip_probe)
            try:
                self.routes.seed_fake()
            except OSError as e:
                log("cannot seed the sample routes:", e)
        else:
            self.trip_probe = None
            self.routes = RouteLibrary(home, False, self.probe)
        self.menu = MenuService(home, MenuChecker(home))
        if fake:
            try:
                self.maps.seed_demo()
            except OSError as e:
                log("cannot seed the sample map:", e)

    # ---- infrastructure
    def emit(self, obj, droppable=False, key=None):
        if key is None:
            self.writer.emit(obj, droppable)
        else:
            self.writer.emit(obj, droppable, key)

    def _map_reset(self):
        """A mapping session starts or ended: forget the old map and let the next new map be sent."""
        self.ros.map_reset()
        with self.stream_lock:
            v = self.streams.get("map")
            if v is not None:
                v["last_seq"] = None

    def start_threads(self):
        try:
            os.makedirs(self.logdir, exist_ok=True)
        except OSError as e:
            log("cannot create", self.logdir, e)
        self.rediscover()
        self.mapping.start_probe()
        for fn, name in ((self._status_loop, "status"), (self._slow_loop, "slow"), (self._run_monitor, "runmon"),
                         (self._teleop_loop, "teleop"), (self._stream_loop, "streams")):
            threading.Thread(target=fn, name=name, daemon=True).start()

    def reply(self, cid, ok, **kw):
        d = {"ev": "reply", "id": cid, "ok": bool(ok)}
        d.update(kw)
        self.emit(d)

    def handle(self, cmd):
        """Run one command (called in its own thread so a slow command never blocks e-stop)."""
        cid = cmd.get("id")
        name = str(cmd.get("cmd", ""))
        fn = getattr(self, "h_" + name, None) if re.fullmatch(r"[a-z_]+", name) else None
        if fn is None:
            self.reply(cid, False, error="unknown command: %s" % name[:40])
            return
        try:
            res = fn(cmd) or {}
            self.reply(cid, True, **res)
        except BridgeError as e:
            extra = dict(e.extra)
            self.reply(cid, False, error=str(e), **extra)
        except RosError as e:
            self.reply(cid, False, error=str(e))
        except Exception as e:
            log("command", name, "failed:", repr(e))
            self.reply(cid, False, error="internal error: %s: %s" % (type(e).__name__, e))

    def need_ros(self):
        if not self.ros.available:
            raise BridgeError("ROS not available: %s" % (self.ros.error or "not started"))
