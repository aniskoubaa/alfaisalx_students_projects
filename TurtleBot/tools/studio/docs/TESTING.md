# Testing TurtleBot Studio

This page describes how Studio is tested, how to run every test, how to measure coverage, what the measured numbers were, and what is deliberately not covered. It is for developers. The numbers are dated; run the commands again before you quote them.

Status of the whole page: everything here ran offline, on a Windows computer, without the robot. The real-robot checklist at the end says what has and has not been run on the robot.

## Test pyramid

From the cheapest and most numerous layer at the bottom to the most expensive and rarest at the top. A defect should be caught in the lowest layer that can show it.

| Layer | What runs | What it proves | What it cannot prove |
|---|---|---|---|
| 1. Pure unit | Functions with no files, no processes and no network: names, YAML text, PGM and PNG bytes, grid encoding, route and menu helpers, ssh argument building, TypeScript model functions | The rules and the arithmetic | That the pieces fit together |
| 2. Service with fakes | Python services (`MappingService`, `MapLibrary`, `RouteLibrary`, `MenuService`, `Bridge` handlers) on a temporary folder, with a scripted runner, probe and checker; the `Studio` object with a stand-in bridge; vitest stores and components with a mocked client | Every state transition and every refusal, and what is left on disk or on screen after a failure | Real processes, real timing |
| 3. Bridge subprocess | `robot_bridge.py --fake` started as a child process and driven through stdin and stdout, as ssh would | The JSON line protocol, streams, the fake robot, start up | The real ROS stack |
| 4. HTTP against `studio.py --fake` | The real `studio.py` with the real fake bridge on a free port, called with HTTP | Endpoints, token and origin checks, the live map PNG, uploads and downloads, settings, events | A browser, a real robot |
| 5. Browser end to end | Playwright drives the real page against `studio.py --fake` | The screens work as a person uses them (buttons enabled only when allowed, dialogs, the Maps, Routes and Robot menu screens, an accessibility scan) | Real robot behaviour |
| 6. Real robot | A person with the robot, following the checklist below | Behaviour that only the robot has: ROS, the base, the lidar, ssh, the front-panel menu | Nothing is offline here: it is the only layer that counts for those claims |

The layers 1 to 5 never connect to the robot. Layer 6 is manual.

## The test files

Python test files are in `TurtleBot/tests/offline/`. Each prints `PASS` or `FAIL` for every check and exits with the number of failures (`test_studio_bridge.py` exits 1 on any failure). Run each from the repository root with `PYTHONDONTWRITEBYTECODE=1 python TurtleBot/tests/offline/<file>`.

| File | Layers | What it covers |
|---|---|---|
| `test_studio_bridge.py` | 1, 3 | The robot bridge as a subprocess in fake mode, its pure helpers, and the boot path that streams the file over ssh (with `STUDIO_BRIDGE_FAKE=1`) |
| `test_studio_desktop.py` | 1, 2, 4 | `studio.py` with a stub bridge: ssh and scp argument building, IPv6 scope handling, neighbour table parsers, ssh config insertion, error mapping, sync planning |
| `test_studio_setup.py` | 1, 4 | Settings, the first-run wizard backend, join-any-Wi-Fi, the frozen-app hooks; shell script syntax checks skip when bash is missing |
| `test_studio_upgrades.py` | 1, 4 | Network search, automatic reconnect, copy diagnostics (redaction), update notice, unchanged-file save |
| `test_studio_window.py` | 1, 4 | App window command per system, single instance, exit when the window closes, `version.json`, installer script, workflow and spec |
| `test_studio_templates.py` | 1, 2 | The program templates and `programs.json` run against the simulated robot in `sim.py` (each run is a child process) |
| `test_studio_v2_backend.py` | 1, 2, 3, 4 | Scan and pose streams, manual driving with its watchdog, clamps and refusals, the journal, history, alerts, events, serving the 2.0 and classic interfaces |
| `test_studio_mapping.py` | 1, 2, 3, 4 | Mapping: names, YAML, PGM, grid encode, pose composition, the state machine with a scripted runner, the map library, the fake bridge as a subprocess, and the desktop endpoints for the map picture |
| `test_studio_mapping_desktop.py` | 1, 2 | PNG encoder, `map` event to PNG, `MapStore`, `/api/map/live.png`, preview, download, `/api/mapping` |
| `test_studio_routes.py` | 2, 3, 4 | Routes: list, current, refusals, upload checks, trip status |
| `test_studio_routes_unit.py` | 1, 2 | Pure route helpers and `RouteLibrary` with a scripted probe |
| `test_studio_menu.py` | 3 | Menu commands against the real checker (`delivery/menu_config.py`, needs PyYAML, else a SKIP line) |
| `test_studio_menu_unit.py` | 1, 2 | Pure menu helpers, `MenuService` and `MenuChecker` with a scripted checker |
| `test_studio_gaps.py` | 1, 2 | Failure scenarios found by coverage (see the next section): the current-route link, upload finish and clean up, a map rename that fails halfway, menu save and checker failures, route upload validation and the failed-upload paths of `Studio.route_upload`, the map zip and preview errors, why manual driving is refused, writing files on the robot, the emergency stop escalation, which programs count as moving |
| `test_studio_e2e.py` | 5 | Playwright: the 2.0 interface end to end (wizard, connect, Programs, Code, Files, Live, driving, Charts, Events, Logs, palette, theme, phone width, axe scan) |
| `test_studio_e2e_maps.py` | 5 | Playwright: the Maps screen (start, the grid grows, save, overwrite prompt, rename, delete, stop with unsaved map) |
| `test_studio_e2e_routes.py` | 5 | Playwright: the Routes screen |
| `test_studio_e2e_menu.py` | 5 | Playwright: the Robot menu screen |

The end to end files skip with exit 0 when Playwright is not installed.

The interface tests are vitest files next to the code in `TurtleBot/tools/studio/ui/src/` (24 files, 463 tests on 2026-11-28). Run them with `npm test` in `TurtleBot/tools/studio/ui/`.

| Vitest file | What it covers |
|---|---|
| `features/mapping/model.test.ts`, `features/mapping/mapping.test.tsx` | Mapping model, store, controls, save dialog, map library, canvas, screen |
| `features/routes/routes.test.tsx` | Route model, list, upload, trip status, screen |
| `features/menu/menu.test.tsx` | Menu model and YAML, built-in list, preview, entry editor, screen |
| `features/stores.gaps.test.ts` | Failure scenarios of the mapping, routes and menu stores (see the next section) |
| `features/teleop/*.test.ts(x)`, `components/safety.test.tsx` | Driving controller and driver, safety components |
| `api/client.test.ts`, `api/sse.test.ts` | The typed client and the event stream |
| `state/*.test.ts(x)`, `App.test.tsx`, `screens/*.test.ts(x)`, `lib/*.test.ts`, `features/palette/commands.test.ts` | Stores, screens, helpers, the command list |

Other checks that belong to the whole repository (link check, `py_compile` of every script) are in the repository README, not here.

## How to measure coverage

Tools used on 2026-11-28: coverage.py 7.17.5 (Python 3.13.3) and `@vitest/coverage-v8` 5.0.5, the same version as vitest 5.0.5 (Node 22.15.0). Install:

```
python -m pip install "coverage==7.*"
cd TurtleBot/tools/studio/ui
npm install        # @vitest/coverage-v8 is in package.json
```

### Python

One command, from the repository root. It runs every `test_studio_*.py` except the Playwright end to end files, under coverage.py with branch coverage, and prints the totals per file. The data files go to a temporary folder outside the repository.

```
python TurtleBot/tools/studio/covhook/run_coverage.py
```

Useful options: `--out DIR` (where the data files go), `--only a,b` or `--skip a,b` (test names without `.py`), `--json FILE` (a JSON report with the numbers per function, which is how the lists below were made). The run takes about 9 minutes on the measuring computer.

How it works:

- `TurtleBot/tools/studio/.coveragerc` sets branch coverage, parallel data files (`[run] parallel`, one file per process), and measures only `studio.py` and `robot_bridge.py`.
- The tests start Python subprocesses (the fake bridge, `studio.py --fake`). To measure those too, the runner puts `TurtleBot/tools/studio/covhook/` on `PYTHONPATH` (it holds a `sitecustomize.py` that calls `coverage.process_startup()`) and sets `COVERAGE_PROCESS_START` to the `.coveragerc`. Nothing in the Python installation is changed.
- After the runs, `coverage combine` merges all data files and `coverage report` prints the table.

A single test file by hand, with subprocesses measured (bash):

```
export STUDIO_COV_DIR=/tmp/cov COVERAGE_PROCESS_START=$PWD/TurtleBot/tools/studio/.coveragerc PYTHONPATH=$PWD/TurtleBot/tools/studio/covhook
python -m coverage run --rcfile TurtleBot/tools/studio/.coveragerc TurtleBot/tests/offline/test_studio_gaps.py
python -m coverage combine --rcfile TurtleBot/tools/studio/.coveragerc --keep /tmp/cov
python -m coverage report --rcfile TurtleBot/tools/studio/.coveragerc
```

Limitations:

- A child process that is killed (for example by a test that stops Studio hard) may lose its data. The totals can therefore be a little low, never high.
- `test_studio_bridge.py` has timing checks. While the computer is busy (for example vitest running at the same time) it failed one check twice during the first measurements; alone, and in the final run, it passed. Do not run other heavy jobs during a coverage run.
- Windows without developer mode cannot create symbolic links, so the real-link branches of `write_current` and the link cases of the upload clean up are not run there (the checks print a NOTE and use the fake file). They do run on Linux: in GitHub Actions (`turtlebot-tests.yml`, offline tests on Ubuntu with Python 3.12 and 3.10) and in WSL Ubuntu; both passed on 2026-11-28. On Linux and macOS they run.

### Interface

```
cd TurtleBot/tools/studio/ui
npm run coverage
```

This is `vitest run --coverage` with the v8 provider and the reporters `text-summary` and `json-summary` (`vite.config.ts`, `test.coverage`). The report goes to `ui/.coverage-ui/` (git-ignored). Set `STUDIO_UI_COVERAGE_DIR` to write it somewhere else, for example outside the repository. `ui/.coverage-ui/coverage-summary.json` has the numbers per file.

## Numbers measured on 2026-11-28

Python, offline test files run: `test_studio_bridge`, `desktop`, `setup`, `upgrades`, `window`, `templates`, `v2_backend`, `mapping`, `mapping_desktop`, `routes`, `routes_unit`, `menu`, `menu_unit` and, after the work of that day, `gaps`. Not run: the four Playwright files. All had 0 failures in the final run (1,652 checks in 14 files). Subprocesses were measured.

| File | Statements before | Statements after | Branches before | Branches after |
|---|---|---|---|---|
| `robot_bridge.py` | 63.5 % | 66.0 % | 62.6 % | 66.3 % |
| `studio.py` | 69.5 % | 71.0 % | 61.7 % | 63.1 % |
| Both (coverage.py combined figure, statements and branches) | 65.3 % | 67.5 % | | |

Interface (vitest, 449 tests before, 463 after, 0 failures):

| | Before | After |
|---|---|---|
| Statements | 66.86 % (3768 of 5635) | 67.06 % (3779 of 5635) |
| Branches | 63.5 % (2849 of 4486) | 63.68 % (2857 of 4486) |
| Functions | 67.79 % | 67.79 % |
| Lines | 67.02 % | 67.25 % |

The interface stores that the new tests target: `features/routes/store.ts` 83 % statements and 50 % branches to 100 % and 100 %; `features/menu/store.ts` 90 % and 91 % to 100 % and 100 %; `features/mapping/store.ts` 76 % and 79 % to 82 % and 86 %.

The totals move little because the mapping, routes and menu code was already well covered (most functions at 85 % or more). The remaining low figures are mostly code that needs the real robot (see "Not covered on purpose"). The new checks were chosen for risk, not for lines: each asserts what is left after a failure.

### Least covered areas that matter (after, 2026-11-28)

Statements missed per function, from the coverage.py JSON report. The first four groups need the real robot or a Linux link and are explained in the next section.

| Area | Function | Missed | Covered | Why or what is left |
|---|---|---|---|---|
| Mapping | `RosReal.ensure_map_subs` | 17 | 0 % | Needs ROS (`/map`, `/pose` subscriptions) |
| Mapping | `RosReal.map_data` | 14 | 0 % | Needs ROS |
| Mapping | `RosReal.pose_data` | 10 | 0 % | Needs ROS |
| Mapping | `RosReal.map_pose` | 9 | 0 % | Needs ROS and TF |
| Mapping | `RosReal._cb_slam_pose` | 8 | 0 % | Needs ROS |
| Routes | `write_current` | 15 | 54 % | The real symbolic link replace; does not run where links are not allowed (Windows without developer mode) |
| Routes | `read_current` | 4 | 74 % | Reading a real link (same reason) |
| Routes | `RouteLibrary._entry` | 4 | 74 % | `OSError` on listing or timestamps, hard to cause |
| Upload | `Studio._upload_scp` | 11 | 0 % | The scp fallback when the robot has no `tar`; needs ssh |
| Upload | `Studio._upload` | 4 | 46 % | The ssh failure mapping; needs ssh |
| Fake robot | `Bridge.h_fake_trip` | 7 | 0 % | Test helper of the fake robot, not product behaviour |
| Files | `Bridge.h_write_file` | 6 | 90 % | Rare `OSError` branches (disk full) |
| Maps | `MapLibrary.rename` | 4 | 91 % | The YAML read failure, not reachable without a race |
| Driving | `Bridge.h_teleop` | 3 | 86 % | Re-check branches inside the live loop |
| Driving | `Bridge._teleop_loop` | 2 | 96 % | Watchdog sleep branches |

Closed on 2026-11-28 (before, missed statements and covered): `Studio.map_download_zip` 22 missed, 20 % covered, now fully covered; `Bridge._pkill_motion` (the emergency stop escalation) 14 missed, 12 %, now fully covered; `Bridge.h_write_file` 44 missed, 0 %, now 90 %; `MenuService.put` 6 missed, now fully covered; `MapLibrary.rename` 9 missed, 77 %, now 91 %; `validate_route_upload` 3 missed, 88 %, now fully covered; `Studio.map_preview_png` 5 missed, 67 %, now 1 missed (94 %); `Bridge.teleop_refusal` 2 missed, 89 %, now 1 missed (94 %).

### What the new checks assert

`test_studio_gaps.py` (119 checks) and `ui/src/features/stores.gaps.test.ts` (14 tests) each describe a failure and check what remains. Examples:

- A failed link replace keeps the old current route and leaves no temporary link; a real folder named `current` is never deleted; every refusal in `set_current` (confirm not exactly `True`, reserved or hidden or path-like names, missing or incomplete route, a trip running, the navigation stack running) leaves the link where it was.
- An upload finish never replaces an existing route; an upload clean up never follows a link; a failed copy or a refused finish removes the hidden upload folder and never reports success.
- A map rename that fails on the third file puts every file back under the old name and the same rename works afterwards; renaming onto an existing map or a map being saved changes nothing.
- A menu save that cannot write leaves the old file unchanged; a text the checker rejects is not saved; a checker that hangs, is missing or exits with another code is a refusal with its reason, not a verdict.
- Route upload validation refuses every bad name, path, duplicate, bad base64, missing required file and too large total.
- The map zip and preview return 400, 404, 409 or 502 as designed, remove their temporary folder, and zip only the files that arrived.
- Manual driving is refused for the STOP file, an active e-stop, ROS not ready, mapping starting, saving or stopping, docked, an unknown dock state (never guessed), a running motion program, and a low battery (and not for plain mapping).
- Writing a file on the robot refuses an existing file without overwrite, a file changed since it was opened (sha1), path escapes, `~/.ssh`, folders and oversize text; a same-text save makes no `.bak`; an overwrite keeps the old text in `.bak`.
- The emergency stop escalation sends INT, then TERM, then KILL only as needed, reports a program nothing can stop as not stopped, and says so when `pkill` is missing.
- A program that cannot be described counts as moving.
- Interface stores keep the old list, picture or document when a refresh, fetch, check or save fails; a picture that cannot be decoded, is older than the one on screen, or arrives after the map was cleared is dropped and released; a refused menu save does not reload from the robot; a menu check goes stale when the document changes.

To make sure the checks can fail, a set of deliberate changes to a copy of the code was tried (no rollback on rename, `confirm` ignored, no cleanup after a refused finish, no sha1 conflict check, overwrite always allowed, the unknown dock state allowed, the battery ignored, no KILL step, a program that cannot be described counted as not moving). Each one made at least one check fail. One change survived at first (a `..` in the middle of a file name was accepted); a check for it was added, and the `.bak` check was made to fail cleanly instead of with an error.

## Not covered on purpose

| What | Why |
|---|---|
| `RosReal` (the real ROS node: `start`, `snapshot`, TF lookups, `/map` and `/pose` subscriptions, actions) | Needs ROS 2 and the robot. The fake robot replaces it; its contract is checked with the fake, and the real behaviour only on the robot |
| ssh, scp and `tar` over a real connection (`_upload`, `_upload_scp`, the real connect and discover paths, `setup_key`, `test_login`) | Needs a robot or an ssh server. Argument building and error mapping are unit tested; the transfer itself is on the real-robot checklist |
| Symbolic links on Windows | Creating a link needs developer mode or administrator rights, so the real link branches of `write_current` and the link cases of the upload clean up run on Linux and macOS only. The fake robot's name file covers the Windows case |
| `pgrep`, `pkill`, `/proc` against real processes | Replaced by stand-ins that record the signals; the real escalation is only seen on the robot |
| Window opening, `open_vscode`, terminal launching, Wi-Fi of the laptop, installer, Windows registry | Operating system dependent and has side effects on the computer; checked by hand when the installer is built |
| The canvas drawing of the map and lidar (`MapCanvas.tsx`) and the browser image decoder | jsdom has no canvas and no image decoding. The Playwright end to end tests draw it in a real browser |
| macOS and Linux builds | Not available on the Windows build computer |

## Real-robot checklist

Run these with the robot in a safe place and a person next to it. Dry run or docked first. Studio must be started from this repository state. Record the date, the Studio version and the result in `README.md` under "Tested on the robot".

State on 2026-11-28: the first item, the docked parts of the mapping cycle, ran on 2026-11-14 (see `README.md`, "Tested on the robot 2026-11-14 (2.1)"). Everything else below is NOT VERIFIED.

1. Mapping cycle, docked: Start mapping, live map picture appears, Save map, Stop mapping, preview, download, rename, delete. Result: verified 2026-11-14 (docked, never driven).
2. Mapping cycle while driving: start mapping, undock, drive slowly with the joystick (driving must be refused while mapping is starting, saving or stopping), watch the map grow, save, stop, dock. Result: NOT VERIFIED.
3. Overwrite: save a map under an existing name; Studio must ask a second time and the old files must be replaced only after yes. Result: NOT VERIFIED on the robot.
4. Route upload: make a route folder with `delivery/tools/plan_route.py`, upload it from the Routes screen over real ssh, check that `.upload-<name>` is gone and the route shows Ready; upload the same name again and expect a refusal; cut the cable during an upload and expect no half route. Result: NOT VERIFIED.
5. Set current: choose another route in **Use this route**, check that `routes/current` points to it, and that the choice is refused while a trip or the navigation stack runs. Result: same route verified 2026-11-14; a different route NOT VERIFIED.
6. Menu save: change an entry in the Robot menu screen, **Check with the robot**, **Save to the robot**, check `menu.yaml` and `menu.yaml.bak`, then restart the menu on the robot and see the new entry on its screen. Result: the same text saved on 2026-11-14; a changed text and the robot's screen NOT VERIFIED.
7. Emergency stop: with a motion program running (started by Studio and started by hand), press E-STOP and check that both stop. Result: NOT VERIFIED for programs started by hand.
8. The installed app on a clean computer. Result: NOT VERIFIED.

## Rules for new tests

- A new check describes a behaviour, ideally a failure, and asserts what is left afterwards (a file, a link, a screen state, a request that was not sent). A check that only runs a function does not count.
- Put it in the lowest layer that can show it. Pure logic goes in the unit files; failures of a service go in the service files or `test_studio_gaps.py`.
- Never connect to the robot from a test. Use `--fake`, temporary folders and stand-ins.
- Python test files use the `check()` helper, print `PASS` or `FAIL`, and exit with the number of failures. Scripts that run on the robot keep LF line endings.
- Try the check against a deliberately broken copy of the code at least once, to see it fail.
- After a change, run the files you touched, then `npm run lint`, `npm run typecheck` and `npm test` in `ui/`, and update the dated numbers above only after running `run_coverage.py` and `npm run coverage` again.
