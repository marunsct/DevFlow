import React, { useEffect, useState } from 'react';
import { ListChecks } from 'lucide-react';
import { previewBrief } from '../api';
import type { BriefPreview } from '../types';

/** How long typing must pause before the brief is read again. */
const PAUSE_MS = 600;

/**
 * What the run will be held to, while the brief is being written (plan BG.10):
 * the acceptance criteria the run numbers from it, each "not yet" until the run
 * proves it - read with the run's own numbering and no model call.
 */
export const CriteriaPreview: React.FC<{ brief: string }> = ({ brief }) => {
  const [preview, setPreview] = useState<BriefPreview | null>(null);

  useEffect(() => {
    if (!brief.trim()) return;
    let live = true;
    const timer = setTimeout(() => {
      previewBrief(brief)
        .then((found) => live && setPreview(found))
        .catch(() => undefined);
    }, PAUSE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [brief]);

  if (!brief.trim() || !preview) return null;
  return (
    <section aria-labelledby="criteria-preview" className="rounded-xl border border-border bg-surface p-4">
      <h2 id="criteria-preview" className="flex items-center gap-2 text-sm font-semibold text-text-primary">
        <ListChecks className="h-4 w-4 text-primary" aria-hidden="true" />
        What the run will be held to
      </h2>
      {preview.from_brief ? (
        <ul className="mt-2 space-y-1">
          {preview.criteria.map((criterion) => (
            <li key={criterion.id} className="flex items-start gap-2 text-sm">
              <span className="mt-0.5 shrink-0 rounded border border-border bg-overlay px-1.5 py-0.5 text-xs font-semibold text-text-muted">not yet</span>
              <span className="text-text-secondary">
                <span className="mr-1.5 font-mono text-xs text-text-muted">{criterion.id}</span>
                {criterion.text}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-text-secondary">
          The brief lists fewer than two behaviours under a heading such as Features or Requirements, so the run will
          draw its criteria from what it understands of the product. List them, one per line, to choose them yourself.
        </p>
      )}
    </section>
  );
};
