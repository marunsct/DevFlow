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
import { api } from '../api';
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
        <img src={url} alt={label} className="w-full h-32 object-cover object-top" />
      ) : (
        <div className="h-32 flex items-center justify-center text-text-muted text-xs">loading</div>
      )}
      <figcaption className="px-2 py-1 text-[11px] text-text-muted truncate" title={label}>{label}</figcaption>
    </figure>
  );
};

export const DeliveryPanel: React.FC<{ runId: string; refreshKey?: string }> = ({ runId, refreshKey }) => {
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
  if (!criteria.length && !decisions.length) return null;
  const passing = criteria.filter((c) => c.status === 'passed').length;

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <button
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
        <div className="grid gap-5 p-5 grid-cols-1 xl:grid-cols-2">
          {criteria.length > 0 && (
            <section>
              <h2 className="text-xs font-medium uppercase tracking-wider text-text-secondary mb-2">Acceptance criteria</h2>
              <ul className="space-y-1.5">
                {criteria.map((c) => (
                  <li key={c.id} className="flex items-start gap-2 text-sm">
                    <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded border text-[10px] font-semibold uppercase ${STATUS_STYLE[c.status] ?? STATUS_STYLE.untested}`}>
                      {c.status}
                    </span>
                    <span className="text-text-secondary min-w-0">
                      <span className="font-mono text-xs text-text-muted mr-1.5">{c.id}</span>
                      {c.text}
                      {evidence?.deferred?.[c.id] && (
                        <span className="block text-xs text-text-muted">deferred: {evidence.deferred[c.id]}</span>
                      )}
                      {(c.tests?.length ?? 0) > 0 && (
                        <details className="mt-1">
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
                                  <span className="block font-mono text-[11px] text-text-muted break-words">
                                    {t.message.trim().split('\n')[0].slice(0, 240)}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
              {evidence?.acceptance?.command && (
                <p className="mt-2 text-[11px] text-text-muted">
                  Measured by the harness with <code>{evidence.acceptance.command}</code>.
                </p>
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
                      onClick={() => setOpenDecision(openDecision === d.id ? null : d.id)}
                      className="w-full text-left flex items-start gap-2 hover:bg-overlay rounded px-1 py-0.5"
                    >
                      <span className="font-mono text-xs text-text-muted mt-0.5 shrink-0">{d.id}</span>
                      <span className="flex-1 text-text-secondary">
                        {d.question} <span className="text-text-primary">{d.decision}</span>
                      </span>
                      <span className={`shrink-0 text-[10px] uppercase px-1.5 py-0.5 rounded ${d.decided_by === 'user' ? 'bg-accent-soft text-primary' : 'bg-overlay text-text-muted'}`}>
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
            <section className="xl:col-span-2">
              <h2 className="text-xs font-medium uppercase tracking-wider text-text-secondary mb-2 flex items-center gap-1.5">
                <ImageIcon className="h-3.5 w-3.5" /> Screenshots from the last acceptance run
              </h2>
              <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
                {evidence!.screenshots.map((path) => (
                  <Screenshot key={path} runId={runId} path={path} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
};
