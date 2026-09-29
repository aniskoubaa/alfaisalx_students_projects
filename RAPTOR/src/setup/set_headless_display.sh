#!/usr/bin/env bash
# Give the Jetson's console a usable resolution when no monitor is attached.
#
# Runs ON THE JETSON, as root:   sudo bash set_headless_display.sh
#
# The problem: with HDMI-0 disconnected, the Tegra driver starts X at 640x480.
# That is what VNC shows, and it is smaller than the RAPTOR demo window.
#
# The fix: install ../system/etc/X11/xorg.conf, which declares a connected
# monitor and an explicit screen. On this board that yields 1024x768 - see the
# comments in that file for why 1080p is not reachable without a fake EDID.
#
# SAFETY: a broken xorg.conf leaves the board with no desktop at all, and it is
# usually only reachable over SSH. So the stock file is backed up once, and if X
# does not come back at >= 1024x768 the backup is restored automatically.
# Restarting the display manager ends any desktop session - including a VNC
# viewer's - so run this when nobody is logged in.
set -uo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SRC_CONF="$HERE/../system/etc/X11/xorg.conf"
CONF=/etc/X11/xorg.conf
BACKUP=/etc/X11/xorg.conf.pre-headless
MIN_W=1024
MIN_H=768

if [ "$(id -u)" -ne 0 ]; then echo "run with sudo" >&2; exit 1; fi
[ -f "$SRC_CONF" ] || { echo "missing $SRC_CONF - run from src/setup/" >&2; exit 1; }

# Current console resolution, read via the running Xorg's own auth file.
current_mode() {
    local auth
    auth="$(ps -eo args= | grep -m1 '^/usr/lib/xorg/Xorg' | sed -n 's/.*-auth \([^ ]*\).*/\1/p')"
    [ -n "$auth" ] || return 1
    DISPLAY=:0 XAUTHORITY="$auth" xrandr 2>/dev/null \
        | sed -n 's/^Screen 0:.*current \([0-9]\+ x [0-9]\+\).*/\1/p' | tr -d ' '
}

restart_display() {
    systemctl restart gdm3 2>/dev/null || systemctl restart gdm
    sleep 12
}

echo "current resolution: $(current_mode || echo unknown)"

if [ ! -f "$BACKUP" ]; then
    cp -a "$CONF" "$BACKUP"
    echo "backed up stock config to $BACKUP"
fi

install -m 0644 "$SRC_CONF" "$CONF"
echo "installed $CONF - restarting display manager"
restart_display

mode="$(current_mode || true)"
echo "resolution now: ${mode:-<X not up>}"
w="${mode%%x*}"; h="${mode##*x}"

# Keep any usable result. An earlier version demanded exactly 1920x1080 and
# rolled a working 1024x768 back to 640x480 - strictly worse than keeping it.
if [ -n "$mode" ] && [ "${w:-0}" -ge "$MIN_W" ] && [ "${h:-0}" -ge "$MIN_H" ]; then
    echo "OK: console is $mode"
    systemctl restart x11vnc 2>/dev/null || true   # re-attach VNC to the new X server
    exit 0
fi

echo "X came up at '${mode:-<none>}', below ${MIN_W}x${MIN_H} - restoring the stock config" >&2
cp -a "$BACKUP" "$CONF"
restart_display
systemctl restart x11vnc 2>/dev/null || true
echo "restored; resolution now: $(current_mode || echo unknown)" >&2
exit 1
