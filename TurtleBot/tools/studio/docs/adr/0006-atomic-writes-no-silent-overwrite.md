# ADR-0006: Every write on the robot is atomic and never overwrites without an explicit request

**Status:** Accepted (2026-11-14)

## Context

Studio writes files that a running robot reads: the menu file (read by the menu service), the `current` route link
(read when a trip starts), route folders and maps. A half-written file or a link that points nowhere could stop a
demo or send the robot to a wrong map. Students also make mistakes, such as reusing a name.

## Decision

- Menu file: write `menu.yaml.tmp`, keep the old file as `menu.yaml.bak`, rename over `menu.yaml`.
- `current` link: create the new link beside it and rename it over the old one (the atomic equivalent of
  `ln -sfn`); refuse when `current` is a real folder; refuse while a trip or the navigation stack runs.
- Route upload: extract into the hidden `routes/.upload-<name>`, then rename to `routes/<name>`; refuse an existing
  name; the name `current` is reserved.
- Maps: `save_map.sh` refuses an existing name unless Studio passes `--force`, which the interface sends only after a
  second confirmation; rename never overwrites; delete needs `confirm: true` and a danger dialog.
- Every name is checked against one rule (letters, digits, `-`, `_`, up to 48 characters) and every path is joined
  and checked to stay inside its folder.

## Consequences

- A reader on the robot sees either the old file or the new one, never a mix.
- Some legitimate cases need two steps (rename the old route first, then upload the new one).
- Tests: `test_studio_routes.py` and `test_studio_routes_unit.py` (reserved names, refusals, no leftover hidden
  folders), `test_studio_menu.py` (`.bak`, no temporary file left), `test_studio_mapping.py` (path escapes, overwrite
  refusals, a save that rewrote nothing counts as failed).

## Alternatives considered

- Write in place: simpler, but readers can see half a file.
- Overwrite with a warning only: one wrong click replaces a map that took an hour to make.
