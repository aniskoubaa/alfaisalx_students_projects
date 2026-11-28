"""MapLibrary: lists, previews, renames and deletes the saved maps on the robot.
It does not run mapping (see mapping_service.py)."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .mapping_helpers import *  # bundle: skip
from .ros_fake import *  # bundle: skip
from .stack_adapters import *  # bundle: skip


class MapLibrary:
    """The maps folder: <name>.pgm, .yaml, .posegraph, .data. Every path is checked to stay inside the folder."""

    def __init__(self, maps_dir, busy=None):
        self.dir = maps_dir
        self.busy = busy or (lambda: None)

    def _path(self, name, ext=""):
        if not valid_map_name(name):
            raise ServiceError("Bad map name. Use 1 to 48 letters, digits, _ or -, starting with a letter or digit.")
        p = safe_join(self.dir, name + ext)
        if p is None or os.path.dirname(p) != os.path.realpath(self.dir):
            raise ServiceError("The path is outside the maps folder.")
        return p

    def names(self):
        try:
            files = os.listdir(self.dir)
        except OSError:
            return []
        return sorted(f[:-5] for f in files if f.endswith(".yaml") and valid_map_name(f[:-5]))

    def _image_path(self, name, meta):
        """The PGM of a map: the image: line of its YAML when that stays inside the folder, else <name>.pgm."""
        img = (meta or {}).get("image")
        if img and not os.path.isabs(img):
            p = safe_join(self.dir, img)
            if p and os.path.isfile(p):
                return p
        return self._path(name, ".pgm")

    def _meta(self, name):
        try:
            with open(self._path(name, ".yaml"), "r", encoding="utf-8", errors="replace") as f:
                return parse_map_yaml(f.read())
        except (OSError, ValueError):
            return None

    def entry(self, name):
        files, mtime, total = {}, 0.0, 0
        for ext in MAP_EXTS:
            try:
                st = os.stat(self._path(name, ext))
                files[ext[1:]] = st.st_size
                mtime, total = max(mtime, st.st_mtime), total + st.st_size
            except OSError:
                files[ext[1:]] = None
        meta = self._meta(name)
        w = h = None
        try:
            with open(self._image_path(name, meta), "rb") as f:
                _, w, h, _, _ = pgm_header(f.read(512))
        except (OSError, ValueError):
            pass
        return {"name": name, "width": w, "height": h, "resolution": meta["resolution"] if meta else None,
                "origin": meta["origin"] if meta else None, "mtime": round(mtime, 3), "bytes": total, "files": files}

    def list(self):
        """Every map of the folder. A map with a file that fails the path check (a link out of the folder) is left out
        and logged: one odd file must not fail the whole library."""
        out = []
        for n in self.names():
            try:
                out.append(self.entry(n))
            except ServiceError as e:
                log("map library: skipping %s: %s" % (n, e))
        out.sort(key=lambda e: (-e["mtime"], e["name"]))
        return out

    def preview(self, name, max_px=512):
        if not os.path.isfile(self._path(name, ".yaml")):
            raise ServiceError("There is no map named %s." % name)
        try:
            with open(self._image_path(name, self._meta(name)), "rb") as f:
                w, h, pix = read_pgm(f.read())
        except OSError:
            raise ServiceError("The map %s has no image file." % name)
        except ValueError as e:
            raise ServiceError("The map image cannot be read: %s" % e)
        stride = max(1, -(-max(w, h) // max(1, int(max_px))))
        sw, sh, raw = sample_grid(w, h, pix, stride)
        return {"width": sw, "height": sh, "stride": stride, "encoding": "gray", "data": pack_cells(raw)}

    def rename(self, name, new_name):
        src = self._path(name, ".yaml")
        if not os.path.isfile(src):
            raise ServiceError("There is no map named %s." % name)
        if not valid_map_name(new_name):
            raise ServiceError("Bad new map name. Use 1 to 48 letters, digits, _ or -, starting with a letter or digit.")
        if name == new_name:
            raise ServiceError("The new name is the same as the old one.")
        if self.busy() == name:
            raise ServiceError("The map %s is being saved right now." % name)
        if any(os.path.lexists(self._path(new_name, ext)) for ext in MAP_EXTS):
            raise ServiceError("A map named %s already exists." % new_name, exists=True)
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            raise ServiceError("Cannot read the map YAML: %s" % e)
        moved = []
        try:
            for ext in MAP_EXTS:
                a = self._path(name, ext)
                if os.path.isfile(a):
                    b = self._path(new_name, ext)
                    os.rename(a, b)
                    moved.append((a, b))
            ydst = self._path(new_name, ".yaml")
            tmp = ydst + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(rewrite_yaml_image(text, new_name + ".pgm"))
            os.replace(tmp, ydst)
        except OSError as e:
            for a, b in reversed(moved):
                try:
                    os.rename(b, a)
                except OSError:
                    pass
            raise ServiceError("Rename failed: %s" % e)
        return {"name": new_name}

    def delete(self, name, confirm=False):
        if confirm is not True:
            raise ServiceError("Deleting a map needs confirm: true.")
        if not os.path.isfile(self._path(name, ".yaml")):
            raise ServiceError("There is no map named %s." % name)
        if self.busy() == name:
            raise ServiceError("The map %s is being saved right now." % name)
        deleted = []
        for ext in MAP_EXTS:
            p = self._path(name, ext)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError as e:
                    raise ServiceError("Cannot delete %s%s: %s" % (name, ext, e), deleted=deleted)
                deleted.append(name + ext)
        return {"deleted": deleted}

    def seed_demo(self, name="demo_room"):
        """Fake robot: when the folder has no map, save a fully revealed fake room so the library is not empty."""
        if self.names():
            return False
        g = FakeMapGrid()
        g.reveal_all()
        g.save(os.path.join(self.dir, name))
        return True
