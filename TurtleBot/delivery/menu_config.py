#!/usr/bin/env python3
"""The menu file of the front-panel menu: lets the lab hide some built-in entries and add its own entries that start a
program under ~/robot_code. Pure checking code (no ROS, no robot), used by menu_core.py on the robot and as a
command line check on any computer:

    python3 menu_config.py --check menu.yaml            # prints OK and the resulting menu, or the problems (exit 1)
    python3 menu_config.py --check menu.yaml --json     # the same as JSON (for TurtleBot Studio)

File (YAML), default path ~/robot_code/menu/menu.yaml, env DELIVERY_MENU_FILE replaces it. It lives OUTSIDE the deployed
delivery folder, so a deploy never overwrites it. Format and examples: delivery/README.md section 9 ("Your own menu
entries") and delivery/menu.example.yaml.

    version: 1                      # optional, must be 1
    hide: [undock, help]            # only undock, wall_left, wall_right, help can be hidden
    entries:                        # at most 8 own entries
      - id: lights                  # a-z, 0-9, _ ; not a built-in id
        label: Lights demo          # 1 to 17 characters, printable ASCII (18 per line, one is the ">" cursor)
        program: ~/robot_code/programs/lights.py     # .py (python3) or .sh (bash), must stay under ~/robot_code
        args: ["--fast", 3]         # optional, at most 10, passed as they are (no shell)
        confirm: false              # true: ask "1 = Yes / 2 = No" first
        moves: false                # true: the program drives the robot; always asks first
        undocks: false              # true: a moving program that undocks the robot itself (allowed while docked)
        timeout: 300                # seconds, 1 to 3600; then the program is stopped
        after: dock                 # where it goes: below this entry (built-in id or another own id); default: the end

Locked (the file cannot change them): the trip entry stays first, Dock, EStop and Power stay, names and order of
the built-in entries stay. Any error rejects the WHOLE file and the menu is today's menu, so a typo can never
half-apply.
"""
import argparse
import json
import os
import posixpath
import re
import sys

BUILTIN_IDS = ('trip', 'dock', 'undock', 'estop', 'wall_left', 'wall_right', 'power', 'help')   # = menu_core.ENTRIES
LOCKED = ('trip', 'dock', 'estop', 'power')
HIDEABLE = ('undock', 'wall_left', 'wall_right', 'help')
BUILTIN_LABELS = ('Go to food court', 'Back to the lab', 'Dock', 'Undock', 'EStop', 'Wall Follow Left',
                  'Wall Follow Right', 'Power', 'Help')   # an own entry may not look like one of them
DISPLAY_CHARS = 18
MAX_LABEL = DISPLAY_CHARS - 1     # one character of every menu line is the ">" cursor
MAX_ENTRIES = 8
MAX_ARGS = 10
MAX_ARG_CHARS = 200
MAX_PROGRAM_CHARS = 200
MAX_FILE_CHARS = 16000
DEFAULT_TIMEOUT_S = 300
MAX_TIMEOUT_S = 3600
DEFAULT_MENU_FILE = '~/robot_code/menu/menu.yaml'
ROBOT_CODE = 'robot_code'
PROGRAM_SUFFIXES = ('.py', '.sh')
TOP_KEYS = ('version', 'hide', 'entries')
ENTRY_KEYS = ('id', 'label', 'program', 'args', 'confirm', 'moves', 'undocks', 'timeout', 'after')
_ID = re.compile(r'^[a-z][a-z0-9_]{0,23}$')


class Result:
    """What parse() found. ok: usable. errors: why not (strings). warnings: allowed but changed (strings).
    custom: {id: entry dict} in file order. hide: list of hidden built-in ids."""

    def __init__(self):
        self.errors, self.warnings = [], []
        self.custom, self.hide = {}, []

    @property
    def ok(self):
        return not self.errors

    def layout(self):
        """The keys of the menu, top to bottom: built-in ids and own ids, hidden ones left out. Today's menu when the
        file is invalid."""
        if self.errors:
            return list(BUILTIN_IDS)
        children = {}
        for key, entry in self.custom.items():
            children.setdefault(entry['after'], []).append(key)
        out = []

        def emit(key):
            if key not in self.hide:
                out.append(key)
            for child in children.get(key, []):
                emit(child)
        for key in BUILTIN_IDS:
            emit(key)
        return out


def menu_file_from(environ, home):
    """The menu file: env DELIVERY_MENU_FILE (with ~ expanded), else ~/robot_code/menu/menu.yaml."""
    value = environ.get('DELIVERY_MENU_FILE') or DEFAULT_MENU_FILE
    if value.startswith('~'):
        value = home.rstrip('/') + value[1:]
    return value


def program_path(rel, home):
    """Absolute path of an own program from the relative path stored by parse()."""
    return home.rstrip('/') + '/' + ROBOT_CODE + '/' + rel


def inside_robot_code(real_path, real_root):
    """True when the (already resolved) path is a file below the (already resolved) robot_code folder."""
    root = real_root.rstrip('/') + '/'
    return real_path.startswith(root) and len(real_path) > len(root)


def command(path, args):
    """The command line of an own program: python3 for .py, bash for .sh, then the args. Never a shell string."""
    return ['bash' if path.endswith('.sh') else 'python3', path, *args]


def screen_note(errors):
    """Lines for the display at start: that the file was rejected and the first reason, cut to 18 characters."""
    lines = ['Menu file error']
    words = ' '.join(str(errors[0] if errors else 'see menu.log').split())
    lines += [words[i:i + DISPLAY_CHARS] for i in range(0, len(words), DISPLAY_CHARS)][:3]
    return lines + ['Standard menu']


# ---------------------------------------------------------------- checking
def _relative_program(value, home):
    """The program path relative to ~/robot_code, or (None, reason)."""
    if not isinstance(value, str) or not value.strip():
        return None, 'program must be a path'
    if len(value) > MAX_PROGRAM_CHARS or '\x00' in value or '\\' in value:
        return None, 'program: use / in paths, at most 200 characters'
    value = value.strip()
    root = home.rstrip('/') + '/' + ROBOT_CODE
    if value.startswith('~'):
        if not value.startswith('~/' + ROBOT_CODE + '/'):
            return None, 'program must be under ~/robot_code'
        rel = value[len('~/' + ROBOT_CODE + '/'):]
    elif value.startswith('/'):
        if not posixpath.normpath(value).startswith(root + '/'):
            return None, 'program must be under ~/robot_code'
        rel = posixpath.normpath(value)[len(root) + 1:]
    else:
        rel = value
    rel = posixpath.normpath(rel)
    if rel in ('.', '') or rel == '..' or rel.startswith('../') or rel.startswith('/'):
        return None, 'program must be a file under ~/robot_code'
    if not rel.endswith(PROGRAM_SUFFIXES):
        return None, 'program must be a .py or .sh file'
    return rel, None


def _entry(raw, index, home, errors, warnings):
    name = f'entry {index + 1}'
    if not isinstance(raw, dict):
        errors.append(f'{name}: must be a mapping (id, label, program ...)')
        return None
    for key in raw:
        if key not in ENTRY_KEYS:
            errors.append(f'{name}: unknown key "{key}"')
    ident = raw.get('id')
    if not isinstance(ident, str) or not _ID.match(ident):
        errors.append(f'{name}: id must be a-z, 0-9, _ (start with a letter, max 24)')
        ident = None
    else:
        name = f'entry "{ident}"'
        if ident in BUILTIN_IDS:
            errors.append(f'{name}: this is a built-in entry (locked), use another id')
    label = raw.get('label')
    if not isinstance(label, str) or not label.strip():
        errors.append(f'{name}: label is missing')
    else:
        label = label.strip()
        if len(label) > MAX_LABEL:
            errors.append(f'{name}: label is {len(label)} characters, the longest is {MAX_LABEL}')
        elif not all(' ' <= c <= '~' for c in label):
            errors.append(f'{name}: label must be plain ASCII characters')
        elif label.lower() in [x.lower() for x in BUILTIN_LABELS]:
            errors.append(f'{name}: label "{label}" is the name of a built-in entry')
    rel, why = _relative_program(raw.get('program'), home)
    if why:
        errors.append(f'{name}: {why}')
    args = raw.get('args', [])
    if not isinstance(args, list) or len(args) > MAX_ARGS:
        errors.append(f'{name}: args must be a list of at most {MAX_ARGS}')
        args = []
    else:
        text = []
        for a in args:
            if (isinstance(a, bool) or not isinstance(a, (str, int, float)) or len(str(a)) > MAX_ARG_CHARS
                    or '\x00' in str(a)):
                errors.append(f'{name}: every arg must be a short text or number')
                break
            text.append(str(a))
        args = text
    flags = {}
    for key in ('confirm', 'moves', 'undocks'):
        flags[key] = raw.get(key, False)
        if not isinstance(flags[key], bool):
            errors.append(f'{name}: {key} must be true or false')
            flags[key] = False
    timeout = raw.get('timeout', DEFAULT_TIMEOUT_S)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT_S:
        errors.append(f'{name}: timeout must be a whole number of seconds, 1 to {MAX_TIMEOUT_S}')
        timeout = DEFAULT_TIMEOUT_S
    after = raw.get('after', BUILTIN_IDS[-1])
    if not isinstance(after, str):
        errors.append(f'{name}: after must be an entry id')
        after = BUILTIN_IDS[-1]
    if flags['undocks'] and not flags['moves']:
        flags['moves'] = True
    if flags['moves'] and not flags['confirm']:
        if raw.get('confirm') is False or 'confirm' in raw:
            warnings.append(f'{name}: moves is true, so it always asks 1 = Yes / 2 = No (confirm false is ignored)')
        flags['confirm'] = True
    if ident is None:
        return None
    return {'id': ident, 'label': label if isinstance(label, str) else '', 'program': rel, 'args': args,
            'confirm': flags['confirm'], 'moves': flags['moves'], 'undocks': flags['undocks'], 'timeout': timeout,
            'after': after}


def parse(text, home='~'):
    """Check the text of a menu file. Returns a Result. home is the robot user's home folder (to accept a full path of
    a program)."""
    res = Result()
    if len(text) > MAX_FILE_CHARS:
        res.errors.append(f'file is too long (over {MAX_FILE_CHARS} characters)')
        return res
    try:
        import yaml
    except ImportError:
        res.errors.append('PyYAML is not installed (python3-yaml)')
        return res
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, 'problem_mark', None)
        where = f' at line {mark.line + 1}' if mark is not None else ''
        res.errors.append(f'not valid YAML{where}: {str(getattr(e, "problem", e)).strip()[:80]}')
        return res
    if data is None:
        return res
    if not isinstance(data, dict):
        res.errors.append('the file must be a mapping (version, hide, entries)')
        return res
    for key in data:
        if key not in TOP_KEYS:
            res.errors.append(f'unknown key "{key}" (allowed: {", ".join(TOP_KEYS)})')
    if 'version' in data and (isinstance(data['version'], bool) or data['version'] != 1):
        res.errors.append('version must be 1')
    hide = data.get('hide') or []
    if not isinstance(hide, list):
        res.errors.append('hide must be a list')
        hide = []
    for h in hide:
        if h in LOCKED:
            res.errors.append(f'hide: "{h}" is locked and cannot be hidden')
        elif h not in HIDEABLE:
            res.errors.append(f'hide: unknown entry "{h}" (can hide: {", ".join(HIDEABLE)})')
    res.hide = [h for h in hide if h in HIDEABLE]
    raw_entries = data.get('entries') or []
    if not isinstance(raw_entries, list):
        res.errors.append('entries must be a list')
        raw_entries = []
    if len(raw_entries) > MAX_ENTRIES:
        res.errors.append(f'at most {MAX_ENTRIES} own entries')
    for i, raw in enumerate(raw_entries[:MAX_ENTRIES]):
        entry = _entry(raw, i, home, res.errors, res.warnings)
        if entry is None:
            continue
        if entry['id'] in res.custom:
            res.errors.append(f'id "{entry["id"]}" is used twice')
        elif entry['label'].lower() in [e['label'].lower() for e in res.custom.values()]:
            res.errors.append(f'label "{entry["label"]}" is used twice')
        else:
            res.custom[entry['id']] = entry
    _check_places(res)
    return res


def _check_places(res):
    """Every 'after' must lead back to a built-in entry: no unknown id, no loop."""
    for key, entry in res.custom.items():
        seen, at = {key}, entry['after']
        while at in res.custom:
            if at in seen:
                res.errors.append(f'entry "{key}": after leads in a loop')
                break
            seen.add(at)
            at = res.custom[at]['after']
        else:
            if at not in BUILTIN_IDS:
                res.errors.append(f'entry "{key}": after "{at}" is not an entry id')


# ---------------------------------------------------------------- command line
def preview(res):
    """The menu as the display shows it: (key, label) pairs. The first entry is shown for a docked robot."""
    labels = {'trip': 'Go to food court', 'dock': 'Dock', 'undock': 'Undock', 'estop': 'EStop',
              'wall_left': 'Wall Follow Left', 'wall_right': 'Wall Follow Right', 'power': 'Power', 'help': 'Help'}
    labels.update({k: e['label'] for k, e in res.custom.items()})
    return [(k, labels[k]) for k in res.layout()]


def main(argv=None):
    p = argparse.ArgumentParser(description='Check a menu file of the front-panel menu (no robot needed).')
    p.add_argument('--check', metavar='FILE', required=True, help='the YAML file to check')
    p.add_argument('--home', default=None, help='home folder of the robot user (default: this user\'s home)')
    p.add_argument('--json', action='store_true', help='print the result as JSON')
    args = p.parse_args(argv)
    home = (args.home or os.path.expanduser('~')).replace('\\', '/')
    try:
        with open(args.check, encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        res, text = Result(), None
        res.errors.append(f'file not found: {args.check}')
    except (OSError, UnicodeDecodeError) as e:
        res, text = Result(), None
        res.errors.append(f'cannot read the file: {e}')
    if text is not None:
        res = parse(text, home)
    rows = preview(res)
    if args.json:
        print(json.dumps({'ok': res.ok, 'errors': res.errors, 'warnings': res.warnings, 'hide': res.hide,
                          'layout': res.layout(), 'labels': dict(rows), 'custom': res.custom}, indent=2))
    elif res.ok:
        noun = 'entry' if len(res.custom) == 1 else 'entries'
        print(f'OK: {len(res.custom)} own {noun}, hidden: {", ".join(res.hide) or "none"}')
        for w in res.warnings:
            print('note: ' + w)
        print('Menu (top to bottom):')
        for key, label in rows:
            print(f'  {label}' + ('' if key in BUILTIN_IDS else f'   [own entry {key}]'))
    else:
        print('INVALID: the robot would show the standard menu')
        for e in res.errors:
            print('  - ' + e)
    return 0 if res.ok else 1


if __name__ == '__main__':
    sys.exit(main())
