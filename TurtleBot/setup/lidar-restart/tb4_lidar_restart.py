#!/usr/bin/env python3
"""Lidar auto-restart for the TurtleBot 4 (TurtleBot/ROADMAP.md, TB-24).

The dock power saver stops the lidar motor while the robot is docked. Sometimes the motor is not started again
after an undock, /scan stays silent and programs fail with "no /scan". This node watches for that and calls the
std_srvs/Empty service /start_motor.

Rules:
  - Docked: do nothing.
  - Undocked (a dock -> undock change, or the node starts while undocked): wait 10 s. If no /scan arrived in the
    last 3 s, call /start_motor (waits up to 5 s for the service), wait 8 s, check again.
  - At most 3 calls per undock. Then one clear warning, and no more tries until the next undock.
  - It never publishes to /cmd_vel and never calls a motion action. Its only ROS output is the /start_motor call.

The decision logic is the plain class LidarRestartLogic (no ROS imports, time passed in), tested offline by
TurtleBot/tests/offline/test_lidar_restart.py. rclpy is imported only inside main(). One node, a
SingleThreadedExecutor, no parameter services and no /rosout publisher, to keep the load on the ROS graph and the
CPU small. Run it with the robot's ROS environment:  source /etc/turtlebot4/setup.bash
"""
import sys
import time

# ---- timing (seconds)
SETTLE_S = 10.0          # wait after an undock before the first check
SCAN_FRESH_S = 3.0       # a scan newer than this counts as "lidar running"
RETRY_WAIT_S = 8.0       # wait after a /start_motor call before checking again
MAX_ATTEMPTS = 3         # calls per undock
SERVICE_WAIT_S = 5.0     # how long to wait for /start_motor to appear
CALL_TIMEOUT_S = 10.0    # give up on a call that never answers
TICK_S = 0.5             # decision timer period


class LidarRestartLogic:
    """Decides when to ask for /start_motor. No ROS, no clock: every method takes `now` (seconds, any monotonic origin).

    tick(now) returns a list of (kind, text); kind is 'info', 'warn' or 'call'. On 'call' the caller must perform
    the /start_motor call and then report on_call_result(now, ok).
    """
    IDLE, SETTLE, CALLING, WAIT, DONE, GAVE_UP = 'idle', 'settle', 'calling', 'wait', 'done', 'gave_up'

    def __init__(self, settle_s=SETTLE_S, fresh_s=SCAN_FRESH_S, retry_wait_s=RETRY_WAIT_S, max_attempts=MAX_ATTEMPTS):
        self.settle_s, self.fresh_s, self.retry_wait_s, self.max_attempts = settle_s, fresh_s, retry_wait_s, max_attempts
        self.docked = None          # unknown until the first /dock_status
        self.last_scan = None
        self.state = self.IDLE
        self.attempts = 0
        self.check_at = None
        self._msgs = []

    def _say(self, kind, text):
        self._msgs.append((kind, text))

    def scan_fresh(self, now):
        return self.last_scan is not None and 0.0 <= now - self.last_scan <= self.fresh_s

    def on_scan(self, now):
        self.last_scan = now

    def on_dock(self, is_docked, now):
        is_docked = bool(is_docked)
        if is_docked == self.docked:
            return
        first, self.docked = self.docked is None, is_docked
        if is_docked:
            self.state, self.attempts, self.check_at = self.IDLE, 0, None
            self._say('info', 'docked: the lidar is stopped by the dock power saver, nothing to do')
        else:
            self.state, self.attempts, self.check_at = self.SETTLE, 0, now + self.settle_s
            self._say('info', '%s: checking /scan in %.0f s' % (
                'node started while undocked' if first else 'undocked', self.settle_s))

    def on_call_result(self, now, ok):
        if self.state != self.CALLING:
            return
        self._say('info' if ok else 'warn', '/start_motor %s (attempt %d of %d), checking /scan in %.0f s' % (
            'called' if ok else 'FAILED', self.attempts, self.max_attempts, self.retry_wait_s))
        self.state, self.check_at = self.WAIT, now + self.retry_wait_s

    def tick(self, now):
        if self.state in (self.SETTLE, self.WAIT) and now >= self.check_at:
            if self.scan_fresh(now):
                note = ''
                if self.attempts:
                    note = ' (after %d /start_motor call%s)' % (self.attempts, '' if self.attempts == 1 else 's')
                self._say('info', '/scan is arriving, lidar is running' + note)
                self.state = self.DONE
            elif self.attempts >= self.max_attempts:
                self._say('warn', 'no /scan after %d /start_motor calls; giving up until the next undock. '
                                  'Check the lidar USB cable and "journalctl -u turtlebot4 | grep -i rplidar"' % self.attempts)
                self.state = self.GAVE_UP
            else:
                self.attempts += 1
                self._say('warn', 'no /scan in the last %.0f s: calling /start_motor (attempt %d of %d)' % (
                    self.fresh_s, self.attempts, self.max_attempts))
                self._say('call', '/start_motor')
                self.state = self.CALLING
        out, self._msgs = self._msgs, []
        return out


def main(argv=None):
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    from std_srvs.srv import Empty
    from irobot_create_msgs.msg import DockStatus

    rclpy.init(args=argv)
    node = rclpy.create_node('tb4_lidar_restart', start_parameter_services=False, enable_rosout=False)
    log = node.get_logger()
    logic = LidarRestartLogic()
    client = node.create_client(Empty, '/start_motor')
    call = {'phase': None, 'since': 0.0, 'future': None}   # phase: None, 'service', 'answer'

    def on_scan(_msg):               # only the arrival time is kept
        logic.on_scan(time.monotonic())

    def on_dock(msg):
        logic.on_dock(msg.is_docked, time.monotonic())

    def finish(ok):
        call.update(phase=None, future=None)
        logic.on_call_result(time.monotonic(), ok)

    def step_call(now):
        if call['phase'] == 'service':
            if client.service_is_ready():
                call.update(phase='answer', since=now, future=client.call_async(Empty.Request()))
            elif now - call['since'] > SERVICE_WAIT_S:
                log.warning('/start_motor service not available after %.0f s' % SERVICE_WAIT_S)
                finish(False)
        elif call['phase'] == 'answer':
            if call['future'].done():
                finish(call['future'].exception() is None)
            elif now - call['since'] > CALL_TIMEOUT_S:
                log.warning('/start_motor gave no answer in %.0f s' % CALL_TIMEOUT_S)
                finish(False)

    def on_timer():
        now = time.monotonic()
        step_call(now)
        for kind, text in logic.tick(now):
            if kind == 'call':
                call.update(phase='service', since=now)
                step_call(now)
            elif kind == 'warn':
                log.warning(text)
            else:
                log.info(text)

    node.create_subscription(DockStatus, '/dock_status', on_dock, qos_profile_sensor_data)
    node.create_subscription(LaserScan, '/scan', on_scan, qos_profile_sensor_data)
    node.create_timer(TICK_S, on_timer)
    log.info('tb4_lidar_restart started: watching /dock_status and /scan; never publishes to /cmd_vel')
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
