/**
 * The reviews a live run stops at, changeable while it runs (plan WS.3,
 * `PUT /runs/{id}/review-policy`). The run reads its reviews at each gate, so
 * the next gate it reaches follows a change; a gate already open stays open.
 */
import React, { useEffect, useState } from 'react';
import { changeReviewPolicy, getReviewPolicy } from '../api';
import { REVIEW_POINTS } from '../lib/runDefaults';
import { Checkbox } from '../ui';
import { useFeedback } from './Feedback';

const detailOf = (error: any): string | undefined => error?.response?.data?.detail;

export const RunReviewsControl: React.FC<{ runId: string }> = ({ runId }) => {
  const [policy, setPolicy] = useState<Record<string, boolean> | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const { notify } = useFeedback();

  useEffect(() => {
    let live = true;
    getReviewPolicy(runId).then((kept) => live && setPolicy(kept)).catch(() => live && setPolicy(null));
    return () => {
      live = false;
    };
  }, [runId]);

  if (policy === null) return null;
  const on = REVIEW_POINTS.filter(([point]) => policy[point]).length;

  const change = async (point: string, wanted: boolean) => {
    setSaving(point);
    try {
      setPolicy(await changeReviewPolicy(runId, { [point]: wanted }));
      notify('Changed. The next review the run reaches follows it.', 'info');
    } catch (error) {
      notify(detailOf(error) ?? 'The reviews could not be changed.', 'error');
    } finally {
      setSaving(null);
    }
  };

  return (
    <details className="glass-card rounded-2xl text-sm">
      <summary className="cursor-pointer list-none px-4 py-2.5 flex flex-wrap items-center gap-3">
        <span className="font-medium text-primary">Reviews this run stops for</span>
        <span className="text-xs text-text-muted" data-testid="reviews-on">
          {on} of {REVIEW_POINTS.length} on &middot; change while it runs
        </span>
      </summary>
      <div className="space-y-2 border-t border-border px-4 py-3">
        {REVIEW_POINTS.map(([point, words]) => (
          <Checkbox
            key={point}
            label={words}
            checked={!!policy[point]}
            disabled={saving !== null}
            onChange={(event) => void change(point, event.target.checked)}
          />
        ))}
        <p className="text-xs text-text-muted">The next review the run reaches follows a change; one already open stays open.</p>
      </div>
    </details>
  );
};
