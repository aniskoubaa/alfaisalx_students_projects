/**
 * Calls and answer shapes for the 2.0 live features (scan, pose, teleop, journal, limits).
 * Kept apart from api/types.ts and api/client.ts so the screens that use them stay self-contained.
 */
import { api } from './index';
import type { ApiResult } from './types';

export interface ArmAnswer {
  armed: boolean;
  max_linear?: number;
  max_angular?: number;
  watchdog_s?: number;
  idle_s?: number;
  was_armed?: boolean;
}

export interface TeleopAnswer {
  armed?: boolean;
  /** The values the bridge really published after clamping. */
  vx?: number;
  wz?: number;
  seq?: number;
  ignored?: boolean;
}

export interface LimitsAnswer {
  linear: number;
  angular: number;
  max_linear: number;
  max_angular: number;
}

export interface JournalAnswer {
  unit?: string;
  requested?: number;
  since?: string | null;
  grep?: string | null;
  count?: number;
  lines?: string[];
  fake?: boolean;
  permission?: boolean;
}

/** Units the backend accepts (the allow-list lives in the bridge). */
export const JOURNAL_UNITS = [
  { id: 'turtlebot4.service', label: 'TurtleBot 4 (turtlebot4.service)' },
  { id: 'NetworkManager.service', label: 'Network (NetworkManager.service)' },
  { id: 'ssh.service', label: 'Remote login (ssh.service)' },
  { id: 'systemd-timesyncd.service', label: 'Clock sync (systemd-timesyncd.service)' },
  { id: 'chrony.service', label: 'Clock sync (chrony.service)' },
] as const;

export const JOURNAL_SINCE = [
  { id: '', label: 'Any time' },
  { id: '10 min ago', label: 'Last 10 minutes' },
  { id: '1 hour ago', label: 'Last hour' },
  { id: '6 hours ago', label: 'Last 6 hours' },
  { id: '1 day ago', label: 'Last day' },
  { id: 'boot', label: 'Since the robot started' },
] as const;

export const JOURNAL_LINES = [50, 100, 300, 500, 1000, 2000] as const;

const bridge = <T>(body: Record<string, unknown>, timeoutMs: number): Promise<ApiResult<T>> =>
  api().post<T>('/api/bridge', body, { timeoutMs });

export const scanOn = (hz = 4, maxPoints = 360) =>
  bridge({ cmd: 'scan_on', hz, max_points: maxPoints }, 8000);
export const scanOff = () => bridge({ cmd: 'scan_off' }, 8000);
export const poseOn = (hz = 10) => bridge({ cmd: 'pose_on', hz }, 8000);
export const poseOff = () => bridge({ cmd: 'pose_off' }, 8000);

export const teleopArm = (on: boolean, reason?: string) =>
  bridge<ArmAnswer>({ cmd: 'teleop_arm', on, ...(reason ? { reason } : {}) }, 8000);

export const teleopSend = (vx: number, wz: number, seq: number) =>
  bridge<TeleopAnswer>({ cmd: 'teleop', vx, wz, seq }, 2000);

export const getTeleopLimits = () => api().get<LimitsAnswer>('/api/teleop_limits');
export const putTeleopLimits = (linear: number, angular: number) =>
  api().post<LimitsAnswer>('/api/teleop_limits', { linear, angular });

export const fetchJournal = (args: { unit: string; lines: number; since: string }) =>
  bridge<JournalAnswer>(
    {
      cmd: 'journal',
      unit: args.unit,
      lines: args.lines,
      ...(args.since ? { since: args.since } : {}),
    },
    20_000,
  );
