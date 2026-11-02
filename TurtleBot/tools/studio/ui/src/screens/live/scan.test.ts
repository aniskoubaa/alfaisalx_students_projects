import { describe, expect, it } from 'vitest';
import type { View } from './scan';
import {
  bearingWord,
  clampScale,
  fmtNearest,
  fmtRing,
  isScanStale,
  noScanNote,
  panBy,
  pushTrail,
  ringRadii,
  ringStep,
  robotToWorld,
  scanToPoints,
  screenToWorld,
  worldToScreen,
  zoomAt,
} from './scan';

const near = (a: number, b: number, d = 4) => expect(a).toBeCloseTo(b, d);

describe('scanToPoints', () => {
  it('puts angle 0 straight ahead (+x) and a positive angle to the left (+y)', () => {
    const p = scanToPoints({
      angle_min: 0,
      angle_inc: Math.PI / 2,
      range_max: 12,
      ranges: [2, 1, null, 3],
    });
    expect(p.n).toBe(3);
    near(p.x[0] as number, 2);
    near(p.y[0] as number, 0);
    near(p.x[1] as number, 0);
    near(p.y[1] as number, 1); // 90 degrees: left
    near(p.x[2] as number, 0);
    near(p.y[2] as number, -3); // 270 degrees (index 3): right
  });

  it('skips null, zero, too close and beyond range_max', () => {
    const p = scanToPoints({
      angle_min: 0,
      angle_inc: 0.1,
      range_max: 5,
      ranges: [null, 0, 0.02, 6, Number.NaN, 4.9],
    });
    expect(p.n).toBe(1);
    near(p.nearest?.dist ?? 0, 4.9);
  });

  it('finds the nearest point with its bearing', () => {
    const p = scanToPoints({
      angle_min: -Math.PI / 2,
      angle_inc: Math.PI / 2,
      range_max: 12,
      ranges: [3, 0.8, 2],
    });
    expect(p.nearest?.dist).toBe(0.8);
    near(p.nearest?.angle ?? 9, 0);
    expect(fmtNearest(p.nearest)).toBe('0.80 m, ahead');
  });

  it('reports no obstacle for an empty scan', () => {
    const p = scanToPoints({ angle_min: 0, angle_inc: 0.1, range_max: 12, ranges: [null, null] });
    expect(p.n).toBe(0);
    expect(p.nearest).toBeNull();
    expect(fmtNearest(null)).toBe('No obstacle in view');
  });
});

describe('transforms', () => {
  const pose = { x: 1, y: 2, yaw: Math.PI / 2 };

  it('robotToWorld rotates by the yaw and adds the position', () => {
    const [x, y] = robotToWorld(pose, 1, 0); // 1 m ahead of a robot facing +y
    near(x, 1);
    near(y, 3);
  });

  const north: View = {
    cx: 0,
    cy: 0,
    scale: 100,
    headingUp: false,
    yaw: 0,
    width: 800,
    height: 600,
  };

  it('map-north: world +y is up on screen', () => {
    const [sx, sy] = worldToScreen(north, 0, 1);
    near(sx, 400);
    near(sy, 200);
  });

  it('heading-up: the robot heading always points up', () => {
    const v: View = { ...north, headingUp: true, yaw: Math.PI / 2 };
    // A robot facing world +y: a point 1 m ahead (world +y) must be above centre.
    const [sx, sy] = worldToScreen(v, 0, 1);
    near(sx, 400);
    near(sy, 200);
    // Facing +x: a point at world +x is above centre.
    const w: View = { ...north, headingUp: true, yaw: 0 };
    const [ax, ay] = worldToScreen(w, 1, 0);
    near(ax, 400);
    near(ay, 200);
    // And the robot's left (world +y when facing +x) is to the left on screen.
    const [lx] = worldToScreen(w, 0, 1);
    expect(lx).toBeLessThan(400);
  });

  it('screenToWorld inverts worldToScreen in both orientations', () => {
    for (const headingUp of [false, true]) {
      const v: View = { ...north, cx: 3, cy: -2, headingUp, yaw: 0.7 };
      const [sx, sy] = worldToScreen(v, 4.2, 1.1);
      const [wx, wy] = screenToWorld(v, sx, sy);
      near(wx, 4.2);
      near(wy, 1.1);
    }
  });

  it('zoomAt keeps the point under the cursor fixed and respects the limits', () => {
    const v: View = { ...north, cx: 1, cy: 1 };
    const before = screenToWorld(v, 600, 150);
    const z = zoomAt(v, 2, 600, 150);
    expect(z.scale).toBe(200);
    const after = screenToWorld(z, 600, 150);
    near(after[0], before[0]);
    near(after[1], before[1]);
    expect(zoomAt({ ...v, scale: 600 }, 2, 0, 0).scale).toBe(600);
    expect(clampScale(1)).toBe(15);
  });

  it('panBy moves the content with the drag', () => {
    const v = north;
    const p = panBy(v, 100, 0); // drag right: content moves right, so the view centre moves left
    expect(p.cx).toBeCloseTo(-1);
    const [sx] = worldToScreen(p, 0, 0);
    near(sx, 500);
  });
});

describe('rings', () => {
  it('uses 0.5 m steps when there is room and widens when zoomed out', () => {
    expect(ringStep(120)).toBe(0.5);
    expect(ringStep(60)).toBe(1);
    expect(ringStep(30)).toBe(2);
    expect(ringStep(16)).toBe(5);
  });

  it('lists radii up to the canvas corner and formats labels', () => {
    const r = ringRadii(0.5, 100, 300);
    expect(r[0]).toBe(0.5);
    expect(r.length).toBeGreaterThanOrEqual(6);
    expect(fmtRing(0.5)).toBe('0.5 m');
    expect(fmtRing(2)).toBe('2 m');
  });
});

describe('trail', () => {
  it('adds points only after the robot moved and caps the length', () => {
    const t: number[] = [];
    expect(pushTrail(t, 0, 0, 3)).toBe(true);
    expect(pushTrail(t, 0.005, 0, 3)).toBe(false);
    expect(pushTrail(t, 0.1, 0, 3)).toBe(true);
    expect(pushTrail(t, 0.2, 0, 3)).toBe(true);
    expect(pushTrail(t, 0.3, 0, 3)).toBe(true);
    expect(t.length / 2).toBe(3);
    expect(t[0]).toBe(0.1); // oldest point dropped
  });
});

describe('words', () => {
  it('names bearings', () => {
    expect(bearingWord(0)).toBe('ahead');
    expect(bearingWord(Math.PI / 2)).toBe('left');
    expect(bearingWord(-Math.PI / 2)).toBe('right');
    expect(bearingWord(Math.PI)).toBe('behind');
    expect(bearingWord(Math.PI / 4)).toBe('ahead left');
    expect(bearingWord((-3 * Math.PI) / 4)).toBe('behind right');
  });

  it('says that the lidar is off while docked and that this is normal', () => {
    const note = noScanNote({ connected: true, docked: true, everScan: false });
    expect(note).toContain('docked');
    expect(note).toContain('normal');
    expect(noScanNote({ connected: false, docked: null, everScan: false })).toContain(
      'Not connected',
    );
    expect(noScanNote({ connected: true, docked: false, everScan: true })).toContain('dimmed');
  });

  it('treats a scan older than 1 s, or none yet, as stale', () => {
    expect(isScanStale(0, 5000)).toBe(true);
    expect(isScanStale(4500, 5000)).toBe(false);
    expect(isScanStale(3900, 5000)).toBe(true);
  });
});
