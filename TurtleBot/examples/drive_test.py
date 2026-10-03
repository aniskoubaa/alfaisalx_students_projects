"""Drive forward slowly for 2 seconds, then stop. MOVES THE ROBOT: clear about 1 m in front of it first.

On this TurtleBot 4 (ROS 2 Jazzy) /cmd_vel takes geometry_msgs/msg/TwistStamped, not Twist.
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TwistStamped

SPEED = 0.1        # metres per second
DRIVE_TIME = 2.0   # seconds
RATE = 10          # messages per second


class DriveTest(Node):
    def __init__(self):
        super().__init__('drive_test')
        self.pub = self.create_publisher(TwistStamped, '/cmd_vel', 10)
        self.ticks = 0
        self.create_timer(1.0 / RATE, self.tick)

    def tick(self):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        if self.ticks < DRIVE_TIME * RATE:
            msg.twist.linear.x = SPEED
        self.pub.publish(msg)
        self.ticks += 1
        if self.ticks >= DRIVE_TIME * RATE + 5:
            raise SystemExit


def main():
    rclpy.init()
    node = DriveTest()
    try:
        rclpy.spin(node)
    except (SystemExit, KeyboardInterrupt):
        pass
    node.pub.publish(TwistStamped())
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
