/**
 * Pure helpers for the Charts screen: the in-memory history, live appends from status events,
 * time windows, and the chart definitions.
 */
import type { HistoryAnswer, StatusEvent } from '../../api';

export const SERIES_KEYS = [
  'battery_pct',
  'voltage',
  'current_a',
  'speed',
  'odom_hz',
  'scan_hz',
  'cpu_pct',
  'temp_c',
  'wifi_dbm',
] as const;
export type SeriesKey = (typeof SERIES_KEYS)[number];
export type Sample = Record<SeriesKey, number | null>;

/** The backend keeps 30 minutes at 1 Hz. */
export const MAX_SECONDS = 1800;
export const WINDOWS = [5, 15, 30] as const;
export type WindowMinutes = (typeof WINDOWS)[number];

export interface HistoryBuffer {
  /** Epoch seconds, ascending. */
  t: number[];
  series: Record<SeriesKey, Array<number | null>>;
}

export function emptyBuffer(): HistoryBuffer {
  const series = {} as HistoryBuffer['series'];
  for (const k of SERIES_KEYS) series[k] = [];
  return { t: [], series };
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** One row of values from a status snapshot. Speed is the size of the forward speed. */
export function sampleFromStatus(ev: StatusEvent): Sample {
  const vx = num(ev.odom?.vx);
  return {
    battery_pct: num(ev.battery?.percent),
    voltage: num(ev.battery?.voltage),
    current_a: num(ev.battery?.current_a),
    speed: vx === null ? null : Math.abs(vx),
    odom_hz: num(ev.odom?.rate_hz),
    scan_hz: num(ev.scan?.rate_hz),
    cpu_pct: num(ev.system?.cpu_pct),
    temp_c: num(ev.system?.temp_c),
    wifi_dbm: num(ev.net?.signal_dbm),
  };
}

/**
 * Add one sample at time `t` (epoch seconds). Ignored when it is not newer than the last one by
 * at least `minGap`. Drops samples older than `maxSeconds`. Returns true when added.
 */
export function appendSample(
  buf: HistoryBuffer,
  t: number,
  sample: Sample,
  maxSeconds = MAX_SECONDS,
  minGap = 0.5,
): boolean {
  const last = buf.t[buf.t.length - 1];
  if (last !== undefined && t - last < minGap) return false;
  buf.t.push(t);
  for (const k of SERIES_KEYS) buf.series[k].push(sample[k]);
  const cutoff = t - maxSeconds;
  let drop = 0;
  while (drop < buf.t.length && (buf.t[drop] as number) < cutoff) drop++;
  if (drop > 0) {
    buf.t.splice(0, drop);
    for (const k of SERIES_KEYS) buf.series[k].splice(0, drop);
  }
  return true;
}

export function fromAnswer(a: HistoryAnswer): HistoryBuffer {
  const buf = emptyBuffer();
  if (!Array.isArray(a.t) || !a.series) return buf;
  const n = a.t.length;
  for (let i = 0; i < n; i++) {
    buf.t.push(a.t[i] as number);
    for (const k of SERIES_KEYS) {
      const col = a.series[k];
      buf.series[k].push(col ? (num(col[i]) ?? null) : null);
    }
  }
  return buf;
}

/** Union of two buffers by whole second; `b` wins where both have the second. */
export function mergeBuffers(a: HistoryBuffer, b: HistoryBuffer): HistoryBuffer {
  const rows = new Map<number, Sample>();
  const put = (buf: HistoryBuffer) => {
    for (let i = 0; i < buf.t.length; i++) {
      const row = {} as Sample;
      for (const k of SERIES_KEYS) row[k] = buf.series[k][i] ?? null;
      rows.set(Math.round(buf.t[i] as number), row);
    }
  };
  put(a);
  put(b);
  const out = emptyBuffer();
  for (const t of [...rows.keys()].sort((x, y) => x - y)) {
    const row = rows.get(t) as Sample;
    out.t.push(t);
    for (const k of SERIES_KEYS) out.series[k].push(row[k]);
  }
  return out;
}

/** First index whose time is at or after `t0` (buf.t is ascending). */
export function firstIndexFrom(times: number[], t0: number): number {
  let lo = 0;
  let hi = times.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((times[mid] as number) < t0) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Data for one chart in uPlot's column layout: [times, series1, series2, ...] for a window. */
export function windowData(
  buf: HistoryBuffer,
  keys: readonly SeriesKey[],
  nowSec: number,
  minutes: number,
): Array<Array<number | null>> {
  const from = firstIndexFrom(buf.t, nowSec - minutes * 60);
  const cols: Array<Array<number | null>> = [buf.t.slice(from)];
  for (const k of keys) cols.push(buf.series[k].slice(from));
  return cols;
}

export function lastValue(buf: HistoryBuffer, key: SeriesKey): number | null {
  const col = buf.series[key];
  for (let i = col.length - 1; i >= Math.max(0, col.length - 5); i--) {
    const v = col[i];
    if (v !== null && v !== undefined) return v;
  }
  return null;
}

/* ---------- chart definitions ---------- */

export interface SeriesDef {
  key: SeriesKey;
  label: string;
  unit: string;
  digits: number;
  /** 'y' (left axis) or 'y2' (right axis). */
  scale: 'y' | 'y2';
  /** Colour token name: signal, green, amber, ink. */
  color: 'signal' | 'green' | 'amber' | 'ink';
  dashed?: boolean;
}

export interface ChartDef {
  id: string;
  title: string;
  /** One sentence under the title. */
  hint?: string;
  series: SeriesDef[];
  /** Smallest range each scale must cover, as [min, max] per scale. */
  range: Partial<Record<'y' | 'y2', [number, number]>>;
  /** True when the range is exactly this and never grows. */
  fixed?: boolean;
}

export const CHARTS: ChartDef[] = [
  {
    id: 'battery',
    title: 'Battery',
    series: [
      { key: 'battery_pct', label: 'Charge', unit: '%', digits: 0, scale: 'y', color: 'green' },
    ],
    range: { y: [0, 100] },
    fixed: true,
  },
  {
    id: 'power',
    title: 'Voltage and current',
    series: [
      { key: 'voltage', label: 'Voltage', unit: 'V', digits: 2, scale: 'y', color: 'signal' },
      {
        key: 'current_a',
        label: 'Current',
        unit: 'A',
        digits: 2,
        scale: 'y2',
        color: 'amber',
        dashed: true,
      },
    ],
    range: { y: [12, 17], y2: [-1, 2] },
  },
  {
    id: 'speed',
    title: 'Speed',
    series: [{ key: 'speed', label: 'Speed', unit: 'm/s', digits: 2, scale: 'y', color: 'signal' }],
    range: { y: [0, 0.3] },
  },
  {
    id: 'rates',
    title: 'Message rates',
    hint: 'Odometry drops to 0 for up to 2 s while the base is busy driving (TB-25). That is a known base issue, not a Studio fault.',
    series: [
      { key: 'odom_hz', label: 'Odometry', unit: 'Hz', digits: 1, scale: 'y', color: 'signal' },
      {
        key: 'scan_hz',
        label: 'Lidar',
        unit: 'Hz',
        digits: 1,
        scale: 'y',
        color: 'green',
        dashed: true,
      },
    ],
    range: { y: [0, 25] },
  },
  {
    id: 'system',
    title: 'CPU and temperature',
    series: [
      { key: 'cpu_pct', label: 'CPU', unit: '%', digits: 0, scale: 'y', color: 'signal' },
      {
        key: 'temp_c',
        label: 'Temperature',
        unit: '°C',
        digits: 1,
        scale: 'y2',
        color: 'amber',
        dashed: true,
      },
    ],
    range: { y: [0, 100], y2: [30, 85] },
  },
  {
    id: 'wifi',
    title: 'Wi-Fi signal',
    hint: 'Closer to 0 dBm is stronger. Below about −75 dBm the link gets unreliable.',
    series: [
      { key: 'wifi_dbm', label: 'Signal', unit: 'dBm', digits: 0, scale: 'y', color: 'signal' },
    ],
    range: { y: [-95, -30] },
  },
];

/** The scale range to use: the default range widened to include the data (unless fixed). */
export function rangeFor(
  def: [number, number],
  dataMin: number | null,
  dataMax: number | null,
  fixed = false,
): [number, number] {
  if (fixed || dataMin === null || dataMax === null) return def;
  const lo = Math.min(def[0], dataMin);
  const hi = Math.max(def[1], dataMax);
  const pad = (hi - lo) * 0.04;
  return [lo - (lo < def[0] ? pad : 0), hi + (hi > def[1] ? pad : 0)];
}

export function fmtValue(
  v: number | null | undefined,
  s: Pick<SeriesDef, 'digits' | 'unit'>,
): string {
  if (v === null || v === undefined) return '–';
  const text = Math.abs(v).toFixed(s.digits);
  return (v < 0 ? '−' : '') + text + ' ' + s.unit;
}
