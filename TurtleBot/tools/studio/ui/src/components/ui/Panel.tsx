import { useId } from 'react';
import type { HTMLAttributes, ReactNode } from 'react';

export interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title?: ReactNode;
  /** Shown at the right of the heading row. */
  actions?: ReactNode;
  /** Dims the content and shows "Old values". */
  stale?: boolean;
  /** Spans the full width of the grid. */
  wide?: boolean;
}

export function Panel({ title, actions, stale, wide, className, children, ...rest }: PanelProps) {
  const id = useId();
  return (
    <section
      className={['panel', wide ? 'panel-wide' : '', stale ? 'is-stale' : '', className ?? '']
        .filter(Boolean)
        .join(' ')}
      aria-labelledby={title ? id : undefined}
      {...rest}
    >
      {title || actions ? (
        <header className="panel-head">
          {title ? (
            <h2 id={id} className="panel-title">
              {title}
            </h2>
          ) : null}
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="panel-body">{children}</div>
      {stale ? <p className="stale-note">Old values</p> : null}
    </section>
  );
}

export function KeyValue({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <dl className="kv" aria-label={label}>
      {children}
    </dl>
  );
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="kv-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** A value that is not known yet. */
export function Dash() {
  return (
    <span className="dim" aria-label="no value">
      {'–'}
    </span>
  );
}
