"""Offline tests of the front-panel menu (TurtleBot/delivery/menu_core.py and the pure parts of delivery_menu.py): screens,
buttons, every state and transition, driven by a FakeIO with a virtual clock. No robot and no ROS needed.
Usage (from the repo root or from this folder): python test_delivery_menu.py
"""
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery'))
sys.path.insert(0, DELIVERY)
import delivery_menu as dmenu  # noqa: E402  (ROS is imported lazily, so this works without ROS)
import menu_core as mc  # noqa: E402

fails = 0
count = 0


def check(name, cond, info=''):
    global fails, count
    count += 1
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


ROUTE_DIR = '/home/u/robot_code/routes/current'
OUT_DIR = '/home/u/robot_code/logs/delivery'
ROUTE_FILE = ROUTE_DIR + '/route.yaml'


# ---------------------------------------------------------------- fake I/O
class FakeIO(mc.MenuIO):
    def __init__(self, docked=True, route=True, stack=False, wheels=True, mission=None):
        self.t = 500.0
        self.docked_v, self.wheels_v = docked, wheels
        self.files = {ROUTE_FILE: 'route'} if route else {}
        self.stack_up = stack
        self.stop_file = False
        self.down = set()
        self.published, self.logs = [], []            # (time, text)
        self.calls = []
        self.stack_exit = None                         # exit code start_stack.sh gives (None = still running)
        self.stack_exit_after = 5.0                    # s after start_stack was called
        self.stack_started_at = None
        self.mission_code = -2                         # -2 = no mission running; None = running; else exit code
        self.mission_args = None
        self.action_result = None                      # result the running action will give
        self.action_after = 4.0
        self.action_started_at = None
        self.action_ok = True
        self.estop_ok = self.power_ok = True
        if mission is not None:
            self.mission_code = None

    # time
    def now(self):
        return self.t

    def wall_time(self):
        return 1793000000.0 + self.t

    def sleep(self, seconds):
        self.t += seconds

    # screen and buttons
    def publish(self, text):
        self.published.append((self.t, text))

    def buttons(self):
        return [i + 1 in self.down for i in range(4)]

    # robot state
    def docked(self):
        return self.docked_v

    def wheels_enabled(self):
        return self.wheels_v

    def stop_file_exists(self):
        return self.stop_file

    def path_exists(self, path):
        return path in self.files

    def read_text(self, path):
        return self.files.get(path, '')

    def log(self, line):
        self.logs.append((self.t, line))

    # processes
    def stack_running(self):
        return self.stack_up

    def start_stack(self, route_dir, out_path):
        self.calls.append(('start_stack', route_dir, out_path))
        self.stack_started_at = self.t
        self.stack_exit = 0 if self.stack_exit is None else self.stack_exit

    def stack_poll(self):
        if self.stack_started_at is not None and self.t - self.stack_started_at >= self.stack_exit_after:
            if self.stack_exit == 0:
                self.stack_up = True
            return self.stack_exit
        return None

    def stack_cancel(self):
        self.calls.append(('stack_cancel',))
        self.stack_started_at = None

    def stop_stack_background(self):
        self.calls.append(('stop_stack',))

    def start_mission(self, args, out_path):
        self.calls.append(('start_mission', tuple(args), out_path))
        self.mission_args = args
        self.mission_code = None

    def mission_poll(self):
        return None if self.mission_code is None else (mc.NO_CODE if self.mission_code == -2 else self.mission_code)

    # actions and services
    def start_action(self, kind):
        self.calls.append(('start_action', kind))
        if not self.action_ok:
            return False
        self.action_started_at = self.t
        return True

    def action_poll(self):
        if self.action_started_at is None or self.action_result is None:
            return None
        return self.action_result if self.t - self.action_started_at >= self.action_after else None

    def action_cancel(self):
        self.calls.append(('action_cancel',))
        self.action_started_at = None

    def call_estop(self, on):
        self.calls.append(('estop', on))
        return self.estop_ok

    def call_power(self):
        self.calls.append(('power',))
        return self.power_ok

    # helpers for the tests
    def called(self, name):
        return [c for c in self.calls if c[0] == name]


NO_CODE = mc.NO_CODE


def make(**kw):
    io = FakeIO(**kw)
    menu = mc.Menu(io, ROUTE_DIR, OUT_DIR)
    menu.start()
    menu.step()
    return io, menu


def run(io, menu, seconds):
    end = io.t + seconds - 1e-9
    while io.t < end:
        menu.step()
        io.sleep(mc.POLL)


def tap(io, menu, number, hold=0.3, after=0.3):
    io.down.add(number)
    run(io, menu, hold)
    io.down.discard(number)
    run(io, menu, after)


def last(io):
    return io.published[-1][1] if io.published else None


def lines(text):
    return text.split('\n')


def fits(texts):
    return all(len(t.split('\n')) <= 5 and all(len(x) <= 18 for x in t.split('\n')) for t in texts)


def logged(io, text):
    return any(text in line for _, line in io.logs)


def go_to_mission(io, menu, kind_presses=(1, 1)):
    """From the menu on the trip entry: Select, Yes, wait for the stack if it has to start. Ends in the mission state."""
    for n in kind_presses:
        tap(io, menu, n)
    run(io, menu, 8.0)


# ---------------------------------------------------------------- pure helpers
check('fit: 5 lines of 18, leading spaces kept', mc.fit(['>Dock', ' Undock']) == '>Dock\n Undock'
      and mc.fit(['x' * 30]) == 'x' * 18 and len(mc.fit(['a'] * 9).split('\n')) == 5)
check('menu_lines: the chosen entry has the marker', mc.menu_lines(['A', 'B', 'C'], 1, 0) == [' A', '>B', ' C'])
check('scroll: down moves the cursor, the window follows after 5 entries', mc.scroll(0, 0, 8, 1) == (1, 0)
      and mc.scroll(4, 0, 8, 1) == (5, 1) and mc.scroll(7, 3, 8, 1) == (7, 3))
check('scroll: up at the top does nothing, up scrolls the window back', mc.scroll(0, 0, 8, -1) == (0, 0)
      and mc.scroll(3, 3, 8, -1) == (2, 2))
check('new_presses: only False -> True, the first sample is a baseline', mc.new_presses(None, [1, 0, 0, 0]) == []
      and mc.new_presses([0, 0, 0, 0], [0, 1, 0, 1]) == [2, 4] and mc.new_presses([0, 1, 0, 0], [0, 1, 0, 0]) == []
      and mc.new_presses([0, 1, 0, 0], [0, 0, 0, 0]) == [])
check('route_dir_from: default, env, and ~ expansion', mc.route_dir_from({}, '/home/u') == '/home/u/robot_code/routes/current'
      and mc.route_dir_from({'DELIVERY_ROUTE_DIR': '/data/r'}, '/home/u') == '/data/r'
      and mc.route_dir_from({'DELIVERY_ROUTE_DIR': '~/x'}, '/home/u') == '/home/u/x')
check('mission_args: full trip', mc.mission_args(ROUTE_DIR, 'full') == ['--route', ROUTE_FILE, '--yes'])
check('mission_args: home trip allows undocked', mc.mission_args(ROUTE_DIR, 'home')
      == ['--route', ROUTE_FILE, '--yes', '--trip', 'home', '--allow-undocked'])
check('mission_args never passes DELIVERY_PAUSE or anything else', 'DELIVERY_PAUSE' not in ' '.join(mc.mission_args(ROUTE_DIR, 'full')))
check('refusal_reason: finds the last reason in the mission output', mc.refusal_reason(
    '14:00:01 run=x REFUSING: battery 20 % is below the minimum 40 %\n14:00:02 run=x other\n') == 'battery 20 % is below the minimum 40 %')
check('refusal_reason: the last one wins, SETUP FAILED and ERROR and result lines count', mc.refusal_reason(
    'REFUSING: a\nERROR: b\n') == 'b' and mc.refusal_reason('x SETUP FAILED: missing /odom. Restart\n') == 'missing /odom. Restart'
      and mc.refusal_reason('12:00 run=1 result: refused (exit 2) Nav2 / AMCL did not become ready') == 'Nav2 / AMCL did not become ready'
      and mc.refusal_reason('nothing here') is None and mc.refusal_reason('') is None)
rl = mc.refusal_lines('the robot is not on the dock (put it on the dock, or use --allow-undocked)')
check('refusal_lines: Cannot start plus the reason cut to the screen', rl[0] == 'Cannot start' and len(rl) == 5
      and fits(['\n'.join(rl)]), str(rl))
check('refusal_lines: no reason still gives a screen', mc.refusal_lines(None)[0] == 'Cannot start' and 2 <= len(mc.refusal_lines(None)) <= 3)
check('out_name: menu_<date>_<time>.out', mc.out_name(1793000000.0).startswith('menu_') and mc.out_name(1793000000.0).endswith('.out')
      and len(mc.out_name(1793000000.0)) == len('menu_20261026_120000.out'))

# ---------------------------------------------------------------- the main menu
io, menu = make()
check('first screen: trip entry first, 5 entries, marker on the first',
      last(io) == '>Go to food court\n Dock\n Undock\n EStop\n Wall Follow Left', last(io))
io2, menu2 = make(docked=False)
check('undocked: the top entry is "Back to the lab"', lines(last(io2))[0] == '>Back to the lab', last(io2))
io3, menu3 = make(docked=None)
check('dock status unknown: the label is the safe default (food court)', lines(last(io3))[0] == '>Go to food court')
tap(io3, menu3, 1)
check('dock status unknown: Select on the trip shows a note and starts nothing', lines(last(io3))[0] == 'Waiting for'
      and not io3.called('start_stack') and not io3.called('start_mission'))

# scrolling
io, menu = make()
for _ in range(4):
    tap(io, menu, 4)
check('4 x Down: cursor on Wall Follow Left, window still at the top',
      last(io) == ' Go to food court\n Dock\n Undock\n EStop\n>Wall Follow Left', last(io))
tap(io, menu, 4)
check('5th Down scrolls the window by one', last(io) == ' Dock\n Undock\n EStop\n Wall Follow Left\n>Wall Follow Right', last(io))
for _ in range(5):
    tap(io, menu, 4)
check('Down at the bottom does nothing: last five entries, Help chosen', last(io) == ' EStop\n Wall Follow Left\n Wall Follow Right\n Power\n>Help', last(io))
tap(io, menu, 3)
check('Up moves the marker, the window stays', last(io).split('\n')[3] == '>Power', last(io))
tap(io, menu, 2)
check('Back returns the cursor to the top', last(io) == '>Go to food court\n Dock\n Undock\n EStop\n Wall Follow Left', last(io))
tap(io, menu, 3)
check('Up at the top does nothing', last(io).split('\n')[0] == '>Go to food court')
check('all menu screens fit 5 x 18', fits([t for _, t in io.published]))

# publishing rhythm
io, menu = make()
n0 = len(io.published)
run(io, menu, 10.0)
check('the screen is published again every 3 s', 3 <= len(io.published) - n0 <= 4, str(len(io.published) - n0))
n0 = len(io.published)
io.down.add(2)
run(io, menu, 0.3)
check('button 2 (clears the override of the stock node) gets a re-publish right away', len(io.published) > n0
      and io.published[-1][0] - io.t > -0.5)
io.down.discard(2)
run(io, menu, 0.3)
io, menu = make()
io.down.add(4)
run(io, menu, 2.0)
check('Down held for 2 s moves the cursor once', menu.cursor == 1, str(menu.cursor))
io.down.discard(4)
run(io, menu, 0.3)
tap(io, menu, 4)
check('releasing and pressing again counts again', menu.cursor == 2)
io = FakeIO()
io.down.add(4)
menu = mc.Menu(io, ROUTE_DIR, OUT_DIR)
menu.start()
run(io, menu, 1.0)
check('a button held when the program starts does not count', menu.cursor == 0)
io.down.discard(4)
run(io, menu, 0.3)
tap(io, menu, 4)
check('...but the next press does', menu.cursor == 1)

# log
io, menu = make()
tap(io, menu, 4)
tap(io, menu, 3)
check('every press is logged with its button and state', logged(io, 'press 4 in state menu') and logged(io, 'press 3 in state menu'))
check('menu start is logged with the route dir', logged(io, 'menu started') and logged(io, ROUTE_DIR))

# ---------------------------------------------------------------- Help
io, menu = make()
for _ in range(7):
    tap(io, menu, 4)
tap(io, menu, 1)
check('Help screen', last(io) == '1 Select  2 Back\n3 Up  4 Down\nTop = delivery', last(io))
tap(io, menu, 3)
check('any press leaves Help for the menu', lines(last(io))[0].startswith(' ') or lines(last(io))[0].startswith('>'))

# ---------------------------------------------------------------- trip: Go to food court
io, menu = make()
tap(io, menu, 1)
check('trip: Select asks first', last(io) == 'Go to food court?\n1 = Yes\n2 = No', last(io))
check('trip: nothing starts without the second press', not io.calls, str(io.calls))
run(io, menu, 20.0)
check('trip: the question stays on the screen and nothing starts by itself', last(io).startswith('Go to food court?') and not io.calls)
tap(io, menu, 3)
tap(io, menu, 4)
check('trip: buttons 3 and 4 do nothing in the question', last(io).startswith('Go to food court?') and not io.calls)
tap(io, menu, 2)
check('trip: 2 = No goes back to the menu, nothing started', lines(last(io))[0] == '>Go to food court' and not io.calls)
tap(io, menu, 1)
tap(io, menu, 1)
check('trip: Yes with the stack not running starts the stack first (route dir, output file)',
      len(io.called('start_stack')) == 1 and io.called('start_stack')[0][1] == ROUTE_DIR
      and io.called('start_stack')[0][2].startswith(OUT_DIR + '/menu_') and not io.called('start_mission'), str(io.calls))
check('trip: stack start screen', last(io) == 'Starting\nabout 1 minute\n2 = Cancel', last(io))
run(io, menu, 8.0)
check('trip: when the stack is up the mission starts as a child (route, --yes, no --trip)',
      len(io.called('start_mission')) == 1 and io.mission_args == ['--route', ROUTE_FILE, '--yes'], str(io.calls))
check('trip: the mission output goes to the same menu_*.out file as the stack',
      io.called('start_mission')[0][2] == io.called('start_stack')[0][2])
check('trip: one transition screen is drawn, then it is the mission\'s screen', last(io) == 'Starting\nplease wait\n2 = Stop')
n0 = len(io.published)
for n in (1, 2, 3, 4, 2, 2):
    tap(io, menu, n)
run(io, menu, 30.0)
check('while the mission runs the menu publishes NOTHING and ignores every button', len(io.published) == n0, str(len(io.published) - n0))
check('...but it logs the presses (so a physical press can be confirmed)', logged(io, 'press 2 in state mission'))
check('mission state: no second mission, no stack stop', len(io.called('start_mission')) == 1 and not io.called('stop_stack'))

# the mission ends at the dock with exit 0
io.docked_v = True
io.mission_code = 0
run(io, menu, 1.0)
check('mission exit 0 at the dock: the stack is stopped in the background (once)', len(io.called('stop_stack')) == 1)
n0 = len(io.published)
run(io, menu, 30.0)
check('result state: the text stays on the screen, drawn by the menu', menu.state == 'result' and last(io) == 'Delivery done')
tap(io, menu, 3)
check('result state: any press returns to the menu (cursor at the top)', lines(last(io))[0] == '>Go to food court')
check('...and the stack was not stopped again', len(io.called('stop_stack')) == 1)

# result: auto return after 60 s only when docked and exit 0
def finished(code, docked, wait):
    io, menu = make(stack=True)
    go_to_mission(io, menu)
    io.docked_v = docked
    io.mission_code = code
    run(io, menu, 1.0)
    n0 = len(io.published)
    run(io, menu, wait)
    return io, menu, len(io.published) - n0

io, menu, extra = finished(0, True, 59.0)
check('docked + exit 0: still the result after 59 s', menu.state == 'result' and last(io) == 'Delivery done')
run(io, menu, 3.0)
check('docked + exit 0: back to the menu by itself after 60 s', menu.state == 'menu' and lines(last(io))[0] == '>Go to food court')
io, menu, extra = finished(0, False, 90.0)
check('not docked + exit 0: stays in the result state, stack kept running', menu.state == 'result' and not io.called('stop_stack'))
io, menu, extra = finished(3, True, 90.0)
check('alarm (exit 3) at the dock: stack stopped but the NEED HELP text stays (no auto return)',
      menu.state == 'result' and len(io.called('stop_stack')) == 1 and last(io) == 'NEED HELP', last(io))
io, menu, extra = finished(130, False, 90.0)
check('stopped away from the dock (exit 130): result state, stack kept for Back to the lab', menu.state == 'result'
      and not io.called('stop_stack'))
io, menu, extra = finished(4, True, 65.0)
check('exit 4 (returned) at the dock also returns to the menu after 60 s', menu.state == 'menu')
io, menu, extra = finished(0, None, 90.0)
check('dock status unknown at the end: stack kept, no auto return', menu.state == 'result' and not io.called('stop_stack'))

# exit 2: refused
io, menu = make(stack=True)
go_to_mission(io, menu)
out = io.called('start_mission')[0][2]
io.files[out] = '12:00:00 run=a REFUSING: battery 20 % is below the minimum 40 %\n'
io.mission_code = 2
run(io, menu, 1.0)
check('exit 2: "Cannot start" and the reason from the output file', lines(last(io))[0] == 'Cannot start'
      and 'battery 20' in last(io) and fits([last(io)]), last(io))
tap(io, menu, 3)
check('exit 2: any press returns to the menu', lines(last(io))[0].lstrip('> ') == 'Go to food court')
io, menu = make(stack=True)
go_to_mission(io, menu)
io.files[io.called('start_mission')[0][2]] = 'x run=a result: refused (exit 2) Nav2 / AMCL did not become ready\n'
io.mission_code = 2
run(io, menu, 1.0)
check('exit 2: the reason of a refusal inside the mission is found too', 'Nav2' in last(io), last(io))
run(io, menu, mc.REFUSED_S + 1)
check('exit 2: the menu comes back by itself', menu.state == 'menu')

# stack already running at the dock
io, menu = make(stack=True)
go_to_mission(io, menu)
check('stack already running: no start_stack, the mission starts at once', not io.called('start_stack')
      and len(io.called('start_mission')) == 1)

# cancel while the stack starts
io, menu = make()
tap(io, menu, 1)
tap(io, menu, 1)
run(io, menu, 2.0)
tap(io, menu, 3)
tap(io, menu, 4)
check('stack start: 3 and 4 do nothing', menu.state == 'starting')
tap(io, menu, 2)
check('stack start: 2 cancels and stops the stack, no mission', io.called('stack_cancel') and io.called('stop_stack')
      and not io.called('start_mission') and last(io) == 'Cancelled', str(io.calls))
run(io, menu, 10.0)
check('stack start: after the cancel the menu is back and the mission never starts', menu.state == 'menu'
      and not io.called('start_mission'))

# start_stack.sh fails
io, menu = make()
io.stack_exit = 1
tap(io, menu, 1)
tap(io, menu, 1)
io.files[io.called('start_stack')[0][2]] = 'ERROR: /home/u/robot_code/routes/current/map.yaml is missing\n'
run(io, menu, 8.0)
check('stack start fails: "Cannot start" and the ERROR reason, no mission', lines(last(io))[0] == 'Cannot start'
      and 'map.yaml' in last(io).replace('\n', '') and not io.called('start_mission'), last(io))
io, menu = make()
io.stack_exit = 1
tap(io, menu, 1)
tap(io, menu, 1)
run(io, menu, 8.0)
check('stack start fails without a reason: still a screen', lines(last(io))[0] == 'Cannot start')
io, menu = make()
io.stack_exit_after = 10 ** 6
io.stack_exit = 0
tap(io, menu, 1)
tap(io, menu, 1)
run(io, menu, mc.STACK_START_TIMEOUT + 2)
check('stack start that never ends: cancelled after the timeout, no mission', io.called('stack_cancel')
      and not io.called('start_mission') and menu.state in ('note', 'menu'))

# no route
io, menu = make(route=False)
tap(io, menu, 1)
check('Go to food court without a saved route: refused at once with the 3 lines', last(io) == 'No route saved\nMap the route\nfirst', last(io))
check('...nothing started, no question asked', not io.calls and menu.state == 'note')
run(io, menu, mc.REFUSED_S + 1)
check('...and the menu comes back', menu.state == 'menu')
io, menu = make(route=False, stack=True)
tap(io, menu, 1)
check('no route is checked even with the stack running', lines(last(io))[0] == 'No route saved')

# the route is looked for in the right place
io = FakeIO(route=False)
io.files['/data/other/route.yaml'] = 'x'
menu = mc.Menu(io, '/data/other', OUT_DIR)
menu.start()
menu.step()
tap(io, menu, 1)
check('DELIVERY_ROUTE_DIR style folder: the route.yaml in it is found', last(io).startswith('Go to food court?'))

# ---------------------------------------------------------------- trip: Back to the lab
io, menu = make(docked=False, stack=False)
tap(io, menu, 1)
check('Back to the lab without the stack: "Not on the map" and nothing else',
      last(io) == 'Not on the map\nUse the controller\nthen Dock', last(io))
check('...the stack is never started away from the dock', not io.called('start_stack') and not io.called('start_mission')
      and not io.calls)
tap(io, menu, 1)
check('...even if the person presses Select again', not io.called('start_stack'))
run(io, menu, 30.0)
check('...and again after the note', not io.called('start_stack') and menu.state == 'menu')

io, menu = make(docked=False, stack=True)
tap(io, menu, 1)
check('Back to the lab with the stack running: asks first', last(io) == 'Back to the lab?\n1 = Yes\n2 = No', last(io))
check('...nothing started yet', not io.calls)
tap(io, menu, 1)
check('...Yes: the mission starts with --trip home --allow-undocked and no stack start',
      io.mission_args == ['--route', ROUTE_FILE, '--yes', '--trip', 'home', '--allow-undocked'] and not io.called('start_stack'),
      str(io.calls))
n0 = len(io.published)
run(io, menu, 30.0)
check('...and the menu is silent while it runs', len(io.published) == n0)
io.mission_code = 4
run(io, menu, 1.0)
check('home trip ended not docked (exit 4): result state, stack kept', menu.state == 'result' and not io.called('stop_stack'))
io.docked_v = True
run(io, menu, 61.0)
check('...docked later: back to the menu after 60 s from the end of the mission', menu.state == 'menu')

io, menu = make(docked=False, stack=True, route=False)
tap(io, menu, 1)
check('Back to the lab without a route file: No route saved', lines(last(io))[0] == 'No route saved')

# the dock status changes while the question is on the screen
io, menu = make(docked=True)
tap(io, menu, 1)
io.docked_v = False
tap(io, menu, 1)
check('dock status changes during the question: refused, nothing started', lines(last(io))[0] == 'Status changed'
      and not io.calls)
io, menu = make(docked=True)
tap(io, menu, 1)
io.files.pop(ROUTE_FILE)
tap(io, menu, 1)
check('route disappears during the question: refused at Yes', lines(last(io))[0] == 'No route saved' and not io.calls)

# stop file
io, menu = make()
io.stop_file = True
tap(io, menu, 1)
check('~/STOP exists: the trip is refused with a clear text', lines(last(io))[0] == 'STOP file is set' and not io.calls)

# a mission is already running (started by hand): the menu does not start another
io, menu = make()
io.mission_code = None
tap(io, menu, 1)
check('another mission running: no second trip', lines(last(io))[0] == 'A delivery' and not io.called('start_mission'))

# ---------------------------------------------------------------- adopting a running mission after a menu restart
io = FakeIO()
io.mission_code = None
menu = mc.Menu(io, ROUTE_DIR, OUT_DIR)
menu.start()
run(io, menu, 10.0)
check('menu restarted while a mission runs: it stays silent and does not touch the mission', not io.published
      and menu.state == 'mission' and not io.calls)
tap(io, menu, 1)
check('...buttons are ignored', not io.published)
io.docked_v = True
io.mission_code = mc.NO_CODE
run(io, menu, 1.0)
check('...when it ends (code unknown) the result state starts, the stack is stopped at the dock', menu.state == 'result'
      and len(io.called('stop_stack')) == 1)

# ---------------------------------------------------------------- Dock, Undock, Wall Follow
def at_entry(n, **kw):
    io, menu = make(**kw)
    for _ in range(n):
        tap(io, menu, 4)
    return io, menu


io, menu = at_entry(1, docked=False)
io.action_result = True
tap(io, menu, 1)
check('Dock: the action starts and the screen says Docking... with 2 = Cancel', io.called('start_action') == [('start_action', 'dock')]
      and last(io) == 'Docking...\n2 = Cancel', last(io))
run(io, menu, 5.0)
check('Dock worked: "Docked" for a few seconds', last(io) == 'Docked', last(io))
run(io, menu, mc.NOTE_S + 0.5)
check('...then the menu', menu.state == 'menu')
io, menu = at_entry(1, docked=False)
io.action_result = False
tap(io, menu, 1)
run(io, menu, 5.0)
check('Dock failed: "Dock failed"', last(io) == 'Dock failed', last(io))
io, menu = at_entry(1, docked=False)
io.action_result = True
tap(io, menu, 1)
run(io, menu, 1.0)
tap(io, menu, 3)
tap(io, menu, 4)
check('Dock running: 3 and 4 do nothing', menu.state == 'action')
tap(io, menu, 2)
check('Dock running: 2 cancels the goal', io.called('action_cancel') and last(io) == 'Cancelled', str(io.calls))
run(io, menu, 10.0)
check('...the late result of the cancelled goal is not shown', menu.state == 'menu')
io, menu = at_entry(1, docked=False)
io.action_result = None   # the goal never finishes
tap(io, menu, 1)
run(io, menu, mc.ACTION_TIMEOUT['dock'] + 2)
check('Dock that never finishes: cancelled after its timeout, "Dock failed"', io.called('action_cancel')
      and last(io) == 'Dock failed', last(io))
io, menu = at_entry(1, docked=False)
io.action_result = None
tap(io, menu, 1)
io.stop_file = True
run(io, menu, 1.0)
check('~/STOP cancels a running action', io.called('action_cancel'))
io, menu = at_entry(1, docked=False)
io.stop_file = True
tap(io, menu, 1)
check('~/STOP blocks a new action', not io.called('start_action') and lines(last(io))[0] == 'STOP file is set')
io, menu = at_entry(2, docked=True)
io.action_result = True
tap(io, menu, 1)
check('Undock: Undocking... screen', io.called('start_action') == [('start_action', 'undock')]
      and last(io) == 'Undocking...\n2 = Cancel', last(io))
run(io, menu, 5.0)
check('Undock worked', last(io) == 'Undocked')
io, menu = at_entry(2, docked=True)
io.action_ok = False
tap(io, menu, 1)
check('an action that cannot be sent: "Undock failed" at once', last(io) == 'Undock failed')

io, menu = at_entry(4, docked=True)
tap(io, menu, 1)
check('Wall Follow Left while docked: "Undock first", nothing sent', last(io) == 'Undock first' and not io.called('start_action'))
io, menu = at_entry(5, docked=True)
tap(io, menu, 1)
check('Wall Follow Right while docked: "Undock first", nothing sent', last(io) == 'Undock first' and not io.called('start_action'))
io, menu = at_entry(4, docked=False)
io.action_result = True
tap(io, menu, 1)
check('Wall Follow Left undocked: starts, screen with 2 = Cancel', io.called('start_action') == [('start_action', 'wall_left')]
      and last(io) == 'Wall following\nleft side\n2 = Cancel', last(io))
run(io, menu, 5.0)
check('Wall follow done', last(io) == 'Wall follow done')
io, menu = at_entry(5, docked=False)
io.action_result = False
tap(io, menu, 1)
run(io, menu, 5.0)
check('Wall Follow Right failed', last(io) == 'Wall follow failed')
check('Wall follow timeout is as long as the goal plus a margin', mc.ACTION_TIMEOUT['wall_left'] > mc.WALL_FOLLOW_SECONDS)

# ---------------------------------------------------------------- EStop and Power
io, menu = at_entry(3, wheels=True)
tap(io, menu, 1)
check('EStop with wheels enabled: e_stop_on=True and "EStop ON"', io.called('estop') == [('estop', True)] and last(io) == 'EStop ON', str(io.calls))
run(io, menu, mc.NOTE_S + 0.5)
check('...the menu comes back', menu.state == 'menu')
io, menu = at_entry(3, wheels=False)
tap(io, menu, 1)
check('EStop with wheels disabled: e_stop_on=False and "EStop off"', io.called('estop') == [('estop', False)] and last(io) == 'EStop off')
io, menu = at_entry(3, wheels=None)
tap(io, menu, 1)
check('EStop without wheel status: nothing is called', not io.calls and lines(last(io))[0] == 'EStop?')
io, menu = at_entry(3)
io.estop_ok = False
tap(io, menu, 1)
check('EStop service missing: "EStop failed"', last(io) == 'EStop failed')

io, menu = at_entry(6)
tap(io, menu, 1)
check('Power asks first', last(io) == 'Power off?\n1 = Yes\n2 = No' and not io.calls, last(io))
tap(io, menu, 2)
check('Power: 2 = No does nothing', not io.calls and menu.state == 'menu')
tap(io, menu, 1)
run(io, menu, 10.0)
check('Power: no call while the question waits', not io.calls and last(io).startswith('Power off?'))
tap(io, menu, 1)
check('Power: after Yes the service is called once', io.called('power') == [('power',)] and last(io) == 'Powering off')
io, menu = at_entry(6)
io.power_ok = False
tap(io, menu, 1)
tap(io, menu, 1)
check('Power service missing: "Power failed"', last(io) == 'Power failed')

# ---------------------------------------------------------------- every screen fits the display
io, menu = make(stack=True)
tap(io, menu, 1)
tap(io, menu, 1)
check('every text ever published fits 5 x 18 (food court run)', fits([t for _, t in io.published]))
check('no published text contains a tab or an empty screen', all(t.strip() and '\t' not in t for _, t in io.published))

# ---------------------------------------------------------------- run loop and the adapter module
io = FakeIO()
menu = mc.Menu(io, ROUTE_DIR, OUT_DIR)
ticks = []
menu.run(lambda: (ticks.append(1), len(ticks) > 50)[1])
check('run(): steps until should_stop says so, publishes the first screen', len(io.published) >= 1 and io.t > 500.0)

check('menu_core imports no ROS', 'rclpy' not in open(os.path.join(DELIVERY, 'menu_core.py'), encoding='utf-8').read())
check('delivery_menu imports ROS only inside functions', not any(
    ln.startswith(('import rclpy', 'from rclpy', 'from irobot', 'from std_msgs', 'from turtlebot4'))
    for ln in open(os.path.join(DELIVERY, 'delivery_menu.py'), encoding='utf-8').read().splitlines()))
check('delivery_menu.parse_args --help style options exist', dmenu.parse_args(['--dry-run']).dry_run is True
      and dmenu.parse_args([]).dry_run is False)
check('delivery_menu: route dir comes from the environment', dmenu.resolve_route_dir({'DELIVERY_ROUTE_DIR': '/x/y'}) == '/x/y')
check('delivery_menu: the stack pattern is the one the stop script uses', dmenu.STACK_PATTERN == 'delivery_stack.launch.py')
check('delivery_menu: the mission pattern is the one deploy.py uses', dmenu.MISSION_PATTERN == 'delivery_mission.py')

# ---------------------------------------------------------------- the stock node clears the text when 2 is RELEASED
io, menu = make()
io.down.add(2)
run(io, menu, 0.3)
io.down.discard(2)
n0 = len(io.published)
menu.step()                                              # the step that sees the release
io.sleep(mc.POLL)
run(io, menu, 0.4)
check('button 2: the screen is published again after the release, not only at the press', len(io.published) - n0 >= 3,
      str(len(io.published) - n0))
n0 = len(io.published)
run(io, menu, 1.5)
check('...and only for a moment, no flood afterwards', len(io.published) - n0 <= 3, str(len(io.published) - n0))

# ---------------------------------------------------------------- contact bounce (a physical button is not clean)
io, menu = make()
tap(io, menu, 1, hold=0.1, after=0.1)                    # Select on "Go to food court": the question comes up
check('bounce: first press opens the question', menu.state == 'confirm', menu.state)
tap(io, menu, 1, hold=0.1, after=0.3)                    # 0.2 s later is a real second press
check('bounce: a press 0.2 s later still counts', menu.state != 'confirm', menu.state)
io, menu = make()
menu.last_press = io.t                                   # a press just counted
io.down.add(1)
menu.step()
check('bounce: a second edge straight after a press is ignored', menu.state == 'menu' and logged(io, 'contact bounce'),
      menu.state)
io.down.discard(1)

# ---------------------------------------------------------------- whoever walks up finds the delivery on top
io, menu = make()
tap(io, menu, 4)
tap(io, menu, 4)
check('idle: the cursor stays where it is for now', last(io).split('\n')[2] == '>Undock', last(io))
run(io, menu, 29.0)
check('idle: still there before 30 s', last(io).split('\n')[2] == '>Undock', last(io))
run(io, menu, 2.0)
check('idle: after 30 s without a press the cursor is back on the top entry', last(io).split('\n')[0] == '>Go to food court', last(io))
io, menu = make()
tap(io, menu, 4)
tap(io, menu, 1)
check('Dock while docked: "Already docked", no goal sent', last(io) == 'Already docked' and not io.called('start_action'), last(io))
io, menu = make(docked=False)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 1)
check('Undock while not docked: "Not docked", no goal sent', last(io) == 'Not docked' and not io.called('start_action'), last(io))

# ---------------------------------------------------------------- the result screen comes from the mission's output
check('last_shown: the last [show] line wins, split into lines', mc.last_shown(
    '12:00 run=1 [show] Going | home\n12:01 run=1 [chime] x\n12:02 run=1 [show] Stopped\n12:03 run=1 result: x') == ['Stopped'])
check('last_shown: none in the text', mc.last_shown('nothing') is None and mc.last_shown('') is None)
io, menu = make(stack=True)
go_to_mission(io, menu)
io.files[io.called('start_mission')[0][2]] = 'x [show] Your food is here | >Done, thank you | Press button 1\n'
io.docked_v = True
io.mission_code = 0
run(io, menu, 1.0)
check('result: the mission\'s last screen is drawn', last(io) == 'Your food is here\n>Done, thank you\nPress button 1', last(io))
run(io, menu, 90.0)
check('result: food still waiting: the message stays, no return to the menu by itself', menu.state == 'result')

print(f'\n{count} checks, {fails} failure(s)')
sys.exit(1 if fails else 0)
