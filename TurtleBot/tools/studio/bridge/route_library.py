"""RouteLibrary: lists routes, sets the current route and takes route uploads, plus a fake trip probe
for tests. It does not drive the robot."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .mapping_helpers import *  # bundle: skip
from .ros_fake import *  # bundle: skip
from .stack_adapters import *  # bundle: skip


class FakeTripProbe(ProcessProbe):
    """Fake robot: the menu runs, a trip only when the hidden fake_trip command says so, no navigation stack."""

    def __init__(self):
        self.mission = False

    def running(self, pattern):
        if pattern == ROUTE_MENU_PATTERN:
            return True
        if pattern == ROUTE_MISSION_PATTERN:
            return bool(self.mission)
        return False


class RouteLibrary:
    """The routes folder (~/robot_code/routes/<name>/ and the link `current`) and the read-only trip status from the menu
    log. Every path is checked to stay inside the routes folder."""

    def __init__(self, home, fake, probe):
        self.home, self.fake, self.probe = home, fake, probe
        self.dir = os.path.join(home, "robot_code", "routes")
        self.log_path = os.path.join(home, "robot_code", "logs", "delivery", "menu.log")

    @staticmethod
    def _check_name(name):
        """A usable route name: valid, not `current` (the link) and not hidden (.upload-<name> folders are hidden)."""
        if isinstance(name, str) and (name == "current" or name.startswith(".")):
            raise ServiceError("%s is a reserved name" % name)
        if not valid_map_name(name):
            raise ServiceError("Bad route name. Use 1 to 48 letters, digits, _ or -, starting with a letter or digit.")

    def _folder(self, name):
        self._check_name(name)
        p = safe_join(self.dir, name)
        if p is None or os.path.dirname(p) != os.path.realpath(self.dir) or not os.path.isdir(p):
            raise ServiceError("There is no route folder named %s." % name)
        return p

    @staticmethod
    def _entry(n, p, files=None):
        if files is None:
            try:
                files = os.listdir(p)
            except OSError:
                files = []
        missing = route_missing(files)
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            mtime = None
        e = {"name": n, "valid": not missing, "missing": missing, "mtime": mtime}
        txt = read_text(os.path.join(p, "route.yaml"), 256 * 1024)
        if txt is not None:
            e["waypoints"] = count_waypoints(txt)
        return e

    def list(self):
        routes = []
        try:
            entries = sorted(os.listdir(self.dir))
        except OSError:
            entries = []
        for n in entries:
            p = os.path.join(self.dir, n)
            if n == "current" or n.startswith(".") or not _is_real_dir(p):
                continue
            routes.append(self._entry(n, p))
        cur, ok = read_current(self.dir)
        return {"routes": routes, "current": cur, "current_ok": ok, "dir": self.dir}

    def trip_running(self):
        """(mission running, name of a running navigation launch or None)."""
        stack = next((pat for pat in ROUTE_STACK_PATTERNS if self.probe.running(pat)), None)
        return bool(self.probe.running(ROUTE_MISSION_PATTERN)), stack

    def set_current(self, name, confirm):
        if confirm is not True:
            raise ServiceError("Changing the route needs confirm:true.")
        p = self._folder(name)
        missing = route_missing(os.listdir(p))
        if missing:
            raise ServiceError("Route %s is not valid, missing: %s." % (name, ", ".join(missing)))
        mission, stack = self.trip_running()
        if mission:
            raise ServiceError("A trip is running; change the route after it ends.")
        if stack:
            raise ServiceError("The navigation stack is running (%s); stop it before changing the route." % stack)
        try:
            write_current(self.dir, name, self.fake)
        except (ValueError, OSError) as e:
            raise ServiceError("Cannot change the route: %s" % e)
        return {"current": name}

    def _upload_paths(self, name):
        """(target routes/<name>, upload folder routes/.upload-<name>), both directly inside the routes folder."""
        self._check_name(name)
        base = os.path.realpath(self.dir)
        target, up = os.path.join(base, name), os.path.join(base, ".upload-" + name)
        if os.path.dirname(target) != base or os.path.dirname(up) != base:
            raise ServiceError("The path is outside the routes folder.")
        return target, up

    def upload_cleanup(self, name):
        """Remove a leftover routes/.upload-<name> (an upload that was cut off). A link is removed, never followed."""
        target, up = self._upload_paths(name)
        try:
            if os.path.islink(up):
                os.remove(up)
            elif os.path.isdir(up):
                shutil.rmtree(up)
            elif os.path.lexists(up):
                raise ServiceError(".upload-%s is not a folder; it was left as it is." % name)
        except OSError as e:
            raise ServiceError("Cannot remove the old upload folder: %s" % e)
        return {"exists": os.path.lexists(target)}

    def upload_finish(self, name):
        """Make the finished upload routes/.upload-<name> the route <name> with one rename (atomic)."""
        target, up = self._upload_paths(name)
        if os.path.lexists(target):
            raise ServiceError("A route named %s already exists." % name, exists=True)
        if os.path.islink(up) or not os.path.isdir(up):
            raise ServiceError("There is no upload folder for %s; upload it again." % name)
        try:
            os.rename(up, target)
        except OSError as e:
            raise ServiceError("Cannot finish the upload: %s" % e)
        return {"route": self._entry(name, target)}

    def trip_status(self, lines=40):
        return {"menu_running": bool(self.probe.running(ROUTE_MENU_PATTERN)),
                "mission_running": bool(self.probe.running(ROUTE_MISSION_PATTERN)),
                "stack_running": any(self.probe.running(pat) for pat in ROUTE_STACK_PATTERNS),
                "log_path": self.log_path, "lines": tail_text_lines(self.log_path, lines)}

    def seed_fake(self):
        """Fake robot: when the routes folder does not exist, make routes home and route1, `current` -> home and a sample
        menu log. Returns True when it seeded."""
        if os.path.exists(self.dir):
            return False
        g = FakeMapGrid()
        g.reveal_all()
        pgm = g.pgm_bytes()
        origin = (g.RES, g.origin[0], g.origin[1])
        yaml_map = ("image: map.pgm\nmode: trinary\nresolution: %s\norigin: [%.3f, %.3f, 0.0]\nnegate: 0\n"
                    "occupied_thresh: 0.65\nfree_thresh: 0.25\n" % origin)
        mask = "image: map.pgm\nmode: scale\nresolution: %s\norigin: [%.3f, %.3f, 0.0]\n" % origin
        routes = {
            "home": ("dock_pose: {x: 0.050, y: 0.156, yaw: -31.6}\n",
                     [(-0.550, 0.540, 157.5), (-0.884, 0.673, 164.4)], [(-1.243, 0.714, -2.1)]),
            "route1": ("dock_pose: {x: 0.000, y: 0.000, yaw: 0.0}\n",
                       [(0.800, 0.000, 0.0), (1.600, 0.400, 20.0), (2.200, 0.400, 90.0)],
                       [(1.600, 0.400, 200.0), (0.600, 0.100, 180.0)]),
        }

        def items(pts):
            return "".join("  - {x: %.3f, y: %.3f, yaw: %.1f}\n" % p for p in pts)

        for name, (dock, out, back) in routes.items():
            d = os.path.join(self.dir, name)
            os.makedirs(d)
            route = ("version: 1\nframe_id: map\nmap: \"map.yaml\"\n" + dock + "outbound:\n" + items(out) + "inbound:\n" +
                     items(back) + "settings:\n  max_speed: 0.2\n")
            for fname, data in (("route.yaml", route.encode("ascii")), ("map.yaml", yaml_map.encode("ascii")),
                                ("keepout_mask.yaml", mask.encode("ascii")), ("speed_mask.yaml", mask.encode("ascii")),
                                ("map.pgm", pgm)):
                with open(os.path.join(d, fname), "wb") as f:
                    f.write(data)
        write_current(self.dir, "home", True)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("2026-11-12 01:40:07 delivery_menu started, pid 1218\n"
                    "2026-11-12 01:40:07 route home, 2 outbound and 1 inbound waypoints\n"
                    "2026-11-12 01:40:08 waiting for a button press\n"
                    "2026-11-12 01:52:31 button: Deliver pressed, no trip started (fake robot)\n")
        return True
