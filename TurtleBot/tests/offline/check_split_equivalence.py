#!/usr/bin/env python3
"""Proves that a joined file (bundle.py output) holds the same code as the file it was split from.

    python check_split_equivalence.py ORIGINAL.py JOINED.py

Used once per split (ADR 0008); kept so a later re-split can be checked the same way. Not a test script (the CI
loop runs only test_*.py). Rules:
  * every top-level statement of ORIGINAL appears in JOINED, in the same order, with the same code (ast.dump);
    comments, docstrings of moved modules and blank lines do not count;
  * a class of ORIGINAL may be split into mixins: JOINED then has classes named <Something>Mixin, and the class of
    the same name whose bases are those mixins. The union of their bodies must equal the original body: same
    methods, same class attributes, each with the same code, and no name defined twice;
  * JOINED may add nothing else.
Exit code 0 when equivalent, 1 with a list of differences otherwise.
"""
import ast
import sys


def _key(node):
    """A name for a class-body item: method name, assigned name(s), or the dumped code for anything else."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign):
        return ','.join(ast.dump(t) for t in node.targets)
    if isinstance(node, ast.AnnAssign):
        return ast.dump(node.target)
    return ast.dump(node)


def _is_docstring(node):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _body(cls):
    return [n for n in cls.body if not _is_docstring(n)]


def compare(original_src, joined_src):
    orig = ast.parse(original_src).body
    joined = ast.parse(joined_src).body
    problems = []
    mixins = {n.name: n for n in joined if isinstance(n, ast.ClassDef) and n.name.endswith('Mixin')}
    rest = [n for n in joined if not (isinstance(n, ast.ClassDef) and n.name.endswith('Mixin'))]
    # the module docstring is compared like any statement; module docstrings of moved modules become comments
    if len(rest) != len(orig):
        problems.append('top-level statements: original %d, joined %d (without mixins)' % (len(orig), len(rest)))
    used_mixins = set()
    for o, j in zip(orig, rest):
        if isinstance(o, ast.ClassDef) and isinstance(j, ast.ClassDef) and o.name == j.name and \
                any(isinstance(b, ast.Name) and b.id in mixins for b in j.bases):
            parts = [mixins[b.id] for b in j.bases if isinstance(b, ast.Name) and b.id in mixins]
            used_mixins.update(p.name for p in parts)
            other_bases = [ast.dump(b) for b in j.bases if not (isinstance(b, ast.Name) and b.id in mixins)]
            if other_bases != [ast.dump(b) for b in o.bases]:
                problems.append('class %s: bases other than the mixins differ' % o.name)
            if [ast.dump(d) for d in o.decorator_list] != [ast.dump(d) for d in j.decorator_list]:
                problems.append('class %s: decorators differ' % o.name)
            want = {}
            for n in _body(o):
                want[_key(n)] = ast.dump(n)
            got = {}
            for part in parts + [j]:
                for n in _body(part):
                    k = _key(n)
                    if k in got:
                        problems.append('class %s: %s is defined twice (in %s)' % (o.name, k, part.name))
                    got[k] = ast.dump(n)
            for k in sorted(set(want) | set(got)):
                if k not in got:
                    problems.append('class %s: %s is missing' % (o.name, k[:80]))
                elif k not in want:
                    problems.append('class %s: %s is new' % (o.name, k[:80]))
                elif want[k] != got[k]:
                    problems.append('class %s: %s has different code' % (o.name, k[:80]))
        elif ast.dump(o) != ast.dump(j):
            name = getattr(o, 'name', None) or type(o).__name__
            problems.append('top-level statement at original line %d (%s) differs from joined line %d'
                            % (o.lineno, name, j.lineno))
    for name in sorted(set(mixins) - used_mixins):
        problems.append('mixin %s is not used by any class' % name)
    return problems


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    with open(argv[1], encoding='utf-8') as f:
        original = f.read()
    with open(argv[2], encoding='utf-8') as f:
        joined = f.read()
    problems = compare(original, joined)
    for p in problems[:200]:
        print('DIFF ' + p)
    print('equivalent' if not problems else '%d difference(s)' % len(problems))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
