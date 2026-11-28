# Raw test logs

Unedited output from runs on the real robot, kept as evidence. Do not edit them. The table of what each file records is in [tests/README.md, Logs](../README.md#logs-logs).

| Files | What they are | Runs on (laptop / robot / CI) |
|---|---|---|
| `2026-10-04_*.log` | Undock, shape programs and the odometry probe (lidar and motion check) | recorded on the robot |
| `2026-10-24_timing_*.jsonl.gz`, `*_joins.log`, `2026-10-24_idle_timing_summary.json` | Timing recordings from `tools/timing/record_timing.py` (gzip; read with `analyze_timing.py`) | recorded on the robot, analysed on a laptop |
| `2026-10-24_tb25_motion_starts_runs.log`, `2026-10-24_studio_motion_runs.log` | Output of supervised motion runs | recorded on the robot |
| `2026-10-24_wifi_powersave.log`, `2026-10-24_wifi_journal_keyevents.log` | Read-only Wi-Fi checks | recorded on the robot |

Time zone: times inside the logs are robot time, EDT (laptop UTC+3 is robot time plus 7 hours). On 2026-10-24 the robot clock read 2024-10-28 in some logs, so the timing tools use seconds since the start of the recording. The three evening Wi-Fi recordings were made with a correct robot clock.

Cited from: the timing, TB-25 and Studio run logs are cited in [../../MAINTENANCE.md](../../MAINTENANCE.md) and [../../ROADMAP.md](../../ROADMAP.md) (TB-25); the other files are described in [../README.md](../README.md).
