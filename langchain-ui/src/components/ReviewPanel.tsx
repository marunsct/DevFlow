import React, { useState } from 'react';
import type { ReviewPayload } from '../types';
import { AlertCircle, CheckCircle, XCircle } from 'lucide-react';

interface ReviewPanelProps {
  review: ReviewPayload;
  onSubmit: (action: 'approve' | 'changes' | 'skip', comment: string) => void;
  isLoading?: boolean;
}

export const ReviewPanel: React.FC<ReviewPanelProps> = ({ review, onSubmit, isLoading }) => {
  const [comment, setComment] = useState('');

  const canSkip = review.available_actions.includes('skip');

  return (
    <div className="bg-warning/10 rounded-lg shadow-sm border border-warning overflow-hidden mt-6">
      <div className="px-4 py-3 bg-warning/20 border-b border-warning/30 flex items-center gap-2">
        <AlertCircle className="h-5 w-5 text-warning" />
        <h3 className="font-semibold text-warning-900">Review Required: {review.point}</h3>
      </div>
      <div className="p-4">
        <div className="mb-4 text-sm text-slate-700">
          <p><strong>Artifact ID:</strong> {review.artifact_id}</p>
          <p><strong>Revision:</strong> {review.revision}</p>
        </div>

        {review.comments && (
          <div className="mb-4 p-3 bg-white/50 rounded border border-warning/20 text-sm">
            <p className="font-medium text-slate-700 mb-1">Previous Comments:</p>
            <p className="whitespace-pre-wrap text-slate-600">{review.comments}</p>
          </div>
        )}

        <div className="mb-4">
          <label htmlFor="review-comment" className="block text-sm font-medium text-slate-700 mb-1">
            Your Feedback
          </label>
          <textarea
            id="review-comment"
            className="w-full rounded-md border border-slate-300 p-2 text-sm focus:border-warning focus:ring-warning"
            rows={4}
            placeholder="Enter feedback or approval notes..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            disabled={isLoading}
          />
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => onSubmit('approve', comment)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-4 py-2 bg-success text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
          >
            <CheckCircle className="h-4 w-4" />
            Approve
          </button>
          
          <button
            onClick={() => onSubmit('changes', comment)}
            disabled={isLoading || !comment.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-danger text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
            title={!comment.trim() ? "A comment is required to request changes" : ""}
          >
            <XCircle className="h-4 w-4" />
            Request Changes
          </button>

          {canSkip && (
            <button
              onClick={() => onSubmit('skip', comment)}
              disabled={isLoading}
              className="px-4 py-2 bg-slate-200 text-slate-700 rounded font-medium hover:bg-slate-300 disabled:opacity-50"
            >
              Skip Review
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
