import React from 'react';
import { cx } from './cx';

interface CardProps extends React.HTMLAttributes<HTMLElement> {
  /** `raised` sits above the page's surfaces; no shadow either way unless asked for. */
  tone?: 'surface' | 'raised';
  as?: 'section' | 'div' | 'article';
}

/** A bordered panel; its header, body and footer are optional slots. */
export const Card: React.FC<CardProps> & {
  Header: React.FC<React.HTMLAttributes<HTMLDivElement> & { title?: React.ReactNode; actions?: React.ReactNode }>;
  Body: React.FC<React.HTMLAttributes<HTMLDivElement>>;
  Footer: React.FC<React.HTMLAttributes<HTMLDivElement>>;
} = ({ tone = 'surface', as: Tag = 'section', className, ...rest }) => (
  <Tag
    className={cx('rounded-xl border border-border', tone === 'raised' ? 'bg-surface-raised' : 'bg-surface', className)}
    {...rest}
  />
);

Card.Header = ({ title, actions, className, children, ...rest }) => (
  <div className={cx('flex items-center justify-between gap-3 border-b border-border px-4 py-3', className)} {...rest}>
    {title !== undefined ? <h2 className="text-sm font-semibold text-text-primary">{title}</h2> : children}
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
);

Card.Body = ({ className, ...rest }) => <div className={cx('px-4 py-4', className)} {...rest} />;

Card.Footer = ({ className, ...rest }) => (
  <div className={cx('flex items-center justify-end gap-2 border-t border-border px-4 py-3', className)} {...rest} />
);
