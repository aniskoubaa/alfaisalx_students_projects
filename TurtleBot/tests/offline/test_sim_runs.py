"""Run the example programs against the simulated robot in sim.py and check the exit codes.

No robot and no ROS needed. Each scenario starts `python sim.py <scenario> <args>` in a fresh process
(the simulator replaces the clock, so a 40 s shape takes well under a second of real time).
Usage: python test_sim_runs.py
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# (name, scenario, program arguments, extra environment, expected exit code[, regex the output must contain])
SCENARIOS = [
    ('square', 'motion', ['square', '--yes'], {}, 0),
    ('rotate', 'motion', ['rotate', '--yes'], {}, 0),
    ('back_and_forth', 'motion', ['back_and_forth', '--yes'], {}, 0),
    ('triangle', 'motion', ['triangle', '--yes'], {}, 0),
    ('figure_eight', 'motion', ['figure_eight', '--yes'], {}, 0),
    ('speed above cap is lowered', 'motion', ['square', '--yes', '--speed', '0.5'], {}, 0),
    ('0.8 s odom gap is held through', 'motion', ['square', '--yes'], {'SIM_ODOM_GAP': '25,0.8'}, 0),
    ('2.5 s odom gap aborts', 'motion', ['square', '--yes'], {'SIM_ODOM_GAP': '25,2.5'}, 1),
    ('docked real run refused', 'motion', ['square', '--yes'], {'SIM_DOCKED': '1'}, 2),
    ('docked dry run allowed', 'motion', ['square', '--dry-run'], {'SIM_DOCKED': '1'}, 0),
    ('more_shapes star', 'shapes', ['star', '--yes'], {}, 0),
    ('more_shapes hexagon', 'shapes', ['polygon', '--sides', '6', '--side', '0.25', '--yes'], {}, 0),
    ('more_shapes circle', 'shapes', ['circle', '--yes'], {}, 0),
    ('more_shapes square_spiral', 'shapes', ['square_spiral', '--yes'], {}, 0),
    ('more_shapes zigzag', 'shapes', ['zigzag', '--yes'], {}, 0),
    ('more_shapes repeatability', 'shapes', ['repeatability', '--shape', 'square', '--loops', '2', '--yes'], {}, 0),
    ('12-gon too big for the 1.2 m fence is refused', 'shapes', ['polygon', '--sides', '12', '--side', '0.3', '--yes'], {}, 2),
    ('wall approach stops at target', 'wall', ['--yes'], {'SIM_WALL': '1.2'}, 0),
    ('keep distance', 'keep', ['--yes', '--duration', '20'], {'SIM_OBJECT': '0.9,0.0'}, 0),
    ('sensor report (no motion)', 'report', ['--seconds', '5'], {}, 0),
    # Wait before the first move (TB-25): the program is 20 s old AND /odom was steady for 5 s (no gap over 0.3 s).
    # Give up after max(30 s, settle time left + 5 s + 10 s) = 35 s (exit 2, nothing sent).
    ('steady odom: motion_shapes waits until 20 s after start, 0 gaps, then moves', 'motion', ['square', '--yes'], {}, 0,
     r'odometry steady for 5\.0 s, 20\.\d s after start \(waited \d+\.\d s, 0 gaps over 0\.3 s\)[\s\S]*segment 8 done'),
    ('steady odom: a 7 s gap at 8 s after start -> /odom paused 7.0 s, still moves after the wait', 'motion', ['square', '--yes'],
     {'SIM_ODOM_GAP': '8,7'}, 0,
     r'/odom paused for 7\.0 s[\s\S]*odometry steady for 5\.0 s, 2\d\.\d s after start \(waited \d+\.\d s, 1 gaps over 0\.3 s\)[\s\S]*segment 8 done'),
    ('steady odom: a 2 s gap at 16 s after start pushes the start to 23 s', 'motion', ['square', '--yes'],
     {'SIM_ODOM_GAP': '16,2'}, 0, r'odometry steady for 5\.0 s, 23\.\d s after start[\s\S]*segment 8 done'),
    ('steady odom: gaps that never stop -> motion_shapes setup failure (2) after 34 to 35 s (not 30), no velocity command', 'motion',
     ['square', '--yes'], {'SIM_ODOM_GAP_EVERY': '0.5,1.5,0.5'}, 2,
     r'SETUP FAILED: odometry not steady within 3[4-5] s \(longest gap 0\.[5-9] s\)\. Starting or stopping a ROS program can pause the base; '
     r'wait a minute and run again \(see ROADMAP\.md TB-25\)[\s\S]*SIM exit=2 t=3[5-9]\.\d+s[\s\S]*nonzero=0 '),
    ('steady odom: motion_shapes dry run also waits', 'motion', ['square', '--dry-run'], {}, 0,
     r'odometry steady for 5\.0 s, 20\.\d s after start[\s\S]*dry run: all checks done'),
    ('steady odom: motion_shapes dry run with endless gaps fails (2)', 'motion', ['square', '--dry-run'],
     {'SIM_ODOM_GAP_EVERY': '0.5,1.5,0.5'}, 2, r'odometry not steady within 3[4-5] s'),
    ('steady odom: SIGTERM during the wait stops motion_shapes (130) before any move', 'motion', ['square', '--yes'],
     {'SIM_EVENT': 'sigterm,2'}, 130, r'stopped by SIGTERM before moving[\s\S]*nonzero=0 '),
    ('steady odom: more_shapes waits, a 7 s gap, then moves', 'shapes', ['star', '--yes'], {'SIM_ODOM_GAP': '8,7'}, 0,
     r'/odom paused for 7\.0 s[\s\S]*odometry steady for 5\.0 s, 2\d\.\d s after start'),
    ('steady odom: more_shapes endless gaps -> setup failure (2), no velocity command', 'shapes', ['star', '--yes'],
     {'SIM_ODOM_GAP_EVERY': '0.5,1.5,0.5'}, 2, r'SETUP FAILED: odometry not steady within 3\d s[\s\S]*nonzero=0 '),
    ('steady odom: more_shapes dry run also waits', 'shapes', ['star', '--dry-run'], {}, 0,
     r'odometry steady for 5\.0 s, 2\d\.\d s after start[\s\S]*dry run: all checks done'),
    ('steady odom: wall_approach waits, a 7 s gap, then drives', 'wall', ['--yes'], {'SIM_WALL': '1.2', 'SIM_ODOM_GAP': '8,7'}, 0,
     r'/odom paused for 7\.0 s[\s\S]*odometry steady for 5\.0 s, 2\d\.\d s after start'),
    ('steady odom: wall_approach endless gaps -> setup failure (2), no velocity command', 'wall', ['--yes'],
     {'SIM_WALL': '1.2', 'SIM_ODOM_GAP_EVERY': '0.5,1.5,0.5'}, 2, r'SETUP FAILED: odometry not steady within 3\d s[\s\S]*nonzero=0 '),
    ('steady odom: wall_approach dry run also waits', 'wall', ['--dry-run'], {'SIM_WALL': '1.2'}, 0,
     r'odometry steady for 5\.0 s[\s\S]*dry run: all checks done'),
    ('steady odom: keep_distance waits, a 7 s gap, then runs', 'keep', ['--yes', '--duration', '10'],
     {'SIM_OBJECT': '0.9,0.0', 'SIM_ODOM_GAP': '8,7'}, 0, r'/odom paused for 7\.0 s[\s\S]*odometry steady for 5\.0 s, 2\d\.\d s after start'),
    ('steady odom: keep_distance endless gaps -> setup failure (2), no velocity command', 'keep', ['--yes', '--duration', '10'],
     {'SIM_OBJECT': '0.9,0.0', 'SIM_ODOM_GAP_EVERY': '0.5,1.5,0.5'}, 2,
     r'SETUP FAILED: odometry not steady within 3\d s[\s\S]*nonzero=0 '),
    ('steady odom: keep_distance dry run also waits', 'keep', ['--dry-run', '--duration', '10'], {'SIM_OBJECT': '0.9,0.0'}, 0,
     r'odometry steady for 5\.0 s[\s\S]*dry run: all checks done'),
    # health_check.py: read only; faults come from SIM_HEALTH (see sim.py). Exit 0 all PASS/INFO, 1 WARN, 2 FAIL.
    ('health: healthy robot off the dock (default 10 s window)', 'health', [], {}, 0,
     r'PASS\s+Lidar /scan\s+7\.\d+ Hz, 720 beams, 75\.0 % valid'),
    ('health: docked -> scan INFO, no FAIL', 'health', ['--seconds', '5'], {'SIM_DOCKED': '1'}, 0,
     r'INFO\s+Lidar /scan\s+scan not checked: the lidar is switched off on the dock'),
    ('health: lidar missing -> FAIL', 'health', ['--seconds', '5'], {'SIM_HEALTH': 'lidar_missing'}, 2,
     r'FAIL\s+Lidar USB\s+no CP210x \(10c4:ea60\) in lsusb, no /dev/RPLIDAR'),
    ('health: lidar missing on the dock -> FAIL', 'health', ['--seconds', '5'],
     {'SIM_HEALTH': 'lidar_missing', 'SIM_DOCKED': '1'}, 2, r'FAIL\s+Lidar USB'),
    ('health: fallback access point -> WARN', 'health', ['--seconds', '5'], {'SIM_HEALTH': 'ap'}, 1,
     r'WARN\s+Wi-Fi\s+netplan-wlan0-Turtlebot4 on wlan0, 10\.42\.0\.1/24'),
    ('health: no Wi-Fi address -> FAIL', 'health', ['--seconds', '5'], {'SIM_HEALTH': 'no_wifi'}, 2,
     r'FAIL\s+Wi-Fi\s+no IPv4 address on wlan0'),
    ('health: turtlebot4.service inactive -> FAIL', 'health', ['--seconds', '5'], {'SIM_HEALTH': 'service_down'}, 2,
     r'FAIL\s+turtlebot4\.service\s+inactive'),
    ('health: other ROS_DOMAIN_ID -> WARN', 'health', ['--seconds', '5'], {'SIM_HEALTH': 'ros_env'}, 1,
     r'WARN\s+ROS environment'),
    ('health: base silent -> FAIL with the restart hint, within the time budget', 'health', [],
     {'SIM_HEALTH': 'base_silent'}, 2, r'FAIL\s+Base /odom[^\n]*\n\s+fix: restart the Create 3 base app: `curl -X POST'),
    ('health: Pi and base clocks 30 s apart -> FAIL', 'health', ['--seconds', '5'], {'SIM_HEALTH': 'clock_skew'}, 2,
     r'FAIL\s+Clock Pi vs base\s+Pi 30\.00 s ahead'),
    ('health: 0.6 s /odom gap -> WARN', 'health', ['--seconds', '5'], {'SIM_ODOM_GAP': '3,0.6'}, 1,
     r'WARN\s+Odometry gaps'),
    ('health: 2.5 s /odom gap -> FAIL', 'health', ['--seconds', '6'], {'SIM_ODOM_GAP': '2,2.5'}, 2,
     r'FAIL\s+Odometry gaps\s+largest arrival gap 2\.5'),
    ('health: low battery, ~/STOP, motion program running -> WARN', 'health', ['--seconds', '5'],
     {'SIM_HEALTH': 'battery_low,stop_file,motion_running'}, 1,
     r'WARN\s+Base /battery_state\s+battery 22 %[\s\S]*fix: rm ~/STOP[\s\S]*INFO\s+Motion programs\s+running: 2345 '),
    ('health: hot CPU, throttled, low disk -> WARN', 'health', ['--seconds', '5'],
     {'SIM_HEALTH': 'hot,throttled,low_disk'}, 1, r'WARN\s+Throttling\s+throttled=0x50005: under-voltage now'),
    ('health: overheated CPU -> FAIL', 'health', ['--seconds', '5'], {'SIM_HEALTH': 'overheat'}, 2,
     r'FAIL\s+CPU temperature\s+84\.0 C'),
    ('health: no vcgencmd, clock fix removed -> INFO only', 'health', ['--seconds', '5'],
     {'SIM_HEALTH': 'no_vcgencmd,no_clock_fix'}, 0, r'INFO\s+Throttling\s+vcgencmd not installed'),
    ('health: hanging nmcli and unreadable temperature are isolated', 'health', ['--seconds', '5'],
     {'SIM_HEALTH': 'nmcli_hang,bad_thermal'}, 1,
     r'WARN\s+Wi-Fi\s+10\.87\.10\.205/18 on wlan0, but connection unknown \(nmcli did not answer[\s\S]*'
     r'WARN\s+CPU temperature\s+check failed: ValueError[\s\S]*PASS\s+Throttling'),
    ('health: few valid lidar beams -> WARN', 'health', ['--seconds', '5'], {'SIM_ROOM': '0'}, 1,
     r'WARN\s+Lidar /scan\s+[\d.]+ Hz, 720 beams, 0\.0 % valid'),
]
HEALTH_BUDGET = 60.0     # s of (simulated) time a health check may take with the default window


def main():
    fails = 0
    for name, scen, args, env, expected, *pattern in SCENARIOS:
        e = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **env)
        r = subprocess.run([sys.executable, os.path.join(HERE, 'sim.py'), scen] + args,
                           capture_output=True, text=True, env=e, timeout=300)
        out = r.stdout + r.stderr
        m = re.search(r'SIM exit=(\S+)', out)
        code = r.returncode if m is None else (int(m.group(1)) if m.group(1).lstrip('-').isdigit() else r.returncode)
        # Safety invariants on every motion run: never above the caps, always ends with a zero command.
        caps_ok = True
        mv = re.search(r'max_v=([\d.]+) max_w=([\d.]+)', out)
        if mv:
            caps_ok = float(mv.group(1)) <= 0.15 + 1e-9 and float(mv.group(2)) <= 1.0 + 1e-9
        stop_ok = 'final_cmd=' not in out or 'final_cmd=(0.0,0.0)' in out or 'final_cmd=(0,0)' in out
        text_ok = not pattern or re.search(pattern[0], out) is not None
        # The health check must never command motion and must stay within its time budget.
        health_ok = True
        if scen == 'health':
            t = re.search(r'SIM exit=\S+ t=([\d.]+)s', out)
            health_ok = ' cmds=0 ' in out and t is not None and float(t.group(1)) <= HEALTH_BUDGET
        ok = code == expected and caps_ok and stop_ok and text_ok and health_ok
        fails += not ok
        print(f'{"PASS" if ok else "FAIL"} {name}: exit {code} (expected {expected})'
              + ('' if caps_ok else ' SPEED CAP EXCEEDED') + ('' if stop_ok else ' DID NOT END WITH ZERO VELOCITY')
              + ('' if text_ok else f' OUTPUT MISSING /{pattern[0] if pattern else ""}/')
              + ('' if health_ok else ' MOVED OR OVER THE TIME BUDGET'))
        if not ok:
            print('   ' + '\n   '.join(out.strip().splitlines()[-6:]))
    print(f'\n{fails} failure(s) in {len(SCENARIOS)} scenarios')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
