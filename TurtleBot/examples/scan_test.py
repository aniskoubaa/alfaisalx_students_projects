"""Print the distance to the nearest object the lidar sees. Does not move the robot."""
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class ScanTest(Node):
    def __init__(self):
        super().__init__('scan_test')
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

    def on_scan(self, msg):
        ranges = [r for r in msg.ranges if msg.range_min < r < msg.range_max]
        if ranges:
            self.get_logger().info(f'Nearest object: {min(ranges):.2f} m')


def main():
    rclpy.init()
    node = ScanTest()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
