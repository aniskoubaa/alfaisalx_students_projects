import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { visibleRange } from './logFilter';
import type { LogLine } from './logFilter';

export const ROW_HEIGHT = 22;

const MARK: Record<LogLine['level'], string | null> = { error: 'error', warn: 'warn', info: null };

/**
 * A long list of fixed-height monospace rows. Only the rows in view (plus a few) are in the page,
 * so 2000 lines scroll smoothly. Warnings and errors have a word as well as a tint.
 */
export function VirtualLines({
  lines,
  scrollKey,
  label,
}: {
  lines: readonly LogLine[];
  /** Changes when a new fetch arrives: the view then jumps to the newest line. */
  scrollKey: number;
  label: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const [height, setHeight] = useState(480);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => setHeight(el.clientHeight);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scrollKey]);

  const { start, end } = visibleRange(top, height, ROW_HEIGHT, lines.length);
  const digits = String(lines.length).length;

  return (
    <div
      ref={box}
      className="logbox"
      role="region"
      aria-label={label}
      tabIndex={0}
      onScroll={(e) => setTop(e.currentTarget.scrollTop)}
    >
      <div style={{ height: start * ROW_HEIGHT }} aria-hidden="true" />
      {lines.slice(start, end).map((l) => (
        <div key={l.n} className={'logline logline-' + l.level} style={{ height: ROW_HEIGHT }}>
          <span className="logline-n" style={{ minWidth: digits + 'ch' }} aria-hidden="true">
            {l.n}
          </span>
          <span className="logline-mark">{MARK[l.level] ?? ''}</span>
          <span className="logline-text">{l.text}</span>
        </div>
      ))}
      <div style={{ height: Math.max(0, lines.length - end) * ROW_HEIGHT }} aria-hidden="true" />
    </div>
  );
}
