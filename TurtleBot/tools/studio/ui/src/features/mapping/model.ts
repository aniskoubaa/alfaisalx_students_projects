/**
 * Pure helpers for the Maps screen: state words, which buttons each state allows, names,
 * the map image <-> world transform, header parsing and number formatting. No React, no DOM.
 */
import type { MapEntry, MapMeta, MappingInfo, MappingState } from '../../api';
import type { Tone } from '../../components/ui';

/* ---------- state words ---------- */

export type MappingStateKey = MappingState | 'unknown';

export const STATE_WORDS: Record<MappingStateKey, string> = {
  idle: 'Not mapping',
  starting: 'Starting mapping…',
  mapping: 'Mapping',
  saving: 'Saving the map…',
  stopping: 'Stopping…',
  error: 'Error',
  unknown: 'Checking the mapping state…',
};

export function stateKey(info: Pick<MappingInfo, 'state'> | null | undefined): MappingStateKey {
  const s = info?.state;
  return s && s in STATE_WORDS ? s : 'unknown';
}

export const stateWord = (info: Pick<MappingInfo, 'state'> | null | undefined): string =>
  STATE_WORDS[stateKey(info)];

const TONES: Record<MappingStateKey, Tone> = {
  idle: 'neutral',
  starting: 'info',
  mapping: 'ok',
  saving: 'info',
  stopping: 'info',
  error: 'bad',
  unknown: 'neutral',
};
export const stateTone = (info: Pick<MappingInfo, 'state'> | null | undefined): Tone =>
  TONES[stateKey(info)];

/** True while the robot is changing state and nothing else should be asked of it. */
export const isBusy = (info: Pick<MappingInfo, 'state'> | null | undefined): boolean => {
  const k = stateKey(info);
  return k === 'starting' || k === 'saving' || k === 'stopping';
};

/* ---------- allowed actions ---------- */

export interface Allowed {
  enabled: boolean;
  /** Why it is off, in words. Empty when enabled. */
  reason: string;
}

export interface AllowedActions {
  start: Allowed;
  save: Allowed;
  stop: Allowed;
  reset: Allowed;
  drive: Allowed;
}

const yes: Allowed = { enabled: true, reason: '' };
const no = (reason: string): Allowed => ({ enabled: false, reason });

export function allowedActions(
  info: MappingInfo | null | undefined,
  connected = true,
): AllowedActions {
  const k = stateKey(info);
  const offline = 'Not connected to the robot.';
  const wait = 'Waiting for the robot to report its mapping state.';

  let start: Allowed;
  if (!connected) start = no(offline);
  else if (k === 'unknown') start = no(wait);
  else if (k !== 'idle')
    start = no(k === 'mapping' ? 'Already mapping.' : 'Wait for the robot to finish first.');
  else if (info?.scripts_ok === false) start = no('The mapping scripts are missing on the robot.');
  else if (info?.other_stack)
    start = no(`A navigation program is running (${info.other_stack}). Stop it first.`);
  else start = yes;

  const save = !connected
    ? no(offline)
    : k === 'mapping'
      ? yes
      : no(k === 'saving' ? 'Already saving.' : 'Start mapping first. There is nothing to save.');

  const stop = !connected
    ? no(offline)
    : k === 'mapping' || k === 'error'
      ? yes
      : no(k === 'idle' ? 'Not mapping.' : 'Wait for the robot to finish first.');

  const reset = !connected ? no(offline) : k === 'error' ? yes : no('There is no error to clear.');

  const drive = !connected
    ? no(offline)
    : isBusy(info)
      ? no('Driving is off while the robot starts, saves or stops mapping.')
      : yes;

  return { start, save, stop, reset, drive };
}

/* ---------- names ---------- */

/** Same rule as the bridge. */
export const MAP_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/;

export type NameCheck = { ok: true } | { ok: false; message: string };

export function validMapName(name: string): NameCheck {
  if (!name) return { ok: false, message: 'Type a name for the map.' };
  if (name.length > 48) return { ok: false, message: 'Use 48 characters or fewer.' };
  if (!/^[A-Za-z0-9]/.test(name))
    return { ok: false, message: 'Start the name with a letter or a digit.' };
  if (!MAP_NAME_RE.test(name))
    return {
      ok: false,
      message: 'Use only letters, digits, hyphens (-) and underscores (_). No spaces.',
    };
  return { ok: true };
}

const p2 = (n: number) => String(n).padStart(2, '0');

/** A default name from the local date and time, for example map-2026-11-12-1430. */
export function suggestName(d: Date = new Date()): string {
  return `map-${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}-${p2(d.getHours())}${p2(
    d.getMinutes(),
  )}`;
}

/* ---------- image <-> world ---------- */

/** What the transform needs of a map. */
export interface GridGeometry {
  width: number;
  height: number;
  resolution: number;
  origin: { x: number; y: number };
}

/**
 * The picture is the grid flipped: image row 0 is the top row, which is the highest y.
 * Cell (i, j) has i along x and j along y (j = 0 is the bottom row in ROS order).
 * The origin yaw is assumed to be 0.
 */
export function cellToWorld(g: GridGeometry, i: number, j: number): [number, number] {
  return [g.origin.x + (i + 0.5) * g.resolution, g.origin.y + (j + 0.5) * g.resolution];
}

/** A world point to a (fractional) image pixel: x to the right, y down from the top edge. */
export function worldToImage(g: GridGeometry, x: number, y: number): [number, number] {
  return [(x - g.origin.x) / g.resolution, g.height - (y - g.origin.y) / g.resolution];
}

export function imageToWorld(g: GridGeometry, px: number, py: number): [number, number] {
  return [g.origin.x + px * g.resolution, g.origin.y + (g.height - py) * g.resolution];
}

/** The image pixel (col, row) that holds cell (i, j). */
export const cellToPixel = (g: GridGeometry, i: number, j: number): [number, number] => [
  i,
  g.height - 1 - j,
];

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export function mapBounds(g: GridGeometry): Bounds {
  return {
    minX: g.origin.x,
    maxX: g.origin.x + g.width * g.resolution,
    minY: g.origin.y,
    maxY: g.origin.y + g.height * g.resolution,
  };
}

/** The centre and pixels-per-metre that show the whole map in a canvas, with a margin. */
export function fitMap(
  g: GridGeometry,
  width: number,
  height: number,
  marginPx = 24,
): { cx: number; cy: number; scale: number } {
  const b = mapBounds(g);
  const w = Math.max(b.maxX - b.minX, 0.01);
  const h = Math.max(b.maxY - b.minY, 0.01);
  const sx = Math.max(width - 2 * marginPx, 10) / w;
  const sy = Math.max(height - 2 * marginPx, 10) / h;
  return { cx: (b.minX + b.maxX) / 2, cy: (b.minY + b.maxY) / 2, scale: Math.min(sx, sy) };
}

/* ---------- map metadata ---------- */

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** Read a map description from an object, or null when a needed field is wrong. */
export function toMapMeta(raw: unknown): MapMeta | null {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  const seq = num(r.seq);
  const width = num(r.width);
  const height = num(r.height);
  const resolution = num(r.resolution);
  if (seq === null || width === null || height === null || resolution === null) return null;
  if (width <= 0 || height <= 0 || resolution <= 0) return null;
  let ox: number | null = null;
  let oy: number | null = null;
  let oyaw = 0;
  const o = r.origin;
  if (Array.isArray(o)) {
    ox = num(o[0]);
    oy = num(o[1]);
    oyaw = num(o[2]) ?? 0;
  } else if (typeof o === 'object' && o !== null) {
    const oo = o as Record<string, unknown>;
    ox = num(oo.x);
    oy = num(oo.y);
    oyaw = num(oo.yaw) ?? 0;
  }
  if (ox === null || oy === null) return null;
  const meta: MapMeta = {
    seq,
    t: num(r.t) ?? 0,
    width,
    height,
    resolution,
    origin: { x: ox, y: oy, yaw: oyaw },
  };
  const stride = num(r.stride);
  if (stride !== null) meta.stride = stride;
  return meta;
}

/** The X-Map-Meta header is JSON. Anything else gives null. */
export function parseMapMeta(header: string | null | undefined): MapMeta | null {
  if (!header) return null;
  try {
    return toMapMeta(JSON.parse(header));
  } catch {
    return null;
  }
}

/* ---------- formatting ---------- */

const metres = (v: number): string => (v >= 100 ? v.toFixed(0) : v.toFixed(1));

/** "12.4 m by 8.0 m" for a map of that size. */
export function mapSizeText(g: Pick<GridGeometry, 'width' | 'height' | 'resolution'>): string {
  return `${metres(g.width * g.resolution)} m by ${metres(g.height * g.resolution)} m`;
}

/** For example "Map size 10.0 m by 8.0 m. Known area 42.5 m² of 80.0 m² (53%)." */
export function knownCellsSummary(
  known: number,
  total: number,
  resolution: number,
  size?: Pick<GridGeometry, 'width' | 'height'>,
): string {
  const cell = resolution * resolution;
  const pct = total > 0 ? Math.round((known / total) * 100) : 0;
  const head = size ? `Map size ${mapSizeText({ ...size, resolution })}. ` : '';
  return `${head}Known area ${(known * cell).toFixed(1)} m² of ${(total * cell).toFixed(1)} m² (${pct}%).`;
}

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '–';
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

/** "just now", "12 s ago", "5 min ago", "3 h ago", "2 days ago". Times are epoch seconds. */
export function formatAge(thenSec: number, nowSec: number = Date.now() / 1000): string {
  const d = Math.max(0, nowSec - thenSec);
  if (d < 5) return 'just now';
  if (d < 60) return `${Math.floor(d)} s ago`;
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  const days = Math.floor(d / 86400);
  return days === 1 ? '1 day ago' : `${days} days ago`;
}

/** A saved time as local date and time, for the library. */
export function formatSaved(epochSec: number): string {
  const d = new Date(epochSec * 1000);
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(
    d.getMinutes(),
  )}`;
}

/** Which of the four files a saved map has, in words. */
export function filesSummary(files: MapEntry['files']): string {
  const parts: Array<[string, number | null]> = [
    ['image', files.pgm],
    ['settings', files.yaml],
    ['graph', files.posegraph],
    ['data', files.data],
  ];
  const have = parts.filter(([, n]) => n !== null).map(([w]) => w);
  const miss = parts.filter(([, n]) => n === null).map(([w]) => w);
  const head = have.length ? have.join(', ') : 'none';
  return miss.length ? `${head} (missing: ${miss.join(', ')})` : head;
}

export const sizeOfEntry = (m: MapEntry): string =>
  mapSizeText({ width: m.width, height: m.height, resolution: m.resolution });

export const resolutionText = (r: number): string => `${(r * 100).toFixed(0)} cm per cell`;
