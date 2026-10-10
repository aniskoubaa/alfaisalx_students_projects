"""Check relative links (and #anchors) in every Markdown and HTML file under TurtleBot/.

Runs anywhere with Python 3 (no robot, no ROS). Usage, from the repository root:
    python TurtleBot/tests/check_links.py            (or give the repository root as an argument)
Prints each broken link (MISSING file or ANCHOR not found) and exits 1 if there are any, 0 otherwise.
Web links (http, https, mailto) are not checked. Also run by .github/workflows/turtlebot-tests.yml.
"""
import os
import re
import sys
from urllib.parse import unquote

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())   # repo root
FILES = sorted(os.path.relpath(os.path.join(d, f), ROOT)
               for d, _, fs in os.walk(os.path.join(ROOT, 'TurtleBot')) for f in fs
               if f.endswith(('.md', '.html')))


def gh_slug(h):
    h = h.strip().lower()
    h = re.sub(r'[^\w\- ]', '', h)   # drop punctuation (keeps letters, digits, _, -, space)
    return h.replace(' ', '-')


def anchors(path):
    text = open(path, encoding='utf-8').read()
    if path.endswith('.md'):
        out, seen = set(), {}
        in_code = False
        for line in text.splitlines():
            if line.startswith('```'):
                in_code = not in_code
            if in_code:
                continue
            m = re.match(r'#{1,6}\s+(.*)', line)
            if m:
                s = gh_slug(re.sub(r'`', '', m.group(1)))
                n = seen.get(s, 0)
                seen[s] = n + 1
                out.add(s if n == 0 else f'{s}-{n}')
        return out
    return set(re.findall(r'\bid="([^"]+)"', text))


bad = 0
total = 0
for rel in FILES:
    path = os.path.join(ROOT, rel)
    text = open(path, encoding='utf-8').read()
    if path.endswith('.md'):
        text_nocode = re.sub(r'```.*?```', '', text, flags=re.S)
        links = re.findall(r'\]\(([^)\s]+)\)', text_nocode)
    else:
        links = re.findall(r'(?:href|src)="([^"]+)"', text)
    for link in links:
        if re.match(r'(https?:|mailto:)', link):
            continue
        total += 1
        target, _, frag = link.partition('#')
        tpath = path if not target else os.path.normpath(os.path.join(os.path.dirname(path), unquote(target)))
        if not os.path.exists(tpath):
            print(f'MISSING  {rel}: {link}')
            bad += 1
            continue
        if frag and os.path.isfile(tpath) and (tpath.endswith('.md') or tpath.endswith('.html')):
            if frag not in anchors(tpath):
                print(f'ANCHOR   {rel}: {link}')
                bad += 1
print(f'{total} relative links checked, {bad} problems')
sys.exit(1 if bad else 0)
