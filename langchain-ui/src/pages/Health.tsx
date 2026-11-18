import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, CheckCircle2, AlertTriangle, XCircle, HelpCircle } from 'lucide-react';
import { getOperatorHealth, type HealthPart, type OperatorHealth } from '../api';

/** How often the page reads the host again while it is open. */
const EVERY_MS = 30_000;

const LOOK: Record<HealthPart['status'], { icon: React.ElementType; tone: string; word: string }> = {
  ok: { icon: CheckCircle2, tone: 'text-success', word: 'OK' },
  warn: { icon: AlertTriangle, tone: 'text-warning', word: 'Look at this' },
  fail: { icon: XCircle, tone: 'text-danger', word: 'Down' },
  unknown: { icon: HelpCircle, tone: 'text-text-muted', word: 'Unknown' },
};

const PARTS: Array<[keyof OperatorHealth, string]> = [
  ['disk', 'Free space on the data volume'],
  ['database', 'Database'],
  ['runs', 'Runs'],
  ['model', 'Model server'],
  ['backup', 'Newest backup'],
];

/**
 * The host at a glance (deep review F5): an operator of one compose host sees free disk, the database, the runs
 * running and waiting, the model server and the age of the newest backup without reading the loop's output.
 * Read-only.
 */
export const Health: React.FC = () => {
  const [health, setHealth] = useState<OperatorHealth | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const read = () => getOperatorHealth()
      .then((found) => { if (live) { setHealth(found); setProblem(null); } })
      .catch((error) => live && setProblem(error?.response?.status === 403
        ? 'Only an operator or an administrator sees the host\'s health.' : 'The server did not answer.'));
    read();
    const timer = setInterval(read, EVERY_MS);
    return () => { live = false; clearInterval(timer); };
  }, []);

  return (
    <div className="mx-auto w-full max-w-3xl mt-4 animate-fade-in space-y-4">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-text-primary">
          <Activity className="h-5 w-5 text-primary" aria-hidden="true" /> Health
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          The machine the runs share, read every 30 seconds. Nothing here changes anything.
        </p>
      </header>
      {problem && <p role="alert" className="rounded-xl border border-danger/30 bg-danger-bg px-4 py-3 text-sm text-danger">{problem}</p>}
      {!health && !problem && <p role="status" className="text-sm text-text-muted">Reading the host…</p>}
      {health && (
        <>
          <ul className="glass-card rounded-2xl divide-y divide-border">
            {PARTS.map(([key, title]) => {
              const part = health[key] as HealthPart;
              const look = LOOK[part.status] ?? LOOK.unknown;
              const Icon = look.icon;
              return (
                <li key={key} className="flex items-start gap-3 px-4 py-3" data-testid={`health-${key}`}>
                  <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${look.tone}`} aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary">
                      {title} <span className={`ml-1 text-xs font-normal ${look.tone}`}>{look.word}</span>
                    </p>
                    <p className="text-sm text-text-secondary">{part.said}</p>
                  </div>
                </li>
              );
            })}
          </ul>
          {(health.runs.waiting?.length ?? 0) > 0 && (
            <section className="glass-card rounded-2xl px-4 py-3" aria-labelledby="waiting-runs">
              <h2 id="waiting-runs" className="text-sm font-semibold text-text-primary">Waiting for a worker</h2>
              <ol className="mt-1 space-y-1 text-sm">
                {health.runs.waiting!.map((run) => (
                  <li key={run.run_id} className="text-text-secondary">
                    <span className="tabular-nums text-text-primary">{run.position}.</span>{' '}
                    <Link to={`/runs/${run.run_id}`} className="text-primary hover:underline">{run.name || run.run_id.slice(0, 12)}</Link>
                    {' '}- waiting {run.minutes} min
                  </li>
                ))}
              </ol>
            </section>
          )}
          <p className="text-xs text-text-muted">
            Version {health.version} · read at {new Date(health.checked_at).toLocaleTimeString()}
          </p>
        </>
      )}
    </div>
  );
};
