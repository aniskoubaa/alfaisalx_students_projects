"""Unit tests of MenuService / MenuChecker of the TurtleBot Studio robot bridge
(TurtleBot/tools/studio/robot_bridge.py, design in docs/DESIGN-MAPPING.md section 4, Robot menu file).
No robot, no ROS, no checker subprocess for MenuService (a scripted fake checker is used).
Usage: python test_studio_menu_unit.py     (prints PASS/FAIL, exit code = number of failures)
"""
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
sys.path.insert(0, STUDIO_DIR)
import robot_bridge as rb  # noqa: E402

fails = 0
OUT = tempfile.mkdtemp(prefix='tb4_menu_unit_')
GOOD = {'ok': True, 'errors': [], 'warnings': [], 'hide': [], 'layout': ['trip', 'dock'], 'labels': {}, 'custom': []}
BAD = {'ok': False, 'errors': ['entry 1: id must be lowercase', 'entry 1: program missing', 'c', 'd'], 'warnings': []}


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode(), flush=True)
    if not cond:
        fails += 1


class FakeChecker:
    """checker_ok() and check_file(path) like MenuChecker; answers come from `script` (a function of the file text)."""

    def __init__(self, script=None, present=True):
        self.script = script or (lambda text: GOOD)
        self.present = present
        self.seen = []

    def checker_ok(self):
        return self.present

    def check_file(self, path):
        if not self.present:
            raise rb.ServiceError('menu checker not found at /x; deploy the delivery package to the robot (delivery/tools/deploy.py)')
        with open(path, encoding='utf-8', newline='') as f:
            text = f.read()
        self.seen.append((path, text))
        r = self.script(text)
        if isinstance(r, Exception):
            raise r
        return r


def new_home():
    return tempfile.mkdtemp(prefix='home_', dir=OUT)


def refused(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except rb.ServiceError as e:
        return e
    return None


def listing(home):
    d = os.path.join(home, 'robot_code', 'menu')
    return sorted(os.listdir(d)) if os.path.isdir(d) else None


def tmp_dirs():
    return sorted(n for n in os.listdir(tempfile.gettempdir()) if n.startswith('studio_menu_'))


# ---------------------------------------------------------------- pure helpers
check('parse_check_json accepts a checker answer', rb.parse_check_json('{"ok": true, "errors": []}') == {'ok': True, 'errors': []})
check('parse_check_json rejects bad JSON', rb.parse_check_json('not json') is None and rb.parse_check_json('') is None)
check('parse_check_json rejects JSON without a boolean ok', rb.parse_check_json('[1]') is None and rb.parse_check_json('{"ok": 1}') is None)
check('menu_error_text joins the first three errors', rb.menu_error_text(BAD) == 'the menu file is not valid: entry 1: id must be lowercase; entry 1: program missing; c')
old = os.environ.pop('STUDIO_MENU_CHECKER', None)
try:
    check('checker path default', rb.menu_checker_path('/h') == os.path.join('/h', 'robot_code', 'delivery', 'menu_config.py'))
    os.environ['STUDIO_MENU_CHECKER'] = '/elsewhere/mc.py'
    check('checker path from the environment', rb.menu_checker_path('/h') == '/elsewhere/mc.py')
finally:
    os.environ.pop('STUDIO_MENU_CHECKER', None)
    if old is not None:
        os.environ['STUDIO_MENU_CHECKER'] = old

# ---------------------------------------------------------------- MenuChecker with scripts as the checker
h = new_home()
mc = rb.MenuChecker(h, os.path.join(OUT, 'nope.py'))
check('checker_ok is False for a missing file', mc.checker_ok() is False)
e = refused(mc.check_file, os.path.join(OUT, 'x.yaml'))
check('missing checker error names the path and deploy', e is not None and 'not found at' in str(e) and 'deploy' in str(e), str(e))


def script(body):
    p = tempfile.mktemp(suffix='.py', dir=OUT)
    with open(p, 'w') as f:
        f.write(body)
    return rb.MenuChecker(h, p)


c1 = script('import sys, json\nprint(json.dumps({"ok": False, "errors": ["e"]}))\nsys.exit(1)\n')
r = c1.check_file('f')
check('exit code 1 still returns the JSON', r == {'ok': False, 'errors': ['e']}, str(r))
c2 = script('import sys\nsys.stderr.write("boom\\nlast line\\n")\nsys.exit(2)\n')
e = refused(c2.check_file, 'f')
check('other exit code: menu checker failed + last stderr line', e is not None and str(e) == 'menu checker failed: last line', str(e))
c3 = script('print("hello")\n')
e = refused(c3.check_file, 'f')
check('bad JSON on exit 0 is an error', e is not None and str(e).startswith('menu checker failed'), str(e))

# ---------------------------------------------------------------- MenuService.get
h = new_home()
ck = FakeChecker()
svc = rb.MenuService(h, ck)
g = svc.get()
check('get: no file', g['exists'] is False and g['text'] == '' and g['check'] is None and g['checker_ok'] is True, str(g))
check('get: path ends with robot_code/menu/menu.yaml', g['path'].replace('\\', '/').endswith('robot_code/menu/menu.yaml'))
g = rb.MenuService(h, FakeChecker(present=False)).get()
check('get: checker missing is reported, no error', g['checker_ok'] is False and g['check'] is None)

# ---------------------------------------------------------------- put refusals
TXT = 'version: 1\nentries: []\n'
for label, kw in (('no confirm', dict(text=TXT, confirm=None)), ('confirm "yes"', dict(text=TXT, confirm='yes')),
                  ('confirm 1', dict(text=TXT, confirm=1)), ('text not a str', dict(text=b'x', confirm=True)),
                  ('text None', dict(text=None, confirm=True)), ('text too long', dict(text='#' * (rb.MENU_MAX_CHARS + 1), confirm=True))):
    e = refused(svc.put, **kw)
    check('put refused: ' + label, e is not None)
check('put at exactly the limit is accepted', refused(svc.put, '#' * rb.MENU_MAX_CHARS, True) is None)
h = new_home()
svc = rb.MenuService(h, FakeChecker())
check('refusals leave no folder behind', listing(h) is None)

# checker missing
svc = rb.MenuService(h, FakeChecker(present=False))
e = refused(svc.put, TXT, True)
check('put refused when the checker is missing', e is not None and 'checker' in str(e) and listing(h) is None, str(e))
e = refused(svc.check, TXT)
check('check refused when the checker is missing', e is not None and 'checker' in str(e))

# invalid text
svc = rb.MenuService(h, FakeChecker(lambda t: BAD))
e = refused(svc.put, TXT, True)
check('put of an invalid text: error with the first errors', e is not None and str(e) == rb.menu_error_text(BAD), str(e))
check('put of an invalid text: reply carries check', e is not None and e.extra.get('check') == BAD)
check('put of an invalid text writes nothing', listing(h) is None)

# checker failures
for label, res in (('timeout', rb.ServiceError('menu checker failed: timed out after 20 s')),
                   ('bad JSON', rb.ServiceError('menu checker failed: its answer was not valid JSON'))):
    svc = rb.MenuService(h, FakeChecker(lambda t, r=res: r))
    e = refused(svc.put, TXT, True)
    check('put when the checker fails (%s)' % label, e is not None and str(e).startswith('menu checker failed') and listing(h) is None, str(e))

# ---------------------------------------------------------------- put: good path, .bak, no stray files
before = tmp_dirs()
ck = FakeChecker()
svc = rb.MenuService(h, ck)
r = svc.put(TXT, True)
menu = os.path.join(h, 'robot_code', 'menu', 'menu.yaml')
check('put creates the folder and the file with exactly the text', open(menu, encoding='utf-8', newline='').read() == TXT)
check('put returns path and check', r['path'] == os.path.realpath(menu) and r['check'] == GOOD, str(r))
check('first save: no .bak, no .tmp', listing(h) == ['menu.yaml'], str(listing(h)))
check('the checked file was outside the menu folder', ck.seen and not os.path.realpath(ck.seen[0][0]).startswith(os.path.realpath(os.path.dirname(menu))))
TXT2 = 'version: 1\r\nentries: []\r\n# é\r\n'
svc.put(TXT2, True)
check('second save: previous kept as .bak', open(menu + '.bak', encoding='utf-8', newline='').read() == TXT)
check('CRLF and non-ASCII are written exactly', open(menu, 'rb').read() == TXT2.encode('utf-8'))
check('only menu.yaml and menu.yaml.bak remain', listing(h) == ['menu.yaml', 'menu.yaml.bak'], str(listing(h)))
check('temporary check folders are removed', tmp_dirs() == before, str(set(tmp_dirs()) - set(before)))
g = svc.get()
check('get returns the text and the check', g['exists'] and g['text'] == TXT2.replace('\r\n', '\n') or g['text'] == TXT2)
check('get check comes from the checker', g['check'] == GOOD)

# menu_check does not touch the menu folder
n = len(ck.seen)
r = svc.check(TXT)
check('check returns the checker JSON', r == {'check': GOOD})
check('check leaves the menu folder alone', listing(h) == ['menu.yaml', 'menu.yaml.bak'] and tmp_dirs() == before)
e = refused(svc.check, 5)
check('check refuses a non-string', e is not None)

# oversized existing file is not read
h2 = new_home()
os.makedirs(os.path.join(h2, 'robot_code', 'menu'))
with open(os.path.join(h2, 'robot_code', 'menu', 'menu.yaml'), 'w') as f:
    f.write('#' * (rb.MENU_MAX_CHARS * 2 + 1))
e = refused(rb.MenuService(h2, FakeChecker()).get)
check('get refuses a file over 2 x limit', e is not None, str(e))

# menu.yaml is a directory
h3 = new_home()
os.makedirs(os.path.join(h3, 'robot_code', 'menu', 'menu.yaml'))
svc3 = rb.MenuService(h3, FakeChecker())
e = refused(svc3.put, TXT, True)
check('put refused when menu.yaml is a directory', e is not None and os.path.isdir(os.path.join(h3, 'robot_code', 'menu', 'menu.yaml')), str(e))
check('nothing else was created next to it', listing(h3) == ['menu.yaml'], str(listing(h3)))
e = refused(svc3.get)
check('get refused when menu.yaml is a directory', e is not None)

shutil.rmtree(OUT, ignore_errors=True)
print('\n%d failure(s)' % fails)
sys.exit(fails)
