#!/usr/bin/env python3
"""RAPTOR dashboard server - runs on the LAPTOP, standard library only.

The Jetson's demo sends what it sees to this server; a browser shows it live.

    python server.py                  # http://127.0.0.1:8765
    python server.py --port 9000

How the data gets here: the server listens on 127.0.0.1 only, and the Jetson
reaches it through an SSH reverse tunnel (run_dashboard.ps1 starts both). That
needs no Windows-firewall rule and nothing is exposed on the network: the only
way in is the SSH key the laptop already uses for the board.

Endpoints
  POST /api/status        JSON  the Jetson's health, ~2 Hz (fps, people, timings, camera, power)
  POST /api/person        JSON  a new person was confirmed (id, posture, confidence, time)
  PUT  /api/photo/<id>/<kind>   JPEG bytes; kind = crop | frame; stored on this laptop
  POST /api/frame         JPEG  the live preview, ~3 Hz
  GET  /                  the dashboard page
  GET  /frame.jpg         the latest live preview
  GET  /api/state         everything now, as JSON
  GET  /api/stream        server-sent events: every change, pushed as it happens
  GET  /photos/<file>     a stored photo
Everything is also written under ../../dashboard-data/ (git-ignored): events.jsonl
and the photos, so a session can be reviewed after the server is closed.
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent.parent / "dashboard-data"
OFFLINE_AFTER_S = 5.0
MAX_BODY = 8 * 1024 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class State:
    """Everything the page shows. One lock; handlers are short."""

    def __init__(self, session_dir: Path):
        self.lock = threading.Lock()
        self.session = session_dir
        self.photos = session_dir / "photos"
        self.photos.mkdir(parents=True, exist_ok=True)
        self.log = (session_dir / "events.jsonl").open("a", buffering=1, encoding="utf-8")
        self.status: dict = {}
        self.status_at = 0.0
        self.people: dict[str, dict] = {}        # person key -> record
        self.events: deque = deque(maxlen=300)
        self.history: deque = deque(maxlen=240)  # (t, fps, people) for the charts
        self.frame: bytes = b""
        self.frame_at = 0.0
        self.clients: list[queue.Queue] = []
        self.started = time.time()
        self.seq = 0

    def broadcast(self, kind: str, data: dict):
        msg = json.dumps({"kind": kind, "data": data})
        dead = []
        for q in self.clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)          # a stuck browser is dropped, never waited on
        for q in dead:
            self.clients.remove(q)

    def add_event(self, level: str, text: str, **extra):
        ev = {"t": time.time(), "level": level, "text": text, **extra}
        self.events.appendleft(ev)
        self.log.write(json.dumps(ev) + "\n")
        self.broadcast("event", ev)

    def snapshot(self) -> dict:
        now = time.time()
        return {
            "now": now,
            "started": self.started,
            "jetson_online": bool(self.status_at) and now - self.status_at < OFFLINE_AFTER_S,
            "status_age": (now - self.status_at) if self.status_at else None,
            "status": self.status,
            "people": sorted(self.people.values(), key=lambda p: -p["first_seen"]),
            "total_people": len(self.people),
            "events": list(self.events)[:100],
            "history": list(self.history),
            "frame_age": (now - self.frame_at) if self.frame_at else None,
            "session": self.session.name,
        }


STATE: State


class Handler(BaseHTTPRequestHandler):
    server_version = "RaptorDash/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):          # quiet; the dashboard has its own event log
        pass

    # ---------------------------------------------------------------- helpers
    def _send(self, code, body=b"", ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("body too large")
        return self.rfile.read(n) if n else b""

    # -------------------------------------------------------------------- GET
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/frame.jpg":
            if not STATE.frame:
                return self._send(404, b"no frame yet", "text/plain")
            return self._send(200, STATE.frame, "image/jpeg")
        if path == "/api/state":
            with STATE.lock:
                return self._send(200, STATE.snapshot())
        if path == "/api/stream":
            return self._stream()
        if path.startswith("/photos/"):
            name = path[len("/photos/"):]
            f = STATE.photos / name
            if SAFE_ID.match(name) and f.is_file():
                return self._send(200, f.read_bytes(), "image/jpeg")
            return self._send(404, b"not found", "text/plain")
        if path == "/healthz":
            return self._send(200, b"ok", "text/plain")
        self._send(404, b"not found", "text/plain")

    def _stream(self):
        q: queue.Queue = queue.Queue(maxsize=200)
        with STATE.lock:
            STATE.clients.append(q)
            first = json.dumps({"kind": "state", "data": STATE.snapshot()})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(("data: " + first + "\n\n").encode())
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=2.0)
                    self.wfile.write(("data: " + msg + "\n\n").encode())
                except queue.Empty:
                    with STATE.lock:        # idle tick: lets the page notice the Jetson going quiet
                        tick = json.dumps({"kind": "tick", "data": STATE.snapshot()})
                    self.wfile.write(("data: " + tick + "\n\n").encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with STATE.lock:
                if q in STATE.clients:
                    STATE.clients.remove(q)

    # ------------------------------------------------------------- POST / PUT
    def do_POST(self):
        self._ingest()

    def do_PUT(self):
        self._ingest()

    def _ingest(self):
        path = self.path.split("?")[0]
        try:
            body = self._body()
            if path == "/api/frame":
                STATE.frame, STATE.frame_at = body, time.time()
                return self._send(204)
            if path.startswith("/api/photo/"):
                _, _, _, pid, kind = path.split("/")
                if kind not in ("crop", "frame") or not SAFE_ID.match(pid):
                    return self._send(400, {"error": "bad photo path"})
                (STATE.photos / "{}_{}.jpg".format(pid, kind)).write_bytes(body)
                with STATE.lock:
                    if pid in STATE.people:
                        STATE.people[pid][kind + "_url"] = "/photos/{}_{}.jpg".format(pid, kind)
                        STATE.broadcast("person", STATE.people[pid])
                return self._send(204)
            data = json.loads(body or b"{}")
            with STATE.lock:
                if path == "/api/status":
                    self._status(data)
                elif path == "/api/person":
                    self._person(data)
                else:
                    return self._send(404, {"error": "unknown endpoint"})
            return self._send(204)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return self._send(400, {"error": str(e)[:120]})

    def _status(self, d: dict):
        was_online = bool(STATE.status_at) and time.time() - STATE.status_at < OFFLINE_AFTER_S
        first = not STATE.status_at
        STATE.status, STATE.status_at = d, time.time()
        STATE.history.append([round(STATE.status_at, 2), d.get("fps"), d.get("people")])
        if first or not was_online:
            STATE.add_event("ok", "Jetson connected" + (": " + d["camera_mode"] if d.get("camera_mode") else ""))
        STATE.broadcast("status", d | {"jetson_online": True})

    def _person(self, d: dict):
        key = str(d["key"])
        if not SAFE_ID.match(key):
            raise ValueError("bad person key")
        rec = STATE.people.get(key)
        if rec is None:
            rec = {"key": key, "id": d.get("id"), "first_seen": d.get("t", time.time()),
                   "posture": d.get("posture"), "confidence": d.get("confidence"),
                   "vlm": d.get("vlm"), "updates": 0}
            STATE.people[key] = rec
            STATE.add_event("info", "New person #{} ({}%)".format(d.get("id"), int(100 * (d.get("confidence") or 0))),
                            person=key)
        else:
            before = rec.get("posture")
            for k in ("posture", "vlm", "confidence"):
                if d.get(k) is not None:
                    rec[k] = d[k]
            rec["updates"] += 1
            if str(d.get("posture")).lower() == "lying" and str(before).lower() != "lying":
                STATE.add_event("alarm", "Person #{} is lying down".format(rec["id"]), person=key)
        rec["last_seen"] = time.time()
        STATE.broadcast("person", rec)


def main():
    global STATE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="leave as is unless you know why (see the docstring)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", default=str(DATA))
    args = ap.parse_args()
    session = Path(args.data) / datetime.now().strftime("session_%Y%m%d-%H%M%S")
    STATE = State(session)
    STATE.add_event("info", "Dashboard server started")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    print("RAPTOR dashboard: http://{}:{}   (data: {})".format(args.host, args.port, session))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
