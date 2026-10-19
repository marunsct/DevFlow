import React from 'react';
import { Link } from 'react-router-dom';
import { Server } from 'lucide-react';
import type { ServerHealth } from '../types';
import { describeServer } from '../lib/serverHealth';
import { cx } from '../ui';

const DOT = { ok: 'bg-success', warn: 'bg-warning', danger: 'bg-danger', accent: 'bg-primary', neutral: 'bg-text-muted' } as const;

/**
 * The build model's server in the header (plan BG.5): a dot in its state, and
 * what it is and who is on it in words, as the link's name and tooltip. It
 * opens the model settings.
 */
export const ServerDot: React.FC<{ health: ServerHealth | null }> = ({ health }) => {
  const view = describeServer(health);
  return (
    <Link
      to="/settings?tab=models"
      aria-label={view.said}
      title={view.said}
      className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg text-text-secondary hover:bg-overlay hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
    >
      <Server className="h-4 w-4" aria-hidden="true" />
      <span aria-hidden="true" className={cx('absolute right-1.5 top-1.5 h-2 w-2 rounded-full ring-2 ring-[var(--bg-surface)]', DOT[view.tone])} />
    </Link>
  );
};
