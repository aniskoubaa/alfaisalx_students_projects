#!/usr/bin/env python3
"""Test tool: press the front-panel buttons from software and print what the screen shows. Runs on the robot.

    source /etc/turtlebot4/setup.bash
    python3 press_buttons.py show 4 4 3 1 2 show

Steps, in order: a number 1..4 = press that button; show = print the 5 screen lines; wait:S = wait S seconds;
until:TEXT:S = wait at most S seconds until the screen contains TEXT (exit 1 if it never does).
Button 1 selects, so this can start the robot moving: use it only with a person next to the robot.
The real button reader publishes /hmi/buttons at about 95 Hz, so a single message is overwritten at once; a press here
is a flood of messages for 0.15 s. It is a new ROS program (TB-25): do not run it while timing the base.
"""
import sys
import time


def main(steps):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from turtlebot4_msgs.msg import UserButton, UserDisplay

    rclpy.init()
    node = Node('press_buttons')
    latest = {'display': None}
    node.create_subscription(UserDisplay, '/hmi/display', lambda m: latest.__setitem__('display', m),
                             qos_profile_sensor_data)
    pub = node.create_publisher(UserButton, '/hmi/buttons', qos_profile_sensor_data)

    def spin(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.02)

    def screen():
        d = latest['display']
        return [] if d is None else [line.rstrip() for line in d.entries]

    def press(number):
        state = [False] * 4
        state[number - 1] = True
        end = time.monotonic() + 0.15
        while time.monotonic() < end:
            pub.publish(UserButton(button=state))
            rclpy.spin_once(node, timeout_sec=0.002)
        spin(0.8)

    spin(5.0)   # discovery
    code = 0
    for step in steps:
        if step in ('1', '2', '3', '4'):
            press(int(step))
            print(f'{time.strftime("%H:%M:%S")} pressed {step}: {screen()}', flush=True)
        elif step == 'show':
            print(f'{time.strftime("%H:%M:%S")} screen: {screen()}', flush=True)
        elif step.startswith('wait:'):
            spin(float(step[5:]))
        elif step.startswith('until:'):
            _, text, seconds = step.split(':')
            end = time.monotonic() + float(seconds)
            while time.monotonic() < end and text not in ' '.join(screen()):
                spin(0.2)
            found = text in ' '.join(screen())
            word = 'found' if found else 'NOT FOUND'
            print(f'{time.strftime("%H:%M:%S")} until {text!r}: {word}: {screen()}', flush=True)
            if not found:
                code = 1
                break
    node.destroy_node()
    rclpy.try_shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
