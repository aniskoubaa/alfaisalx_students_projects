#!/usr/bin/env bash
# Installs the TurtleBot Studio program for the current user on Linux. Add-only: it copies one file and writes
# one launcher entry; it needs no administrator rights and changes nothing else.
#   bash install-linux.sh [path-to-TurtleBotStudio]      (default: the file next to this script)
set -eu

SRC="${1:-$(cd "$(dirname "$0")" && pwd)/TurtleBotStudio}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
BIN="$BIN_DIR/turtlebot-studio"
DESKTOP="$APP_DIR/turtlebot-studio.desktop"

if [ ! -f "$SRC" ]; then
  echo "Cannot find the program: $SRC" >&2
  echo "Download TurtleBotStudio next to this script, or pass its path: bash install-linux.sh /path/to/TurtleBotStudio" >&2
  exit 1
fi

mkdir -p "$BIN_DIR" "$APP_DIR"
cp "$SRC" "$BIN"
chmod 755 "$BIN"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=TurtleBot Studio
Comment=Connect to the lab TurtleBot 4, run and edit its programs
Exec=$BIN
Terminal=false
Categories=Development;Education;
EOF

echo "Installed:"
echo "  $BIN"
echo "  $DESKTOP"
echo "Start it from your applications menu (TurtleBot Studio) or run: turtlebot-studio"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Note: $BIN_DIR is not on your PATH, so the command name works only after you add it (the menu entry works anyway)." ;;
esac
echo
echo "To undo (removes exactly these two files; your settings in ~/.config/turtlebot-studio stay):"
echo "  rm \"$BIN\" \"$DESKTOP\""
