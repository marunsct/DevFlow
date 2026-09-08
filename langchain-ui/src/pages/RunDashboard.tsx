import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import type {
  RunStatusResponse,
  LogEntry,
  ReviewPayload,
  ApprovalPayload
} from '../types';
import {
  getRun,
  getLogs,
  getPendingReview,
  getPendingApproval,
  submitReview,
  submitApproval,
  cancelRun,
  resumeRun,
  cloneRun
} from '../api';
import { DynamicWorkflowUI } from '../components/DynamicWorkflowUI';
import { LogViewer } from '../components/LogViewer';
import { ArtifactList } from '../components/ArtifactList';
import { ReviewPanel } from '../components/ReviewPanel';
import { ApprovalGate } from '../components/ApprovalGate';
import { Activity, CheckCircle2, Clock, XCircle, AlertCircle, ArrowLeft, Ban, Play, Copy } from 'lucide-react';



export const RunDashboard: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [run, setRun] = useState<RunStatusResponse | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [review, setReview] = useState<ReviewPayload | null>(null);
  const [approval, setApproval] = useState<ApprovalPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const logsRef = useRef<LogEntry[]>([]);

  const fetchState = async () => {
    if (!runId) return;
    try {
      const runData = await getRun(runId);
      setRun(runData);

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

      const currentLogsLength = logsRef.current.length;
      const logsData = await getLogs(runId, 100, currentLogsLength);
      if (logsData.logs && logsData.logs.length > 0) {
        const newLogs = [...logsRef.current, ...logsData.logs];
        logsRef.current = newLogs;
        setLogs(newLogs);
      }

      setLoading(false);
    } catch (err: any) {
      console.error(err);
      setError("Failed to load run status.");
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 2000);
    return () => clearInterval(interval);
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

  const handleResume = async () => {
    if (!runId) return;
    try {
      await resumeRun(runId);
      await fetchState();
    } catch (err: any) {
      alert("Failed to resume: " + (err.response?.data?.detail || err.message));
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

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      {/* Top Bar */}
      <div className="flex items-center justify-between">
        <Link to="/runs" className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-white transition-colors">
          <ArrowLeft className="h-4 w-4" />
          All Runs
        </Link>
        <div className="flex gap-2">
          {run.status === 'failed' && (
            <button
              onClick={handleResume}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-primary/80 hover:text-primary border border-primary/30 hover:border-primary/60 rounded-lg transition-all hover:bg-primary/5"
            >
              <Play className="h-3.5 w-3.5" />
              Resume Run
            </button>
          )}
          <button
            onClick={handleClone}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-white/80 hover:text-white border border-white/30 hover:border-white/60 rounded-lg transition-all hover:bg-white/5"
          >
            <Copy className="h-3.5 w-3.5" />
            Clone Run
          </button>
          {!isTerminal && (
            <button
              onClick={handleCancel}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-danger/80 hover:text-danger border border-danger/30 hover:border-danger/60 rounded-lg transition-all hover:bg-danger/5"
            >
              <Ban className="h-3.5 w-3.5" />
              Cancel Run
            </button>
          )}
        </div>
      </div>

      {/* Header Card */}
      <div className="glass-card-strong rounded-2xl p-6">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-xl font-bold text-white mb-1">Workflow Run</h1>
            <p className="text-xs text-text-muted font-mono">{run.run_id}</p>
          </div>
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${config.bg} ${config.text} ${config.glow}`}>
            <StatusIcon className="h-3.5 w-3.5" />
            <span className="uppercase tracking-wider">{run.status.replace(/_/g, ' ')}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <div className="p-3 rounded-xl bg-surface/50 border border-border/30">
            <p className="text-xs font-medium text-text-muted mb-1 uppercase tracking-wider">Current Stage</p>
            <p className="font-semibold text-white text-sm">{run.current_stage || 'Not started'}</p>
          </div>
          <div className="p-3 rounded-xl bg-surface/50 border border-border/30">
            <p className="text-xs font-medium text-text-muted mb-1 uppercase tracking-wider">Activity</p>
            <p className="font-medium text-text-primary text-sm">{run.stage_meaning || 'Waiting...'}</p>
          </div>
          <div className="p-3 rounded-xl bg-surface/50 border border-border/30">
            <p className="text-xs font-medium text-text-muted mb-1 uppercase tracking-wider">Created</p>
            <p className="font-medium text-text-primary text-sm">{new Date(run.created_at).toLocaleString()}</p>
          </div>
        </div>

        <DynamicWorkflowUI run={run} />

        {run.error && (
          <div className="mt-4 p-3 bg-danger/10 border border-danger/30 rounded-xl text-danger text-sm">
            <strong>Error:</strong> {run.error.slice(0, 300)}
          </div>
        )}
      </div>

      {/* Action Gates */}
      {review && (
        <ReviewPanel
          runId={runId!}
          review={review}
          onSubmit={handleReviewSubmit}
          isLoading={actionLoading}
        />
      )}

      {approval && (
        <ApprovalGate
          runId={runId!}
          approval={approval}
          onSubmit={handleApprovalSubmit}
          isLoading={actionLoading}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <LogViewer logs={logs} />
        </div>
        <div>
          <ArtifactList artifacts={run.artifacts} runId={runId!} />
        </div>
      </div>
    </div>
  );
};
