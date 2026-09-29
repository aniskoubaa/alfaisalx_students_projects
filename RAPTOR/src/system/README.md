# system/ — configuration files, exactly as installed on the Jetson

These are not scripts to run. They are the operating-system files RAPTOR installs on
the board, each stored at the **same path it is installed to**, with `system/` as the
root: `system/etc/X11/xorg.conf` is `/etc/X11/xorg.conf` on the board.

Keeping them in git means the board's configuration is reviewable, diffable, and
restorable after a reflash. The scripts in [`../setup/`](../setup/README.md) install
them — do not copy them over by hand unless you know which service to restart.

| File (on the board) | Installed by | What it does |
|---|---|---|
| `/usr/local/sbin/raptor-clock-keeper` | `install_clock_keeper.sh` | Keeps a monotonic time floor: `load` steps the clock forward if it has fallen behind the saved time, `save` records the current time, `sync` does both. |
| `/etc/systemd/system/raptor-clock-keeper.service` | `install_clock_keeper.sh` | Restores the time floor early in boot. |
| `/etc/systemd/system/raptor-clock-keeper-rtc.service` | `install_clock_keeper.sh` | Restores it **again** once the RTC driver has loaded — see below. |
| `/etc/udev/rules.d/90-raptor-clock-keeper.rules` | `install_clock_keeper.sh` | Starts the service above the moment `rtc0` appears. |
| `/etc/systemd/system/raptor-clock-keeper-save.{service,timer}` | `install_clock_keeper.sh` | Every 10 minutes: fix the clock if needed, then save it. |
| `/usr/local/sbin/raptor-x11vnc-start` | `setup_vnc.sh` | Starts x11vnc against the console, reading the X authority from the running Xorg. |
| `/etc/systemd/system/x11vnc.service` | `setup_vnc.sh` | Keeps x11vnc running and restarts it when someone logs in (the X session changes). |
| `/etc/X11/xorg.conf` | `set_headless_display.sh` | Gives the console 1024×768 with no monitor attached (640×480 otherwise). |
| `/etc/apt/apt.conf.d/99proxy` | `setup_ros2.sh`, only when needed | Sends apt through the laptop proxy. **While present, apt only works with the tunnel up** — delete it once the board has direct internet. |

Not here on purpose: `/etc/x11vnc.pass` and the RDP credentials. Secrets are created on
the board by the setup scripts and never committed.

## Why the clock needs three pieces

The board has **no RTC backup battery**. After a full power-off its real-time clock
restarts at zero, i.e. 1970. That silently breaks every rosbag timestamp and every
geolocation fix ([docs/04](../../docs/04-ros2-architecture.md): "One clock").

The obvious fix — restore a saved time early in boot — was tried first and **failed**,
because of this, from the kernel log:

```
[10.14 s] raptor-clock-keeper: clock restored to 2026-09-28 11:31:01
[10.94 s] nvvrs-pseq-rtc: registered as rtc0
[10.95 s] nvvrs-pseq-rtc: setting system clock to 1970-01-01T00:00:26 UTC
```

The PMIC RTC driver is a loadable module that registers ~11 s into boot, and the
kernel (`CONFIG_RTC_HCTOSYS_DEVICE=rtc0`) copies it into the system clock at that
moment — *after* the early restore. Hence the udev rule, which re-applies the floor as
soon as `rtc0` registers. And the first version of the periodic save then recorded
the bad 1970 time over the good one, so `save` is now monotonic: it never moves the
floor backwards, and never records anything before 2026.

Tested by forcing the clock back to 2020, replaying the `rtc0` add event, and
confirming the keeper restored it within seconds.
