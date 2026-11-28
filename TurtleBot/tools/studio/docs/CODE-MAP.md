# Studio code map

Which file to open for which job. The design behind it is in [ARCHITECTURE.md](ARCHITECTURE.md).

Studio has three parts, and each part has its own folder:

| Part | Edit here | Built into | How to rebuild |
|---|---|---|---|
| Interface (screens) | `ui/src/` | `web/v2/` | `npm run build` in `ui/` |
| Desktop app | `desktop/` | `studio.py` | `python bundle.py` |
| Robot bridge | `bridge/` | `robot_bridge.py` | `python bundle.py` |

Never edit `studio.py`, `robot_bridge.py` or `web/v2/` by hand. They are generated, and CI fails if they do not
match their source ([ADR-0008](adr/0008-small-source-modules-joined-into-single-files.md)).

## "I want to change ..."

| I want to change ... | Open |
|---|---|
| A screen's layout or wording | `ui/src/screens/<Screen>.tsx` (for example `Programs.tsx`, `Code.tsx`) or its folder |
| The sidebar or its groups | `ui/src/state/router.ts` (the `ROUTES` list) and `ui/src/components/shell/Sidebar.tsx` |
| The E-STOP button or key | `ui/src/components/shell/EStopButton.tsx`, then `desktop/forwarding.py` (`estop`), then `bridge/estop_commands.py` |
| What happens when a program runs | `desktop/programs.py` (does it move?), `desktop/forwarding.py` (`forward`), `bridge/programs_commands.py` (`h_run`) |
| Which programs count as moving, and their example arguments | `programs.json` (the catalog) |
| The New program templates | `templates/` |
| Connecting and reconnecting | `desktop/connection.py`, `desktop/bridge_process.py` |
| Finding the robot on the network | `desktop/discovery.py`, `desktop/network_parse.py` |
| Keyboard and joystick driving | `ui/src/features/teleop/`, `bridge/teleop_commands.py` (limits and arming) |
| Mapping | `ui/src/features/mapping/`, `desktop/map_api.py`, `bridge/service_commands.py`, `bridge/mapping_service.py` |
| Saved maps (list, rename, delete) | `bridge/map_library.py`, `desktop/mapping.py` (map pictures) |
| Routes | `ui/src/features/routes/`, `bridge/route_library.py` |
| The robot's front-panel menu | `ui/src/features/menu/`, `bridge/menu_service.py` |
| Wi-Fi | `ui/src/screens/wifi/`, `desktop/wifi.py`, `desktop/wifi_scripts.py`, `bridge/wifi_commands.py`, `bridge/wifi_join.py` |
| Copying a folder to the robot | `ui/src/screens/Files.tsx`, `desktop/file_sync.py`, `desktop/sync_helpers.py` |
| Settings and trusted robots | `desktop/settings.py`, `desktop/trust.py` |
| Alerts (battery low, program finished) | `desktop/alerts.py` |
| Live numbers on Home | `bridge/telemetry_commands.py` (sent), `desktop/telemetry.py` (kept), `ui/src/screens/overview/` (shown) |
| An HTTP endpoint | `desktop/http_server.py` (`make_handler`) |
| The simulated robot used by tests | `bridge/ros_fake.py`, `bridge/stack_adapters.py` (fake runners) |

## Desktop app: `desktop/`

Joined in this order into `studio.py`. The first line of each file says the same.

| Module | Job |
|---|---|
| `config.py` | Imports and constants (ports, limits, file names) |
| `helpers.py` | Small pure helpers: config folder, host checks, ssh and scp command lines, host keys, error texts |
| `network_parse.py` | Pure parsers for neighbour tables and network interfaces, and the address list to search |
| `notices.py` | Short texts and timing shown to the user: update notice, reconnect delays, hiding secrets |
| `sync_helpers.py` | Pure parts of folder sync: planning, tar streaming, the ssh config block |
| `window.py` | Studio's own window, one Studio per user, closing when the window closes |
| `wifi_scripts.py` | The script texts that save, join and remove a Wi-Fi network on the robot |
| `laptop_network.py` | The laptop's own Wi-Fi and cable: reading what it is connected to |
| `programs.py` | The program catalog and templates, and the decision whether a run moves the robot (`ProgramsMixin`) |
| `events.py` | The event bus that feeds every open window, and the one-per-second history |
| `alerts.py` | Turns status into alerts (battery low, program finished) without repeats |
| `mapping.py` | Map names, route upload checks, map pictures (`MapStore`) |
| `bridge_process.py` | The one ssh process to the robot: sends a command, waits for the reply with the same id |
| `connection.py` | Connect, disconnect, discovery, whole-network search, automatic reconnect (`ConnectionMixin`) |
| `forwarding.py` | Passes interface commands to the robot, applies driving limits, E-STOP and its fallback (`ForwardingMixin`) |
| `telemetry.py` | What Studio learns from the robot's status events, and diagnostics (`TelemetryMixin`) |
| `file_sync.py` | Copying a laptop folder to and from the robot (`FileSyncMixin`) |
| `terminals.py` | Opening a terminal or VS Code on the robot (`TerminalMixin`) |
| `settings.py` | Loading and saving settings, the app log, the settings page (`SettingsMixin`) |
| `trust.py` | The ssh key, trusted robot keys, the setup wizard (`TrustMixin`) |
| `map_api.py` | Map events, previews, map download, route upload (`MappingMixin`) |
| `updates.py` | Asking GitHub whether a newer Studio exists (`UpdatesMixin`) |
| `wifi.py` | Robot Wi-Fi, the laptop's network, the robot's hotspot (`WifiMixin`) |
| `app.py` | `class Studio`: built from all the mixins above; holds the shared state, start and shutdown |
| `discovery.py` | Searching for the robot: cable address, neighbour tables, the port-22 sweep |
| `http_server.py` | The local web server: token check, routes to `Studio` methods, live events |
| `main.py` | Command-line options and `main()` |

## Robot bridge: `bridge/`

Joined in this order into `robot_bridge.py`, which is streamed to the robot at connect time.

| Module | Job |
|---|---|
| `base.py` | Imports and constants |
| `pure_helpers.py` | Small pure functions: logging, JSON cleaning, battery flags, angle maths, nearest obstacle ahead |
| `stream_helpers.py` | Pure helpers for the scan and pose streams, driving limits, the robot log, system readings |
| `path_describe.py` | Keeps paths inside `~/robot_code`; reads a program's description and usage |
| `wifi_join.py` | Joining another Wi-Fi network safely, and holding a password in memory for a short time |
| `mapping_helpers.py` | Pure helpers for maps and routes: names, map files, the map encoding sent to the desktop |
| `ros_base.py` | The one locked writer of output, and the part of the ROS layer shared by real and fake |
| `ros_real.py` | `RosReal`: the real ROS 2 node (subscriptions, driving speed, dock and e-stop services) |
| `ros_fake.py` | `FakeRos`: the simulated robot, room and map used by demos and tests |
| `run_state.py` | The record of one started program |
| `stack_adapters.py` | Starting and stopping the mapping stack, looking for running processes (real and fake) |
| `mapping_service.py` | `MappingService`: start, save and stop mapping, one state at a time |
| `map_library.py` | `MapLibrary`: list, preview, rename and delete saved maps |
| `route_library.py` | `RouteLibrary`: list routes, set the current one, take uploads |
| `menu_service.py` | `MenuService`: read, check and save the front-panel menu file |
| `commands_basic.py` | Commands answered from memory: ping, status on and off, topics, lidar (`BasicCommandsMixin`) |
| `files_commands.py` | Reading and writing files, describing a program (`FilesMixin`) |
| `wifi_commands.py` | Wi-Fi information and joining (`WifiMixin`) |
| `programs_commands.py` | Starting, watching and stopping programs (`ProgramsMixin`) |
| `estop_commands.py` | The emergency stop and its release (`EstopMixin`) |
| `streams_commands.py` | Switching the scan, pose and map streams on and off (`StreamsMixin`) |
| `teleop_commands.py` | Manual driving: checks before driving, arming, the drive command (`TeleopMixin`) |
| `service_commands.py` | Thin commands for mapping, maps, routes, trips and the menu (`ServiceHandlersMixin`) |
| `system_commands.py` | The robot log, dock, undock, cancel (`SystemMixin`) |
| `telemetry_commands.py` | Health check and the regular status reports (`TelemetryMixin`) |
| `bridge_core.py` | `class Bridge`: built from the mixins above; shared state, sending events, choosing the handler |
| `main.py` | Startup: real or fake mode, the hello message, the command loop |

A command named `x` is handled by the method `h_x`. To find a command, search the bridge folder for `def h_x`.

## Interface: `ui/src/`

| Folder | Job |
|---|---|
| `screens/` | One file or folder per screen in the sidebar |
| `features/` | Larger features with their own model, store and parts: `mapping/`, `routes/`, `menu/`, `teleop/` |
| `components/shell/` | Sidebar, top bar, E-STOP button, banners, events drawer |
| `components/ui/` | Shared building blocks: buttons, panels, fields, badges |
| `state/` | App state (zustand stores) and the actions that change it; `router.ts` lists the screens |
| `api/` | Every call to the desktop app and the live event stream; screens never call `fetch` directly |
| `lib/` | Small shared helpers |

Pure logic lives in `model.ts` files next to the feature, so it is tested without a browser.

## Tests

| Folder or file | What it checks |
|---|---|
| `tests/offline/test_studio_*.py` | Desktop and bridge, against the simulated robot ([TESTING.md](TESTING.md)) |
| `tests/offline/test_studio_e2e*.py` | The real interface in a browser, against the simulated robot |
| `ui/src/**/*.test.ts(x)` | Interface units (vitest) |
| `tests/offline/check_split_equivalence.py` | Proves a re-split of `studio.py` or `robot_bridge.py` moved code without changing it |
