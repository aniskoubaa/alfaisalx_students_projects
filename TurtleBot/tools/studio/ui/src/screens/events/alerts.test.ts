import { describe, expect, it } from 'vitest';
import type { Alert, AlertSeverity } from '../../api';
import { initialState, reduceEvent } from '../../state/store';
import {
  countBySeverity,
  filterAlerts,
  latestId,
  mergeAlerts,
  needsToast,
  unreadCount,
} from './alerts';

const mk = (id: number, severity: AlertSeverity = 'info'): Alert => ({
  id,
  t: 1000 + id,
  severity,
  code: 'c' + id,
  text: 'text ' + id,
});

describe('mergeAlerts', () => {
  it('unions by id, sorts oldest first and keeps the newest when capped', () => {
    const a = mergeAlerts([mk(3), mk(1)], [mk(2), mk(3, 'warn')]);
    expect(a.map((x) => x.id)).toEqual([1, 2, 3]);
    expect(a[2]?.severity).toBe('warn'); // incoming wins
    expect(mergeAlerts([mk(1), mk(2), mk(3)], [], 2).map((x) => x.id)).toEqual([2, 3]);
  });

  it('does not change its inputs', () => {
    const base = [mk(2)];
    mergeAlerts(base, [mk(1)]);
    expect(base.map((x) => x.id)).toEqual([2]);
  });
});

describe('filter and count', () => {
  const list = [mk(1, 'info'), mk(2, 'warn'), mk(3, 'critical'), mk(4, 'warn')];

  it('filters by severity, newest first', () => {
    expect(filterAlerts(list, new Set<AlertSeverity>(['warn'])).map((a) => a.id)).toEqual([4, 2]);
    expect(
      filterAlerts(list, new Set<AlertSeverity>(['critical', 'info']), false).map((a) => a.id),
    ).toEqual([1, 3]);
    expect(filterAlerts(list, new Set<AlertSeverity>())).toEqual([]);
  });

  it('counts per severity', () => {
    expect(countBySeverity(list)).toEqual({ critical: 1, warn: 2, info: 1 });
  });
});

describe('unread and toast', () => {
  it('counts only warnings and critical alerts newer than the last seen id', () => {
    const list = [mk(1, 'warn'), mk(2, 'info'), mk(3, 'critical'), mk(4, 'warn')];
    expect(unreadCount(list, 0)).toBe(3);
    expect(unreadCount(list, 3)).toBe(1);
    expect(unreadCount(list, 4)).toBe(0);
    expect(latestId(list)).toBe(4);
    expect(latestId([])).toBe(0);
  });

  it('raises a toast for critical alerts only', () => {
    expect(needsToast(mk(1, 'critical'))).toBe(true);
    expect(needsToast(mk(1, 'warn'))).toBe(false);
  });
});

describe('store alert reducer', () => {
  it('appends a live alert once and ignores a repeated id', () => {
    const s0 = initialState();
    const ev = { ev: 'alert' as const, ...mk(7, 'critical') };
    const p1 = reduceEvent(s0, ev, 0);
    expect(p1.alerts?.map((a) => a.id)).toEqual([7]);
    const p2 = reduceEvent({ ...s0, ...p1 }, ev, 1);
    expect(p2).toEqual({});
  });
});
