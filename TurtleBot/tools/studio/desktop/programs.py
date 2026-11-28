"""The program catalog (programs.json and templates) and the decision whether a run needs
the motion safety checks. ProgramsMixin serves them to the page.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip
from .notices import *  # bundle: skip
from .sync_helpers import *  # bundle: skip
from .window import *  # bundle: skip
from .wifi_scripts import *  # bundle: skip
from .laptop_network import *  # bundle: skip


def list_templates(templates_dir):
    try:
        return sorted(n for n in os.listdir(templates_dir)
                      if TEMPLATE_NAME_RE.match(n) and os.path.isfile(os.path.join(templates_dir, n)))
    except OSError:
        return []


def load_catalog(path, templates_dir):
    """programs.json + templates/ -> dict for GET /api/catalog. Missing or broken files give an empty catalog."""
    out = {'ok': True, 'version': 1, 'programs': {}, 'templates': [], 'catalog_found': False}
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get('programs'), dict):
            out['programs'] = d['programs']
            out['version'] = d.get('version', 1)
            out['catalog_found'] = True
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        out['error'] = 'programs.json could not be read: %s' % e
    for n in list_templates(templates_dir):
        out['templates'].append({'name': n, 'entry': out['programs'].get(n)})
    return out


def decide_motion(base, catalog_programs, user_files, described):
    """Motion decision for `run`. described: the bridge `describe` entry for the file, 'unavailable' if describe
    failed, or None if the file was not listed. Returns (motion, reasons)."""
    reasons = []
    if base in MOTION_FILES:
        reasons.append('known motion program')
    if base in (user_files or []):
        reasons.append('marked as moving in settings')
    ent = catalog_programs.get(base) if isinstance(catalog_programs, dict) else None
    if isinstance(ent, dict) and ent.get('moves'):
        reasons.append('catalog says it moves the robot')
    if isinstance(described, dict) and described.get('moves_detected'):
        reasons.append('code uses motion topics/actions: %s' % ', '.join(map(str, described.get('moves_reasons') or [])))
    if described == 'unavailable' and not isinstance(ent, dict) and not reasons:
        reasons.append('unknown file and the robot could not check it (treated as moving)')
    return bool(reasons), reasons


class ProgramsMixin:
    # ---------------------------------------------------------------- v1.1: catalog, templates, motion decision
    def catalog(self):
        return load_catalog(self.catalog_path, self.templates_dir)

    def template_text(self, name):
        if not TEMPLATE_NAME_RE.match(name or '') or name not in list_templates(self.templates_dir):
            return None
        try:
            with open(os.path.join(self.templates_dir, name), 'rb') as f:
                return f.read().decode('utf-8')
        except (OSError, UnicodeDecodeError):
            return None

    def motion_for_run(self, cmd):
        """Sets cmd['motion'] (never lowers an explicit True) and returns the reasons."""
        path = str(cmd.get('path', ''))
        base = os.path.basename(path)
        cat = self.catalog()['programs']
        reasons_known = decide_motion(base, cat, self.settings.get('motion_files'), None)
        if reasons_known[0] or cmd.get('motion'):
            cmd['motion'] = True
            return reasons_known[1] or ['requested']
        described = None
        try:
            r = self.bridge.request({'cmd': 'describe', 'dir': cmd.get('dir') or DEFAULT_REMOTE_DIR}, 10)
            if r.get('ok'):
                described = next((p for p in r.get('programs', []) if p.get('name') == path or p.get('name') == base), None)
            else:
                described = 'unavailable'
        except BridgeError:
            described = 'unavailable'
        motion, reasons = decide_motion(base, cat, self.settings.get('motion_files'), described)
        cmd['motion'] = bool(motion)
        return reasons
