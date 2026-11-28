# Offline tests

Tests that run on any computer with no robot and no ROS (Python 3.10 or newer). Used by anyone changing code in `TurtleBot/`, and by CI.

Run one test, from the repo root, then everything for the delivery project:

```bash
python TurtleBot/tests/offline/test_plan_route.py
python TurtleBot/delivery/tools/verify_all.py
```

Each script prints PASS or FAIL and exits non-zero on a failure. Some need PyYAML, `bash`, or (the `test_studio_e2e*` ones) Playwright and a browser; see the top of each file. CI runs them from [.github/workflows/turtlebot-tests.yml](../../../.github/workflows/turtlebot-tests.yml).

| Area | Files | Runs on (laptop / robot / CI) |
|---|---|---|
| Delivery | `test_delivery_config.py`, `test_delivery_deploy.py`, `test_delivery_menu.py`, `test_delivery_menu_config.py`, `test_delivery_mission.py`, `test_delivery_sim.py`, `test_delivery_voice.py`, `test_plan_route.py` | laptop, CI |
| Studio (unit and backend) | `test_studio_bridge.py`, `test_studio_desktop.py`, `test_studio_mapping.py`, `test_studio_mapping_desktop.py`, `test_studio_menu.py`, `test_studio_menu_unit.py`, `test_studio_routes.py`, `test_studio_routes_unit.py`, `test_studio_setup.py`, `test_studio_templates.py`, `test_studio_upgrades.py`, `test_studio_v2_backend.py`, `test_studio_window.py` | laptop, CI |
| Studio (browser, Playwright) | `test_studio_e2e.py`, `test_studio_e2e_maps.py`, `test_studio_e2e_menu.py`, `test_studio_e2e_routes.py` | laptop, CI |
| Examples and shapes | `test_pure.py`, `test_sim_runs.py` | laptop, CI |
| Simulator | `sim.py` (stub ROS and virtual-clock robot used by the tests; not a test itself) | laptop, CI |
| Setup scripts and timing | `test_lidar_restart.py`, `test_wifi_retry.py`, `test_timing.py` | laptop, CI |

Passing these tests does not prove a program works on the robot.

See also: [tests/README.md, Offline tests](../README.md#offline-tests-offline-any-computer-no-robot-no-ros) and [delivery/README.md, Offline tests](../../delivery/README.md#12-offline-tests).
