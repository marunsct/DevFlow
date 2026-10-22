import React from 'react';
import { statusView, TONE_BADGE, type Tone } from '../lib/status';
import { cx } from './cx';

/** A small label in one of the status tones; the words carry the meaning, the colour only helps. */
export const Badge: React.FC<{ tone?: Tone; icon?: React.ReactNode; className?: string; children: React.ReactNode }> = ({
  tone = 'neutral', icon, className, children,
}) => (
  <span className={cx('inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold', TONE_BADGE[tone], className)}>
    {icon && <span aria-hidden="true" className="inline-flex">{icon}</span>}
    {children}
  </span>
);

/** A run's status, from the one status map every surface reads. */
export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const view = statusView(status);
  const Icon = view.icon;
  return <Badge tone={view.tone} icon={<Icon className="h-3 w-3" />}>{view.label}</Badge>;
};
