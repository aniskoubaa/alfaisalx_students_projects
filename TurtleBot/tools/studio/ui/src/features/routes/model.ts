/**
 * Pure helpers for the Routes screen: status words, the rules for changing the current route,
 * the name rule, the check of a folder chosen in the browser and the trip status words.
 */
import type { RouteEntry, TripStatusAnswer } from '../../api';

export const REQUIRED_ROUTE_FILES = [
  'route.yaml',
  'map.yaml',
  'keepout_mask.yaml',
  'speed_mask.yaml',
] as const;

/** The desktop refuses bodies over 32 MB on the upload path. */
export const UPLOAD_LIMIT_BYTES = 32 * 1024 * 1024;

/* ---------- route list ---------- */

/** "Ready", or "Incomplete: missing route.yaml, map.yaml". */
export function routeStatus(r: Pick<RouteEntry, 'valid' | 'missing'>): string {
  if (r.valid) return 'Ready';
  return r.missing.length > 0 ? `Incomplete: missing ${r.missing.join(', ')}` : 'Incomplete';
}

export function waypointsText(r: Pick<RouteEntry, 'waypoints'>): string {
  const w = r.waypoints;
  return w ? `${w.outbound} out, ${w.inbound} in` : 'Not known';
}

/** One line about where `current` points. */
export function currentSummary(
  current: string | null | undefined,
  currentOk: boolean | undefined,
  routes: RouteEntry[],
): string {
  if (!current) return 'No current route is set.';
  const found = routes.find((r) => r.name === current);
  if (!found || currentOk === false) {
    return `The current route is ${current}, but its folder is missing or incomplete.`;
  }
  return 'The front-panel menu and the next trip use this route.';
}

export interface TripState {
  mission_running: boolean;
  stack_running: boolean;
}

export interface CanSet {
  ok: boolean;
  /** Why not, in words; empty when ok. */
  reason: string;
}

/** Whether "Use this route" is allowed for a route. `trip` is null when not known yet. */
export function canSetCurrent(
  route: Pick<RouteEntry, 'name' | 'valid' | 'missing'>,
  current: string | null | undefined,
  trip: TripState | null,
): CanSet {
  if (!route.valid) return { ok: false, reason: `Not ready. ${routeStatus(route)}.` };
  if (route.name === current) return { ok: false, reason: 'Already the current route.' };
  if (trip?.mission_running) {
    return { ok: false, reason: 'A trip is running. Wait until it has finished.' };
  }
  if (trip?.stack_running) {
    return { ok: false, reason: 'The navigation stack is running. Stop it first.' };
  }
  return { ok: true, reason: '' };
}

export function confirmText(oldName: string | null | undefined, newName: string): string {
  const was = oldName ? oldName : 'the route that is set now';
  return `The front-panel menu and the next trip will use ${newName} instead of ${was}. Nothing moves now.`;
}

/* ---------- names ---------- */

export const ROUTE_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/;

export type NameCheck = { ok: true } | { ok: false; message: string };

export function validRouteName(name: string): NameCheck {
  if (!name) return { ok: false, message: 'Type a name for the route.' };
  if (name.length > 48) return { ok: false, message: 'Use 48 characters or fewer.' };
  if (!/^[A-Za-z0-9]/.test(name))
    return { ok: false, message: 'Start the name with a letter or a digit.' };
  if (!ROUTE_NAME_RE.test(name))
    return {
      ok: false,
      message: 'Use only letters, digits, hyphens (-) and underscores (_). No spaces.',
    };
  return { ok: true };
}

/** A valid name made from a folder name: odd characters become hyphens, 48 characters at most. */
export function suggestRouteName(folder: string): string {
  const s = folder
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, '-')
    .replace(/^[^A-Za-z0-9]+/, '')
    .slice(0, 48)
    .replace(/[-_]+$/, '');
  return s || 'route';
}

export function existsMessage(name: string): string {
  return `A route named ${name} already exists on the robot. Choose another name.`;
}

/* ---------- folder check ---------- */

/** What the check needs of a chosen file. */
export interface PickedFile {
  webkitRelativePath: string;
  name: string;
  size: number;
}

export interface UploadCheck {
  ok: boolean;
  /** The folder the person chose ("" when the browser gave no folder paths). */
  folder: string;
  /** Files directly inside the folder, by name. */
  found: string[];
  /** Required files that are not there. */
  missing: string[];
  /** Paths of files inside subfolders; they are ignored. */
  nested: string[];
  /** The files that count are over the size limit together. */
  tooBig: boolean;
  /** Total bytes of the files that will be sent. */
  total: number;
}

/**
 * The browser gives "folder/file" for every file under the chosen folder. Only files directly
 * inside it count; deeper ones are reported and ignored. Required: the four route files.
 */
export function checkUploadFiles(files: ArrayLike<PickedFile>): UploadCheck {
  const found: string[] = [];
  const nested: string[] = [];
  let folder = '';
  let total = 0;
  for (let i = 0; i < files.length; i++) {
    const f = files[i] as PickedFile;
    const parts = (f.webkitRelativePath || f.name).split('/');
    if (parts.length >= 2 && !folder) folder = parts[0] ?? '';
    if (parts.length <= 2) {
      found.push(parts[parts.length - 1] ?? f.name);
      total += f.size;
    } else {
      nested.push(parts.slice(1).join('/'));
    }
  }
  const missing = REQUIRED_ROUTE_FILES.filter((r) => !found.includes(r));
  const tooBig = total > UPLOAD_LIMIT_BYTES;
  return {
    ok: missing.length === 0 && !tooBig && found.length > 0,
    folder,
    found,
    missing,
    nested,
    tooBig,
    total,
  };
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/* ---------- trip status ---------- */

const yn = (b: boolean) => (b ? 'yes' : 'no');

export interface TripWords {
  menu: string;
  trip: string;
  stack: string;
}

export function tripWords(
  t: Pick<TripStatusAnswer, 'menu_running' | 'mission_running' | 'stack_running'>,
): TripWords {
  return {
    menu: `Menu running: ${yn(t.menu_running)}`,
    trip: `Trip running: ${yn(t.mission_running)}`,
    stack: `Navigation running: ${yn(t.stack_running)}`,
  };
}

export function formatSaved(epochSec: number): string {
  const p = (n: number) => String(n).padStart(2, '0');
  const d = new Date(epochSec * 1000);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export const TRIP_NOTE =
  "Starting trips from Studio is not part of this version; use the robot's front-panel menu.";
