#!/usr/bin/env python3
"""Laptop tool: renders the clips of a phrase file (phrases.example.yaml) with a text-to-speech command, or writes
placeholder WAV files so the whole voice chain can be tested before real voices exist. Downloads nothing.

Examples (run from this folder):
    python make_clips.py --placeholder                       # short beeps for every clip, no voices needed
    python make_clips.py --placeholder --kind silence --force
    python make_clips.py --tts-cmd "piper --model en.onnx --output_file {out}" --lang en    # text goes to stdin
    python make_clips.py --tts-cmd "mytts --voice {lang} --text {text} --out {out}" --dry-run
The --tts-cmd template is split like a shell line; {text}, {out} and {lang} are replaced per argument. Without {text} in
the template the text is sent on standard input (Piper style). Existing clips are kept unless --force is given.
"""
import argparse
import math
import os
import shlex
import struct
import subprocess
import sys
import wave

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from voice_player import load_phrases  # noqa: E402

RATE = 22050


def placeholder_seconds(text):
    """Length of a placeholder clip: 0.3 s plus 0.05 s per word, at most 2 s."""
    return min(2.0, 0.3 + 0.05 * len(text.split()))


def write_placeholder_wav(path, seconds, kind='beep', freq=440.0):
    """A valid mono 16-bit 22.05 kHz WAV: a quiet sine beep or silence."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    n = int(RATE * seconds)
    if kind == 'silence':
        frames = b'\x00\x00' * n
    else:
        fade = max(1, int(RATE * 0.02))
        samples = []
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            samples.append(int(6000 * env * math.sin(2 * math.pi * freq * i / RATE)))
        frames = struct.pack('<%dh' % n, *samples)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def clip_jobs(cfg, langs=None, only=None):
    """(phrase id, language, text, absolute clip path) for every clip in the phrase file."""
    jobs = []
    for pid, info in cfg['phrases'].items():
        if only and pid not in only:
            continue
        for lang in cfg['languages']:
            if langs and lang not in langs:
                continue
            entry = (info or {}).get(lang)
            if not isinstance(entry, dict) or not entry.get('file') or not entry.get('text'):
                continue
            name = entry['file']
            path = name if os.path.isabs(name) else os.path.join(cfg['clips_dir'], name)
            jobs.append((pid, lang, entry['text'], path))
    return jobs


def tts_command(template, text, out, lang):
    """(argument list, text for stdin or None) for one clip."""
    parts = shlex.split(template)
    uses_text = any('{text}' in p for p in parts)
    cmd = [p.replace('{text}', text).replace('{out}', out).replace('{lang}', lang) for p in parts]
    return cmd, (None if uses_text else text)


def render(job, template, run=subprocess.run):
    pid, lang, text, path = job
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd, stdin = tts_command(template, text, path, lang)
    r = run(cmd, input=stdin, text=True, encoding='utf-8', capture_output=True, timeout=300)
    if r.returncode != 0:
        return False, (r.stderr or '').strip()[:200]
    if not os.path.isfile(path):
        return False, 'the command ran but wrote no file at the output path'
    return True, ''


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--phrases', default=os.path.join(HERE, 'phrases.example.yaml'), help='phrase file (YAML)')
    ap.add_argument('--tts-cmd', help='text-to-speech command template with {text}, {out}, {lang}')
    ap.add_argument('--placeholder', action='store_true', help='write placeholder WAV files instead of speech')
    ap.add_argument('--kind', choices=('beep', 'silence'), default='beep', help='placeholder content')
    ap.add_argument('--lang', action='append', help='only this language (repeatable)')
    ap.add_argument('--only', action='append', help='only this phrase id (repeatable)')
    ap.add_argument('--force', action='store_true', help='overwrite existing clips')
    ap.add_argument('--dry-run', action='store_true', help='print what would be written')
    a = ap.parse_args(argv)
    if bool(a.tts_cmd) == bool(a.placeholder):
        ap.error('give exactly one of --tts-cmd and --placeholder')
    cfg = load_phrases(a.phrases)
    jobs = clip_jobs(cfg, a.lang, a.only)
    failed = 0
    for job in jobs:
        pid, lang, text, path = job
        if os.path.exists(path) and not a.force:
            print(f'keep   {pid} [{lang}] {path}')
            continue
        if a.dry_run:
            print(f'would write {pid} [{lang}] {path}')
            continue
        if a.placeholder:
            write_placeholder_wav(path, placeholder_seconds(text), a.kind)
            print(f'wrote  {pid} [{lang}] {path} (placeholder {a.kind})')
            continue
        try:
            ok, why = render(job, a.tts_cmd)
        except (OSError, subprocess.SubprocessError) as e:
            ok, why = False, str(e)
        print(('wrote  ' if ok else 'FAILED ') + f'{pid} [{lang}] {path} {why}'.rstrip())
        failed += 0 if ok else 1
    print(f'{len(jobs)} clips listed, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
