# TurtleBot Studio 2.1: mapping, map library and routes (design)

Status: design for Studio 2.1, written 2026-11-12. It is the contract between the three layers (robot bridge, desktop
backend, interface) and the tests. Real-robot behaviour of everything here is **NOT VERIFIED** until it is listed as
tested in the README.

## 1. Goal and scope

Map any place from inside Studio, without logging in to the robot and running scripts by hand, then manage the saved
maps and the delivery route folders.

In scope:

- **Maps screen**: start and stop mapping with a visible state, the live occupancy grid with the robot pose and the
  lidar overlay, driving with the existing teleop panel, save the map under a name (with overwrite protection), a map
  library (list, preview, rename, download to the laptop, delete with a danger confirmation).
- **Routes screen**: list route folders, show where `current` points, change it with a confirmation, upload a route
  folder made by `delivery/tools/plan_route.py`, read-only trip status from the menu log.
- **Robot menu page** (only if the menu file format is fixed in time; see the hand-over).

Out of scope: starting or cancelling delivery trips from Studio, navigation (Nav2) goals, editing maps, planning
routes inside Studio.

Mapping is a general Studio feature. It reuses the robot scripts of the delivery package because they are the tested
procedure on this robot (`start_stack.sh map`, `save_map.sh`, `stop_stack.sh`, SLAM parameters
`delivery/config/slam_delivery.yaml`), but nothing on the Maps screen depends on the delivery mission.

## 2. Layers

```
 Interface (ui/, React + TypeScript)                       screens/maps, screens/routes  (composition only)
   features/mapping  features/routes                        model.ts (pure), store, components, typed api calls
        |  HTTP JSON + Server-Sent Events (unchanged security: token, Host and Origin checks)
 Desktop backend (studio.py)
   pure helpers: map payload decode, cells -> grey, PNG encoder, upload validation
   MapStore: latest live map as PNG + last `mapping` event (replayed to pages opened later)
   endpoints: thin; bridge commands go through POST /api/bridge as before
        |  one ssh connection, JSON lines (unchanged)
 Robot bridge (robot_bridge.py, ONE file because it is streamed to the robot at connect time)
   pure helpers: names, map YAML, PGM read/downsample, grid encode, pose composition, route checks, link read/write
   adapters:  StackRunner  (real: runs the delivery scripts with bash; fake: timers, no processes)
              ProcessProbe (real: pgrep -f; fake: the fake runner's own state)
              MapSource    (real: /map and /pose subscriptions on the EXISTING node; fake: FakeMapGrid)
   services:  MappingService (state machine), MapLibrary (maps folder), RouteLibrary (routes folder, menu log)
   handlers:  h_* methods, thin: check arguments, call a service, return its dict
```

Rules: handlers hold no logic beyond argument checks; services do not know about JSON lines or HTTP; adapters are the
only code that touches processes, ROS or the robot's file system layout; every pure helper has a unit test.

TB-25 (one ROS participant): the bridge keeps its single node. `/map` (reliable, transient local, depth 1, raw bytes)
and `/pose` (`geometry_msgs/PoseWithCovarianceStamped`, published by slam_toolbox) are subscriptions created on the
existing node the first time `map_on` arrives. Starting and saving a map run the delivery scripts, which start their own
ROS processes (the SLAM launch, and one short `ros2 service call` per save step): that is the same as the manual
procedure, and driving is blocked while it happens (section 6).

## 3. Robot paths

| What | Path on the robot | Fake robot |
|---|---|---|
| Delivery scripts | `~/robot_code/delivery/robot/{start_stack,save_map,stop_stack}.sh` (deployed by `delivery/tools/deploy.py`) | not used |
| Maps | `~/robot_code/maps/<name>.{pgm,yaml,posegraph,data}` | `<fake home>/robot_code/maps/` |
| Routes | `~/robot_code/routes/<name>/` and the link `current -> <name>` | `<fake home>/robot_code/routes/`, seeded with `home` and `route1`; when the OS cannot make a symbolic link the fake stores the target in `routes/.current_fake` |
| Menu log | `~/robot_code/logs/delivery/menu.log` | seeded with a few sample lines |

## 4. Bridge commands (robot side)

All replies are `{ok:true, ...}` or `{ok:false, error, ...}` as before. Long operations reply at once with the new state
and report the outcome in a `mapping` event.

### Mapping

| Command | Reply | Notes |
|---|---|---|
| `mapping_status` | `MappingInfo` (below) | |
| `mapping_start {keep_camera?:bool}` | `MappingInfo` with `state:"starting"` | Refused unless `idle`; refused if a navigation stack runs (`other_stack`) or the scripts are missing (`scripts_missing`). Disarms driving first |
| `mapping_save {name, overwrite?:bool}` | `MappingInfo` with `state:"saving"` | Only in `mapping`. Bad name: `ok:false, error`. Existing map without `overwrite:true`: `ok:false, exists:true`. Runs `save_map.sh <maps>/<name> [--force]` |
| `mapping_stop` | `MappingInfo` with `state:"stopping"` | Allowed in `mapping` and `error`. Runs `stop_stack.sh` |
| `mapping_reset` | `MappingInfo` | Leaves `error`: the state is derived again from the processes (`idle` or `mapping`) |

`MappingInfo = {state, since, last_error, last_saved, unsaved, scripts_ok, other_stack, maps_dir}`

- `state`: `idle | starting | mapping | saving | stopping | error`
- `since`: wall-clock seconds when the state was entered
- `last_error`: text or null (kept until the next successful operation or `mapping_reset`)
- `last_saved`: `{name, t}` or null
- `unsaved`: true when mapping has run since the last successful save (the stop confirmation uses it)
- `other_stack`: name of a running navigation launch or null

Event `{ev:"mapping", ...MappingInfo, result?:{op:"start"|"save"|"stop", ok, name?, error?, output_tail?}}` on every
change. `output_tail` is the last 20 lines of the script output.

State machine:

```
 idle --start--> starting --script ok + SLAM process seen--> mapping
                          --script failed------------------> error
 mapping --save--> saving --ok--> mapping (last_saved set, unsaved false)
                          --failed--> mapping (last_error set, result.ok false)
 mapping|error --stop--> stopping --SLAM gone--> idle
                                  --still running or script failed--> error
 error --reset--> idle or mapping (from the processes)
 idle    --SLAM seen by the 2 s probe (started outside Studio)--> mapping
 mapping --SLAM gone without a stop (crash or stopped outside)--> error
```

### Live map stream

| Command | Effect |
|---|---|
| `map_on {hz 0.2-2 (0.5), max_cells 10000-4000000 (1000000)}` | `map` events while on |
| `map_off` | stops them |

Event `{ev:"map", seq, t, width, height, resolution, origin:{x,y,yaw}, stride, encoding:"cells", data}`: sent only when
a new map arrived since the last event. `data` is zlib then base64 of one byte per cell, row 0 = bottom row (ROS
order): 0..100 occupancy, 255 unknown. When the grid has more than `max_cells` cells it is sampled every `stride` cells
in both directions (nearest sample; `width`, `height` and `resolution` are the sampled values).

While the map stream is on, `pose` events gain `map:{x, y, yaw, source}`: `source:"slam"` is the slam_toolbox pose
moved forward by the odometry since then; `source:"odom"` means no map pose is known yet and the odometry pose is used.

### Map library

| Command | Reply |
|---|---|
| `maps_list` | `{maps:[MapEntry], dir}` newest first |
| `map_preview {name, max_px 64-1024 (512)}` | `{width, height, stride, encoding:"gray", data}`: the PGM pixels (zlib + base64, row 0 = top), sampled |
| `map_rename {name, new_name}` | `{name:new_name}`; renames every file of the map and rewrites the `image:` line of the YAML. Refuses an existing target |
| `map_delete {name, confirm:true}` | `{deleted:[file names]}`; refused without `confirm:true` and while that map is being saved |

`MapEntry = {name, width, height, resolution, origin:[x,y,yaw], mtime, bytes, files:{pgm, yaml, posegraph, data}}`
(each file: size in bytes or null). A map is a `<name>.yaml` in the maps folder. Names: `^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$`.

### Routes (backlog item 3)

| Command | Reply |
|---|---|
| `routes_list` | `{routes:[{name, valid, missing:[file], mtime, waypoints?}], current, current_ok, dir}` |
| `route_set_current {name, confirm:true}` | `{current}`; refused without confirm, for an invalid folder, and while a trip or the navigation stack runs. Real robot: a new link is made beside the old one and renamed over it (same effect as `ln -sfn`, atomic) |
| `trip_status {lines 1-200 (40)}` | `{menu_running, mission_running, stack_running, log_path, lines:[text]}` read-only |

A route folder is valid when it has `route.yaml`, `map.yaml`, `keepout_mask.yaml` and `speed_mask.yaml`.

## 5. Desktop endpoints (studio.py)

| Endpoint | Content |
|---|---|
| `GET /api/mapping` | last `MappingInfo` seen (or `{state:"unknown"}`) |
| `GET /api/map/live.png` | latest live map as an 8-bit grey PNG (free 254, occupied 0, unknown 205, in between scaled); header `X-Map-Meta` with the JSON metadata; 404 when none |
| `GET /api/maps/preview.png?name=&max=` | the saved map's preview as PNG (asks the bridge for `map_preview`) |
| `GET /api/maps/download?name=` | a zip of the map's files (`Content-Disposition: attachment`), fetched with the existing tar-over-ssh download |
| `POST /api/routes/upload {name, files:[{path, data_b64}]}` | uploads a planned route folder (item 3). Body limit 32 MB on this path only. Flat folder only, the four files above required, the name must be new |

`map` events from the bridge are not passed to the browser with their data: the desktop decodes them into the PNG and
publishes `{ev:"map", seq, t, width, height, resolution, origin, stride}` without `data`; the page then fetches
`/api/map/live.png`. `mapping` events are passed on unchanged and remembered.

## 6. Safety rules

1. Nothing in the mapping feature moves the wheels. Studio never undocks or docks by itself. Driving while mapping is the
   existing teleop with every 2.0 rule (arm confirmation, watchdog, limits, idle disarm, automatic disarm).
2. Driving is disarmed when start, save or stop begins, and arming is refused while the state is `starting`, `saving` or
   `stopping` (new ROS processes can stall the base for up to about 12 s, TB-25).
3. Leaving the Maps screen disarms, as leaving Live does.
4. Saving never overwrites without `overwrite:true`, which the interface sends only after a second confirmation.
   Delete needs `confirm:true` and a danger dialog. Rename never overwrites.
5. Every name is checked against the pattern; every path is joined and checked to stay inside the maps or routes folder.
6. Stopping with unsaved mapping asks first ("This map is not saved. Stop and lose it?").
7. Changing `current` is refused while a trip or the navigation stack runs, and needs a confirmation that names the old
   and the new route.
8. Upload refuses existing names, nested paths, missing files and bodies over 32 MB.
9. One stack at a time: start is refused while a navigation launch runs (the script refuses too).

## 7. Fake robot (`--fake`)

- `FakeStackRunner`: `starting` 1.5 s, `saving` 1 s, `stopping` 1 s (multiplied by `STUDIO_FAKE_MAP_SCALE`, default 1,
  so tests can speed it up). No processes.
- `FakeMapGrid`: a 0.05 m grid over the fake room (`FAKE_ROOM` plus 1 m margin). Every 0.5 s while mapping it ray-casts
  from the fake pose with the same geometry as the fake lidar (`fake_room_ranges`), marks free cells along each beam and
  the hit cell occupied. The usable range grows from 1 m to 12 m over the first 10 s, so the map visibly grows even
  without driving; driving reveals the area behind the box.
- Saving writes a real P5 PGM (254 free, 0 occupied, 205 unknown), a map_server YAML and small placeholder `.posegraph`
  and `.data` files, so the library works on real files.
- Routes: seeded `home` (valid) and `route1` (valid) folders and `current -> home`; the menu log has sample lines.

## 8. Interface

- `ui/src/api/types.ts`: the types above (`MappingInfo`, `MapEvent`, `MapEntry`, routes), added to `BridgeArgs` and
  `BridgeAnswers`.
- `ui/src/features/mapping/`: `model.ts` (pure: state labels and colours, which buttons each state allows, name check
  mirroring the bridge, world to pixel transform, map metadata parsing), a small store fed by `mapping`, `map` and
  `pose` events, `MapCanvas` (grid image, robot, lidar overlay, zoom and follow), `MappingControls`, `SaveMapDialog`,
  `MapLibrary`.
- `ui/src/screens/maps/Maps.tsx`: composition with the existing `DrivePanel`; sidebar entry **Maps** after Live.
- `ui/src/features/routes/` and `ui/src/screens/routes/Routes.tsx` (item 3).
- Colours and words follow 2.0: red only for E-STOP and destructive actions, every state written in words.

## 9. Tests

| Layer | File | What |
|---|---|---|
| Robot pure helpers and services | `tests/offline/test_studio_mapping.py` | names, YAML, PGM, grid encode, pose composition, state machine with a scripted runner (all transitions, refusals, outside start, crash), library on a temp folder (list, rename, delete, preview, path escape), fake bridge as a subprocess (start, growing map events, save, list, rename, delete) |
| Desktop | same file | PNG encoder (decodes back), `map` event to PNG, `/api/map/live.png`, `/api/maps/preview.png`, `/api/maps/download`, `/api/mapping` |
| Routes | `tests/offline/test_studio_routes.py` | list, current, set current refusals, upload checks, trip status |
| Interface | vitest next to the code | model functions, store reducers, components (state words, button rules, dialogs) |
| End to end | `tests/offline/test_studio_e2e_maps.py` | Playwright against `studio.py --fake`: Maps (start, grid appears and grows, save, overwrite prompt, library rename and delete, stop with unsaved prompt) and Routes |
