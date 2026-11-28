#!/usr/bin/env python3
"""TurtleBot Studio - desktop backend (ROADMAP TB-27).

Starts a small web server on 127.0.0.1 (random per-launch token), opens the browser UI in web/, and talks to
the lab TurtleBot 4 through ONE long-lived ssh process that streams robot_bridge.py to the robot at connect
time (nothing is installed on the robot). Python >= 3.10, standard library only, Windows / macOS / Linux.

Usage:
    python studio.py [--port 8765] [--no-browser] [--host-override ADDR] [--fake]

The app never stores, asks for, logs or sends a password. Password login happens only in a system terminal
that ssh itself opened (setup_key). Every ssh call checks the robot against a pinned host key.
See README.md for the architecture and the security model.
"""
import argparse
import base64
import collections
import concurrent.futures
import hashlib
import hmac
import http.server
import io
import ipaddress
import json
import os
import platform
import queue
import re
import secrets
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import zlib
import http.client

sys.dont_write_bytecode = True
VERSION = '2.2.1'
FROZEN = bool(getattr(sys, 'frozen', False))  # PyInstaller one-file build
HERE = getattr(sys, '_MEIPASS', None) if FROZEN else None
HERE = HERE or os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, 'web')

PIN_ALIAS = 'turtlebot4-lab'
LAB_HOST_KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINezwwah6HhR6o0ONkI77+B+XmFckK7JhQHI1Fn1nyBb'
PINNED_HOST_KEY = LAB_HOST_KEY  # old name, kept for importers
ROBOT_USER = 'ubuntu'
DEFAULT_SETTINGS = {'robot_hostname': 'turtlebot4', 'robot_user': ROBOT_USER, 'hotspot_ssid': 'Turtlebot4',
                    'hotspot_addr': '10.42.0.1', 'cable_addr': '192.168.185.3'}
LEGACY_TRUST_LABEL = 'Imported from settings'
WIFI_SECRET_TTL = 180   # s the bridge keeps a Wi-Fi password in memory
WIFI_JOIN_TIMEOUT = 45  # s nmcli may take to join
DNS_LABEL_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')
USER_RE = re.compile(r'^[a-z_][a-z0-9_-]{0,31}$')
NONCE_RE = re.compile(r'^[0-9a-f]{32}$')
DEFAULT_REMOTE_DIR = '~/robot_code'
BOOT = ("source /etc/turtlebot4/setup.bash >/dev/null 2>&1; exec python3 -u -c "
        "\"import sys;b=sys.stdin.buffer;n=int(b.readline());exec(compile(b.read(n).decode(),'robot_bridge','exec'))\"")
MOTION_FILES = ['drive_test.py', 'motion_shapes.py', 'motion_test.sh', 'more_shapes.py', 'wall_approach.py',
                'keep_distance.py', 'campaign.sh']
# '[m]' trick: pkill -f must not match the shell that carries this very command line.
MOTION_PKILL_REGEX = '|'.join('[%s]%s' % (n[0], re.escape(n[1:])) for n in MOTION_FILES)
PI_MAC_PREFIXES = ('D8:3A:DD', 'DC:A6:32', 'E4:5F:01', '28:CD:C1', 'B8:27:EB')
SYNC_SKIP_DIRS = ('__pycache__', '.git', 'logs')
SYNC_MAX_BYTES = 20 * 1024 * 1024
MARK_BEGIN = '# >>> TurtleBot Studio >>>'
MARK_END = '# <<< TurtleBot Studio <<<'
HOST_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:%\-]{0,200}$')
KEY_LINE_RE = re.compile(r'^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/=]{20,}$')
PUB_LINE_RE = re.compile(r'^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/=]{20,}( [A-Za-z0-9._@\-]+)?$')
IS_WIN = os.name == 'nt'
VERSION_RE = re.compile(r'^\d+(\.\d+){0,3}$')
UPDATE_PAGE_PREFIX = 'https://github.com/aniskoubaa/alfaisalx_students_projects/'
DEFAULT_UPDATE_PAGE = UPDATE_PAGE_PREFIX + 'blob/main/TurtleBot/tools/studio/INSTALL.md'
DEFAULT_UPDATE_URL = ('https://raw.githubusercontent.com/aniskoubaa/alfaisalx_students_projects/main/'
                      'TurtleBot/tools/studio/version.json')
UPDATE_EVERY = 24 * 3600        # s between automatic update checks
RECONNECT_DELAYS = (2, 4, 8, 15, 30)   # s before attempt 1, 2, ...; the last one repeats
RECONNECT_GIVE_UP = 600                # s after which automatic reconnecting stops
DEEP_MAX_TARGETS = 1024         # addresses the "Search the whole network" sweep may probe
DEEP_DEADLINE = 12.0            # s for the whole port-22 sweep
DEEP_CONNECT_TIMEOUT = 0.4      # s per TCP connect
DEEP_WORKERS = 64
DEEP_KEYSCAN_MAX = 24           # hosts whose identity is checked with ssh-keyscan
DEEP_KEYSCAN_PARALLEL = 8
CLOSE_GRACE = 45.0              # s without any open Studio page before the built app stops itself
WINDOW_MODES = ('app', 'browser')
DEFAULT_WINDOW_MODE = 'app'
UI_CHOICES = ('v2', 'classic')  # 2.0: which interface GET / serves; 'classic' is the 1.3 page (always also at /classic/)
TELEOP_MAX_LINEAR = 0.30        # m/s, same hard caps as robot_bridge.py (the bridge enforces them; Studio mirrors them)
TELEOP_MAX_ANGULAR = 1.20       # rad/s
TELEOP_MIN_LINEAR = 0.02
TELEOP_MIN_ANGULAR = 0.10
TELEOP_DEFAULT_LINEAR = 0.15
TELEOP_DEFAULT_ANGULAR = 0.60
HISTORY_KEEP_S = 1800           # s of 1 Hz metrics kept in memory
HISTORY_SERIES = ('battery_pct', 'voltage', 'current_a', 'speed', 'odom_hz', 'scan_hz', 'cpu_pct', 'temp_c', 'wifi_dbm')
ALERT_DEDUP_S = 60.0            # the same alert code is raised at most once per this many seconds
ALERT_EDGE_DEDUP_S = 2.0        # state changes (e-stop, dock, connection, programs, driving) only drop exact repeats
ALERT_EDGE_CODES = frozenset({'estop_on', 'estop_off', 'docked', 'undocked', 'teleop_armed', 'teleop_disarmed',
                              'conn_connected', 'conn_lost', 'conn_restored', 'conn_disconnected', 'program_started',
                              'program_exited', 'program_failed'})
# Program alerts name the program, so two different programs are two events: these codes are de-duplicated by code
# AND text (only an exact repeat inside the window is dropped). Found 2026-11-28 on a fast Linux runner, where
# "drive_test.py was stopped." came 1.8 s after "hello.py finished." and was lost.
ALERT_PER_TEXT_CODES = frozenset({'program_started', 'program_exited', 'program_failed'})
ALERT_SEVERITIES = ('info', 'warn', 'critical')
EVENTS_MAX_BYTES = 1_000_000    # events.jsonl rotates to events.jsonl.old at this size
