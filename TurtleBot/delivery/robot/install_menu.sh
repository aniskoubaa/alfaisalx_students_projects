#!/bin/bash
# Install, remove or check the front-panel menu of the delivery robot as a systemd USER service. Runs ON THE ROBOT
# (log in with ssh first; see delivery/README.md, Connecting). Never uses sudo: the service lives in
# ~/.config/systemd/user and the robot's user has Linger=yes, so it starts at boot without a login.
#
#   bash install_menu.sh [--dry-run]               copy delivery-menu.service, reload, enable and start it
#   bash install_menu.sh --uninstall [--dry-run]   stop it, disable it, remove the unit file
#   bash install_menu.sh --status                  is it enabled / active, the last log lines, the last menu.log lines
#
# What the service runs: delivery_menu.py through ~/robot_code/delivery (the symlink that tools/deploy.py switches), so
# deploy the delivery folder first. A deploy restarts the service by itself when it is enabled and no mission runs.
# KillMode=process in the unit: stopping or restarting the menu never stops the navigation stack or a running mission.
# The menu uses the front-panel buttons and the display. To go back to the stock menu run --uninstall.
# --dry-run prints the commands and runs nothing (nothing is copied, nothing is changed).

UNIT_NAME="delivery-menu.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="$SCRIPT_DIR/$UNIT_NAME"
UNIT_DIR="$HOME/.config/systemd/user"
MENU_PY="$HOME/robot_code/delivery/delivery_menu.py"
MENU_LOG="$HOME/robot_code/logs/delivery/menu.log"

usage() { sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "ERROR: $*" >&2; exit 1; }

MODE=install; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) MODE=uninstall ;;
    --status) MODE=status ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

# systemctl --user needs the user's runtime directory; an ssh login normally has it, a bare shell may not.
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
  XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export XDG_RUNTIME_DIR
fi

# run CMD...: print it; run it unless this is a dry run.
run() {
  if [ "$DRY" = 1 ]; then echo "(dry run) $*"; else echo "+ $*"; "$@" || die "failed: $*"; fi
}

need_systemctl() {
  command -v systemctl >/dev/null 2>&1 && return 0
  [ "$DRY" = 1 ] && { echo "(dry run) systemctl not found here; the robot has it"; return 0; }
  die "systemctl not found"
}

case "$MODE" in
  install)
    [ -f "$UNIT_SRC" ] || die "$UNIT_SRC is missing"
    [ -f "$MENU_PY" ] || echo "WARNING: $MENU_PY is missing: deploy the delivery folder first (tools/deploy.py), the service fails until then"
    need_systemctl
    if command -v loginctl >/dev/null 2>&1 && [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
      echo "WARNING: Linger is not 'yes' for $USER: the menu would only start after a login"
    fi
    run mkdir -p "$UNIT_DIR"
    run cp "$UNIT_SRC" "$UNIT_DIR/$UNIT_NAME"
    run systemctl --user daemon-reload
    run systemctl --user enable --now "$UNIT_NAME"
    echo "Installed. Check it with: bash $0 --status   (the first screen appears within a few seconds)"
    ;;
  uninstall)
    need_systemctl
    if [ "$DRY" = 1 ] || [ -f "$UNIT_DIR/$UNIT_NAME" ]; then
      run systemctl --user disable --now "$UNIT_NAME"
      run rm -f "$UNIT_DIR/$UNIT_NAME"
      run systemctl --user daemon-reload
      echo "Removed. The stock menu is back after you press button 2 once. A running mission and the stack were not touched."
    else
      echo "Not installed ($UNIT_DIR/$UNIT_NAME does not exist), nothing to do"
    fi
    ;;
  status)
    need_systemctl
    echo "unit file: $( [ -f "$UNIT_DIR/$UNIT_NAME" ] && echo "$UNIT_DIR/$UNIT_NAME" || echo '(not installed)' )"
    echo "enabled:   $(systemctl --user is-enabled "$UNIT_NAME" 2>&1)"
    echo "active:    $(systemctl --user is-active "$UNIT_NAME" 2>&1)"
    echo "--- systemctl status"
    systemctl --user status "$UNIT_NAME" --no-pager -n 10 2>&1 || true
    echo "--- last lines of $MENU_LOG"
    tail -n 10 "$MENU_LOG" 2>/dev/null || echo "(no menu.log yet)"
    ;;
esac
