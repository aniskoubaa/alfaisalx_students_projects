# TurtleBot 4 documentation

All the written material for the AlfaisalX lab's TurtleBot 4, sorted by what you need from it. The same index with cards and status chips is [index.html](index.html) (open it in a browser; GitHub shows HTML only as source). Back to the [TurtleBot folder README](../README.md).

## How these docs are organised

The pages follow the Diataxis idea: four kinds of documentation, kept apart because they answer different questions, plus a section for investigations.

| Section | Folder | It answers | You read it when |
|---|---|---|---|
| Tutorials | [getting-started/](getting-started/README.md) | "Take me through it from the start" | You are new, or showing the robot to a visitor |
| How-to guides | [guides/](guides/README.md) | "How do I do this one task?" | You know the basics and need one thing done |
| Explanations | [explanations/](explanations/README.md) | "How does it work and why was it built this way?" | You want to understand, not follow steps |
| Reference | [reference/](reference/README.md) | "What are the facts, lists and results?" | You look something up |
| Findings | [findings/](findings/README.md) | "What went wrong, and what did we measure?" | You want the record of one investigation |

Records that other files link by path stay at the root of `TurtleBot/`: [README.md](../README.md), [ROADMAP.md](../ROADMAP.md), [MAINTENANCE.md](../MAINTENANCE.md) and [HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md). Dated step logs are in `General Tasks/` at the repository root. See [CONTRIBUTING.md](../CONTRIBUTING.md) for where new pages go.

Many pages come in two versions. The HTML version is interactive and is meant to be opened in a browser from a downloaded copy of the repository. The Markdown version has the same content for reading on GitHub.

## Tutorials: getting started

| Document | For | What it answers |
|---|---|---|
| [meet-the-robot.html](getting-started/meet-the-robot.html) | Visitors, new students, reviewers | What are the robot's parts, what does each do, and what works today |
| [what-you-can-build.html](getting-started/what-you-can-build.html) | Students choosing a project | What can I build on this robot, from a first program to navigation, and what is tested |
| [do-it-yourself.html](getting-started/do-it-yourself.html) / [.md](getting-started/do-it-yourself.md) | New students | How do I power on, connect, run my own code, drive, dock and stop, on Windows, macOS or Linux |
| [studio-lab-demo.html](getting-started/studio-lab-demo.html) / [.md](getting-started/studio-lab-demo.md) | Studio users | How do I get from installing Studio to running the delivery demo from the robot's front panel |
| [field-guide.html](getting-started/field-guide.html) | Beginners | A short overview of the hardware and ROS 2 |

## How-to guides

| Document | For | What it answers |
|---|---|---|
| [lidar-guide.html](guides/lidar-guide.html) / [.md](guides/lidar-guide.md) | Students and developers | How does the lidar work, how do I read a scan, and how do I use it in Python |

Other task guides live next to the code they describe: [../examples/README.md](../examples/README.md) (run the example programs safely), [../delivery/README.md](../delivery/README.md) (map, plan and run the campus delivery), [../tools/studio/INSTALL.md](../tools/studio/INSTALL.md) and the Studio guides in [../tools/studio/docs/](../tools/studio/docs/FIRST-CONNECTION.md), and [../HOW-TO-CONNECT.md](../HOW-TO-CONNECT.md).

## Explanations

| Document | For | What it answers |
|---|---|---|
| [how-a-command-travels.html](explanations/how-a-command-travels.html) | Developers, maintainers | How does one drive command reach the wheels and come back as `/odom`, and why could a starting program pause the base (TB-25) |
| [docking-explained.html](explanations/docking-explained.html) | Students | How does the robot find its dock, and what are the docking stages |
| [motion-program-design.html](explanations/motion-program-design.html) | Developers | How does `motion_shapes.py` plan, control and guard a run |
| [motion-simulator.html](explanations/motion-simulator.html) | Students, developers | What does a shape look like when driven, with the speed commands, the lidar stop zone and odometry dropouts |
| [network-and-connectivity.html](explanations/network-and-connectivity.html) | Maintainers, anyone who cannot connect | What networks are around the robot and why did the Wi-Fi drop (Markdown: [network-findings.md](findings/network-findings.md)) |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | Developers, maintainers | How is the whole system built, and why are there constraints such as one ROS participant |

## Reference

| Document | For | What it answers |
|---|---|---|
| [test-results.html](reference/test-results.html) | Developers, maintainers | What were the results of the motion program runs of 2026-10-04 |
| [parts-list.md](reference/parts-list.md) | Lab maintainer | What parts does the delivery project still need, and what do they cost (planning only) |
| [spoken-messages.md](reference/spoken-messages.md) | Developers | What spoken lines are planned for the delivery (plan only, not tested on the robot) |
| [../tests/README.md](../tests/README.md) | Developers | What the test folders hold and how to run the offline tests |

## Findings

| Document | For | What it answers |
|---|---|---|
| [lidar-diagnosis.html](findings/lidar-diagnosis.html) / [lidar-findings.md](findings/lidar-findings.md) | Maintainers | How was the "lidar not detected" fault of 2026-10-03 diagnosed and fixed |
| [network-findings.md](findings/network-findings.md) | Maintainers | What was measured during the Wi-Fi drops of 2026-10-04 and 2026-10-05, and what was proposed |
