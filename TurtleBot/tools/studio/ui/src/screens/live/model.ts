/**
 * State and drawing of the Live canvas. Lives outside React: scan and pose events write into it,
 * a requestAnimationFrame loop draws it. React only owns the buttons around the canvas.
 */
import type { PoseEvent, ScanEvent } from '../../api';
import {
  DEFAULT_SCALE,
  ROBOT_RADIUS_M,
  fmtRing,
  isScanStale,
  panBy,
  pushTrail,
  ringRadii,
  ringStep,
  robotToWorld,
  scanToPoints,
  worldToScreen,
  zoomAt,
} from './scan';
import type { Pose, ScanPoints, View } from './scan';

export const TRAIL_CAP = 4000;

export interface Palette {
  bg: string;
  ring: string;
  label: string;
  point: string;
  trail: string;
  robot: string;
  onRobot: string;
  caution: string;
  ink: string;
}

export function readPalette(el: Element = document.documentElement): Palette {
  const cs = getComputedStyle(el);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  return {
    bg: v('--surface-2', '#f5f7f9'),
    ring: v('--line-strong', '#aeb8c5'),
    label: v('--muted', '#5a6676'),
    point: v('--ink', '#18212b'),
    trail: v('--signal', '#1d5bd6'),
    robot: v('--signal', '#1d5bd6'),
    onRobot: v('--on-signal', '#ffffff'),
    caution: v('--amber', '#d99a00'),
    ink: v('--ink', '#18212b'),
  };
}

export interface ModelSnapshot {
  lastScanAt: number;
  lastPoseAt: number;
  scanHz: number;
  pose: Pose | null;
  vx: number;
  wz: number;
  nearest: ScanPoints['nearest'];
  points: number;
  trailPoints: number;
}

export class LiveModel {
  scale = DEFAULT_SCALE;
  follow = true;
  headingUp = true;
  /** Centre of the view in the world frame while not following. */
  centre: [number, number] = [0, 0];

  pose: Pose | null = null;
  lastPoseAt = 0;
  vx = 0;
  wz = 0;
  scan: ScanPoints | null = null;
  scanPose: Pose = { x: 0, y: 0, yaw: 0 };
  lastScanAt = 0;
  trail: number[] = [];
  /** Moving average of the scan rate, from arrival times. */
  scanHz = 0;
  dirty = true;
  private scanTimes: number[] = [];

  /** `now` is Date.now() (the caller can pass a fake clock in tests). */
  onScan(ev: ScanEvent, now = Date.now()): void {
    this.scan = scanToPoints(ev);
    this.scanPose = this.pose ?? { x: 0, y: 0, yaw: 0 };
    this.lastScanAt = now;
    this.scanTimes.push(now);
    while (this.scanTimes.length > 8) this.scanTimes.shift();
    if (this.scanTimes.length >= 2) {
      const span =
        (this.scanTimes[this.scanTimes.length - 1] as number) - (this.scanTimes[0] as number);
      this.scanHz = span > 0 ? ((this.scanTimes.length - 1) * 1000) / span : 0;
    }
    this.dirty = true;
  }

  onPose(ev: PoseEvent, now = Date.now()): void {
    this.pose = { x: ev.x, y: ev.y, yaw: ev.yaw };
    this.lastPoseAt = now;
    this.vx = ev.vx;
    this.wz = ev.wz;
    pushTrail(this.trail, ev.x, ev.y, TRAIL_CAP);
    this.dirty = true;
  }

  /** Ask for a redraw on the next frame. */
  touch(): void {
    this.dirty = true;
  }

  clearTrail(): void {
    this.trail.length = 0;
    if (this.pose) this.trail.push(this.pose.x, this.pose.y);
    this.dirty = true;
  }

  setFollow(v: boolean, width: number, height: number): void {
    if (v === this.follow) return;
    if (!v) {
      // Freeze the view where it is.
      const view = this.view(width, height);
      this.centre = [view.cx, view.cy];
    }
    this.follow = v;
    this.dirty = true;
  }

  setHeadingUp(v: boolean): void {
    this.headingUp = v;
    this.dirty = true;
  }

  view(width: number, height: number): View {
    const p = this.pose ?? { x: 0, y: 0, yaw: 0 };
    const [cx, cy] = this.follow ? [p.x, p.y] : this.centre;
    return {
      cx,
      cy,
      scale: this.scale,
      headingUp: this.headingUp,
      yaw: p.yaw,
      width,
      height,
    };
  }

  zoom(factor: number, width: number, height: number, sx = width / 2, sy = height / 2): void {
    const next = zoomAt(this.view(width, height), factor, sx, sy);
    this.scale = next.scale;
    if (!this.follow) this.centre = [next.cx, next.cy];
    this.dirty = true;
  }

  /** Drag by (dx, dy) pixels. Returns true when this turned follow mode off. */
  pan(dx: number, dy: number, width: number, height: number): boolean {
    const turnedOff = this.follow;
    if (this.follow) this.setFollow(false, width, height);
    const next = panBy(this.view(width, height), dx, dy);
    this.centre = [next.cx, next.cy];
    this.dirty = true;
    return turnedOff;
  }

  snapshot(): ModelSnapshot {
    return {
      lastScanAt: this.lastScanAt,
      lastPoseAt: this.lastPoseAt,
      scanHz: this.scanHz,
      pose: this.pose,
      vx: this.vx,
      wz: this.wz,
      nearest: this.scan?.nearest ?? null,
      points: this.scan?.n ?? 0,
      trailPoints: this.trail.length / 2,
    };
  }

  isStale(now: number): boolean {
    return isScanStale(this.lastScanAt, now);
  }

  /** Draw everything. `width`/`height` are CSS pixels; the context is already scaled by dpr. */
  draw(
    ctx: CanvasRenderingContext2D,
    width: number,
    height: number,
    pal: Palette,
    now = Date.now(),
  ): void {
    const stale = this.isStale(now);
    const view = this.view(width, height);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = pal.bg;
    ctx.fillRect(0, 0, width, height);

    const robot = this.pose ?? { x: 0, y: 0, yaw: 0 };
    const [rx, ry] = worldToScreen(view, robot.x, robot.y);

    this.drawRings(ctx, view, rx, ry, pal);
    this.drawTrail(ctx, view, pal);
    if (this.scan && this.scan.n > 0) this.drawScan(ctx, view, pal, stale);
    this.drawRobot(ctx, view, robot, rx, ry, pal);
    this.drawCompass(ctx, view, width, pal);
    this.dirty = false;
  }

  private drawRings(
    ctx: CanvasRenderingContext2D,
    view: View,
    rx: number,
    ry: number,
    pal: Palette,
  ): void {
    const step = ringStep(view.scale);
    const half = Math.hypot(view.width, view.height);
    ctx.lineWidth = 1;
    ctx.strokeStyle = pal.ring;
    ctx.fillStyle = pal.label;
    ctx.font = '12px "IBM Plex Sans", system-ui, sans-serif';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    ctx.globalAlpha = 0.55;
    // Forward axis and side axis through the robot.
    const [ax, ay] = worldToScreen(
      view,
      (this.pose?.x ?? 0) + Math.cos(this.pose?.yaw ?? 0),
      (this.pose?.y ?? 0) + Math.sin(this.pose?.yaw ?? 0),
    );
    const dx = ax - rx;
    const dy = ay - ry;
    const len = Math.hypot(dx, dy) || 1;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(rx - (dx / len) * half, ry - (dy / len) * half);
    ctx.lineTo(rx + (dx / len) * half, ry + (dy / len) * half);
    ctx.moveTo(rx + (dy / len) * half, ry - (dx / len) * half);
    ctx.lineTo(rx - (dy / len) * half, ry + (dx / len) * half);
    ctx.stroke();
    ctx.setLineDash([]);
    for (const r of ringRadii(step, view.scale, half / 2)) {
      const px = r * view.scale;
      ctx.beginPath();
      ctx.arc(rx, ry, px, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // Labels on the upper right diagonal, with a halo so they stay readable over points.
    ctx.lineJoin = 'round';
    ctx.lineWidth = 4;
    for (const r of ringRadii(step, view.scale, half / 2)) {
      const px = r * view.scale;
      const lx = rx + px * Math.SQRT1_2 + 3;
      const ly = ry - px * Math.SQRT1_2;
      if (lx < -40 || lx > view.width + 40 || ly < -10 || ly > view.height + 10) continue;
      const text = fmtRing(r);
      ctx.strokeStyle = pal.bg;
      ctx.strokeText(text, lx, ly);
      ctx.fillText(text, lx, ly);
    }
    ctx.lineWidth = 1;
  }

  private drawTrail(ctx: CanvasRenderingContext2D, view: View, pal: Palette): void {
    const t = this.trail;
    if (t.length < 4) return;
    ctx.strokeStyle = pal.trail;
    ctx.globalAlpha = 0.75;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (let i = 0; i < t.length; i += 2) {
      const [sx, sy] = worldToScreen(view, t[i] as number, t[i + 1] as number);
      if (i === 0) ctx.moveTo(sx, sy);
      else ctx.lineTo(sx, sy);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  private drawScan(ctx: CanvasRenderingContext2D, view: View, pal: Palette, stale: boolean): void {
    const scan = this.scan as ScanPoints;
    ctx.globalAlpha = stale ? 0.22 : 0.9;
    ctx.fillStyle = pal.point;
    const size = 3;
    for (let i = 0; i < scan.n; i++) {
      const [wx, wy] = robotToWorld(this.scanPose, scan.x[i] as number, scan.y[i] as number);
      const [sx, sy] = worldToScreen(view, wx, wy);
      ctx.fillRect(sx - size / 2, sy - size / 2, size, size);
    }
    ctx.globalAlpha = 1;
    const n = scan.nearest;
    if (n && !stale) {
      const [wx, wy] = robotToWorld(this.scanPose, n.x, n.y);
      const [sx, sy] = worldToScreen(view, wx, wy);
      const robot = this.pose ?? this.scanPose;
      const [rx, ry] = worldToScreen(view, robot.x, robot.y);
      ctx.strokeStyle = pal.caution;
      ctx.fillStyle = pal.caution;
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(rx, ry);
      ctx.lineTo(sx, sy);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(sx, sy, 6, 0, Math.PI * 2);
      ctx.stroke();
      ctx.lineWidth = 1;
    }
  }

  private drawRobot(
    ctx: CanvasRenderingContext2D,
    view: View,
    robot: Pose,
    rx: number,
    ry: number,
    pal: Palette,
  ): void {
    const radius = Math.max(9, ROBOT_RADIUS_M * view.scale);
    // Heading on screen.
    const [hx, hy] = worldToScreen(
      view,
      robot.x + Math.cos(robot.yaw),
      robot.y + Math.sin(robot.yaw),
    );
    const ang = Math.atan2(hy - ry, hx - rx);
    ctx.fillStyle = pal.robot;
    ctx.globalAlpha = 0.22;
    ctx.beginPath();
    ctx.arc(rx, ry, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = pal.robot;
    ctx.lineWidth = 2;
    ctx.stroke();
    // Wedge pointing the way the robot faces.
    ctx.fillStyle = pal.robot;
    ctx.beginPath();
    ctx.moveTo(rx + Math.cos(ang) * radius * 1.0, ry + Math.sin(ang) * radius * 1.0);
    ctx.lineTo(rx + Math.cos(ang + 2.5) * radius * 0.7, ry + Math.sin(ang + 2.5) * radius * 0.7);
    ctx.lineTo(rx + Math.cos(ang - 2.5) * radius * 0.7, ry + Math.sin(ang - 2.5) * radius * 0.7);
    ctx.closePath();
    ctx.fill();
    ctx.lineWidth = 1;
  }

  /** A small north arrow in the top right corner. */
  private drawCompass(
    ctx: CanvasRenderingContext2D,
    view: View,
    width: number,
    pal: Palette,
  ): void {
    const cx = width - 34;
    const cy = 38;
    const [ox, oy] = worldToScreen(view, view.cx, view.cy);
    const [nx, ny] = worldToScreen(view, view.cx, view.cy + 1);
    const ang = Math.atan2(ny - oy, nx - ox);
    ctx.strokeStyle = pal.label;
    ctx.fillStyle = pal.label;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, 16, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(ang) * 13, cy + Math.sin(ang) * 13);
    ctx.lineTo(cx + Math.cos(ang + 2.6) * 8, cy + Math.sin(ang + 2.6) * 8);
    ctx.lineTo(cx + Math.cos(ang - 2.6) * 8, cy + Math.sin(ang - 2.6) * 8);
    ctx.closePath();
    ctx.fill();
    ctx.font = '600 11px "IBM Plex Sans", system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('N', cx + Math.cos(ang) * 25, cy + Math.sin(ang) * 25);
    ctx.lineWidth = 1;
  }
}
