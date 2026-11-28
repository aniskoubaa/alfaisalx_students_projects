# Contributing to the TurtleBot folder

How to work in `TurtleBot/` of the lab repository: where things go, how to record changes, how to write the docs and what to check before you finish. Read [README.md](README.md) first for what the project is, and [ARCHITECTURE.md](ARCHITECTURE.md) for how it fits together.

The repository is public. Never put a password, Wi-Fi key, private key, token or personal data in it. The one exception is the robot's factory login (user `ubuntu`, password `turtlebot4`), which is the public default from the TurtleBot 4 manual and is already in the guides. For any other secret, write "ask the lab maintainer".

## 1. Where things go

| What you add | Where | Notes |
|---|---|---|
| A first-time walkthrough or tutorial | `docs/getting-started/` | Takes a newcomer from start to finish |
| A task guide ("how do I do X") | `docs/guides/` | Not tied to one program. A guide tied to a program sits next to it, as in `examples/README.md` |
| An explanation (how or why) | `docs/explanations/` | No step-by-step tasks |
| Lists, tables, results, plans to look up | `docs/reference/` | |
| An investigation of one problem | `docs/findings/` | Dated and not rewritten; later facts are added as dated updates |
| A new docs page | Also add it to `docs/index.html`, `docs/README.md` and the README of its folder | Every page needs a link in the hub |
| A dated step log | `General Tasks/` at the repository root | Include what failed |
| A record of a change to the robot | [MAINTENANCE.md](MAINTENANCE.md) | See section 2 |
| Planned work | [ROADMAP.md](ROADMAP.md) | See section 3 |
| An example program for the robot | `examples/` | Describe how to run it safely in `examples/README.md` |
| A script that runs on the robot to configure it | `setup/` | Read MAINTENANCE.md before running any of them |
| The delivery project | `delivery/` | Its layout is deployed to the robot as is. Do not move files without checking `delivery/tools/deploy.py` |
| Studio (desktop app) | `tools/studio/` | Has its own README, INSTALL and `docs/` |
| Connect and timing tools | `tools/connect/`, `tools/timing/` | |
| Offline tests | `tests/offline/` | Run on any computer, no robot |
| Scripts that run on the robot to diagnose it | `tests/robot/` | |
| Evidence from real runs | `tests/logs/` | Raw logs, dated names |
| Installer for Studio | `Download/` | The installer link is used by installed apps. Do not rename or move it |

These stay at the root of `TurtleBot/` on purpose, because programs, Studio and the lab skills link to them by path: `README.md`, `ROADMAP.md`, `MAINTENANCE.md`, `HOW-TO-CONNECT.md`. This file and `ARCHITECTURE.md` are there too.

### Naming

- Docs files: lowercase-kebab-case (`network-and-connectivity.html`, `parts-list.md`). Pages that come as HTML and Markdown share the base name.
- The four root files above keep their upper-case names.
- Dated records start with the date as `YYYY-MM-DD` (as in `tests/logs/`).
- Do not use a laptop's user name or machine name in a document. Use `ubuntu@turtlebot4.local`, or the address on the robot's display.

## 2. Every robot change goes in MAINTENANCE.md

A change to the robot, its network settings, a shared account or the lab router gets a row in the change register of [MAINTENANCE.md](MAINTENANCE.md#change-register) with these columns: ID, change, location, purpose, **verify** and **undo**, status. Take the next free R number. Write the verify command and the undo command so someone else can run them. Add a dated entry with what you did, and what failed, to a log in `General Tasks/`.

Things that are not installed changes (a read-only check, a program run from your own folder) still go in the dated log. Admin steps (`sudo`, Wi-Fi changes) need a person who knows the `ubuntu` password to type it.

## 3. ROADMAP task blocks

Planned work lives in [ROADMAP.md](ROADMAP.md), one block per task, in the format already used there:

1. Heading `### TB-nn Title`. Take the next free ID. Do not reuse or renumber IDs.
2. A line with `**Priority:** P0 to P3 | **Status:** ... | **Depends on:** ...`.
3. **Goal**, **Why it matters**, **Steps**, **Acceptance criteria** (as `[ ]` boxes), **Risks and rollback**, **Estimated effort**.
4. Add the task to the summary table at the top.
5. Progress is added as dated "Progress" or "Update" paragraphs. Do not rewrite earlier ones.

Set a task to In progress with your name and date when you start, and Done with the date when its acceptance criteria are met. Then go through the "Definition of done" at the end of the roadmap.

## 4. Docs style

- Plain, specific English. Short sentences. No marketing tone, no filler.
- Write for any lab member on any computer (Windows, macOS, Linux). In a main flow, show the command for each system, or one that works on all.
- Only state facts you can check in the repo or that you measured. Mark anything not run on the real robot **NOT VERIFIED**, **[to verify]** or "not yet tested on this robot". Do not invent numbers. Give the date and the conditions for every measurement.
- Never delete earlier documentation. When something is outdated, keep it, mark it "superseded" with the date and say what replaced it, and add the new facts as a dated update.
- HTML pages are single self-contained files: inline CSS and JS, no external resources. They reuse the style block of [docs/explanations/network-and-connectivity.html](docs/explanations/network-and-connectivity.html), support light and dark mode and work at phone width. Each page under `docs/` has an "All guides" link at the top that goes to `docs/index.html`.
- Every relative link must resolve. Use relative links, not absolute paths or machine paths.
- Refer to the safety rules where a page tells someone to move the robot.

## 5. Tests and checks

Before you finish, run from the repository root:

```bash
python TurtleBot/tests/check_links.py                 # must report 0 problems
python TurtleBot/delivery/tools/verify_all.py         # linters (if installed), syntax checks and the offline tests
```

- The offline tests are in `tests/offline/`. Each file runs on its own, for example `python TurtleBot/tests/offline/test_pure.py`. They must pass. They use a simulated robot, so a pass says nothing about the real robot. The full list and what each covers is in [tests/README.md](tests/README.md) and in section 12 of [delivery/README.md](delivery/README.md#12-offline-tests).
- The delivery tests need PyYAML. The browser tests skip with exit 0 when Playwright is not installed.
- If you change the Studio interface in `tools/studio/ui/`: `npm ci`, then `npm run lint`, `npm run typecheck`, `npm test` and `npm run build`. The build output in `web/v2/` is committed, so rebuild and commit it with the source change. Details: [tools/studio/ui/README.md](tools/studio/ui/README.md).
- If you change Studio's Python code: edit the small modules in `tools/studio/desktop/` (the desktop app) or `tools/studio/bridge/` (the robot side), never `studio.py` or `robot_bridge.py` directly. Then run `python TurtleBot/tools/studio/bundle.py`, which joins the modules back into those two files, and commit both. CI fails if they differ ([ADR-0008](tools/studio/docs/adr/0008-small-source-modules-joined-into-single-files.md)). [tools/studio/docs/CODE-MAP.md](tools/studio/docs/CODE-MAP.md) says which module holds what.
- GitHub runs the same checks on every push that changes `TurtleBot/` (`.github/workflows/`).
- Add or update a test with every change to code. When you fix a bug, add a test that fails without the fix.

## 6. Commit messages and pull requests

- One logical change per commit. The first line says what changed, in the imperative, in about 70 characters or fewer: "Add architecture overview", "Fix route check for empty waypoint list".
- Add a body when the why is not obvious. Name the task (`TB-29`) or change (`R22`) it belongs to.
- Plain and professional. No jokes, no filler, no tool names.
- Review the diff for credentials before you commit.
- Commit and push when the work is finished and verified, not after every step.

## 7. Safety before motion

Anything that can move the robot needs a person next to it. Before you run a program that moves the robot, or test one:

1. Dry-run first where the program has `--dry-run`.
2. Clear about 1 m of floor around the robot. Check there is no cable, step or person in its way.
3. Know how to stop it: E-STOP in Studio (Esc or Space), `touch ~/STOP` on the robot, controller button B (**NOT VERIFIED on this robot**). See [ARCHITECTURE.md](ARCHITECTURE.md#emergency-stop-paths).
4. Do not start extra `ros2` commands or reconnect Studio during a run. A new ROS participant can stall the base (TB-25).
5. Record the run, including failures, in the dated log, and the result in MAINTENANCE.md if the robot's configuration changed.

Offline work needs none of this. Nothing in the offline tests moves a robot.
