"""Offline test of the lidar auto-restart decision logic (TurtleBot/setup/lidar-restart/tb4_lidar_restart.py).

No robot and no ROS needed: LidarRestartLogic has no ROS imports and takes the time as an argument.
Usage: python test_lidar_restart.py
"""
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
NODE_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'setup', 'lidar-restart'))
sys.path.insert(0, NODE_DIR)
import tb4_lidar_restart as lr  # noqa: E402

fails = 0


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info else ''))
    if not cond:
        fails += 1


def run(L, t0, t1, step=0.5, scan_from=None, answer_ok=True, texts=None):
    """Drive L from t0 to t1. Scans arrive each step from scan_from on; a call is answered at once.
    Returns the times of the /start_motor calls."""
    calls, t = [], t0
    while t <= t1 + 1e-9:
        if scan_from is not None and t >= scan_from:
            L.on_scan(t)
        for k, txt in L.tick(t):
            if texts is not None:
                texts.append((t, k, txt))
            if k == 'call':
                calls.append(t)
                L.on_call_result(t, answer_ok)
        t += step
    return calls


# docked: nothing, with or without scans
L = lr.LidarRestartLogic()
L.on_dock(True, 0.0)
check('docked: no call in 60 s without scans', run(L, 0, 60) == [] and L.state == L.IDLE)

# unknown dock state: nothing
L = lr.LidarRestartLogic()
check('no /dock_status yet: nothing happens', run(L, 0, 60) == [] and L.state == L.IDLE)

# node starts undocked
L = lr.LidarRestartLogic()
L.on_dock(False, 0.0)
check('start undocked: no call before 10 s', run(L, 0, 9.5, scan_from=0) == [] and L.state == L.SETTLE)
check('start undocked, scan present: no call, done', run(L, 10, 30, scan_from=0) == [] and L.state == L.DONE)

# dock -> undock with scan present
L = lr.LidarRestartLogic()
L.on_dock(True, 0.0)
run(L, 0, 20)
L.on_dock(False, 20.0)
check('dock -> undock, scan present: no call', run(L, 20, 60, scan_from=20) == [] and L.state == L.DONE)

# scan silent: one call at 10 s, motor starts, scan returns
L = lr.LidarRestartLogic()
L.on_dock(True, 0.0)
L.on_dock(False, 100.0)
check('scan silent: no call before 10 s', run(L, 100, 109.5) == [])
calls = run(L, 110, 140, scan_from=112.0)
check('scan silent: /start_motor called once at 10 s, done when scans return', calls == [110.0] and L.state == L.DONE, str(calls))

# 3 s freshness rule
L = lr.LidarRestartLogic()
L.on_scan(8.0)
check('scan_fresh: 3.0 s old is fresh, 3.5 s old is not', L.scan_fresh(11.0) and not L.scan_fresh(11.5))
L = lr.LidarRestartLogic()
L.on_dock(False, 0.0)
L.on_scan(5.0)
check('last scan 5 s old at the check: call', len(run(L, 0, 10.0)) == 1)
L = lr.LidarRestartLogic()
L.on_dock(False, 0.0)
L.on_scan(8.0)
check('last scan 2 s old at the check: no call', run(L, 0, 10.0) == [] and L.state == L.DONE)

# lidar never starts: 3 calls 8 s apart, one warning, silence until next undock
L = lr.LidarRestartLogic()
L.on_dock(False, 0.0)
texts = []
calls = run(L, 0, 120, texts=texts)
warns = [t for t, k, x in texts if k == 'warn' and 'giving up' in x]
check('never starts: exactly 3 calls at 10, 18, 26 s', calls == [10.0, 18.0, 26.0], str(calls))
check('never starts: one give-up warning at 34 s, state gave_up', warns == [34.0] and L.state == L.GAVE_UP, str(warns))
check('gave up: no more calls later', run(L, 120, 300) == [])
L.on_dock(True, 300.0)
L.on_dock(False, 310.0)
calls = run(L, 310, 360)
check('next undock: tries again (3 calls, first at +10 s)', len(calls) == 3 and calls[0] == 320.0, str(calls))

# docked during a retry
L = lr.LidarRestartLogic()
L.on_dock(False, 0.0)
run(L, 0, 12)
L.on_dock(True, 12.0)
check('docked during the wait: back to idle, no further call', run(L, 12, 100) == [] and L.state == L.IDLE and L.attempts == 0)

# failed service calls still count as attempts
L = lr.LidarRestartLogic()
L.on_dock(False, 0.0)
check('failed calls count: still capped at 3', len(run(L, 0, 100, answer_ok=False)) == 3)

# a result without a call is ignored; repeated dock messages do not move the deadline
L = lr.LidarRestartLogic()
L.on_call_result(1.0, True)
check('call result without a call is ignored', L.state == L.IDLE and L.tick(2.0) == [])
L = lr.LidarRestartLogic()
L.on_dock(False, 0.0)
for t in range(1, 10):
    L.on_dock(False, float(t))
check('repeated undocked messages keep the first deadline', L.check_at == 10.0 and run(L, 0, 10.5) == [10.0])

# safety: static checks of the node source
with open(os.path.join(NODE_DIR, 'tb4_lidar_restart.py'), encoding='utf-8') as f:
    src = f.read()
check('node has no publisher and no action client', 'create_publisher' not in src and 'ActionClient' not in src and 'cmd_vel' not in src.replace('/cmd_vel', ''))
check('node uses SingleThreadedExecutor only', 'SingleThreadedExecutor' in src and 'MultiThreadedExecutor' not in src)
check('rclpy is not imported at module level', 'rclpy' not in sys.modules)

print(f'\n{fails} failure(s)')
sys.exit(1 if fails else 0)
