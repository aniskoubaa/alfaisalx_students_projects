# Diagnostic: 10 cm forward at 0.05 m/s, logging every /odom arrival gap. ODOM_STALE raised to 2 s for this probe only.
import sys, time
sys.path.insert(0, '/home/ubuntu/robot_code')
import rclpy, motion_shapes as m
m.ODOM_STALE = 2.0
rclpy.init()
n = m.MotionShapes(use_lidar=True, dry_run=False)
arrivals = []
orig = n.on_odom
def on_odom(msg):
    arrivals.append((time.monotonic(), msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9))
    orig(msg)
n.on_odom = on_odom
list(n.subscriptions)[0].callback = on_odom   # first subscription is /odom
try:
    ok = m.wait_for(n, 'odom, dock, scan', lambda: n.odom_time and n.is_docked is not None and n.scan is not None, 30)
    if not ok or n.is_docked:
        raise SystemExit(f'not ready (docked={n.is_docked})')
    m.log(f'front clear {n.nearest_front:.2f} m')
    if n.nearest_front < 0.40:
        raise SystemExit('front not clear')
    m.stand_still(n, 1.0, time.monotonic() + 30)
    t_move = time.monotonic()
    seg = m.add_timing([{'kind': 'straight', 'distance': 0.10}], 0.05, 0.5)[0]
    took = m.run_segment(n, seg, n.heading.total, time.monotonic() + 30)
    m.log(f'segment done in {took:.1f} s')
    m.stand_still(n, 1.0, time.monotonic() + 30)
except m.Abort as e:
    m.log(f'ABORT {e}')
finally:
    m.stop_robot(n)
    gaps = [(b[0] - a[0], b[1] - a[1], a[0] - t_move if 't_move' in dir() else 0) for a, b in zip(arrivals, arrivals[1:])]
    big = [g for g in gaps if g[0] > 0.15]
    print(f'odom msgs {len(arrivals)}, max arrival gap {max(g[0] for g in gaps):.3f} s')
    for g in big:
        print(f'  gap arrival {g[0]:.3f} s, stamp gap {g[1]:.3f} s, at t={g[2]:+.2f} s from motion start')
    rclpy.try_shutdown()
