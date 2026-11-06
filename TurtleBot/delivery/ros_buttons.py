"""Read the front-panel buttons without waking up for every message. Used by delivery_menu.py and delivery_mission.py.

turtlebot4_base_node publishes /hmi/buttons at about 95 Hz, all the time. A normal subscription runs Python 95 times a
second: on the robot that cost the idle menu about a third of a CPU core (measured 2026-11-06). Here the subscription
sits on a second node that no executor spins, so nothing wakes up, and poll() takes what has queued, every 0.1 s or so.
A second node in the same process adds no new DDS participant, so it is not a new base stall risk (TB-25).
ROS is imported inside the class, so this file can be imported without ROS.
"""
QUEUE = 50      # messages kept between two polls: about 0.5 s at 95 Hz, so a press is not lost between two polls


class ButtonPoller:
    """poll() calls callback(msg) for every /hmi/buttons message that arrived since the last poll, oldest first."""

    def __init__(self, node_name, callback):
        from rclpy.node import Node
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        from turtlebot4_msgs.msg import UserButton
        self.callback = callback
        self.node = Node(node_name)
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=QUEUE, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.sub = self.node.create_subscription(UserButton, '/hmi/buttons', lambda _msg: None, qos)

    def poll(self):
        sub = self.sub
        with sub.handle:
            while True:
                taken = sub.handle.take_message(sub.msg_type, sub.raw)
                if taken is None or taken[0] is None:
                    return
                self.callback(taken[0])

    def close(self):
        self.node.destroy_node()
