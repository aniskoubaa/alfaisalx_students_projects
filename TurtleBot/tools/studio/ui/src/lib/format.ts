const DASH = '–';

/** A number with fixed decimals, or an en dash when the value is missing. */
export function fmtNum(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined || Number.isNaN(v) ? DASH : v.toFixed(digits);
}

export function fmtUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return DASH;
  const s = Math.floor(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return (d ? d + 'd ' : '') + (h || d ? h + 'h ' : '') + m + 'm';
}

export function fmtSize(n: number | null | undefined): string {
  if (n === null || n === undefined) return DASH;
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(1) + ' MB';
}

/** HH:MM:SS in local time. */
export function fmtTime(d: Date): string {
  return d.toTimeString().slice(0, 8);
}

/** HH:MM in local time from epoch seconds. */
export function fmtClock(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toTimeString().slice(0, 5);
}

export const MINUS = '−';

export function signed(v: number, digits: number): string {
  return (v < 0 ? MINUS : '') + Math.abs(v).toFixed(digits);
}
