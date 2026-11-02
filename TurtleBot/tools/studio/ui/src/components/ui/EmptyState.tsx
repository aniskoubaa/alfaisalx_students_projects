import type { ReactNode } from 'react';

export function EmptyState({
  icon,
  title,
  children,
  action,
  compact,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={compact ? 'empty empty-compact' : 'empty'}>
      {icon ? (
        <div className="empty-icon" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <h3 className="empty-title">{title}</h3>
      {children ? <p className="empty-text">{children}</p> : null}
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}
