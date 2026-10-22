/**
 * Owner Rating
 *
 * The owner's own verdict on a delivered product (plan EV.1): a score of 1 to 5
 * and a line, one click and an optional sentence. Hidden tests say whether the
 * product works; this says whether it is any good. It is kept with the run's
 * KPI row (`loop.sh kpi`) and `bench-report` shows it beside the hidden score.
 */

import React, { useEffect, useState } from 'react';
import { Star } from 'lucide-react';
import { api } from '../api';

interface Rating {
  score: number;
  note: string;
  rated_by?: string;
  rated_at?: string;
}

export const OwnerRating: React.FC<{ runId: string }> = ({ runId }) => {
  const [saved, setSaved] = useState<Rating | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api
      .get(`/runs/${runId}/rating`)
      .then((res) => {
        if (res.data) {
          setSaved(res.data);
          setNote(res.data.note ?? '');
        }
      })
      .catch(() => {});
  }, [runId]);

  const rate = (score: number) => {
    setError('');
    api
      .put(`/runs/${runId}/rating`, { score, note })
      .then((res) => setSaved(res.data))
      .catch((err) => setError(err?.response?.data?.detail ?? 'The rating was not saved.'));
  };

  return (
    <div className="glass-card rounded-2xl px-5 py-3 flex flex-wrap items-center gap-3" data-testid="owner-rating">
      <span className="text-sm font-semibold text-text-primary">Your rating</span>
      <div role="radiogroup" aria-label="Rating of the delivered product" className="flex gap-1">
        {[1, 2, 3, 4, 5].map((score) => (
          <button
            key={score}
            type="button"
            role="radio"
            aria-checked={saved?.score === score}
            aria-label={`${score} of 5`}
            onClick={() => rate(score)}
            className="p-0.5 rounded hover:bg-overlay"
          >
            <Star className={`h-5 w-5 ${saved && score <= saved.score ? 'fill-warning text-warning' : 'text-text-muted'}`} />
          </button>
        ))}
      </div>
      <input
        aria-label="One line on the product"
        value={note}
        maxLength={500}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => saved && note !== saved.note && rate(saved.score)}
        placeholder="One line on the product (optional)"
        className="flex-1 min-w-[12rem] rounded-md border border-border/50 bg-transparent px-2 py-1 text-sm"
      />
      {saved && <span className="text-xs text-text-muted">saved: {saved.score} of 5</span>}
      {error && <span className="text-xs text-danger" role="alert">{error}</span>}
    </div>
  );
};
