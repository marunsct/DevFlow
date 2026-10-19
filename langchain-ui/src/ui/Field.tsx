import React, { useId } from 'react';
import { cx } from './cx';

interface FieldWiring {
  id: string;
  'aria-describedby'?: string;
  'aria-invalid'?: true;
}

interface FieldProps {
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  /** Shown at the right of the label: a stored value's state, a unit. */
  aside?: React.ReactNode;
  className?: string;
  /** Given the control's id and description wiring; render the control with them. */
  children: (wiring: FieldWiring) => React.ReactNode;
}

/** A label, the control, a hint and an error, wired together so a screen reader reads them as one. */
export const Field: React.FC<FieldProps> = ({ label, hint, error, aside, className, children }) => {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div className={className}>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium text-text-secondary">{label}</label>
        {aside && <span className="text-xs text-text-muted">{aside}</span>}
      </div>
      {children({ id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {hint && <p id={hintId} className="mt-1 text-xs text-text-muted">{hint}</p>}
      {error && <p id={errorId} className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
};

const CONTROL = cx(
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder-text-muted',
  'focus:outline-none focus:border-primary focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
  'aria-[invalid=true]:border-danger disabled:opacity-50',
);

type Labelled = { label: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; aside?: React.ReactNode };

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & Labelled>(function Input(
  { label, hint, error, aside, className, ...rest }, ref,
) {
  return (
    <Field label={label} hint={hint} error={error} aside={aside} className={className}>
      {(wiring) => <input ref={ref} {...wiring} {...rest} className={CONTROL} />}
    </Field>
  );
});

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement> & Labelled>(function Textarea(
  { label, hint, error, aside, className, ...rest }, ref,
) {
  return (
    <Field label={label} hint={hint} error={error} aside={aside} className={className}>
      {(wiring) => <textarea ref={ref} {...wiring} {...rest} className={cx(CONTROL, 'min-h-24')} />}
    </Field>
  );
});

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement> & Labelled>(function Select(
  { label, hint, error, aside, className, children, ...rest }, ref,
) {
  return (
    <Field label={label} hint={hint} error={error} aside={aside} className={className}>
      {(wiring) => <select ref={ref} {...wiring} {...rest} className={CONTROL}>{children}</select>}
    </Field>
  );
});

/** A checkbox with its label beside it; a hint below, read with it. */
export const Checkbox = React.forwardRef<HTMLInputElement, Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> & { label: React.ReactNode; hint?: React.ReactNode }>(function Checkbox(
  { label, hint, className, ...rest }, ref,
) {
  const id = useId();
  return (
    <div className={cx('flex items-start gap-2', className)}>
      <input
        ref={ref}
        id={id}
        type="checkbox"
        aria-describedby={hint ? `${id}-hint` : undefined}
        className="mt-0.5 h-4 w-4 rounded border-border accent-[var(--accent)] focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        {...rest}
      />
      <div>
        <label htmlFor={id} className="text-sm text-text-primary">{label}</label>
        {hint && <p id={`${id}-hint`} className="text-xs text-text-muted">{hint}</p>}
      </div>
    </div>
  );
});
