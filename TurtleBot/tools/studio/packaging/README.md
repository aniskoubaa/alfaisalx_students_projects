# Studio packaging

Builds the single-file TurtleBot Studio program and its installers. Used by whoever releases Studio; students download the finished installer instead.

| File | What it does | Runs on (laptop / robot / CI) |
|---|---|---|
| `build.py` | Builds with PyInstaller; `--smoke` tests the result; `--installer` makes the Windows setup exe | laptop, CI |
| `studio.spec` | PyInstaller spec (Windows exe, macOS app, Linux binary) | laptop, CI |
| `installer.nsi` | NSIS 3 script for the per-user Windows installer | laptop, CI |
| `install-linux.sh` | Installs the Linux binary for the current user, no administrator rights | laptop (Linux) |
| `studio.ico` | Program icon | laptop, CI |
| `dist/` | Build output (setup exes for 1.3, 2.0, 2.1 and 2.1.1, and the exe) | built files |

Build on the system you want the file for (PyInstaller cannot cross-compile). Run from `TurtleBot/tools/studio/`:

```bash
pip install pyinstaller==6.20.0
python packaging/build.py --smoke
```

`--installer` needs NSIS 3 (`makensis`). The interface in `web/v2/` is built separately from `ui/`; see the Studio README.

See also: [Studio README, Building the app](../README.md#building-the-app).
