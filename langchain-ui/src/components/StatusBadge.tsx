import React from 'react';
import { statusView, TONE_BADGE } from '../lib/status';

/** A run's status in words, with its icon and colour; the words carry the meaning, the colour only helps. */
export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const view = statusView(status);
  const Icon = view.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border shrink-0 ${TONE_BADGE[view.tone]}`}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {view.label}
    </span>
  );
};
