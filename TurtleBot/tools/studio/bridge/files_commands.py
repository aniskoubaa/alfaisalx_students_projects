"""Bridge commands for the file browser: resolve a path safely, describe a program, read and write a
file. All paths go through the path-safety helpers first."""
from .base import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .path_describe import *  # bundle: skip


class FilesMixin:
    # ---- v1.1: path safety, files, describe, wifi
    def resolve_dir(self, d):
        """Directory argument -> real absolute path inside the home directory (not in ~/.ssh), else BridgeError."""
        p = expand_home(d, self.home, "~/robot_code")
        if "\0" in p:
            raise BridgeError("bad directory")
        real = os.path.realpath(p)
        if not home_path_ok(real, self.home):
            raise BridgeError("directory must be inside your home directory (and not ~/.ssh)")
        return real

    def resolve_file(self, d, rel):
        """(dir, real file path) for a relative name; refuses bad names, '..', and symlinks leaving home."""
        base = self.resolve_dir(d)
        if not valid_rel(rel):
            raise BridgeError("bad file name (allowed: letters, digits, _ . - and / for subfolders, max 120 characters)")
        full = os.path.realpath(os.path.join(base, rel))
        if not inside_root(full, base) or not home_path_ok(full, self.home):
            raise BridgeError("path leaves the directory or the home directory")
        return base, full

    def h_describe(self, c):
        base = self.resolve_dir(c.get("dir"))
        out = []
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                if not name.lower().endswith((".py", ".sh")) or not valid_rel(name):
                    continue
                full = os.path.realpath(os.path.join(base, name))
                if not os.path.isfile(full) or not home_path_ok(full, self.home):
                    continue
                e = describe_file(full)
                if e:
                    e["name"] = name
                    out.append(e)
        return {"dir": base, "programs": out}

    def h_read_file(self, c):
        base, full = self.resolve_file(c.get("dir"), c.get("path"))
        if not os.path.isfile(full):
            raise BridgeError("no such file: %s" % c.get("path"))
        size = os.path.getsize(full)
        if size > MAX_TEXT_BYTES:
            raise BridgeError("file is larger than 512 KB")
        with open(full, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise BridgeError("not a UTF-8 text file")
        if "\0" in text:
            raise BridgeError("not a text file")
        return {"path": c.get("path"), "text": text, "size": size, "mtime": round(os.path.getmtime(full), 1),
                "sha1": hashlib.sha1(raw).hexdigest()}

    def h_write_file(self, c):
        base, full = self.resolve_file(c.get("dir"), c.get("path"))
        text = c.get("text")
        if not isinstance(text, str):
            raise BridgeError("text must be a string")
        raw = text.encode("utf-8")
        if len(raw) > MAX_TEXT_BYTES:
            raise BridgeError("text is larger than 512 KB")
        exists = os.path.lexists(full)
        if exists and os.path.isdir(full):
            raise BridgeError("a folder with that name exists")
        if exists and not c.get("overwrite"):
            raise BridgeError("file exists (set overwrite)")
        old = None
        if exists:
            with open(full, "rb") as f:
                old = f.read()
            exp = c.get("expect_sha1")
            if exp and hashlib.sha1(old).hexdigest() != exp:
                raise BridgeError("changed on the robot since you opened it")
        if old is not None and old == raw:  # same content: no rewrite and no .bak (it would replace the older backup)
            return {"path": c.get("path"), "size": len(raw), "sha1": hashlib.sha1(raw).hexdigest(), "backup": None,
                    "unchanged": True}
        parent = os.path.dirname(full)
        os.makedirs(parent, exist_ok=True)
        mode = 0o755 if full.lower().endswith((".py", ".sh")) else 0o644
        backup = None
        if old is not None:
            backup = full + ".bak"
            with open(backup, "wb") as f:
                f.write(old)
        fd, tmp = tempfile.mkstemp(prefix=".studio_", dir=parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, full)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise BridgeError("cannot write: %s" % e)
        return {"path": c.get("path"), "size": len(raw), "sha1": hashlib.sha1(raw).hexdigest(), "backup": backup}
