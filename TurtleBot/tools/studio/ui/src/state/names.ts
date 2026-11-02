import { DEFAULT_DEFAULTS } from '../lib/settingsForm';
import type { StudioState } from './store';

/** A robot name or address from the settings, else the server default, else the built-in one. */
export function nameOf(
  s: Pick<StudioState, 'settings' | 'defaults'>,
  key: 'robot_hostname' | 'robot_user' | 'hotspot_ssid' | 'hotspot_addr' | 'cable_addr',
): string {
  const v = s.settings[key];
  if (typeof v === 'string' && v) return v;
  return s.defaults[key] || DEFAULT_DEFAULTS[key] || '';
}
