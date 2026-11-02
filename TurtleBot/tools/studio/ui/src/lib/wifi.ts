import type {
  SavedWifi,
  ScannedWifi,
  WifiInfo,
  WifiJoin,
  WifiStatusAnswer,
} from '../api/setup-types';

/* ---------- security of a scanned network ---------- */

export interface WifiSecurity {
  /** True when the robot can join it with just a password (WPA or WPA2 personal). */
  ok: boolean;
  kind: 'open' | 'enterprise' | 'wpa3' | 'wep' | 'personal';
  label: string;
  why?: string;
}

export function wifiSecurity(sec: string | null | undefined): WifiSecurity {
  const s = String(sec ?? '').trim();
  if (!s || s === '--' || /^(open|none|owe)$/i.test(s)) {
    return {
      ok: false,
      kind: 'open',
      label: 'Open network',
      why: 'Open networks are not supported.',
    };
  }
  if (/802\.1x|eap|enterprise/i.test(s)) {
    return {
      ok: false,
      kind: 'enterprise',
      label: 'Enterprise (802.1X)',
      why: 'Enterprise networks (802.1X, username and password) are not supported yet.',
    };
  }
  const t = s
    .toUpperCase()
    .split(/[\s,/]+/)
    .filter(Boolean);
  const wpa12 = t.some((x) => x === 'WPA' || x === 'WPA1' || x === 'WPA2');
  if (t.includes('WPA3') && !wpa12) {
    return {
      ok: false,
      kind: 'wpa3',
      label: 'WPA3 only',
      why: 'WPA3-only networks are not supported yet.',
    };
  }
  if (t.includes('WEP') && !wpa12) {
    return { ok: false, kind: 'wep', label: 'WEP', why: 'WEP networks are not supported.' };
  }
  return { ok: true, kind: 'personal', label: s };
}

/** 8 to 63 printable ASCII characters, or exactly 64 hex digits. */
export function validPsk(p: string): boolean {
  return /^[\x20-\x7e]{8,63}$/.test(p) || /^[0-9a-fA-F]{64}$/.test(p);
}

/* ---------- saved networks ---------- */

/** Connections the robot needs for its own hotspot and cable. They cannot be removed here. */
export const PROTECTED_WIFI: readonly string[] = [
  'netplan-wlan0-Turtlebot4',
  'netplan-eth0',
  'netplan-usb0',
];

export function isProtectedWifi(name: string, hotspotSsid: string): boolean {
  return PROTECTED_WIFI.includes(name) || name === 'netplan-wlan0-' + hotspotSsid;
}

/** The scan entry for an SSID: a supported one when several share the name. */
export function scanFor(scan: ScannedWifi[] | undefined, ssid: string): ScannedWifi | null {
  const list = (scan ?? []).filter((x) => x.ssid === ssid);
  return list.find((x) => wifiSecurity(x.security).ok) ?? list[0] ?? null;
}

/* ---------- where you are ---------- */

export type RobotMode = 'ap' | 'client' | null;

export function robotMode(info: WifiInfo | null, statusMode: string | null | undefined): RobotMode {
  const m = info?.wlan0?.mode ?? statusMode ?? null;
  if (m === 'ap') return 'ap';
  if (m === 'infrastructure' || m === 'client') return 'client';
  return null;
}

export type Way = 'A' | 'B' | 'C' | null;

/**
 * Which of the three ways to connect is in use now: C cable, A the robot's hotspot,
 * B a shared Wi-Fi network. Without a connection only the hotspot can be told from this computer.
 */
export function currentWay(opts: {
  connected: boolean;
  via: string | null | undefined;
  mode: RobotMode;
  laptopSsid: string | null | undefined;
  hotspotSsid: string;
}): Way {
  if (opts.connected) {
    if (opts.via === 'cable') return 'C';
    if (opts.via === 'hotspot' || opts.mode === 'ap') return 'A';
    return 'B';
  }
  return opts.laptopSsid === opts.hotspotSsid ? 'A' : null;
}

/* ---------- the "join a network" form ---------- */

export interface WifiFormState {
  ssid: string;
  already: boolean;
  sec: WifiSecurity | null;
  /** Empty when the form can be sent; otherwise the one thing that stops it, in plain words. */
  why: string;
}

/** Validates the form. It only looks at the length and characters of the password. */
export function wifiFormState(input: {
  ssid: string;
  psk: string;
  connected: boolean;
  hotspotSsid: string;
  info: WifiInfo | null;
}): WifiFormState {
  const ssid = input.ssid.trim();
  const hasPsk = input.psk.length > 0;
  const already = !!(ssid && input.info && (input.info.saved ?? []).some((n) => n.ssid === ssid));
  const hit = ssid ? scanFor(input.info?.scan, ssid) : null;
  const sec = hit ? wifiSecurity(hit.security) : null;
  let why = '';
  if (!input.connected) why = 'Connect to the robot first (cable or hotspot).';
  else if (!ssid) why = 'Type or pick a network name.';
  else if (ssid === input.hotspotSsid) {
    why = "That is the robot's own hotspot. Pick another network.";
  } else if (already) {
    why = `“${ssid}” is already saved. To change its password, remove it below and add it again.`;
  } else if (sec && !sec.ok) why = sec.why ?? 'This network is not supported.';
  else if (!hasPsk) why = 'Type the Wi-Fi password.';
  else if (!validPsk(input.psk))
    why = 'The password must be 8 to 63 characters (or 64 hex digits).';
  return { ssid, already, sec, why };
}

/* ---------- the add-a-network job ---------- */

export interface WifiJob {
  nonce: string;
  ssid: string;
  /** The robot switches to the network right away and tests it. */
  now: boolean;
  /** When the job started (epoch milliseconds). */
  t: number;
  /** The robot's join timestamp before this attempt, to ignore an older result. */
  base?: number | null;
  fake?: boolean;
}

export type StepState = 'ok' | 'bad' | 'run' | 'wait' | 'idle' | 'warn';
export interface JobStep {
  text: string;
  state: StepState;
}
export type JobResult = 'joined' | 'failed' | 'saved' | 'expired' | null;
export interface JobView {
  steps: JobStep[];
  done: boolean;
  result: JobResult;
  join: WifiJoin | null;
}

/** Pure: turns the last robot_wifi_status answer into the progress steps and the result. */
export function wifiView(job: WifiJob, r: WifiStatusAnswer | null, lost: boolean): JobView {
  const secret = r?.secret ?? null;
  let jn: WifiJoin | null = r?.join ?? null;
  // A status file left by an older attempt does not belong to this job.
  if (jn && ((jn.ssid && jn.ssid !== job.ssid) || (job.base != null && jn.t === job.base))) {
    jn = null;
  }
  const state = jn?.state;
  const fetched = secret === 'fetched' || !!jn;
  const expired = secret === 'expired' && !jn;

  const steps: JobStep[] = [{ text: 'Password sent to the robot (memory only)', state: 'ok' }];
  steps.push({
    text: job.fake
      ? 'Robot password (test mode: not needed)'
      : 'Type the robot password in the terminal',
    state: fetched ? 'ok' : expired ? 'bad' : 'wait',
  });
  steps.push({
    text: 'Saving the network on the robot',
    state: fetched ? (job.now && !jn ? 'run' : 'ok') : 'idle',
  });
  if (job.now) {
    steps.push({
      text: `Joining “${job.ssid}” (up to 45 s)`,
      state: state === 'joining' ? 'run' : state === 'joined' || state === 'failed' ? 'ok' : 'idle',
    });
  }
  const result: JobResult =
    state === 'joined'
      ? 'joined'
      : state === 'failed'
        ? 'failed'
        : !job.now && fetched
          ? 'saved'
          : expired
            ? 'expired'
            : null;
  steps.push({
    text: 'Result',
    state:
      result === 'joined' || result === 'saved'
        ? 'ok'
        : result === 'failed' || result === 'expired'
          ? 'bad'
          : lost
            ? 'warn'
            : 'idle',
  });
  return { steps, done: result !== null, result, join: jn };
}

export type JobFlag = 'lost' | 'timeout' | null;
export interface PollState {
  last: WifiStatusAnswer | null;
  /** Failed polls in a row. */
  fails: number;
}
export interface PollStep {
  state: PollState;
  view: JobView;
  flag: JobFlag;
  /** Set on the first good answer: the robot's join timestamp before this job. */
  base?: number | null;
  /** True when polling should stop. */
  stop: boolean;
  error?: string;
}

export const POLL_MAX_FAILS = 3;
export const POLL_TIMEOUT_MS = 150_000;
export const POLL_EVERY_MS = 2000;

/**
 * Pure: one step of the polling loop. Gives the next state, what to show, and whether to stop.
 * It stops when the result is known, when the robot cannot be reached (it probably changed
 * network), or after 150 s.
 */
export function pollStep(
  job: WifiJob,
  prev: PollState,
  answer: { ok: true; data: WifiStatusAnswer } | { ok: false; error: string },
  ctx: { connected: boolean; elapsedMs: number },
): PollStep {
  let state = prev;
  let base: number | null | undefined;
  if (answer.ok) {
    state = { last: answer.data, fails: 0 };
    if (job.base === undefined) base = answer.data.join?.t ?? null;
  } else {
    state = { last: prev.last, fails: prev.fails + 1 };
  }
  const jobNow = base !== undefined ? { ...job, base } : job;
  const view = wifiView(jobNow, state.last, false);
  if (view.done) return { state, view, flag: null, base, stop: true };
  if (state.fails >= POLL_MAX_FAILS || (!answer.ok && !ctx.connected)) {
    return {
      state,
      view: wifiView(jobNow, state.last, true),
      flag: 'lost',
      base,
      stop: true,
      error: answer.ok ? undefined : answer.error,
    };
  }
  if (ctx.elapsedMs > POLL_TIMEOUT_MS) return { state, view, flag: 'timeout', base, stop: true };
  return { state, view, flag: null, base, stop: false };
}

/* ---------- saved list helpers ---------- */

export function savedLabel(x: SavedWifi): string {
  return x.ssid && x.ssid !== x.name ? `${x.name} (${x.ssid})` : x.name;
}
