import React, { useState } from 'react';
import type { ApprovalPayload } from '../types';
import { ShieldAlert, CheckCircle, XCircle, Download, FileWarning } from 'lucide-react';
import { downloadArtifact } from '../api';

interface ApprovalGateProps {
  runId: string;
  approval: ApprovalPayload;
  onSubmit: (action: 'approve' | 'reject', reason: string) => void;
  isLoading?: boolean;
}

export const ApprovalGate: React.FC<ApprovalGateProps> = ({ runId, approval, onSubmit, isLoading }) => {
  const [reason, setReason] = useState('');

  const riskColors: Record<string, string> = {
    low: 'text-success bg-success/10 border-success/30',
    medium: 'text-warning bg-warning/10 border-warning/30',
    high: 'text-danger bg-danger/10 border-danger/30',
  };

  return (
    <div className="rounded-2xl overflow-hidden border border-warning/40 bg-warning/5 backdrop-blur-sm">
      <div className="px-5 py-3.5 bg-warning/10 border-b border-warning/30 flex items-center gap-2.5">
        <ShieldAlert className="h-5 w-5 text-warning" />
        <h3 className="font-semibold text-warning text-sm">Write Approval Required</h3>
      </div>
      <div className="p-5">
        {/* Artifact Info */}
        <div className="mb-4 p-4 rounded-xl bg-surface/50 border border-border/30 space-y-2">
          <div className="flex justify-between items-start">
            <div className="space-y-1.5 text-sm">
              <p className="text-text-secondary">
                <span className="text-text-muted">Artifact:</span>{' '}
                <span className="font-mono text-text-primary">{approval.artifact_path}</span>
              </p>
              <p className="text-text-secondary">
                <span className="text-text-muted">Stage:</span>{' '}
                <span className="text-text-primary">{approval.stage}</span>
              </p>
              <p className="text-text-secondary">
                <span className="text-text-muted">Requested by:</span>{' '}
                <span className="text-text-primary">{approval.requested_by}</span>
              </p>
              <div className="flex items-center gap-2">
                <span className="text-text-muted text-sm">Risk:</span>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${riskColors[approval.risk_level] || riskColors.medium}`}>
                  <FileWarning className="h-3 w-3" />
                  {approval.risk_level.toUpperCase()}
                </span>
              </div>
            </div>
            {approval.artifact_path && (
              <button
              type="button"
              // Through the client, so the auth header goes with it; a plain
              // link is a navigation and the endpoint rejects it.
              onClick={() => void downloadArtifact(runId, approval.artifact_path)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-surface border border-border rounded-lg text-text-secondary text-xs font-medium hover:text-text-primary hover:border-primary/50 transition-all shrink-0"
              >
                <Download className="h-3.5 w-3.5" />
                Download
              </button>
            )}
          </div>
        </div>

        {/* Content Summary */}
        <div className="mb-4">
          <p className="text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">Content Preview</p>
          <pre className="whitespace-pre-wrap text-xs text-text-secondary bg-inset p-3 rounded-xl border border-border/30 max-h-32 overflow-y-auto font-mono">
            {approval.content_summary}
          </pre>
        </div>

        {/* Reason */}
        <div className="mb-5">
          <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">
            Comments (optional for approve, required for reject)
          </label>
          <textarea
            className="w-full rounded-xl border border-border bg-surface p-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-warning/30 focus:border-warning/50 transition-all resize-none"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={isLoading}
            placeholder="Enter your comments..."
          />
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={() => onSubmit('approve', reason)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-5 py-2.5 bg-success/90 hover:bg-success text-text-primary rounded-xl font-semibold text-sm transition-all disabled:opacity-50 shadow-lg shadow-success/20"
          >
            <CheckCircle className="h-4 w-4" />
            Approve
          </button>
          <button
            onClick={() => onSubmit('reject', reason)}
            disabled={isLoading || !reason.trim()}
            className="flex items-center gap-1.5 px-5 py-2.5 bg-danger/90 hover:bg-danger text-text-primary rounded-xl font-semibold text-sm transition-all disabled:opacity-50 shadow-lg shadow-danger/20"
            title={!reason.trim() ? "A reason is required to reject" : ""}
          >
            <XCircle className="h-4 w-4" />
            Reject
          </button>
        </div>
      </div>
    </div>
  );
};
