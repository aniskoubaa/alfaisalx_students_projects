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
HOME = '/home/u'
MENU_FILE = HOME + '/robot_code/menu/menu.yaml'
PROGRAM = HOME + '/robot_code/programs/lights.py'


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
        self.stamps, self.real = {}, {}                # menu file stamps; real paths that differ from the path (links)
        self.custom_code = -2                          # -2 = no own program; None = running; else exit code
        self.custom_started_at = 0.0
        self.custom_exit_after = None                  # s after the start the program ends by itself (None = never)
        self.custom_exit_code = 0
        self.custom_dies_on = ('INT',)                 # signals that end it
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

    def mission_interrupt(self):
        self.calls.append(('mission_interrupt',))
        return self.mission_code is None

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

    # own menu entries (menu file) and own programs
    def path_stamp(self, path):
        return self.stamps.get(path)

    def real_path(self, path):
        if path in self.real:
            return self.real[path]
        return path if path in self.files or path == HOME + '/robot_code' else None

    def custom_start(self, cmd, out_path):
        self.calls.append(('custom_start', tuple(cmd), out_path))
        self.custom_code = None
        self.custom_started_at = self.t

    def custom_poll(self):
        if self.custom_code is None and self.custom_exit_after is not None \
                and self.t - self.custom_started_at >= self.custom_exit_after:
            self.custom_code = self.custom_exit_code
        return mc.NO_CODE if self.custom_code == -2 else self.custom_code

    def custom_signal(self, name):
        self.calls.append(('custom_signal', name))
        if self.custom_code is None and name in self.custom_dies_on:
            self.custom_code = 130 if name == 'INT' else -15
        return True

    def set_menu_file(self, text):
        self.files[MENU_FILE] = text
        self.stamps[MENU_FILE] = (self.t, len(text))

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
check('trip: the menu draws the first screen while the mission loads', last(io) == 'Starting\nplease wait\n2 = Stop')
io.files[io.called('start_mission')[0][2]] = 'x [stop_button] armed\n'
run(io, menu, mc.ARMED_CHECK_S + 0.2)
check('trip: the armed line hands the screen to the mission', menu.state == 'mission')
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
io.files[io.called('start_mission')[0][2]] = 'x [stop_button] armed\n'
run(io, menu, mc.ARMED_CHECK_S + 0.2)
n0 = len(io.published)
run(io, menu, 30.0)
check('...and the menu is silent once the mission has loaded', len(io.published) == n0)
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

# ---------------------------------------------------------------- the seconds before the mission listens to the buttons
def loading(**kw):
    """Yes was pressed with the stack already up: the mission has been started and is loading."""
    io, menu = make(stack=True, **kw)
    tap(io, menu, 1)
    tap(io, menu, 1)
    return io, menu, io.called('start_mission')[0][2]


io, menu, out = loading()
check('mission started: the menu keeps the screen, 2 = Stop is on it', menu.state == 'loading'
      and last(io) == 'Starting\nplease wait\n2 = Stop', last(io))
tap(io, menu, 3)
tap(io, menu, 4)
tap(io, menu, 1)
check('...1, 3 and 4 do nothing and start no stock entry', menu.state == 'loading' and not io.called('mission_interrupt')
      and len(io.called('start_mission')) == 1 and last(io) == 'Starting\nplease wait\n2 = Stop', last(io))
check('...the mission gets no SIGINT by itself', not io.called('mission_interrupt'))
now = len(io.published)
run(io, menu, mc.REPUBLISH_S + 0.5)
check('...the text is published again while it loads (the stock node may have drawn over it)', len(io.published) > now)
tap(io, menu, 2)
check('button 2 while it loads: SIGINT, screen says Stopping', io.called('mission_interrupt') == [('mission_interrupt',)]
      and last(io) == 'Stopping\nplease wait', last(io))
tap(io, menu, 2)
run(io, menu, 1.0)
tap(io, menu, 2)
check('...more presses send no second SIGINT', len(io.called('mission_interrupt')) == 1)
io.mission_code = mc.EXIT_STOPPED
run(io, menu, 1.0)
check('...the mission exits 130 at the dock: Stopped, the stack is stopped', menu.state == 'result'
      and last(io) == 'Stopped' and len(io.called('stop_stack')) == 1, last(io))
tap(io, menu, 1)
check('...any press returns to the menu, no new trip', menu.state == 'menu' and len(io.called('start_mission')) == 1)

io, menu, out = loading()
tap(io, menu, 2)
io.mission_code = -9       # the real code would be -2 (SIGINT), which this fake reserves for "no mission"
run(io, menu, 1.0)
check('killed by the SIGINT before its handler was set (negative code): still Stopped, not "Trip ended"',
      menu.state == 'result' and last(io) == 'Stopped', last(io))

io, menu, out = loading(docked=True)
io.files[out] = 'x\n12:00:00 run=a [stop_button] armed\n'
run(io, menu, mc.ARMED_CHECK_S + 0.2)
now = len(io.published)
check('armed line in the output: the mission owns the screen and the buttons', menu.state == 'mission')
run(io, menu, mc.REPUBLISH_S + 1.0)
tap(io, menu, 2)
check('...the menu stays silent and sends no SIGINT, the mission handles button 2', len(io.published) == now
      and not io.called('mission_interrupt'))

io, menu, out = loading()
run(io, menu, mc.MISSION_LOAD_S + 1.0)
now = len(io.published)
check('no armed line ever: after MISSION_LOAD_S the menu leaves the screen to the mission', menu.state == 'mission')
run(io, menu, mc.REPUBLISH_S + 1.0)
check('...and stays silent, it cannot draw over a prompt', len(io.published) == now)

io, menu, out = loading()
io.files[out] = 'x REFUSING: battery too low\n'
io.mission_code = mc.EXIT_REFUSED
run(io, menu, 1.0)
check('mission refuses while it loads: Cannot start with the reason', lines(last(io))[0] == 'Cannot start'
      and not io.called('mission_interrupt'), last(io))

io, menu, out = loading()
tap(io, menu, 2)
io.mission_code = 0   # the SIGINT lost the race against a very short mission: keep the mission's own result
io.files[out] = 'x [show] Delivered\n'
run(io, menu, 1.0)
check('a known exit code is kept even after a SIGINT', menu.result_code == 0 and last(io) == 'Delivered', last(io))
io, menu, out = loading()
tap(io, menu, 2)
io.mission_code = 130
run(io, menu, 1.0)
tap(io, menu, 1)
tap(io, menu, 1)
tap(io, menu, 1)
check('the next trip after a stop while loading starts clean', menu.state == 'loading'
      and last(io) == 'Starting\nplease wait\n2 = Stop', last(io))

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

# ================================================================ the menu file (own entries, hidden entries)
BASE = '''
entries:
  - id: lights
    label: Lights demo
    program: ~/robot_code/programs/lights.py
    after: dock
'''


def make_file(text=None, with_program=True, **kw):
    io = FakeIO(**kw)
    if with_program:
        io.files[PROGRAM] = 'print(1)'
    if text is not None:
        io.set_menu_file(text)
    menu = mc.Menu(io, ROUTE_DIR, OUT_DIR, menu_file=MENU_FILE, home=HOME)
    menu.start()
    menu.step()
    return io, menu


def screen_lines(io):
    return last(io).split('\n')


def goto_entry(io, menu, label):
    """Press 4 until the cursor is on the entry with this label."""
    for _ in range(20):
        if any(x == '>' + label for x in menu.screen()):
            return
        tap(io, menu, 4)


# ---- missing, invalid and valid files
io, menu = make_file(None)
check('menu file missing: today\'s menu, the problem is only logged, no note', menu.state == 'menu'
      and [x[1:] for x in screen_lines(io)] == ['Go to food court', 'Dock', 'Undock', 'EStop', 'Wall Follow Left']
      and logged(io, 'no menu file'), (menu.state, last(io)))
io, menu = make_file('hide: [dock]\n')
check('menu file invalid: a short note at start, the error is logged', menu.state == 'note' and screen_lines(io)[0] == 'Menu file error'
      and fits([last(io)]) and logged(io, 'menu file rejected') and logged(io, 'locked'), (menu.state, last(io)))
tap(io, menu, 3)
check('menu file invalid: a press dismisses the note and the menu is exactly today\'s menu', menu.state == 'menu'
      and menu.keys == list(mc.ENTRIES) and last(io).split('\n')[0] == '>Go to food court', (menu.state, last(io)))
io, menu = make_file('entries: [unclosed')
check('menu file broken YAML: standard menu and a note, no crash', menu.state == 'note' and menu.keys == list(mc.ENTRIES))
io, menu = make_file(BASE)
check('menu file valid: own entry below Dock', menu.state == 'menu' and screen_lines(io) == ['>Go to food court', ' Dock', ' Lights demo', ' Undock', ' EStop'],
      screen_lines(io))
check('menu file valid: the trip entry is first and the log says what was loaded', menu.keys[0] == 'trip' and logged(io, 'menu file loaded'))
io, menu = make_file('hide: [undock, wall_left, wall_right, help]\n')
check('hide: the hidden entries are gone, Dock EStop Power stay', menu.keys == ['trip', 'dock', 'estop', 'power']
      and screen_lines(io) == ['>Go to food court', ' Dock', ' EStop', ' Power'], screen_lines(io))
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 4)
check('hide: the cursor stops on the last entry', screen_lines(io)[-1] == '>Power', screen_lines(io))
many = 'entries:\n' + ''.join(f'  - {{id: e{i}, label: Entry {i}, program: a.py}}\n' for i in range(8))
io, menu = make_file(many)
for _ in range(15):
    tap(io, menu, 4)
check('16 entries: scrolling shows 5 lines and reaches the last one', len(screen_lines(io)) == 5 and screen_lines(io)[-1] == '>Entry 7', screen_lines(io))
io, menu = make_file(BASE, docked=False)
check('trip label still follows the dock status with a menu file', screen_lines(io)[0] == '>Back to the lab', screen_lines(io))

# ---- pick up changes when the menu returns to the top menu
io, menu = make_file(None)
io.set_menu_file(BASE)
run(io, menu, 5.0)
check('reload: a change is not read while the menu just sits there', 'lights' not in menu.keys)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 4)
tap(io, menu, 1)         # Help
check('reload: help screen is up', menu.state == 'help')
tap(io, menu, 1)         # any press: back to the menu
check('reload: the file is read when the menu comes back, no restart', menu.state == 'menu' and 'lights' in menu.keys
      and logged(io, 'menu file loaded'), (menu.state, menu.keys))
n = len([1 for _, line in io.logs if 'menu file loaded' in line])
tap(io, menu, 1)
tap(io, menu, 1)
check('reload: the same file (same stamp) is not read again', len([1 for _, line in io.logs if 'menu file loaded' in line]) == n)
io, menu = make_file(BASE)
goto_entry(io, menu, 'Lights demo')
io.set_menu_file(BASE.replace('Lights demo', 'Lights show').replace('after: dock', 'after: trip'))
tap(io, menu, 1)         # select: asks nothing, starts the program (no confirm)
check('reload: not while the program runs, the screen keeps the old label', menu.state == 'custom'
      and screen_lines(io)[0] == 'Lights demo', (menu.state, last(io)))
io.custom_exit_after, io.custom_exit_code = 0.5, 0
run(io, menu, 1.0)
tap(io, menu, 1)         # any press: back to the menu, the new file is read now
check('reload: after the program the menu reads the file again', menu.state == 'menu' and 'Lights show' in menu.labels(), menu.labels())
io, menu = make_file(BASE)
goto_entry(io, menu, 'Lights demo')
io.set_menu_file(BASE.replace('after: dock', 'after: trip'))
run(io, menu, 31.0)      # idle: the cursor falls back to the top, and the menu file is read again
check('reload: the idle return to the top reads the file too', menu.keys[:2] == ['trip', 'lights'] and menu.cursor == 0, menu.keys)
io, menu = make_file(BASE)
goto_entry(io, menu, 'Lights demo')
io.set_menu_file(BASE.replace('after: dock', 'after: trip'))
tap(io, menu, 3)         # a press that does not leave the menu does not reload
check('reload: moving the cursor in the menu does not reload', menu.keys[2] == 'lights')
io, menu = make_file(BASE)
io.set_menu_file('hide: [trip]\n')
goto_entry(io, menu, 'Help')
tap(io, menu, 1)
tap(io, menu, 1)
check('reload: a file that became invalid gives a note and today\'s menu', menu.state == 'note' and screen_lines(io)[0] == 'Menu file error'
      and menu.keys == list(mc.ENTRIES), (menu.state, menu.keys))
io, menu = make_file(BASE)
del io.files[MENU_FILE]
del io.stamps[MENU_FILE]
goto_entry(io, menu, 'Help')
tap(io, menu, 1)
tap(io, menu, 1)
check('reload: a file that was removed gives today\'s menu, no note', menu.state == 'menu' and menu.keys == list(mc.ENTRIES)
      and logged(io, 'menu file removed'), (menu.state, menu.keys))
io, menu = make_file(BASE)
goto_entry(io, menu, 'Dock')
io.set_menu_file('hide: [wall_left]\n')
tap(io, menu, 1)         # Dock: the robot is docked, a note comes up; any press returns to the menu
tap(io, menu, 1)
check('reload: after a note the new file is in use and the cursor is on a real entry', 'wall_left' not in menu.keys
      and menu.cursor < len(menu.keys), (menu.state, menu.keys, menu.cursor))
check('reload: the cursor stays on the same entry when it is still there', menu.keys[menu.cursor] == 'dock', (menu.cursor, menu.keys))

# ---- running an own entry
def lights(io, menu):
    goto_entry(io, menu, 'Lights demo')
    tap(io, menu, 1)


io, menu = make_file(BASE)
lights(io, menu)
cmds = io.called('custom_start')
check('run: no question for a harmless program, the program starts at once', menu.state == 'custom' and len(cmds) == 1, menu.state)
check('run: the command is python3, the path under robot_code, no shell', cmds[0][1] == ('python3', PROGRAM), cmds[0][1])
check('run: output file menu_custom_<date>_<time>.out in the log folder', cmds[0][2].startswith(OUT_DIR + '/menu_custom_')
      and cmds[0][2].endswith('.out'), cmds[0][2])
check('run: the screen shows the label and 2 = Stop', screen_lines(io) == ['Lights demo', 'Running', '2 = Stop'], screen_lines(io))
check('run: no delivery mission and no stack were started', not io.called('start_mission') and not io.called('start_stack'))
tap(io, menu, 1)
tap(io, menu, 3)
tap(io, menu, 4)
check('run: buttons 1, 3 and 4 do nothing while it runs', menu.state == 'custom' and not io.called('custom_signal'))
tap(io, menu, 2)
check('run: button 2 sends SIGINT once and the screen says Stopping', io.called('custom_signal') == [('custom_signal', 'INT')]
      and screen_lines(io) == ['Lights demo', 'Stopping', 'please wait'] or menu.state == 'result', screen_lines(io))
io, menu = make_file(BASE)
io.custom_dies_on = ()
lights(io, menu)
tap(io, menu, 2)
tap(io, menu, 2)
tap(io, menu, 2)
check('run: more presses of 2 send no second SIGINT', io.called('custom_signal') == [('custom_signal', 'INT')], io.calls)
check('run: the screen says Stopping while it ends', screen_lines(io) == ['Lights demo', 'Stopping', 'please wait'], screen_lines(io))
run(io, menu, 15.0)
check('run: still running 15 s after SIGINT: SIGTERM once', ('custom_signal', 'TERM') in io.calls and io.calls.count(('custom_signal', 'TERM')) == 1, io.calls)
run(io, menu, 10.0)
check('run: still running 10 s after that: SIGKILL once', io.calls.count(('custom_signal', 'KILL')) == 1, io.calls)
io.custom_code = -9
run(io, menu, 1.0)
check('run: killed program: result screen says Stopped with the exit code', menu.state == 'result'
      and screen_lines(io) == ['Lights demo', 'Stopped', 'Exit code -9'], screen_lines(io))

io, menu = make_file(BASE)
io.custom_exit_after, io.custom_exit_code = 3.0, 0
lights(io, menu)
run(io, menu, 4.0)
check('result: exit 0 = Finished with the exit code', menu.state == 'result' and screen_lines(io) == ['Lights demo', 'Finished', 'Exit code 0'], screen_lines(io))
check('result: the menu does not stop the navigation stack for an own program', not io.called('stop_stack'))
run(io, menu, 26.0)
check('result: stays 30 s', menu.state == 'result')
run(io, menu, 4.0)
check('result: back to the menu by itself after 30 s', menu.state == 'menu')
io, menu = make_file(BASE)
io.custom_exit_after, io.custom_exit_code = 3.0, 7
lights(io, menu)
run(io, menu, 4.0)
check('result: a non-zero exit code = Failed with the code', screen_lines(io) == ['Lights demo', 'Failed', 'Exit code 7'], screen_lines(io))
tap(io, menu, 3)
check('result: any press returns to the menu', menu.state == 'menu')
io, menu = make_file(BASE)
lights(io, menu)
tap(io, menu, 2)
run(io, menu, 1.0)
check('result: ended by button 2 = Stopped with the exit code', screen_lines(io) == ['Lights demo', 'Stopped', 'Exit code 130'], screen_lines(io))

# ---- timeout and the STOP file
io, menu = make_file(BASE.replace('after: dock', 'after: dock\n    timeout: 20'))
lights(io, menu)
run(io, menu, 19.0)
check('timeout: nothing before the time is up', not io.called('custom_signal'))
run(io, menu, 2.0)
check('timeout: SIGINT once, result says Timed out', io.called('custom_signal') == [('custom_signal', 'INT')]
      and screen_lines(io) == ['Lights demo', 'Timed out', 'Exit code 130'], (io.calls, screen_lines(io)))
io, menu = make_file(BASE)
lights(io, menu)
io.stop_file = True
run(io, menu, 1.0)
check('STOP file while it runs: SIGINT once, result Stopped', io.called('custom_signal') == [('custom_signal', 'INT')]
      and screen_lines(io)[1] == 'Stopped' and logged(io, 'stopfile'), (io.calls, screen_lines(io)))

# ---- confirm and moving programs
CONF = BASE.replace('after: dock', 'after: dock\n    confirm: true')
io, menu = make_file(CONF)
lights(io, menu)
check('confirm: asks first, nothing starts', menu.state == 'confirm' and screen_lines(io) == ['Lights demo?', '1 = Yes', '2 = No']
      and not io.called('custom_start'), screen_lines(io))
tap(io, menu, 2)
check('confirm: 2 = No goes back, nothing started', menu.state == 'menu' and not io.called('custom_start'))
lights(io, menu)
tap(io, menu, 1)
check('confirm: 1 = Yes starts the program', menu.state == 'custom' and len(io.called('custom_start')) == 1)
LONG = BASE.replace('Lights demo', 'L' * 17).replace('after: dock', 'after: dock\n    confirm: true')
io, menu = make_file(LONG)
goto_entry(io, menu, 'L' * 17)
tap(io, menu, 1)
check('confirm: a 17 character label still fits the title (18)', fits([last(io)]) and screen_lines(io)[0] == 'L' * 17 + '?', screen_lines(io))
MOVE = BASE.replace('after: dock', 'after: dock\n    moves: true')
io, menu = make_file(MOVE, docked=False)
lights(io, menu)
check('moves: always asks, and says the robot will move', menu.state == 'confirm' and screen_lines(io)
      == ['Lights demo?', 'Robot will move', '1 = Yes', '2 = No'], screen_lines(io))
tap(io, menu, 1)
check('moves: Yes while undocked starts it', menu.state == 'custom')
io, menu = make_file(MOVE, docked=True)
lights(io, menu)
check('moves: refused while docked ("Undock first"), nothing asked or started', menu.state == 'note' and screen_lines(io) == ['Undock first']
      and not io.called('custom_start'), (menu.state, last(io)))
io, menu = make_file(MOVE.replace('moves: true', 'undocks: true'), docked=True)
lights(io, menu)
check('undocks: a moving program that undocks itself may start while docked (after a question)', menu.state == 'confirm', menu.state)
tap(io, menu, 1)
check('undocks: Yes starts it', menu.state == 'custom')
io, menu = make_file(MOVE, docked=None)
lights(io, menu)
check('moves: refused while the dock status is unknown', menu.state == 'note' and screen_lines(io)[0] == 'Waiting for', last(io))
io, menu = make_file(BASE, docked=None)
lights(io, menu)
check('harmless program: dock status does not matter', menu.state == 'custom')
io, menu = make_file(MOVE, docked=False)
lights(io, menu)
io.docked_v = True
tap(io, menu, 1)
check('moves: the dock status is checked again at Yes', menu.state == 'note' and not io.called('custom_start'), (menu.state, last(io)))

# ---- refusals
io, menu = make_file(BASE)
io.stop_file = True
lights(io, menu)
check('refused: ~/STOP exists', menu.state == 'note' and screen_lines(io)[0] == 'STOP file is set' and not io.called('custom_start'), last(io))
io, menu = make_file(BASE)
io.mission_code = None
lights(io, menu)
check('refused: a delivery is running', menu.state == 'note' and screen_lines(io)[:2] == ['A delivery', 'is running']
      and not io.called('custom_start'), last(io))
io, menu = make_file(BASE, with_program=False)
lights(io, menu)
check('refused: the program file is missing', menu.state == 'note' and screen_lines(io)[0] == 'Program not found'
      and not io.called('custom_start'), last(io))
io, menu = make_file(BASE)
io.real[PROGRAM] = '/etc/evil.py'
lights(io, menu)
check('refused: a link that leads outside robot_code', menu.state == 'note' and screen_lines(io)[0] == 'Not allowed'
      and not io.called('custom_start'), last(io))
io, menu = make_file(BASE)
io.real[HOME + '/robot_code'] = HOME + '/robot_code'
io.real[PROGRAM] = HOME + '/robot_code/real/lights.py'
lights(io, menu)
check('allowed: a link that stays inside robot_code', menu.state == 'custom' and fits(io.published and [last(io)] or []), (menu.state, last(io)))
io, menu = make_file(CONF)
lights(io, menu)
io.stop_file = True
tap(io, menu, 1)
check('refused: ~/STOP appears while the question is on the screen', menu.state == 'note' and not io.called('custom_start'), (menu.state, last(io)))
io, menu = make_file(CONF)
lights(io, menu)
io.mission_code = None
tap(io, menu, 1)
check('refused: a delivery starts while the question is on the screen', menu.state == 'note' and not io.called('custom_start'))
io, menu = make_file(BASE, stack=True)
io.custom_code = None
tap(io, menu, 1)
check('a trip is refused while an own program runs', menu._trip_problem('full') == ['A program', 'is running'], menu._trip_problem('full'))

# ---- the old menu still works when a file exists but changes nothing
io, menu = make_file('version: 1\n')
check('empty menu file: exactly today\'s menu', menu.keys == list(mc.ENTRIES) and screen_lines(io)[0] == '>Go to food court')

# ---- the example file
EXAMPLE = os.path.join(DELIVERY, 'menu.example.yaml')
with open(EXAMPLE, encoding='utf-8') as f:
    ex = mc.menu_config.parse(f.read(), HOME)
check('menu.example.yaml is valid', ex.ok, ex.errors)

# ---- the ROS adapter's own-program runner (real processes, so only where process groups exist)
check('parse_args: --menu-file and the default (env DELIVERY_MENU_FILE, else ~/robot_code/menu/menu.yaml)',
      dmenu.parse_args(['--menu-file', '/x/m.yaml']).menu_file == '/x/m.yaml' and dmenu.parse_args([]).menu_file is None
      and dmenu.resolve_menu_file({}, '/home/u') == MENU_FILE and dmenu.resolve_menu_file({'DELIVERY_MENU_FILE': '/y.yaml'}, '/home/u') == '/y.yaml')
if os.name == 'posix':
    import tempfile
    import time as _time
    with tempfile.TemporaryDirectory() as tmp:
        polite = os.path.join(tmp, 'polite.py')
        stubborn = os.path.join(tmp, 'stubborn.py')
        with open(polite, 'w') as f:
            f.write('import os, signal, sys, time\nsignal.signal(signal.SIGINT, lambda *a: (print("got int", os.getcwd()), sys.exit(5)))\n'
                    'print("ready", sys.argv[1:], flush=True)\nwhile True: time.sleep(0.05)\n')
        with open(stubborn, 'w') as f:
            f.write('import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
                    'while True: time.sleep(0.05)\n')
        out = os.path.join(tmp, 'o.out')

        def wait_code(runner, seconds=10.0):
            end = _time.time() + seconds
            while _time.time() < end:
                if runner.poll() is not None:
                    return runner.poll()
                _time.sleep(0.05)
            return None

        runner = dmenu.CustomRunner()
        check('runner: no program started = NO_CODE and signals are refused', runner.poll() == mc.NO_CODE and runner.signal('INT') is False)
        runner.start(['python3', polite, 'a', '3'], out)
        check('runner: running = None', runner.poll() is None)
        _time.sleep(0.5)
        check('runner: SIGINT reaches the program, its exit code comes back', runner.signal('INT') is True and wait_code(runner) == 5, runner.poll())
        with open(out) as f:
            text = f.read()
        check('runner: output goes to the file, the folder of the program is the working folder, args kept',
              "ready ['a', '3']" in text and 'got int ' + os.path.realpath(tmp) in text, text)
        check('runner: a finished program cannot be signalled again', runner.signal('INT') is False)
        runner.start(['python3', stubborn], out)
        _time.sleep(0.5)
        runner.signal('INT')
        runner.signal('TERM')
        _time.sleep(0.5)
        check('runner: a program that ignores SIGINT and SIGTERM is still running', runner.poll() is None)
        runner.signal('KILL')
        check('runner: SIGKILL ends it (exit code -9)', wait_code(runner) == -9, runner.poll())
else:
    print('SKIP runner tests: they need process groups (Linux / macOS)')

print(f'\n{count} checks, {fails} failure(s)')
sys.exit(1 if fails else 0)
