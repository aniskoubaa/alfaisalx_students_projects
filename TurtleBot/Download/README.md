# Download TurtleBot Studio

TurtleBot Studio is the app for the lab's TurtleBot 4. It finds the robot, shows what it sees, runs programs, lets you drive it and has an emergency stop. You do not need to install Python, ROS or anything else.

## Windows 10 and 11

**[Download TurtleBot Studio for Windows](https://github.com/aniskoubaa/alfaisalx_students_projects/raw/main/TurtleBot/Download/TurtleBotStudio-Setup-2.0.exe)**

| | |
|---|---|
| File | [TurtleBotStudio-Setup-2.0.exe](TurtleBotStudio-Setup-2.0.exe) |
| Version | <!-- studio-version -->2.0<!-- /studio-version --> |
| Size | <!-- studio-size -->8.8 MB<!-- /studio-size --> |
| SHA-256 | <!-- studio-sha256 -->79C7A9891482D66628E369777717810AFC754B8CC7ED21AA50B1B811D3A0F464<!-- /studio-sha256 --> |
| Needs | Windows 10 or 11. No administrator rights |

> **Version 2.1 (2026-11-12)** adds the Maps, Routes and Robot menu screens. Its Windows installer is not built yet, so the file above is still version 2.0. To use 2.1 now, run it with Python: [INSTALL.md, option B](../tools/studio/INSTALL.md#option-b-run-it-with-python).

How to install:

1. Click the download link above. Your browser saves the file.
2. Open the file. Windows may show "Windows protected your PC" because the app is not signed by a company. Click **More info**, then **Run anyway**.
3. Click **Next**, **Install**, **Finish**. Studio opens by itself.

You now have **TurtleBot Studio** on your desktop and in the Start menu. The Start menu also has **TurtleBot Studio (simulated robot)**, a practice version with a pretend robot. Nothing real moves in it, so you can try every button.

Next: [connect to the robot for the first time](../tools/studio/docs/FIRST-CONNECTION.md).

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
