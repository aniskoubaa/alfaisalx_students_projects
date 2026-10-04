# Read one scan, print the nearest range per 30-degree sector in the ROBOT frame (0 = ahead, + = left). No motion.
import math, rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
rclpy.init(); n = rclpy.create_node('opensectors'); got = []
n.create_subscription(LaserScan, '/scan', lambda m: got.append(m), qos_profile_sensor_data)
while len(got) < 3: rclpy.spin_once(n, timeout_sec=1.0)
s = got[-1]; sec = {}
for i, r in enumerate(s.ranges):
    if s.range_min < r < s.range_max:
        a = math.degrees(math.atan2(math.sin(s.angle_min + i*s.angle_increment + math.pi/2), math.cos(s.angle_min + i*s.angle_increment + math.pi/2)))
        k = int(round(a / 30.0)) * 30
        k = -180 if k == 180 else k
        sec[k] = min(sec.get(k, 99), r)
for k in sorted(sec): print(f'{k:+5d} deg  nearest {sec[k]:.2f} m')
