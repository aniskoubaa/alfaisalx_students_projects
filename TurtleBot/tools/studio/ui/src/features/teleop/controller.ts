/**
 * Pure logic for manual driving. No timers, no network, no DOM: the caller passes the time in
 * and sends whatever `tick`, `setInput` or `release` returns. That keeps every safety rule testable.
 *
 * Rules implemented here:
 * - nothing is produced unless armed;
 * - while the input is non-zero, one command every `1000 / rateHz` ms, each with a higher seq;
 * - the moment the input becomes zero, exactly one zero command goes out at once (not rate limited);
 * - disarming (blur, hidden tab, route change, lost stream, bridge disarm) clears the input and
 *   sends nothing: the caller sends `teleop_arm {on:false}`, which makes the bridge publish zero;
 * - speeds are never above the limits, and the limits are clamped to the bridge ceilings.
 */

export interface Limits {
  /** Metres per second. */
  linear: number;
  /** Radians per second. */
  angular: number;
}

export interface TeleopCommand {
  vx: number;
  wz: number;
  seq: number;
}

/** Hard ceilings of the bridge (also enforced there). Used to clamp what the page sends and shows. */
export const HARD_LIMITS: Limits = { linear: 0.3, angular: 1.2 };
export const MIN_LIMITS: Limits = { linear: 0.02, angular: 0.1 };
export const DEFAULT_LIMITS: Limits = { linear: 0.15, angular: 0.6 };
export const SEND_RATE_HZ = 10;
export const DEADZONE = 0.12;

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const round3 = (v: number): number => Math.round(v * 1000) / 1000;

/** Normalise an axis value: dead zone removed, result in -1..1. */
export function axis(v: number): number {
  if (!Number.isFinite(v)) return 0;
  const a = Math.abs(v);
  if (a < DEADZONE) return 0;
  // Rescale so the output starts at 0 just outside the dead zone and reaches 1 at the rim.
  const scaled = Math.min(1, (a - DEADZONE) / (1 - DEADZONE));
  return v < 0 ? -scaled : scaled;
}

/** Velocity for the two axes (forward -1..1, turn -1..1; turn left is positive) and the limits. */
export function velocityFor(
  forward: number,
  turn: number,
  limits: Limits,
): { vx: number; wz: number } {
  const vx = clamp(forward, -1, 1) * limits.linear;
  const wz = clamp(turn, -1, 1) * limits.angular;
  // `+ 0` turns -0 into 0 so tests and displays never show "-0".
  return { vx: round3(vx) + 0, wz: round3(wz) + 0 };
}

/** Limits as the page may show or use them: inside [floor, ceiling]. */
export function clampLimits(l: Limits, hard: Limits = HARD_LIMITS): Limits {
  return {
    linear: clamp(
      Number.isFinite(l.linear) ? l.linear : DEFAULT_LIMITS.linear,
      MIN_LIMITS.linear,
      hard.linear,
    ),
    angular: clamp(
      Number.isFinite(l.angular) ? l.angular : DEFAULT_LIMITS.angular,
      MIN_LIMITS.angular,
      hard.angular,
    ),
  };
}

/** Text for a commanded value, with a real minus sign and units. */
export function fmtVelocity(vx: number, wz: number): string {
  const f = (v: number, d: number) => (v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
  return `${f(vx, 2)} m/s, ${f(wz, 2)} rad/s`;
}

export type DriveDir = 'fwd' | 'back' | 'left' | 'right';

/** Keys that drive (lower case `KeyboardEvent.key`). */
export const DRIVE_KEYS: Readonly<Record<string, DriveDir>> = {
  w: 'fwd',
  arrowup: 'fwd',
  s: 'back',
  arrowdown: 'back',
  a: 'left',
  arrowleft: 'left',
  d: 'right',
  arrowright: 'right',
};

export function axesFromKeys(held: ReadonlySet<DriveDir>): { forward: number; turn: number } {
  const forward = (held.has('fwd') ? 1 : 0) - (held.has('back') ? 1 : 0);
  const turn = (held.has('left') ? 1 : 0) - (held.has('right') ? 1 : 0);
  return { forward, turn };
}

export class TeleopController {
  armed = false;
  limits: Limits;
  readonly intervalMs: number;
  private forward = 0;
  private turn = 0;
  private seqNo = 0;
  private lastSentAt = -Infinity;
  /** True when the last command sent was non-zero, so a zero still has to follow. */
  private moving = false;

  constructor(limits: Limits = DEFAULT_LIMITS, rateHz: number = SEND_RATE_HZ) {
    this.limits = clampLimits(limits);
    this.intervalMs = 1000 / Math.max(1, Math.min(20, rateHz));
  }

  get seq(): number {
    return this.seqNo;
  }

  /** The target velocity right now (zero when not armed). */
  get target(): { vx: number; wz: number } {
    if (!this.armed) return { vx: 0, wz: 0 };
    return velocityFor(this.forward, this.turn, this.limits);
  }

  get active(): boolean {
    return this.armed && (this.forward !== 0 || this.turn !== 0);
  }

  setLimits(l: Limits): void {
    this.limits = clampLimits(l);
  }

  /** The bridge accepted the arm request. The seq counter restarts at every arm. */
  arm(): void {
    this.armed = true;
    this.forward = 0;
    this.turn = 0;
    this.seqNo = 0;
    this.lastSentAt = -Infinity;
    this.moving = false;
  }

  /** Any disarm: the input is dropped and nothing more is produced. */
  disarm(): void {
    this.armed = false;
    this.forward = 0;
    this.turn = 0;
    this.moving = false;
  }

  /** Window lost focus, tab hidden, screen left, stream lost: same as disarm. */
  blur(): void {
    this.disarm();
  }

  /** Set the input axes. Returns the zero command to send now when the input just became zero. */
  setInput(forward: number, turn: number, nowMs: number): TeleopCommand | null {
    if (!this.armed) return null;
    this.forward = clamp(forward, -1, 1);
    this.turn = clamp(turn, -1, 1);
    if (this.forward === 0 && this.turn === 0) return this.release(nowMs);
    return null;
  }

  /** Input released (key up, stick let go). Emits one zero if the last command was not zero. */
  release(nowMs: number): TeleopCommand | null {
    this.forward = 0;
    this.turn = 0;
    if (!this.armed || !this.moving) return null;
    this.moving = false;
    this.lastSentAt = nowMs;
    return { vx: 0, wz: 0, seq: ++this.seqNo };
  }

  /** Call often (every 50 ms is fine). Returns the command to send now, or null. */
  tick(nowMs: number): TeleopCommand | null {
    if (!this.armed || !this.active) return null;
    if (nowMs - this.lastSentAt < this.intervalMs) return null;
    const { vx, wz } = this.target;
    this.lastSentAt = nowMs;
    this.moving = vx !== 0 || wz !== 0;
    return { vx, wz, seq: ++this.seqNo };
  }
}
