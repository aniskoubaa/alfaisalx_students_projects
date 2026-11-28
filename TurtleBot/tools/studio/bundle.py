#!/usr/bin/env python3
"""Builds the two single-file programs of TurtleBot Studio from their small source modules.

    studio.py        <- desktop/*.py   (the desktop app: web server, ssh, settings)
    robot_bridge.py  <- bridge/*.py    (runs on the robot; streamed over ssh as ONE file, see ADR 0002)

Edit the modules in desktop/ and bridge/, never the two generated files, then run:

    python bundle.py           rebuild both files
    python bundle.py --check   exit 1 if a generated file is not up to date (CI runs this)

How the joining works (ADR 0008):
  * each package's __init__.py lists its modules in MODULES, in the order they are joined;
  * a line that ends with "# bundle: skip" is left out (the imports between modules of the same package,
    which a single file does not need);
  * the docstring of every module except the first becomes a comment banner, so the result has exactly one
    docstring at the top, like the original single file.
Standard library only. Python 3.10 or newer.
"""
import argparse
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = [('studio.py', 'desktop'), ('robot_bridge.py', 'bridge')]
SKIP_MARK = '# bundle: skip'


def module_order(package_dir):
    """The MODULES list from the package's __init__.py, read without importing it."""
    with open(os.path.join(package_dir, '__init__.py'), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'MODULES' for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise SystemExit('%s/__init__.py has no MODULES list' % os.path.basename(package_dir))


def docstring_lines(source):
    """(first line, last line) of the module docstring, 1-based, or None."""
    tree = ast.parse(source)
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], 'value', None),
                                                                        ast.Constant) \
            and isinstance(tree.body[0].value.value, str):
        return tree.body[0].lineno, tree.body[0].end_lineno, tree.body[0].value.value
    return None


def build(package):
    """The joined source text for one package."""
    package_dir = os.path.join(HERE, package)
    out = []
    for i, name in enumerate(module_order(package_dir)):
        path = os.path.join(package_dir, name)
        with open(path, encoding='utf-8') as f:
            source = f.read()
        lines = source.splitlines()
        doc = docstring_lines(source)
        if i == 0:
            # the first module carries the shebang and the file docstring; the generated-file notice follows it
            end = doc[1] if doc else (1 if lines and lines[0].startswith('#!') else 0)
            out.extend(lines[:end])
            out.append('# GENERATED FILE, do not edit. Source: tools/studio/%s/*.py; rebuild with: python bundle.py'
                       % package)
            body = lines[end:]
        else:
            out.append('')
            out.append('# ' + '=' * 96)
            out.append('# %s/%s' % (package, name))
            if doc:
                for text in doc[2].strip().splitlines():
                    out.append(('# ' + text).rstrip())
                body = lines[:doc[0] - 1] + lines[doc[1]:]
            else:
                body = lines
            out.append('# ' + '=' * 96)
        out.extend(line for line in body if not line.rstrip().endswith(SKIP_MARK))
    text = '\n'.join(out).rstrip('\n') + '\n'
    while '\n\n\n\n' in text:   # at most two blank lines in a row, as in hand-written Python
        text = text.replace('\n\n\n\n', '\n\n\n')
    ast.parse(text)   # the joined file must be valid Python
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--check', action='store_true', help='only check that the generated files are up to date')
    args = ap.parse_args(argv)
    stale = []
    for target, package in TARGETS:
        if not os.path.isdir(os.path.join(HERE, package)):
            continue   # not split yet
        text = build(package)
        path = os.path.join(HERE, target)
        try:
            with open(path, encoding='utf-8', newline='') as f:
                current = f.read().replace('\r\n', '\n')   # a Windows checkout may have CRLF line ends
        except OSError:
            current = None
        if current == text:
            print('up to date  %s' % target)
        elif args.check:
            stale.append(target)
            print('OUT OF DATE %s: edit %s/*.py, then run python bundle.py and commit both' % (target, package))
        else:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
            print('wrote       %s (%d lines)' % (target, text.count('\n')))
    return 1 if stale else 0


if __name__ == '__main__':
    sys.exit(main())
