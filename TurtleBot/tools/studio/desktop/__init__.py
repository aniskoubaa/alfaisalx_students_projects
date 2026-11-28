"""Source of studio.py, the desktop backend of TurtleBot Studio, split into small modules.

Edit the modules here, then run `python bundle.py` (one folder up) to rebuild studio.py. Never edit studio.py by hand.
Each module has one job. The big class Studio is built from one mixin class per feature (modules programs, connection,
forwarding, telemetry, file_sync, terminals, settings, trust, map_api, updates, wifi) and is finished in app.py.
The `from .x import *  # bundle: skip` lines only help readers and editors; the bundler leaves them out.
MODULES is the join order, the same order as the original single file.
"""
MODULES = [
    'config.py',
    'helpers.py',
    'network_parse.py',
    'notices.py',
    'sync_helpers.py',
    'window.py',
    'wifi_scripts.py',
    'laptop_network.py',
    'programs.py',
    'events.py',
    'alerts.py',
    'mapping.py',
    'bridge_process.py',
    'connection.py',
    'forwarding.py',
    'telemetry.py',
    'file_sync.py',
    'terminals.py',
    'settings.py',
    'trust.py',
    'map_api.py',
    'updates.py',
    'wifi.py',
    'app.py',
    'discovery.py',
    'http_server.py',
    'main.py',
]
