import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import type {
  RunStatusResponse,
  LogEntry,
  ReviewPayload,
  ApprovalPayload,
  WizardModel
} from '../types';
import {
  getRun,
  getLogs,
  getPendingReview,
  getPendingApproval,
  submitReview,
  submitApproval,
  cancelRun,
  pauseRun,
  resumeRun,
  getRewindPoints,
  rewindRun,
  cloneRun,
  downloadHandover,
  startRun,
  type RewindPoint,
  getStreamTicket,
  getWizard
} from '../api';
import { LogViewer } from '../components/LogViewer';
import { ArtifactList } from '../components/ArtifactList';
import { ExecutionFlow } from '../components/ExecutionFlow';
import { AgentActivity } from '../components/AgentActivity';
import { ReviewPanel } from '../components/ReviewPanel';
import { ApprovalGate } from '../components/ApprovalGate';
import { WizardDashboard } from '../components/WizardDashboard';
import { SprintSummaryPanel } from '../components/SprintSummaryPanel';
import { DeliveryPanel } from '../components/DeliveryPanel';
import { Activity, CheckCircle2, Clock, XCircle, AlertCircle, ArrowLeft, Ban, Play, Pause, Copy, ListChecks, LayoutGrid, RotateCcw, Download } from 'lucide-react';
import { describeStage, describeStatus, RESUMABLE } from '../lib/activity';



export const RunDashboard: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [run, setRun] = useState<RunStatusResponse | null>(null);
  const [rewindPoints, setRewindPoints] = useState<RewindPoint[] | null>(null);
  const [rewindTo, setRewindTo] = useState<string>('');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  // The wizard model: the finished phase structure of the run, derived on the
  // server from its event history and graph state. Fetched alongside the run
  // itself so both are always in sync; `null` until the first fetch lands.
  const [wizard, setWizard] = useState<WizardModel | null>(null);
  const [review, setReview] = useState<ReviewPayload | null>(null);
  const [approval, setApproval] = useState<ApprovalPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  // The centre column carries two different audiences: what the run produced,
  // and the raw event log. Tabs let each have the full width instead of
  // splitting it and leaving both cramped.
  const [centreTab, setCentreTab] = useState<'results' | 'log'>('results');
  // A failure message can be a paragraph or twenty lines. Collapsed by default
  // so a short screen still has room for the panels underneath; the first lines
  // carry the summary, and the rest is one click away.
  const [errorOpen, setErrorOpen] = useState(false);
  // The view mode: the classic dashboard (stages + log) or the guided wizard
  // (phases + detail). Persisted so the reader's preference survives a reload.
  const [viewMode, setViewMode] = useState<'wizard' | 'classic'>(() => {
    try {
      return (localStorage.getItem('runView') as 'wizard' | 'classic') || 'classic';
    } catch {
      return 'classic';
    }
  });
  const handleViewModeChange = (mode: 'wizard' | 'classic') => {
    setViewMode(mode);
    try {
      localStorage.setItem('runView', mode);
    } catch {
      // localStorage can be unavailable (private mode); the preference just
      // does not persist.
    }
  };

  // Logs are keyed by event id so history pages and live events can be merged
  // without duplicates. The previous version deduplicated by JSON.stringify
  // across the whole array on every arriving message, and paged history using
  // the merged length as an offset - so live events silently shifted the cursor
  // past history the user had never seen.
  const logsById = useRef<Map<string, LogEntry>>(new Map());
  const historyCursor = useRef(0);
  const lastSequence = useRef(0);

  const mergeLogs = (incoming: LogEntry[]) => {
    if (incoming.length === 0) return;
    let changed = false;
    for (const entry of incoming) {
      const key = entry.event_id ?? `${entry.sequence}:${entry.timestamp}`;
      if (!logsById.current.has(key)) {
        logsById.current.set(key, entry);
        changed = true;
      }
      if (typeof entry.sequence === 'number' && entry.sequence > lastSequence.current) {
        lastSequence.current = entry.sequence;
      }
    }
    if (changed) {
      setLogs([...logsById.current.values()].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0)));
    }
  };

  const fetchInFlight = useRef(false);
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const fetchState = async () => {
    if (!runId) return;
    // One refresh at a time. Without this an event burst stacks overlapping
    // round-trips, each of which is two or three API calls.
    if (fetchInFlight.current) return;
    fetchInFlight.current = true;
    try {
      const runData = await getRun(runId);
      setRun(runData);

      // The wizard model is derived server-side from the same event history,
      // so it refreshes in lockstep with the run status. It is only needed in
      // wizard mode, but fetching it unconditionally keeps the two views equal
      // and costs one small request per (already coalesced) refresh.
      try {
        setWizard(await getWizard(runId));
      } catch {
        // A failed wizard fetch should not take the whole dashboard down; the
        // run status above is the load-bearing data. The wizard view shows its
        // own loading state on the next successful fetch.
        setWizard(null);
      }

      if (runData.status === 'waiting_for_review') {
        const reviewData = await getPendingReview(runId);
        if (reviewData.pending) setReview(reviewData.review);
      } else {
        setReview(null);
      }

      if (runData.status === 'waiting_for_approval') {
        const approvalData = await getPendingApproval(runId);
        if (approvalData.pending) setApproval(approvalData.approval);
      } else {
        setApproval(null);
      }

      // History paging uses its own cursor, independent of what the live
      // stream has already delivered.
      const logsData = await getLogs(runId, 200, historyCursor.current);
      if (logsData.logs?.length) {
        historyCursor.current += logsData.logs.length;
        mergeLogs(logsData.logs);
      }

      setError(null);
      setLoading(false);
    } catch (err: any) {
      console.error(err);
      setError(
        err?.response?.status === 429
          ? 'Too many updates at once. Catching up...'
          : 'Could not load this run. Retrying...'
      );
      setLoading(false);
    } finally {
      fetchInFlight.current = false;
    }
  };

  /**
   * Refresh soon, and only once, however many events arrive.
   *
   * An unattended run emits an `approval_auto` per gate - a thousand of them on
   * a long build - and the stream handler called `fetchState()` for each. Every
   * call is two or three requests, so a run like that fired several thousand in
   * a couple of minutes, tripped the 300-per-minute budget, and the resulting
   * 429 surfaced as "Could not load this run". Coalescing a burst into one
   * trailing refresh is what the UI actually wanted: the events themselves
   * already stream into the log view, and this is only for the run's summary.
   */
  const scheduleRefetch = () => {
    if (refetchTimer.current) clearTimeout(refetchTimer.current);
    refetchTimer.current = setTimeout(() => {
      refetchTimer.current = undefined;
      fetchState();
    }, 700);
  };

  useEffect(() => {
    if (!runId) return;

    fetchState();

    let ws: WebSocket | null = null;
    let isSubscribed = true;
    let attempt = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = async () => {
      if (!isSubscribed) return;
      try {
        // A short-lived ticket, not the bearer token, so no credential ends up
        // in the URL.
        const ticket = await getStreamTicket(runId);
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url =
          `${protocol}//${window.location.host}/api/runs/${runId}/events/stream` +
          `?ticket=${encodeURIComponent(ticket)}&last_event_id=${lastSequence.current}`;
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }

      ws.onopen = () => {
        attempt = 0;
      };

      ws.onmessage = (event) => {
        if (!isSubscribed) return;
        try {
          const message = JSON.parse(event.data);
          if (message.event === 'ping') return;
          if (message.event === 'closed') {
            // The run finished and the server closed the stream deliberately.
            isSubscribed = false;
            fetchState();
            return;
          }
          if (message.event === 'error') {
            console.error('Stream error:', message.data);
            return;
          }

          const logEntry: LogEntry = JSON.parse(message.data);
          mergeLogs([logEntry]);

          if (['stage_change', 'error', 'complete', 'approval_request', 'review_request', 'approval_auto'].includes(logEntry.event_type)) {
            scheduleRefetch();
          }
        } catch (err) {
          console.error('Could not parse a stream message:', err);
        }
      };

      ws.onerror = () => ws?.close();
      ws.onclose = () => {
        if (isSubscribed) scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (!isSubscribed) return;
      // Exponential backoff capped at 30s. The old loop retried every 3s
      // forever, including after the server closed a finished run.
      const delay = Math.min(30000, 1000 * 2 ** attempt);
      attempt += 1;
      retryTimer = setTimeout(connect, delay);
    };

    connect();

    return () => {
      isSubscribed = false;
      if (retryTimer) clearTimeout(retryTimer);
      // A pending refresh would otherwise fire after the page is gone, setting
      // state on an unmounted component.
      if (refetchTimer.current) clearTimeout(refetchTimer.current);
      ws?.close();
    };
  }, [runId]);

  const handleReviewSubmit = async (action: 'approve' | 'changes' | 'skip', comment: string, file?: File) => {
    if (!runId) return;
    setActionLoading(true);
    try {
      await submitReview(runId, { action, comment, file });
      setReview(null);
      await fetchState();
    } catch (err: any) {
      alert("Failed to submit review: " + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprovalSubmit = async (action: 'approve' | 'reject', reason: string) => {
    if (!runId) return;
    setActionLoading(true);
    try {
      await submitApproval(runId, { action, reason: reason || null });
      setApproval(null);
      await fetchState();
    } catch (err: any) {
      alert("Failed to submit approval: " + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!runId || !confirm('Are you sure you want to cancel this run?')) return;
    try {
      await cancelRun(runId);
      await fetchState();
    } catch (err: any) {
      alert("Failed to cancel: " + (err.response?.data?.detail || err.message));
    }
  };

  const handlePause = async () => {
    if (!runId) return;
    try {
      await pauseRun(runId);
      await fetchState();
    } catch (err: any) {
      alert("Failed to pause: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleResume = async () => {
    if (!runId) return;
    try {
      await resumeRun(runId);
      await fetchState();
    } catch (err: any) {
      alert("Failed to resume: " + (err.response?.data?.detail || err.message));
    }
  };

  const openRewind = async () => {
    if (!runId) return;
    try {
      const points = await getRewindPoints(runId);
      setRewindPoints(points);
      setRewindTo(points.length ? points[points.length - 1].checkpoint_id : '');
    } catch (err: any) {
      alert("Failed to list rewind points: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleRewind = async () => {
    if (!runId || !rewindTo) return;
    const point = rewindPoints?.find((p) => p.checkpoint_id === rewindTo);
    if (!confirm(`Rewind this run to the start of "${point ? describeStage(point.stage).title : rewindTo}" and run it from there? `
      + 'Files made after that point are removed (a snapshot of them is kept).')) return;
    try {
      const done = await rewindRun(runId, rewindTo);
      setRewindPoints(null);
      if (!done.files_restored) alert('Rewound. No snapshot of the files existed for that point, so they were left as they are.');
      await fetchState();
    } catch (err: any) {
      alert("Failed to rewind: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleClone = async () => {
    if (!runId) return;
    try {
      const clonedRun = await cloneRun(runId);
      navigate(`/runs/${clonedRun.run_id}`);
    } catch (err: any) {
      alert("Failed to clone: " + (err.response?.data?.detail || err.message));
    }
  };

  /**
   * Start a run that is registered but not running.
   *
   * A clone lands in `created` and nothing on this page could move it, so the
   * recommended recovery path - clone the damaged run - produced a run that sat
   * there. The settings the clone carried are already on the record; an empty
   * payload keeps them rather than overwriting them with defaults.
   */
  const handleStart = async () => {
    if (!runId) return;
    setActionLoading(true);
    try {
      await startRun(runId, {});
      await fetchState();
    } catch (err: any) {
      alert("Failed to start: " + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !run) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 border-3 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-text-secondary font-medium">Loading workflow state...</p>
        </div>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="max-w-lg mx-auto mt-20 p-8 glass-card rounded-2xl text-center">
        <AlertCircle className="h-12 w-12 text-danger mx-auto mb-4" />
        <h2 className="text-lg font-bold text-white mb-2">Error Loading Run</h2>
        <p className="text-text-secondary">{error || "Run not found"}</p>
        <Link to="/runs" className="inline-block mt-6 text-primary hover:text-primary-hover text-sm font-medium">
          &larr; Back to Runs
        </Link>
      </div>
    );
  }


  const statusConfig: Record<string, { bg: string; text: string; glow: string; icon: any }> = {
    created: { bg: 'bg-slate-500/20', text: 'text-slate-300', glow: '', icon: Clock },
    running: { bg: 'bg-primary/20', text: 'text-primary', glow: 'status-running', icon: Activity },
    waiting_for_review: { bg: 'bg-warning/20', text: 'text-warning', glow: 'status-warning', icon: AlertCircle },
    waiting_for_approval: { bg: 'bg-warning/20', text: 'text-warning', glow: 'status-warning', icon: AlertCircle },
    completed: { bg: 'bg-success/20', text: 'text-success', glow: 'status-success', icon: CheckCircle2 },
    failed: { bg: 'bg-danger/20', text: 'text-danger', glow: 'status-danger', icon: XCircle },
    cancelled: { bg: 'bg-slate-500/20', text: 'text-slate-400', glow: '', icon: XCircle },
    paused: { bg: 'bg-warning/20', text: 'text-warning', glow: 'status-warning', icon: Clock },
  };

  const config = statusConfig[run.status] || statusConfig.created;
  const StatusIcon = config.icon;
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(run.status);

  // How long the run has been going, or took. The dashboard could say which
  // node was current but never how long any of it had taken, which is the first
  // thing anyone watching a long build wants to know.
  const startedAt = new Date(run.created_at).getTime();
  const endedAt = isTerminal ? new Date(run.updated_at).getTime() : Date.now();
  const totalSeconds = Math.max(0, Math.round((endedAt - startedAt) / 1000));
  const elapsed =
    totalSeconds < 60
      ? `${totalSeconds}s`
      : totalSeconds < 3600
        ? `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`
        : `${Math.floor(totalSeconds / 3600)}h ${Math.floor((totalSeconds % 3600) / 60)}m`;

  const stageCopy = describeStage(run.current_stage);
  const statusCopy = describeStatus(run.status);

  const actionButton =
    'flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium rounded-lg border transition-colors';

  return (
    // `min-h`, not `h`: the panels below fill whatever the viewport has left
    // after the summary, but when they cannot fit their own minimum the page
    // grows and scrolls. Pinning the height instead made the workspace overflow
    // its container on a short screen and render underneath the footer.
    <div className="animate-fade-in flex flex-col gap-4 xl:min-h-[calc(100vh-11rem)]">
      {/* Top bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/runs"
          className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-white transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          All runs
        </Link>
        <div className="flex flex-wrap gap-2">
          {/* View mode toggle: the classic dashboard or the guided wizard. */}
          <button
            onClick={() => handleViewModeChange(viewMode === 'wizard' ? 'classic' : 'wizard')}
            className={`${actionButton} ${
              viewMode === 'wizard'
                ? 'text-primary/90 border-primary/30 hover:border-primary/60 hover:bg-primary/5'
                : 'text-white/80 border-white/20 hover:border-white/50 hover:bg-white/5'
            }`}
            title={viewMode === 'wizard' ? 'Switch to classic dashboard' : 'Switch to guided wizard'}
          >
            {viewMode === 'wizard' ? <LayoutGrid className="h-3.5 w-3.5" /> : <ListChecks className="h-3.5 w-3.5" />}
            {viewMode === 'wizard' ? 'Classic' : 'Wizard'}
          </button>
          {run.status === 'created' && (
            <button onClick={handleStart} disabled={actionLoading}
              className={`${actionButton} text-success/90 border-success/30 hover:border-success/60 hover:bg-success/5 disabled:opacity-50`}>
              <Play className="h-3.5 w-3.5" /> Start
            </button>
          )}
          {run.status === 'running' && (
            <button onClick={handlePause}
              className={`${actionButton} text-warning/90 border-warning/30 hover:border-warning/60 hover:bg-warning/5`}
              title="Stop at the next step and keep the run to resume later">
              <Pause className="h-3.5 w-3.5" /> Pause
            </button>
          )}
          {RESUMABLE.includes(run.status) && !run.error?.startsWith('Interrupted:') && (
            <button onClick={handleResume}
              className={`${actionButton} text-primary/90 border-primary/30 hover:border-primary/60 hover:bg-primary/5`}>
              <Play className="h-3.5 w-3.5" /> Resume
            </button>
          )}
          {(RESUMABLE.includes(run.status) || run.status === 'completed') && rewindPoints === null && (
            <button onClick={openRewind}
              className={`${actionButton} text-white/80 border-white/20 hover:border-white/50 hover:bg-white/5`}
              title="Go back to the start of an earlier stage and run from there">
              <RotateCcw className="h-3.5 w-3.5" /> Rewind
            </button>
          )}
          {rewindPoints !== null && (
            <span className="flex items-center gap-2 flex-wrap">
              <select value={rewindTo} onChange={(e) => setRewindTo(e.target.value)}
                className="bg-surface/50 border border-border/50 rounded-lg px-2 py-1 text-xs text-white max-w-[16rem]">
                {rewindPoints.map((p) => (
                  <option key={p.checkpoint_id} value={p.checkpoint_id}>
                    {describeStage(p.stage).title}{p.sprint ? ` (sprint ${p.sprint})` : ''}
                    {p.at ? ` - ${new Date(p.at).toLocaleString()}` : ''}
                  </option>
                ))}
              </select>
              <button onClick={handleRewind} disabled={!rewindTo}
                className={`${actionButton} text-warning/90 border-warning/30 hover:border-warning/60 hover:bg-warning/5 disabled:opacity-50`}>
                <RotateCcw className="h-3.5 w-3.5" /> Rewind here
              </button>
              <button onClick={() => setRewindPoints(null)}
                className={`${actionButton} text-white/60 border-white/10 hover:border-white/30`}>
                Close
              </button>
            </span>
          )}
          <button onClick={handleClone}
            className={`${actionButton} text-white/80 border-white/20 hover:border-white/50 hover:bg-white/5`}>
            <Copy className="h-3.5 w-3.5" /> Clone
          </button>
          <button onClick={() => void downloadHandover(runId!)}
            title="The run's documents, decisions and acceptance suite, as one zip"
            className={`${actionButton} text-white/80 border-white/20 hover:border-white/50 hover:bg-white/5`}>
            <Download className="h-3.5 w-3.5" /> Handover pack
          </button>
          {!isTerminal && (
            <button onClick={handleCancel}
              className={`${actionButton} text-danger/90 border-danger/30 hover:border-danger/60 hover:bg-danger/5`}>
              <Ban className="h-3.5 w-3.5" /> Cancel
            </button>
          )}
        </div>
      </div>

      {/* Summary. Leads with what is happening in plain words; the run id and
          stage name are present but demoted, because they matter only when
          something has to be reported or looked up. */}
      <div className="glass-card-strong rounded-2xl px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1 basis-80">
            <div className="flex items-center gap-2.5">
              <span className={`grid place-items-center h-8 w-8 rounded-xl ${config.bg}`}>
                <StatusIcon className={`h-4 w-4 ${config.text}`} />
              </span>
              <div className="min-w-0">
                <h1 className="text-base sm:text-lg font-semibold text-white leading-tight truncate">
                  {stageCopy.title}
                </h1>
                {/* A terminal run's stage title already *is* its status
                    ("Stopped", "Finished"), so repeating it underneath read as
                    a rendering bug rather than as emphasis. */}
                {statusCopy.label !== stageCopy.title && (
                  <p className={`text-xs font-medium ${config.text}`}>{statusCopy.label}</p>
                )}
              </div>
            </div>
            <p className="text-[13px] text-text-secondary leading-relaxed mt-2.5">
              {stageCopy.blurb}
            </p>
            {/* A completed run that knows what it did not prove says so here,
                beside the green badge - the record must not read as a plain
                success (Initiative J.4). */}
            {run.completion_gaps && run.completion_gaps.length > 0 && (
              <div className="mt-3 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2">
                <p className="text-xs font-semibold text-warning">
                  Completed with {run.completion_gaps.length} gap{run.completion_gaps.length === 1 ? '' : 's'} it did not prove
                </p>
                <ul className="mt-1 space-y-0.5">
                  {run.completion_gaps.map((gap, index) => (
                    <li key={index} className="text-xs text-text-secondary leading-relaxed">
                      • {gap}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <dl className="flex flex-wrap items-start gap-x-5 sm:gap-x-7 gap-y-3">
            <div>
              <dt className="text-[11px] text-text-muted uppercase tracking-wider">Started</dt>
              <dd className="mt-1 text-[13px] text-text-primary tabular-nums">
                {new Date(run.created_at).toLocaleString([], {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                })}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] text-text-muted uppercase tracking-wider">
                {isTerminal ? 'Took' : 'Running for'}
              </dt>
              <dd className="mt-1 text-[13px] text-text-primary tabular-nums">{elapsed}</dd>
            </div>
            <div>
              <dt className="text-[11px] text-text-muted uppercase tracking-wider">Documents</dt>
              <dd className="mt-1 text-[13px] text-text-primary tabular-nums">
                {run.artifacts?.length ?? 0} produced
              </dd>
            </div>
            {/* A partial total must not read as the whole spend: the
                MAX_RUN_COST_USD ceiling counts only the calls it could price. */}
            {run.cost && (
              <div>
                <dt className="text-[11px] text-text-muted uppercase tracking-wider">Spend</dt>
                <dd
                  className="mt-1 text-[13px] text-text-primary tabular-nums"
                  title={
                    run.cost.fully_priced
                      ? undefined
                      : `Partial: ${run.cost.unpriced_requests} call(s) had no known price ` +
                        `(${run.cost.unpriced_models.join(', ') || 'no usage reported'}). ` +
                        'The spending ceiling does not count them.'
                  }
                >
                  ${run.cost.estimated_cost_usd.toFixed(2)}
                  {!run.cost.fully_priced && (
                    <span className="text-warning"> + {run.cost.unpriced_requests} unpriced</span>
                  )}
                </dd>
              </div>
            )}
          </dl>
        </div>

        <p className="mt-3 pt-3 border-t border-border/30 text-[11px] text-text-muted font-mono truncate">
          {run.run_id}
        </p>

        {/* A failure message can run to a dozen lines when the reviewer lists
            everything it is still unhappy about. Left unbounded it pushed the
            workspace off a 768px screen entirely, so it is clamped and expands
            on request. */}
        {run.error && (
          <div className="mt-3 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-[13px] text-danger">
            <p
              className={`whitespace-pre-wrap leading-relaxed ${
                errorOpen ? 'max-h-64 overflow-y-auto pr-1' : 'line-clamp-2'
              }`}
            >
              {run.error}
            </p>
            {run.error.length > 160 && (
              <button
                onClick={() => setErrorOpen((v) => !v)}
                className="mt-1.5 text-[12px] font-medium text-danger/80 hover:text-danger underline underline-offset-2"
              >
                {errorOpen ? 'Show less' : 'Show the full reason'}
              </button>
            )}
            {run.error.startsWith('Interrupted:') && (
              <p className="mt-2 text-text-secondary">
                This run cannot be resumed. Use <strong>Clone</strong> to start again from the
                beginning with the same documents and settings.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Anything waiting on a person goes full width, above the workspace. It
          is the only thing on the page that is a request rather than a report. */}
      {review && (
        <ReviewPanel runId={runId!} review={review} onSubmit={handleReviewSubmit} isLoading={actionLoading} />
      )}
      {approval && (
        <ApprovalGate runId={runId!} approval={approval} onSubmit={handleApprovalSubmit} isLoading={actionLoading} />
      )}

      {/* Sprint Milestones - shown in both views */}
      <SprintSummaryPanel runId={runId!} />

      {/* Acceptance criteria, screenshots and the decision log. Refreshed as the
          run moves between stages. */}
      <DeliveryPanel runId={runId!} refreshKey={`${run.current_stage ?? ''}:${run.status}`} />

      {/* Workspace: the guided wizard or the classic dashboard. The wizard
          presents the run as phases (intake, design, sprints, summary) with a
          detail panel; the classic dashboard shows stages + log + activity. */}
      {viewMode === 'wizard' ? (
        <WizardDashboard run={run} model={wizard} />
      ) : (
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-[17rem_minmax(0,1fr)] xl:grid-cols-[19rem_minmax(0,1fr)_23rem] 2xl:grid-cols-[22rem_minmax(0,1fr)_28rem] min-[2200px]:grid-cols-[26rem_minmax(0,1fr)_34rem] xl:flex-1 xl:min-h-[28rem]">
        <div className="min-h-0 h-[22rem] sm:h-[26rem] lg:h-[32rem] xl:h-auto">
          <ExecutionFlow stages={run.stages || []} currentStage={run.current_stage} isTerminal={isTerminal} />
        </div>

        <div className="min-h-0 h-[26rem] sm:h-[30rem] lg:h-[32rem] xl:h-auto glass-card rounded-2xl flex flex-col overflow-hidden">
          <div className="flex-none flex items-center gap-1 px-3 py-2.5 border-b border-border/40">
            {([
              { id: 'results', label: 'Results', count: run.artifacts?.length ?? 0 },
              { id: 'log', label: 'Technical log', count: logs.length },
            ] as const).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setCentreTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors ${
                  centreTab === tab.id
                    ? 'bg-white/[0.07] text-white'
                    : 'text-text-muted hover:text-text-secondary hover:bg-white/[0.03]'
                }`}
              >
                {tab.label}
                <span className="text-[11px] tabular-nums opacity-60">{tab.count}</span>
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-0">
            {centreTab === 'results' ? (
              <ArtifactList artifacts={run.artifacts} runId={runId!} />
            ) : (
              <LogViewer logs={logs} />
            )}
          </div>
        </div>

        <div className="min-h-0 h-[26rem] sm:h-[30rem] lg:h-[24rem] lg:col-span-2 xl:col-span-1 xl:h-auto">
          <AgentActivity logs={logs} isRunning={!isTerminal} />
        </div>
      </div>
      )}
    </div>
  );
};
