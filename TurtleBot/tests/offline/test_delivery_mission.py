"""Offline tests of the delivery mission (TurtleBot/delivery): route file, odometry watch, button edges, display text
and the DeliveryMission state machine driven by a FakeRobot with a virtual clock. No robot and no ROS needed.
Usage (from the repo root or from this folder): python test_delivery_mission.py
"""
import copy
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import types
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERY = os.path.normpath(os.path.join(HERE, '..', '..', 'delivery'))
sys.path.insert(0, DELIVERY)
import delivery_core as core  # noqa: E402
import delivery_mission as dm  # noqa: E402  (ROS is imported lazily, so this works without ROS)

fails = 0
count = 0


def check(name, cond, info=''):
    global fails, count
    count += 1
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


# ---------------------------------------------------------------- fake robot
class FakeRobot(core.Robot):
    """Virtual-clock robot. presses = [(n, offset, duration, button)]: the nth 'arrive' chime, offset seconds later,
    button (1..4) is down for duration seconds."""

    def __init__(self, docked=True, battery=0.9, battery_fn=None, nav_results=None, nav_time=30.0, dock_ok=True,
                 undock_ok=True, presses=(), stop_fn=None, safety_fn=None, steady_after=25.0, raise_in_go=False,
                 stale_fn=None, remaining=None, alive_fn=None, blocked_fn=None, dock_results=None, pos=None,
                 stop_presses=()):
        self.t = 1000.0
        self.pos = pos                    # (x, y) from AMCL, or None
        self.stop_presses = list(stop_presses)   # [(seconds after start, duration)] button 2 held down
        self.armed = False
        self.latched = False
        self.armed_log = []
        self.start = self.t
        self._docked = docked
        self._battery = battery
        self.battery_fn = battery_fn
        self.nav_results = list(nav_results if nav_results is not None else ['succeeded'] * 10)
        self.nav_time, self.dock_ok, self.undock_ok = nav_time, dock_ok, undock_ok
        self.presses, self.stop_fn, self.safety_fn = list(presses), stop_fn, safety_fn
        self.steady_after, self.raise_in_go = steady_after, raise_in_go
        self.stale_fn = stale_fn          # fn(robot) -> None / 'odom' / 'scan'
        self.remaining = remaining        # {goal index: poses remaining}; missing = nothing reached; 'none' = unknown
        self.last_stale = -1e9
        self.alive_fn, self.blocked_fn, self.dock_results = alive_fn, blocked_fn, dock_results
        self.dock_count = 0
        self.cur_dock_ok = dock_ok
        self.nav_start = None
        self.calls, self.shows, self.chimes, self.go_poses = [], [], [], []
        self.arrive_times = []
        self.nav_end = self.nav_idx = self.undock_end = self.dock_end = None
        self.nav_count = 0
        self.initial_pose = None

    def now(self):
        return self.t

    def sleep(self, seconds):
        if self.blocked_fn and self.nav_end is not None and self.blocked_fn(self):
            self.nav_end += seconds   # Nav2 makes no progress while the path is blocked
        self.t += seconds

    def nav_alive(self):
        return self.alive_fn(self) if self.alive_fn else None

    def blocked(self):
        return bool(self.blocked_fn(self)) if self.blocked_fn else False

    def battery(self):
        return self.battery_fn(self) if self.battery_fn else self._battery

    def is_docked(self):
        return self._docked

    def buttons(self):
        state = [False] * 4
        for n, off, dur, b in self.presses:
            if len(self.arrive_times) >= n:
                a = self.arrive_times[n - 1]
                if a + off <= self.t < a + off + dur:
                    state[b - 1] = True
        return state

    def odom_steady(self):
        return self.t - self.start >= self.steady_after and self.t - self.last_stale >= 5.0

    def stale_sensor(self):
        kind = self.stale_fn(self) if self.stale_fn else None
        if kind:
            self.last_stale = self.t
        return kind

    def poses_remaining(self):
        if self.remaining == 'none':
            return None
        if self.remaining and self.nav_idx in self.remaining:
            return self.remaining[self.nav_idx]
        return len(self.go_poses[-1])

    def safety_problem(self):
        return self.safety_fn(self) if self.safety_fn else None

    def stop_requested(self):
        if self.armed and any(a <= self.t - self.start < a + d for a, d in self.stop_presses):
            self.latched = True     # like RosRobot: a press of button 2 while armed latches
        if self.latched:
            return core.STOP_BUTTON_REASON
        return self.stop_fn(self) if self.stop_fn else None

    def set_stop_button(self, armed):
        self.armed = armed
        self.latched = False
        self.armed_log.append(armed)

    def position(self):
        return self.pos

    def show(self, text):
        self.shows.append(text)

    def chime(self, kind):
        self.chimes.append(kind)
        self.calls.append('chime ' + kind)
        if kind == 'arrive':
            self.arrive_times.append(self.t)

    def set_initial_pose(self, pose):
        self.initial_pose = pose
        self.calls.append('set_initial_pose')

    def wait_nav_ready(self, timeout):
        self.calls.append('wait_nav_ready')
        self.t += 3.0
        return True

    def clear_costmaps(self):
        self.calls.append('clear_costmaps')

    def undock_start(self):
        self.calls.append('undock_start')
        self.undock_end = self.t + 5.0

    def undock_done(self):
        if self.t < self.undock_end:
            return None
        if self.undock_ok:
            self._docked = False
        return self.undock_ok

    def go_through(self, poses):
        self.calls.append('go_through')
        if self.raise_in_go:
            raise RuntimeError('boom')
        self.go_poses.append(list(poses))
        self.nav_idx = self.nav_count
        self.nav_count += 1
        self.nav_end = self.t + self.nav_time
        self.nav_start = self.t

    def nav_done(self):
        if self.nav_end is None or self.t < self.nav_end:
            return None
        return self.nav_results[self.nav_idx]

    def cancel_nav(self):
        self.calls.append('cancel_nav')
        self.nav_end = None

    def dock_start(self):
        self.calls.append('dock_start')
        self.dock_end = self.t + 10.0
        self.cur_dock_ok = self.dock_results[self.dock_count] if self.dock_results else self.dock_ok
        self.dock_count += 1

    def dock_done(self):
        if self.t < self.dock_end:
            return None
        if self.cur_dock_ok:
            self._docked = True
        return self.cur_dock_ok

    def stop_motion(self):
        self.calls.append('stop_motion')


ROUTE_DICT = {
    'version': 1, 'frame_id': 'map', 'map': 'm.yaml',
    'dock_pose': {'x': 0.0, 'y': 0.0, 'yaw': 0.0},
    'outbound': [{'x': 2.0, 'y': 0.5, 'yaw': 0.0}, {'x': 20.0, 'y': 0.5, 'yaw': 0.0}],
    'inbound': [{'x': 10.0, 'y': 0.5, 'yaw': 180.0}, {'x': 0.7, 'y': 0.0, 'yaw': 180.0}],
    'settings': {'max_speed': 0.2, 'pickup_timeout_s': 60, 'handoff_timeout_s': 60, 'hands_clear_s': 2,
                 'min_battery_start': 0.4, 'leg_timeout_s': 300, 'button_placed': 3, 'button_received': 4},
}
GOOD_PRESSES = [(1, 3.0, 0.5, 3), (2, 2.0, 0.5, 4)]


def route(**settings):
    d = copy.deepcopy(ROUTE_DICT)
    d['settings'].update(settings)
    return core.parse_route(d)


def run(robot, allow_undocked=False, **settings):
    return core.DeliveryMission(robot, route(**settings), allow_undocked).run()


def names(result):
    return [e[1] for e in result.events]


def in_order(seq, wanted):
    it = iter(seq)
    return all(any(w == x for x in it) for w in wanted)


def fits(texts):
    return all(len(t.split('\n')) <= 5 and all(len(line) <= 18 for line in t.split('\n')) for t in texts)


def raises(data, text):
    try:
        core.parse_route(data)
    except core.RouteError as e:
        return text.lower() in str(e).lower(), str(e)
    return False, 'no error'


# ---------------------------------------------------------------- happy path
r = FakeRobot(presses=GOOD_PRESSES)
res = run(r)
check('happy path: exit 0, delivered', res.code == 0 and res.outcome == 'delivered', f'{res.code} {res.reason}')
check('happy path: event order', in_order(names(res), ['preflight_ok', 'initial_pose', 'nav_ready', 'odom_steady',
                                                      'undock_start', 'undocked', 'leg_start', 'leg_end', 'wait_button',
                                                      'button', 'leg_start', 'leg_end', 'wait_button', 'button',
                                                      'dock_start', 'docked', 'end']), str(names(res)))
check('happy path: buttons 3 then 4', [e[2] for e in res.events if e[1] == 'button'] == ['3', '4'])
check('happy path: initial pose is the dock pose', r.initial_pose == core.Pose(0.0, 0.0, 0.0))
check('happy path: outbound then inbound poses sent', len(r.go_poses) == 2 and r.go_poses[0][-1].x == 20.0
      and r.go_poses[1][-1].x == 0.7)
check('happy path: display texts fit 5 x 18', fits(r.shows), str(r.shows))
check('happy path: texts', 'Going to food' in r.shows[1] and any('Press button 1' in s for s in r.shows)
      and any('Done, thank you' in s for s in r.shows), str(r.shows))
check('happy path: chimes', r.chimes == ['start', 'arrive', 'thanks', 'arrive', 'thanks'], str(r.chimes))
check('happy path: ends docked, no cancel, zero velocity at the end', r.is_docked() is True
      and 'cancel_nav' not in r.calls and r.calls[-1] == 'stop_motion')
check('happy path: waited for steady odom before the undock',
      next(e[0] for e in res.events if e[1] == 'undock_start') - r.start >= 25.0)

# ---------------------------------------------------------------- pickup timeout
r = FakeRobot(presses=[])
res = run(r)
check('pickup timeout: exit 4 and the robot drove home and docked', res.code == 4 and r.is_docked() is True
      and r.nav_count == 2 and 'dock_start' in r.calls, f'{res.code}')
check('pickup timeout: message shown', any('No food' in s for s in r.shows), str(r.shows))
check('pickup timeout: no received-button wait', names(res).count('wait_button') == 1)
check('pickup timeout: display fits', fits(r.shows))

# ---------------------------------------------------------------- held / pre-arm buttons
e = core.ButtonEdge(armed_at=10.0)
seq = [(10.1, [0, 0, 1, 0]), (10.3, [0, 0, 1, 0]), (10.6, [0, 0, 1, 0]), (11.0, [0, 0, 1, 0])]
check('ButtonEdge: button held since before arming never counts', all(e.update(t, s) == [] for t, s in seq))
e = core.ButtonEdge(armed_at=10.0)
out = [e.update(10.0, [0] * 4), e.update(10.2, [0, 0, 1, 0]), e.update(10.3, [0] * 4), e.update(10.7, [0] * 4)]
check('ButtonEdge: press inside the first 0.5 s is ignored', out == [[], [], [], []], str(out))
e = core.ButtonEdge(armed_at=10.0)
out = [e.update(10.6, [0] * 4)] + [e.update(10.7 + 0.1 * i, [0, 0, 1, 0]) for i in range(10)]
check('ButtonEdge: a held button counts once', sum(1 for x in out if x == [3]) == 1 and sum(len(x) for x in out) == 1,
      str(out))
out2 = [e.update(12.0, [0] * 4), e.update(12.1, [0, 0, 1, 0])]
check('ButtonEdge: release and press again counts again', out2 == [[], [3]], str(out2))
check('ButtonEdge: None sample and short sample are safe', core.ButtonEdge(0).update(5, None) == []
      and core.ButtonEdge(0).update(5, [1]) == [1] and core.ButtonEdge(0).update(5, None) == [])

r = FakeRobot(presses=[(1, 0.2, 5.0, 3)])   # held from 0.2 s after the prompt through the arming window
res = run(r, pickup_timeout_s=20)
check('pre-arm press held through the window does not count: pickup times out (exit 4)', res.code == 4, f'{res.code}')

r = FakeRobot(presses=[(1, 1.0, 3.0, 4), (1, 12.0, 0.5, 3), (2, 2.0, 0.5, 4)])
res = run(r)
check('held wrong button gives one other_button event, then button 3 still works',
      res.code == 0 and names(res).count('other_button') == 1, f'{res.code} {names(res).count("other_button")}')
check('display re-shown after the button event and every 5 s',
      sum(1 for s in r.shows if 'Press button 1' in s) >= 3, str(sum(1 for s in r.shows if 'Press button 1' in s)))

# ---------------------------------------------------------------- handoff timeout
r = FakeRobot(presses=[(1, 3.0, 0.5, 3)])
res = run(r)
check('handoff timeout: docks anyway, exit 0, keeps the food message',
      res.code == 0 and 'handoff_timeout' in names(res) and r.is_docked() is True and 'Your food is here' in r.shows[-1],
      f'{res.code} {r.shows[-1:]}')

# ---------------------------------------------------------------- navigation failures
r = FakeRobot(presses=GOOD_PRESSES, nav_results=['failed', 'succeeded', 'succeeded'])
res = run(r)
check('nav failure then retry success: exit 0, costmaps cleared once, same poses sent again',
      res.code == 0 and r.calls.count('clear_costmaps') == 1 and r.nav_count == 3 and r.go_poses[0] == r.go_poses[1],
      f'{res.code} {names(res)}')
check('retry is logged', 'retry' in names(res))

r = FakeRobot(presses=GOOD_PRESSES, nav_results=['failed', 'failed'])
res = run(r)
check('two failures: alarm exit 3', res.code == 3 and res.outcome == 'alarm', f'{res.code}')
check('two failures: no further motion', r.nav_count == 2 and 'dock_start' not in r.calls and r.calls.count('undock_start') == 1
      and r.calls[-1] == 'stop_motion' and 'alarm' in r.chimes)
check('two failures: NEED HELP shown, fits', r.shows[-1].startswith('NEED HELP') and fits(r.shows), r.shows[-1])

r = FakeRobot(presses=GOOD_PRESSES, nav_results=['succeeded', 'failed', 'failed'])
res = run(r)
check('inbound failing twice also alarms (after the pickup press)', res.code == 3 and 'dock_start' not in r.calls)

r = FakeRobot(presses=GOOD_PRESSES, nav_time=1000.0)
res = run(r, leg_timeout_s=100)
check('leg timeout: alarm, navigation cancelled', res.code == 3 and 'cancel_nav' in r.calls and 'Leg timeout' in res.reason)

# ---------------------------------------------------------------- re-send only the poses not yet reached
P4 = [{'x': float(i * 5), 'y': 0.0, 'yaw': 0.0} for i in range(1, 5)]   # 4 poses along +x: 5, 10, 15, 20 m


def run4(robot, **settings):
    d = copy.deepcopy(ROUTE_DICT)
    d['outbound'] = copy.deepcopy(P4)
    d['settings'].update(settings)
    return core.DeliveryMission(robot, core.parse_route(d)).run()


r = FakeRobot(presses=GOOD_PRESSES, nav_results=['failed', 'succeeded', 'succeeded'], remaining={0: 2})
res = run4(r)
check('retry after failing at 2 of 4 poses re-sends exactly the last 2', res.code == 0 and len(r.go_poses[0]) == 4
      and r.go_poses[1] == r.go_poses[0][-2:] and [p.x for p in r.go_poses[1]] == [15.0, 20.0], str([len(g) for g in r.go_poses]))
check('retry never contains the first waypoint again', r.go_poses[0][0] not in r.go_poses[1])
r = FakeRobot(presses=GOOD_PRESSES, nav_results=['failed', 'succeeded', 'succeeded'], remaining={0: 0})
res = run4(r)
check('remaining 0 still sends the final pose (never an empty goal)', res.code == 0 and r.go_poses[1] == r.go_poses[0][-1:])
r = FakeRobot(presses=GOOD_PRESSES, nav_results=['failed', 'succeeded', 'succeeded'], remaining={0: 99})
res = run4(r)
check('remaining larger than the list is limited to the list', res.code == 0 and r.go_poses[1] == r.go_poses[0])
r = FakeRobot(presses=GOOD_PRESSES, nav_results=['failed', 'succeeded', 'succeeded'], remaining='none')
res = run4(r)
check('unknown progress on a retry: alarm, no re-send of the full list', res.code == 3 and r.nav_count == 1
      and 'Progress unknown' in res.reason, f'{res.code} {res.reason}')

pp = [core.Pose(float(x), 0.0, 0.0) for x in (0, 5, 10, 15)]
check('poses_ahead: robot between poses 1 and 2 -> last two', [p.x for p in core.poses_ahead(pp, 7.0, 0.2)] == [10.0, 15.0])
check('poses_ahead: robot before the start keeps everything', len(core.poses_ahead(pp, -1.0, 0.0)) == 4)
check('poses_ahead: robot past everything keeps only the last', [p.x for p in core.poses_ahead(pp, 20.0, 0.0)] == [15.0])
check('poses_ahead: exactly on pose 1 drops only pose 0', [p.x for p in core.poses_ahead(pp, 5.0, 0.0)] == [5.0, 10.0, 15.0])
check('poses_ahead: single pose and turning path',
      len(core.poses_ahead(pp[:1], 3.0, 0.0)) == 1
      and [(p.x, p.y) for p in core.poses_ahead([core.Pose(0, 0, 0), core.Pose(5, 0, 0), core.Pose(5, 5, 90)], 5.0, 2.0)]
      == [(5, 5)])

# ---------------------------------------------------------------- holds: stale odometry / lidar
def stale_between(kind, a, b):
    return lambda rb: kind if a <= rb.t - rb.start < b else None


r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, remaining={0: 3}, stale_fn=stale_between('odom', 40, 50))
res = run4(r, leg_timeout_s=120)
check('stale odometry: hold, not alarm; the leg resumes with the remaining poses and the run ends 0',
      res.code == 0 and names(res).count('hold') == 1 and names(res).count('retry') == 0, f'{res.code} {res.reason}')
check('stale odometry: cancel_nav and stop_motion called, "Paused" shown, then the old text again',
      'cancel_nav' in r.calls and any(sh.startswith('Paused') for sh in r.shows)
      and r.shows[[sh.startswith('Paused') for sh in r.shows].index(True) + 1].startswith('Going to'), str(r.shows[:4]))
check('stale odometry: resumed with the last 3 poses, no costmap clearing',
      r.go_poses[1] == r.go_poses[0][-3:] and 'clear_costmaps' not in r.calls)
hold_t = [e[0] for e in res.events if e[1] == 'hold'][0]
end_t = [e[0] for e in res.events if e[1] == 'hold_end'][0]
check('stale odometry: resumes only after 5 s steady odometry', end_t - hold_t >= 10.0, f'{end_t - hold_t:.1f} s')
check('hold time extends the leg deadline (leg 120 s, about 10 s drive + 15 s hold + 100 s drive = 125 s)',
      res.code == 0 and [e for e in res.events if e[1] == 'leg_end'][0][0] - [e for e in res.events if e[1] == 'leg_start'][0][0] > 120.0)

r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, stale_fn=stale_between('scan', 40, 60))
res = run(r, leg_timeout_s=300)
check('stale lidar: hold, then resume, exit 0', res.code == 0 and names(res).count('hold') == 1
      and 'lidar' in [sh for sh in r.shows if sh.startswith('Paused')][0], f'{res.code} {res.reason}')
check('hold is logged with its kind', any(e[1] == 'hold' and 'scan' in e[2] for e in res.events))

r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, stale_fn=lambda rb: 'odom' if rb.t - rb.start > 40 else None)
res = run(r, leg_timeout_s=1000)
t_hold = [e[0] for e in res.events if e[1] == 'hold'][0]
check('odometry that never comes back: alarm after the 60 s limit', res.code == 3 and 59.0 <= res.events[-2][0] - t_hold <= 62.0
      and 'Odometry lost' in res.reason, f'{res.code} {res.reason} {res.events[-2][0] - t_hold:.1f}')
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, stale_fn=lambda rb: 'scan' if rb.t - rb.start > 40 else None)
res = run(r, leg_timeout_s=1000)
t_hold = [e[0] for e in res.events if e[1] == 'hold'][0]
check('lidar that never comes back: alarm after the 30 s limit', res.code == 3 and 29.0 <= res.events[-2][0] - t_hold <= 32.0
      and 'Lidar lost' in res.reason, f'{res.code} {res.reason} {res.events[-2][0] - t_hold:.1f}')
check('after such an alarm nothing drives on', r.nav_count == 1 and 'dock_start' not in r.calls
      and r.calls[-1] == 'stop_motion')

r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, nav_results=['succeeded'] * 10,
              stale_fn=lambda rb: 'odom' if rb.nav_end is not None and rb.t - rb.nav_start > 5 else None)
res = run(r, leg_timeout_s=1000)
check('a 4th hold in one leg: alarm after 3 holds', res.code == 3 and names(res).count('hold') == 3 and r.nav_count == 4,
      f'{res.code} holds {names(res).count("hold")} goals {r.nav_count}')

r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, nav_results=['succeeded', 'failed', 'succeeded', 'succeeded'],
              stale_fn=lambda rb: 'odom' if rb.nav_idx == 0 and rb.nav_end is not None and rb.t - rb.nav_start > 30 else None,
              remaining={0: 3, 1: 2})
res = run4(r, leg_timeout_s=1000)
check('a hold does not use up the retry: hold, then a failure, then the retry works (3 poses, then the last 2)',
      res.code == 0 and names(res).count('hold') == 1 and names(res).count('retry') == 1
      and [len(g) for g in r.go_poses[:3]] == [4, 3, 2], f'{res.code} {[len(g) for g in r.go_poses]}')

# ---------------------------------------------------------------- hazards
dock_windows = lambda rb: ((rb.undock_end is not None and rb.undock_end - 5.0 <= rb.t < rb.undock_end)
                           or (rb.dock_end is not None and rb.dock_end - 10.0 <= rb.t < rb.dock_end))
r = FakeRobot(presses=GOOD_PRESSES,
              safety_fn=lambda rb: 'Hazard BUMP (bump_left)' if dock_windows(rb) else None)
res = run(r)
check('a hazard report while docking or undocking is ignored (dock contact is expected)', res.code == 0, f'{res.code} {res.reason}')
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0,
              safety_fn=lambda rb: 'Hazard CLIFF (cliff_front_left)' if rb.nav_start and rb.t - rb.nav_start > 20 else None)
res = run(r)
check('a hazard during a leg: alarm 3, cancel, stop', res.code == 3 and 'cancel_nav' in r.calls and 'CLIFF' in res.reason)
r = FakeRobot(presses=[], safety_fn=lambda rb: 'Hazard BUMP (x)' if rb.arrive_times and rb.nav_count == 1 else None)
res = run(r, pickup_timeout_s=20)
check('hazards are not checked while standing at the pickup', res.code == 4, f'{res.code}')

hl = core.HazardLatch()
check('HazardLatch: nothing before the first message', hl.current(0.0) is None)
hl.update(10.0, 'BUMP (bump_left)')
check('HazardLatch: a report is current for 1 s', hl.current(10.5) == 'BUMP (bump_left)' and hl.current(10.9) is not None)
check('HazardLatch: no newer message for over 1 s clears it', hl.current(11.2) is None)
hl.update(20.0, 'CLIFF (c)')
hl.update(20.1, None)
check('HazardLatch: a clean message clears it at once', hl.current(20.1) is None)
hl.update(30.0, 'WHEEL_DROP (w)')
hl.update(30.5, 'WHEEL_DROP (w)')
check('HazardLatch: it follows the latest message', hl.current(31.4) == 'WHEEL_DROP (w)' and hl.current(31.6) is None)

# ---------------------------------------------------------------- behavior tree file
BT = os.path.join(DELIVERY, 'config', 'delivery_through_poses_bt.xml')
check('behavior tree file exists', os.path.isfile(BT))
tree = ET.parse(BT)
root = tree.getroot()
tags = [e.tag for e in root.iter()]
check('BT parses as XML with BTCPP_format 4 and MainTree', root.tag == 'root' and root.get('BTCPP_format') == '4'
      and root.get('main_tree_to_execute') == 'MainTree')
check('BT has no Spin and no BackUp', 'Spin' not in tags and 'BackUp' not in tags, str(sorted(set(tags))))
rec = [e for e in root.iter('RecoveryNode') if e.get('name') == 'NavigateRecovery']
check('BT: NavigateRecovery retries are 3', len(rec) == 1 and rec[0].get('number_of_retries') == '3')
check('BT keeps Wait, the clearing actions and RemovePassedGoals', 'Wait' in tags and 'RemovePassedGoals' in tags
      and sum(1 for e in root.iter('ClearEntireCostmap')) == 4)
check('BT keeps the node names of the installed tree',
      {e.get('name') for e in root.iter() if e.get('name')} == {
          'NavigateRecovery', 'NavigateWithReplanning', 'ComputePathThroughPoses', 'ClearGlobalCostmap-Context', 'FollowPath',
          'ClearLocalCostmap-Context', 'RecoveryFallback', 'RecoveryActions', 'ClearingActions', 'ClearLocalCostmap-Subtree',
          'ClearGlobalCostmap-Subtree'})
with open(BT, encoding='utf-8') as f:
    bt_text = f.read()
check('BT: each of the 3 changes has a comment', len(re.findall(r'DELIVERY CHANGE [123]:', bt_text)) == 3)
check('BT: no CR line endings', '\r' not in bt_text)
check('core.bt_file_problem accepts the file', core.bt_file_problem(BT) is None)
missing = os.path.join(DELIVERY, 'config', 'nope.xml')
check('core.bt_file_problem names a missing file', 'nope.xml' in (core.bt_file_problem(missing) or ''))
bad_xml = os.path.join(tempfile.mkdtemp(prefix='tb4_bt_'), 'bad.xml')
with open(bad_xml, 'w', encoding='utf-8') as f:
    f.write('<root><oops></root>')
check('core.bt_file_problem rejects broken XML', 'cannot be read' in (core.bt_file_problem(bad_xml) or ''))
with open(os.path.join(DELIVERY, 'delivery_mission.py'), encoding='utf-8') as f:
    mission_src = f.read()
check('adapter points at the file and passes it as behavior_tree',
      os.path.normpath(dm.BT_FILE) == os.path.normpath(BT) and 'behavior_tree=self.bt_file' in mission_src
      and 'delivery_through_poses_bt.xml' in mission_src and 'bt_file_problem(BT_FILE)' in mission_src)

# ---------------------------------------------------------------- what the real display does with a message
# Measured on the robot, 2026-11-06: turtlebot4_node cuts /hmi/display/message every 18 characters and does NOT split on
# newlines, so 'Going to food\ncourt' showed as 'Going to food\ncour' and 't'.
def _real_display(data):
    return [data[i:i + core.DISPLAY_CHARS] for i in range(0, len(data), core.DISPLAY_CHARS)]
check('display_wire: two lines reach the real display as two lines',
      [x.rstrip() for x in _real_display(core.display_wire('Going to food\ncourt'))] == ['Going to food', 'court'])
check('display_wire: no newline is ever sent', '\n' not in core.display_wire('NEED HELP\nDock failed'))
check('display_wire: one line is unchanged, a full 18-character line stays one line',
      core.display_wire('Thank you!') == 'Thank you!' and _real_display(core.display_wire('x' * 18 + '\ny')) == ['x' * 18, 'y'])
check('display_wire: every prompt of the mission fits and keeps its words',
      all(_real_display(core.display_wire(core.display_text(t)))[0].strip() == core.display_text(t).split('\n')[0]
          for t in (core.PICKUP_TEXT, core.HANDOFF_TEXT, 'Paused\nwaiting for\nodometry\n2 = Stop')))
check('the adapter sends display_wire, not the raw text', 'core.display_wire(text)' in open(
    os.path.join(DELIVERY, 'delivery_mission.py'), encoding='utf-8').read())

# ---------------------------------------------------------------- wait_nav_ready with a lost reply
# Seen on the Pi (sim_20261106_091206_mapping): every Nav2 node was active, but a get_state reply never arrived, the
# adapter never asked again, and after 120 s the mission refused to start.
class _Fut:
    def __init__(self, label=None):
        self.label = label
    def done(self):
        return self.label is not None
    def result(self):
        return types.SimpleNamespace(current_state=types.SimpleNamespace(label=self.label))
class _Client:
    def __init__(self, lose_first):
        self.lose = lose_first
        self.calls = self.removed = 0
    def service_is_ready(self):
        return True
    def call_async(self, _req):
        self.calls += 1
        return _Fut(None if self.calls <= self.lose else 'active')
    def remove_pending_request(self, _f):
        self.removed += 1
class _NavNode:
    def __init__(self, lose_first):
        self.clients_made = {}
        self.lose = lose_first
        self.initial_pose_received = True
    def create_client(self, _srv, name):
        self.clients_made[name] = _Client(self.lose)
        return self.clients_made[name]
    def destroy_client(self, _c):
        pass
def _nav_ready(lose_first, timeout=1.5):
    robot = object.__new__(dm.RosRobot)
    robot.node = _NavNode(lose_first)
    robot.initial_pose_set = False
    robot.stop_requested = lambda: None
    robot.sleep = lambda s: time.sleep(0.01)
    saved = dm.GET_STATE_TIMEOUT
    dm.GET_STATE_TIMEOUT = 0.05
    fake = types.ModuleType('lifecycle_msgs.srv')
    fake.GetState = types.SimpleNamespace(Request=lambda: None)
    sys.modules['lifecycle_msgs'], sys.modules['lifecycle_msgs.srv'] = types.ModuleType('lifecycle_msgs'), fake
    try:
        return robot.wait_nav_ready(timeout), robot.node.clients_made
    finally:
        dm.GET_STATE_TIMEOUT = saved
        del sys.modules['lifecycle_msgs'], sys.modules['lifecycle_msgs.srv']
ok_, made_ = _nav_ready(0)
check('wait_nav_ready: normal answers give ready at the first call', ok_ and made_['amcl/get_state'].calls == 1)
ok_, made_ = _nav_ready(1)
check('wait_nav_ready: a lost reply is asked again and the wait still succeeds', ok_
      and made_['amcl/get_state'].calls == 2 and made_['amcl/get_state'].removed == 1, str(made_))
ok_, made_ = _nav_ready(10 ** 6, timeout=0.3)
check('wait_nav_ready: a service that never answers still ends in a refusal, and pending calls do not pile up',
      not ok_ and made_['amcl/get_state'].removed >= made_['amcl/get_state'].calls - 1)

# ---------------------------------------------------------------- Nav2 liveness
def alive_seq(values):
    it = iter(values + [True] * 500)
    return lambda rb: next(it)


r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, alive_fn=lambda rb: False if rb.nav_start and rb.t - rb.nav_start > 10 else True)
res = run(r, leg_timeout_s=1000)
check('Nav2 not alive on 3 polls in a row: alarm "Nav2 stopped", navigation cancelled, no retry',
      res.code == 3 and 'Nav2 stopped' in res.reason and 'cancel_nav' in r.calls and r.nav_count == 1
      and 'retry' not in names(res), f'{res.code} {res.reason}')
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, alive_fn=alive_seq([False, False, True, False, False, True]))
res = run(r, leg_timeout_s=1000)
check('two False polls then True: no alarm (the count restarts)', res.code == 0, f'{res.code} {res.reason}')
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, alive_fn=lambda rb: None)
res = run(r, leg_timeout_s=1000)
check('unknown liveness (None) never alarms', res.code == 0)
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, alive_fn=lambda rb: None)
polls = []
r.nav_alive = lambda: polls.append(r.t) or None
run(r, leg_timeout_s=1000)
gaps = [b - a for a, b in zip(polls, polls[1:])]
check('liveness is polled about every 2 s', len(polls) > 20 and min(gaps) >= 1.9 and sorted(gaps)[len(gaps) // 2] <= 2.3, str(gaps[:5]))

# ---------------------------------------------------------------- collision monitor: blocked
blocked_between = lambda a, b: (lambda rb: rb.nav_start is not None and a <= rb.t - rb.nav_start < b and rb.nav_idx == 0)
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, blocked_fn=blocked_between(10, 30))
res = run(r, leg_timeout_s=110)
check('blocked 20 s: "Please step aside" once with one chime, then the old text again, exit 0',
      res.code == 0 and sum(1 for sh in r.shows if sh == 'Please step\naside\n2 = Stop') == 1 and r.chimes.count('attention') == 1
      and r.shows[r.shows.index('Please step\naside\n2 = Stop') + 1].startswith('Going to'), f'{res.code} {res.reason} {r.shows[:4]}')
check('blocked time extends the leg deadline (leg 110 s, 100 s of driving + 20 s blocked)', res.code == 0
      and 18.0 <= res.blocked_s <= 21.0, f'{res.blocked_s:.1f}')
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, blocked_fn=blocked_between(10, 15))
res = run(r)
check('blocked only 5 s: no message, no chime', res.code == 0 and 'Please step\naside\n2 = Stop' not in r.shows
      and 'attention' not in r.chimes)
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, blocked_fn=lambda rb: rb.nav_start is not None and rb.t - rb.nav_start >= 10)
res = run(r, leg_timeout_s=1000)
notice = [e[0] for e in res.events if e[1] == 'blocked'][0]
alarm = [e[0] for e in res.events if e[1] == 'alarm'][0]
check('blocked for 120 s: alarm "Blocked", cancelled and stopped, nothing drives on',
      res.code == 3 and 'Blocked' in res.reason and 'cancel_nav' in r.calls and r.nav_count == 1 and r.calls[-1] == 'stop_motion'
      and 109.0 <= alarm - notice <= 113.0, f'{res.code} {res.reason} {alarm - notice:.1f}')

tr = core.BlockedTracker()
for i in range(50):
    tr.update_odom(100.0 + i * 0.1, 1.0, 2.0)
check('BlockedTracker: action 0 (nothing) is never blocked', tr.blocked(104.9) is False)
tr.set_action(3)
check('BlockedTracker: action 3 and no movement for 3 s is blocked', tr.blocked(104.9) is True)
check('BlockedTracker: odometry that stopped arriving is not "blocked"', tr.blocked(110.0) is False)
tr2 = core.BlockedTracker()
tr2.set_action(3)
for i in range(50):
    tr2.update_odom(100.0 + i * 0.1, 1.0 + i * 0.02, 2.0)    # 0.2 m/s
check('BlockedTracker: a moving robot is not blocked', tr2.blocked(104.9) is False)
tr3 = core.BlockedTracker()
tr3.set_action(1)
for i in range(10):
    tr3.update_odom(100.0 + i * 0.1, 0.0, 0.0)
check('BlockedTracker: under 3 s of history is not enough', tr3.blocked(100.9) is False)
check('BlockedTracker: nothing received at all is not blocked', core.BlockedTracker().blocked(5.0) is False)

# ---------------------------------------------------------------- dock retry
r = FakeRobot(presses=GOOD_PRESSES, dock_results=[False, True])
res = run(r)
check('dock fails once, second try works: exit 0 with the retry leg to a pose CLOSER than the handoff pose',
      res.code == 0 and r.calls.count('dock_start') == 2 and r.nav_count == 3 and r.is_docked() is True
      and r.go_poses[2] == [core.Pose(core.DOCK_RETRY_DISTANCE, 0.0, 180.0)] and 'dock_retry' in names(res),
      f'{res.code} {res.reason} {r.go_poses[2]}')
# Nav2 believes it is already at the handoff pose, so a retry leg to that same pose would not move the robot at all
# (sim run sim_20261105_022632_stall: AMCL was 0.53 m off, the leg "succeeded" at once and the second dock failed too).
check('dock_retry_pose: on the line from the handoff pose to the dock, handoff yaw kept',
      core.dock_retry_pose(core.Pose(0.7, 0.0, 180.0), core.Pose(0.0, 0.0, 0.0), 0.45) == core.Pose(0.45, 0.0, 180.0))
rp = core.dock_retry_pose(core.Pose(3.0, 4.0, 233.0), core.Pose(0.0, 0.0, 53.0), 1.0)
check('dock_retry_pose: works on a diagonal', abs(rp.x - 0.6) < 1e-9 and abs(rp.y - 0.8) < 1e-9 and rp.yaw == 233.0, str(rp))
check('dock_retry_pose: a handoff pose already that close stays as it is',
      core.dock_retry_pose(core.Pose(0.3, 0.0, 180.0), core.Pose(0.0, 0.0, 0.0), 0.45) == core.Pose(0.3, 0.0, 180.0))
check('dock retry: chime, "Docking again" shown, counted as a retry', 'attention' in r.chimes
      and 'Docking again\n2 = Stop' in r.shows and res.retries == 1)
r = FakeRobot(presses=GOOD_PRESSES, dock_results=[False, False])
res = run(r)
check('dock fails twice: alarm "Dock failed", only two tries', res.code == 3 and 'Dock failed' in r.shows[-1]
      and r.calls.count('dock_start') == 2 and r.nav_count == 3)
r = FakeRobot(presses=GOOD_PRESSES, dock_results=[False, True], battery_fn=lambda rb: 0.10 if rb.dock_count >= 1 else 0.9)
res = run(r)
check('no dock retry with a low battery: alarm after the first failure', res.code == 3 and r.calls.count('dock_start') == 1
      and r.nav_count == 2, f'{res.code} {res.reason}')
r = FakeRobot(presses=GOOD_PRESSES, dock_results=[False, True],
              stop_fn=lambda rb: 'SIGINT' if rb.dock_count >= 1 and rb.t >= rb.dock_end else None)
res = run(r)
check('no dock retry after a stop request: exit 130', res.code == 130 and r.calls.count('dock_start') == 1 and r.nav_count == 2)
r = FakeRobot(presses=GOOD_PRESSES, dock_results=[False, True], nav_results=['succeeded', 'succeeded', 'failed', 'failed'])
res = run(r)
check('dock retry leg that fails twice: alarm, no second dock', res.code == 3 and r.calls.count('dock_start') == 1)

# ---------------------------------------------------------------- run id and summary
check('run id format', re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{6}', core.new_run_id()) is not None and core.new_run_id() != core.new_run_id())
r = FakeRobot(presses=GOOD_PRESSES)
res = core.DeliveryMission(r, route(), run_id='20261105T101530Z-a1b2c3').run()
line = core.format_summary(res)
check('summary line of a clean run', line == 'SUMMARY run=20261105T101530Z-a1b2c3 exit=0 outcome=delivered duration_s='
      + line.split('duration_s=')[1].split()[0] + ' holds=0 retries=0 blocked_s=0 battery_start=0.90 battery_end=0.90', line)
check('summary is one line and parseable', '\n' not in line and dict(kv.split('=') for kv in line.split()[1:])['exit'] == '0'
      and res.run_id == '20261105T101530Z-a1b2c3' and float(line.split('duration_s=')[1].split()[0]) > 60)
check('the run id is in the first event', res.events[0][1] == 'start' and '20261105T101530Z-a1b2c3' in res.events[0][2])
r = FakeRobot(presses=GOOD_PRESSES, nav_time=100.0, nav_results=['succeeded', 'failed', 'succeeded', 'succeeded', 'succeeded'],
              stale_fn=stale_between('odom', 40, 50), remaining={0: 3, 1: 2})
res = run4(r, leg_timeout_s=1000)
check('summary counts holds, retries and blocked seconds', res.holds == 1 and res.retries == 1
      and ' holds=1 retries=1 ' in core.format_summary(res), core.format_summary(res))
r = FakeRobot(battery=None, presses=GOOD_PRESSES)
res = run(r)
check('refused run: summary with exit=2 and battery na', ' exit=2 outcome=refused ' in core.format_summary(res)
      and 'battery_start=na battery_end=na' in core.format_summary(res))
check('adapter writes the summary and the JSON Lines file', 'format_summary(result)' in mission_src and ".jsonl" in mission_src
      and 'run_id=RUN_ID' in mission_src)

# ---------------------------------------------------------------- dock / undock failures
r = FakeRobot(presses=GOOD_PRESSES, dock_ok=False)
res = run(r)
check('dock failure: alarm exit 3 with "Dock failed"', res.code == 3 and 'Dock failed' in r.shows[-1], r.shows[-1])
r = FakeRobot(presses=GOOD_PRESSES, undock_ok=False)
res = run(r)
check('undock failure: alarm exit 3 and no navigation', res.code == 3 and r.nav_count == 0)

# ---------------------------------------------------------------- preflight
r = FakeRobot(battery=0.3, presses=GOOD_PRESSES)
res = run(r)
check('low battery at start: refused (2), nothing moved', res.code == 2 and r.nav_count == 0
      and 'undock_start' not in r.calls and 'set_initial_pose' not in r.calls, f'{res.code} {res.reason}')
r = FakeRobot(docked=False, presses=GOOD_PRESSES)
res = run(r)
check('not docked: refused (2)', res.code == 2 and r.nav_count == 0, res.reason)
r = FakeRobot(docked=False, presses=GOOD_PRESSES)
res = run(r, allow_undocked=True)
check('--allow-undocked: runs, no initial pose, no undock, docks at the end',
      res.code == 0 and 'set_initial_pose' not in r.calls and 'undock_start' not in r.calls and r.is_docked() is True,
      f'{res.code} {res.reason}')
r = FakeRobot(battery=None)
check('no battery data: refused (2)', run(r).code == 2)
r = FakeRobot(steady_after=1e9)
res = run(r)
check('odometry never steady: refused (2) after the wait, nothing moved', res.code == 2 and r.nav_count == 0
      and 'undock_start' not in r.calls, res.reason)

# ---------------------------------------------------------------- alarms and stop during a run
r = FakeRobot(presses=GOOD_PRESSES, nav_time=200.0,
              battery_fn=lambda rb: 0.9 if rb.t - rb.start < 60 else 0.10)
res = run(r)
check('battery drop mid-run: alarm 3, navigation cancelled, stopped', res.code == 3 and 'cancel_nav' in r.calls
      and r.calls[-1] == 'stop_motion' and 'Battery low' in r.shows[-1], f'{res.code} {r.shows[-1]}')

r = FakeRobot(presses=GOOD_PRESSES, nav_time=200.0,
              safety_fn=lambda rb: 'Hazard BUMP (bump_left)' if rb.t - rb.start > 60 else None)
res = run(r)
check('hazard while driving: alarm 3, cancel, stop', res.code == 3 and 'cancel_nav' in r.calls and 'stop_motion' in r.calls
      and r.nav_count == 1)

r = FakeRobot(presses=GOOD_PRESSES, nav_time=200.0, stop_fn=lambda rb: 'SIGINT' if rb.t - rb.start > 50 else None)
res = run(r)
check('STOP during outbound: exit 130, cancel_nav and stop_motion called, shows Stopped',
      res.code == 130 and 'cancel_nav' in r.calls and 'stop_motion' in r.calls and r.shows[-1] == 'Stopped'
      and r.nav_count == 1 and 'dock_start' not in r.calls, f'{res.code} {r.calls[-3:]}')

r = FakeRobot(presses=[], stop_fn=lambda rb: '~/STOP' if rb.arrive_times and rb.t - rb.arrive_times[0] > 10 else None)
res = run(r)
check('STOP while waiting for the vendor: exit 130, no more motion', res.code == 130 and r.nav_count == 1)

r = FakeRobot(raise_in_go=True)
res = run(r)
check('unexpected exception: alarm 3 and stop_motion', res.code == 3 and 'stop_motion' in r.calls)

# ---------------------------------------------------------------- route validation
good, _ = raises(copy.deepcopy(ROUTE_DICT), 'zzz')
check('valid route dict parses', core.parse_route(copy.deepcopy(ROUTE_DICT)).settings.button_placed == 3 and not good)
for btn, word in ((1, 'Select'), (2, 'Back'), (5, 'safe'), (0, 'safe')):
    d = copy.deepcopy(ROUTE_DICT)
    d['settings']['button_placed'] = btn
    ok, msg = raises(d, word)
    check(f'button_placed {btn} refused ("{word}")', ok, msg)
d = copy.deepcopy(ROUTE_DICT)
d['settings']['button_received'] = 1
check('button_received 1 refused with the reason (1 is always accepted anyway)', raises(d, 'always accepted')[0])
d = copy.deepcopy(ROUTE_DICT)
d['settings']['button_received'] = 3
check('same button twice refused', raises(d, 'differ')[0])
d = copy.deepcopy(ROUTE_DICT)
d['outbound'] = []
check('empty outbound refused', raises(d, 'outbound')[0] and raises(d, 'empty')[0])
d = copy.deepcopy(ROUTE_DICT)
d['inbound'] = []
check('empty inbound refused', raises(d, 'inbound')[0])
d = copy.deepcopy(ROUTE_DICT)
del d['dock_pose']
check('missing dock_pose refused', raises(d, 'dock_pose')[0])
d = copy.deepcopy(ROUTE_DICT)
del d['settings']['leg_timeout_s']
check('missing setting refused', raises(d, 'leg_timeout_s')[0])
d = copy.deepcopy(ROUTE_DICT)
del d['inbound']
check('missing inbound refused', raises(d, 'inbound')[0])
d = copy.deepcopy(ROUTE_DICT)
del d['outbound'][0]['yaw']
check('pose without yaw refused', raises(d, 'yaw')[0])
d = copy.deepcopy(ROUTE_DICT)
d['outbound'][0]['x'] = 'far'
check('non-number x refused', raises(d, 'number')[0])
for key in ('pickup_timeout_s', 'handoff_timeout_s', 'leg_timeout_s'):
    for v in (0, -5):
        d = copy.deepcopy(ROUTE_DICT)
        d['settings'][key] = v
        check(f'{key} = {v} refused', raises(d, key)[0])
for v in (-0.1, 1.5, 40):
    d = copy.deepcopy(ROUTE_DICT)
    d['settings']['min_battery_start'] = v
    check(f'min_battery_start {v} refused', raises(d, 'between 0 and 1')[0])
d = copy.deepcopy(ROUTE_DICT)
d['version'] = 2
check('unknown version refused', raises(d, 'version')[0])
check('non-mapping refused', raises([1, 2], 'mapping')[0])

EXAMPLE = os.path.join(DELIVERY, 'route.example.yaml')
ex = core.load_route(EXAMPLE)
check('route.example.yaml loads', len(ex.outbound) == 4 and len(ex.inbound) == 3 and ex.settings.button_placed == 3
      and ex.settings.button_received == 4 and ex.dock_pose == core.Pose(0.0, 0.0, 0.0) and ex.settings.leg_timeout_s == 600,
      str(ex))
check('describe_route gives lines', len(core.describe_route(ex)) == 5)
try:
    core.load_route(os.path.join(DELIVERY, 'no_such_route.yaml'))
    check('missing route file raises RouteError', False)
except core.RouteError as e:
    check('missing route file raises RouteError', 'cannot read' in str(e))
bad = os.path.join(tempfile.mkdtemp(prefix='tb4_delivery_'), 'bad.yaml')
with open(bad, 'w', encoding='utf-8') as f:
    f.write('version: [1\n  oops: {')
try:
    core.load_route(bad)
    check('bad YAML raises RouteError', False)
except core.RouteError as e:
    check('bad YAML raises RouteError', 'YAML' in str(e))

# ---------------------------------------------------------------- display text
check('display_text: short text unchanged', core.display_text('Thank you!') == 'Thank you!')
t = core.display_text('Going to food court')
check('display_text: long line wraps to 18', t == 'Going to food\ncourt', repr(t))
t = core.display_text('a' * 40)
check('display_text: unbroken word is cut', t.split('\n') == ['a' * 18, 'a' * 18, 'a' * 4], repr(t))
t = core.display_text(['l1', 'l2', 'l3', 'l4', 'l5', 'l6', 'l7'])
check('display_text: at most 5 lines', len(t.split('\n')) == 5)
check('display_text: list and string forms agree', core.display_text(['NEED HELP', 'Dock failed']) == 'NEED HELP\nDock failed')
check('display_text: every mission text fits', fits([core.display_text(s) for s in (
    'Going to food court', 'Food placed?\nPress button 3', 'Your food is here\nTake it, press 4',
    'NEED HELP\nBattery low 12%', 'NEED HELP\nHazard WHEEL_DROP (front_left)', 'No food. Going home')]))

# ---------------------------------------------------------------- SteadyOdomWatch
def stream(a, b, step=0.1):
    out, i = [], 0
    while a + i * step <= b + 1e-9:
        out.append(round(a + i * step, 6))
        i += 1
    return out


def feed(times, **kw):
    w = core.SteadyOdomWatch(**kw)
    for t in times:
        w.update(t)
    return w


w = feed(stream(0.0, 20.0), started=0.0)
check('odom watch: ready 20 s after start with 5 s steady', w.ready(20.0) and not w.ready(19.95))
w = feed(stream(0.0, 10.0), started=0.0)
check('odom watch: 10 s after start is not ready (20 s settle)', not w.ready(10.0))
w = feed(stream(0.0, 17.95) + stream(18.5, 22.95), started=0.0)
check('odom watch: a 0.55 s gap restarts the window', w.gaps == 1 and not w.ready(22.95))
w = feed(stream(0.0, 17.95) + stream(18.5, 23.5), started=0.0)
check('odom watch: ready 5 s after the gap', w.ready(23.5))
w = feed(stream(0.0, 30.0), started=0.0)
check('odom watch: a stall that is still going on is not ready', w.ready(30.0) and not w.ready(30.5))
w = feed([0.0, 0.3, 0.6], steady=0.5)
check('odom watch: 0.3 s spacing is not a gap', w.gaps == 0 and w.ready(0.6))
check('odom watch: no data is not ready, age is inf', not core.SteadyOdomWatch().ready(5.0)
      and core.SteadyOdomWatch().age(5.0) == float('inf'))

# ---------------------------------------------------------------- the program itself
proc = subprocess.run([sys.executable, '-I', os.path.join(DELIVERY, 'delivery_mission.py'), '--help'],
                      capture_output=True, text=True, timeout=60)
check('delivery_mission.py --help exits 0 without ROS', proc.returncode == 0 and '--route' in proc.stdout
      and '--dry-run' in proc.stdout and '--allow-undocked' in proc.stdout, proc.stderr[-200:])
proc = subprocess.run([sys.executable, '-I', os.path.join(DELIVERY, 'delivery_mission.py'), '--route', bad, '--dry-run'],
                      capture_output=True, text=True, timeout=60)
check('delivery_mission.py with a bad route refuses (exit 2) before touching ROS', proc.returncode == 2
      and 'REFUSING' in proc.stdout, proc.stdout[-200:] + proc.stderr[-200:])
for fname in ('delivery_core.py', 'delivery_mission.py'):
    with open(os.path.join(DELIVERY, fname), 'rb') as f:
        check(f'{fname}: LF line endings', b'\r\n' not in f.read())

# ---------------------------------------------------------------- same rule as motion_shapes.SteadyOdom
# Last, because sim.py replaces the clock and stubs ROS for the rest of the process.
try:
    import sim  # noqa: E402,F401  (installs the ROS stubs)
    import motion_shapes as ms  # noqa: E402
except Exception as e:   # noqa: BLE001
    check('motion_shapes importable through sim.py for the comparison', False, repr(e))
else:
    rng = random.Random(7)
    same = True
    for _ in range(200):
        times, t = [], 0.0
        for _ in range(rng.randint(1, 120)):
            t += rng.choice([0.1, 0.1, 0.1, 0.25, 0.3, 0.35, 0.8])
            times.append(t)
        started = rng.choice([None, 0.0])
        a = core.SteadyOdomWatch(started=started)
        b = ms.SteadyOdom(started=started)
        for x in times:
            if a.update(x) != b.update(x):
                same = False
        for probe in (times[-1], times[-1] + 0.2, times[-1] + 1.0, 25.0):
            same = same and a.ready(probe) == b.ready(probe)
    check('SteadyOdomWatch gives the same answers as motion_shapes.SteadyOdom (200 random streams)', same)
    check('constants equal motion_shapes', (core.ODOM_STEADY, core.ODOM_MAX_GAP, core.ODOM_SETTLE_AFTER_START)
          == (ms.ODOM_STEADY, ms.ODOM_MAX_GAP, ms.ODOM_SETTLE_AFTER_START))

# ---------------------------------------------------------------- menu-style prompts: button 1 beside the setting
r = FakeRobot(presses=[(1, 3.0, 0.5, 1), (2, 2.0, 0.5, 1)])
res = run(r)
check('button 1 answers both prompts (route settings 3 and 4 stay valid)', res.code == 0
      and [e[2] for e in res.events if e[1] == 'button'] == ['1', '1'], f'{res.code} {res.reason}')
check('pickup prompt is menu style', core.PICKUP_TEXT in r.shows and core.PICKUP_TEXT == 'Food placed?\n>Back to the lab\nPress button 1')
check('handoff prompt is menu style', core.HANDOFF_TEXT in r.shows
      and core.HANDOFF_TEXT == 'Your food is here\n>Done, thank you\nPress button 1')
check('both prompts fit the display', fits([core.PICKUP_TEXT, core.HANDOFF_TEXT]))
r = FakeRobot(presses=[(1, 3.0, 0.5, 3), (2, 2.0, 0.5, 4)])
check('buttons 3 and 4 of the route still work', run(r).code == 0)
r = FakeRobot(presses=[(1, 3.0, 0.5, 4), (1, 20.0, 0.5, 1), (2, 2.0, 0.5, 3), (2, 20.0, 0.5, 1)])
res = run(r)
check('the other route button does not answer the prompt (4 at pickup, 3 at handoff), 1 does', res.code == 0
      and names(res).count('other_button') == 2, f'{res.code} {names(res).count("other_button")}')
r = FakeRobot(presses=[(1, 3.0, 0.5, 2)])
res = run(r, pickup_timeout_s=20)
check('button 2 while waiting for an answer is no stop: it only shows the text again', res.code == 4
      and 'other_button' in names(res) and 'button 2' not in res.reason, f'{res.code} {res.reason}')
d = copy.deepcopy(ROUTE_DICT)
d['settings']['button_placed'] = 1
check('route setting 1 and 2 stay refused', raises(d, 'always accepted')[0] and raises(
    dict(d, settings=dict(d['settings'], button_placed=2)), 'stop button')[0])

# ---------------------------------------------------------------- button 2 = stop while the robot works
r = FakeRobot(presses=GOOD_PRESSES, nav_time=200.0, stop_presses=[(50.0, 0.5)])
res = run(r)
check('button 2 while driving: exit 130, reason button 2, cancel + zero velocity, Stopped shown',
      res.code == 130 and res.reason == 'button 2' and 'cancel_nav' in r.calls and r.calls[-1] == 'stop_motion'
      and r.shows[-1] == 'Stopped' and r.nav_count == 1, f'{res.code} {res.reason} {r.shows[-1]}')
check('stop button is armed while driving and disarmed at the end', r.armed_log[0] is True and r.armed_log[-1] is False)
r = FakeRobot(presses=GOOD_PRESSES, nav_time=200.0, stop_presses=[(5.0, 0.5)])
res = run(r)
check('button 2 while preparing (waiting for odometry): exit 130, nothing moved', res.code == 130
      and 'undock_start' not in r.calls and r.nav_count == 0, f'{res.code} {res.reason}')
r = FakeRobot(presses=GOOD_PRESSES, nav_time=30.0, steady_after=1.0)
res = run(r)
check('stop button is disarmed during each wait for an answer and armed again after',
      r.armed_log == [True, False, True, False, True, False], str(r.armed_log))
check('every driving text has "2 = Stop" as its last line', all(
    sh.split('\n')[-1] == '2 = Stop' for sh in r.shows if sh.startswith(('Going to', 'Starting', 'No food\nGoing'))), str(r.shows))
r = FakeRobot(presses=GOOD_PRESSES, dock_ok=False)
check('a plain FakeRobot subclass without the hook still runs: Robot.set_stop_button defaults to a no-op',
      core.Robot.set_stop_button(r, True) is None)
# the adapter latches a press of button 2 (False -> True) only while armed; a button held since before does not count
class _Msg:
    def __init__(self, *down):
        self.button = [i + 1 in down for i in range(4)]
rr = object.__new__(dm.RosRobot)
rr.state, rr.latch, rr.have_buttons, rr.stop_armed, rr.stop_latched = [False] * 4, [False] * 4, False, False, False
rr._on_buttons(_Msg(2))
check('RosRobot: a press of button 2 while not armed is not a stop', not rr.stop_latched and rr.stop_requested() is None)
rr._on_buttons(_Msg())
rr.set_stop_button(True)
rr._on_buttons(_Msg(2))
check('RosRobot: button 2 while armed latches and stop_requested says button 2', rr.stop_requested() == 'button 2')
rr._on_buttons(_Msg())
check('RosRobot: the latch stays after the release', rr.stop_requested() == 'button 2')
rr.set_stop_button(True)
check('RosRobot: arming again clears an old latch', rr.stop_requested() is None)
rr._on_buttons(_Msg(2))
rr.set_stop_button(True)
rr._on_buttons(_Msg(2))
check('RosRobot: button 2 held since before arming is no new press', rr.stop_requested() is None)
rr._on_buttons(_Msg())
rr._on_buttons(_Msg(1, 3, 4))
check('RosRobot: buttons 1, 3 and 4 are never a stop', rr.stop_requested() is None)
rr.stop_request_saved, dm.stop_request = None, 'SIGTERM'
check('RosRobot: a signal beats the button', rr.stop_requested() == 'SIGTERM')
dm.stop_request = None

# ---------------------------------------------------------------- preparing shows a text first (so the menu program goes silent)
r = FakeRobot(presses=GOOD_PRESSES)
run(r)
check('preparing shows "Starting / please wait / 2 = Stop" before anything else', r.shows[0] == 'Starting\nplease wait\n2 = Stop'
      and r.calls.index('wait_nav_ready') > -1, str(r.shows[:2]))

# ---------------------------------------------------------------- home trip
I4 = [core.Pose(15.0, 0.5, 180.0), core.Pose(10.0, 0.5, 180.0), core.Pose(5.0, 0.5, 180.0), core.Pose(0.7, 0.0, 180.0)]
check('home_poses: starts at the pose nearest to the robot', core.home_poses(I4, 9.0, 1.0) == I4[1:])
check('home_poses: robot near the start gets the whole path', core.home_poses(I4, 16.0, 0.0) == I4)
check('home_poses: robot next to the dock gets only the last pose', core.home_poses(I4, 0.0, 0.0) == I4[3:])
check('home_poses: a tie takes the earlier pose', core.home_poses(I4, 7.5, 0.5) == I4[1:])
check('home_poses: one-pose route', core.home_poses(I4[3:], 50.0, 50.0) == I4[3:])
check('home_poses: never mutates the route', core.home_poses(I4, 9.0, 1.0) is not I4 and len(I4) == 4)

def _bad_trip():
    try:
        core.DeliveryMission(FakeRobot(), route(), trip='x')
    except ValueError:
        return True
    return False


def home(robot, **kw):
    return core.DeliveryMission(robot, route(), trip='home', **kw).run()

r = FakeRobot(docked=False, pos=(9.0, 1.0))
res = home(r)
check('home trip: exit 4, outcome returned, reason', (res.code, res.outcome) == (4, 'returned')
      and res.reason == 'back to the lab trip', f'{res.code} {res.outcome} {res.reason}')
check('home trip: no initial pose, no undock, no button wait, one leg from the nearest pose, then dock',
      'set_initial_pose' not in r.calls and 'undock_start' not in r.calls and 'wait_button' not in names(res)
      and r.nav_count == 1 and [p.x for p in r.go_poses[0]] == [10.0, 0.7] and r.calls.count('dock_start') == 1
      and r.is_docked() is True, str(r.go_poses))
check('home trip: texts', r.shows[0].startswith('Starting') and 'Going to the lab\n2 = Stop' in r.shows
      and r.shows[-1] == 'Back at the lab' and fits(r.shows), str(r.shows))
check('home trip: stop button armed during the trip, disarmed after', r.armed_log == [True, False])
r = FakeRobot(docked=False, pos=(9.0, 1.0))
res = core.DeliveryMission(r, route(), allow_undocked=True, trip='home').run()
check('home trip with --allow-undocked as well behaves the same', res.code == 4 and r.nav_count == 1)

r = FakeRobot(docked=True, pos=(0.0, 0.0))
res = home(r)
check('home trip while docked: nothing to do, exit 4 returned, robot not moved', (res.code, res.outcome) == (4, 'returned')
      and r.nav_count == 0 and not any(c in r.calls for c in ('dock_start', 'undock_start', 'set_initial_pose'))
      and r.shows[-1] == 'Already docked', f'{res.reason} {r.shows}')
r = FakeRobot(docked=False, pos=None)
res = home(r)
check('home trip with no AMCL position: refused (2) after 10 s, nothing moved, clear reason', res.code == 2
      and 'AMCL' in res.reason and r.nav_count == 0 and 'dock_start' not in r.calls
      and 9.5 <= r.t - r.start - 25.0 <= 20.0 and r.shows[-1].startswith('Cannot start'), f'{res.reason} {r.t - r.start}')
r = FakeRobot(docked=False, pos=(9.0, 1.0), battery=0.2)
res = home(r)
check('home trip with an empty battery is refused too (route minimum)', res.code == 2 and r.nav_count == 0)
r = FakeRobot(docked=False, pos=(9.0, 1.0), nav_time=100.0, stop_fn=lambda rb: 'SIGINT' if rb.t - rb.start > 50 else None)
res = home(r)
check('home trip: stop request cancels, stops, shows Stopped (130)', res.code == 130 and 'cancel_nav' in r.calls
      and r.shows[-1] == 'Stopped' and 'dock_start' not in r.calls)
r = FakeRobot(docked=False, pos=(9.0, 1.0), nav_time=100.0, stop_presses=[(40.0, 0.5)])
res = home(r)
check('home trip: button 2 stops it (130)', res.code == 130 and res.reason == 'button 2', f'{res.code} {res.reason}')
r = FakeRobot(docked=False, pos=(9.0, 1.0), nav_results=['failed', 'failed'])
res = home(r)
check('home trip: two failed tries are the alarm (3), no dock', res.code == 3 and 'dock_start' not in r.calls)
r = FakeRobot(docked=False, pos=(9.0, 1.0), dock_results=[False, True])
res = home(r)
check('home trip: a failed dock is retried once like the full trip', res.code == 4 and r.calls.count('dock_start') == 2
      and res.retries == 1, f'{res.code} {r.calls.count("dock_start")}')
r = FakeRobot(docked=False, pos=(9.0, 1.0), dock_ok=False)
res = home(r)
check('home trip: dock failing twice is the alarm (3)', res.code == 3)
check('home trip: trip other than full/home is rejected', _bad_trip())
check('--trip is a command line option, default full', dm.parse_args(['--route', 'r.yaml']).trip == 'full'
      and dm.parse_args(['--route', 'r.yaml', '--trip', 'home']).trip == 'home')

print(f'\n{count} checks, {fails} failure(s)')
sys.exit(1 if fails else 0)
