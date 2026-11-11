"""Offline tests of the menu file (TurtleBot/delivery/menu_config.py): the format, the locked rules, the layout and the
command line check. No robot and no ROS needed. Usage: python test_delivery_menu_config.py
"""
import os
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery'))
sys.path.insert(0, DELIVERY)
import menu_config as cfg  # noqa: E402
import menu_core as mc  # noqa: E402

fails = 0
count = 0
HOME = '/home/u'


def check(name, cond, info=''):
    global fails, count
    count += 1
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


def parse(text):
    return cfg.parse(text, HOME)


def ok(text):
    r = parse(text)
    return r if r.ok else None


def errs(text):
    return ' | '.join(parse(text).errors)


ONE = '''
entries:
  - id: lights
    label: Lights demo
    program: ~/robot_code/programs/lights.py
'''

# ---------------------------------------------------------------- the built-in list
check('builtin ids are the ids of menu_core.ENTRIES, in the same order', tuple(cfg.BUILTIN_IDS) == mc.ENTRIES)
check('locked and hideable together are all built-in ids, none twice',
      sorted(cfg.LOCKED + cfg.HIDEABLE) == sorted(cfg.BUILTIN_IDS))
check('locked: trip, dock, estop, power. hideable: undock, wall follow left and right, help',
      set(cfg.LOCKED) == {'trip', 'dock', 'estop', 'power'} and set(cfg.HIDEABLE) == {'undock', 'wall_left', 'wall_right', 'help'})

# ---------------------------------------------------------------- empty and minimal files
r = parse('')
check('empty file: valid, today\'s menu', r.ok and r.layout() == list(mc.ENTRIES), r.errors)
r = parse('version: 1\nentries: []\nhide: []\n')
check('no entries, nothing hidden: valid, today\'s menu', r.ok and r.layout() == list(mc.ENTRIES))
r = parse(ONE)
check('one custom entry: valid, goes to the end by default', r.ok and r.layout() == list(mc.ENTRIES) + ['lights'], r.errors)
e = r.custom['lights']
check('defaults: no args, no confirm, does not move, default timeout, program stored relative to robot_code',
      e['args'] == [] and e['confirm'] is False and e['moves'] is False and e['undocks'] is False
      and e['timeout'] == cfg.DEFAULT_TIMEOUT_S and e['program'] == 'programs/lights.py', e)

# ---------------------------------------------------------------- hide
r = parse('hide: [undock, wall_left, wall_right, help]')
check('hide: undock, wall follow and help can be hidden, the order of the rest stays',
      r.ok and r.layout() == ['trip', 'dock', 'estop', 'power'], r.layout())
for locked in ('trip', 'dock', 'estop', 'power'):
    check(f'hide: {locked} is locked and the file is rejected', not parse(f'hide: [{locked}]').ok and 'locked' in errs(f'hide: [{locked}]'),
          errs(f'hide: [{locked}]'))
check('hide: an unknown name is an error', not parse('hide: [banana]').ok)
check('hide: must be a list', not parse('hide: undock').ok)

# ---------------------------------------------------------------- ids and labels
check('id: a built-in id cannot be redefined (locked)', not parse(ONE.replace('lights', 'dock', 1)).ok
      and 'built-in' in errs(ONE.replace('id: lights', 'id: dock')))
check('id: lower-case letters, digits and underscore only', not parse(ONE.replace('id: lights', 'id: Bad-Id')).ok)
check('id: missing', not parse('entries:\n  - label: x\n    program: a.py\n').ok)
check('id: twice is an error', not parse(ONE + ONE.split('entries:')[1]).ok and 'twice' in errs(ONE + ONE.split('entries:')[1]))
check('label: 17 characters is the longest (18 per line, one is the cursor)',
      ok(ONE.replace('Lights demo', 'a' * 17)) is not None and ok(ONE.replace('Lights demo', 'a' * 18)) is None)
check('label: empty, missing or non-ASCII is an error', ok(ONE.replace('Lights demo', "''")) is None
      and ok(ONE.replace('    label: Lights demo\n', '')) is None and ok(ONE.replace('Lights demo', 'Lichter \u00fc')) is None)
check('label: cannot copy a built-in label (any case) or a second custom label',
      ok(ONE.replace('Lights demo', 'dock')) is None and ok(ONE.replace('Lights demo', 'go to food court')) is None
      and ok(ONE + '  - id: l2\n    label: LIGHTS DEMO\n    program: a.py\n') is None)

# ---------------------------------------------------------------- program
def prog(value):
    return parse(f'entries:\n  - id: p\n    label: P\n    program: "{value}"\n')


check('program: ~/robot_code/x.py, relative x.py and the full home path all give the same file',
      all(prog(v).ok and prog(v).custom['p']['program'] == 'x/y.py'
          for v in ('~/robot_code/x/y.py', 'x/y.py', './x/y.py', HOME + '/robot_code/x/y.py', '~/robot_code/x/../x/y.py')))
for bad in ('/etc/passwd', '../x.py', '~/robot_code/../x.py', '~/x.py', '~/robot_code/a/../../b.py', '/home/other/robot_code/x.py',
            HOME + '/robot_code/../.ssh/x.py', 'C:\\\\tools\\\\x.py', '~/robot_code/', '~/robot_code', 'x.txt', 'x'):
    check(f'program: {bad!r} is refused', not prog(bad).ok, errs(f'entries:\n  - id: p\n    label: P\n    program: "{bad}"\n'))
check('program: a .sh file is accepted', prog('run.sh').ok)
check('program: missing or not a string', not parse('entries:\n  - id: p\n    label: P\n').ok
      and not parse('entries:\n  - id: p\n    label: P\n    program: 5\n').ok)

# ---------------------------------------------------------------- args, flags, timeout
def entry(extra):
    return parse('entries:\n  - id: p\n    label: P\n    program: a.py\n' + extra)


check('args: a list of strings and numbers, kept as text', entry('    args: ["--fast", 3, 1.5]\n').ok
      and entry('    args: ["--fast", 3, 1.5]\n').custom['p']['args'] == ['--fast', '3', '1.5'])
check('args: not a list, a nested list or more than 10 is an error', not entry('    args: x\n').ok
      and not entry('    args: [[1]]\n').ok and not entry('    args: [' + ','.join('a' * 1 for _ in range(11)) + ']\n').ok)
check('args: one longer than 200 characters is an error', not entry('    args: ["' + 'a' * 201 + '"]\n').ok)
check('confirm and moves must be true or false', not entry('    confirm: maybe\n').ok and not entry('    moves: 1\n').ok)
check('moves alone: confirms, no warning', entry('    moves: true\n').custom['p']['confirm'] is True
      and not entry('    moves: true\n').warnings)
r = entry('    moves: true\n    confirm: false\n')
check('moves: true always confirms, even when confirm is false', r.ok and r.custom['p']['confirm'] is True
      and any('confirm' in w for w in r.warnings), (r.errors, r.warnings))
r = entry('    moves: true\n    confirm: true\n')
check('moves and confirm both true: no warning', r.ok and not r.warnings, r.warnings)
r = entry('    undocks: true\n')
check('undocks: true means the program moves (and so confirms)', r.ok and r.custom['p']['moves'] is True
      and r.custom['p']['confirm'] is True and r.custom['p']['undocks'] is True, r.custom if r.ok else r.errors)
check('timeout: 1 to 3600 seconds, whole numbers', entry('    timeout: 1\n').ok and entry('    timeout: 3600\n').ok
      and not entry('    timeout: 0\n').ok and not entry('    timeout: 3601\n').ok and not entry('    timeout: 1.5\n').ok
      and not entry('    timeout: true\n').ok and not entry('    timeout: abc\n').ok)
check('unknown key in an entry is an error (typos must not pass)', not entry('    confrim: true\n').ok
      and 'confrim' in errs('entries:\n  - id: p\n    label: P\n    program: a.py\n    confrim: true\n'))
check('unknown top-level key or wrong version is an error', not parse('colour: red').ok and not parse('version: 2').ok
      and parse('version: 1').ok)
check('entries must be a list of mappings, at most 8', not parse('entries: x').ok and not parse('entries: [1]').ok
      and not parse('entries:\n' + ''.join(f'  - {{id: e{i}, label: E{i}, program: a.py}}\n' for i in range(9))).ok
      and parse('entries:\n' + ''.join(f'  - {{id: e{i}, label: E{i}, program: a.py}}\n' for i in range(8))).ok)

# ---------------------------------------------------------------- where an entry goes
def after(value):
    return parse(ONE + f'    after: {value}\n')


check('after: dock puts it right below Dock', after('dock').layout() == ['trip', 'dock', 'lights', 'undock', 'estop', 'wall_left',
                                                                         'wall_right', 'power', 'help'])
check('after: trip puts it second, nothing can go above the trip entry', after('trip').layout()[:2] == ['trip', 'lights'])
check('after: an unknown id is an error', not after('nothing').ok and 'nothing' in errs(ONE + '    after: nothing\n'))
check('after: a hidden built-in still marks the place', parse('hide: [undock]\n' + ONE + '    after: undock\n').layout()
      == ['trip', 'dock', 'lights', 'estop', 'wall_left', 'wall_right', 'power', 'help'])
two = ('entries:\n  - {id: a, label: A, program: a.py, after: dock}\n  - {id: b, label: B, program: b.py, after: dock}\n'
       '  - {id: c, label: C, program: c.py, after: a}\n')
check('after: same place = file order; after another custom entry = right below it', parse(two).layout()[:6]
      == ['trip', 'dock', 'a', 'c', 'b', 'undock'], parse(two).layout())
cyc = '  - {id: x, label: X, program: a.py, after: y}\n  - {id: y, label: Y, program: b.py, after: x}\n'
check('after: a loop (x after y after x) is an error', not parse('entries:\n' + cyc).ok and 'loop' in errs('entries:\n' + cyc))
check('after: itself is an error', not parse('entries:\n  - {id: x, label: X, program: a.py, after: x}\n').ok)

# ---------------------------------------------------------------- bad text
check('broken YAML is an error, not a crash', not parse('entries: [unclosed').ok and not parse('\t\tx: [').ok)
check('a list at the top is an error', not parse('- a\n- b\n').ok)
check('a huge file is an error', not parse('# ' + 'x' * (cfg.MAX_FILE_CHARS + 10)).ok)
check('errors are short strings, at least one when invalid', all(isinstance(x, str) and 0 < len(x) < 200 for x in parse('hide: [dock]').errors))
check('screen_note: one short note that fits 5 x 18', all(len(x) <= 18 for x in cfg.screen_note(parse('hide: [dock]').errors))
      and len(cfg.screen_note(['x'])) <= 5 and cfg.screen_note(['a']) [0] == 'Menu file error')

# ---------------------------------------------------------------- resolving a program path at run time
check('program_path: home + robot_code + relative path', cfg.program_path('programs/lights.py', '/home/u') == '/home/u/robot_code/programs/lights.py')
check('inside_robot_code: real paths inside pass, outside or the folder itself do not',
      cfg.inside_robot_code('/home/u/robot_code/a/b.py', '/home/u/robot_code') and not cfg.inside_robot_code('/home/u/robot_code', '/home/u/robot_code')
      and not cfg.inside_robot_code('/home/u/robot_code2/a.py', '/home/u/robot_code') and not cfg.inside_robot_code('/etc/x.py', '/home/u/robot_code'))
check('command: .py runs with python3, .sh with bash, args follow', cfg.command('/p/a.py', ['1']) == ['python3', '/p/a.py', '1']
      and cfg.command('/p/a.sh', []) == ['bash', '/p/a.sh'])
check('menu_file_from: default, env and ~', cfg.menu_file_from({}, '/home/u') == '/home/u/robot_code/menu/menu.yaml'
      and cfg.menu_file_from({'DELIVERY_MENU_FILE': '/x/m.yaml'}, '/home/u') == '/x/m.yaml'
      and cfg.menu_file_from({'DELIVERY_MENU_FILE': '~/m.yaml'}, '/home/u') == '/home/u/m.yaml')

# ---------------------------------------------------------------- command line check
SCRIPT = os.path.join(DELIVERY, 'menu_config.py')
with tempfile.TemporaryDirectory() as tmp:
    good = os.path.join(tmp, 'good.yaml')
    bad = os.path.join(tmp, 'bad.yaml')
    with open(good, 'w', encoding='utf-8') as f:
        f.write(ONE + '    after: dock\n')
    with open(bad, 'w', encoding='utf-8') as f:
        f.write('hide: [dock]\n')

    def cli(*args):
        return subprocess.run([sys.executable, '-I', SCRIPT, *args], capture_output=True, text=True, timeout=60,
                              cwd=tmp, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    r = cli('--check', good, '--home', HOME)
    check('CLI: a good file prints OK and the menu, exit 0', r.returncode == 0 and r.stdout.startswith('OK') and 'Lights demo' in r.stdout
          and 'Go to food court' in r.stdout, r.stdout + r.stderr)
    r = cli('--check', bad, '--home', HOME)
    check('CLI: a bad file prints the problems, exit 1', r.returncode == 1 and 'locked' in r.stdout and 'INVALID' in r.stdout, r.stdout + r.stderr)
    r = cli('--check', os.path.join(tmp, 'none.yaml'))
    check('CLI: a missing file is exit 1 with a clear text', r.returncode == 1 and 'not found' in r.stdout.lower(), r.stdout + r.stderr)
    r = cli('--check', good, '--home', HOME, '--json')
    check('CLI: --json gives a machine-readable result', r.returncode == 0 and '"ok": true' in r.stdout and '"layout"' in r.stdout
          and '"labels"' in r.stdout, r.stdout + r.stderr)
    r = cli('--help')
    check('CLI: --help works', r.returncode == 0 and '--check' in r.stdout)

print(f'\n{count} checks, {fails} failure(s)')
sys.exit(1 if fails else 0)
