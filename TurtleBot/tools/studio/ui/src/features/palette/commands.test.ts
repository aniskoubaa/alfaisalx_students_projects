import { describe, expect, it } from 'vitest';
import { initialState } from '../../state/store';
import { buildDiagnostics, filterCommands, scoreCommand } from './commands';

const cmds = [
  { label: 'Go to Overview', keywords: 'home dashboard' },
  { label: 'Go to Logs', keywords: 'journal' },
  { label: 'Discover robots', keywords: 'find search network' },
  { label: 'Run health check', keywords: 'test' },
  { label: 'Toggle theme', keywords: 'dark light colour' },
];

describe('filterCommands', () => {
  it('returns everything for an empty query, in order', () => {
    expect(filterCommands(cmds, '').map((c) => c.label)).toEqual(cmds.map((c) => c.label));
  });

  it('matches word starts in the label and the keywords', () => {
    expect(filterCommands(cmds, 'journ').map((c) => c.label)).toEqual(['Go to Logs']);
    expect(filterCommands(cmds, 'dark').map((c) => c.label)).toEqual(['Toggle theme']);
    expect(filterCommands(cmds, 'health').map((c) => c.label)).toEqual(['Run health check']);
  });

  it('requires every word of the query', () => {
    expect(filterCommands(cmds, 'go logs').map((c) => c.label)).toEqual(['Go to Logs']);
    expect(filterCommands(cmds, 'go zebra')).toEqual([]);
  });

  it('ranks a label that starts with the query first', () => {
    const r = filterCommands(cmds, 'dis');
    expect(r[0]?.label).toBe('Discover robots');
  });

  it('does not offer any motion command', () => {
    for (const q of ['drive', 'move', 'undock', 'dock']) {
      expect(filterCommands(cmds, q)).toEqual([]);
    }
    expect(scoreCommand({ label: 'Go to Overview' }, 'zzz')).toBe(0);
  });
});

describe('buildDiagnostics', () => {
  it('lists the state without any token', () => {
    const s = initialState();
    s.conn = { ev: 'conn', state: 'connected', host: 'turtlebot4', via: 'cable' };
    s.status = { ev: 'status', battery: { percent: 76 }, dock: { is_docked: false } };
    const text = buildDiagnostics(s, new Date('2026-10-30T00:00:00Z'));
    expect(text).toContain('Robot connection: connected (turtlebot4, Ethernet cable)');
    expect(text).toContain('Battery: 76 %');
    expect(text).toContain('Docked: false');
    expect(text.toLowerCase()).not.toContain('token');
  });
});
