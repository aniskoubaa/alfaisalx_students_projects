/**
 * Pure geometry for the Live view: scan -> points, robot/world/screen transforms, rings, trail.
 * Conventions: robot frame x forward, y left (angle 0 = ahead, counter-clockwise positive);
 * world (odom) frame x, y with yaw counter-clockwise; screen pixels with y pointing down.
 */

export interface ScanFrame {
  angle_min: number;
  angle_inc: number;
  range_max: number;
  ranges: ReadonlyArray<number | null>;
}

export interface Pose {
  x: number;
  y: number;
  yaw: number;
}

export interface ScanPoints {
  /** Robot-frame coordinates in metres, `n` valid points. */
  x: Float32Array;
  y: Float32Array;
  n: number;
  nearest: Nearest | null;
}

export interface Nearest {
  /** Metres. */
  dist: number;
  /** Radians in the robot frame (0 ahead, positive to the left). */
  angle: number;
  x: number;
  y: number;
}

/** The TurtleBot 4 base is a disc of about 0.34 m diameter. */
export const ROBOT_RADIUS_M = 0.17;
/** Returns closer than this are the robot's own body or noise. */
export const MIN_RANGE_M = 0.05;

export function scanToPoints(scan: ScanFrame): ScanPoints {
  const len = scan.ranges.length;
  const x = new Float32Array(len);
  const y = new Float32Array(len);
  let n = 0;
  let nearest: Nearest | null = null;
  for (let i = 0; i < len; i++) {
    const r = scan.ranges[i];
    if (r === null || r === undefined || !Number.isFinite(r)) continue;
    if (r < MIN_RANGE_M || (scan.range_max > 0 && r > scan.range_max)) continue;
    const a = scan.angle_min + i * scan.angle_inc;
    const px = r * Math.cos(a);
    const py = r * Math.sin(a);
    x[n] = px;
    y[n] = py;
    n++;
    if (!nearest || r < nearest.dist) nearest = { dist: r, angle: a, x: px, y: py };
  }
  return { x, y, n, nearest };
}

/** A point in the robot frame to the world frame, for a robot at `pose`. */
export function robotToWorld(pose: Pose, x: number, y: number): [number, number] {
  const c = Math.cos(pose.yaw);
  const s = Math.sin(pose.yaw);
  return [pose.x + x * c - y * s, pose.y + x * s + y * c];
}

export interface View {
  /** World point shown at the middle of the canvas. */
  cx: number;
  cy: number;
  /** Pixels per metre. */
  scale: number;
  /** When true, the robot's heading points up on screen. When false, world +y is up. */
  headingUp: boolean;
  /** Robot heading, used only when `headingUp`. */
  yaw: number;
  /** CSS pixels. */
  width: number;
  height: number;
}

export const MIN_SCALE = 15;
export const MAX_SCALE = 600;
export const DEFAULT_SCALE = 90;

export const clampScale = (s: number): number => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

/** Rotation applied to world offsets so that the chosen direction points up. */
function rotation(v: View): number {
  return v.headingUp ? Math.PI / 2 - v.yaw : 0;
}

export function worldToScreen(v: View, wx: number, wy: number): [number, number] {
  const dx = wx - v.cx;
  const dy = wy - v.cy;
  const phi = rotation(v);
  const c = Math.cos(phi);
  const s = Math.sin(phi);
  const ux = dx * c - dy * s;
  const uy = dx * s + dy * c;
  return [v.width / 2 + ux * v.scale, v.height / 2 - uy * v.scale];
}

export function screenToWorld(v: View, sx: number, sy: number): [number, number] {
  const ux = (sx - v.width / 2) / v.scale;
  const uy = (v.height / 2 - sy) / v.scale;
  const phi = -rotation(v);
  const c = Math.cos(phi);
  const s = Math.sin(phi);
  return [v.cx + ux * c - uy * s, v.cy + ux * s + uy * c];
}

/** Zoom by `factor` keeping the world point under screen position (sx, sy) fixed. */
export function zoomAt(v: View, factor: number, sx: number, sy: number): View {
  const scale = clampScale(v.scale * factor);
  if (scale === v.scale) return v;
  const [wx, wy] = screenToWorld(v, sx, sy);
  const next: View = { ...v, scale };
  const [nx, ny] = screenToWorld(next, sx, sy);
  return { ...next, cx: v.cx + (wx - nx), cy: v.cy + (wy - ny) };
}

/** Move the view so the content follows a drag of (dx, dy) screen pixels. */
export function panBy(v: View, dx: number, dy: number): View {
  const [ax, ay] = screenToWorld(v, 0, 0);
  const [bx, by] = screenToWorld(v, dx, dy);
  return { ...v, cx: v.cx + (ax - bx), cy: v.cy + (ay - by) };
}

/** Metres between range rings: 0.5 m when there is room, wider when zoomed out. */
export function ringStep(scale: number): number {
  const minPx = 46;
  for (const step of [0.5, 1, 2, 5, 10]) if (step * scale >= minPx) return step;
  return 20;
}

/** Radii (metres) of the rings that fit in a canvas of the given half-diagonal. */
export function ringRadii(step: number, scale: number, halfDiagonalPx: number): number[] {
  const out: number[] = [];
  const max = halfDiagonalPx / scale;
  for (let r = step; r <= max + step && out.length < 60; r += step)
    out.push(Math.round(r * 100) / 100);
  return out;
}

export function fmtRing(r: number): string {
  return (Number.isInteger(r) ? r.toFixed(0) : r.toFixed(1)) + ' m';
}

/**
 * Add a point to a flat [x0, y0, x1, y1, ...] trail when the robot moved at least `minDist` since
 * the last point. Drops the oldest points beyond `cap` points. Returns true when a point was added.
 */
export function pushTrail(
  trail: number[],
  x: number,
  y: number,
  cap: number,
  minDist = 0.02,
): boolean {
  const n = trail.length;
  if (n >= 2) {
    const dx = x - (trail[n - 2] as number);
    const dy = y - (trail[n - 1] as number);
    if (dx * dx + dy * dy < minDist * minDist) return false;
  }
  trail.push(x, y);
  const extra = trail.length / 2 - cap;
  if (extra > 0) trail.splice(0, extra * 2);
  return true;
}

export function bearingWord(angle: number): string {
  const deg = (((angle * 180) / Math.PI + 540) % 360) - 180; // -180..180
  const a = Math.abs(deg);
  if (a <= 22.5) return 'ahead';
  if (a >= 157.5) return 'behind';
  const side = deg > 0 ? 'left' : 'right';
  if (a < 67.5) return 'ahead ' + side;
  if (a <= 112.5) return side;
  return 'behind ' + side;
}

export function fmtNearest(n: Nearest | null): string {
  if (!n) return 'No obstacle in view';
  return `${n.dist.toFixed(2)} m, ${bearingWord(n.angle)}`;
}

/** What the person should read when there is no fresh scan. */
export function noScanNote(opts: {
  connected: boolean;
  docked: boolean | null;
  everScan: boolean;
}): string {
  if (!opts.connected) return 'Not connected to the robot.';
  if (opts.docked === true)
    return 'No lidar data. The lidar is off while the robot is docked. That is normal.';
  return opts.everScan
    ? 'No lidar data. The last scan is shown dimmed.'
    : 'No lidar data yet. Waiting for the first scan.';
}

/** Scan is stale when nothing arrived for more than `limitMs`. */
export const SCAN_STALE_MS = 1000;
export const isScanStale = (lastAt: number, now: number, limitMs = SCAN_STALE_MS): boolean =>
  lastAt === 0 || now - lastAt > limitMs;
