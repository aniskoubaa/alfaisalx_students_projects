# ADR-0005: The robot's own checker is the only validator of the menu file

**Status:** Accepted (2026-11-12)

## Context

The front-panel menu reads `~/robot_code/menu/menu.yaml`. Its rules (locked entries, 17-character labels, program
paths under `~/robot_code`, placement with `after`, at most 8 own entries) are implemented in
`delivery/menu_config.py`, which the menu service uses at run time. An invalid file makes the robot fall back to the
standard menu.

## Decision

Studio never decides alone whether a menu file is valid. The bridge runs the robot's deployed checker
(`menu_config.py --check FILE --json`) for every check and before every save, and refuses to save when the checker is
missing or says no. The interface mirrors the rules only for instant feedback while typing, and builds the file with
its own small YAML writer for the fixed schema.

## Consequences

- No drift between what Studio accepts and what the robot accepts: the robot's answer wins.
- Saving needs the delivery package (with the checker) deployed; until then Studio explains this and disables Save.
- Saves keep the old file as `menu.yaml.bak` and replace the file atomically (ADR-0006).
- Tests: `test_studio_menu.py` (with the repository's checker), `test_studio_menu_unit.py` (scripted checker:
  missing, bad JSON, timeout), vitest for the editor rules and the YAML writer, `test_studio_e2e_menu.py`.

## Alternatives considered

- Validate in Studio only: fast, but a second rule set that would drift from the robot's.
- Import `menu_config.py` into the desktop: needs PyYAML in the packaged app and still may not match the deployed
  version on the robot.
