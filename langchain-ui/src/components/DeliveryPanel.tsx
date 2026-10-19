/**
 * Delivery Panel
 *
 * What a product owner asks of a run: which acceptance criteria pass, what the
 * product looks like, and which decisions were taken - by whom and why.
 *
 * The criteria come from the harness's own run of the locked acceptance suite
 * (`GET /runs/{id}/evidence`), never from a model's summary of it. The
 * decisions are the run's decision log (`GET /runs/{id}/decisions`): the same
 * record in auto mode, where the harness decides, and in approval mode, where
 * a person does.
 */

import React, { useEffect, useState } from 'react';
import { api, getChanges } from '../api';
import { describeStage } from '../lib/activity';
import { ClipboardCheck, Gavel, Image as ImageIcon, ChevronDown, ChevronRight } from 'lucide-react';

interface CriterionResult {
  id: string;
  text: string;
  status: string;
  tests?: Array<{ name: string; outcome: string; message?: string }>;
}

interface Evidence {
  acceptance: {
    ran?: boolean;
    command?: string;
    passed?: number;
    failed?: number;
    criteria?: Record<string, CriterionResult>;
    change_requests?: Record<string, CriterionResult>;
  };
  deferred: Record<string, string>;
  screenshots: string[];
  pages: string[];
  completion_gaps?: string[];
  support_tier?: string;
  /** Each criterion's first passing test: after which step, and when (plan BG.9). */
  first_passed?: Record<string, { test: string; after: string; at: string }>;
}

interface Decision {
  id: string;
  point: string;
  question: string;
  decision: string;
  rationale: string;
  decided_by: string;
  decided_at: string;
  comment?: string;
}

const STATUS_STYLE: Record<string, string> = {
  passed: 'bg-success-bg text-success border-success/30',
  failed: 'bg-danger-bg text-danger border-danger/30',
  untested: 'bg-warning-bg text-warning border-warning/30',
  deferred: 'bg-overlay text-text-muted border-border/50',
};

const Screenshot: React.FC<{ runId: string; path: string }> = ({ runId, path }) => {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    api
      .get(`/runs/${runId}/artifacts/download`, { params: { path }, responseType: 'blob' })
      .then((res) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(res.data);
        setUrl(objectUrl);
      })
      .catch(() => {});
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [runId, path]);
  const label = path.split('/').slice(-2, -1)[0] ?? path;
  return (
    <figure className="rounded-lg overflow-hidden border border-border/50 bg-surface/40">
      {url ? (
        <img src={url} alt={label} loading="lazy" className="w-full h-32 object-cover object-top" />
      ) : (
        <div className="h-32 flex items-center justify-center text-text-muted text-xs">loading</div>
      )}
      <figcaption className="px-2 py-1 text-xs text-text-muted truncate" title={label}>{label}</figcaption>
    </figure>
  );
};

const SUMMARY_ORDER = ['passed', 'failed', 'untested', 'deferred'] as const;

/** How many criteria stand where, above the list: a bar and the count of each status. */
const CriteriaSummary: React.FC<{ criteria: CriterionResult[] }> = ({ criteria }) => {
  const count = (status: string) => criteria.filter((c) => c.status === status).length;
  const passed = count('passed');
  return (
    <div className="mb-3 space-y-1.5">
      <div role="progressbar" aria-label="Acceptance criteria passing" aria-valuemin={0} aria-valuemax={criteria.length} aria-valuenow={passed}
        className="h-1.5 w-full overflow-hidden rounded-full bg-overlay-strong">
        <div className="h-full rounded-full bg-success" style={{ width: `${(passed / Math.max(1, criteria.length)) * 100}%` }} />
      </div>
      <p className="flex flex-wrap gap-x-3 text-xs text-text-secondary tabular-nums">
        {SUMMARY_ORDER.filter((status) => count(status) > 0).map((status) => (
          <span key={status}>{count(status)} {status}</span>
        ))}
      </p>
    </div>
  );
};

/** The measurement a criterion first passed in, in words: its snapshot's label is "after X", "before X" or a moment. */
function whenMeasured(label: string): string {
  const [, which, stage] = /^(after|before) (.+)$/.exec(label) ?? [];
  if (which === 'after') return `after ${describeStage(stage).title}`;
  if (which === 'before') return `by the start of ${describeStage(stage).title}`;
  if (label === 'suite locked') return 'when the suite was locked';
  if (label === 'accepted') return 'when the sprint was accepted';
  return `at ${label}`;
}

/**
 * When a criterion first passed and after which step, and the change that did
 * it: the first commit made from that moment on (plan BG.9).
 */
const FirstPassed: React.FC<{
  runId: string;
  first: { test: string; after: string; at: string };
  onOpenChange?: (sha: string) => void;
}> = ({ runId, first, onOpenChange }) => {
  const when = new Date(first.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const open = async () => {
    const { commits } = await getChanges(runId);
    const from = new Date(first.at).getTime();
    const made = [...commits].reverse().find((commit) => new Date(commit.at).getTime() >= from - 1000);
    if (made) onOpenChange?.(made.sha);
  };
  return (
    <span className="block text-xs text-text-muted" title={first.test}>
      {/* Its first passing test, not the criterion: a failing criterion can have one. */}
      first passing test: {whenMeasured(first.after)}, {when}
      {onOpenChange && (
        <>
          {' \u00B7 '}
          <button type="button" onClick={() => void open()} className="text-primary hover:underline">see the change</button>
        </>
      )}
    </span>
  );
};

export const DeliveryPanel: React.FC<{
  runId: string;
  refreshKey?: string;
  /** Open the Changes tab on a commit: the one that made a criterion pass. */
  onOpenChange?: (sha: string) => void;
}> = ({ runId, refreshKey, onOpenChange }) => {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [open, setOpen] = useState(true);
  const [openDecision, setOpenDecision] = useState<string | null>(null);

  useEffect(() => {
    api.get(`/runs/${runId}/evidence`).then((res) => setEvidence(res.data)).catch(() => {});
    api.get(`/runs/${runId}/decisions`).then((res) => setDecisions(res.data.decisions ?? [])).catch(() => {});
  }, [runId, refreshKey]);

  const criteria = [
    ...Object.values(evidence?.acceptance?.criteria ?? {}),
    ...Object.values(evidence?.acceptance?.change_requests ?? {}),
  ];
  const gaps = evidence?.completion_gaps ?? [];
  if (!criteria.length && !decisions.length && !gaps.length) return null;
  const passing = criteria.filter((c) => c.status === 'passed').length;

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="w-full px-5 py-3 flex items-center justify-between border-b border-border/40 text-left"
      >
        <span className="flex items-center gap-2 font-semibold text-text-primary text-sm">
          <ClipboardCheck className="h-4 w-4 text-primary" />
          Delivery
          {criteria.length > 0 && (
            <span className="text-xs font-normal text-text-muted">
              {passing} of {criteria.length} acceptance criteria passing
            </span>
          )}
        </span>
        {open ? <ChevronDown className="h-4 w-4 text-text-muted" /> : <ChevronRight className="h-4 w-4 text-text-muted" />}
      </button>
      {open && (
        // Laid out by the pane's own width, not the window's: in the run page's
        // ledger column a two-column split left each criterion a few words a line.
        <div className="@container">
        <div className="grid gap-5 p-4 grid-cols-1 @3xl:grid-cols-2">
          {criteria.length > 0 && (
            <section>
              <h2 className="text-xs font-medium uppercase tracking-wider text-text-secondary mb-2">Acceptance criteria</h2>
              <CriteriaSummary criteria={criteria} />
              <ul className="space-y-1.5">
                {criteria.map((c) => (
                  <li key={c.id} className="rounded-lg border border-border/40 px-3 py-2 text-sm">
                    <div className="flex items-start gap-2">
                      <span className="mt-0.5 w-11 shrink-0 font-mono text-xs text-text-muted">{c.id}</span>
                      <span className="min-w-0 flex-1 break-words text-text-primary">{c.text}</span>
                      <span className={`shrink-0 rounded border px-1.5 py-0.5 text-xs font-semibold ${STATUS_STYLE[c.status] ?? STATUS_STYLE.untested}`}>
                        {c.status}
                      </span>
                    </div>
                    <div className="mt-1 pl-[3.25rem] text-xs text-text-muted space-y-0.5">
                      {evidence?.deferred?.[c.id] && (
                        <span className="block">deferred: {evidence.deferred[c.id]}</span>
                      )}
                      {evidence?.first_passed?.[c.id] && (
                        <FirstPassed runId={runId} first={evidence.first_passed[c.id]} onOpenChange={onOpenChange} />
                      )}
                      {(c.tests?.length ?? 0) > 0 && (
                        <details>
                          <summary className="cursor-pointer text-xs text-text-muted hover:text-text-secondary">
                            {c.tests!.filter((t) => t.outcome === 'passed').length} of {c.tests!.length} test{c.tests!.length === 1 ? '' : 's'} passing
                          </summary>
                          <ul className="mt-1 space-y-1">
                            {c.tests!.map((t) => (
                              <li key={t.name} className="text-xs">
                                <span className={t.outcome === 'passed' ? 'text-success' : t.outcome === 'skipped' ? 'text-text-muted' : 'text-danger'}>
                                  {t.outcome}
                                </span>{' '}
                                <span className="text-text-secondary">{t.name}</span>
                                {t.outcome !== 'passed' && t.message && (
                                  <span className="block font-mono text-xs text-text-muted break-words">
                                    {t.message.trim().split('\n')[0].slice(0, 240)}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {evidence?.acceptance?.command && (
                <p className="mt-2 text-xs text-text-muted">
                  Measured by the harness with <code>{evidence.acceptance.command}</code>.
                </p>
              )}
            </section>
          )}
          {((evidence?.completion_gaps?.length ?? 0) > 0 || evidence?.support_tier) && (
            <section>
              <h2 className="text-xs font-medium uppercase tracking-wider text-text-secondary mb-2">What this release did not prove</h2>
              {evidence?.support_tier && <p className="text-xs text-text-muted mb-1.5">{evidence.support_tier}</p>}
              {(evidence?.completion_gaps?.length ?? 0) > 0 ? (
                <ul className="space-y-1">
                  {evidence!.completion_gaps!.map((gap, index) => (
                    <li key={index} className="text-sm text-text-secondary flex gap-2">
                      <span className="text-warning shrink-0" aria-hidden="true">!</span>
                      <span className="min-w-0 break-words">{gap}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-text-muted">Nothing is recorded as unproven.</p>
              )}
            </section>
          )}
          {decisions.length > 0 && (
            <section>
              <h2 className="text-xs font-medium uppercase tracking-wider text-text-secondary mb-2 flex items-center gap-1.5">
                <Gavel className="h-3.5 w-3.5" /> Decisions
              </h2>
              <ul className="space-y-1">
                {decisions.map((d) => (
                  <li key={d.id} className="text-sm">
                    <button
                      type="button"
                      aria-expanded={openDecision === d.id}
                      onClick={() => setOpenDecision(openDecision === d.id ? null : d.id)}
                      className="w-full text-left flex items-start gap-2 hover:bg-overlay rounded px-1 py-0.5"
                    >
                      <span className="font-mono text-xs text-text-muted mt-0.5 shrink-0">{d.id}</span>
                      <span className="flex-1 text-text-secondary">
                        {d.question} <span className="text-text-primary">{d.decision}</span>
                      </span>
                      <span className={`shrink-0 text-xs uppercase px-1.5 py-0.5 rounded ${d.decided_by === 'user' ? 'bg-accent-soft text-primary' : 'bg-overlay text-text-muted'}`}>
                        {d.decided_by}
                      </span>
                    </button>
                    {openDecision === d.id && (
                      <div className="ml-10 mt-1 mb-2 text-xs text-text-muted whitespace-pre-wrap">
                        {d.rationale}
                        {d.comment ? `\nComment: ${d.comment}` : ''}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {(evidence?.screenshots?.length ?? 0) > 0 && (
            <section className="@3xl:col-span-2">
              <h2 className="text-xs font-medium uppercase tracking-wider text-text-secondary mb-2 flex items-center gap-1.5">
                <ImageIcon className="h-3.5 w-3.5" /> Screenshots from the last acceptance run
              </h2>
              <div className="grid gap-3 grid-cols-1 @sm:grid-cols-2 @xl:grid-cols-3 @4xl:grid-cols-4">
                {evidence!.screenshots.map((path) => (
                  <Screenshot key={path} runId={runId} path={path} />
                ))}
              </div>
            </section>
          )}
        </div>
        </div>
      )}
    </div>
  );
};
