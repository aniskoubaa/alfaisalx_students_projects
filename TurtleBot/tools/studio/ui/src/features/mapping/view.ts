/**
 * View state of the map canvas (zoom, centre, follow) and the geometry that draws one frame.
 * North is up. Reuses the Live view maths (screens/live/scan.ts).
 */
import { DEFAULT_SCALE, clampScale, panBy, worldToScreen, zoomAt } from '../../screens/live/scan';
import type { Pose, View } from '../../screens/live/scan';
import { fitMap } from './model';
import type { GridGeometry } from './model';

export class MapViewState {
  scale = DEFAULT_SCALE;
  follow = false;
  centre: [number, number] = [0, 0];
  dirty = true;

  view(width: number, height: number, robot: Pose | null): View {
    const [cx, cy] = this.follow && robot ? [robot.x, robot.y] : this.centre;
    return { cx, cy, scale: this.scale, headingUp: false, yaw: 0, width, height };
  }

  touch(): void {
    this.dirty = true;
  }

  zoom(
    factor: number,
    width: number,
    height: number,
    robot: Pose | null,
    sx = width / 2,
    sy = height / 2,
  ): void {
    const next = zoomAt(this.view(width, height, robot), factor, sx, sy);
    this.scale = next.scale;
    if (!(this.follow && robot)) this.centre = [next.cx, next.cy];
    this.dirty = true;
  }

  /** Drag by (dx, dy) pixels. Returns true when this turned follow mode off. */
  pan(dx: number, dy: number, width: number, height: number, robot: Pose | null): boolean {
    const turnedOff = this.follow;
    if (this.follow) this.setFollow(false, width, height, robot);
    const next = panBy(this.view(width, height, robot), dx, dy);
    this.centre = [next.cx, next.cy];
    this.dirty = true;
    return turnedOff;
  }

  setFollow(v: boolean, width: number, height: number, robot: Pose | null): void {
    if (v === this.follow) return;
    if (!v) {
      const view = this.view(width, height, robot);
      this.centre = [view.cx, view.cy];
    }
    this.follow = v;
    this.dirty = true;
  }

  /** Show the whole map. Leaves follow mode. */
  fit(g: GridGeometry, width: number, height: number): void {
    const f = fitMap(g, width, height);
    this.follow = false;
    this.centre = [f.cx, f.cy];
    this.scale = clampScale(f.scale);
    this.dirty = true;
  }
}

/** Where the picture goes on the canvas: its top-left corner and its size in pixels. */
export function imageRect(
  view: View,
  g: GridGeometry,
): { x: number; y: number; w: number; h: number } {
  const [x, y] = worldToScreen(view, g.origin.x, g.origin.y + g.height * g.resolution);
  return { x, y, w: g.width * g.resolution * view.scale, h: g.height * g.resolution * view.scale };
}
