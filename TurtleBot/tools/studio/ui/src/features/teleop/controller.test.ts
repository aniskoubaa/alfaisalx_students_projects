import { describe, expect, it } from 'vitest';
import type { TeleopCommand } from './controller';
import {
  DEFAULT_LIMITS,
  HARD_LIMITS,
  TeleopController,
  axesFromKeys,
  axis,
  clampLimits,
  fmtVelocity,
  velocityFor,
} from './controller';

function armed(limits = DEFAULT_LIMITS): TeleopController {
  const c = new TeleopController(limits, 10);
  c.arm();
  return c;
}

describe('TeleopController', () => {
  it('produces nothing until armed', () => {
    const c = new TeleopController();
    expect(c.setInput(1, 0, 0)).toBeNull();
    expect(c.tick(0)).toBeNull();
    expect(c.tick(1000)).toBeNull();
  });

  it('sends at 10 Hz with rising seq while the input is non-zero', () => {
    const c = armed();
    c.setInput(1, 0, 0);
    const sent: TeleopCommand[] = [];
    for (let t = 0; t <= 1000; t += 20) {
      const cmd = c.tick(t);
      if (cmd) sent.push(cmd);
    }
    // t = 0, 100, ..., 1000
    expect(sent.length).toBe(11);
    expect(sent.map((s) => s.seq)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
    expect(sent.every((s) => s.vx === 0.15 && s.wz === 0)).toBe(true);
  });

  it('does not send faster than the rate when ticked often', () => {
    const c = armed();
    c.setInput(1, 0, 0);
    expect(c.tick(0)).not.toBeNull();
    expect(c.tick(10)).toBeNull();
    expect(c.tick(99)).toBeNull();
    expect(c.tick(100)).not.toBeNull();
  });

  it('sends one immediate zero on release, ignoring the rate, then nothing', () => {
    const c = armed();
    c.setInput(1, 0, 0);
    c.tick(0);
    const z = c.setInput(0, 0, 5);
    expect(z).toEqual({ vx: 0, wz: 0, seq: 2 });
    expect(c.tick(10)).toBeNull();
    expect(c.tick(500)).toBeNull();
    expect(c.release(600)).toBeNull();
  });

  it('release before anything was sent sends no zero', () => {
    const c = armed();
    c.setInput(1, 0, 0);
    expect(c.release(1)).toBeNull();
  });

  it('seq restarts at every arm', () => {
    const c = armed();
    c.setInput(1, 0, 0);
    c.tick(0);
    c.tick(100);
    expect(c.seq).toBe(2);
    c.disarm();
    c.arm();
    expect(c.seq).toBe(0);
  });

  it('blur disarms, drops the input and sends nothing more', () => {
    const c = armed();
    c.setInput(1, 1, 0);
    c.tick(0);
    c.blur();
    expect(c.armed).toBe(false);
    expect(c.active).toBe(false);
    expect(c.target).toEqual({ vx: 0, wz: 0 });
    expect(c.tick(500)).toBeNull();
  });

  it('turns left with positive wz and goes backwards with negative vx', () => {
    const c = armed();
    c.setInput(-1, 1, 0);
    expect(c.tick(0)).toEqual({ vx: -0.15, wz: 0.6, seq: 1 });
  });

  it('scales with the limits and never exceeds the hard ceilings', () => {
    const c = armed({ linear: 5, angular: 9 });
    expect(c.limits).toEqual(HARD_LIMITS);
    c.setInput(1, -1, 0);
    expect(c.tick(0)).toEqual({ vx: 0.3, wz: -1.2, seq: 1 });
    c.setLimits({ linear: 0.1, angular: 0.4 });
    c.setInput(0.5, 0.5, 0);
    expect(c.tick(200)).toEqual({ vx: 0.05, wz: 0.2, seq: 2 });
  });

  it('clamps the input axes to -1..1', () => {
    const c = armed();
    c.setInput(7, -7, 0);
    expect(c.tick(0)).toEqual({ vx: 0.15, wz: -0.6, seq: 1 });
  });
});

describe('helpers', () => {
  it('axis removes the dead zone and reaches 1 at the rim', () => {
    expect(axis(0.05)).toBe(0);
    expect(axis(-0.1)).toBe(0);
    expect(axis(1)).toBe(1);
    expect(axis(-2)).toBe(-1);
    expect(axis(0.5)).toBeGreaterThan(0);
    expect(axis(0.5)).toBeLessThan(0.5);
    expect(axis(Number.NaN)).toBe(0);
  });

  it('velocityFor never shows negative zero', () => {
    const v = velocityFor(0, 0, DEFAULT_LIMITS);
    expect(Object.is(v.vx, 0)).toBe(true);
    expect(Object.is(v.wz, 0)).toBe(true);
    const w = velocityFor(-0, -0, DEFAULT_LIMITS);
    expect(Object.is(w.vx, 0)).toBe(true);
  });

  it('clampLimits keeps the values inside the floor and the ceiling', () => {
    expect(clampLimits({ linear: 0, angular: 0 })).toEqual({ linear: 0.02, angular: 0.1 });
    expect(clampLimits({ linear: 1, angular: 3 })).toEqual(HARD_LIMITS);
    expect(clampLimits({ linear: Number.NaN, angular: Number.NaN })).toEqual(DEFAULT_LIMITS);
  });

  it('axesFromKeys combines opposite keys to zero', () => {
    expect(axesFromKeys(new Set(['fwd', 'left']))).toEqual({ forward: 1, turn: 1 });
    expect(axesFromKeys(new Set(['fwd', 'back']))).toEqual({ forward: 0, turn: 0 });
    expect(axesFromKeys(new Set(['right']))).toEqual({ forward: 0, turn: -1 });
  });

  it('fmtVelocity writes units and a real minus sign', () => {
    expect(fmtVelocity(-0.15, 0.6)).toBe('−0.15 m/s, 0.60 rad/s');
  });
});
