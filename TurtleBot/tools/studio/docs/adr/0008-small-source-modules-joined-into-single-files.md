# ADR-0008: Small source modules, joined into the two single files by a build step

**Status:** Accepted (2026-11-28). Refines [ADR-0002](0002-streamed-single-file-bridge.md); does not replace it.

## Context

`robot_bridge.py` (about 4,400 lines) and `studio.py` (about 4,200 lines) had grown into two files that are hard to
read. Each was mostly one large class: `Bridge` (about 1,200 lines) and `Studio` (about 1,600 lines). A new reader
could not see where one feature ends and the next begins.

The robot side must still reach the robot as one file (ADR-0002). The offline tests import both files as single
modules and replace module-level names while they run. A plain split into a Python package would break both.

## Decision

- The source of each file lives in a small package of modules: `bridge/` for `robot_bridge.py`, `desktop/` for
  `studio.py`. Each module has one job, and its first lines say what that job is.
- The two large classes are split by feature into mixin classes, one per module: connection, programs, files,
  Wi-Fi, maps, routes, menu and so on. The final class only names its mixins.
- `bundle.py` joins the modules, in the order listed in each package's `__init__.py`, into the same two files as
  before. Lines marked `# bundle: skip` (the imports between modules of one package) are left out.
- The two joined files are committed. CI runs `python bundle.py --check` and fails if they are not up to date,
  the same way it checks the committed `web/v2` build.

## Consequences

- Nothing changes at run time: the robot still receives one file, the packaged app still ships two files, and
  every test still imports the same modules.
- Readers and reviewers open the module for the feature they care about. `docs/CODE-MAP.md` lists them all.
- Code is in the repository twice (source and joined). The joined files start with a "GENERATED FILE, do not
  edit" line, and the CI check stops a hand edit from being merged.
- One extra step for contributors: run `python bundle.py` after editing a module. Forgetting it fails CI with
  the exact command to run.

## Alternatives considered

- **Real Python packages imported at run time.** On the desktop this is normal, but the tests replace
  module-level names on `studio` and `robot_bridge`, which a package does not pass through to its submodules.
  On the robot it would need a custom importer inside the ssh start command.
- **Leave the single files and add more section comments.** Cheapest, but the two large classes would stay the
  same size, which was the main problem.
- **A zip application (`.pyz`).** Python can run one, but not from standard input, so the robot would need a
  temporary file, which ADR-0002 avoids.
