import React, { useState } from 'react';
import type { ReviewPayload } from '../types';
import { AlertCircle, CheckCircle, XCircle, Download, UploadCloud } from 'lucide-react';

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
    <div className="bg-warning/10 rounded-lg shadow-sm border border-warning overflow-hidden mt-6">
      <div className="px-4 py-3 bg-warning/20 border-b border-warning/30 flex items-center gap-2">
        <AlertCircle className="h-5 w-5 text-warning" />
        <h3 className="font-semibold text-warning-900">Review Required: {review.point}</h3>
      </div>
      <div className="p-4">
        <div className="mb-4 text-sm text-slate-700 flex justify-between items-start">
          <div>
            <p><strong>Artifact ID:</strong> {review.artifact_id}</p>
            <p><strong>Revision:</strong> {review.revision}</p>
          </div>
          {review.artifact_id && (
            <a 
              href={`/api/runs/${runId}/artifacts/download?path=${encodeURIComponent(review.artifact_id)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 rounded text-slate-700 hover:bg-slate-50 transition-colors"
            >
              <Download className="h-4 w-4" />
              Download Artifact
            </a>
          )}
        </div>

        {review.comments && review.comments.length > 0 && (
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
            className="w-full rounded-md border border-slate-300 p-2 text-sm focus:border-warning focus:ring-warning mb-2"
            rows={4}
            placeholder="Enter feedback or approval notes..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            disabled={isLoading}
          />
          
          <div className="mt-2">
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Upload Edited Artifact (Optional)
            </label>
            <div className="flex items-center gap-2">
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
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 rounded text-slate-700 text-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
              >
                <UploadCloud className="h-4 w-4" />
                Select File
              </button>
              {file && (
                <span className="text-sm text-slate-600 flex items-center gap-2">
                  {file.name}
                  <button 
                    type="button" 
                    onClick={() => setFile(null)}
                    className="text-danger hover:underline text-xs"
                  >
                    Remove
                  </button>
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              If you made manual changes to the downloaded artifact, upload the modified file here to incorporate your edits.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-3 mt-6">
          <button
            onClick={() => onSubmit('approve', comment, file || undefined)}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-4 py-2 bg-success text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
          >
            <CheckCircle className="h-4 w-4" />
            Approve
          </button>
          
          <button
            onClick={() => onSubmit('changes', comment, file || undefined)}
            disabled={isLoading || (!comment.trim() && !file)}
            className="flex items-center gap-1.5 px-4 py-2 bg-danger text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
            title={!comment.trim() && !file ? "A comment or uploaded file is required to request changes" : ""}
          >
            <XCircle className="h-4 w-4" />
            Request Changes / Regenerate
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
