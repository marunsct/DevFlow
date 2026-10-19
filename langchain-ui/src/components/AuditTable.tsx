import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getKpis, getUsage } from '../api';
import { CARD_KPIS, kpiLabel, kpiValue } from '../lib/kpis';
import type { RunUsage, StageUsage } from '../types';
import { describeStage } from '../lib/activity';
import { tokens } from '../lib/runSummary';
import { Skeleton } from '../ui';

const minutes = (seconds: number): string =>
  seconds < 60 ? `${Math.round(seconds)} s` : seconds < 3600 ? `${Math.round(seconds / 60)} min` : `${(seconds / 3600).toFixed(1)} h`;

interface Column {
  key: keyof StageUsage;
  label: string;
  /** What the figure counts and where it comes from: no number without its source. */
  title: string;
  show: (stage: StageUsage) => string;
  /** Whether more is worse, so the column's largest cell is marked. */
  worse?: boolean;
}

const COLUMNS: Column[] = [
  { key: 'wall_seconds', label: 'Wall', title: 'From the stage’s first record to its last', show: (s) => minutes(s.wall_seconds), worse: true },
  { key: 'model_seconds', label: 'Model', title: 'Time waiting on model replies', show: (s) => minutes(s.model_seconds), worse: true },
  { key: 'model_calls', label: 'Calls', title: 'Model replies', show: (s) => String(s.model_calls), worse: true },
  { key: 'input_tokens', label: 'In', title: 'Input tokens sent', show: (s) => tokens(s.input_tokens), worse: true },
  { key: 'cached_tokens', label: 'Cached', title: 'Input tokens the server had cached', show: (s) => tokens(s.cached_tokens) },
  { key: 'output_tokens', label: 'Out', title: 'Output tokens, reasoning included', show: (s) => tokens(s.output_tokens), worse: true },
  { key: 'lost_replies', label: 'Lost', title: 'Replies cut off at the output limit with nothing kept', show: (s) => String(s.lost_replies), worse: true },
  { key: 'redundant_reads', label: 'Re-reads', title: 'Reads answered with "you already have this"', show: (s) => String(s.redundant_reads), worse: true },
  { key: 'tool_failures', label: 'Failed', title: 'Tool calls that failed or were refused', show: (s) => `${s.tool_failures}/${s.tool_calls}`, worse: true },
];

/**
 * Where the run spent its time and tokens, stage by stage (plan BG.7), from
 * the run's transcript (`GET /runs/{id}/usage`). The worst cell of each column
 * is marked, so the stage to read first is the one that stands out.
 */
export const AuditTable: React.FC<{ runId: string; refreshKey: string }> = ({ runId, refreshKey }) => {
  const [usage, setUsage] = useState<RunUsage | null | undefined>(undefined);
  const [kpis, setKpis] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    let live = true;
    getKpis(runId).then((found) => live && setKpis(found)).catch(() => undefined);
    getUsage(runId)
      .then((found) => live && setUsage(found))
      .catch(() => live && setUsage(null));
    return () => {
      live = false;
    };
  }, [runId, refreshKey]);

  if (usage === undefined) return <div className="p-4"><Skeleton lines={5} /></div>;
  if (!usage || usage.stages.length === 0) {
    return <p className="p-4 text-sm text-text-muted">No transcript for this run yet: nothing to measure.</p>;
  }
  const worst = Object.fromEntries(
    COLUMNS.filter((column) => column.worse).map((column) => [
      column.key,
      Math.max(...usage.stages.map((stage) => Number(stage[column.key]) || 0)),
    ]),
  );
  return (
    <div className="h-full overflow-auto" tabIndex={0} role="region" aria-label="Usage by stage">
      {kpis && (
        <div className="flex flex-wrap items-start gap-x-6 gap-y-2 border-b border-border/40 px-3 py-2">
          <dl className="flex flex-wrap gap-x-6 gap-y-2">
            {CARD_KPIS.filter((key) => key in kpis).map((key) => (
              <div key={key}>
                <dt className="text-xs text-text-muted">{kpiLabel(key)}</dt>
                <dd className="text-sm text-text-primary tabular-nums">{kpiValue(key, kpis[key])}</dd>
              </div>
            ))}
          </dl>
          <Link to={`/runs/compare?a=${runId}`} className="ml-auto text-xs font-medium text-primary hover:underline">Compare with another run</Link>
        </div>
      )}
      <table className="w-full text-xs tabular-nums">
        <caption className="sr-only">Time, tokens and failures per stage, from the run's transcript; the worst of each column is marked</caption>
        <thead className="sticky top-0 bg-surface">
          <tr className="text-left text-text-secondary border-b border-border">
            <th scope="col" className="px-3 py-2 font-medium">Stage</th>
            {COLUMNS.map((column) => (
              <th key={column.key} scope="col" title={column.title} className="px-3 py-2 font-medium text-right">{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {usage.stages.map((stage) => (
            <tr key={stage.stage} className="border-b border-border/40">
              <th scope="row" className="px-3 py-1.5 text-left font-normal text-text-primary" title={stage.stage}>
                {describeStage(stage.stage).title}
              </th>
              {COLUMNS.map((column) => {
                const value = Number(stage[column.key]) || 0;
                const marked = column.worse && value > 0 && value === worst[column.key];
                return (
                  <td key={column.key} className={`px-3 py-1.5 text-right ${marked ? 'bg-warning-bg text-warning font-semibold' : 'text-text-secondary'}`}>
                    {column.show(stage)}
                    {marked && <span className="sr-only"> (the most of any stage)</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
