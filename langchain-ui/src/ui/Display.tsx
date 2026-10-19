import React, { useId, useState } from 'react';
import { cx } from './cx';

/** A grey block in the shape of what is loading; hidden from screen readers, which hear the region's busy state instead. */
export const Skeleton: React.FC<{ className?: string; lines?: number }> = ({ className, lines = 1 }) => (
  <div aria-hidden="true" className="space-y-2">
    {Array.from({ length: lines }, (_, index) => (
      <div key={index} className={cx('h-4 animate-pulse rounded bg-overlay-strong', index === lines - 1 && lines > 1 && 'w-2/3', className)} />
    ))}
  </div>
);

/** Nothing here yet: an icon, one sentence and at most one thing to do about it. */
export const EmptyState: React.FC<{ icon?: React.ReactNode; title: string; action?: React.ReactNode }> = ({ icon, title, action }) => (
  <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-6 py-10 text-center">
    {icon && <span aria-hidden="true" className="text-text-muted">{icon}</span>}
    <p className="text-sm text-text-secondary">{title}</p>
    {action}
  </div>
);

/** A number with what it counts and where it came from: no figure in the interface without its source. */
export const Stat: React.FC<{ label: string; value: React.ReactNode; source: string }> = ({ label, value, source }) => (
  <div className="min-w-0">
    <dt className="text-xs text-text-muted">{label}</dt>
    <dd className="text-lg font-semibold text-text-primary tabular-nums">{value}</dd>
    <dd className="truncate text-xs text-text-muted" title={source}>{source}</dd>
  </div>
);

/** A key on the keyboard. */
export const Kbd: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <kbd className="rounded border border-border bg-inset px-1.5 py-0.5 font-mono text-[11px] text-text-secondary">{children}</kbd>
);

/** A short explanation shown on hover and on keyboard focus alike, and read as the trigger's description. */
export const Tooltip: React.FC<{ text: string; children: React.ReactElement<React.HTMLAttributes<HTMLElement>> }> = ({ text, children }) => {
  const id = useId();
  const [shown, setShown] = useState(false);
  const show = () => setShown(true);
  const hide = () => setShown(false);
  return (
    <span className="relative inline-flex" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
      onKeyDown={(event) => { if (event.key === 'Escape') hide(); }}>
      {React.cloneElement(children, { 'aria-describedby': id })}
      <span
        role="tooltip"
        id={id}
        hidden={!shown}
        className="absolute bottom-full left-1/2 z-50 mb-1 w-max max-w-xs -translate-x-1/2 rounded-md border border-border bg-surface-raised px-2 py-1 text-xs text-text-primary"
      >
        {text}
      </span>
    </span>
  );
};

/** How far along something is; with no `value`, that it is under way and not how far. */
export const Progress: React.FC<{ label: string; value?: number; max?: number; className?: string }> = ({ label, value, max = 100, className }) => {
  const known = typeof value === 'number';
  const share = known ? Math.max(0, Math.min(1, value / max)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={known ? 0 : undefined}
      aria-valuemax={known ? max : undefined}
      aria-valuenow={known ? value : undefined}
      className={cx('h-2 w-full overflow-hidden rounded-full bg-overlay-strong', className)}
    >
      <div className={cx('h-full rounded-full bg-primary', !known && 'w-1/3 animate-pulse')} style={known ? { width: `${share * 100}%` } : undefined} />
    </div>
  );
};

/** A label and its value on one line, as a definition: settings and facts about a run. */
export const InfoRow: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex items-center justify-between border-b border-border/30 py-3 last:border-0">
    <dt className="text-sm text-text-secondary">{label}</dt>
    <dd className="text-sm font-medium text-text-primary font-mono">{value}</dd>
  </div>
);
