import { describe, expect, it } from 'vitest';
import {
  classifyLine,
  countLevels,
  filterLogLines,
  linesToText,
  logFileName,
  toLogLines,
  visibleRange,
} from './logFilter';

const sample = [
  '2026-10-29T21:32:55+0000 turtlebot4 turtlebot4[1000]: Started turtlebot4.service.',
  '2026-10-29T21:38:55+0000 turtlebot4 turtlebot4[1005]: WARNING: odometry delayed 0.6 s',
  '2026-10-29T21:40:07+0000 turtlebot4 turtlebot4[1006]: ERROR: lidar motor stopped',
  '2026-10-29T21:41:19+0000 turtlebot4 turtlebot4[1007]: wifi: signal -55 dBm',
];

describe('classifyLine', () => {
  it('finds errors and warnings by word, not by substring', () => {
    expect(classifyLine(sample[2] as string)).toBe('error');
    expect(classifyLine(sample[1] as string)).toBe('warn');
    expect(classifyLine(sample[0] as string)).toBe('info');
    expect(classifyLine('terrorist group')).toBe('info');
    expect(classifyLine('Connection failed: no route')).toBe('error');
    expect(classifyLine('request timed out')).toBe('warn');
  });
});

describe('filterLogLines', () => {
  const lines = toLogLines(sample);

  it('numbers lines from 1 in the fetched order', () => {
    expect(lines.map((l) => l.n)).toEqual([1, 2, 3, 4]);
  });

  it('filters by plain text, ignoring case and keeping the original line numbers', () => {
    const r = filterLogLines(lines, { text: 'LIDAR', problemsOnly: false });
    expect(r.map((l) => l.n)).toEqual([3]);
    expect(filterLogLines(lines, { text: '', problemsOnly: false })).toHaveLength(4);
    expect(filterLogLines(lines, { text: '   ', problemsOnly: false })).toHaveLength(4);
  });

  it('treats the text as plain text, not a pattern', () => {
    expect(filterLogLines(lines, { text: '.*', problemsOnly: false })).toHaveLength(0);
    expect(filterLogLines(lines, { text: '[1000]', problemsOnly: false })).toHaveLength(1);
  });

  it('shows only warnings and errors when asked, and combines with the text', () => {
    expect(filterLogLines(lines, { text: '', problemsOnly: true }).map((l) => l.n)).toEqual([2, 3]);
    expect(filterLogLines(lines, { text: 'odometry', problemsOnly: true }).map((l) => l.n)).toEqual(
      [2],
    );
  });

  it('counts levels', () => {
    expect(countLevels(lines)).toEqual({ error: 1, warn: 1 });
  });
});

describe('visibleRange', () => {
  it('returns the rows in view plus an overscan, clipped to the list', () => {
    expect(visibleRange(0, 200, 20, 1000, 5)).toEqual({ start: 0, end: 15 });
    expect(visibleRange(2000, 200, 20, 1000, 5)).toEqual({ start: 95, end: 115 });
    expect(visibleRange(19900, 200, 20, 1000, 5)).toEqual({ start: 990, end: 1000 });
  });

  it('is empty for an empty list', () => {
    expect(visibleRange(0, 200, 20, 0)).toEqual({ start: 0, end: 0 });
  });
});

describe('saving', () => {
  it('joins lines with a final newline', () => {
    expect(linesToText(toLogLines(['a', 'b']))).toBe('a\nb\n');
    expect(linesToText([])).toBe('');
  });

  it('names the file from the unit and the time', () => {
    const d = new Date(2026, 9, 30, 1, 5);
    expect(logFileName('turtlebot4.service', d)).toBe('turtlebot4-2026-10-30-0105.log');
    expect(logFileName('systemd-timesyncd.service', d)).toBe(
      'systemd-timesyncd-2026-10-30-0105.log',
    );
  });
});
