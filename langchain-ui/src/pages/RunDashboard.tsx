import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom';
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
  downloadTranscript,
  startRun,
  type RewindPoint,
  getStreamTicket,
  getWizard
} from '../api';
import { LogViewer } from '../components/LogViewer';
import { LatestChange } from '../components/LatestChange';
import { AuditTable } from '../components/AuditTable';
import { ModelPressure } from '../components/ModelPressure';
import { Timeline } from '../components/Timeline';
import { Tabs } from '../ui';
import { ChangesPanel } from '../components/ChangesPanel';
import { SteeringBox } from '../components/SteeringBox';
import { ArtifactList } from '../components/ArtifactList';
import { ExecutionFlow } from '../components/ExecutionFlow';
import { AgentActivity } from '../components/AgentActivity';
import { ReviewPanel } from '../components/ReviewPanel';
import { ApprovalGate } from '../components/ApprovalGate';
import { WizardDashboard } from '../components/WizardDashboard';
import { SprintSummaryPanel } from '../components/SprintSummaryPanel';
import { DeliveryPanel } from '../components/DeliveryPanel';
import { RunFigures } from '../components/RunFigures';
import { fixLoop, useTypicalTime } from '../lib/runSummary';
import { holdingTheModel, useServerHealth } from '../lib/serverHealth';
import { Activity, CheckCircle2, Clock, XCircle, AlertCircle, ArrowLeft, Ban, Play, Pause, Copy, ListChecks, LayoutGrid, RotateCcw, Download } from 'lucide-react';
import { describeStage, describeStatus, RESUMABLE } from '../lib/activity';
import { useNow } from '../lib/usePageVisible';
import { useFeedback } from '../components/Feedback';



export const RunDashboard: React.FC = () => {
  const { notify, confirm: askConfirm } = useFeedback();
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
  // Whether the live stream is connected: it reconnects on its own, and said
  // nothing while it did - a stopped feed looked like a quiet run.
  const [streamDown, setStreamDown] = useState(false);
  const live = !!run && !['completed', 'failed', 'cancelled'].includes(run.status);
  const now = useNow(live);
  const typical = useTypicalTime(run?.delivery_mode, run?.criteria_total);
  // On a server that serves one request at a time, another run on it holds this one's calls.
  const health = useServerHealth();
  // A moment chosen on the timeline, for the feed to show.
  const [focusAt, setFocusAt] = useState<string | null>(null);
  const waitingOn = holdingTheModel(health, runId);
  // The tab says what the run needs, so a gate is seen from another tab.
  useEffect(() => {
    if (!run) return;
    const waiting = run.status === 'waiting_for_review' || run.status === 'waiting_for_approval';
    const mark = waiting ? '\u23F8 Needs you' : run.status === 'failed' ? '\u2716 Failed' : run.status === 'completed' ? '\u2714 Done' : run.status === 'running' ? '\u25B6' : '';
    document.title = `${mark ? mark + ' \u00B7 ' : ''}${run.run_id.slice(0, 12)} \u00B7 DevFlow.ai`;
    return () => { document.title = 'DevFlow.ai'; };
  }, [run?.status, run?.run_id]);
  const [actionLoading, setActionLoading] = useState(false);
  // The centre column carries two different audiences: what the run produced,
  // and the raw event log. Tabs let each have the full width instead of
  // splitting it and leaving both cramped.
  // Kept in the address, so a link or a reload opens the same view and change.
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get('view');
  type CentreTab = 'activity' | 'results' | 'log' | 'changes' | 'audit';
  const centreTab: CentreTab =
    viewParam === 'log' || viewParam === 'changes' || viewParam === 'results' || viewParam === 'audit' ? viewParam : 'activity';
  const selectedChange = searchParams.get('change');
  const setCentreTab = (tab: CentreTab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'activity') next.delete('view'); else next.set('view', tab);
    if (tab !== 'changes') next.delete('change');
    setSearchParams(next, { replace: true });
  };
  const selectChange = (sha: string | null) => {
    const next = new URLSearchParams(searchParams);
    next.set('view', 'changes');
    if (sha) next.set('change', sha); else next.delete('change');
    setSearchParams(next, { replace: true });
  };
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
  // Whether the live stream is open: while it is, it carries every event.
  const streamOpen = useRef(false);
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
  // A refresh asked for while one is in flight. Dropping it left the page on
  // the stage the in-flight read saw, until the next event or a reload.
  const fetchAgain = useRef(false);
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // The stage the last streamed event came from. The runner announces a
  // `stage_change` only at a gate; the stages between two gates (the specialist
  // consults, say) arrive as agent events alone, and the header, the progress
  // panel and the artifacts stayed on the first of them until a reload.
  const lastEventStage = useRef('');

  const fetchState = async () => {
    if (!runId) return;
    // One refresh at a time. Without this an event burst stacks overlapping
    // round-trips, each of which is two or three API calls.
    if (fetchInFlight.current) {
      fetchAgain.current = true;
      return;
    }
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
      // stream has already delivered - and only while the stream is down: an
      // open stream replays everything after the last event it saw, so paging
      // the same events again cost a request each refresh and gave nothing.
      if (!streamOpen.current) {
        const logsData = await getLogs(runId, 200, historyCursor.current);
        if (logsData.logs?.length) {
          historyCursor.current += logsData.logs.length;
          mergeLogs(logsData.logs);
        }
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
      if (fetchAgain.current) {
        fetchAgain.current = false;
        scheduleRefetch();
      }
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
        streamOpen.current = true;
        setStreamDown(false);
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

          const movedOn = !!logEntry.stage && logEntry.stage !== lastEventStage.current;
          if (logEntry.stage) lastEventStage.current = logEntry.stage;
          if (movedOn || ['stage_change', 'artifact', 'error', 'complete', 'approval_request', 'review_request', 'approval_auto'].includes(logEntry.event_type)) {
            scheduleRefetch();
          }
        } catch (err) {
          console.error('Could not parse a stream message:', err);
        }
      };

      ws.onerror = () => ws?.close();
      ws.onclose = () => {
        streamOpen.current = false;
        if (isSubscribed) {
          setStreamDown(true);
          scheduleReconnect();
        }
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
      notify("Failed to submit review: " + (err.response?.data?.detail || err.message));
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
      notify("Failed to submit approval: " + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!runId || !(await askConfirm({
      title: 'Cancel this run?',
      message: 'It stops at the next stage boundary and cannot be resumed. Pause it instead to continue later.',
      confirmLabel: 'Cancel run',
      danger: true,
    }))) return;
    try {
      await cancelRun(runId);
      await fetchState();
    } catch (err: any) {
      notify("Failed to cancel: " + (err.response?.data?.detail || err.message));
    }
  };

  const handlePause = async () => {
    if (!runId) return;
    try {
      await pauseRun(runId);
      await fetchState();
    } catch (err: any) {
      notify("Failed to pause: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleResume = async () => {
    if (!runId) return;
    try {
      await resumeRun(runId);
      await fetchState();
    } catch (err: any) {
      notify("Failed to resume: " + (err.response?.data?.detail || err.message));
    }
  };

  const openRewind = async () => {
    if (!runId) return;
    try {
      const points = await getRewindPoints(runId);
      setRewindPoints(points);
      setRewindTo(points.length ? points[points.length - 1].checkpoint_id : '');
    } catch (err: any) {
      notify("Failed to list rewind points: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleRewind = async () => {
    if (!runId || !rewindTo) return;
    const point = rewindPoints?.find((p) => p.checkpoint_id === rewindTo);
    if (!(await askConfirm({
      title: `Rewind to "${point ? describeStage(point.stage).title : rewindTo}"?`,
      message: 'The run starts again from there. Files made after that point are removed (a snapshot of them is kept).',
      confirmLabel: 'Rewind',
      danger: true,
    }))) return;
    try {
      const done = await rewindRun(runId, rewindTo);
      setRewindPoints(null);
      if (!done.files_restored) notify('Rewound. No snapshot of the files existed for that point, so they were left as they are.', 'info');
      await fetchState();
    } catch (err: any) {
      notify("Failed to rewind: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleClone = async () => {
    if (!runId) return;
    try {
      const clonedRun = await cloneRun(runId);
      navigate(`/runs/${clonedRun.run_id}`);
    } catch (err: any) {
      notify("Failed to clone: " + (err.response?.data?.detail || err.message));
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
      notify("Failed to start: " + (err.response?.data?.detail || err.message));
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

  if (!run) {
    return (
      <div className="max-w-lg mx-auto mt-20 p-8 glass-card rounded-2xl text-center">
        <AlertCircle className="h-12 w-12 text-danger mx-auto mb-4" />
        <h2 className="text-lg font-bold text-text-primary mb-2">Error Loading Run</h2>
        <p className="text-text-secondary">{error || "Run not found"}</p>
        <Link to="/runs" className="inline-block mt-6 text-primary hover:text-primary-hover text-sm font-medium">
          &larr; Back to Runs
        </Link>
      </div>
    );
  }


  const statusConfig: Record<string, { bg: string; text: string; glow: string; icon: any }> = {
    created: { bg: 'bg-overlay-strong', text: 'text-text-secondary', glow: '', icon: Clock },
    running: { bg: 'bg-accent-soft', text: 'text-primary', glow: 'status-running', icon: Activity },
    waiting_for_review: { bg: 'bg-warning-bg', text: 'text-warning', glow: 'status-warning', icon: AlertCircle },
    waiting_for_approval: { bg: 'bg-warning-bg', text: 'text-warning', glow: 'status-warning', icon: AlertCircle },
    completed: { bg: 'bg-success-bg', text: 'text-success', glow: 'status-success', icon: CheckCircle2 },
    failed: { bg: 'bg-danger-bg', text: 'text-danger', glow: 'status-danger', icon: XCircle },
    cancelled: { bg: 'bg-overlay-strong', text: 'text-text-secondary', glow: '', icon: XCircle },
    paused: { bg: 'bg-warning-bg', text: 'text-warning', glow: 'status-warning', icon: Clock },
  };

  const config = statusConfig[run.status] || statusConfig.created;
  const StatusIcon = config.icon;
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(run.status);

  // How long the run has been going, or took. The dashboard could say which
  // node was current but never how long any of it had taken, which is the first
  // thing anyone watching a long build wants to know.
  const startedAt = new Date(run.created_at).getTime();
  const endedAt = isTerminal ? new Date(run.updated_at).getTime() : now;
  const totalSeconds = Math.max(0, Math.round((endedAt - startedAt) / 1000));
  const elapsed =
    totalSeconds < 60
      ? `${totalSeconds}s`
      : totalSeconds < 3600
        ? `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`
        : `${Math.floor(totalSeconds / 3600)}h ${Math.floor((totalSeconds % 3600) / 60)}m`;

  const stageCopy = describeStage(run.current_stage);
  // Panels that read the run's state again when it moves to another stage or status.
  const stageKey = `${run.current_stage ?? ''}:${run.status}`;
  const statusCopy = describeStatus(run.status);

  const actionButton =
    'flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium rounded-lg border transition-colors';

  return (
    // `min-h`, not `h`: the panels below fill whatever the viewport has left
    // after the summary, but when they cannot fit their own minimum the page
    // grows and scrolls. Pinning the height instead made the workspace overflow
    // its container on a short screen and render underneath the footer.
    <div className="animate-fade-in flex flex-col gap-4 xl:min-h-[calc(100vh-11rem)]">
      {(error || streamDown) && (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-warning/30 bg-warning-bg px-4 py-2 text-sm text-warning">
          <span className="h-2 w-2 rounded-full bg-warning animate-pulse" aria-hidden="true" />
          {error
            ? `${error} The page shows the last state it loaded.`
            : 'Live updates paused - reconnecting. The page shows the last state it loaded.'}
        </div>
      )}
      {live && waitingOn && (
        <div role="status" className="rounded-xl border border-border bg-overlay px-4 py-2 text-sm text-text-secondary">
          The model serves one request at a time and {waitingOn} is on it: this run's calls wait for it to free the model.
        </div>
      )}
      {/* Top bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/runs"
          className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors"
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
                ? 'text-primary border-primary/30 hover:border-primary/60 hover:bg-primary/5'
                : 'text-text-secondary border-border hover:border-border-strong hover:bg-overlay'
            }`}
            title={viewMode === 'wizard' ? 'Switch to classic dashboard' : 'Switch to guided wizard'}
          >
            {viewMode === 'wizard' ? <LayoutGrid className="h-3.5 w-3.5" /> : <ListChecks className="h-3.5 w-3.5" />}
            {viewMode === 'wizard' ? 'Classic' : 'Wizard'}
          </button>
          {run.status === 'created' && (
            <button onClick={handleStart} disabled={actionLoading}
              className={`${actionButton} text-success border-success/30 hover:border-success/60 hover:bg-success/5 disabled:opacity-50`}>
              <Play className="h-3.5 w-3.5" /> Start
            </button>
          )}
          {run.status === 'running' && (
            <button onClick={handlePause}
              className={`${actionButton} text-warning border-warning/30 hover:border-warning/60 hover:bg-warning/5`}
              title="Stop at the next step and keep the run to resume later">
              <Pause className="h-3.5 w-3.5" /> Pause
            </button>
          )}
          {RESUMABLE.includes(run.status) && !run.error?.startsWith('Interrupted:') && (
            <button onClick={handleResume}
              className={`${actionButton} text-primary border-primary/30 hover:border-primary/60 hover:bg-primary/5`}>
              <Play className="h-3.5 w-3.5" /> Resume
            </button>
          )}
          {(RESUMABLE.includes(run.status) || run.status === 'completed') && rewindPoints === null && (
            <button onClick={openRewind}
              className={`${actionButton} text-text-secondary border-border hover:border-border-strong hover:bg-overlay`}
              title="Go back to the start of an earlier stage and run from there">
              <RotateCcw className="h-3.5 w-3.5" /> Rewind
            </button>
          )}
          {rewindPoints !== null && (
            <span className="flex items-center gap-2 flex-wrap">
              <select aria-label="The stage to go back to" value={rewindTo} onChange={(e) => setRewindTo(e.target.value)}
                className="bg-surface/50 border border-border/50 rounded-lg px-2 py-1 text-xs text-text-primary max-w-[16rem]">
                {rewindPoints.map((p) => (
                  <option key={p.checkpoint_id} value={p.checkpoint_id}>
                    {describeStage(p.stage).title}{p.sprint ? ` (sprint ${p.sprint})` : ''}
                    {p.at ? ` - ${new Date(p.at).toLocaleString()}` : ''}
                  </option>
                ))}
              </select>
              <button onClick={handleRewind} disabled={!rewindTo}
                className={`${actionButton} text-warning border-warning/30 hover:border-warning/60 hover:bg-warning/5 disabled:opacity-50`}>
                <RotateCcw className="h-3.5 w-3.5" /> Rewind here
              </button>
              <button onClick={() => setRewindPoints(null)}
                className={`${actionButton} text-text-secondary border-border hover:border-border-strong`}>
                Close
              </button>
            </span>
          )}
          <button onClick={handleClone}
            className={`${actionButton} text-text-secondary border-border hover:border-border-strong hover:bg-overlay`}>
            <Copy className="h-3.5 w-3.5" /> Clone
          </button>
          <button onClick={() => void downloadHandover(runId!)}
            title="The run's documents, decisions and acceptance suite, as one zip"
            className={`${actionButton} text-text-secondary border-border hover:border-border-strong hover:bg-overlay`}>
            <Download className="h-3.5 w-3.5" /> Handover pack
          </button>
          <button onClick={() => void downloadTranscript(runId!)}
            title="Every model call, reply, tool call and result of the run, as text"
            className={`${actionButton} text-text-secondary border-border hover:border-border-strong hover:bg-overlay`}>
            <Download className="h-3.5 w-3.5" /> Transcript
          </button>
          {!isTerminal && (
            <button onClick={handleCancel}
              className={`${actionButton} text-danger border-danger/30 hover:border-danger/60 hover:bg-danger/5`}>
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
                <h1 className="text-base sm:text-lg font-semibold text-text-primary leading-tight truncate">
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
            {fixLoop(run.remediation, run.current_stage) && (
              <p className="mt-1.5 text-xs text-text-secondary tabular-nums">{fixLoop(run.remediation, run.current_stage)}</p>
            )}
            {/* A completed run that knows what it did not prove says so here,
                beside the green badge - the record must not read as a plain
                success (Initiative J.4). */}
            {run.completion_gaps && run.completion_gaps.length > 0 && (
              <div className="mt-3 rounded-xl border border-warning/30 bg-warning-bg px-3 py-2">
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
            {/* The workspace tells the truth after the run ends: what the
                NON-DELIVERABLE marker says, on the run card (Initiative J.6). */}
            {run.non_deliverable && (
              <div className="mt-3 rounded-xl border border-danger/30 bg-danger-bg px-3 py-2">
                <p className="text-xs font-semibold text-danger">Marked non-deliverable</p>
                <p className="mt-0.5 text-xs text-text-secondary leading-relaxed">{run.non_deliverable}</p>
              </div>
            )}
          </div>

          <dl className="flex flex-wrap items-start gap-x-5 sm:gap-x-7 gap-y-3">
            <div>
              <dt className="text-xs text-text-muted uppercase tracking-wider">Started</dt>
              <dd className="mt-1 text-[13px] text-text-primary tabular-nums">
                {new Date(run.created_at).toLocaleString([], {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                })}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-text-muted uppercase tracking-wider">
                {isTerminal ? 'Took' : 'Running for'}
              </dt>
              <dd className="mt-1 text-[13px] text-text-primary tabular-nums">
                {elapsed}
                {!isTerminal && typical && <span className="block max-w-56 text-xs text-text-muted">{typical}</span>}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-text-muted uppercase tracking-wider">Documents</dt>
              <dd className="mt-1 text-[13px] text-text-primary tabular-nums">
                {run.artifacts?.length ?? 0} produced
              </dd>
            </div>
            <RunFigures run={run} />
          </dl>
        </div>

        <p className="mt-3 pt-3 border-t border-border/30 text-xs text-text-muted font-mono truncate">
          {run.run_id}
        </p>

        {/* A failure message can run to a dozen lines when the reviewer lists
            everything it is still unhappy about. Left unbounded it pushed the
            workspace off a 768px screen entirely, so it is clamped and expands
            on request. */}
        {run.error && (
          <div className="mt-3 rounded-xl border border-danger/30 bg-danger-bg px-4 py-3 text-[13px] text-danger">
            <p
              className={`whitespace-pre-wrap leading-relaxed ${
                errorOpen ? 'max-h-64 overflow-y-auto pr-1' : 'line-clamp-2'
              }`}
            >
              {run.error}
            </p>
            {run.error.length > 160 && (
              <button
                type="button"
                aria-expanded={errorOpen}
                onClick={() => setErrorOpen((v) => !v)}
                className="mt-1.5 text-[12px] font-medium text-danger hover:text-danger underline underline-offset-2"
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
        <>
          <GateDeadline run={run} now={now} />
          <ReviewPanel runId={runId!} review={review} onSubmit={handleReviewSubmit} isLoading={actionLoading} />
        </>
      )}
      {approval && (
        <>
          <GateDeadline run={run} now={now} />
          <ApprovalGate runId={runId!} approval={approval} onSubmit={handleApprovalSubmit} isLoading={actionLoading} />
        </>
      )}

      {/* The owner's direction to a run that is still going. */}
      {!isTerminal && run.status !== 'paused' && run.status !== 'waiting_for_budget' && <SteeringBox runId={runId!} stage={run.current_stage} />}
      {run.status === 'paused' && (
        <p role="status" className="text-sm text-text-muted">Resume the run to send it a direction.</p>
      )}

      {/* Workspace: the guided wizard or the classic dashboard. The wizard
          presents the run as phases (intake, design, sprints, summary) with a
          detail panel, under the sprints and the criteria. The classic
          dashboard is a rail, a work area and a ledger (plan BG.4): the stages
          with their times, the work in real tabs, and what is proven beside
          it, so a 1366x768 screen shows all three without scrolling. */}
      {viewMode === 'wizard' ? (
        <>
          <SprintSummaryPanel runId={runId!} refreshKey={stageKey} />
          <DeliveryPanel runId={runId!} refreshKey={stageKey} />
          <WizardDashboard run={run} model={wizard} />
        </>
      ) : (
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-[17rem_minmax(0,1fr)] xl:grid-cols-[19rem_minmax(0,1fr)_23rem] 2xl:grid-cols-[22rem_minmax(0,1fr)_28rem] min-[2200px]:grid-cols-[26rem_minmax(0,1fr)_34rem] xl:flex-1 xl:min-h-[28rem]">
        {/* At desktop width each column fills the row and scrolls inside it:
            no column's length sets the row's height, so the page ends where
            the window does. */}
        <div className="relative min-h-0 h-[22rem] sm:h-[26rem] lg:h-[32rem] xl:h-auto">
          <div className="flex h-full flex-col gap-3 xl:absolute xl:inset-0">
            <LatestChange runId={runId!} refreshKey={stageKey} onOpen={selectChange} />
            <ModelPressure runId={runId!} live={live} slotContext={health?.slot_context} />
            <div className="flex-1 min-h-0">
              <ExecutionFlow stages={run.stages || []} currentStage={run.current_stage} isTerminal={isTerminal} />
            </div>
          </div>
        </div>

        <div className="relative min-h-0 h-[26rem] sm:h-[30rem] lg:h-[32rem] xl:h-auto">
        <div className="h-full xl:absolute xl:inset-0 glass-card rounded-2xl flex flex-col overflow-hidden px-3 pt-1">
          <Tabs
            label="The run's work"
            className="flex h-full min-h-0 flex-col"
            panelClassName="flex-1 min-h-0"
            selected={centreTab}
            onSelect={(id) => setCentreTab(id as CentreTab)}
            items={[
              {
                id: 'activity',
                label: 'Activity',
                content: (
                  <div className="flex h-full flex-col">
                    <Timeline
                      runId={runId!}
                      startedAt={run.created_at}
                      endedAt={isTerminal && run.updated_at ? Date.parse(run.updated_at) : now}
                      stages={run.stages || []}
                      logs={logs}
                      onPick={setFocusAt}
                    />
                    <div className="flex-1 min-h-0">
                      <AgentActivity logs={logs} isRunning={!isTerminal} bare focusAt={focusAt} />
                    </div>
                  </div>
                ),
              },
              {
                id: 'changes',
                label: 'Changes',
                content: <ChangesPanel runId={runId!} refreshKey={stageKey} selected={selectedChange} onSelect={selectChange} />,
              },
              {
                id: 'log',
                label: <>Log <span className="text-xs tabular-nums text-text-muted">{logs.length}</span></>,
                content: <LogViewer logs={logs} />,
              },
              {
                id: 'results',
                label: <>Artifacts <span className="text-xs tabular-nums text-text-muted">{run.artifacts?.length ?? 0}</span></>,
                content: <ArtifactList artifacts={run.artifacts} runId={runId!} />,
              },
              { id: 'audit', label: 'Audit', content: <AuditTable runId={runId!} refreshKey={stageKey} /> },
            ]}
          />
        </div>
        </div>

        {/* The ledger scrolls inside its column: its length must not set the
            row's height, or the work area and the rail stretch with it. */}
        <div className="relative min-h-0 lg:col-span-2 xl:col-span-1">
          <div className="space-y-4 xl:absolute xl:inset-0 xl:overflow-y-auto">
            {/* Acceptance criteria, screenshots and the decision log, then the
                sprints - refreshed as the run moves between stages. */}
            <DeliveryPanel runId={runId!} refreshKey={stageKey} onOpenChange={selectChange} />
            <SprintSummaryPanel runId={runId!} refreshKey={stageKey} />
          </div>
        </div>
      </div>
      )}
    </div>
  );
};


/** Whether a waiting gate approves itself, and when - or that it waits for the person however long it takes. */
const GateDeadline: React.FC<{ run: RunStatusResponse; now: number }> = ({ run, now }) => {
  if (!run.gate_deadline) {
    return (
      <p role="status" className="text-sm text-text-secondary">
        This step waits for you however long it takes - nothing approves it on its own.
      </p>
    );
  }
  const at = new Date(run.gate_deadline);
  const minutes = Math.max(0, Math.round((at.getTime() - now) / 60000));
  const clock = at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return (
    <p role="status" className="text-sm text-warning">
      {minutes > 0
        ? `Approves itself at ${clock} (in ${minutes} min) unless you decide first.`
        : 'Approving itself now: its waiting time has passed.'}
    </p>
  );
};
