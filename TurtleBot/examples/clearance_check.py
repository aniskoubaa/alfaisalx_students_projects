"""Measure free space in front of the robot from one lidar scan.

Prints the nearest obstacle within +/-30 degrees of straight ahead (in the robot's own frame)
and exits 0 if it is farther than the limit, 1 if it is closer, 2 if no scan arrived.
Usage: python3 clearance_check.py [min_metres]
"""
import math
import sys
import time

import rclpy
import tf2_ros
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.6
HALF_WIDTH = math.radians(30)


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Clearance(Node):
    def __init__(self):
        super().__init__('clearance_check')
        self.scan = None
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

    def on_scan(self, msg):
        self.scan = msg


def main():
    rclpy.init()
    node = Clearance()
    end = time.time() + 40
    offset = None
    while time.time() < end and (node.scan is None or offset is None):
        rclpy.spin_once(node, timeout_sec=0.5)
        if node.scan is not None and offset is None:
            try:
                t = node.tf_buffer.lookup_transform('base_link', node.scan.header.frame_id, rclpy.time.Time())
                offset = yaw_of(t.transform.rotation)
            except tf2_ros.TransformException:
                pass
    if node.scan is None:
        print('NO SCAN: the lidar is not publishing')
        sys.exit(2)
    if offset is None:
        offset = 0.0
        print('warning: no transform from the lidar to the robot, assuming the lidar faces forward')
    s = node.scan
    front = []
    for i, r in enumerate(s.ranges):
        if not (s.range_min < r < s.range_max):
            continue
        a = s.angle_min + i * s.angle_increment + offset
        a = math.atan2(math.sin(a), math.cos(a))
        if abs(a) <= HALF_WIDTH:
            front.append(r)
    nearest = min(front) if front else float('inf')
    print(f'lidar frame offset {math.degrees(offset):.0f} deg, beams in front: {len(front)}, nearest in front: {nearest:.2f} m (limit {LIMIT:.2f} m)')
    node.destroy_node()
    rclpy.try_shutdown()
    sys.exit(0 if nearest > LIMIT else 1)


if __name__ == '__main__':
    main()
