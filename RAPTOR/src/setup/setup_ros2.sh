#!/usr/bin/env bash
# Install ROS 2 Jazzy on the Orin NX (Ubuntu 24.04 / JetPack 7.2).
#
# Runs ON THE JETSON (uses passwordless sudo):   bash setup_ros2.sh
#
# Why Jazzy and not Humble: Humble targets Ubuntu 22.04 and has no binaries for
# 24.04, which is what JetPack 7 ships. See docs/11-jetson-platform-setup.md.
#
# Network: the board has no Wi-Fi and reaches the internet through the laptop.
# This script uses a direct connection if one works, otherwise the laptop proxy
# tunnelled to 127.0.0.1:3128 (start it with src/tools/jetson_internet.sh).
# Only in the proxy case is ../system/etc/apt/apt.conf.d/99proxy installed - and
# while that file exists, apt ONLY works with the tunnel up. Remove it once the
# board has a direct route:   sudo rm /etc/apt/apt.conf.d/99proxy
#
# The ROS repository is added over http:// rather than https:// because this
# network intercepts TLS to packages.ros.org (curl: SEC_E_WRONG_PRINCIPAL). That
# is not a weakening: apt verifies every package against the repository's GPG
# signature regardless of transport.
set -uo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PROXY_CONF_SRC="$HERE/../system/etc/apt/apt.conf.d/99proxy"
PROXY="http://127.0.0.1:3128"
DISTRO="jazzy"
PROBE="http://packages.ros.org/ros2/ubuntu/dists/noble/Release"

echo "=== 1. network route ==="
CURL_PROXY=()
if curl -s -m 15 -o /dev/null "$PROBE"; then
    echo "direct internet works - no proxy needed"
elif curl -s -m 15 -x "$PROXY" -o /dev/null "$PROBE"; then
    echo "using the laptop proxy on $PROXY"
    sudo -n install -m 0644 "$PROXY_CONF_SRC" /etc/apt/apt.conf.d/99proxy
    echo "installed /etc/apt/apt.conf.d/99proxy (remove it once the board has direct internet)"
    CURL_PROXY=(-x "$PROXY")
else
    echo "ERROR: packages.ros.org is unreachable, directly and through $PROXY." >&2
    echo "  Start the tunnel on the laptop: src/tools/jetson_internet.sh" >&2
    echo "  Nothing has been changed." >&2
    exit 1
fi

echo "=== 2. universe repository ==="
sudo -n apt-get update -qq || true
sudo -n apt-get install -y -qq software-properties-common curl gnupg
sudo -n add-apt-repository -y universe

echo "=== 3. ROS 2 signing key and source list ==="
sudo -n install -d -m 0755 /etc/apt/keyrings
curl -fsSL "${CURL_PROXY[@]}" \
    https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    | sudo -n gpg --dearmor --yes -o /etc/apt/keyrings/ros-archive-keyring.gpg
sudo -n chmod 0644 /etc/apt/keyrings/ros-archive-keyring.gpg
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main" \
    | sudo -n tee /etc/apt/sources.list.d/ros2.list >/dev/null

echo "=== 4. apt update ==="
sudo -n apt-get update

echo "=== 5. install ros-$DISTRO-ros-base ==="
# ros-base, not desktop: the flight computer is headless; rviz belongs on the
# ground station. vision_msgs carries Detection2DArray (docs/04), colcon builds
# the raptor_msgs workspace.
sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y \
    "ros-$DISTRO-ros-base" "ros-$DISTRO-vision-msgs" python3-colcon-common-extensions

echo "=== 6. verify ==="
set +u
# shellcheck disable=SC1090
. "/opt/ros/$DISTRO/setup.bash"
set -u
echo "ROS_DISTRO=${ROS_DISTRO:-unset}"
echo "packages: $(ros2 pkg list 2>/dev/null | wc -l)"
echo
echo "Functional check (two shells):"
echo "  source /opt/ros/$DISTRO/setup.bash && ros2 topic pub /t std_msgs/msg/String '{data: ok}'"
echo "  source /opt/ros/$DISTRO/setup.bash && ros2 topic echo --once /t"
echo "Do not source ROS in ~/.bashrc alongside ~/raptor-venv without testing the"
echo "combination - see docs/11 ('One trap specific to this board')."
