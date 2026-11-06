#!/usr/bin/env python3
"""One local command that answers "does everything pass?" for the TurtleBot delivery project.

    python TurtleBot/delivery/tools/verify_all.py            # everything
    python TurtleBot/delivery/tools/verify_all.py --strict   # a missing lint tool counts as a failure
    python TurtleBot/delivery/tools/verify_all.py --skip-tests   # lint and syntax only (fast)
    python TurtleBot/delivery/tools/verify_all.py -v         # show the output of every step, not just failures

Steps: ruff, yamllint, shellcheck (scoped to delivery/ and the delivery tests), py_compile, bash -n, check_links,
the offline test scripts that CI runs (test_pure, test_sim_runs, test_timing, test_studio_bridge, test_studio_desktop,
test_studio_templates, test_delivery_mission, test_plan_route, test_delivery_config) and every other
tests/offline/test_delivery_*.py (for example test_delivery_deploy.py).
A lint tool that is not installed gives SKIP with the install command, not a failure, unless --strict.
Prints a PASS / FAIL / SKIP table and exits 0 when nothing failed, 1 otherwise. Runs on Windows, macOS and Linux;
changes no file in the repository (no bytecode is written). Install the tools with:
    python -m pip install ruff yamllint shellcheck-py pyyaml
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.dirname(HERE)
TURTLEBOT = os.path.dirname(DELIVERY)
ROOT = os.path.dirname(TURTLEBOT)                                   # repository root
OFFLINE = os.path.join(TURTLEBOT, 'tests', 'offline')
CI_TESTS = ('test_pure', 'test_sim_runs', 'test_timing', 'test_studio_bridge', 'test_studio_desktop',
            'test_studio_templates', 'test_delivery_mission', 'test_plan_route', 'test_delivery_config')
TEST_TIMEOUT = 900
PASS, FAIL, SKIP = 'PASS', 'FAIL', 'SKIP'


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, '/')


def delivery_files(*suffixes):
    out = []
    for d, dirs, files in os.walk(DELIVERY):
        dirs[:] = [x for x in dirs if x not in ('__pycache__', 'upstream', '.ruff_cache')]
        out += [os.path.join(d, f) for f in files if f.endswith(suffixes)]
    return sorted(out)


def delivery_tests():
    return sorted(glob.glob(os.path.join(OFFLINE, 'test_delivery_*.py')))


def run(cmd, timeout=300, env=None):
    """(returncode, combined output). A timeout or a missing program is reported as a failure code."""
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    if env:
        e.update(env)
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=timeout, env=e)
    except subprocess.TimeoutExpired:
        return 124, f'timed out after {timeout} s'
    except OSError as ex:
        return 127, str(ex)
    return r.returncode, (r.stdout + r.stderr).decode('utf-8', 'replace')


def python_module_present(name):
    rc, _ = run([sys.executable, '-m', name, '--version'], timeout=60)
    return rc == 0


def find_shellcheck():
    p = shutil.which('shellcheck')
    if p:
        return p
    exe = 'shellcheck.exe' if os.name == 'nt' else 'shellcheck'
    for d in (os.path.dirname(sys.executable), os.path.join(os.path.dirname(sys.executable), 'Scripts'),
              os.path.join(sys.prefix, 'Scripts'), os.path.join(sys.prefix, 'bin')):
        c = os.path.join(d, exe)
        if os.path.isfile(c):
            return c
    return None


def find_bash():
    if os.name == 'nt':
        for p in (r'C:\Program Files\Git\bin\bash.exe', r'C:\Program Files\Git\usr\bin\bash.exe'):
            if os.path.isfile(p):
                return p
    b = shutil.which('bash')
    return None if (b and 'system32' in b.lower()) else b          # System32\bash.exe is WSL, not what the robot runs


# ------------------------------------------------------------------ steps: each returns (status, detail text)
def step_ruff():
    if not python_module_present('ruff'):
        return SKIP, 'ruff is not installed: python -m pip install ruff'
    targets = [DELIVERY, *delivery_tests()]
    rc, out = run([sys.executable, '-m', 'ruff', 'check', '--no-cache', '--config', os.path.join(DELIVERY, 'ruff.toml'),
                   *targets])
    return (PASS if rc == 0 else FAIL), out


def step_yamllint():
    if not python_module_present('yamllint'):
        return SKIP, 'yamllint is not installed: python -m pip install yamllint'
    targets = [DELIVERY] + sorted(glob.glob(os.path.join(ROOT, '.github', 'workflows', 'turtlebot-delivery.yml')))
    rc, out = run([sys.executable, '-m', 'yamllint', '-c', os.path.join(DELIVERY, '.yamllint.yml'), *targets])
    return (PASS if rc == 0 else FAIL), out


def step_shellcheck():
    sc = find_shellcheck()
    if not sc:
        return SKIP, 'shellcheck is not installed: python -m pip install shellcheck-py'
    scripts = delivery_files('.sh')
    rc, out = run([sc, '-x', *scripts])
    return (PASS if rc == 0 else FAIL), out or f'{len(scripts)} scripts'


def step_py_compile():
    bad, n = [], 0
    for p in delivery_files('.py') + delivery_tests():
        n += 1
        try:
            with open(p, 'rb') as f:
                compile(f.read(), p, 'exec')
        except (SyntaxError, ValueError) as e:
            bad.append(f'{rel(p)}: {e}')
    return (FAIL if bad else PASS), '\n'.join(bad) or f'{n} files'


def step_bash_n():
    bash = find_bash()
    if not bash:
        return SKIP, 'bash not found (on Windows install Git for Windows)'
    bad, scripts = [], delivery_files('.sh')
    for p in scripts:
        rc, out = run([bash, '-n', rel(p)])
        if rc != 0:
            bad.append(f'{rel(p)}: {out.strip()}')
        with open(p, 'rb') as f:
            if b'\r\n' in f.read():
                bad.append(f'{rel(p)}: CRLF line endings (the robot needs LF)')
    return (FAIL if bad else PASS), '\n'.join(bad) or f'{len(scripts)} scripts'


def step_links():
    rc, out = run([sys.executable, os.path.join(TURTLEBOT, 'tests', 'check_links.py'), ROOT])
    return (PASS if rc == 0 else FAIL), out


def step_test(path):
    def go():
        rc, out = run([sys.executable, path], timeout=TEST_TIMEOUT)
        return (PASS if rc == 0 else FAIL), out
    return go


def build_steps(skip_tests):
    steps = [('ruff', step_ruff), ('yamllint', step_yamllint), ('shellcheck', step_shellcheck),
             ('py_compile', step_py_compile), ('bash -n', step_bash_n), ('check_links', step_links)]
    if not skip_tests:
        names = list(CI_TESTS)
        pattern = os.path.join(OFFLINE, 'test_delivery_*.py')
        extra = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(pattern))
        names += [n for n in extra if n not in names]
        for n in names:
            p = os.path.join(OFFLINE, n + '.py')
            if os.path.isfile(p):
                steps.append((n + '.py', step_test(p)))
            else:
                steps.append((n + '.py', lambda n=n: (FAIL, f'{n}.py not found')))
    return steps


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--strict', action='store_true', help='a missing lint tool is a failure, not a SKIP')
    ap.add_argument('--skip-tests', action='store_true', help='lint and syntax checks only')
    ap.add_argument('-v', '--verbose', action='store_true', help='print the output of every step')
    a = ap.parse_args(argv)
    rows = []
    t_all = time.time()
    for name, fn in build_steps(a.skip_tests):
        t0 = time.time()
        sys.stdout.write(f'running {name} ... ')
        sys.stdout.flush()
        try:
            status, detail = fn()
        except Exception as e:                                      # a broken step must not hide the others
            status, detail = FAIL, f'{type(e).__name__}: {e}'
        if status == SKIP and a.strict:
            status, detail = FAIL, detail + ' (--strict)'
        print(status)
        rows.append((name, status, time.time() - t0, detail))
    width = max(len(r[0]) for r in rows)
    print('\n' + 'step'.ljust(width) + '  result  seconds')
    print('-' * (width + 18))
    for name, status, secs, _ in rows:
        print(f'{name.ljust(width)}  {status:<6}  {secs:6.1f}')
    for name, status, _, detail in rows:
        if status == FAIL or (a.verbose and detail.strip()) or (status == SKIP and detail.strip()):
            tail = detail.strip().splitlines()
            if status != FAIL and not a.verbose:
                tail = tail[:2]
            elif len(tail) > 60 and not a.verbose:
                tail = ['...'] + tail[-60:]
            print(f'\n[{status}] {name}')
            print('\n'.join('    ' + ln for ln in tail))
    counts = {s: sum(1 for r in rows if r[1] == s) for s in (PASS, FAIL, SKIP)}
    print(f'\n{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped in {time.time() - t_all:.0f} s')
    print('ALL PASSED' if counts[FAIL] == 0 else 'SOMETHING FAILED')
    return 1 if counts[FAIL] else 0


if __name__ == '__main__':
    sys.exit(main())
