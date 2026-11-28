# Download TurtleBot Studio

TurtleBot Studio is the app for the lab's TurtleBot 4. It finds the robot, shows what it sees, runs programs, lets you drive it and has an emergency stop. You do not need to install Python, ROS or anything else.

## Windows 10 and 11

**[Download TurtleBot Studio for Windows](https://github.com/aniskoubaa/alfaisalx_students_projects/raw/main/TurtleBot/Download/TurtleBotStudio-Setup-2.2.1.exe)**

| | |
|---|---|
| File | [TurtleBotStudio-Setup-2.2.1.exe](TurtleBotStudio-Setup-2.2.1.exe) |
| Version | <!-- studio-version -->2.2.1<!-- /studio-version --> |
| Size | <!-- studio-size -->8.9 MB<!-- /studio-size --> |
| SHA-256 | <!-- studio-sha256 -->63C2723FCE07141B9EB38303B8C4FD32B309C2C790DF03612327E305CCEB71CF<!-- /studio-sha256 --> |
| Needs | Windows 10 or 11. No administrator rights |

> **Version 2.2.1** (2026-11-28) fixes a bug from every earlier version: Studio sometimes answered a request with a stray "not found" left over from the page before, so a button or a list could fail at random. Install it over any earlier version; your settings stay.
>
> **Version 2.2.0** (2026-11-28, replaced the same day by 2.2.1) is easier to find your way around: Home asks what you want to do, the menu on the left is grouped in plain words, Programs and Code link to each other, the arguments box shows each program's own example, and Studio warns before a moving program starts on the dock. Install it over 2.1.1; your settings stay. Not tried on the real robot yet.
>
> Earlier, **version 2.1.1** (2026-11-26) was a small fix: on the Programs screen, pressing Run with an empty arguments box for a program that needs one (for example `motion_shapes.py`, which needs a shape) no longer starts it; Studio fills in a safe dry-run example and says why. Install it over 2.1; your settings stay.
>
> **Version 2.1** adds the Maps, Routes and Robot menu screens. The installer above is version 2.1 (built 2026-11-14). It replaces the 2.0 installer (2026-10-30), which is still in the repository history. What has and has not been tested on the robot: [Studio README, "Tested on the robot 2026-11-14 (2.1)"](../tools/studio/README.md).
>
> *Earlier text, superseded 2026-11-14:* "Its Windows installer is not built yet, so the file above is still version 2.0. To use 2.1 now, run it with Python: INSTALL.md, option B."

How to install:

1. Click the download link above. Your browser saves the file.
2. Open the file. Windows may show "Windows protected your PC" because the app is not signed by a company. Click **More info**, then **Run anyway**.
3. Click **Next**, **Install**, **Finish**. Studio opens by itself.

You now have **TurtleBot Studio** on your desktop and in the Start menu. The Start menu also has **TurtleBot Studio (simulated robot)**, a practice version with a pretend robot. Nothing real moves in it, so you can try every button.

Next: [connect to the robot for the first time](../tools/studio/docs/FIRST-CONNECTION.md).

Short on time in the lab? The [Studio quick guide for a lab demo](../docs/getting-started/studio-lab-demo.md) goes from install to mapping and a delivery demo on one page ([interactive version](../docs/getting-started/studio-lab-demo.html)).

## macOS and Linux

There is no ready-made file for macOS and Linux in this folder yet. Use the Python version: [INSTALL.md, option B](../tools/studio/INSTALL.md#option-b-run-it-with-python). It is the same app.

## Remove it

Windows Settings, Apps, **TurtleBot Studio**, Uninstall. Your settings stay in `%APPDATA%\TurtleBotStudio`; delete that folder too if you want everything gone.

## For the maintainer

This folder holds exactly one installer, the current version. To publish a new version, from `TurtleBot/tools/studio`:

```
python packaging/build.py --smoke --installer --publish
```

That builds and tests the app, makes the installer, copies it here (removing the older one) and updates the version, size and checksum on this page and on the TurtleBot start page. Then commit and push.
