import type { Settings } from '../api/types';

export const DEFAULT_DEFAULTS: Record<string, string> = {
  robot_hostname: 'turtlebot4',
  robot_user: 'ubuntu',
  hotspot_ssid: 'Turtlebot4',
  hotspot_addr: '10.42.0.1',
  cable_addr: '192.168.185.3',
};

export const DEFAULT_REMOTE_DIR = '~/robot_code';

/** The settings screen's editable values. Text boxes hold text; the programs list is one line each. */
export interface SettingsForm {
  last_host: string;
  key_path: string;
  local_dir: string;
  remote_dir: string;
  motion_files: string;
  robot_hostname: string;
  robot_user: string;
  hotspot_ssid: string;
  hotspot_addr: string;
  cable_addr: string;
  window_mode: 'app' | 'browser';
  auto_reconnect: boolean;
  update_check: boolean;
  builtin_host_key: boolean;
  /** True when the classic interface should open next time (the setting `ui` is 'classic'). */
  classic_ui: boolean;
}

export type TextKey =
  'robot_hostname' | 'robot_user' | 'hotspot_ssid' | 'hotspot_addr' | 'cable_addr';
const TEXT_WITH_DEFAULT: readonly TextKey[] = [
  'robot_hostname',
  'robot_user',
  'hotspot_ssid',
  'hotspot_addr',
  'cable_addr',
];

export function defaultFor(defaults: Record<string, string>, key: string): string {
  return defaults[key] || DEFAULT_DEFAULTS[key] || '';
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '');

/** Form values for the settings the server holds now. */
export function formFromSettings(s: Settings, defaults: Record<string, string> = {}): SettingsForm {
  const files = Array.isArray(s.motion_files)
    ? s.motion_files.filter((x) => typeof x === 'string')
    : [];
  return {
    last_host: str(s.last_host),
    key_path: str(s.key_path),
    local_dir: str(s.local_dir),
    remote_dir: str(s.remote_dir) || DEFAULT_REMOTE_DIR,
    motion_files: files.join('\n'),
    robot_hostname: str(s.robot_hostname) || defaultFor(defaults, 'robot_hostname'),
    robot_user: str(s.robot_user) || defaultFor(defaults, 'robot_user'),
    hotspot_ssid: str(s.hotspot_ssid) || defaultFor(defaults, 'hotspot_ssid'),
    hotspot_addr: str(s.hotspot_addr) || defaultFor(defaults, 'hotspot_addr'),
    cable_addr: str(s.cable_addr) || defaultFor(defaults, 'cable_addr'),
    window_mode: s.window_mode === 'browser' ? 'browser' : 'app',
    auto_reconnect: s.auto_reconnect !== false,
    update_check: s.update_check !== false,
    builtin_host_key: s.builtin_host_key !== false,
    classic_ui: s.ui === 'classic',
  };
}

export function linesToList(text: string): string[] {
  return text
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean);
}

/** Make a form comparable: trim text, fill an empty address or name with its default. */
export function normalizeForm(
  f: SettingsForm,
  defaults: Record<string, string> = {},
): SettingsForm {
  const out: SettingsForm = {
    ...f,
    last_host: f.last_host.trim(),
    key_path: f.key_path.trim(),
    local_dir: f.local_dir.trim(),
    remote_dir: f.remote_dir.trim() || DEFAULT_REMOTE_DIR,
    motion_files: linesToList(f.motion_files).join('\n'),
  };
  for (const k of TEXT_WITH_DEFAULT) out[k] = f[k].trim() || defaultFor(defaults, k);
  return out;
}

/**
 * Only the settings that changed, ready to send to POST /api/settings.
 * Compares normalized values, so retyping the default or adding a space changes nothing.
 */
export function buildPatch(
  form: SettingsForm,
  saved: SettingsForm,
  defaults: Record<string, string> = {},
): Settings {
  const a = normalizeForm(form, defaults);
  const b = normalizeForm(saved, defaults);
  const patch: Settings = {};
  if (a.last_host !== b.last_host) patch.last_host = a.last_host;
  if (a.key_path !== b.key_path) patch.key_path = a.key_path;
  if (a.local_dir !== b.local_dir) patch.local_dir = a.local_dir;
  if (a.remote_dir !== b.remote_dir) patch.remote_dir = a.remote_dir;
  if (a.motion_files !== b.motion_files) patch.motion_files = linesToList(a.motion_files);
  for (const k of TEXT_WITH_DEFAULT) if (a[k] !== b[k]) patch[k] = a[k];
  if (a.window_mode !== b.window_mode) patch.window_mode = a.window_mode;
  if (a.auto_reconnect !== b.auto_reconnect) patch.auto_reconnect = a.auto_reconnect;
  if (a.update_check !== b.update_check) patch.update_check = a.update_check;
  if (a.builtin_host_key !== b.builtin_host_key) patch.builtin_host_key = a.builtin_host_key;
  if (a.classic_ui !== b.classic_ui) patch.ui = a.classic_ui ? 'classic' : 'v2';
  return patch;
}

/* ---------- driving limits ---------- */

export interface LimitsRange {
  minLinear: number;
  maxLinear: number;
  minAngular: number;
  maxAngular: number;
}

/** Lowest values Studio accepts; the highest come from the server (0.30 m/s and 1.20 rad/s). */
export const LIMIT_FLOORS = { linear: 0.02, angular: 0.1 } as const;
export const LIMIT_CAPS = { linear: 0.3, angular: 1.2 } as const;

export interface LimitsText {
  linear: string;
  angular: string;
}

export function limitsToText(l: { linear: number; angular: number }): LimitsText {
  return { linear: String(l.linear), angular: String(l.angular) };
}

export function parseLimit(text: string): number | null {
  const t = text.trim().replace(',', '.');
  if (!/^\d*\.?\d+$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** An error in plain words, or '' when the value can be saved. */
export function limitError(
  kind: 'linear' | 'angular',
  text: string,
  caps: { linear: number; angular: number },
): string {
  const unit = kind === 'linear' ? 'm/s' : 'rad/s';
  const lo = LIMIT_FLOORS[kind];
  const hi = caps[kind];
  const n = parseLimit(text);
  if (n === null) return `Enter a number, for example ${kind === 'linear' ? '0.15' : '0.6'}.`;
  if (n < lo || n > hi) return `Use a value from ${lo} to ${hi} ${unit}.`;
  return '';
}

/** Only the limits that changed (as numbers). Empty when nothing changed. */
export function limitsPatch(
  text: LimitsText,
  saved: { linear: number; angular: number },
): { linear?: number; angular?: number } {
  const out: { linear?: number; angular?: number } = {};
  const l = parseLimit(text.linear);
  const a = parseLimit(text.angular);
  if (l !== null && l !== saved.linear) out.linear = l;
  if (a !== null && a !== saved.angular) out.angular = a;
  return out;
}
