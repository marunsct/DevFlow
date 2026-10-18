import React, { useState } from 'react';
import type { ReviewPayload } from '../types';
import { MessageSquare, CheckCircle, XCircle, Download, UploadCloud, SkipForward } from 'lucide-react';
import { downloadArtifact } from '../api';

interface ReviewPanelProps {
  runId: string;
  review: ReviewPayload;
  onSubmit: (action: 'approve' | 'changes' | 'skip', comment: string, file?: File) => void;
  isLoading?: boolean;
}

export const ReviewPanel: React.FC<ReviewPanelProps> = ({ runId, review, onSubmit, isLoading }) => {
  const [comment, setComment] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const canSkip = review.available_actions.includes('skip');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  return (
    <div className="rounded-2xl overflow-hidden border border-primary/40 bg-primary/5 backdrop-blur-sm">
      <div className="px-5 py-3.5 bg-primary/10 border-b border-primary/30 flex items-center gap-2.5">
        <MessageSquare className="h-5 w-5 text-primary" />
        <h3 className="font-semibold text-primary text-sm">Review Required: {review.point}</h3>
      </div>
      <div className="p-5">
        {/* Artifact Info */}
        <div className="mb-4 p-4 rounded-xl bg-surface/50 border border-border/30 flex justify-between items-start">
          <div className="space-y-1.5 text-sm">
            <p className="text-text-secondary">
              <span className="text-text-muted">Artifact:</span>{' '}
              <span className="font-mono text-text-primary">{review.artifact_id}</span>
            </p>
            <p className="text-text-secondary">
              <span className="text-text-muted">Revision:</span>{' '}
              <span className="text-text-primary">{review.revision}</span>
            </p>
          </div>
          {review.artifact_id && (
            <button
              type="button"
              // Through the client, so the auth header goes with it; a plain
              // link is a navigation and the endpoint rejects it.
              onClick={() => void downloadArtifact(runId, review.artifact_id)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-surface border border-border rounded-lg text-text-secondary text-xs font-medium hover:text-text-primary hover:border-primary/50 transition-all shrink-0"
            >
              <Download className="h-3.5 w-3.5" />
              Download
            </button>
          )}
        </div>

        {/* Previous Comments */}
        {review.comments && review.comments.length > 0 && (
          <div className="mb-4 p-3 bg-inset rounded-xl border border-border/30">
            <p className="text-xs font-medium text-text-muted mb-1.5 uppercase tracking-wider">Previous Comments</p>
            <p className="whitespace-pre-wrap text-xs text-text-secondary">{review.comments}</p>
          </div>
        )}

        {/* Feedback Input */}
        <div className="mb-4">
          <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">
            Your Feedback
          </label>
          <textarea
            className="w-full rounded-xl border border-border bg-surface p-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all resize-none"
            rows={4}
            placeholder="Enter feedback or approval notes..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            disabled={isLoading}
          />
        </div>

        {/* File Upload */}
        <div className="mb-5">
          <label className="block text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">
            Upload Edited Artifact (Optional)
          </label>
          <div className="flex items-center gap-3">
            <input
              id="review-file-upload"
              type="file"
              className="hidden"
              onChange={handleFileChange}
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={() => document.getElementById('review-file-upload')?.click()}
              disabled={isLoading}
              className="flex items-center gap-1.5 px-3 py-2 bg-surface border border-border rounded-lg text-text-secondary text-xs font-medium hover:text-text-primary hover:border-primary/50 transition-all disabled:opacity-50"
            >
              <UploadCloud className="h-3.5 w-3.5" />
              Select File
            </button>
            {file && (
              <span className="text-xs text-text-secondary flex items-center gap-2">
                <span className="font-mono">{file.name}</span>
                <button
                  type="button"
                  onClick={() => setFile(null)}
                  className="text-danger hover:text-danger/80 text-xs font-medium"
                >
                  Remove
                </button>
              </span>
            )}
          </div>
          <p className="text-xs text-text-muted mt-1.5">
            Download the artifact, make your edits, then re-upload the modified file here.
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => onSubmit('approve', comment, file || undefined)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-5 py-2.5 bg-success/90 hover:bg-success text-text-primary rounded-xl font-semibold text-sm transition-all disabled:opacity-50 shadow-lg shadow-success/20"
          >
            <CheckCircle className="h-4 w-4" />
            Approve
          </button>
          <button
            onClick={() => onSubmit('changes', comment, file || undefined)}
            disabled={isLoading || (!comment.trim() && !file)}
            className="flex items-center gap-1.5 px-5 py-2.5 bg-danger/90 hover:bg-danger text-text-primary rounded-xl font-semibold text-sm transition-all disabled:opacity-50 shadow-lg shadow-danger/20"
            title={!comment.trim() && !file ? "A comment or uploaded file is required to request changes" : ""}
          >
            <XCircle className="h-4 w-4" />
            Request Changes
          </button>
          {canSkip && (
            <button
              onClick={() => onSubmit('skip', comment)}
              disabled={isLoading}
              className="flex items-center gap-1.5 px-5 py-2.5 bg-surface-overlay hover:bg-surface-overlay/80 text-text-secondary rounded-xl font-semibold text-sm transition-all disabled:opacity-50 border border-border"
            >
              <SkipForward className="h-4 w-4" />
              Skip
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
