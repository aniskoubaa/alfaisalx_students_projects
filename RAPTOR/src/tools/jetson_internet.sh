#!/usr/bin/env bash
# Give the Jetson internet access through this laptop's Wi-Fi - one command.
#
# Runs ON THE LAPTOP, in Git Bash. Keep the window open; Ctrl+C stops it.
#
#   ./jetson_internet.sh
#   JETSON=user@host KEY=~/.ssh/other_key ./jetson_internet.sh
#
# Why this is needed at all: the Jetson has no Wi-Fi hardware. It hangs off the
# laptop on a point-to-point Ethernet cable (laptop 100.100.100.2, board
# 100.100.100.1) with no route beyond it.
#
# How it works:
#   1. starts laptop_proxy.py on the laptop's loopback, port 3128 (if not running)
#   2. opens an SSH reverse tunnel, so the Jetson's own 127.0.0.1:3128 leads to
#      that proxy - outbound from the laptop, so no firewall exception needed
#   3. proves it works by fetching the ROS repository index from the Jetson
# apt on the board uses it via /etc/apt/apt.conf.d/99proxy; pip and curl need
# `-x http://127.0.0.1:3128` or `export https_proxy=http://127.0.0.1:3128`.
#
# This is a stop-gap. The access lasts only while this window is open. A
# permanent route (NAT on the laptop) is described in docs/11-jetson-platform-setup.md.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
JETSON="${JETSON:-alfaisal-x-nx@100.100.100.1}"
KEY="${KEY:-$HOME/.ssh/claude_nx}"
PORT=3128
PROBE="http://packages.ros.org/ros2/ubuntu/dists/noble/Release"
PROXY_PID=""

cleanup() {
    if [ -n "$PROXY_PID" ]; then
        kill "$PROXY_PID" 2>/dev/null && echo "stopped the proxy (pid $PROXY_PID)"
    fi
}
trap cleanup EXIT INT TERM

echo "=== 1. proxy on the laptop ==="
if netstat -ano 2>/dev/null | grep -qE "127\.0\.0\.1:$PORT .*LISTENING"; then
    echo "already listening on 127.0.0.1:$PORT"
else
    python "$HERE/laptop_proxy.py" > "${TMPDIR:-/tmp}/raptor_proxy.log" 2>&1 &
    PROXY_PID=$!
    sleep 2
    if ! kill -0 "$PROXY_PID" 2>/dev/null; then
        echo "ERROR: the proxy failed to start:" >&2
        cat "${TMPDIR:-/tmp}/raptor_proxy.log" >&2
        exit 1
    fi
    echo "started (pid $PROXY_PID)"
fi

echo "=== 2. reach the Jetson ==="
# An SSH check, not ping: 100.100.100.x sits inside this ISP's carrier-grade NAT
# range, so with the cable out a ping can be answered by an unrelated internet host.
if ! ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=8 "$JETSON" true 2>/dev/null; then
    echo "ERROR: cannot SSH to $JETSON - check the cable and that the board is on." >&2
    exit 1
fi
echo "reachable"

echo "=== 3. tunnel (Ctrl+C to stop) ==="
ssh -i "$KEY" -o BatchMode=yes \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -R "$PORT:127.0.0.1:$PORT" "$JETSON" \
    "code=\$(curl -s -m 20 -x http://127.0.0.1:$PORT -o /dev/null -w '%{http_code}' $PROBE); \
     if [ \"\$code\" = 200 ]; then echo 'Jetson internet: UP (ROS repository reachable)'; \
     else echo \"Jetson internet: FAILED (HTTP \$code)\"; fi; \
     echo 'Leave this window open while the Jetson needs internet.'; \
     exec sleep infinity"
