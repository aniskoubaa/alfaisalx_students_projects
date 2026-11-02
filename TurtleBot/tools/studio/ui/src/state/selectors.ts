import type { Run, StudioState } from './store';

export const STALE_AFTER_MS = 3000;

export const isConnected = (s: StudioState): boolean => s.conn.state === 'connected';

/** True while the e-stop is latched, or was just pressed here and Studio has not confirmed yet. */
export const isEstopOn = (s: StudioState): boolean => s.estopLocal || s.status?.estop?.on === true;

export const isDocked = (s: StudioState): boolean | null => s.status?.dock?.is_docked ?? null;

/** Newest first. */
export const runList = (s: StudioState): Run[] =>
  Object.values(s.runs).sort((a, b) => b.started - a.started);

export const anyRunAlive = (s: StudioState): boolean => Object.values(s.runs).some((r) => r.alive);

export const aliveRunsOf = (s: StudioState, name: string): Run[] =>
  Object.values(s.runs).filter((r) => r.alive && r.name === name);

/** Values on screen are old when no snapshot arrived for 3 s, or the robot is not connected. */
export function isStale(s: StudioState, now: number): boolean {
  if (s.conn.state !== 'connected') return true;
  if (!s.statusAt) return true;
  return now - s.statusAt > STALE_AFTER_MS;
}

export const remoteDir = (s: StudioState): string => s.settings.remote_dir || '~/robot_code';

export const lowBattery = (s: StudioState): boolean => {
  const p = s.status?.battery?.percent;
  return p !== null && p !== undefined && p < 20;
};
