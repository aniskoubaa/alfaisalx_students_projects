#!/usr/bin/env python3
"""Voice player for the campus delivery (TB-29): follows the mission's JSON Lines event file and plays clips.

Plain Python, standard library plus PyYAML. It creates no ROS node and imports nothing from ROS, so it cannot stall the
Create 3 base (TB-25). The mission is not changed: this program only reads the file delivery_mission.py writes
(delivery_<date>_<time>.jsonl, one JSON object per line with run, time, mono, event, detail).

Usage:
    python3 voice_player.py --config ~/robot_code/voice/phrases.yaml            # follow the newest event file
    python3 voice_player.py --config phrases.yaml --dry-run --from-start --log-dir DIR   # print what would play
Switch it off without stopping it: create the file ~/robot_code/voice/SILENT (or use --silent): events are only logged.
Player command: the first of "aplay -q -D <device> <file>" and "ffplay -nodisp -autoexit -loglevel quiet <file>" that is
installed (ffplay has no device option); --player-cmd overrides the choice.
Design and open questions: TurtleBot/docs/SPOKEN-MESSAGES.md, sections 3 to 8.
"""
import argparse
import glob
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time

DEFAULT_LOG_DIR = '~/robot_code/logs'
DEFAULT_SILENT_FILE = '~/robot_code/voice/SILENT'
APLAY_DEVICE = ['aplay', '-q', '-D', '{device}', '{file}']
APLAY_PLAIN = ['aplay', '-q', '{file}']
FFPLAY = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', '{file}']
POLL_S = 0.2
REPEAT_GAP_S = 8.0
PLAY_TIMEOUT_S = 30.0
LANGUAGES = ('en', 'ar')


# ---------------------------------------------------------------- pure helpers
def load_phrases(path):
    """Read the phrase file (YAML). Returns a dict with keys phrases, rules, device, repeat_gap_s, languages and
    clips_dir (the folder the clip names are relative to: the folder of the phrase file unless the file says
    otherwise)."""
    import yaml
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data.get('phrases'), dict):
        raise ValueError(f'{path}: "phrases" must be a mapping of phrase id to texts and clip files')
    base = os.path.dirname(os.path.abspath(path))
    clips_dir = data.get('clips_dir') or base
    if not os.path.isabs(clips_dir):
        clips_dir = os.path.join(base, clips_dir)
    return {
        'phrases': data['phrases'],
        'rules': list(data.get('rules') or []),
        'device': data.get('device'),
        'repeat_gap_s': float(data.get('repeat_gap_s', REPEAT_GAP_S)),
        'languages': list(data.get('languages') or LANGUAGES),
        'clips_dir': clips_dir,
    }


def rule_matches(rule, event, detail):
    """One rule: event (required) plus optional detail_equals, detail_startswith, detail_contains."""
    if rule.get('event') != event:
        return False
    detail = detail or ''
    if 'detail_equals' in rule and detail != rule['detail_equals']:
        return False
    if 'detail_startswith' in rule and not detail.startswith(rule['detail_startswith']):
        return False
    return not ('detail_contains' in rule and rule['detail_contains'] not in detail)


def phrase_for_event(rules, event, detail):
    """The phrase id of the first matching rule, or None."""
    for rule in rules:
        if rule_matches(rule, event, detail) and rule.get('phrase'):
            return rule['phrase']
    return None


def parse_event_line(line):
    """One line of the event file as a dict with an 'event' key, or None (blank, broken, not an event)."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get('event'), str):
        return None
    return obj


def newest_event_file(log_dir):
    """The newest delivery_*.jsonl in the folder (the names carry the start time), or None."""
    files = sorted(glob.glob(os.path.join(os.path.expanduser(log_dir), 'delivery_*.jsonl')))
    return files[-1] if files else None


def default_player_template(device=None, which=shutil.which):
    """The first available player as an argument list with {file} and {device} placeholders: aplay (with -D when a
    device is given), else ffplay (no device option), else None."""
    if which('aplay'):
        return list(APLAY_DEVICE if device else APLAY_PLAIN)
    if which('ffplay'):
        return list(FFPLAY)
    return None


def build_player_command(template, clip, device=None, which=shutil.which):
    """The argument list that plays one clip, or None when no player is available. template is the --player-cmd text
    (split like a shell line), or None to pick aplay or ffplay. {file} and {device} are replaced per argument, so a path
    with spaces stays one argument."""
    parts = shlex.split(template) if template else default_player_template(device, which)
    if not parts:
        return None
    return [p.replace('{file}', clip).replace('{device}', device or '') for p in parts]


def clip_path(info, lang, clips_dir):
    """Path of the clip of one phrase in one language, or None when the phrase has no clip entry for it."""
    entry = (info or {}).get(lang)
    name = entry.get('file') if isinstance(entry, dict) else None
    if not name:
        return None
    return name if os.path.isabs(name) else os.path.join(clips_dir, name)


# ---------------------------------------------------------------- follower
class EventFollower:
    """Follows the newest event file as it grows. poll() returns the new complete events since the last call.
    It starts at the end of a file that already exists (history is not replayed) unless from_start is set; a file that
    appears later (the next trip) is read from its first line. A partial last line waits for its newline, and a file
    that became shorter (truncated) is read again from the start."""

    def __init__(self, log_dir, from_start=False, log=None):
        self.log_dir = log_dir
        self.from_start = from_start
        self.log = log or (lambda msg: None)
        self.path = None
        self.offset = 0
        self.buf = b''
        self.first = True

    def _read_new(self):
        try:
            size = os.path.getsize(self.path)
            if size < self.offset:
                self.log(f'{os.path.basename(self.path)} became shorter, reading it again from the start')
                self.offset, self.buf = 0, b''
            if size == self.offset:
                return []
            with open(self.path, 'rb') as f:
                f.seek(self.offset)
                data = f.read()
        except OSError as e:
            self.log(f'cannot read {self.path}: {e}')
            return []
        self.offset += len(data)
        pieces = (self.buf + data).split(b'\n')
        self.buf = pieces.pop()           # the part after the last newline: empty, or a line still being written
        events = []
        for raw in pieces:
            ev = parse_event_line(raw.decode('utf-8', errors='replace'))
            if ev:
                events.append(ev)
        return events

    def poll(self):
        events = []
        newest = newest_event_file(self.log_dir)
        if newest is None:
            self.first = False
            return events
        if self.path is not None and newest != self.path:
            events += self._read_new()    # the end of the old trip, then the new file from its start
            self.log(f'following {os.path.basename(newest)}')
            self.path, self.offset, self.buf = newest, 0, b''
        elif self.path is None:
            self.path, self.offset, self.buf = newest, 0, b''
            if self.first and not self.from_start:
                self.log(f'following {os.path.basename(newest)} from its end (history is skipped)')
                self._read_new()          # skip what is there; a partial last line stays in the buffer
                self.first = False
                return events
            self.log(f'following {os.path.basename(newest)}')
        self.first = False
        return events + self._read_new()


# ---------------------------------------------------------------- player
class VoicePlayer:
    def __init__(self, config, follower, device=None, player_cmd=None, silent=False, silent_file=DEFAULT_SILENT_FILE,
                 dry_run=False, repeat_gap_s=None, clock=time.monotonic, sleep=time.sleep, log=None,
                 which=shutil.which):
        self.cfg = config
        self.follower = follower
        self.device = device or config.get('device')
        self.player_cmd = player_cmd
        self.silent = silent
        self.silent_file = os.path.expanduser(silent_file) if silent_file else None
        self.dry_run = dry_run
        self.repeat_gap_s = config['repeat_gap_s'] if repeat_gap_s is None else repeat_gap_s
        self.clock, self.sleep, self.which = clock, sleep, which
        self.log = log or (lambda msg: print(f'{time.strftime("%H:%M:%S")} {msg}', flush=True))
        self.last_played = {}             # phrase id -> clock time of its last play
        self.stop = False
        self.proc = None
        self.warned = set()

    def is_silent(self):
        return self.silent or bool(self.silent_file and os.path.exists(self.silent_file))

    def request_stop(self, *_):
        self.stop = True

    def _warn_once(self, key, msg):
        if key not in self.warned:
            self.warned.add(key)
            self.log('WARNING: ' + msg)

    def handle_event(self, ev):
        """Map an event to a phrase and play it. Returns the list of clips played (or that would be played)."""
        phrase = phrase_for_event(self.cfg['rules'], ev.get('event'), ev.get('detail'))
        if phrase is None:
            return []
        now = self.clock()
        last = self.last_played.get(phrase)
        if last is not None and now - last < self.repeat_gap_s:
            self.log(f'skip {phrase}: said {now - last:.1f} s ago (gap {self.repeat_gap_s:g} s)')
            return []
        info = self.cfg['phrases'].get(phrase)
        if info is None:
            self._warn_once('phrase:' + phrase, f'rule points at the phrase "{phrase}", which is not in the list')
            return []
        self.last_played[phrase] = now
        played = []
        for lang in self.cfg['languages']:
            if self.stop:
                break
            path = clip_path(info, lang, self.cfg['clips_dir'])
            if path is None:
                continue
            text = (info.get(lang) or {}).get('text', '')
            if self.is_silent():
                self.log(f'silent: {phrase} [{lang}] {text}')
            elif self.dry_run:
                self.log(f'would play {phrase} [{lang}] {path}  "{text}"')
                played.append(path)
            elif not os.path.isfile(path):
                self._warn_once('clip:' + path, f'clip {path} is missing, skipping {phrase} [{lang}]')
            elif self._play(path):
                played.append(path)
        return played

    def _play(self, path):
        cmd = build_player_command(self.player_cmd, path, self.device, self.which)
        if cmd is None:
            self._warn_once('player', 'no player found (neither aplay nor ffplay is installed), nothing is played')
            return False
        self.log(f'play {os.path.basename(path)}')
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.PIPE)
        except OSError as e:
            self._warn_once('player', f'cannot start the player command {cmd[0]!r}: {e}')
            return False
        proc = self.proc
        deadline = time.monotonic() + PLAY_TIMEOUT_S
        err = b''
        try:
            while proc.poll() is None:
                if self.stop or time.monotonic() > deadline:
                    proc.terminate()
                    break
                time.sleep(0.02)
            try:
                _, err = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, err = proc.communicate()
        finally:
            self.proc = None
        err = (err or b'').decode('utf-8', errors='replace').strip()
        if proc.returncode != 0 and not self.stop:
            self._warn_once('exit:' + path,
                            f'player exited with code {proc.returncode} for {os.path.basename(path)}: {err[:200]}')
            return False
        return True

    def step(self):
        """One poll of the event file; plays what it finds. Returns the clips played."""
        played = []
        for ev in self.follower.poll():
            if self.stop:
                break
            played += self.handle_event(ev)
        return played

    def run(self):
        self.log('voice player started' + (' (silent)' if self.is_silent() else '')
                 + (' (dry run)' if self.dry_run else ''))
        try:
            while not self.stop:
                self.step()
                self.sleep(POLL_S)
        finally:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
        self.log('voice player stopped')
        return 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='Plays prerecorded clips for the delivery mission events (no ROS).')
    ap.add_argument('--config', default='~/robot_code/voice/phrases.yaml', help='phrase file (YAML)')
    ap.add_argument('--log-dir', default=DEFAULT_LOG_DIR, help='folder of the delivery_*.jsonl event files')
    ap.add_argument('--device', help='sound device for aplay -D (for example plughw:1,0); default: the config file. '
                    'ffplay has no device option')
    ap.add_argument('--player-cmd', help='player command template with {file} and {device} '
                    '(default: aplay if installed, else ffplay)')
    ap.add_argument('--from-start', action='store_true', help='play the events already in the newest file too')
    ap.add_argument('--silent', action='store_true', help='log only, play nothing')
    ap.add_argument('--silent-file', default=DEFAULT_SILENT_FILE, help='if this file exists, play nothing')
    ap.add_argument('--repeat-gap', type=float, help='seconds before a phrase may repeat (default: config, 8)')
    ap.add_argument('--dry-run', action='store_true', help='print what would play, play nothing')
    ap.add_argument('--once', action='store_true', help='read once, then exit (with --from-start: a replay)')
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='backslashreplace')   # Arabic text must never crash a console that cannot show it
        except (AttributeError, ValueError):
            pass
    try:
        cfg = load_phrases(os.path.expanduser(a.config))
    except (OSError, ValueError, ImportError) as e:
        print(f'cannot load the phrase file {a.config}: {e}', file=sys.stderr)
        return 2

    def log(msg):
        print(f'{time.strftime("%H:%M:%S")} {msg}', flush=True)

    follower = EventFollower(a.log_dir, from_start=a.from_start, log=log)
    player = VoicePlayer(cfg, follower, device=a.device, player_cmd=a.player_cmd, silent=a.silent,
                         silent_file=a.silent_file, dry_run=a.dry_run, repeat_gap_s=a.repeat_gap, log=log)
    signal.signal(signal.SIGINT, player.request_stop)
    signal.signal(signal.SIGTERM, player.request_stop)
    if a.once:
        player.step()
        return 0
    return player.run()


if __name__ == '__main__':
    sys.exit(main())
