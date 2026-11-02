/**
 * Types for the setup, Wi-Fi, topics, tools and settings endpoints (Frontend F2).
 * Written from studio.py (2.0) and the 1.3 interface in web/app.js.
 */
import type { TrustedKey } from './types';

/* ---------- setup wizard ---------- */

export interface KeyInfo {
  path: string;
  exists?: boolean;
  fingerprint?: string | null;
}

export interface SetupStatus {
  ssh?: { found: boolean; path?: string | null; version?: string | null };
  keygen?: { found: boolean };
  keyscan?: { found: boolean };
  key?: KeyInfo;
  host?: string | null;
  setup_done?: boolean;
  fake?: boolean;
  /** 'windows', 'macos' or 'linux'. */
  os?: string;
  user?: string;
}

export interface HostKeyScan {
  host: string;
  key: string;
  fingerprint: string;
  trusted: boolean;
  label: string | null;
}

export interface TrustAnswer {
  key: string;
  fingerprint: string;
  label: string;
  trusted: TrustedKey[];
}

export interface CreateKeyAnswer {
  path: string;
  fingerprint?: string | null;
  created: boolean;
}

export interface TestLoginAnswer {
  hostname?: string | null;
  fake?: boolean;
}

export interface SetupKeyAnswer {
  note?: string;
  fake?: boolean;
}

/** A trusted-robot entry as the server lists it (the built-in key can be switched off). */
export interface TrustedEntry extends TrustedKey {
  enabled?: boolean;
}

/* ---------- Wi-Fi ---------- */

export interface LaptopWifi {
  ssid?: string | null;
  signal_pct?: number | null;
  state?: string | null;
  interface?: string | null;
  /** True when the name is Windows' network name, which can differ from the real SSID. */
  ssid_guess?: boolean;
  note?: string | null;
}
export interface LaptopWired {
  name: string;
  up?: boolean;
  ipv4?: string[];
}
export interface LaptopNet {
  wifi: LaptopWifi | null;
  wired: LaptopWired[];
  os?: string;
}

export interface WlanInfo {
  state?: string | null;
  connection?: string | null;
  /** 'ap' for the robot's own hotspot, 'infrastructure' or 'client' when joined to a network. */
  mode?: string | null;
  ssid?: string | null;
  ip?: string | null;
  signal_dbm?: number | null;
  powersave?: string | null;
}
export interface SavedWifi {
  name: string;
  ssid?: string | null;
  mode?: string | null;
  autoconnect?: boolean | null;
  priority?: number | null;
  powersave?: string | null;
  active?: boolean | null;
}
export interface ScannedWifi {
  ssid?: string | null;
  signal?: number | null;
  security?: string | null;
  chan?: string | number | null;
}
export interface WifiInfo {
  fake?: boolean;
  wlan0?: WlanInfo;
  saved?: SavedWifi[];
  scan?: ScannedWifi[];
  scan_note?: string | null;
}

export interface WifiAddAnswer {
  fake?: boolean;
  note?: string;
  nonce?: string;
  ssid?: string;
  connect_now?: boolean;
  ttl?: number;
  timeout?: number;
}

export interface WifiJoin {
  /** 'joining', 'joined' or 'failed'. */
  state?: string;
  ssid?: string;
  ip?: string;
  t?: number;
  reason?: string;
  fallback?: string;
  fallback_ok?: boolean;
  removed?: boolean;
}
export interface WifiStatusAnswer {
  /** 'fetched', 'expired' or 'none' (also 'pending' while the robot password is awaited). */
  secret: string;
  join: WifiJoin | null;
  stored?: boolean;
}

export interface JoinHotspotAnswer {
  warning?: string;
  detail?: string;
  message?: string;
}

/* ---------- tools ---------- */

export interface DiagnosticsAnswer {
  text: string;
}
export interface TeleopLimitsAnswer {
  linear: number;
  angular: number;
  max_linear: number;
  max_angular: number;
}

/* ---------- topics ---------- */

export interface TopicInfo {
  name: string;
  types?: string[];
  publishers?: number;
  subscribers?: number;
}
