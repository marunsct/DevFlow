import React, { useEffect, useState } from 'react';
import { Download, Stethoscope } from 'lucide-react';
import { downloadDiagnosticBundle, getRunDoctor, type RunDoctorReport } from '../api';
import { describeStage } from '../lib/activity';

const minutes = (seconds: number) => (seconds < 60 ? `${Math.round(seconds)}s` : `${Math.round(seconds / 60)}m`);

/**
 * The run doctor (deep review F1): what happened in the run and what to do next, read from its records - the stages
 * in order with their times, the defects and what became of them, refusals for want of memory or disk - so a run can
 * be understood without an operator's audit scripts. Read-only; the diagnostic bundle is downloaded only when asked.
 */
export const RunDoctor: React.FC<{ runId: string; refreshKey?: string }> = ({ runId, refreshKey }) => {
  const [report, setReport] = useState<RunDoctorReport | null>(null);
  const [failed, setFailed] = useState(false);
  const [bundling, setBundling] = useState(false);

  useEffect(() => {
    let live = true;
    getRunDoctor(runId)
      .then((found) => { if (live) { setReport(found); setFailed(false); } })
      .catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [runId, refreshKey]);

  const bundle = async () => {
    setBundling(true);
    try {
      await downloadDiagnosticBundle(runId);
    } finally {
      setBundling(false);
    }
  };

  if (failed) return <p role="status" className="p-3 text-sm text-text-muted">The run's records could not be read.</p>;
  if (!report) return <p role="status" className="p-3 text-sm text-text-muted">Reading the run's records…</p>;
  const d = report.defects;
  return (
    <section aria-labelledby="run-doctor" className="h-full overflow-y-auto p-3 space-y-4 text-sm" data-testid="run-doctor">
      <h2 id="run-doctor" className="flex items-center gap-2 font-semibold text-text-primary">
        <Stethoscope className="h-4 w-4 text-primary" aria-hidden="true" /> Run doctor
      </h2>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">What to do</h3>
        <ul className="mt-1 space-y-1.5">
          {report.suggestions.map((s, i) => (
            <li key={i} className={s.action === 'none' ? 'text-text-secondary' : 'text-text-primary'} data-testid="doctor-suggestion">
              {s.said}{s.stage ? ` (stage: ${describeStage(s.stage).title})` : ''}
            </li>
          ))}
        </ul>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <div><dt className="text-text-muted text-xs">Defects raised</dt><dd className="tabular-nums">{d.raised}</dd></div>
        <div><dt className="text-text-muted text-xs">Fixed</dt><dd className="tabular-nums">{d.fixed}</dd></div>
        <div><dt className="text-text-muted text-xs">Left open</dt><dd className="tabular-nums">{d.left_open}</dd></div>
        <div><dt className="text-text-muted text-xs">Fixes undone</dt><dd className="tabular-nums">{d.reverted}</dd></div>
        <div><dt className="text-text-muted text-xs">Refused for memory or disk</dt><dd className="tabular-nums">{report.resource_refusals}</dd></div>
        <div><dt className="text-text-muted text-xs">Model errors</dt><dd className="tabular-nums">{report.model_errors}</dd></div>
        <div><dt className="text-text-muted text-xs">Restarts</dt><dd className="tabular-nums">{report.restarts}</dd></div>
        <div><dt className="text-text-muted text-xs">Rewinds</dt><dd className="tabular-nums">{report.rewinds}</dd></div>
      </dl>

      {d.repeated.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">Defects that keep coming back</h3>
          <ul className="mt-1 space-y-1">
            {d.repeated.map((r) => (
              <li key={r.id} className="text-text-secondary">
                <span className="tabular-nums text-text-primary">{r.rounds} rounds</span>, ended {r.ending}: {r.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.stages.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Stages in the order they first ran ({report.stage_switches} switches)
          </h3>
          <table className="mt-1 w-full text-left">
            <thead className="text-xs text-text-muted">
              <tr><th className="font-normal">Stage</th><th className="font-normal">Time</th><th className="font-normal">Model calls</th><th className="font-normal">Failed tools</th></tr>
            </thead>
            <tbody>
              {report.stages.map((s) => (
                <tr key={s.stage} className="border-t border-border">
                  <td className="py-0.5 pr-2">{describeStage(s.stage).title}</td>
                  <td className="tabular-nums">{minutes(s.wall_seconds)}{s.share >= 0.25 ? ` (${Math.round(s.share * 100)}%)` : ''}</td>
                  <td className="tabular-nums">{s.model_calls}</td>
                  <td className="tabular-nums">{s.tool_failures}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="border-t border-border pt-3">
        <button type="button" onClick={() => void bundle()} disabled={bundling} data-testid="diagnostic-bundle"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-text-secondary hover:border-border-strong hover:bg-overlay disabled:opacity-50">
          <Download className="h-3.5 w-3.5" /> Download a diagnostic bundle
        </button>
        <p className="mt-1 text-xs text-text-muted">
          The transcript, this account and the run's record, as one zip, for someone helping with the run. Keys,
          tokens and passwords are replaced; nothing of the server's settings is included. It is only made when you
          ask, and sent nowhere.
        </p>
      </div>
    </section>
  );
};
