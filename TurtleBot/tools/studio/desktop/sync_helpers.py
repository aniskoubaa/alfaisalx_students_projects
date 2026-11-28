"""Pure parts of the ssh config block, file sync planning and tar streaming, plus small
executable and PowerShell helpers.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip


def ssh_config_block(host, key, known_hosts, alias='turtlebot-studio', user=ROBOT_USER):
    lines = [MARK_BEGIN, 'Host ' + alias, '    HostName ' + strip_user(host), '    User ' + user,
             '    IdentityFile ' + opt_path(key), '    IdentitiesOnly yes', '    HostKeyAlias ' + PIN_ALIAS,
             '    UserKnownHostsFile ' + opt_path(known_hosts), '    StrictHostKeyChecking yes', MARK_END]
    return '\n'.join(lines) + '\n'


def insert_ssh_config_block(existing, block):
    """Add-only: append the marked block, or (only if it exists) replace our own marked block. Everything
    outside the markers is returned byte-identical. Returns (new_text, action) with action in
    'added' | 'unchanged' | 'updated'."""
    b = existing.find(MARK_BEGIN)
    e = existing.find(MARK_END, b + 1) if b >= 0 else -1
    if b >= 0 and e >= 0:
        e_end = e + len(MARK_END)
        if existing[e_end:e_end + 1] == '\n':
            e_end += 1
        if existing[b:e_end] == block:
            return existing, 'unchanged'
        return existing[:b] + block + existing[e_end:], 'updated'
    sep = '' if (not existing or existing.endswith('\n\n')) else ('\n' if existing.endswith('\n') else '\n\n')
    return existing + sep + block, 'added'


def should_skip_local(rel_parts, name):
    return any(p in SYNC_SKIP_DIRS for p in rel_parts[:-1]) or name.endswith('.pyc')


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def scan_local(root, with_sha=True):
    """{'rel/posix/path': {'size','mtime','sha1'}} - skips __pycache__, .git, logs/, *.pyc, files > 20 MB."""
    out = {}
    root = os.path.abspath(root)
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SYNC_SKIP_DIRS]
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            if fn.endswith('.pyc'):
                continue
            try:
                st = os.stat(full)
                if st.st_size > SYNC_MAX_BYTES or not os.path.isfile(full):
                    continue
                out[rel] = {'size': st.st_size, 'mtime': st.st_mtime, 'sha1': sha1_file(full) if with_sha else None}
            except OSError:
                continue
    return out


def plan_sync(local, remote, direction):
    """local/remote: {rel: {'size','sha1'}} (remote sha1 may be None for big files). Returns a plan dict.
    'transfer' = files to send in the given direction (new or changed); 'extra' = files only on the receiving side."""
    def same(a, b):
        if a.get('sha1') and b.get('sha1'):
            return a['sha1'] == b['sha1']
        return a.get('size') == b.get('size')
    src, dst = (local, remote) if direction == 'up' else (remote, local)
    new, changed, same_n = [], [], 0
    for rel in sorted(src):
        if rel not in dst:
            new.append(rel)
        elif same(src[rel], dst[rel]):
            same_n += 1
        else:
            changed.append(rel)
    extra = sorted(r for r in dst if r not in src)
    return {'new': new, 'changed': changed, 'same': same_n, 'transfer': new + changed, 'extra': extra}


def tar_mode(rel):
    return 0o755 if rel.endswith(('.py', '.sh')) else 0o644


def safe_member_path(dest, name):
    """Destination path for a tar member, or None if it would escape dest."""
    if not name or name.startswith('/') or '\\' in name or re.match(r'^[A-Za-z]:', name):
        return None
    parts = name.split('/')
    if any(p in ('..', '') for p in parts if p != '.'):
        return None
    parts = [p for p in parts if p != '.']
    if not parts:
        return None
    full = os.path.abspath(os.path.join(dest, *parts))
    root = os.path.abspath(dest)
    return full if full.startswith(root + os.sep) else None


def extract_tar_stream(fileobj, dest):
    """Extract regular files from a tar stream into dest (no links, no devices, no escapes). Returns names."""
    got = []
    with tarfile.open(fileobj=fileobj, mode='r|') as tf:
        for m in tf:
            if not m.isreg():
                continue
            target = safe_member_path(dest, m.name)
            if target is None:
                raise ValueError('unsafe path in archive: %r' % m.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            src = tf.extractfile(m)
            with open(target, 'wb') as f:
                shutil.copyfileobj(src, f)
            got.append(m.name.lstrip('./'))
    return got


def write_tar_stream(fileobj, root, rels):
    with tarfile.open(fileobj=fileobj, mode='w|', format=tarfile.GNU_FORMAT) as tf:
        for rel in rels:
            def flt(ti, rel=rel):
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = ''
                ti.mode = tar_mode(rel)
                return ti
            tf.add(os.path.join(root, *rel.split('/')), arcname=rel, recursive=False, filter=flt)


def expand_remote(path, home):
    if path == '~':
        return home
    if path.startswith('~/'):
        return os.path.join(home, *path[2:].split('/'))
    return path


def find_exe(name):
    if IS_WIN:
        p = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'OpenSSH', name + '.exe')
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def hide_flags():
    if IS_WIN:
        return {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}
