"""The source of robot_bridge.py, in small modules.

robot_bridge.py runs on the robot and is streamed over ssh as ONE file, so it is built by joining these
modules in the order of MODULES below. Edit here, then run python bundle.py (from tools/studio) to rebuild it.
Never edit robot_bridge.py by hand. See docs/adr/0008-small-source-modules-joined-into-single-files.md.
"""
MODULES = [
    'base.py',
    'pure_helpers.py',
    'stream_helpers.py',
    'path_describe.py',
    'wifi_join.py',
    'mapping_helpers.py',
    'ros_base.py',
    'ros_real.py',
    'ros_fake.py',
    'run_state.py',
    'stack_adapters.py',
    'mapping_service.py',
    'map_library.py',
    'route_library.py',
    'menu_service.py',
    'commands_basic.py',
    'files_commands.py',
    'wifi_commands.py',
    'programs_commands.py',
    'estop_commands.py',
    'streams_commands.py',
    'teleop_commands.py',
    'service_commands.py',
    'system_commands.py',
    'telemetry_commands.py',
    'bridge_core.py',
    'main.py',
]
