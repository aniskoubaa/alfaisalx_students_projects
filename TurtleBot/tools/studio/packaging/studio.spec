# PyInstaller spec for TurtleBot Studio.
#   Windows: one windowed .exe (no console; the app opens its own window; errors go to studio.log).
#   macOS:   a windowed TurtleBotStudio.app bundle (not code-signed: Gatekeeper asks the user to allow it).
#   Linux:   one binary; the console is kept so a terminal launch still prints the address.
# Build with build.py (or: python -m PyInstaller --clean --noconfirm studio.spec, from this folder).
import json
import os
import sys

STUDIO = os.path.abspath(os.path.join(SPECPATH, '..'))   # SPECPATH = folder of this spec
IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
ICON = os.path.join(SPECPATH, 'studio.ico')               # made by build.py (stdlib only), not committed
with open(os.path.join(STUDIO, 'version.json'), encoding='utf-8') as _f:
    VERSION = json.load(_f)['version']


def tree(sub):
    """Every file under STUDIO/sub as (source, folder inside the bundle)."""
    out = []
    root = os.path.join(STUDIO, sub)
    for d, _dirs, files in os.walk(root):
        if '__pycache__' in d:
            continue
        rel = os.path.relpath(d, STUDIO).replace(os.sep, '/')
        for f in files:
            if not f.endswith(('.pyc', '.pyo')):
                out.append((os.path.join(d, f), rel))
    return out


datas = tree('web') + tree('templates') + [
    (os.path.join(STUDIO, 'programs.json'), '.'),
    (os.path.join(STUDIO, 'version.json'), '.'),
    (os.path.join(STUDIO, 'robot_bridge.py'), '.'),   # also sent as bytes to the robot
]

a = Analysis(
    [os.path.join(STUDIO, 'studio.py')],
    pathex=[STUDIO],
    datas=datas,
    hiddenimports=['robot_bridge'],
    excludes=['tkinter', 'unittest', 'pydoc', 'test', 'lib2to3', 'idlelib', 'turtledemo'],
    noarchive=False,
)
pyz = PYZ(a.pure)
windowed = IS_WIN or IS_MAC

if IS_MAC:
    exe = EXE(
        pyz, a.scripts, [], exclude_binaries=True,
        name='TurtleBotStudio',
        console=False,
        upx=False, debug=False, strip=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TurtleBotStudio-files')
    app = BUNDLE(
        coll,
        name='TurtleBotStudio.app',
        icon=None,
        bundle_identifier='org.alfaisalx.turtlebotstudio',
        info_plist={'CFBundleName': 'TurtleBot Studio', 'CFBundleDisplayName': 'TurtleBot Studio',
                    'CFBundleShortVersionString': VERSION, 'CFBundleVersion': VERSION,
                    'NSHighResolutionCapable': True},
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name='TurtleBotStudio',
        console=not windowed,
        icon=ICON if (IS_WIN and os.path.isfile(ICON)) else None,
        upx=False,
        debug=False,
        strip=False,
    )
