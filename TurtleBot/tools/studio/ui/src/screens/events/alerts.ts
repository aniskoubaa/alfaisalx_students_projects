/** Pure helpers for alerts: merge, filter, unread count, wording. */
import type { Alert, AlertSeverity } from '../../api';

export const SEVERITIES: readonly AlertSeverity[] = ['critical', 'warn', 'info'] as const;
export const MAX_ALERTS_KEPT = 500;

export const SEVERITY_WORD: Record<AlertSeverity, string> = {
  critical: 'Critical',
  warn: 'Warning',
  info: 'Info',
};

/** Union by id, sorted by id (oldest first), newest `cap` kept. Does not change its inputs. */
export function mergeAlerts(
  existing: readonly Alert[],
  incoming: readonly Alert[],
  cap = MAX_ALERTS_KEPT,
): Alert[] {
  const byId = new Map<number, Alert>();
  for (const a of existing) byId.set(a.id, a);
  for (const a of incoming) byId.set(a.id, a);
  const all = [...byId.values()].sort((a, b) => a.id - b.id);
  return all.length > cap ? all.slice(all.length - cap) : all;
}

/** Keep the alerts whose severity is in `show`. Newest first when `newestFirst`. */
export function filterAlerts(
  alerts: readonly Alert[],
  show: ReadonlySet<AlertSeverity>,
  newestFirst = true,
): Alert[] {
  const out = alerts.filter((a) => show.has(a.severity));
  return newestFirst ? out.reverse() : out;
}

export function countBySeverity(alerts: readonly Alert[]): Record<AlertSeverity, number> {
  const c: Record<AlertSeverity, number> = { critical: 0, warn: 0, info: 0 };
  for (const a of alerts) c[a.severity]++;
  return c;
}

/** Warnings and critical alerts newer than the last one the person has seen. Info is not counted. */
export function unreadCount(alerts: readonly Alert[], seenId: number): number {
  let n = 0;
  for (const a of alerts) if (a.id > seenId && a.severity !== 'info') n++;
  return n;
}

export const latestId = (alerts: readonly Alert[]): number =>
  alerts.reduce((m, a) => Math.max(m, a.id), 0);

/** Critical alerts also raise a toast, once. */
export const needsToast = (a: Alert): boolean => a.severity === 'critical';

/** HH:MM:SS local time from epoch seconds. */
export function fmtAlertTime(t: number): string {
  return new Date(t * 1000).toTimeString().slice(0, 8);
}

export const toneOf = (s: AlertSeverity): 'bad' | 'warn' | 'info' =>
  s === 'critical' ? 'bad' : s === 'warn' ? 'warn' : 'info';
