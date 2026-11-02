import { useCallback, useRef } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { axis } from './controller';
import { setStick } from './driver';

/**
 * On-screen stick. Up drives forward, left turns left. Letting go (or losing the pointer for any
 * reason) sends zero at once. The knob moves through a ref, so dragging never re-renders React.
 * Keyboard: with driving armed, W A S D and the arrow keys work anywhere on the Live screen,
 * including while this control has focus.
 */
export function Joystick({ enabled }: { enabled: boolean }) {
  const base = useRef<HTMLDivElement>(null);
  const knob = useRef<HTMLDivElement>(null);
  const active = useRef<number | null>(null);

  const place = useCallback((nx: number, ny: number) => {
    const k = knob.current;
    if (!k) return;
    const r = (base.current?.clientWidth ?? 160) / 2;
    const pad = 24;
    k.style.transform = `translate(${nx * (r - pad)}px, ${ny * (r - pad)}px)`;
  }, []);

  const move = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const el = base.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const r = rect.width / 2;
      let dx = (e.clientX - (rect.left + r)) / r;
      let dy = (e.clientY - (rect.top + r)) / r;
      const len = Math.hypot(dx, dy);
      if (len > 1) {
        dx /= len;
        dy /= len;
      }
      place(dx, dy);
      setStick(axis(-dy), axis(-dx));
    },
    [place],
  );

  const end = useCallback(() => {
    active.current = null;
    place(0, 0);
    setStick(0, 0);
  }, [place]);

  return (
    <div
      ref={base}
      className={'stick' + (enabled ? '' : ' is-off')}
      role="group"
      aria-label="Drive stick"
      aria-describedby="stick-help"
      aria-disabled={!enabled}
      tabIndex={enabled ? 0 : -1}
      onPointerDown={(e) => {
        if (!enabled || active.current !== null) return;
        active.current = e.pointerId;
        e.currentTarget.setPointerCapture(e.pointerId);
        move(e);
      }}
      onPointerMove={(e) => {
        if (active.current === e.pointerId) move(e);
      }}
      onPointerUp={(e) => {
        if (active.current === e.pointerId) end();
      }}
      onPointerCancel={(e) => {
        if (active.current === e.pointerId) end();
      }}
      onLostPointerCapture={(e) => {
        if (active.current === e.pointerId) end();
      }}
    >
      <span className="stick-mark stick-up" aria-hidden="true">
        Forward
      </span>
      <span className="stick-mark stick-down" aria-hidden="true">
        Back
      </span>
      <span className="stick-mark stick-left" aria-hidden="true">
        Left
      </span>
      <span className="stick-mark stick-right" aria-hidden="true">
        Right
      </span>
      <div ref={knob} className="stick-knob" aria-hidden="true" />
      <p id="stick-help" className="sr-only">
        Drag to drive, release to stop. Or hold W, A, S, D or the arrow keys.
      </p>
    </div>
  );
}
