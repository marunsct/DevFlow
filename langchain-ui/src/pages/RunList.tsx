import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listRuns, deleteRun, cloneRun, resumeRun } from '../api';
import type { RunSummary } from '../types';
import { Clock, Activity, AlertCircle, CheckCircle2, XCircle, Inbox, Plus, Trash2, ArrowRight, Copy } from 'lucide-react';

export const RunList: React.FC = () => {
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

  useEffect(() => {
    fetchRuns();
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDelete = async (runId: string) => {
    if (!confirm('Delete this run?')) return;
    try {
      await deleteRun(runId);
      await fetchRuns();
    } catch (err: any) {
      alert('Failed to delete: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleClone = async (runId: string) => {
    try {
      const clonedRun = await cloneRun(runId);
      navigate(`/runs/${clonedRun.run_id}`);
    } catch (err: any) {
      alert("Failed to clone: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleResume = async (runId: string) => {
    try {
      await resumeRun(runId);
      await fetchRuns();
    } catch (err: any) {
      alert("Failed to resume: " + (err.response?.data?.detail || err.message));
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
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
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
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4 min-w-0 flex-1">
                    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border shrink-0 ${config.bg} ${config.text} ${config.glow}`}>
                      <StatusIcon className="h-3 w-3" />
                      <span className="uppercase tracking-wider">{run.status.replace(/_/g, ' ')}</span>
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-mono text-text-primary truncate">{run.run_id}</p>
                      <div className="flex items-center gap-3 mt-0.5 text-xs text-text-muted">
                        <span>{new Date(run.created_at).toLocaleString()}</span>
                        {run.current_stage && (
                          <>
                            <span>•</span>
                            <span className="text-text-secondary">{run.current_stage}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {isTerminal && (
                      <button
                        onClick={() => handleDelete(run.run_id)}
                        className="p-2 text-text-muted hover:text-danger hover:bg-danger/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                        title="Delete run"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                    {run.status === 'failed' && (
                      <button
                        onClick={() => handleResume(run.run_id)}
                        className="p-2 text-text-muted hover:text-white hover:bg-white/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                        title="Resume run"
                      >
                        <Activity className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() => handleClone(run.run_id)}
                      className="p-2 text-text-muted hover:text-white hover:bg-white/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
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
