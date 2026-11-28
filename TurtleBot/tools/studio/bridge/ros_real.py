"""RosReal: the real ROS 2 node. It subscribes to the robot topics, keeps the latest messages, publishes
velocity commands and calls services and actions. It needs rclpy and is not used in fake mode."""
from .base import *  # bundle: skip
from .pure_helpers import *  # bundle: skip
from .stream_helpers import *  # bundle: skip
from .mapping_helpers import *  # bundle: skip
from .ros_base import *  # bundle: skip


class RosReal(RosBase):
    def __init__(self):
        self.available = False
        self.error = None
        self.emit = lambda *a, **k: None
        self._lock = threading.Lock()
        self._odom = self._scan = self._wheel = None        # (raw bytes, receive monotonic)
        self._odom_n = self._scan_n = 0
        self._map = None                                    # (raw OccupancyGrid bytes, receive monotonic)
        self._map_n = 0
        self._slam = None                                   # ((x, y, yaw), odom (x, y, yaw) or None, receive monotonic)
        self._map_subs = False
        self._rate = {}
        self._battery = {}
        self._dock = {}
        self._haz = collections.deque(maxlen=64)
        self._dock_t = self._batt_t = None
        self._scan_frame = None
        self._scan_yaw = SCAN_YAW_DEFAULT
        self._yaw_assumed = True
        self._tf_started = False
        self._goals = {}
        self._clients = {}
        self._watches = {}
        self._own_subs = collections.Counter()
        self._own_pubs = collections.Counter()
        self._stop = threading.Event()
        self._cache = {}

    # ---- startup
    def start(self, emit):
        self.emit = emit
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import qos_profile_sensor_data
            from rclpy.serialization import deserialize_message
            from geometry_msgs.msg import Twist, TwistStamped
            from nav_msgs.msg import Odometry
            from sensor_msgs.msg import BatteryState, LaserScan
            from std_srvs.srv import Empty
            from irobot_create_msgs.msg import DockStatus, HazardDetectionVector, WheelStatus
            from irobot_create_msgs.srv import EStop
            try:
                from rclpy.signals import SignalHandlerOptions
                rclpy.init(args=None, signal_handler_options=SignalHandlerOptions.NO)
            except ImportError:
                rclpy.init(args=None)
        except Exception as e:
            self.error = "%s: %s" % (type(e).__name__, e)
            log("ROS not available:", self.error)
            return
        self.rclpy, self.deser, self.sensor_qos = rclpy, deserialize_message, qos_profile_sensor_data
        self.M = dict(Twist=Twist, TwistStamped=TwistStamped, Odometry=Odometry, LaserScan=LaserScan,
                      BatteryState=BatteryState, DockStatus=DockStatus, WheelStatus=WheelStatus, Empty=Empty,
                      EStop=EStop, HazardDetectionVector=HazardDetectionVector)
        try:
            self.node = rclpy.create_node("studio_bridge_%d" % os.getpid(), start_parameter_services=False,
                                          enable_rosout=False)
            # publishers first: the e-stop must have no set-up delay
            self.pub_cmd = self.node.create_publisher(TwistStamped, "/cmd_vel", 10)
            self.pub_unst = self.node.create_publisher(Twist, "/cmd_vel_unstamped", 10)
            self._own_pubs.update(["/cmd_vel", "/cmd_vel_unstamped"])
            q = qos_profile_sensor_data

            def sub(cls, topic, cb, raw=False):
                self.node.create_subscription(cls, topic, cb, q, raw=raw)
                self._own_subs[topic] += 1

            sub(Odometry, "/odom", self._cb_odom, raw=True)
            sub(LaserScan, "/scan", self._cb_scan, raw=True)
            sub(WheelStatus, "/wheel_status", self._cb_wheel, raw=True)      # ~30 Hz: bytes only, parsed per status tick
            sub(BatteryState, "/battery_state", self._cb_battery)
            sub(DockStatus, "/dock_status", self._cb_dock)
            sub(HazardDetectionVector, "/hazard_detection", self._cb_haz)
            self._svc = {"/e_stop": self.node.create_client(EStop, "/e_stop"),
                         "/start_motor": self.node.create_client(Empty, "/start_motor"),
                         "/stop_motor": self.node.create_client(Empty, "/stop_motor")}
            # Single-threaded on purpose: MultiThreadedExecutor cost about 97 % of a Pi 4 core on 2026-10-24,
            # the single-threaded one 11 % for the same subscriptions. Calls wait on futures in their own threads.
            self.executor = SingleThreadedExecutor()
            self.executor.add_node(self.node)
            self._spin = threading.Thread(target=self._spin_loop, name="rclpy", daemon=True)
            self._spin.start()
            self.available = True
        except Exception as e:
            self.error = "%s: %s" % (type(e).__name__, e)
            log("ROS set-up failed:", self.error)

    def _spin_loop(self):
        try:
            self.executor.spin()
        except Exception as e:
            log("executor stopped:", e)

    def shutdown(self):
        self._stop.set()
        if not self.available:
            return
        self.available = False
        try:
            self.executor.shutdown(timeout_sec=0.5)
        except Exception:
            pass
        try:
            self.node.destroy_node()
            self.rclpy.shutdown()
        except Exception:
            pass

    # ---- callbacks: tiny, never block
    def _cb_odom(self, data):
        self._odom = (data, time.monotonic())
        self._odom_n += 1

    def _cb_scan(self, data):
        self._scan = (data, time.monotonic())
        self._scan_n += 1

    def _cb_wheel(self, data):
        self._wheel = (data, time.monotonic())

    def _cb_battery(self, m):
        self._battery = {"percent": None if not math.isfinite(m.percentage) else round(m.percentage * 100.0, 1)
                         if m.percentage <= 1.5 else round(m.percentage, 1),
                         "voltage": round(m.voltage, 2) if math.isfinite(m.voltage) else None,
                         "charging": None, "_status": int(m.power_supply_status),
                         "current_a": round(m.current, 2) if math.isfinite(m.current) else None}
        self._batt_t = time.monotonic()

    def _cb_dock(self, m):
        self._dock = {"is_docked": bool(m.is_docked), "dock_visible": bool(m.dock_visible)}
        self._dock_t = time.monotonic()

    def _cb_haz(self, m):
        now = time.monotonic()
        for d in m.detections:
            self._haz.append((now, hazard_name(d.type)))

    # ---- snapshot (called at the status period, off the executor thread)
    def _rate_of(self, name, n, now):
        pn, pt, rate = self._rate.get(name, (0, now, None))
        if now - pt >= 0.5:
            rate = round((n - pn) / (now - pt), 1) if (n or pn) else None
            self._rate[name] = (n, now, rate)
        elif name not in self._rate:
            self._rate[name] = (pn, pt, rate)
        return rate

    def snapshot(self):
        now = time.monotonic()
        out = {"battery": {"percent": None, "voltage": None, "charging": None, "current_a": None, "full": None}, "dock": {"is_docked": None, "dock_visible": None},
               "odom": {"x": None, "y": None, "yaw_deg": None, "vx": None, "wz": None, "age_s": None, "rate_hz": None},
               "scan": {"rate_hz": None, "front_m": None, "min_m": None, "age_s": None},
               "hazards": [], "wheels_enabled": None}
        if not self.available:
            return out
        out["dock"].update(self._dock)
        out["battery"].update({k: v for k, v in self._battery.items() if not k.startswith("_")})
        if self._battery:
            b = out["battery"]
            b["charging"], b["full"] = battery_flags(self._battery.get("_status"), b.get("current_a"), b.get("percent"),
                                                     out["dock"].get("is_docked"))
        od = self._odom
        if od is not None:
            o = out["odom"]
            o["age_s"], o["rate_hz"] = round(now - od[1], 2), self._rate_of("odom", self._odom_n, now)
            try:
                m = self._cached("odom", od[0], lambda: self.deser(od[0], self.M["Odometry"]))
                p, q, tw = m.pose.pose.position, m.pose.pose.orientation, m.twist.twist
                o.update(x=round(p.x, 3), y=round(p.y, 3), yaw_deg=round(yaw_deg_from_quat(q.x, q.y, q.z, q.w), 1),
                         vx=round(tw.linear.x, 3), wz=round(tw.angular.z, 3))
            except Exception as e:
                log("odom decode:", e)
        sc = self._scan
        if sc is not None:
            s = out["scan"]
            s["age_s"], s["rate_hz"] = round(now - sc[1], 2), self._rate_of("scan", self._scan_n, now)
            try:
                m = self._cached("scan", sc[0], lambda: self.deser(sc[0], self.M["LaserScan"]))
                if self._scan_frame is None:
                    self._scan_frame = m.header.frame_id
                    self._start_tf(m.header.frame_id)
                rmax = m.range_max if m.range_max and math.isfinite(m.range_max) else None
                s["front_m"], s["min_m"] = scan_front_min(m.ranges, m.angle_min, m.angle_increment, self._scan_yaw,
                                                          max(BODY_MIN_M, m.range_min or 0.0), rmax)
            except Exception as e:
                log("scan decode:", e)
            s["scan_yaw_assumed"] = self._yaw_assumed
        out["hazards"] = sorted({n for t, n in list(self._haz) if now - t <= HAZARD_WINDOW})
        wh = self._wheel
        if wh is not None and now - wh[1] < 5.0:
            try:
                m = self._cached("wheel", wh[0], lambda: self.deser(wh[0], self.M["WheelStatus"]))
                out["wheels_enabled"] = bool(m.wheels_enabled)
            except Exception as e:
                log("wheel decode:", e)
        return out

    def _cached(self, key, raw, fn):
        c = self._cache.get(key)
        if c and c[0] is raw:
            return c[1]
        v = fn()
        self._cache[key] = (raw, v)
        return v

    def _start_tf(self, frame):
        if self._tf_started or not frame:
            return
        self._tf_started = True
        threading.Thread(target=self._tf_lookup, args=(frame,), name="tf", daemon=True).start()

    def _tf_lookup(self, frame):
        """One-shot TF lookup base_link <- scan frame, then the listener is dropped (it would cost CPU at /tf rates)."""
        lis = None
        try:
            import tf2_ros
            buf = tf2_ros.Buffer()
            lis = tf2_ros.TransformListener(buf, self.node, spin_thread=False)
            end = time.monotonic() + 10.0
            while time.monotonic() < end and not self._stop.is_set():
                try:
                    t = buf.lookup_transform("base_link", frame, self.rclpy.time.Time())
                    q = t.transform.rotation
                    self._scan_yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
                    self._yaw_assumed = False
                    log("scan yaw from TF: %.1f deg" % math.degrees(self._scan_yaw))
                    break
                except Exception:
                    time.sleep(0.3)
        except Exception as e:
            log("TF not used, assuming +90 deg:", e)
        finally:
            try:
                if lis is not None:
                    lis.unregister()
            except Exception:
                pass

    # ---- Studio 2.0: manual driving, scan and pose streams (reuse the existing node, publisher and subscriptions)
    def publish_cmd(self, vx, wz):
        ts = self.M["TwistStamped"]()
        ts.header.stamp = self.node.get_clock().now().to_msg()
        ts.twist.linear.x = float(vx)
        ts.twist.angular.z = float(wz)
        self.pub_cmd.publish(ts)
        if vx == 0.0 and wz == 0.0:
            self.pub_unst.publish(self.M["Twist"]())       # a zero must reach whichever topic the base listens to

    def is_docked(self):
        v = self._dock.get("is_docked")
        return None if v is None else bool(v)

    def scan_data(self):
        sc = self._scan
        if sc is None or not self.available:
            return None
        try:
            m = self._cached("scan", sc[0], lambda: self.deser(sc[0], self.M["LaserScan"]))
            if self._scan_frame is None:
                self._scan_frame = m.header.frame_id
                self._start_tf(m.header.frame_id)
            return {"ranges": m.ranges, "angle_min": m.angle_min, "angle_inc": m.angle_increment,
                    "range_min": max(BODY_MIN_M, m.range_min or 0.0), "range_max": m.range_max, "yaw": self._scan_yaw,
                    "seq": self._scan_n, "age_s": time.monotonic() - sc[1], "yaw_assumed": self._yaw_assumed}
        except Exception as e:
            log("scan decode:", e)
            return None

    def pose_data(self):
        od = self._odom
        if od is None or not self.available:
            return None
        try:
            m = self._cached("odom", od[0], lambda: self.deser(od[0], self.M["Odometry"]))
            p, q, tw = m.pose.pose.position, m.pose.pose.orientation, m.twist.twist
            return {"x": p.x, "y": p.y, "yaw": math.radians(yaw_deg_from_quat(q.x, q.y, q.z, q.w)),
                    "vx": tw.linear.x, "wz": tw.angular.z, "age_s": time.monotonic() - od[1], "seq": self._odom_n}
        except Exception as e:
            log("odom decode:", e)
            return None

    # ---- map (subscriptions are created on the first map_on and kept; decoded only when the stream asks)
    def ensure_map_subs(self):
        with self._lock:
            if self._map_subs:
                return
            if not self.available:
                raise RosError("ROS not available: %s" % (self.error or "not started"))
            try:
                from geometry_msgs.msg import PoseWithCovarianceStamped
                from nav_msgs.msg import OccupancyGrid
                from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
                qos = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST, reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
                self.M["OccupancyGrid"] = OccupancyGrid
                self.node.create_subscription(OccupancyGrid, "/map", self._cb_map, qos, raw=True)
                self.node.create_subscription(PoseWithCovarianceStamped, "/pose", self._cb_slam_pose, 10)
            except Exception as e:
                raise RosError("cannot subscribe to /map and /pose: %s: %s" % (type(e).__name__, e))
            self._own_subs.update(["/map", "/pose"])
            self._map_subs = True

    def map_reset(self):
        """A new SLAM session must not show the previous one: drop the map, the SLAM pose and the decoded copy."""
        self._map = None
        self._slam = None
        try:
            self._cache.pop("map", None)
        except Exception:
            pass

    def _cb_map(self, data):
        self._map = (data, time.monotonic())
        self._map_n += 1

    def _cb_slam_pose(self, m):
        try:
            p, q = m.pose.pose.position, m.pose.pose.orientation
            slam = (p.x, p.y, math.radians(yaw_deg_from_quat(q.x, q.y, q.z, q.w)))
            od = self.pose_data()
            odom = (od["x"], od["y"], od["yaw"]) if od and od["age_s"] < 1.0 else None
            self._slam = (slam, odom, time.monotonic())
        except Exception as e:
            log("slam pose:", e)

    def map_data(self):
        mp = self._map
        if mp is None or not self.available:
            return None
        try:
            m = self._cached("map", mp[0], lambda: self.deser(mp[0], self.M["OccupancyGrid"]))
            i = m.info
            if i.width < 1 or i.height < 1 or len(m.data) != i.width * i.height:
                return None
            q = i.origin.orientation
            yaw = math.radians(yaw_deg_from_quat(q.x, q.y, q.z, q.w))
            return {"seq": self._map_n, "width": i.width, "height": i.height, "resolution": i.resolution,
                    "origin": (i.origin.position.x, i.origin.position.y, yaw), "cells": m.data,
                    "age_s": time.monotonic() - mp[1]}
        except Exception as e:
            log("map decode:", e)
            return None

    def map_pose(self):
        od = self.pose_data()
        if od is None or od["age_s"] > 2.0:
            return None
        now = (od["x"], od["y"], od["yaw"])
        sl = self._slam
        if sl is None or sl[1] is None:
            return {"x": now[0], "y": now[1], "yaw": now[2], "source": "odom"}
        x, y, yaw = compose_map_pose(sl[0], sl[1], now)
        return {"x": x, "y": y, "yaw": yaw, "source": "slam"}

    # ---- graph
    def topics(self):
        out = []
        for name, types in sorted(self.node.get_topic_names_and_types()):
            pubs = max(0, self.node.count_publishers(name) - self._own_pubs.get(name, 0))
            subs = max(0, self.node.count_subscribers(name) - self._own_subs.get(name, 0))
            out.append({"name": name, "types": list(types), "publishers": pubs, "subscribers": subs})
        return out

    def watch_add(self, topic, typ, max_hz, on_msg):
        if not typ:
            types = dict(self.node.get_topic_names_and_types()).get(topic)
            if not types:
                raise RosError("topic %s not found (give a type)" % topic)
            typ = types[0]
        from rosidl_runtime_py.utilities import get_message
        from rosidl_runtime_py import message_to_ordereddict
        cls = get_message(typ)
        state = {"n": 0, "last": 0.0, "t0": time.monotonic(), "rate": None, "n0": 0}
        min_dt = 1.0 / max(0.05, float(max_hz))

        def cb(data):
            now = time.monotonic()
            state["n"] += 1
            if now - state["t0"] >= 1.0:
                state["rate"] = round((state["n"] - state["n0"]) / (now - state["t0"]), 1)
                state["n0"], state["t0"] = state["n"], now
            if now - state["last"] < min_dt:
                return
            state["last"] = now
            try:
                on_msg(message_to_ordereddict(self.deser(data, cls)), state["rate"])
            except Exception as e:
                log("watch decode:", e)

        s = self.node.create_subscription(cls, topic, cb, self.sensor_qos, raw=True)
        key = object()
        self._watches[key] = (s, topic)
        self._own_subs[topic] += 1
        return key, typ

    def watch_remove(self, key):
        w = self._watches.pop(key, None)
        if w:
            self._own_subs[w[1]] -= 1
            try:
                self.node.destroy_subscription(w[0])
            except Exception:
                pass

    # ---- publish / services / actions
    def zero_burst(self, n=10, hz=20.0):
        sent = 0
        for i in range(n):
            ts = self.M["TwistStamped"]()
            ts.header.stamp = self.node.get_clock().now().to_msg()
            self.pub_cmd.publish(ts)
            self.pub_unst.publish(self.M["Twist"]())
            sent += 1
            if i < n - 1:
                time.sleep(1.0 / hz)
        return sent

    def _call(self, name, req, timeout):
        cl = self._svc[name]
        end = time.monotonic() + timeout
        while not cl.service_is_ready():
            if time.monotonic() >= end:
                raise RosError("service %s not available" % name)
            time.sleep(0.05)
        done = threading.Event()
        fut = cl.call_async(req)
        fut.add_done_callback(lambda f: done.set())
        if not done.wait(max(0.1, end - time.monotonic())):
            try:
                cl.remove_pending_request(fut)
            except Exception:
                pass
            raise RosError("service %s timed out after %.0f s" % (name, timeout))
        return fut.result()

    def call_estop(self, on, timeout=3.0):
        req = self.M["EStop"].Request()
        req.e_stop_on = bool(on)
        r = self._call("/e_stop", req, timeout)
        return bool(r.success), str(r.message)

    def lidar(self, on, timeout=5.0):
        self._call("/start_motor" if on else "/stop_motor", self.M["Empty"].Request(), timeout)
        return "lidar motor %s" % ("start" if on else "stop")

    def services_ready(self):
        return {n: bool(c.service_is_ready()) for n, c in self._svc.items()}

    def _client(self, name):
        if name in self._clients:
            return self._clients[name]
        from rclpy.action import ActionClient
        from irobot_create_msgs.action import Dock, Undock
        cls = {"dock": Dock, "undock": Undock}[name]
        c = (ActionClient(self.node, cls, "/" + name), cls)
        self._clients[name] = c
        return c

    def start_action(self, name, timeout=5.0):
        if name not in ("dock", "undock"):
            raise RosError("unknown action %s" % name)
        client, cls = self._client(name)
        if not client.wait_for_server(timeout_sec=2.0):
            raise RosError("action server /%s not available" % name)
        last_fb = [0.0]

        def fb(msg):
            if time.monotonic() - last_fb[0] >= 1.0:
                last_fb[0] = time.monotonic()
                self.emit({"ev": "action", "name": name, "state": "feedback", "detail": str(msg.feedback)[:200]}, True)

        done = threading.Event()
        fut = client.send_goal_async(cls.Goal(), feedback_callback=fb)
        fut.add_done_callback(lambda f: done.set())
        if not done.wait(timeout):
            raise RosError("goal for /%s not answered in %.0f s" % (name, timeout))
        gh = fut.result()
        if not gh.accepted:
            self.emit({"ev": "action", "name": name, "state": "rejected", "detail": ""})
            return {"accepted": False}
        self._goals[name] = gh
        self.emit({"ev": "action", "name": name, "state": "accepted", "detail": ""})

        def res(f):
            self._goals.pop(name, None)
            try:
                st = f.result().status
            except Exception as e:
                self.emit({"ev": "action", "name": name, "state": "aborted", "detail": str(e)})
                return
            state = {4: "succeeded", 5: "canceled", 6: "aborted"}.get(st, "aborted")
            self.emit({"ev": "action", "name": name, "state": state, "detail": "status %s" % st})
        gh.get_result_async().add_done_callback(res)
        return {"accepted": True}

    def cancel_action(self, name, timeout=3.0):
        gh = self._goals.get(name)
        if gh is None:
            return False
        done = threading.Event()
        fut = gh.cancel_goal_async()
        fut.add_done_callback(lambda f: done.set())
        done.wait(timeout)
        return True

    def cancel_all_actions(self):
        names = list(self._goals)
        for n in names:
            try:
                self.cancel_action(n, 2.0)
            except Exception as e:
                log("cancel", n, e)
        return names
