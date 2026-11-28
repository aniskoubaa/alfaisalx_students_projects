import sys, time
sys.path.insert(0, '/home/ubuntu/robot_code')
import rclpy, motion_shapes as m
rclpy.init()
n = m.MotionShapes(use_lidar=True, dry_run=False)  # publisher on, but we only ever send zero
m.wait_for(n, 'odom+scan', lambda: n.odom_time is not None and n.scan is not None, 30)
worst = 0.0; worst_at = None; t0 = time.monotonic(); gaps = []
period = 1.0 / m.CONTROL_RATE; nxt = time.monotonic()
while time.monotonic() - t0 < 20:
    nxt += period
    m.spin_for(n, nxt - time.monotonic()); n.send(0.0, 0.0)
    g = time.monotonic() - n.odom_time
    gaps.append(g)
    if g > worst: worst, worst_at = g, time.monotonic() - t0
late = sum(1 for g in gaps if g > 0.5)
print(f'ticks {len(gaps)} worst odom age {worst:.3f}s at t={worst_at:.1f}s, ticks over 0.5s: {late}, over 0.2s: {sum(1 for g in gaps if g>0.2)}')
