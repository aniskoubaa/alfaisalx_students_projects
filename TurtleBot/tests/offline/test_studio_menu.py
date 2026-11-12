"""Offline tests of the TurtleBot Studio 2.1 robot menu page backend (TurtleBot/tools/studio/robot_bridge.py, design in
docs/DESIGN-MAPPING.md, "Robot menu file"): reading, checking and writing ~/robot_code/menu/menu.yaml with the robot's own
checker (delivery/menu_config.py).

No robot and no ROS: the bridge runs in --fake mode as a subprocess with a temporary robot home. The checker is the
repository's delivery/menu_config.py (needs PyYAML); without PyYAML the checker part is skipped with a SKIP line.
Usage: python test_studio_menu.py     (prints PASS/FAIL/SKIP, exit code = number of failures)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'tools', 'studio'))
BRIDGE = os.path.join(STUDIO_DIR, 'robot_bridge.py')
CHECKER = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery', 'menu_config.py'))
OUT = tempfile.mkdtemp(prefix='tb4_studio_menu_')
fails = 0

GOOD = """version: 1
hide: [wall_left, wall_right]
entries:
  - id: hello
    label: Hello demo
    program: ~/robot_code/programs/hello.py
    after: dock
"""
GOOD2 = GOOD.replace('Hello demo', 'Hello again')
BAD = """entries:
  - id: Bad
    label: x
"""


def check(name, cond, info=''):
    global fails
    print((('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else '')).encode('ascii', 'replace').decode(), flush=True)
    if not cond:
        fails += 1


class Proc:
    def __init__(self, checker):
        self.home = tempfile.mkdtemp(prefix='home_', dir=OUT)
        env = dict(os.environ, STUDIO_BRIDGE_FAKE='1', STUDIO_BRIDGE_HOME=self.home, PYTHONDONTWRITEBYTECODE='1',
                   STUDIO_MENU_CHECKER=checker)
        self.p = subprocess.Popen([sys.executable, '-u', BRIDGE, '--fake'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env)
        self.events, self.next_id, self.lock = [], 0, threading.Lock()
        threading.Thread(target=self._rd, daemon=True).start()
        threading.Thread(target=lambda: [None for _ in self.p.stderr], daemon=True).start()

    def _rd(self):
        for line in self.p.stdout:
            try:
                ev = json.loads(line.decode('utf-8'))
            except ValueError:
                continue
            with self.lock:
                self.events.append(ev)

    def send(self, cmd, timeout=20.0, **kw):
        self.next_id += 1
        i = self.next_id
        self.p.stdin.write((json.dumps(dict(kw, id=i, cmd=cmd)) + '\n').encode())
        self.p.stdin.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                for e in self.events:
                    if e.get('ev') == 'reply' and e.get('id') == i:
                        return e
            time.sleep(0.01)
        return {'ok': False, 'error': 'no reply (timeout)'}

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(3)
        except Exception:
            self.p.kill()


def has_yaml():
    r = subprocess.run([sys.executable, '-c', 'import yaml'], capture_output=True)
    return r.returncode == 0


# ================================================================ checker missing (like a robot without the delivery package)
b = Proc(os.path.join(OUT, 'no_such_checker.py'))
try:
    g = b.send('menu_get')
    check('menu_get answers without a checker', g.get('ok') is True, str(g)[:160])
    check('menu_get: no menu file yet', g.get('exists') is False and g.get('check') is None, str(g)[:160])
    check('menu_get: the checker is reported missing', g.get('checker_ok') is False)
    check('menu_get: names robot_code/menu/menu.yaml', str(g.get('path', '')).replace('\\', '/').endswith('robot_code/menu/menu.yaml'), str(g.get('path')))
    r = b.send('menu_put', text=GOOD, confirm=True)
    check('menu_put is refused when the checker is missing', r.get('ok') is False and 'checker' in str(r.get('error', '')).lower(), str(r)[:160])
    check('nothing was written without a checker', not os.path.exists(os.path.join(b.home, 'robot_code', 'menu', 'menu.yaml')))
finally:
    b.close()

# ================================================================ with the repository's checker
if not os.path.isfile(CHECKER):
    print('SKIP checker part: %s not found' % CHECKER)
elif not has_yaml():
    print('SKIP checker part: PyYAML is not installed (python -m pip install pyyaml)')
else:
    b = Proc(CHECKER)
    menu = os.path.join(b.home, 'robot_code', 'menu', 'menu.yaml')
    try:
        g = b.send('menu_get')
        check('menu_get: checker found', g.get('checker_ok') is True, str(g)[:160])
        r = b.send('menu_check', text=GOOD)
        check('menu_check: a good file is ok', r.get('ok') is True and r.get('check', {}).get('ok') is True, str(r)[:200])
        lay = (r.get('check') or {}).get('layout') or []
        check('menu_check: the layout puts the own entry right below Dock', lay[:3] == ['trip', 'dock', 'hello'], str(lay))
        check('menu_check: hidden entries are reported', (r.get('check') or {}).get('hide') == ['wall_left', 'wall_right'])
        check('menu_check does not write the menu file', not os.path.exists(menu))
        r = b.send('menu_check', text=BAD)
        c = r.get('check') or {}
        check('menu_check: a bad file is not ok and lists the problems', c.get('ok') is False and len(c.get('errors') or []) >= 1, str(r)[:200])
        r = b.send('menu_put', text=GOOD)
        check('menu_put without confirm is refused', r.get('ok') is False)
        r = b.send('menu_put', text=BAD, confirm=True)
        check('menu_put of a bad file is refused with the checker errors', r.get('ok') is False and 'id' in json.dumps(r).lower(), str(r)[:200])
        check('a refused file is not written', not os.path.exists(menu))
        r = b.send('menu_put', text='#' * 16001, confirm=True)
        check('menu_put of a file over 16000 characters is refused', r.get('ok') is False)
        r = b.send('menu_put', text=GOOD, confirm=True)
        check('menu_put of a good file works', r.get('ok') is True and (r.get('check') or {}).get('ok') is True, str(r)[:200])
        check('the menu file has exactly the text', os.path.isfile(menu) and open(menu, encoding='utf-8').read() == GOOD)
        check('no temporary file is left', not os.path.exists(menu + '.tmp'))
        g = b.send('menu_get')
        check('menu_get returns the text and its check', g.get('exists') is True and g.get('text') == GOOD and (g.get('check') or {}).get('ok') is True,
              str(g)[:200])
        r = b.send('menu_put', text=GOOD2, confirm=True)
        check('a second save works', r.get('ok') is True)
        check('the previous file is kept as menu.yaml.bak', os.path.isfile(menu + '.bak') and open(menu + '.bak', encoding='utf-8').read() == GOOD)
        check('the menu file has the new text', open(menu, encoding='utf-8').read() == GOOD2)
        stray = [n for n in os.listdir(os.path.dirname(menu)) if n not in ('menu.yaml', 'menu.yaml.bak')]
        check('menu_check leaves no stray files in the menu folder', not stray, str(stray))
    finally:
        b.close()

shutil.rmtree(OUT, ignore_errors=True)
print('\n%d failure(s)' % fails)
sys.exit(fails)
