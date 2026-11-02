import { useEffect, useRef } from 'react';
import type { MutableRefObject } from 'react';
import { onStudioEvent } from '../../state/runtime';
import { readPalette } from './model';
import type { LiveModel, ModelSnapshot, Palette } from './model';

interface Props {
  model: LiveModel;
  /** Called at most 5 times a second with the latest numbers, for the readouts. */
  onSnapshot: (s: ModelSnapshot, stale: boolean) => void;
  /** The person dragged the map, which turns follow mode off. */
  onFreePan: () => void;
  sizeRef: MutableRefObject<{ width: number; height: number }>;
}

/**
 * The map. Draws from `model` inside requestAnimationFrame and only when something changed, so
 * React never re-renders per frame. Wheel and pinch zoom, drag to pan.
 */
export function LiveCanvas({ model, onSnapshot, onFreePan, sizeRef }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const snapRef = useRef(onSnapshot);
  const panRef = useRef(onFreePan);
  useEffect(() => {
    snapRef.current = onSnapshot;
    panRef.current = onFreePan;
  });

  useEffect(() => {
    const unsubScan = onStudioEvent('scan', (ev) => model.onScan(ev));
    const unsubPose = onStudioEvent('pose', (ev) => model.onPose(ev));
    return () => {
      unsubScan();
      unsubPose();
    };
  }, [model]);

  useEffect(() => {
    const el = canvas.current;
    const box = wrap.current;
    if (!el || !box) return;
    const ctx = el.getContext('2d');
    if (!ctx) return;
    const st = {
      pal: readPalette() as Palette,
      width: 0,
      height: 0,
      raf: 0,
      lastStale: null as boolean | null,
      lastSnap: 0,
    };

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
      sizeRef.current = { width: st.width, height: st.height };
      model.touch();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);

    // Colours follow the theme: re-read when the theme attribute or the system scheme changes.
    const repal = () => {
      st.pal = readPalette();
      model.touch();
    };
    const mo = new MutationObserver(repal);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', repal);

    const frame = () => {
      st.raf = requestAnimationFrame(frame);
      const now = Date.now();
      const stale = model.isStale(now);
      if (stale !== st.lastStale) {
        st.lastStale = stale;
        model.touch();
      }
      if (model.dirty) model.draw(ctx, st.width, st.height, st.pal, now);
      if (now - st.lastSnap >= 200) {
        st.lastSnap = now;
        snapRef.current(model.snapshot(), stale);
      }
    };
    st.raf = requestAnimationFrame(frame);

    // Wheel zoom needs a non-passive listener to stop the page from scrolling.
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      model.zoom(
        Math.exp(-e.deltaY * 0.0015),
        st.width,
        st.height,
        e.clientX - r.left,
        e.clientY - r.top,
      );
    };
    el.addEventListener('wheel', onWheel, { passive: false });

    // One pointer pans, two pointers pinch.
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
        if (model.pan(dx, dy, st.width, st.height)) panRef.current();
      } else if (pts.size === 2) {
        const d = dist();
        if (pinch > 0 && d > 0) {
          const [a, b] = [...pts.values()];
          const r = el.getBoundingClientRect();
          model.zoom(
            d / pinch,
            st.width,
            st.height,
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
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
    };
  }, [model, sizeRef]);

  return (
    <div ref={wrap} className="live-canvas-wrap">
      <canvas
        ref={canvas}
        className="live-canvas"
        role="img"
        aria-label="Top-down map of the robot, the lidar points around it and its path. Drag to move the view, scroll or pinch to zoom."
        tabIndex={0}
        onKeyDown={(e) => {
          const { width, height } = sizeRef.current;
          if (e.key === '+' || e.key === '=') model.zoom(1.25, width, height);
          else if (e.key === '-' || e.key === '_') model.zoom(0.8, width, height);
        }}
      />
    </div>
  );
}
