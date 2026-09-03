import React, { useEffect, useState, useRef } from 'react';
import { useParams } from 'react-router-dom';
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
  submitApproval
} from '../api';
import { ProgressBar } from '../components/ProgressBar';
import { LogViewer } from '../components/LogViewer';
import { ArtifactList } from '../components/ArtifactList';
import { ReviewPanel } from '../components/ReviewPanel';
import { ApprovalGate } from '../components/ApprovalGate';
import { Activity, CheckCircle2, Clock, XCircle, AlertCircle } from 'lucide-react';

// Stages in order to calculate progress
const WORKFLOW_STAGES = [
  'initialize',
  'read_product_intake',
  'select_tools_and_models',
  'draft_technical_specification',
  'review_technical_specification',
  'draft_architecture',
  'review_architecture',
  'draft_sprint_plan',
  'review_sprint_plan',
  'finalize_plan'
];

export const RunDashboard: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  
  const [run, setRun] = useState<RunStatusResponse | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [review, setReview] = useState<ReviewPayload | null>(null);
  const [approval, setApproval] = useState<ApprovalPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  
  // Use a ref to store the latest logs to avoid dependency cycles in interval
  const logsRef = useRef<LogEntry[]>([]);
  
  const fetchState = async () => {
    if (!runId) return;
    try {
      const runData = await getRun(runId);
      setRun(runData);
      
      // If waiting for something, fetch it
      if (runData.status === 'waiting_for_review') {
        const reviewData = await getPendingReview(runId);
        if (reviewData.pending) {
          setReview(reviewData.review);
        }
      } else {
        setReview(null);
      }
      
      if (runData.status === 'waiting_for_approval') {
        const approvalData = await getPendingApproval(runId);
        if (approvalData.pending) {
          setApproval(approvalData.approval);
        }
      } else {
        setApproval(null);
      }
      
      // Fetch new logs
      const currentLogsLength = logsRef.current.length;
      const logsData = await getLogs(runId, 100, currentLogsLength);
      
      if (logsData.events && logsData.events.length > 0) {
        const newLogs = [...logsRef.current, ...logsData.events];
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
    
    // Poll every 2 seconds for updates
    const interval = setInterval(fetchState, 2000);
    
    return () => clearInterval(interval);
  }, [runId]);

  const handleReviewSubmit = async (action: 'approve' | 'changes' | 'skip', comment: string) => {
    if (!runId) return;
    setActionLoading(true);
    try {
      await submitReview(runId, { action, comment });
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

  if (loading && !run) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-slate-500 font-medium">Loading Workflow State...</p>
        </div>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="p-8 bg-danger/10 border border-danger/30 rounded-lg text-danger text-center">
        <AlertCircle className="h-10 w-10 mx-auto mb-4" />
        <h2 className="text-lg font-bold mb-2">Error Loading Run</h2>
        <p>{error || "Run not found"}</p>
      </div>
    );
  }

  // Calculate progress
  let progress = 0;
  if (run.status === 'completed') {
    progress = 100;
  } else if (run.current_stage) {
    const stageIndex = WORKFLOW_STAGES.indexOf(run.current_stage);
    if (stageIndex >= 0) {
      progress = Math.round((stageIndex / (WORKFLOW_STAGES.length - 1)) * 100);
    } else {
      progress = 50; // Fallback
    }
  }

  // Status badge config
  const statusConfig = {
    created: { color: 'bg-slate-200 text-slate-700', icon: Clock },
    running: { color: 'bg-blue-100 text-blue-700', icon: Activity },
    waiting_for_review: { color: 'bg-warning/20 text-warning-800', icon: AlertCircle },
    waiting_for_approval: { color: 'bg-danger/20 text-danger-800', icon: AlertCircle },
    completed: { color: 'bg-success/20 text-success-800', icon: CheckCircle2 },
    failed: { color: 'bg-danger/20 text-danger-800', icon: XCircle },
    cancelled: { color: 'bg-slate-200 text-slate-700', icon: XCircle },
    paused: { color: 'bg-warning/20 text-warning-800', icon: Clock }
  };

  const config = statusConfig[run.status as keyof typeof statusConfig] || statusConfig.created;
  const StatusIcon = config.icon;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header Card */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-800 mb-2">Workflow Run</h1>
            <p className="text-sm text-slate-500 font-mono">{run.run_id}</p>
          </div>
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${config.color}`}>
            <StatusIcon className="h-4 w-4" />
            <span className="uppercase tracking-wider text-xs">{run.status.replace(/_/g, ' ')}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div>
            <p className="text-sm font-medium text-slate-500 mb-1">Current Stage</p>
            <p className="font-semibold text-slate-800">{run.current_stage || 'Not started'}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500 mb-1">Activity</p>
            <p className="font-medium text-slate-700">{run.stage_meaning || 'Waiting...'}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500 mb-1">Created At</p>
            <p className="font-medium text-slate-700">{new Date(run.created_at).toLocaleString()}</p>
          </div>
        </div>

        <ProgressBar progress={progress} label="Workflow Progress" />
      </div>

      {/* Action Gates */}
      {review && (
        <ReviewPanel 
          review={review} 
          onSubmit={handleReviewSubmit}
          isLoading={actionLoading}
        />
      )}

      {approval && (
        <ApprovalGate 
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
          <ArtifactList artifacts={run.artifacts} />
        </div>
      </div>
    </div>
  );
};
