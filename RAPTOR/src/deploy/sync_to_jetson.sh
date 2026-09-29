#!/usr/bin/env bash
# Copy this repository's code to the Jetson, so the board runs what git holds.
#
# Runs ON THE LAPTOP, in Git Bash:
#   ./sync_to_jetson.sh
#   JETSON=user@host KEY=~/.ssh/other_key ./sync_to_jetson.sh
#
# The repository is the source of truth. On the board, ~/raptor/src is a MIRROR
# of this repo's src/ - edit here, commit, sync; do not edit on the board, or the
# next sync will replace your change. The previous mirror is kept once, at
# ~/raptor/src.prev, in case something needs recovering.
#
# Only code is copied. Weights, datasets and results stay where they are on the
# board (~/raptor-models, ~/raptor-data, ~/raptor-vlm, ~/raptor-deploy,
# ~/raptor-results) - they are large, regenerable, and git-ignored.
#
# Line endings are normalised to LF on arrival: a script checked out on Windows
# with CRLF fails on the board with "$'\r': command not found".
#
# The copy lands in ~/raptor/src.new first and is swapped in only once it is
# complete, so a dropped cable mid-copy leaves the old mirror working. Laptop-only
# clutter (analysis/node_modules, __pycache__) is not sent.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/.." && pwd)"               # the repository's src/
JETSON="${JETSON:-alfaisal-x-nx@100.100.100.1}"
KEY="${KEY:-$HOME/.ssh/claude_nx}"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=8)

echo "syncing $SRC -> $JETSON:~/raptor/src"
"${SSH[@]}" "$JETSON" 'rm -rf ~/raptor/src.new && mkdir -p ~/raptor/src.new'
tar -C "$SRC" --exclude=node_modules --exclude=__pycache__ -cf - . \
    | "${SSH[@]}" "$JETSON" 'tar -C ~/raptor/src.new -xf -'
"${SSH[@]}" "$JETSON" 'cd ~/raptor && rm -rf src.prev && { [ -d src ] && mv src src.prev || true; } && mv src.new src'

"${SSH[@]}" "$JETSON" '
    cd ~/raptor/src &&
    find . -type f ! -name "*.bat" -exec sed -i "s/\r$//" {} + &&
    find . -type f -name "*.sh" -exec chmod +x {} + &&
    chmod +x system/usr/local/sbin/* demo/raptor_live_demo.py 2>/dev/null
    echo "files on the board: $(find . -type f | wc -l)"'

echo
echo "done. Code lives at ~/raptor/src on the board. Note that this does NOT"
echo "reinstall system files - run the relevant src/setup/ script for those."
