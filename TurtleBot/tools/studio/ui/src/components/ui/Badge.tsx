import { CircleAlert, CircleCheck, Dot, TriangleAlert } from 'lucide-react';
import type { HTMLAttributes, ReactNode } from 'react';
import { Spinner } from './Spinner';

export type Tone = 'ok' | 'warn' | 'bad' | 'neutral' | 'info';

const ICONS: Record<Tone, ReactNode> = {
  ok: <CircleCheck size={14} aria-hidden="true" />,
  warn: <TriangleAlert size={14} aria-hidden="true" />,
  bad: <CircleAlert size={14} aria-hidden="true" />,
  info: <Dot size={14} aria-hidden="true" />,
  neutral: <Dot size={14} aria-hidden="true" />,
};

/** A small label whose meaning is in its words; the icon and tint only support them. */
export function Badge({
  tone = 'neutral',
  children,
  icon,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  icon?: ReactNode | false;
  title?: string;
}) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {icon === false ? null : (icon ?? ICONS[tone])}
      <span>{children}</span>
    </span>
  );
}

/** A larger state indicator for the top bar and panel headings. */
export function StatusPill({
  tone = 'neutral',
  busy = false,
  children,
  className,
  ...rest
}: {
  tone?: Tone;
  busy?: boolean;
  children: ReactNode;
} & HTMLAttributes<HTMLSpanElement>) {
  return (
    <span className={['pill', `pill-${tone}`, className ?? ''].filter(Boolean).join(' ')} {...rest}>
      {busy ? <Spinner size={12} /> : <span className="pill-dot" aria-hidden="true" />}
      <span className="pill-text">{children}</span>
    </span>
  );
}
