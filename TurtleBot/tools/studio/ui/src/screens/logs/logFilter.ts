/** Pure helpers for the Logs screen: classify, filter, window a long list, name the saved file. */

export type LineLevel = 'error' | 'warn' | 'info';

export interface LogLine {
  /** 1-based number in the fetched list. */
  n: number;
  text: string;
  level: LineLevel;
}

const ERROR_RE =
  /\b(error|err|fail(?:ed|ure|s)?|fatal|critical|crit|panic|exception|traceback|denied|segfault|abort(?:ed)?)\b/i;
const WARN_RE =
  /\b(warn(?:ing)?|timeout|timed out|retry|retrying|deprecated|stall(?:ed)?|delayed|lost)\b/i;

export function classifyLine(text: string): LineLevel {
  if (ERROR_RE.test(text)) return 'error';
  if (WARN_RE.test(text)) return 'warn';
  return 'info';
}

export function toLogLines(lines: readonly string[]): LogLine[] {
  return lines.map((text, i) => ({ n: i + 1, text, level: classifyLine(text) }));
}

export interface FilterOptions {
  /** Plain text, case-insensitive. Empty shows everything. */
  text: string;
  /** Show only warnings and errors. */
  problemsOnly: boolean;
}

export function filterLogLines(lines: readonly LogLine[], opts: FilterOptions): LogLine[] {
  const needle = opts.text.trim().toLowerCase();
  return lines.filter((l) => {
    if (opts.problemsOnly && l.level === 'info') return false;
    return needle === '' || l.text.toLowerCase().includes(needle);
  });
}

export function countLevels(lines: readonly LogLine[]): { error: number; warn: number } {
  let error = 0;
  let warn = 0;
  for (const l of lines) {
    if (l.level === 'error') error++;
    else if (l.level === 'warn') warn++;
  }
  return { error, warn };
}

/** Which rows to render for a scrolled list of fixed-height rows. `end` is exclusive. */
export function visibleRange(
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  total: number,
  overscan = 10,
): { start: number; end: number } {
  if (total <= 0 || rowHeight <= 0) return { start: 0, end: 0 };
  const first = Math.floor(Math.max(0, scrollTop) / rowHeight);
  const count = Math.ceil(Math.max(0, viewportHeight) / rowHeight);
  const start = Math.max(0, first - overscan);
  const end = Math.min(total, first + count + overscan);
  return { start: Math.min(start, total), end: Math.max(end, Math.min(start, total)) };
}

/** The text that Copy and Save use: one line per row, in the order shown. */
export function linesToText(lines: readonly LogLine[]): string {
  return lines.map((l) => l.text).join('\n') + (lines.length ? '\n' : '');
}

/** For example turtlebot4-2026-10-30-0145.log. */
export function logFileName(unit: string, d: Date): string {
  const base = unit.replace(/\.service$/, '').replace(/[^A-Za-z0-9_-]/g, '-');
  const p = (n: number) => String(n).padStart(2, '0');
  return `${base}-${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.log`;
}
