"""Pure logic of the TurtleBot 4 front-panel menu for the delivery system (no ROS, no clock of its own, no files):
the screens, the buttons and the state machine. Run on the robot through delivery_menu.py, tested off the robot with a
fake MenuIO and a virtual clock in tests/offline/test_delivery_menu.py.

Why it exists: the stock menu of turtlebot4_node has a fixed list of entries and changing it needs sudo. Publishing
std_msgs/String on /hmi/display/message puts the node in "menu override": it shows the text, buttons 1, 3 and 4 do
nothing, and button 2 (Back) clears the override and shows the stock menu. So this program draws its own menu through
that channel and publishes it again right after every button press, which means it owns the screen and the buttons.

Buttons (same meaning as the stock menu): 1 = Select, 2 = Back, 3 = Up, 4 = Down. A press is the change False -> True.
Entries, top to bottom: TRIP ("Go to food court" when the robot is docked, "Back to the lab" when it is not), Dock,
Undock, EStop, Wall Follow Left, Wall Follow Right, Power, Help. Five entries show at a time; Back returns to the top.

Screens and states:
  menu      the entries with a ">" in front of the chosen one.
  confirm   TRIP and Power ask "1 = Yes / 2 = No". Nothing happens without that second press.
  note      a short text (a result or a refusal) that goes back to the menu after a few seconds or on any press.
  help      what the buttons do.
  action    Dock, Undock or Wall Follow is running; 2 = Cancel.
  starting  the navigation stack is starting (about a minute); 2 = Cancel stops it again.
  mission   delivery_mission.py runs as a child process in its own session. The mission owns the screen and the
            buttons: this program publishes nothing and ignores the buttons (it only logs them).
  result    the mission ended. The mission's last text (from its output file, or a short text for the exit code) stays
            on the screen, drawn by this program so button 2 cannot wipe it; any press returns to the menu. Docked and
            exit 0 or 4: back to the menu by itself after RESULT_RETURN_S, unless the text says the food still waits.
            Exit 2 (refused) shows "Cannot start" and the reason from the output file instead.
After a mission that ends while the robot is docked, the navigation stack is stopped (stop_stack.sh, in the
background). If the robot is not docked the stack keeps running, so "Back to the lab" works afterwards. The stack is
never started away from the dock: AMCL would be told the robot is on the dock.

Every press and every change of state goes to the menu log through MenuIO.log (read it to confirm
that a physical press happened).
"""
import abc
import re
import textwrap
import time

# ---------------------------------------------------------------- constants (units in comments)
DISPLAY_LINES = 5            # lines on the TurtleBot 4 display
DISPLAY_CHARS = 18           # characters per line
POLL = 0.1                   # s, step of the main loop
DEBOUNCE_S = 0.2             # s, a second press of any button this soon after a press is contact bounce: not counted
REPUBLISH_S = 3.0            # s, publish the current screen again this often (the stock node may restart)
REDRAW_AFTER_S = 0.6         # s, after a press or a release publish at every step: the stock node acts on button 2 when
                             # it is RELEASED (tested 2026-11-06), so a redraw at the press alone is wiped straight away
IDLE_TOP_S = 30.0            # s, with no press for this long the cursor goes back to the top entry (the delivery)
NOTE_S = 3.0                 # s, a result text stays this long, then the menu comes back
REFUSED_S = 10.0             # s, a refusal ("Cannot start" and the reason) stays this long
RESULT_RETURN_S = 60.0       # s, after a docked, successful mission the menu comes back by itself
STACK_START_TIMEOUT = 150.0  # s, start_stack.sh must be done within this time
ACTION_TIMEOUT = {'dock': 120.0, 'undock': 60.0, 'wall_left': 20.0, 'wall_right': 20.0}   # s, then cancel
WALL_FOLLOW_SECONDS = 10     # s, max_runtime of the wall follow goal (same as the stock menu)
NO_CODE = -1                 # exit code of a mission whose exit status is unknown (it was started by an earlier menu)
ROUTE_FILE = 'route.yaml'
DEFAULT_ROUTE_DIR = '~/robot_code/routes/current'   # env DELIVERY_ROUTE_DIR replaces it
DEFAULT_OUT_DIR = '~/robot_code/logs/delivery'      # menu.log and menu_<date>_<time>.out go here
EXIT_REFUSED, EXIT_DELIVERED, EXIT_NO_FOOD, EXIT_ALARM, EXIT_STOPPED = 2, 0, 4, 3, 130   # same as delivery_core

ENTRIES = ('trip', 'dock', 'undock', 'estop', 'wall_left', 'wall_right', 'power', 'help')
LABELS = {'dock': 'Dock', 'undock': 'Undock', 'estop': 'EStop', 'wall_left': 'Wall Follow Left',
          'wall_right': 'Wall Follow Right', 'power': 'Power', 'help': 'Help'}
TRIP_LABELS = {'full': 'Go to food court', 'home': 'Back to the lab'}
CONFIRM_TITLES = {'full': 'Go to food court?', 'home': 'Back to the lab?', 'power': 'Power off?'}
ACTION_TEXT = {   # while running, if it worked, if it failed
    'dock': (['Docking...'], 'Docked', 'Dock failed'),
    'undock': (['Undocking...'], 'Undocked', 'Undock failed'),
    'wall_left': (['Wall following', 'left side'], 'Wall follow done', 'Wall follow failed'),
    'wall_right': (['Wall following', 'right side'], 'Wall follow done', 'Wall follow failed'),
}
HELP_LINES = ['1 Select  2 Back', '3 Up  4 Down', 'Top = delivery']
STARTING_LINES = ['Starting', 'about 1 minute', '2 = Cancel']
MISSION_STARTING_LINES = ['Starting', 'please wait', '2 = Stop']   # same text the mission shows first
RESULT_TEXT = {EXIT_DELIVERED: ['Delivery done'], EXIT_NO_FOOD: ['Back at the lab'], EXIT_ALARM: ['NEED HELP'],
               EXIT_STOPPED: ['Stopped'], NO_CODE: ['Trip ended']}
PUBLISHING = ('menu', 'confirm', 'note', 'help', 'action', 'starting', 'result')   # this program draws the screen


# ---------------------------------------------------------------- pure helpers
def fit(lines):
    """The wire text for a list of lines: at most 5 lines of 18 characters, leading spaces kept (the menu needs them),
    lines joined with newline (core.display_wire turns the newlines into padding)."""
    return '\n'.join(str(x)[:DISPLAY_CHARS] for x in list(lines)[:DISPLAY_LINES])


def route_dir_from(environ, home):
    """The route folder: env DELIVERY_ROUTE_DIR (with ~ expanded), else ~/robot_code/routes/current."""
    value = environ.get('DELIVERY_ROUTE_DIR') or DEFAULT_ROUTE_DIR
    if value.startswith('~'):
        value = home.rstrip('/') + value[1:]
    return value


def route_file(route_dir):
    return route_dir.rstrip('/') + '/' + ROUTE_FILE


def mission_args(route_dir, kind):
    """Arguments of delivery_mission.py (after the script name) for the trip kind 'full' or 'home'."""
    args = ['--route', route_file(route_dir), '--yes']
    if kind == 'home':
        args += ['--trip', 'home', '--allow-undocked']
    return args


def out_name(wall_time):
    """File name of the output file of one trip: menu_<date>_<time>.out"""
    return time.strftime('menu_%Y%m%d_%H%M%S.out', time.localtime(wall_time))


_REASON_PATTERNS = (re.compile(r'(?:REFUSING|SETUP FAILED|ERROR):\s*(.+)$'),
                    re.compile(r'result: refused \(exit 2\)\s*(.+)$'))


def refusal_reason(text):
    """The last reason in the output of delivery_mission.py or start_stack.sh ("REFUSING: ...", "SETUP FAILED: ...",
    "ERROR: ...", "result: refused (exit 2) ..."), or None."""
    for line in reversed(str(text).splitlines()):
        for pattern in _REASON_PATTERNS:
            m = pattern.search(line.strip())
            if m:
                return m.group(1).strip()
    return None


_SHOW_PATTERN = re.compile(r'\[show\] (.+)$')


def last_shown(text):
    """The lines of the last screen delivery_mission.py logged ("[show] Stopped | ..."), or None."""
    for line in reversed(str(text).splitlines()):
        m = _SHOW_PATTERN.search(line.rstrip())
        if m:
            return m.group(1).split(' | ')
    return None


def refusal_lines(reason):
    """'Cannot start' plus the reason cut to the screen: 4 lines of 18 characters."""
    words = ' '.join((reason or 'see the output file').split())
    return ['Cannot start'] + textwrap.wrap(words, width=DISPLAY_CHARS, break_long_words=True)[:DISPLAY_LINES - 1]


def menu_lines(labels, cursor, top):
    """The 5 visible entries; '>' in front of the chosen one, a space in front of the others."""
    return [('>' if i == cursor else ' ') + labels[i] for i in range(top, min(top + DISPLAY_LINES, len(labels)))]


def scroll(cursor, top, count, step):
    """Move the cursor by step (+1 down, -1 up) like the stock menu: no wrap, the window follows the cursor."""
    cursor = max(0, min(count - 1, cursor + step))
    if cursor < top:
        top = cursor
    if cursor >= top + DISPLAY_LINES:
        top = cursor - DISPLAY_LINES + 1
    return cursor, top


def new_presses(prev, cur):
    """Buttons (1..4) that went from False to True between two samples. prev None = first sample = no press."""
    if prev is None or cur is None:
        return []
    return [i + 1 for i in range(4) if cur[i] and not prev[i]]


# ---------------------------------------------------------------- I/O interface
class MenuIO(abc.ABC):
    """What the menu needs from the robot. The ROS adapter (delivery_menu.py) and the test fake implement all of it.
    now() is a monotonic clock in seconds; sleep(s) waits and lets ROS callbacks run (in tests it advances a virtual
    clock). Getters return None when no data has arrived yet. Start methods return at once; *_poll methods poll."""

    @abc.abstractmethod
    def now(self): ...

    @abc.abstractmethod
    def wall_time(self):
        """Seconds since the epoch (for file names)."""

    @abc.abstractmethod
    def sleep(self, seconds): ...

    @abc.abstractmethod
    def publish(self, text):
        """Publish text on /hmi/display/message (lines separated by newline, at most 5 x 18 characters)."""

    @abc.abstractmethod
    def buttons(self):
        """Latest state of the 4 buttons as a list of bools, or None. The adapter latches a press that was released
        again between two calls, so a quick tap is not lost."""

    @abc.abstractmethod
    def docked(self):
        """True / False from /dock_status, or None if unknown."""

    @abc.abstractmethod
    def wheels_enabled(self):
        """True / False from /wheel_status, or None if unknown."""

    @abc.abstractmethod
    def stop_file_exists(self):
        """True while ~/STOP exists."""

    @abc.abstractmethod
    def path_exists(self, path): ...

    @abc.abstractmethod
    def read_text(self, path):
        """The text of a file ('' if it cannot be read)."""

    @abc.abstractmethod
    def log(self, line):
        """Append a line to the menu log (the adapter adds the time stamp)."""

    @abc.abstractmethod
    def stack_running(self):
        """True while the navigation stack runs (pgrep -f delivery_stack.launch.py)."""

    @abc.abstractmethod
    def start_stack(self, route_dir, out_path):
        """Start `bash robot/start_stack.sh nav --route-dir DIR` (it detaches the stack and returns), output appended
        to out_path."""

    @abc.abstractmethod
    def stack_poll(self):
        """None while start_stack.sh runs, else its exit code."""

    @abc.abstractmethod
    def stack_cancel(self):
        """Stop start_stack.sh if it still runs."""

    @abc.abstractmethod
    def stop_stack_background(self):
        """Run robot/stop_stack.sh in the background."""

    @abc.abstractmethod
    def start_mission(self, args, out_path):
        """Start delivery_mission.py with these arguments in its own session (it must survive this program), output
        appended to out_path."""

    @abc.abstractmethod
    def mission_poll(self):
        """None while a delivery mission runs (the child started here, or any other one found with pgrep), else its
        exit code, or NO_CODE when the code is unknown."""

    @abc.abstractmethod
    def start_action(self, kind):
        """Send the goal for 'dock', 'undock', 'wall_left' or 'wall_right'. False if it cannot be sent."""

    @abc.abstractmethod
    def action_poll(self):
        """None while the goal runs, True if it succeeded, False if it failed or was rejected."""

    @abc.abstractmethod
    def action_cancel(self): ...

    @abc.abstractmethod
    def call_estop(self, on):
        """Call the e_stop service with e_stop_on=on. False if it cannot be called."""

    @abc.abstractmethod
    def call_power(self):
        """Call the robot_power service (powers the robot off). False if it cannot be called."""


# ---------------------------------------------------------------- the menu
class Menu:
    """The state machine. start() once, then step() every POLL seconds (or run())."""

    def __init__(self, io, route_dir, out_dir=DEFAULT_OUT_DIR):
        self.io, self.route_dir, self.out_dir = io, route_dir, out_dir
        self.state = 'menu'
        self.cursor = self.top = 0
        self.prev_buttons = None
        self.last_press = None        # time of the last press that counted (DEBOUNCE_S)
        self.last_pub = None          # time of the last publish, None = nothing published since the screen went silent
        self.last_text = None
        self.note_lines, self.note_until = [], 0.0
        self.pending = None          # what the confirm screen is about: 'full', 'home' or 'power'
        self.action = None           # kind of the running action
        self.action_deadline = 0.0
        self.stack_deadline = 0.0
        self.out_path = None
        self.result_code = None
        self.result_at = 0.0
        self.result_lines = []
        self.redraw_until = 0.0

    # ---- helpers
    def _log(self, text):
        self.io.log(text)

    def _goto(self, state):
        if state != self.state:
            self._log(f'state {self.state} -> {state}')
        self.state = state
        if state not in PUBLISHING:
            self.last_pub = self.last_text = None

    def _note(self, lines, seconds=NOTE_S):
        self.note_lines, self.note_until = list(lines), self.io.now() + seconds
        self._goto('note')

    def _to_menu(self, keep_cursor=True):
        if not keep_cursor:
            self.cursor = self.top = 0
        self.pending = self.action = None
        self._goto('menu')

    def trip_kind(self):
        """'full' when the robot is docked, 'home' when it is not, None while /dock_status is unknown."""
        docked = self.io.docked()
        return None if docked is None else ('full' if docked else 'home')

    def labels(self):
        kind = self.trip_kind() or 'full'
        return [TRIP_LABELS[kind] if key == 'trip' else LABELS[key] for key in ENTRIES]

    def screen(self):
        """The lines of the current screen (only for the states in PUBLISHING)."""
        if self.state == 'menu':
            return menu_lines(self.labels(), self.cursor, self.top)
        if self.state == 'confirm':
            return [CONFIRM_TITLES[self.pending], '1 = Yes', '2 = No']
        if self.state == 'note':
            return self.note_lines
        if self.state == 'help':
            return HELP_LINES
        if self.state == 'action':
            return ACTION_TEXT[self.action][0] + ['2 = Cancel']
        if self.state == 'starting':
            return STARTING_LINES
        if self.state == 'result':
            return self.result_lines
        return []

    # ---- start
    def start(self):
        """A mission that is already running (this program was restarted) is adopted: stay silent."""
        self._log('menu started, route dir ' + self.route_dir)
        if self.io.mission_poll() is None:
            self._log('a delivery mission is already running: staying silent')
            self._goto('mission')
        else:
            self._goto('menu')

    # ---- one step
    def step(self):
        io = self.io
        now = io.now()
        sample = io.buttons()
        pressed = new_presses(self.prev_buttons, sample)
        released = self.prev_buttons is not None and sample is not None and any(self.prev_buttons) and not any(sample)
        if pressed or released:
            self.redraw_until = now + REDRAW_AFTER_S
        if sample is not None:
            self.prev_buttons = [bool(b) for b in sample[:4]] + [False] * (4 - len(sample))
        if pressed and self.last_press is not None and now - self.last_press < DEBOUNCE_S - 1e-6:
            self._log(f'ignored as contact bounce: {pressed}')
            pressed = []
        if pressed:
            self.last_press = now
        if (self.state == 'menu' and self.cursor != 0 and self.last_press is not None
                and now - self.last_press >= IDLE_TOP_S):
            self._log('idle: cursor back to the top')
            self.cursor = self.top = 0
        for number in pressed:
            self._log(f'press {number} in state {self.state}')
            self._on_press(number)
        self._poll(now)
        if self.state in PUBLISHING:
            text = fit(self.screen())
            if (pressed or now < self.redraw_until or text != self.last_text or self.last_pub is None
                    or now - self.last_pub >= REPUBLISH_S):
                io.publish(text)     # after every press and release (2 clears the override), on change, every 3 s
                self.last_pub, self.last_text = now, text

    def run(self, should_stop):
        """Loop until should_stop() says so. should_stop is checked every POLL seconds."""
        self.start()
        while not should_stop():
            self.step()
            self.io.sleep(POLL)

    # ---- buttons
    def _on_press(self, number):
        state = self.state
        if state == 'menu':
            if number == 3:
                self.cursor, self.top = scroll(self.cursor, self.top, len(ENTRIES), -1)
            elif number == 4:
                self.cursor, self.top = scroll(self.cursor, self.top, len(ENTRIES), +1)
            elif number == 2:
                self.cursor = self.top = 0
            elif number == 1:
                self._select(ENTRIES[self.cursor])
        elif state == 'confirm':
            if number == 1:
                self._confirmed()
            elif number == 2:
                self._to_menu()
        elif state in ('note', 'help'):
            self._to_menu()
        elif state == 'action':
            if number == 2:
                self._log(f'cancel {self.action}')
                self.io.action_cancel()
                self._note(['Cancelled'])
        elif state == 'starting':
            if number == 2:
                self._cancel_start()
        elif state == 'result':
            self._to_menu(keep_cursor=False)
        # state == 'mission': the mission owns the buttons; the press is only logged

    def _select(self, key):
        if key == 'trip':
            kind = self.trip_kind()
            if kind is None:
                self._note(['Waiting for', 'dock status'])
                return
            problem = self._trip_problem(kind)
            if problem:
                self._note(problem, REFUSED_S)
                return
            self.pending = kind
            self._goto('confirm')
        elif key == 'power':
            self.pending = 'power'
            self._goto('confirm')
        elif key == 'help':
            self._goto('help')
        elif key == 'estop':
            self._estop()
        else:
            self._begin_action(key)

    def _confirmed(self):
        what, self.pending = self.pending, None
        if what == 'power':
            ok = self.io.call_power()
            self._log(f'power off requested, accepted: {ok}')
            self._note(['Powering off'] if ok else ['Power failed'])
            return
        kind = self.trip_kind()
        if kind != what:   # the dock status changed while the question was on the screen
            self._note(['Status changed', 'try again'])
            return
        problem = self._trip_problem(kind)
        if problem:
            self._note(problem, REFUSED_S)
            return
        self._begin_trip(kind)

    # ---- trips
    def _trip_problem(self, kind):
        """Lines for a note when the trip must not start, else None. Checked at Select and again at Yes."""
        io = self.io
        if io.stop_file_exists():
            return ['STOP file is set', 'Delete ~/STOP']
        if io.mission_poll() is None:
            return ['A delivery', 'is running']
        if kind == 'home':
            if not io.stack_running():   # never start the stack away from the dock: AMCL would assume the dock
                return ['Not on the map', 'Use the controller', 'then Dock']
        if not io.path_exists(route_file(self.route_dir)):
            return ['No route saved', 'Map the route', 'first']
        return None

    def _begin_trip(self, kind):
        io = self.io
        self.out_path = None
        if kind == 'full' and not io.stack_running():
            self.out_path = self._new_out_path()
            self._log(f'starting the navigation stack for the trip, output {self.out_path}')
            io.start_stack(self.route_dir, self.out_path)
            self.stack_deadline = io.now() + STACK_START_TIMEOUT
            self._goto('starting')
            return
        self._spawn_mission(kind)

    def _new_out_path(self):
        return self.out_dir.rstrip('/') + '/' + out_name(self.io.wall_time())

    def _spawn_mission(self, kind):
        io = self.io
        if self.out_path is None:
            self.out_path = self._new_out_path()
        self._log(f'starting the {kind} mission, output {self.out_path}')
        io.publish(fit(MISSION_STARTING_LINES))   # the last text this program draws; the mission replaces it
        io.start_mission(mission_args(self.route_dir, kind), self.out_path)
        self._goto('mission')

    def _cancel_start(self):
        self._log('trip cancelled while the stack starts: stopping the stack')
        self.io.stack_cancel()
        self.io.stop_stack_background()
        self._note(['Cancelled'])

    # ---- actions
    def _begin_action(self, kind):
        io = self.io
        if io.stop_file_exists():
            self._note(['STOP file is set', 'Delete ~/STOP'], REFUSED_S)
            return
        if kind.startswith('wall') and io.docked() is True:
            self._note(['Undock first'])
            return
        if kind == 'dock' and io.docked() is True:
            self._note(['Already docked'])
            return
        if kind == 'undock' and io.docked() is False:
            self._note(['Not docked'])
            return
        if io.mission_poll() is None:
            self._note(['A delivery', 'is running'])
            return
        self._log(f'start {kind}')
        if not io.start_action(kind):
            self._note([ACTION_TEXT[kind][2]])
            return
        self.action = kind
        self.action_deadline = io.now() + ACTION_TIMEOUT[kind]
        self._goto('action')

    def _estop(self):
        wheels = self.io.wheels_enabled()
        if wheels is None:
            self._note(['EStop?', 'no wheel status'])
            return
        on = bool(wheels)   # wheels enabled -> stop them; wheels disabled -> release (the stock menu toggles too)
        ok = self.io.call_estop(on)
        self._log(f'estop {"on" if on else "off"} requested, accepted: {ok}')
        self._note((['EStop ON'] if on else ['EStop off']) if ok else ['EStop failed'])

    # ---- polling
    def _poll(self, now):
        io = self.io
        if self.state == 'action':
            result = io.action_poll()
            if result is None and (now > self.action_deadline or io.stop_file_exists()):
                self._log(f'cancel {self.action}: ' + ('STOP file' if io.stop_file_exists() else 'timeout'))
                io.action_cancel()
                self._note([ACTION_TEXT[self.action][2]])
            elif result is not None:
                self._log(f'{self.action} finished, success: {result}')
                self._note([ACTION_TEXT[self.action][1] if result else ACTION_TEXT[self.action][2]])
        elif self.state == 'starting':
            code = io.stack_poll()
            if code is None:
                if now > self.stack_deadline:
                    self._log('start_stack.sh took too long')
                    io.stack_cancel()
                    self._note(['Cannot start', 'Stack too slow'], REFUSED_S)
            elif code != 0:
                reason = refusal_reason(io.read_text(self.out_path))
                self._log(f'start_stack.sh failed with {code}: {reason}')
                self._note(refusal_lines(reason or 'Stack did not start'), REFUSED_S)
            else:
                self._spawn_mission('full')
        elif self.state == 'mission':
            code = io.mission_poll()
            if code is not None:
                self._mission_ended(code, now)
        elif self.state == 'result':
            waiting = any('food is here' in line for line in self.result_lines)   # handoff timed out: keep the message
            if (self.result_code in (EXIT_DELIVERED, EXIT_NO_FOOD) and io.docked() is True and not waiting
                    and now - self.result_at >= RESULT_RETURN_S):
                self._to_menu(keep_cursor=False)
        elif self.state == 'note' and now >= self.note_until:
            self._to_menu()

    def _mission_ended(self, code, now):
        io = self.io
        self._log(f'mission ended, exit code {code}')
        self.result_code, self.result_at = code, now
        if io.docked() is True:
            self._log('docked: stopping the navigation stack')
            io.stop_stack_background()
        else:
            self._log('not docked: the navigation stack keeps running (Back to the lab needs it)')
        if code == EXIT_REFUSED and self.out_path:
            reason = refusal_reason(io.read_text(self.out_path))
            self._note(refusal_lines(reason), REFUSED_S)
        else:
            shown = last_shown(io.read_text(self.out_path)) if self.out_path else None
            self.result_lines = shown or RESULT_TEXT.get(code, RESULT_TEXT[NO_CODE])
            self._goto('result')
