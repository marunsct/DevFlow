import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listRuns, deleteRun, cloneRun, resumeRun, pauseRun } from '../api';
import type { RunSummary } from '../types';
import { Clock, Activity, AlertCircle, CheckCircle2, XCircle, Inbox, Plus, Trash2, ArrowRight, Copy, Pause } from 'lucide-react';
import { describeStage, describeStatus, RESUMABLE } from '../lib/activity';
import { OutcomesPanel } from '../components/OutcomesPanel';
import { usePageVisible } from '../lib/usePageVisible';
import { useFeedback } from '../components/Feedback';

export const RunList: React.FC = () => {
  const { notify, confirm: askConfirm } = useFeedback();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const fetchRuns = async () => {
    try {
      const response = await listRuns();
      const sortedRuns = response.runs.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setRuns(sortedRuns);
    } catch (err: any) {
      console.error(err);
      setError("Failed to load past runs.");
    } finally {
      setLoading(false);
    }
  };

  // Polled only while the tab is visible: a hidden tab polling every 5 s
  // spent the server's request budget for nobody.
  const visible = usePageVisible();
  useEffect(() => {
    if (!visible) return;
    fetchRuns();
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, [visible]);

  const handleDelete = async (runId: string) => {
    if (!(await askConfirm({
      title: 'Delete this run?',
      message: 'Its record and workspace are removed. This cannot be undone.',
      confirmLabel: 'Delete',
      danger: true,
    }))) return;
    try {
      await deleteRun(runId);
      await fetchRuns();
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
      await fetchRuns();
    } catch (err: any) {
      notify("Failed to pause: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleResume = async (runId: string) => {
    try {
      await resumeRun(runId);
      await fetchRuns();
    } catch (err: any) {
      notify("Failed to resume: " + (err.response?.data?.detail || err.message));
    }
  };

  const getStatusConfig = (status: string) => {
    const configs: Record<string, { bg: string; text: string; glow: string; icon: any }> = {
      created: { bg: 'bg-slate-500/20', text: 'text-slate-300', glow: '', icon: Clock },
      running: { bg: 'bg-primary/20', text: 'text-primary', glow: 'status-running', icon: Activity },
      waiting_for_review: { bg: 'bg-warning/20', text: 'text-warning', glow: 'status-warning', icon: AlertCircle },
      waiting_for_approval: { bg: 'bg-warning/20', text: 'text-warning', glow: 'status-warning', icon: AlertCircle },
      completed: { bg: 'bg-success/20', text: 'text-success', glow: 'status-success', icon: CheckCircle2 },
      failed: { bg: 'bg-danger/20', text: 'text-danger', glow: 'status-danger', icon: XCircle },
      cancelled: { bg: 'bg-slate-500/20', text: 'text-slate-400', glow: '', icon: XCircle },
      paused: { bg: 'bg-warning/20', text: 'text-warning', glow: 'status-warning', icon: Clock },
    };
    return configs[status] || configs.created;
  };

  return (
    <div className="w-full space-y-6 animate-fade-in">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Workflow Runs</h1>
          <p className="text-sm text-text-secondary mt-1">View and manage all your workflow runs</p>
        </div>
        <Link
          to="/"
          className="gradient-btn flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-white text-sm"
        >
          <Plus className="h-4 w-4" />
          New Run
        </Link>
      </div>

      <OutcomesPanel />

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="h-10 w-10 border-3 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : error ? (
        <div className="p-8 glass-card rounded-2xl text-center">
          <AlertCircle className="h-10 w-10 text-danger mx-auto mb-4" />
          <p className="text-danger">{error}</p>
        </div>
      ) : runs.length === 0 ? (
        <div className="glass-card rounded-2xl p-16 text-center">
          <Inbox className="h-14 w-14 text-text-muted mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-semibold text-white mb-2">No runs yet</h3>
          <p className="text-text-secondary mb-6 text-sm">Start your first workflow to see it here.</p>
          <Link
            to="/"
            className="gradient-btn inline-flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-white text-sm"
          >
            <Plus className="h-4 w-4" />
            Start Your First Run
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => {
            const config = getStatusConfig(run.status);
            const StatusIcon = config.icon;
            const isTerminal = ['completed', 'failed', 'cancelled'].includes(run.status);
            return (
              <div
                key={run.run_id}
                className="glass-card rounded-xl p-4 hover:bg-white/[0.03] transition-all duration-200 group"
              >
                {/* Stacks on a phone. Laid out as one row it put the status
                    chip, the step, a full timestamp, the run id and four
                    controls on a 390px line, which truncated the step name to
                    "De..." and left the buttons sitting on top of the date. */}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-start gap-3 min-w-0 flex-1 sm:items-center sm:gap-4">
                    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border shrink-0 ${config.bg} ${config.text} ${config.glow}`}>
                      <StatusIcon className="h-3 w-3" />
                      <span>{describeStatus(run.status).label}</span>
                    </div>
                    {/* The step it is on, in words, is what tells you whether a
                        run needs you. The run id is an identifier for support,
                        so it moves underneath rather than leading the row. */}
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white truncate">
                        {describeStage(run.current_stage).title}
                      </p>
                      <div className="mt-0.5 text-xs text-text-muted">
                        <span>
                          {new Date(run.created_at).toLocaleString([], {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                          })}
                        </span>
                        <span className="hidden sm:inline"> · </span>
                        <span className="block sm:inline font-mono truncate">{run.run_id}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                    {isTerminal && (
                      <button
                        onClick={() => handleDelete(run.run_id)}
                        className="p-2 text-text-muted hover:text-danger hover:bg-danger/10 rounded-lg transition-all sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 focus:opacity-100"
                        title="Delete run"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                    {run.status === 'running' && (
                      <button
                        onClick={() => handlePause(run.run_id)}
                        className="p-2 text-text-muted hover:text-warning hover:bg-warning/10 rounded-lg transition-all sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 focus:opacity-100"
                        title="Pause run"
                      >
                        <Pause className="h-4 w-4" />
                      </button>
                    )}
                    {RESUMABLE.includes(run.status) && (
                      <button
                        onClick={() => handleResume(run.run_id)}
                        className="p-2 text-text-muted hover:text-white hover:bg-white/10 rounded-lg transition-all sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 focus:opacity-100"
                        title="Resume run"
                      >
                        <Activity className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() => handleClone(run.run_id)}
                      className="p-2 text-text-muted hover:text-white hover:bg-white/10 rounded-lg transition-all sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 focus:opacity-100"
                      title="Clone run"
                    >
                      <Copy className="h-4 w-4" />
                    </button>
                    <Link
                      to={`/runs/${run.run_id}`}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-primary hover:text-primary-hover rounded-lg hover:bg-primary/10 transition-all"
                    >
                      Dashboard
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
