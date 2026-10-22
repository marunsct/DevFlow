import React from 'react';
import { cx } from './cx';

export interface IconButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  /** What the button does, in words: an icon alone says nothing to a screen reader. Required. */
  label: string;
  icon: React.ReactNode;
  size?: 'sm' | 'md';
}

/** A button that shows only an icon; its label is its accessible name and its tooltip. */
export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, size = 'md', className, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        'inline-flex items-center justify-center rounded-lg text-text-secondary transition-colors',
        'hover:bg-overlay hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
        size === 'sm' ? 'h-7 w-7' : 'h-9 w-9',
        className,
      )}
      {...rest}
    >
      <span aria-hidden="true" className="inline-flex">{icon}</span>
    </button>
  );
});
