import React, { useState } from 'react';
import type { ApprovalPayload } from '../types';
import { ShieldAlert, CheckCircle, XCircle } from 'lucide-react';

interface ApprovalGateProps {
  approval: ApprovalPayload;
  onSubmit: (action: 'approve' | 'reject', reason: string) => void;
  isLoading?: boolean;
}

export const ApprovalGate: React.FC<ApprovalGateProps> = ({ approval, onSubmit, isLoading }) => {
  const [reason, setReason] = useState('');

  return (
    <div className="bg-danger/10 rounded-lg shadow-sm border border-danger/50 overflow-hidden mt-6">
      <div className="px-4 py-3 bg-danger/20 border-b border-danger/30 flex items-center gap-2">
        <ShieldAlert className="h-5 w-5 text-danger" />
        <h3 className="font-semibold text-danger-900">Write Approval Required</h3>
      </div>
      <div className="p-4">
        <div className="mb-4 text-sm text-slate-700 bg-white/50 p-3 rounded border border-danger/20">
          <p><strong>Artifact:</strong> <span className="font-mono">{approval.artifact_path}</span></p>
          <p><strong>Stage:</strong> {approval.stage}</p>
          <p><strong>Risk Level:</strong> <span className="uppercase font-semibold text-danger">{approval.risk_level}</span></p>
          <p><strong>Requested By:</strong> {approval.requested_by}</p>
        </div>

        <div className="mb-4 text-sm">
          <p className="font-medium text-slate-800 mb-1">Content Summary:</p>
          <p className="whitespace-pre-wrap text-slate-600 bg-slate-50 p-3 rounded border border-slate-200">
            {approval.content_summary}
          </p>
        </div>

        <div className="mb-4">
          <label htmlFor="approval-reason" className="block text-sm font-medium text-slate-700 mb-1">
            Reason / Comments (optional for approval, required for rejection)
          </label>
          <textarea
            id="approval-reason"
            className="w-full rounded-md border border-slate-300 p-2 text-sm focus:border-danger focus:ring-danger"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={isLoading}
          />
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => onSubmit('approve', reason)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-4 py-2 bg-success text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
          >
            <CheckCircle className="h-4 w-4" />
            Approve Write
          </button>
          
          <button
            onClick={() => onSubmit('reject', reason)}
            disabled={isLoading || !reason.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-danger text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
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
