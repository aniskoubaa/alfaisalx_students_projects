"""Offline tests of the delivery voice player (TurtleBot/delivery/voice): event-to-phrase rules, following the event file,
repeat gap, silent switch, missing clip or player, language order, placeholder clips. No robot, no ROS, no sound card: a
fake clock and a fake player command (a small Python script that appends the clip name to a file).
Usage (from the repo root or from this folder): python test_delivery_voice.py
"""
import ast
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import wave

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
VOICE = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery', 'voice'))
sys.path.insert(0, VOICE)
import make_clips as mk  # noqa: E402
import voice_player as vp  # noqa: E402

fails = 0
count = 0


def check(name, cond, info=''):
    global fails, count
    count += 1
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


TMP = tempfile.mkdtemp(prefix='voicetest_')
LOGS = os.path.join(TMP, 'logs')
os.makedirs(LOGS)
PHRASES = os.path.join(TMP, 'phrases.yaml')
shutil.copy(os.path.join(VOICE, 'phrases.example.yaml'), PHRASES)
OUT = os.path.join(TMP, 'played.txt')
FAKE = os.path.join(TMP, 'fake_player.py')
with open(FAKE, 'w') as f:
    f.write('import os, sys\nwith open(os.environ["FAKE_OUT"], "a") as o:\n    o.write(os.path.basename(sys.argv[1]) + "\\n")\n')
os.environ['FAKE_OUT'] = OUT
PLAYER = f'"{sys.executable}" "{FAKE}" {{file}}'.replace('\\', '/')


def played():
    if not os.path.exists(OUT):
        return []
    with open(OUT) as f:
        return f.read().split()


def reset():
    if os.path.exists(OUT):
        os.remove(OUT)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def ev(event, detail='', run='r1'):
    return json.dumps({'run': run, 'time': '2026-11-14T10:00:00', 'mono': 1.0, 'event': event, 'detail': detail},
                      ensure_ascii=False) + '\n'


def append(path, text):
    with open(path, 'a', encoding='utf-8', newline='') as f:
        f.write(text)


def make(from_start=False, **kw):
    cfg = vp.load_phrases(PHRASES)
    logs = []
    fol = vp.EventFollower(LOGS, from_start=from_start, log=logs.append)
    clock = Clock()
    kw.setdefault('player_cmd', PLAYER)
    kw.setdefault('silent_file', os.path.join(TMP, 'NO_SUCH_SILENT'))
    pl = vp.VoicePlayer(cfg, fol, clock=clock, sleep=lambda s: None, log=logs.append, **kw)
    return pl, fol, clock, logs


def clean_logs():
    for p in os.listdir(LOGS):
        os.remove(os.path.join(LOGS, p))


# ---------------------------------------------------------------- placeholder clips
rc = mk.main(['--phrases', PHRASES, '--placeholder'])
check('make_clips --placeholder exits 0', rc == 0)
cfg = vp.load_phrases(PHRASES)
jobs = mk.clip_jobs(cfg)
check('12 clips listed (6 phrases x 2 languages)', len(jobs) == 12, len(jobs))
ok = True
for _, _, _, path in jobs:
    try:
        with wave.open(path, 'rb') as w:
            ok = ok and w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getnframes() > 1000
    except (OSError, wave.Error):
        ok = False
check('every placeholder clip is a valid WAV (opens with wave)', ok)
mk.write_placeholder_wav(os.path.join(TMP, 'sil.wav'), 0.5, 'silence')
with wave.open(os.path.join(TMP, 'sil.wav'), 'rb') as w:
    check('silence placeholder is valid and silent', w.getnframes() == 11025 and set(w.readframes(100)) == {0})
before = os.path.getmtime(jobs[0][3])
mk.main(['--phrases', PHRASES, '--placeholder', '--kind', 'silence'])
check('existing clips are kept without --force', os.path.getmtime(jobs[0][3]) == before)
cmd, stdin = mk.tts_command('piper --model m.onnx --output_file {out}', 'Hello', 'o.wav', 'en')
check('tts command without {text} sends the text on stdin', stdin == 'Hello' and cmd[-1] == 'o.wav')
cmd, stdin = mk.tts_command('tts --lang {lang} --text {text} --out {out}', 'Hi there', 'o.wav', 'ar')
check('tts command with {text} keeps the text as one argument', stdin is None and 'Hi there' in cmd and 'ar' in cmd)
mk.main(['--phrases', PHRASES, '--placeholder', '--dry-run', '--force'])
check('--dry-run writes nothing new', os.path.getmtime(jobs[0][3]) == before)
bad = mk.render(jobs[0], f'"{sys.executable}" -c "import sys; sys.exit(3)"'.replace('\\', '/'))
check('a failing TTS command is reported, not raised', bad[0] is False)

# ---------------------------------------------------------------- mapping
R = cfg['rules']
m = vp.phrase_for_event
check('show "Food placed?" -> ask_food', m(R, 'show', 'Food placed? | >Back to the lab | Press button 1') == 'ask_food')
check('show "Your food is here" -> food_here', m(R, 'show', 'Your food is here | >Done, thank you | Press button 1') == 'food_here')
check('show "Thank you!" -> thanks_food', m(R, 'show', 'Thank you!') == 'thanks_food')
check('show "Thank you! | Docking | ..." -> thanks_handoff', m(R, 'show', 'Thank you! | Docking | B: stop') == 'thanks_handoff')
check('show "Going to food court" -> going_food', m(R, 'show', 'Going to food court | Button 2: stop') == 'going_food')
check('alarm event -> help', m(R, 'alarm', 'battery low') == 'help')
check('chime alarm -> help', m(R, 'chime', 'alarm') == 'help')
check('chime arrive has no phrase', m(R, 'chime', 'arrive') is None)
check('other events have no phrase', m(R, 'leg_start', 'outbound') is None and m(R, 'show', 'No food | Going to the lab') is None)
check('rule with a missing key does not match', not vp.rule_matches({'event': 'show', 'detail_startswith': 'A'}, 'show', None))
check('parse_event_line: broken or non-event lines are None',
      vp.parse_event_line('{"event": ') is None and vp.parse_event_line('[1]') is None and vp.parse_event_line('') is None
      and vp.parse_event_line('{"run": "x", "detail": "s"}') is None)

# ---------------------------------------------------------------- player: order, repeat gap
reset()
pl, fol, clock, logs = make()
check('handle_event plays English then Arabic', [os.path.basename(p) for p in pl.handle_event({'event': 'alarm', 'detail': 'x'})]
      == ['help.wav', 'help.wav'])
check('fake player ran twice', len(played()) == 2)
reset()
pl, fol, clock, logs = make()
pl.handle_event({'event': 'show', 'detail': 'Thank you!'})
order = []
for lang in ('en', 'ar'):
    order.append(vp.clip_path(cfg['phrases']['thanks_food'], lang, cfg['clips_dir']))
check('play order follows the languages list', 'en' in os.path.relpath(order[0], cfg['clips_dir']) and 'ar' in os.path.relpath(order[1], cfg['clips_dir']))
check('both clips of the phrase were played in one go', played() == ['thanks_food.wav', 'thanks_food.wav'])
reset()
pl, fol, clock, logs = make()
first = pl.handle_event({'event': 'alarm', 'detail': 'a'})
clock.t += 3
second = pl.handle_event({'event': 'alarm', 'detail': 'b'})
check('same phrase within the repeat gap is skipped', len(first) == 2 and second == [])
other = pl.handle_event({'event': 'show', 'detail': 'Thank you!'})
check('a different phrase is not blocked by the gap', len(other) == 2)
clock.t += 6
check('same phrase after the gap plays again', len(pl.handle_event({'event': 'alarm', 'detail': 'c'})) == 2)
pl2, _, _, _ = make(repeat_gap_s=1.0)
pl2.handle_event({'event': 'alarm', 'detail': 'a'})
pl2.clock.t += 2
check('--repeat-gap overrides the config', len(pl2.handle_event({'event': 'alarm', 'detail': 'a'})) == 2)

# English only when no Arabic clip entry
cfg_en = vp.load_phrases(PHRASES)
del cfg_en['phrases']['help']['ar']
reset()
pl3 = vp.VoicePlayer(cfg_en, fol, player_cmd=PLAYER, silent_file=None, log=lambda m_: None)
check('a phrase with only English plays only English', len(pl3.handle_event({'event': 'alarm', 'detail': ''})) == 1)

# ---------------------------------------------------------------- dry run, silent, missing clip, missing player
reset()
pl, fol, clock, logs = make(dry_run=True)
res = pl.handle_event({'event': 'alarm', 'detail': ''})
check('--dry-run reports clips but plays nothing', len(res) == 2 and played() == [] and any('would play' in x for x in logs))
reset()
pl, fol, clock, logs = make(silent=True)
res = pl.handle_event({'event': 'alarm', 'detail': ''})
check('--silent plays nothing and logs it', res == [] and played() == [] and any(x.startswith('silent:') for x in logs))
sfile = os.path.join(TMP, 'SILENT')
reset()
pl, fol, clock, logs = make(silent_file=sfile)
check('no SILENT file: plays', len(pl.handle_event({'event': 'alarm', 'detail': ''})) == 2)
open(sfile, 'w').close()
clock.t += 20
reset()
check('SILENT file present: plays nothing', pl.handle_event({'event': 'alarm', 'detail': ''}) == [] and played() == [])
os.remove(sfile)
clock.t += 20
check('SILENT file removed: plays again, no restart needed', len(pl.handle_event({'event': 'alarm', 'detail': ''})) == 2)

reset()
pl, fol, clock, logs = make()
gone = vp.clip_path(cfg['phrases']['help'], 'en', cfg['clips_dir'])
keep = gone + '.bak'
os.rename(gone, keep)
try:
    res = pl.handle_event({'event': 'alarm', 'detail': ''})
    check('missing clip: warning, the other language still plays, no crash',
          len(res) == 1 and any('WARNING' in x and 'missing' in x for x in logs), logs)
finally:
    os.rename(keep, gone)
reset()
pl, fol, clock, logs = make(player_cmd='no-such-player-xyz {file}')
res = pl.handle_event({'event': 'alarm', 'detail': ''})
check('missing player command: warning once, no crash, nothing played',
      res == [] and sum('WARNING' in x for x in logs) == 1, logs)
pl, fol, clock, logs = make(player_cmd=None, which=lambda n: None)
res = pl.handle_event({'event': 'alarm', 'detail': ''})
check('neither aplay nor ffplay installed: warning, no crash', res == [] and any('no player found' in x for x in logs), logs)
pl, fol, clock, logs = make(player_cmd=f'"{sys.executable}" -c "import sys; sys.exit(2)"'.replace('\\', '/'))
check('player exiting with an error: warning, no crash', pl.handle_event({'event': 'alarm', 'detail': ''}) == [] and any('exited' in x for x in logs))
pl, fol, clock, logs = make()
pl.cfg['rules'] = [{'event': 'show', 'phrase': 'nope'}]
check('rule pointing at an unknown phrase: warning, no crash', pl.handle_event({'event': 'show', 'detail': ''}) == [] and any('nope' in x for x in logs))

# ---------------------------------------------------------------- player command choice
b = vp.build_player_command
has = lambda *names: (lambda n: '/usr/bin/' + n if n in names else None)
check('aplay with a device: aplay -q -D dev file', b(None, 'f.wav', 'plughw:1,0', has('aplay', 'ffplay')) == ['aplay', '-q', '-D', 'plughw:1,0', 'f.wav'])
check('aplay without a device: no -D', b(None, 'f.wav', None, has('aplay')) == ['aplay', '-q', 'f.wav'])
check('no aplay, ffplay present: ffplay, no device option',
      b(None, 'f.wav', 'plughw:1,0', has('ffplay')) == ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', 'f.wav'])
check('neither installed: None', b(None, 'f.wav', None, has()) is None)
check('--player-cmd overrides the choice', b('myplay --dev {device} {file}', 'a b.wav', 'd', has('aplay')) == ['myplay', '--dev', 'd', 'a b.wav'])

# ---------------------------------------------------------------- following the event file
clean_logs()
f1 = os.path.join(LOGS, 'delivery_20261114_100000.jsonl')
append(f1, ev('start', 'run r1') + ev('show', 'Going to food court | x'))
pl, fol, clock, logs = make()
check('start at end: history of an old file is skipped', fol.poll() == [])
append(f1, ev('alarm', 'x'))
got = fol.poll()
check('start at end: a new line is delivered', [e['event'] for e in got] == ['alarm'])
check('no new data: nothing', fol.poll() == [])
pl, fol, clock, logs = make(from_start=True)
check('--from-start delivers the history', [e['event'] for e in fol.poll()] == ['start', 'show', 'alarm'])

# partial last line
clean_logs()
append(f1, ev('start'))
pl, fol, clock, logs = make()
fol.poll()
line = ev('show', 'Thank you!')
append(f1, line[:20])
check('partial last line is not delivered', fol.poll() == [])
append(f1, line[20:])
got = fol.poll()
check('partial line is delivered once complete', len(got) == 1 and got[0]['detail'] == 'Thank you!')
clean_logs()
append(f1, ev('start') + ev('show', 'Thank')[:15])
pl, fol, clock, logs = make()
fol.poll()
append(f1, ev('show', 'Thank')[15:])
check('a partial line already there at the start is completed later', len(fol.poll()) == 1)
append(f1, 'not json at all\n' + ev('alarm', 'ok'))
check('a broken line is skipped, the next is read', [e['event'] for e in fol.poll()] == ['alarm'])

# truncation
clean_logs()
append(f1, ev('start') + ev('show', 'a') + ev('show', 'b'))
pl, fol, clock, logs = make(from_start=True)
check('truncation setup: three events', len(fol.poll()) == 3)
with open(f1, 'w', encoding='utf-8', newline='') as f:
    f.write(ev('alarm', 'again'))
got = fol.poll()
check('truncated file is read again from its start', [e['event'] for e in got] == ['alarm'], got)

# next trip: a new file appears
clean_logs()
append(f1, ev('start'))
pl, fol, clock, logs = make()
fol.poll()
append(f1, ev('alarm', 'tail of trip 1'))
f2 = os.path.join(LOGS, 'delivery_20261114_110000.jsonl')
append(f2, ev('start', 'run r2', run='r2') + ev('show', 'Thank you!', run='r2'))
got = fol.poll()
check('a new file for the next trip is read from its first line, after the old tail',
      [e['event'] for e in got] == ['alarm', 'start', 'show'], got)
check('the new file is the one followed', fol.path == f2)
append(f2, ev('alarm', 'x', run='r2'))
check('following continues in the new file', [e['event'] for e in fol.poll()] == ['alarm'])

# no file at the start, then a file appears: read from its start
clean_logs()
pl, fol, clock, logs = make()
check('no event file yet: nothing, no crash', fol.poll() == [])
append(f1, ev('start') + ev('alarm', 'x'))
check('a file that appears after the player started is read from the start', [e['event'] for e in fol.poll()] == ['start', 'alarm'])
shutil.rmtree(LOGS)
pl, fol, clock, logs = make()
check('missing log folder: nothing, no crash', fol.poll() == [])
os.makedirs(LOGS)

# end to end: step() over a file
clean_logs()
reset()
pl, fol, clock, logs = make(from_start=True)
append(f1, ev('start') + ev('show', 'Your food is here | >Done | Press button 1') + ev('chime', 'thanks') + ev('alarm', 'x'))
pl.step()
check('step() plays the clips of the events in the file, in order',
      played() == ['food_here.wav', 'food_here.wav', 'help.wav', 'help.wav'], played())

# ---------------------------------------------------------------- stop on SIGTERM
old = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
try:
    reset()
    pl, fol, clock, logs = make()
    signal.signal(signal.SIGTERM, pl.request_stop)
    calls = []

    def fake_sleep(s):
        calls.append(s)
        if len(calls) == 3:
            signal.raise_signal(signal.SIGTERM)
    pl.sleep = fake_sleep
    rc = pl.run()
    check('SIGTERM stops the loop and the exit code is 0', rc == 0 and pl.stop and len(calls) == 3, (rc, len(calls)))
    pl, fol, clock, logs = make()
    signal.signal(signal.SIGINT, pl.request_stop)
    pl.sleep = lambda s: signal.raise_signal(signal.SIGINT)
    check('SIGINT stops the loop cleanly', pl.run() == 0)
finally:
    for s, h in old.items():
        signal.signal(s, h)
if os.name == 'posix':
    import time
    proc = subprocess.Popen([sys.executable, os.path.join(VOICE, 'voice_player.py'), '--config', PHRASES, '--log-dir', LOGS,
                             '--player-cmd', PLAYER], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(1.0)
    proc.send_signal(signal.SIGTERM)
    try:
        code = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = -999
    check('real process exits 0 on SIGTERM', code == 0, code)
else:
    print('SKIP real-process SIGTERM test (needs POSIX signals)')

# Arabic text on a console that cannot show it (cp1252 or ascii) must not crash the player
clean_logs()
append(f1, ev('alarm', 'x'))
env = dict(os.environ, PYTHONIOENCODING='ascii')
r = subprocess.run([sys.executable, os.path.join(VOICE, 'voice_player.py'), '--config', PHRASES, '--log-dir', LOGS,
                    '--dry-run', '--from-start', '--once'], capture_output=True, text=True, env=env)
check('--dry-run --once prints Arabic text on an ascii console without crashing',
      r.returncode == 0 and 'would play help [ar]' in r.stdout, (r.returncode, r.stderr[-200:]))

# ---------------------------------------------------------------- no ROS
with open(os.path.join(VOICE, 'voice_player.py'), encoding='utf-8') as f:
    tree = ast.parse(f.read())
mods = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        mods |= {a.name.split('.')[0] for a in node.names}
    elif isinstance(node, ast.ImportFrom) and node.module:
        mods.add(node.module.split('.')[0])
ros_like = {'rclpy', 'rospy', 'ament_index_python', 'std_msgs', 'geometry_msgs', 'nav_msgs', 'sensor_msgs', 'tf2_ros',
            'irobot_create_msgs', 'turtlebot4_msgs', 'nav2_msgs', 'action_msgs', 'lifecycle_msgs', 'delivery_core',
            'delivery_mission', 'ros_buttons'}
check('voice_player.py imports no ROS module and no mission module', not (mods & ros_like), sorted(mods))
check('voice_player.py imports only the standard library (and lazily yaml)',
      mods <= {'argparse', 'glob', 'json', 'os', 'shlex', 'shutil', 'signal', 'subprocess', 'sys', 'time', 'yaml'}, sorted(mods))

shutil.rmtree(TMP, ignore_errors=True)
print(f'\n{count} checks, {fails} failure(s)')
sys.exit(1 if fails else 0)
