import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { compareRuns, listRuns, type KpiRow } from '../api';
import type { RunSummary } from '../types';
import { Select } from '../ui';
import { describeStage } from '../lib/activity';
import { kpiLabel, kpiValue } from '../lib/kpis';

/**
 * Two runs side by side (plan UI-S6, BG.16): every KPI the loop's ledger keeps,
 * the change from the first to the second, and each regression marked by the
 * ledger's own rule - the gate comparison, on a page.
 */
export const Compare: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const a = params.get('a') ?? '';
  const b = params.get('b') ?? '';
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [rows, setRows] = useState<KpiRow[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    listRuns().then(({ runs: found }) => setRuns(found)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!a || !b) return;
    let live = true;
    compareRuns(a, b)
      .then((found) => { if (live) { setRows(found.rows); setProblem(null); } })
      .catch(() => live && setProblem('These two runs could not be compared.'));
    return () => {
      live = false;
    };
  }, [a, b]);

  const choose = (key: 'a' | 'b', value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };
  const name = (run: RunSummary) => `${run.run_id.slice(0, 12)} · ${describeStage(run.current_stage).title} · ${new Date(run.created_at).toLocaleDateString()}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Compare two runs</h1>
        <p className="mt-1 text-sm text-text-secondary">Every measure the loop keeps for a run, side by side; a change for the worse is marked as the ledger would flag it.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {(['a', 'b'] as const).map((key) => (
          <Select key={key} label={key === 'a' ? 'First run (before)' : 'Second run (after)'} value={key === 'a' ? a : b} onChange={(event) => choose(key, event.target.value)}>
            <option value="">Choose a run</option>
            {runs.map((run) => <option key={run.run_id} value={run.run_id}>{name(run)}</option>)}
          </Select>
        ))}
      </div>
      {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
      {a && b && rows && (
        <div className="relative overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-sm tabular-nums">
            <caption className="sr-only">Measures of the two runs; a change for the worse is marked</caption>
            <thead>
              <tr className="border-b border-border text-left text-xs text-text-secondary">
                <th scope="col" className="px-4 py-2 font-medium">Measure</th>
                <th scope="col" className="px-4 py-2 text-right font-medium"><Link to={`/runs/${a}`} className="hover:underline">Before</Link></th>
                <th scope="col" className="px-4 py-2 text-right font-medium"><Link to={`/runs/${b}`} className="hover:underline">After</Link></th>
                <th scope="col" className="px-4 py-2 text-right font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className={`border-b border-border/40 ${row.worse ? 'bg-warning-bg' : ''}`}>
                  <th scope="row" className="px-4 py-1.5 text-left font-normal text-text-primary" title={row.key}>
                    {kpiLabel(row.key)}
                    {row.worse && <span className="ml-2 text-xs font-semibold text-warning">worse</span>}
                  </th>
                  <td className="px-4 py-1.5 text-right text-text-secondary">{kpiValue(row.key, row.a)}</td>
                  <td className="px-4 py-1.5 text-right text-text-secondary">{kpiValue(row.key, row.b)}</td>
                  <td className="px-4 py-1.5 text-right text-text-muted">{row.change === null ? '-' : `${row.change > 0 ? '+' : ''}${Math.round(row.change * 100)} %`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
