import type { ReactNode, TableHTMLAttributes } from 'react';

export interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  /** Required: the accessible name of the table. */
  label: string;
  maxHeight?: number | string;
  children: ReactNode;
}

export function Table({ label, maxHeight, children, className, ...rest }: TableProps) {
  return (
    <div className="table-scroll" style={maxHeight ? { maxHeight } : undefined}>
      <table
        aria-label={label}
        className={['table', className ?? ''].filter(Boolean).join(' ')}
        {...rest}
      >
        {children}
      </table>
    </div>
  );
}
