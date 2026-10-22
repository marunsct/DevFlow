import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getOutcomes, type RunOutcome, type RunForecast } from '../api';
import { typicalTime } from '../lib/runSummary';

/** Finished runs side by side: how each ended, how long it took and what it scored. */
export const OutcomesPanel: React.FC = () => {
  const [rows, setRows] = useState<RunOutcome[]>([]);
  const [forecast, setForecast] = useState<Record<string, RunForecast | null>>({});

  useEffect(() => {
    getOutcomes()
      .then((data) => {
        setRows(data.runs);
        setForecast(data.forecast);
      })
      .catch(() => setRows([]));
  }, []);

  if (rows.length === 0) return null;
  const typical = Object.values(forecast).filter((f): f is RunForecast => !!f);

  return (
    <div className="glass-card rounded-2xl p-5 space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-text-primary">Outcomes of finished runs</h2>
        <p className="text-xs text-text-muted">
          {typical.map((f) => `${f.delivery_mode}: ${typicalTime(f)}`).join(' · ')}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-text-muted border-b border-border/50">
              <th className="py-2 pr-4 font-medium">Run</th>
              <th className="py-2 pr-4 font-medium">Ended</th>
              <th className="py-2 pr-4 font-medium">Mode</th>
              <th className="py-2 pr-4 font-medium">Models</th>
              <th className="py-2 pr-4 font-medium text-right">Hours</th>
              <th className="py-2 font-medium text-right">Hidden tests</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 15).map((row) => (
              <tr key={row.run_id} className="border-b border-border/30 text-text-secondary">
                <td className="py-2 pr-4">
                  <Link to={`/runs/${row.run_id}`} className="text-primary hover:underline">{row.run_id.slice(0, 12)}</Link>
                </td>
                <td className="py-2 pr-4">
                  {row.completion_gaps && row.completion_gaps.length > 0 ? (
                    <span className="text-warning" title={row.completion_gaps.join('\n')}>
                      {row.status} · {row.completion_gaps.length} gap{row.completion_gaps.length === 1 ? '' : 's'}
                    </span>
                  ) : (
                    row.status
                  )}
                </td>
                <td className="py-2 pr-4">{row.delivery_mode || '-'}</td>
                <td className="py-2 pr-4">{row.use_frontier_model ? 'frontier + local' : 'local only'}</td>
                <td className="py-2 pr-4 text-right">{row.hours ?? '-'}</td>
                <td className="py-2 text-right">
                  {row.score ? `${row.score.passed}/${row.score.total}` : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
