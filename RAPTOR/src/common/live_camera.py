"""USB camera read on its own thread, that finds the camera and survives unplugs.

Why this exists (2026-09-29, measured on the bench C922):

  * decoding one 1080p MJPEG frame takes ~22 ms of CPU. Read in the main loop,
    that is added to every frame's inference time (the demo ran at ~17 FPS).
    On its own thread it overlaps with inference instead;
  * the webcam dropped off USB and came back as /dev/video1, so a demo hard-wired
    to /dev/video0 could no longer open it. The camera is found by its USB path
    each time it is (re)opened, and a lost camera is re-opened automatically;
  * the camera was set to lower its frame rate in dim light
    (exposure_dynamic_framerate=1): 720p gave 29.7 fps instead of 41.7. It is
    switched off on open.

`read()` always returns the newest frame; stale frames are dropped, never queued,
so the picture on screen is never behind the room.

2026-10-05, Arducam B0498 (USB 3, uncompressed YUYV only - it has no MJPG):

  * fourcc "auto" picks the format by the camera's USB link. On USB 3, YUYV:
    no decode, 1080p60 measured at 60.0 fps for 18.4 ms of CPU per frame. On
    USB 2, MJPG: uncompressed 1080p does not fit (the C922 managed 5 fps);
  * the negotiated format and frame rate are kept (`fourcc_got`, `fps_got`), so
    the demo can say what it actually got rather than what it asked for;
  * an exception inside the camera thread used to end the thread silently -
    the demo then showed its last status forever, which looks like a crash. It
    is now reported and handled like a lost camera: release, back off, re-open.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path


def find_camera(preferred=None):
    """The device node of the first USB camera, or `preferred` if it exists."""
    if preferred and preferred != "auto" and os.path.exists(preferred):
        return preferred
    for pattern in ("/dev/v4l/by-id/*-video-index0", "/dev/v4l/by-path/*usb*-video-index0"):
        for link in sorted(glob.glob(pattern)):
            return os.path.realpath(link)
    nodes = sorted(glob.glob("/dev/video*"))
    return nodes[0] if nodes else None


def usb_speed_mbps(dev):
    """Link speed of the USB port a /dev/videoN sits on (480 = USB 2, 5000+ = USB 3), or None."""
    node = Path("/sys/class/video4linux") / os.path.basename(os.path.realpath(dev)) / "device"
    try:
        p = node.resolve()
        for d in (p, *p.parents):              # walk up from the interface to the USB device
            f = d / "speed"
            if f.is_file():
                return int(float(f.read_text().strip()))
    except (OSError, ValueError):
        pass
    return None


def pick_fourcc(dev, requested):
    """`requested` if given; for "auto", YUYV on a USB 3 link and MJPG otherwise."""
    if requested and requested.lower() != "auto":
        return requested
    speed = usb_speed_mbps(dev)
    return "YUYV" if speed is not None and speed >= 5000 else "MJPG"


def fourcc_str(code):
    code = int(code)
    return "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)).strip("\x00") or "?"


def set_control(dev, name, value):
    """Set one V4L2 control; False if the camera has no such control or refused it."""
    try:
        done = subprocess.run(["v4l2-ctl", "-d", dev, "-c", "{}={}".format(name, value)],
                              capture_output=True, timeout=3)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class LiveCamera:
    """See the module docstring. `focus`: None leaves the camera's autofocus on; a
    number (C922: 0 = far ... 250 = near) locks the focus there, so the focus motor
    does not run every time something new comes into view."""

    def __init__(self, device="auto", width=1920, height=1080, fourcc="auto", fps=60, focus=None):
        self.want = device
        self.width, self.height, self.fourcc, self.fps = width, height, fourcc, fps
        self.focus = focus
        self.device = None
        self.size = (width, height)
        self.fourcc_got, self.fps_got = None, None
        self.status = "opening"
        self.reconnects = 0
        self.errors = 0             # exceptions raised inside the camera thread
        self._drops = []            # monotonic times the camera fell off USB
        self._frame = None
        self._seq = 0
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)

    def start(self, timeout=10.0):
        """Start reading; wait up to `timeout` s for the first frame. False if none came."""
        self._thread.start()
        with self._cond:
            self._cond.wait_for(lambda: self._seq > 0 or self._stop.is_set(), timeout)
            return self._seq > 0

    def _open(self):
        import cv2

        dev = find_camera(self.want)
        if dev is None:
            return None
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*pick_fourcc(dev, self.fourcc)))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Keep the driver's default buffer count. With ONE buffer the camera has
        # nowhere to put the next frame while this one is decoded, and every
        # other frame is lost (measured: 15 fps instead of 30). Latency stays
        # low anyway - this thread drains the buffers as fast as they fill.
        set_control(dev, "exposure_dynamic_framerate", 0)   # keep the frame rate up in dim rooms
        if self.focus is not None:
            set_control(dev, "focus_automatic_continuous", 0)
            set_control(dev, "focus_absolute", int(self.focus))
        self.device = dev
        self.size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.fourcc_got = fourcc_str(cap.get(cv2.CAP_PROP_FOURCC))
        self.fps_got = round(cap.get(cv2.CAP_PROP_FPS), 1) or None
        return cap

    def _wait(self, seconds):
        """Sleep, but wake at once if stop() is called."""
        self._stop.wait(seconds)

    def _run(self):
        cap, fails = None, 0
        while not self._stop.is_set():
            try:
                cap, fails = self._step(cap, fails)
            except Exception:  # noqa: BLE001 - this thread must outlive any one bad read
                self.errors += 1
                print("camera thread error #{} (re-opening the camera):".format(self.errors), file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:  # noqa: BLE001
                        pass
                cap, fails = None, 0
                self.reconnects += 1
                self.status = "camera error - re-opening"
                self._wait(1.0)
        if cap is not None:
            cap.release()

    def _step(self, cap, fails):
        """One pass of the read loop. Returns the (cap, fails) to carry on with."""
        if cap is None:
            cap = self._open()
            if cap is None:
                self.status = "camera not found - plug it in (retrying)"
                self._wait(1.0)
                return None, fails
            self.status = "ok"
            fails = 0
        ok, frame = cap.read()
        if not ok or frame is None:
            fails += 1
            if fails < 15:               # ~0.5 s of nothing means the camera has gone
                self._wait(0.03)
                return cap, fails
            cap.release()
            self.reconnects += 1
            # Back off. Re-opening a camera the instant it re-appears and
            # streaming 1080p again knocked an unstable one straight back
            # off (2026-09-29: six drops in a minute, then it stopped
            # answering USB at all). Wait 2 s, doubling per recent drop.
            now = time.monotonic()
            self._drops = [t for t in self._drops if now - t < 60] + [now]
            n = len(self._drops)
            wait = min(2.0 * 2 ** (n - 1), 30.0)
            self.status = ("camera dropped off USB - reconnecting" if n == 1 else
                           "camera dropped off USB {}x in a minute - check cable/port; "
                           "waiting {:.0f} s".format(n, wait))
            self._wait(wait)
            return None, 0
        with self._cond:
            self._frame = frame
            self._seq += 1
            self._cond.notify_all()
        return cap, 0

    def read(self, last_seq=0, timeout=1.0):
        """(frame, seq) for the newest frame after `last_seq`, or (None, last_seq) on timeout."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._seq > last_seq or self._stop.is_set(), timeout):
                return None, last_seq
            return self._frame, self._seq

    def stop(self):
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        self._thread.join(timeout=3)
