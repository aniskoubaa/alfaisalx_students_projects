import { useEffect, useRef } from 'react';

/** Monospace output of a program. Follows new lines when `follow` is true. */
export function OutputLog({
  lines,
  label,
  empty,
  follow = true,
  tall,
}: {
  lines: string[] | null;
  label: string;
  /** Shown when there is nothing to show yet. */
  empty: string;
  follow?: boolean;
  tall?: boolean;
}) {
  const ref = useRef<HTMLPreElement>(null);
  const text = lines && lines.length ? lines.join('\n') : null;
  useEffect(() => {
    const el = ref.current;
    if (el && follow) el.scrollTop = el.scrollHeight;
  }, [text, follow]);
  return (
    <pre
      ref={ref}
      className={'output' + (tall ? ' output-tall' : '') + (text ? '' : ' output-empty')}
      tabIndex={0}
      aria-label={label}
      aria-live="off"
    >
      {text ?? empty}
    </pre>
  );
}
