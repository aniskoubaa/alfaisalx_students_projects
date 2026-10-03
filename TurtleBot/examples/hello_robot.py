"""First test program: show a message on the robot's screen and turn the light ring green for 5 seconds.

Does not move the robot, so it is safe to run while it is on the dock.
"""
import time

import rclpy
from irobot_create_msgs.msg import LedColor, LightringLeds
from rclpy.node import Node
from std_msgs.msg import String

MESSAGE = 'Hello from Ibrahim'
SECONDS = 5


class HelloRobot(Node):
    def __init__(self):
        super().__init__('hello_robot')
        self.display = self.create_publisher(String, '/hmi/display/message', 10)
        self.lights = self.create_publisher(LightringLeds, '/cmd_lightring', 10)

    def wait_for_robot(self, timeout=30.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.display.get_subscription_count() and self.lights.get_subscription_count():
                return True
            rclpy.spin_once(self, timeout_sec=0.5)
        return False

    def lightring(self, r, g, b, override):
        msg = LightringLeds()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.override_system = override
        msg.leds = [LedColor(red=r, green=g, blue=b) for _ in range(6)]
        self.lights.publish(msg)


def main():
    rclpy.init()
    node = HelloRobot()
    if not node.wait_for_robot():
        node.get_logger().error('Could not find the robot screen or light ring. Is the robot on and running?')
    else:
        node.display.publish(String(data=MESSAGE))
        node.get_logger().info(f'Sent "{MESSAGE}" to the screen, light ring green for {SECONDS} s')
        end = time.time() + SECONDS
        while time.time() < end:
            node.lightring(0, 255, 0, True)
            time.sleep(0.2)
        node.lightring(0, 0, 0, False)
        node.get_logger().info('Done, light ring handed back to the robot')
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
