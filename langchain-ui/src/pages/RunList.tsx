import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { listRuns, deleteRun, cloneRun, resumeRun, pauseRun, RUNS_PER_PAGE } from '../api';
import type { RunSummary } from '../types';
import { Activity, AlertCircle, Inbox, Plus, Trash2, Copy, Pause, Search } from 'lucide-react';
import { describeStage, RESUMABLE } from '../lib/activity';
import { statusView } from '../lib/status';
import { StatusBadge } from '../components/StatusBadge';
import { markRunsSeen } from '../lib/useNeedsYou';
import { OutcomesPanel } from '../components/OutcomesPanel';
import { useNow, usePageVisible } from '../lib/usePageVisible';
import { useFeedback } from '../components/Feedback';
import { Button } from '../ui';

export const RunList: React.FC = () => {
  const { notify, confirm: askConfirm } = useFeedback();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // The view lives in the address, so a link or a reload opens the same list.
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1);

  // Read again now, as after a delete or a resume; the poll goes on as before.
  const [reads, setReads] = useState(0);
  const fetchRuns = useCallback(() => setReads((n) => n + 1), []);

  // Polled only while the tab is visible: a hidden tab polling every 5 s
  // spent the server's request budget for nobody.
  const visible = usePageVisible();
  useEffect(() => {
    if (!visible) return;
    let live = true;
    const read = async () => {
      try {
        const response = await listRuns(page);
        if (!live) return;
        const sortedRuns = response.runs.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        setRuns(sortedRuns);
        setTotal(response.total ?? sortedRuns.length);
      } catch (err: any) {
        console.error(err);
        if (live) setError("Failed to load past runs.");
      } finally {
        if (live) setLoading(false);
      }
    };
    void read();
    const interval = setInterval(read, 5000);
    return () => {
      live = false;
      clearInterval(interval);
    };
  }, [visible, page, reads]);

  const handleDelete = async (runId: string) => {
    if (!(await askConfirm({
      title: 'Delete this run?',
      message: 'Its record and workspace are removed. This cannot be undone.',
      confirmLabel: 'Delete',
      danger: true,
    }))) return;
    try {
      await deleteRun(runId);
      fetchRuns();
    } catch (err: any) {
      notify('Failed to delete: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleClone = async (runId: string) => {
    try {
      const clonedRun = await cloneRun(runId);
      navigate(`/runs/${clonedRun.run_id}`);
    } catch (err: any) {
      notify("Failed to clone: " + (err.response?.data?.detail || err.message));
    }
  };

  const handlePause = async (runId: string) => {
    try {
      await pauseRun(runId);
      fetchRuns();
    } catch (err: any) {
      notify("Failed to pause: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleResume = async (runId: string) => {
    try {
      await resumeRun(runId);
      fetchRuns();
    } catch (err: any) {
      notify("Failed to resume: " + (err.response?.data?.detail || err.message));
    }
  };

  const filter = params.get('status') ?? 'all';
  const query = (params.get('q') ?? '').trim().toLowerCase();
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value && value !== 'all' && !(key === 'page' && value === '1')) next.set(key, value); else next.delete(key);
    setParams(next, { replace: key !== 'page' });
  };
  const pages = Math.max(1, Math.ceil(total / RUNS_PER_PAGE));
  const first = (page - 1) * RUNS_PER_PAGE + 1;
  const last = Math.min(total, page * RUNS_PER_PAGE);

  useEffect(() => { markRunsSeen(); }, []);
  const now = useNow(true, 30_000);

  const shown = useMemo(() => {
    const keep = runs.filter((run) => {
      const view = statusView(run.status);
      if (filter === 'needs-you' && !view.needsYou) return false;
      if (filter === 'running' && run.status !== 'running') return false;
      if (filter === 'finished' && !view.terminal) return false;
      if (query) {
        const text = `${run.run_id} ${(run.document_names ?? []).join(' ')} ${describeStage(run.current_stage).title}`.toLowerCase();
        if (!text.includes(query)) return false;
      }
      return true;
    });
    // The runs that need the owner first, then the newest.
    return keep.sort((a, b) =>
      Number(statusView(b.status).needsYou) - Number(statusView(a.status).needsYou)
      || new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [runs, filter, query]);

  const elapsed = (run: RunSummary): string => {
    const end = statusView(run.status).terminal && run.updated_at ? new Date(run.updated_at).getTime() : now;
    const minutes = Math.max(0, Math.round((end - new Date(run.created_at).getTime()) / 60000));
    return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`;
  };

  return (
    <div className="w-full space-y-6 animate-fade-in">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Workflow Runs</h1>
          <p className="text-sm text-text-secondary mt-1">View and manage all your workflow runs</p>
        </div>
        <Link
          to="/"
          className="gradient-btn flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-primary-foreground text-sm"
        >
          <Plus className="h-4 w-4" />
          New Run
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="h-10 w-10 border-3 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : error ? (
        <div className="p-8 glass-card rounded-2xl text-center">
          <AlertCircle className="h-10 w-10 text-danger mx-auto mb-4" />
          <p className="text-danger">{error}</p>
        </div>
      ) : total === 0 && runs.length === 0 ? (
        <div className="glass-card rounded-2xl p-16 text-center">
          <Inbox className="h-14 w-14 text-text-muted mx-auto mb-4" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-text-primary mb-2">No runs yet</h2>
          <p className="text-text-secondary mb-6 text-sm">No runs yet. Start a build and it appears here.</p>
          <Link
            to="/"
            className="gradient-btn inline-flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-primary-foreground text-sm"
          >
            <Plus className="h-4 w-4" />
            Start Your First Run
          </Link>
        </div>
      ) : (
        <div>
          <div className="flex flex-col sm:flex-row gap-3 mb-3">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" aria-hidden="true" />
              <label htmlFor="runs-search" className="sr-only">Search runs</label>
              <input
                id="runs-search" type="search" value={params.get('q') ?? ''}
                onChange={(e) => change('q', e.target.value)}
                placeholder="Search by run, brief or step"
                className="w-full rounded-lg bg-overlay border border-border pl-9 pr-3 py-2 text-sm text-text-primary"
              />
            </div>
            <label htmlFor="runs-filter" className="sr-only">Show</label>
            <select
              id="runs-filter" value={filter} onChange={(e) => change('status', e.target.value)}
              className="rounded-lg bg-overlay border border-border px-3 py-2 text-sm text-text-primary"
            >
              <option value="all">All runs</option>
              <option value="needs-you">Needs you</option>
              <option value="running">Running</option>
              <option value="finished">Finished</option>
            </select>
          </div>
          {shown.length === 0 ? (
            <p role="status" className="glass-card rounded-xl p-8 text-center text-sm text-text-secondary">
              No run matches. <button type="button" className="underline text-primary" onClick={() => setParams({}, { replace: true })}>Show every run</button>
            </p>
          ) : (
          <div className="relative glass-card rounded-xl overflow-x-auto">
            {/* Relative, so the visually hidden header label stays inside the scroller instead of widening the page. */}
            <table className="w-full text-sm">
              <caption className="sr-only">Runs, the ones that need you first</caption>
              <thead>
                <tr className="text-left text-xs text-text-secondary border-b border-border">
                  <th scope="col" className="px-4 py-3 font-medium">Status</th>
                  <th scope="col" className="px-4 py-3 font-medium">Run</th>
                  <th scope="col" className="px-4 py-3 font-medium hidden lg:table-cell">Brief</th>
                  <th scope="col" className="px-4 py-3 font-medium hidden md:table-cell">Mode</th>
                  <th scope="col" className="px-4 py-3 font-medium hidden xl:table-cell">Model</th>
                  <th scope="col" className="px-4 py-3 font-medium hidden md:table-cell text-right">Elapsed</th>
                  <th scope="col" className="px-4 py-3 font-medium text-right">Proven</th>
                  <th scope="col" className="px-4 py-3 font-medium hidden lg:table-cell text-right">Gaps</th>
                  <th scope="col" className="px-4 py-3 font-medium text-right"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((run) => {
                  const view = statusView(run.status);
                  const label = describeStage(run.current_stage).title;
                  const button = 'p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-overlay-strong transition-colors';
                  return (
                    <tr key={run.run_id} className={`border-b border-border last:border-0 hover:bg-overlay ${view.needsYou ? 'bg-accent-soft' : ''}`}>
                      <td className="px-4 py-3 align-top"><StatusBadge status={run.status} /></td>
                      <td className="px-4 py-3 align-top min-w-0">
                        <Link to={`/runs/${run.run_id}`} className="font-medium text-text-primary hover:underline">{label}</Link>
                        <div className="text-xs text-text-muted font-mono truncate max-w-[16rem]" title={run.run_id}>
                          {run.run_id} · {new Date(run.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </td>
                      <td className="px-4 py-3 align-top hidden lg:table-cell text-text-secondary max-w-[14rem] truncate" title={(run.document_names ?? []).join(', ')}>
                        {(run.document_names ?? [])[0] ?? '-'}
                      </td>
                      <td className="px-4 py-3 align-top hidden md:table-cell text-text-secondary capitalize">{run.delivery_mode ?? '-'}</td>
                      <td className="px-4 py-3 align-top hidden xl:table-cell text-text-secondary">
                        {run.local_only === null || run.local_only === undefined ? '-' : run.local_only ? 'Local only' : 'Local + judgement'}
                      </td>
                      <td className="px-4 py-3 align-top hidden md:table-cell text-right tabular-nums text-text-secondary">{elapsed(run)}</td>
                      <td className="px-4 py-3 align-top text-right tabular-nums">
                        {run.criteria_total ? `${run.criteria_proven ?? 0} of ${run.criteria_total}` : '-'}
                      </td>
                      <td className="px-4 py-3 align-top hidden lg:table-cell text-right tabular-nums">
                        {run.completion_gaps ? <span className="text-warning">{run.completion_gaps}</span> : <span className="text-text-muted">0</span>}
                      </td>
                      <td className="px-4 py-2 align-top whitespace-nowrap text-right">
                        {run.status === 'running' && (
                          <button type="button" onClick={() => handlePause(run.run_id)} className={button} aria-label={`Pause ${run.run_id}`} title="Pause run">
                            <Pause className="h-4 w-4" aria-hidden="true" />
                          </button>
                        )}
                        {RESUMABLE.includes(run.status) && (
                          <button type="button" onClick={() => handleResume(run.run_id)} className={button} aria-label={`Resume ${run.run_id}`} title="Resume run">
                            <Activity className="h-4 w-4" aria-hidden="true" />
                          </button>
                        )}
                        <button type="button" onClick={() => handleClone(run.run_id)} className={button} aria-label={`Clone ${run.run_id}`} title="Clone run">
                          <Copy className="h-4 w-4" aria-hidden="true" />
                        </button>
                        {view.terminal && (
                          <button type="button" onClick={() => handleDelete(run.run_id)} className={`${button} hover:text-danger`} aria-label={`Delete ${run.run_id}`} title="Delete run">
                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          )}
          {pages > 1 && (
            <nav aria-label="Pages of runs" className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-text-secondary">
              <p>
                Runs {first}-{last} of {total}
                {(filter !== 'all' || query) && ' (search and filters look at this page)'}
              </p>
              <div className="flex items-center gap-2">
                <Button size="sm" disabled={page <= 1} onClick={() => change('page', String(page - 1))}>Newer</Button>
                <span aria-current="page">Page {page} of {pages}</span>
                <Button size="sm" disabled={page >= pages} onClick={() => change('page', String(page + 1))}>Older</Button>
              </div>
            </nav>
          )}
        </div>
      )}

      {/* After the list: what the owner came for is the run that needs them. */}
      <OutcomesPanel />
    </div>
  );
};
