import { forwardRef, useId } from 'react';
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';

export interface FieldControlProps {
  id: string;
  'aria-describedby'?: string;
  'aria-invalid'?: true;
}

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: (p: FieldControlProps) => ReactNode;
}) {
  const id = useId();
  const hintId = id + '-hint';
  const errId = id + '-err';
  const describedBy = [hint ? hintId : '', error ? errId : ''].filter(Boolean).join(' ');
  return (
    <div className={['field', className ?? ''].filter(Boolean).join(' ')}>
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      {children({
        id,
        'aria-describedby': describedBy || undefined,
        'aria-invalid': error ? true : undefined,
      })}
      {hint ? (
        <p id={hintId} className="field-hint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errId} className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, type, ...rest }, ref) {
    return (
      <input
        ref={ref}
        type={type ?? 'text'}
        className={['input', className ?? ''].filter(Boolean).join(' ')}
        autoComplete="off"
        spellCheck={false}
        {...rest}
      />
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...rest }, ref) {
    return (
      <select ref={ref} className={['select', className ?? ''].filter(Boolean).join(' ')} {...rest}>
        {children}
      </select>
    );
  },
);

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: ReactNode;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, className, ...rest },
  ref,
) {
  return (
    <label className={['check', className ?? ''].filter(Boolean).join(' ')}>
      <input ref={ref} type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
});
