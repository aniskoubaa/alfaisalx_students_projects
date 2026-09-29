#!/usr/bin/env bash
# Install the RAPTOR clock keeper, so the board never boots into 1970.
#
# Runs ON THE JETSON, as root:   sudo bash install_clock_keeper.sh
#
# The problem it solves: this board has no RTC backup battery. After a full
# power-off the PMIC real-time clock (rtc0) restarts from zero, and the kernel
# copies it into the system clock when its driver registers - about 11 s into
# boot, after ordinary services have run. The result is a 1970 clock, which
# silently corrupts every rosbag timestamp and geolocation fix.
#
# What gets installed (all from ../system/, mirrored to the same paths):
#   /usr/local/sbin/raptor-clock-keeper                 load | save | sync
#   /etc/systemd/system/raptor-clock-keeper.service      restore early in boot
#   /etc/systemd/system/raptor-clock-keeper-rtc.service  restore again after rtc0
#   /etc/udev/rules.d/90-raptor-clock-keeper.rules       ...triggered by this rule
#   /etc/systemd/system/raptor-clock-keeper-save.{service,timer}
#                                                        check + persist every 10 min
#
# It keeps a monotonic time *floor*, not accurate time. NTP (when networked) or
# the flight controller's GPS time still has to provide the real thing.
set -uo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SYS="$HERE/../system"

if [ "$(id -u)" -ne 0 ]; then echo "run with sudo" >&2; exit 1; fi

install -m 0755 "$SYS/usr/local/sbin/raptor-clock-keeper" /usr/local/sbin/raptor-clock-keeper
for unit in raptor-clock-keeper.service raptor-clock-keeper-rtc.service \
            raptor-clock-keeper-save.service raptor-clock-keeper-save.timer; do
    install -m 0644 "$SYS/etc/systemd/system/$unit" "/etc/systemd/system/$unit"
done
install -m 0644 "$SYS/etc/udev/rules.d/90-raptor-clock-keeper.rules" \
    /etc/udev/rules.d/90-raptor-clock-keeper.rules

systemctl daemon-reload
udevadm control --reload
systemctl enable raptor-clock-keeper.service raptor-clock-keeper-save.timer
systemctl start raptor-clock-keeper-save.timer

echo "installed. Current state:"
/usr/local/sbin/raptor-clock-keeper load
if [ "$(date -u +%Y)" -lt 2026 ]; then
    echo
    echo "The clock is still wrong and there is no saved floor yet. Set it once from"
    echo "the laptop, then save it:"
    echo "  ssh alfaisal-x-nx@100.100.100.1 \"sudo date -u -s '\$(date -u +'%Y-%m-%d %H:%M:%S')'\""
    echo "  ssh alfaisal-x-nx@100.100.100.1 'sudo hwclock -w && sudo raptor-clock-keeper save'"
else
    /usr/local/sbin/raptor-clock-keeper save
    hwclock -w 2>/dev/null || true
    echo "floor saved: $(cat /var/lib/raptor-clock-keeper/timestamp)"
fi
