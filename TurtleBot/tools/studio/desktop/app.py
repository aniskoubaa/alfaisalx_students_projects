"""The Studio application object: state, start-up and shutdown. Its features come from the mixins
of the modules above; this class only lists them.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip
from .wifi_scripts import *  # bundle: skip
from .laptop_network import *  # bundle: skip
from .programs import *  # bundle: skip
from .events import *  # bundle: skip
from .alerts import *  # bundle: skip
from .mapping import *  # bundle: skip
from .bridge_process import *  # bundle: skip
from .connection import *  # bundle: skip
from .forwarding import *  # bundle: skip
from .telemetry import *  # bundle: skip
from .file_sync import *  # bundle: skip
from .terminals import *  # bundle: skip
from .settings import *  # bundle: skip
from .trust import *  # bundle: skip
from .map_api import *  # bundle: skip
from .updates import *  # bundle: skip
from .wifi import *  # bundle: skip


class Studio(ProgramsMixin, ConnectionMixin, ForwardingMixin, TelemetryMixin, FileSyncMixin, TerminalMixin, SettingsMixin, TrustMixin, MappingMixin, UpdatesMixin, WifiMixin):
    def __init__(self, args):
        self.args = args
        self.fake = bool(args.fake)
        self.cfg = args.config_dir or config_dir()
        os.makedirs(self.cfg, exist_ok=True)
        self.token = secrets.token_urlsafe(24)
        self.heartbeat = getattr(args, 'heartbeat', 15.0)
        self.port = None
        self.bus = Bus()
        self.maps = MapStore()
        self.bridge = Bridge(self)
        self.set_lock = threading.Lock()
        self.settings = self._load_settings()
        self.known_hosts = os.path.join(self.cfg, 'known_hosts')
        # the fake robot's home: --fake-home, else STUDIO_BRIDGE_HOME (tests), else in the config folder. The fake bridge and
        # the fake tar helper must use the same folder.
        self.fake_home = args.fake_home or os.environ.get('STUDIO_BRIDGE_HOME') or os.path.join(self.cfg, 'fake_home')
        self.bridge_script = args.bridge_script or os.path.join(HERE, 'robot_bridge.py')
        self.catalog_path = getattr(args, 'catalog', None) or os.path.join(HERE, 'programs.json')
        self.templates_dir = getattr(args, 'templates_dir', None) or os.path.join(HERE, 'templates')
        self.log_path = os.path.join(self.cfg, 'studio.log')
        try:
            if os.path.getsize(self.log_path) > 1_000_000:
                os.replace(self.log_path, self.log_path + '.old')
        except OSError:
            pass
        self.write_known_hosts()
        self.sync_lock = threading.Lock()
        self._ssh_ver = None
        self.wifi_jobs = collections.OrderedDict()  # nonce -> ssid of the Wi-Fi joins started from this process
        self.closing = False
        self.stop_cb = None             # v1.3: set by main(); stops the server (Quit Studio, exit when closed)
        self.reconn = None              # v1.3: state of a running automatic reconnect, else None
        self.reconn_lock = threading.Lock()
        self.reconnect_delays = RECONNECT_DELAYS
        self.reconnect_give_up = RECONNECT_GIVE_UP
        self.last_cands = []            # newest discover result (diagnostics)
        self.deep_lock = threading.Lock()
        self.update_delay = getattr(args, 'update_delay', 5.0)
        self.update = {'checked': None, 'latest': None, 'page': None, 'notes': '', 'error': None}
        self.update_lock = threading.Lock()
        self._update_logged = False
        # 2.0
        self.web_dir = getattr(args, 'web_dir', None) or WEB_DIR
        self.history = History()
        self.alerts = AlertCenter(os.path.join(self.cfg, 'events.jsonl'), self.bus.publish)
        self.tele_armed = False         # what Studio believes (from the bridge's teleop events and replies)
        self.tele_gen = None            # bridge generation the arm belongs to: motion is never sent to another process
        self.conn_lost = False
        self.run_names = {}
        self.run_stopped = set()       # run ids the user stopped (a stopped program ends with a non-zero code: not an error)
        self.estop_until = 0.0         # runs that end shortly after an e-stop or Stop all were stopped by it
        self.bus.tap = self._tap

    def quit(self):
        """Quit Studio button: answer first, then stop cleanly (the page shows 'Studio has stopped')."""
        self.log('info', 'Quit requested from the page')
        self.teleop_off('Studio is quitting.', 1.5)
        self.bus.publish({'ev': 'quit'})
        t = threading.Timer(0.4, lambda: self.stop_cb() if self.stop_cb else None)
        t.daemon = True
        t.start()
        return {'ok': True}

    def shutdown(self):
        self.closing = True
        self.teleop_off('Studio is quitting.', 1.5)
        self.reconnect_cancel(quiet=True)
        try:
            self.bridge.stop()
        except Exception:
            pass
        self.bus.close_all()
