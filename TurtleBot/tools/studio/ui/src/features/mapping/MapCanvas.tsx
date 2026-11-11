import { Crosshair, Maximize, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button, IconButton } from '../../components/ui';
import { ROBOT_RADIUS_M, isScanStale, robotToWorld, worldToScreen } from '../../screens/live/scan';
import type { Pose } from '../../screens/live/scan';
import { readPalette } from '../../screens/live/model';
import type { Palette } from '../../screens/live/model';
import { knownCellsSummary, mapSizeText } from './model';
import { useMapping } from './store';
import { MapViewState, imageRect } from './view';

function drawFrame(
  ctx: CanvasRenderingContext2D,
  vs: MapViewState,
  width: number,
  height: number,
  pal: Palette,
  now: number,
): void {
  const s = useMapping.getState();
  const robot = s.pose;
  const view = vs.view(width, height, robot);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = pal.bg;
  ctx.fillRect(0, 0, width, height);

  if (s.image) {
    const r = imageRect(view, s.image.meta);
    ctx.imageSmoothingEnabled = false;
    try {
      ctx.drawImage(s.image.source, r.x, r.y, r.w, r.h);
    } catch {
      /* the picture was closed while a newer one is on its way */
    }
    ctx.strokeStyle = pal.ring;
    ctx.lineWidth = 1;
    ctx.strokeRect(r.x, r.y, r.w, r.h);
  }

  // Lidar points, moved from the robot frame into the map frame by the pose of the scan.
  const scan = s.scan;
  if (scan && scan.n > 0 && s.scanPose) {
    const stale = isScanStale(s.scanAt, now);
    ctx.globalAlpha = stale ? 0.2 : 0.9;
    ctx.fillStyle = pal.caution;
    for (let i = 0; i < scan.n; i++) {
      const [wx, wy] = robotToWorld(s.scanPose, scan.x[i] as number, scan.y[i] as number);
      const [sx, sy] = worldToScreen(view, wx, wy);
      ctx.fillRect(sx - 1.5, sy - 1.5, 3, 3);
    }
    ctx.globalAlpha = 1;
  }

  if (robot) drawRobot(ctx, view.scale, robot, worldToScreen(view, robot.x, robot.y), pal, view);
}

function drawRobot(
  ctx: CanvasRenderingContext2D,
  scale: number,
  robot: Pose,
  [rx, ry]: [number, number],
  pal: Palette,
  view: Parameters<typeof worldToScreen>[0],
): void {
  const radius = Math.max(9, ROBOT_RADIUS_M * scale);
  const [hx, hy] = worldToScreen(
    view,
    robot.x + Math.cos(robot.yaw),
    robot.y + Math.sin(robot.yaw),
  );
  const ang = Math.atan2(hy - ry, hx - rx);
  ctx.fillStyle = pal.robot;
  ctx.globalAlpha = 0.25;
  ctx.beginPath();
  ctx.arc(rx, ry, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.strokeStyle = pal.robot;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(rx + Math.cos(ang) * radius, ry + Math.sin(ang) * radius);
  ctx.lineTo(rx + Math.cos(ang + 2.5) * radius * 0.7, ry + Math.sin(ang + 2.5) * radius * 0.7);
  ctx.lineTo(rx + Math.cos(ang - 2.5) * radius * 0.7, ry + Math.sin(ang - 2.5) * radius * 0.7);
  ctx.closePath();
  ctx.fill();
  ctx.lineWidth = 1;
}

/** The map picture with the robot and the lidar points, plus zoom, follow and fit buttons. */
export function MapCanvas() {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const size = useRef({ width: 800, height: 600 });
  const [vs] = useState(() => new MapViewState());
  const [follow, setFollow] = useState(false);
  const seq = useMapping((s) => s.image?.seq ?? null);
  const meta = useMapping((s) => s.image?.meta ?? null);
  const known = useMapping((s) => s.image?.known ?? null);
  const fetchError = useMapping((s) => s.fetchError);

  // Show the whole map the first time one arrives.
  const fitted = useRef<number | null>(null);
  useEffect(() => {
    if (meta === null) {
      fitted.current = null;
      return;
    }
    if (fitted.current === null) {
      fitted.current = meta.seq;
      vs.fit(meta, size.current.width, size.current.height);
      setFollow(false);
    }
  }, [meta, vs]);

  useEffect(() => {
    const el = canvas.current;
    const box = wrap.current;
    if (!el || !box) return;
    const ctx = el.getContext('2d');
    if (!ctx) return;
    const st = { pal: readPalette() as Palette, width: 0, height: 0, raf: 0 };

    const resize = () => {
      const r = box.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      st.width = Math.max(1, Math.round(r.width));
      st.height = Math.max(1, Math.round(r.height));
      el.width = Math.round(st.width * dpr);
      el.height = Math.round(st.height * dpr);
      el.style.width = st.width + 'px';
      el.style.height = st.height + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      size.current = { width: st.width, height: st.height };
      vs.touch();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);

    const repal = () => {
      st.pal = readPalette();
      vs.touch();
    };
    const mo = new MutationObserver(repal);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', repal);
    const unsub = useMapping.subscribe(() => vs.touch());

    let lastStale: boolean | null = null;
    const frame = () => {
      st.raf = requestAnimationFrame(frame);
      const now = Date.now();
      const stale = isScanStale(useMapping.getState().scanAt, now);
      if (stale !== lastStale) {
        lastStale = stale;
        vs.touch();
      }
      if (vs.dirty) {
        drawFrame(ctx, vs, st.width, st.height, st.pal, now);
        vs.dirty = false;
      }
    };
    st.raf = requestAnimationFrame(frame);

    const robot = () => useMapping.getState().pose;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      vs.zoom(
        Math.exp(-e.deltaY * 0.0015),
        st.width,
        st.height,
        robot(),
        e.clientX - r.left,
        e.clientY - r.top,
      );
    };
    el.addEventListener('wheel', onWheel, { passive: false });

    const pts = new Map<number, { x: number; y: number }>();
    let pinch = 0;
    const dist = () => {
      const [a, b] = [...pts.values()];
      return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
    };
    const onDown = (e: PointerEvent) => {
      el.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 2) pinch = dist();
    };
    const onMove = (e: PointerEvent) => {
      const p = pts.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x;
      const dy = e.clientY - p.y;
      p.x = e.clientX;
      p.y = e.clientY;
      if (pts.size === 1) {
        if (vs.pan(dx, dy, st.width, st.height, robot())) setFollow(false);
      } else if (pts.size === 2) {
        const d = dist();
        if (pinch > 0 && d > 0) {
          const [a, b] = [...pts.values()];
          const r = el.getBoundingClientRect();
          vs.zoom(
            d / pinch,
            st.width,
            st.height,
            robot(),
            ((a?.x ?? 0) + (b?.x ?? 0)) / 2 - r.left,
            ((a?.y ?? 0) + (b?.y ?? 0)) / 2 - r.top,
          );
        }
        pinch = d;
      }
    };
    const onUp = (e: PointerEvent) => {
      pts.delete(e.pointerId);
      pinch = pts.size === 2 ? dist() : 0;
    };
    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onUp);

    return () => {
      cancelAnimationFrame(st.raf);
      ro.disconnect();
      mo.disconnect();
      mq.removeEventListener('change', repal);
      unsub();
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
    };
  }, [vs]);

  const zoom = (f: number) =>
    vs.zoom(f, size.current.width, size.current.height, useMapping.getState().pose);

  return (
    <div className="map-stage">
      <div className="live-toolbar" role="toolbar" aria-label="Map view controls">
        <IconButton
          label="Zoom out"
          icon={<ZoomOut size={18} aria-hidden="true" />}
          variant="secondary"
          onClick={() => zoom(0.8)}
        />
        <IconButton
          label="Zoom in"
          icon={<ZoomIn size={18} aria-hidden="true" />}
          variant="secondary"
          onClick={() => zoom(1.25)}
        />
        <Button
          icon={<Crosshair size={16} aria-hidden="true" />}
          aria-pressed={follow}
          onClick={() => {
            const v = !follow;
            vs.setFollow(v, size.current.width, size.current.height, useMapping.getState().pose);
            setFollow(v);
          }}
        >
          {follow ? 'Following robot' : 'Free view'}
        </Button>
        <Button
          icon={<Maximize size={16} aria-hidden="true" />}
          disabled={!meta}
          onClick={() => {
            const m = useMapping.getState().image?.meta;
            if (m) vs.fit(m, size.current.width, size.current.height);
            setFollow(false);
          }}
        >
          Fit map
        </Button>
        {meta ? (
          <span className="map-info dim small" data-testid="map-info">
            {known !== null
              ? knownCellsSummary(known, meta.width * meta.height, meta.resolution, meta)
              : `Map size ${mapSizeText(meta)}.`}
          </span>
        ) : null}
      </div>
      <div ref={wrap} className="live-canvas-wrap map-canvas-wrap">
        <canvas
          ref={canvas}
          className="live-canvas"
          data-testid="map-canvas"
          data-map-seq={seq === null ? '' : String(seq)}
          role="img"
          aria-label="Top-down map of the place the robot is mapping, with the robot and its lidar points. Drag to move the view, scroll or pinch to zoom."
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === '+' || e.key === '=') zoom(1.25);
            else if (e.key === '-' || e.key === '_') zoom(0.8);
          }}
        />
        {!meta ? (
          <p className="map-empty" role="status">
            No map yet. Start mapping to build one.
          </p>
        ) : null}
        {fetchError ? (
          <p className="map-error" role="alert">
            Could not load the map picture. {fetchError}
          </p>
        ) : null}
      </div>
    </div>
  );
}
