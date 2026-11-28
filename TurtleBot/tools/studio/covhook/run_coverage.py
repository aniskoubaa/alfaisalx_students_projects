"""Run the Studio offline Python tests under coverage.py and print the report.

Usage (from the repository root):
    python TurtleBot/tools/studio/covhook/run_coverage.py [--out DIR] [--skip NAME,...] [--only NAME,...] [--json FILE]

The data files go to DIR (default: a temporary folder outside the repository), never into the repository.
Subprocesses (fake bridge, studio.py --fake) are measured through covhook/sitecustomize.py.
The Playwright end to end tests are not run here (they need a browser).
"""
import argparse
import glob
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
TESTS = os.path.normpath(os.path.join(STUDIO, '..', '..', 'tests', 'offline'))
RC = os.path.join(STUDIO, '.coveragerc')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='')
    ap.add_argument('--skip', default='')
    ap.add_argument('--only', default='')
    ap.add_argument('--json', default='')
    a = ap.parse_args()
    out = a.out or tempfile.mkdtemp(prefix='studio_cov_')
    os.makedirs(out, exist_ok=True)
    skip = set(x for x in a.skip.split(',') if x)
    only = set(x for x in a.only.split(',') if x)
    files = sorted(glob.glob(os.path.join(TESTS, 'test_studio_*.py')))
    env = dict(os.environ, STUDIO_COV_DIR=out, COVERAGE_PROCESS_START=RC, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=HERE + os.pathsep + os.environ.get('PYTHONPATH', ''))
    for old in glob.glob(os.path.join(out, '.coverage*')):
        os.remove(old)
    bad = 0
    for f in files:
        name = os.path.basename(f)[:-3]
        if '_e2e' in name or name in skip or (only and name not in only):
            continue
        t0 = time.time()
        r = subprocess.run([sys.executable, '-m', 'coverage', 'run', '--rcfile', RC, f], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
        npass = sum(1 for ln in r.stdout.splitlines() if ln.startswith('PASS '))
        nfail = sum(1 for ln in r.stdout.splitlines() if ln.startswith('FAIL '))
        print(f'{name}: exit {r.returncode}, {npass} pass, {nfail} fail, {time.time() - t0:.0f}s', flush=True)
        for line in r.stdout.splitlines():
            if line.startswith('FAIL ') or line.startswith('Traceback'):
                print('    ' + line[:200], flush=True)
        bad += 1 if r.returncode else 0
    env2 = dict(env)
    subprocess.run([sys.executable, '-m', 'coverage', 'combine', '--rcfile', RC, '--keep', out], env=env2)
    subprocess.run([sys.executable, '-m', 'coverage', 'report', '--rcfile', RC], env=env2)
    if a.json:
        subprocess.run([sys.executable, '-m', 'coverage', 'json', '--rcfile', RC, '-o', a.json], env=env2)
    return bad


if __name__ == '__main__':
    sys.exit(main())
