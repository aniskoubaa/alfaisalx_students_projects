#!/usr/bin/env bash
# Start TurtleBot Studio on macOS or Linux: bash start-studio.sh  (needs Python 3.10 or newer)
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "TurtleBot Studio needs Python 3.10 or newer (python3 was not found)." >&2
  exit 1
fi
exec python3 studio.py "$@"
