"""The front-panel menu: reading and writing the menu file and checking it with the menu checker.
It does not draw the screen on the robot."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .mapping_helpers import *  # bundle: skip
from .stack_adapters import *  # bundle: skip


MENU_REL = "robot_code/menu/menu.yaml"
MENU_MAX_CHARS = 16000
MENU_CHECK_TIMEOUT = 20.0


def menu_checker_path(home):
    """The robot's own menu checker: env STUDIO_MENU_CHECKER, else <home>/robot_code/delivery/menu_config.py."""
    return os.environ.get("STUDIO_MENU_CHECKER") or os.path.join(home, "robot_code", "delivery", "menu_config.py")


def parse_check_json(text):
    """The checker's JSON (a dict with a boolean `ok`), or None when the text is not that."""
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("ok"), bool) else None


def menu_error_text(check, limit=3):
    errs = [str(e) for e in (check or {}).get("errors") or []][:limit]
    return "the menu file is not valid: " + ("; ".join(errs) if errs else "the checker found problems")


class MenuChecker:
    """Runs the delivery package's menu_config.py: check_file(path) -> the checker's JSON dict (exit 0 and 1 both carry JSON)."""

    def __init__(self, home, path=None):
        self.home = home
        self.path = path or menu_checker_path(home)

    def checker_ok(self):
        return os.path.isfile(self.path)

    def check_file(self, path):
        if not self.checker_ok():
            raise ServiceError("menu checker not found at %s; deploy the delivery package to the robot "
                               "(delivery/tools/deploy.py)" % self.path)
        argv = [sys.executable, self.path, "--check", path, "--json", "--home", self.home]
        try:
            r = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=MENU_CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ServiceError("menu checker failed: timed out after %d s" % MENU_CHECK_TIMEOUT)
        except OSError as e:
            raise ServiceError("menu checker failed: %s" % e)
        out = r.stdout.decode("utf-8", "replace")
        err = tail_lines(r.stderr.decode("utf-8", "replace"), 1)
        if r.returncode not in (0, 1):
            raise ServiceError("menu checker failed: %s" % (err[0] if err else "exit code %s" % r.returncode))
        d = parse_check_json(out)
        if d is None:
            raise ServiceError("menu checker failed: %s" % (err[0] if err else "its answer was not valid JSON"))
        return d


class MenuService:
    """~/robot_code/menu/menu.yaml: read it, check a text and save a text, always with the robot's own checker."""

    def __init__(self, home, checker):
        self.home, self.checker = home, checker
        self.dir = os.path.join(home, "robot_code", "menu")
        self.path = os.path.join(self.dir, "menu.yaml")

    def _inside(self, rel):
        p = safe_join(self.home, rel)
        if p is None:
            raise ServiceError("The menu path is outside the home folder.")
        return p

    def get(self):
        path = self._inside(MENU_REL)
        ck_ok = self.checker.checker_ok()
        out = {"path": path, "exists": False, "text": "", "check": None, "checker_ok": ck_ok}
        if not os.path.exists(path):
            return out
        if not os.path.isfile(path):
            raise ServiceError("%s is not a regular file." % path)
        try:
            if os.path.getsize(path) > MENU_MAX_CHARS * 2:
                raise ServiceError("The menu file is larger than %d characters; edit it on the robot." % (MENU_MAX_CHARS * 2))
            with open(path, "rb") as f:
                text = f.read().decode("utf-8", "replace")
        except OSError as e:
            raise ServiceError("cannot read the menu file: %s" % e)
        out["exists"], out["text"] = True, text
        if ck_ok:
            out["check"] = self.checker.check_file(path)
        return out

    @staticmethod
    def _text_ok(text):
        if not isinstance(text, str):
            raise ServiceError("text must be a string")
        if len(text) > MENU_MAX_CHARS:
            raise ServiceError("The menu file is over %d characters." % MENU_MAX_CHARS)

    def _need_checker(self):
        if not self.checker.checker_ok():
            self.checker.check_file("")      # raises the "menu checker not found at ..." error

    def _check_text(self, text):
        d = tempfile.mkdtemp(prefix="studio_menu_")
        try:
            tmp = os.path.join(d, "menu.yaml")
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            return self.checker.check_file(tmp)
        except OSError as e:
            raise ServiceError("cannot check the text: %s" % e)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def check(self, text):
        self._text_ok(text)
        self._need_checker()
        return {"check": self._check_text(text)}

    def put(self, text, confirm):
        if confirm is not True:
            raise ServiceError("Saving the menu needs confirm:true.")
        self._text_ok(text)
        self._need_checker()
        path = self._inside(MENU_REL)
        folder = self._inside("robot_code/menu")
        if os.path.lexists(path) and not os.path.isfile(path):
            raise ServiceError("%s is not a regular file; the menu was not saved." % path)
        ck = self._check_text(text)
        if not ck.get("ok"):
            raise ServiceError(menu_error_text(ck), check=ck)
        try:
            os.makedirs(folder, exist_ok=True)
            if os.path.isfile(path):
                shutil.copy2(path, path + ".bak")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            os.replace(tmp, path)
        except OSError as e:
            try:
                os.remove(path + ".tmp")
            except OSError:
                pass
            raise ServiceError("cannot save the menu file: %s" % e)
        return {"path": path, "check": ck}
