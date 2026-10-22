import React, { useId, useState } from 'react';
import type { ReviewPayload } from '../types';
import { MessageSquare, CheckCircle, XCircle, Download, SkipForward } from 'lucide-react';
import { downloadArtifact } from '../api';
import { Button, IconButton, Textarea } from '../ui';
import { describeStage } from '../lib/activity';
import { GateDocument } from './GateDocument';

interface ReviewPanelProps {
  runId: string;
  review: ReviewPayload;
  onSubmit: (action: 'approve' | 'changes' | 'skip', comment: string, file?: File) => void;
  isLoading?: boolean;
}

/**
 * A review as a composer (plan BG.3): the document in place, what changed since
 * the last revision, one comment box, and the answers. Replacing the document
 * with an edited copy is still possible, folded away: no review asks for a
 * download, an edit and an upload.
 */
export const ReviewPanel: React.FC<ReviewPanelProps> = ({ runId, review, onSubmit, isLoading }) => {
  const [comment, setComment] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const fileId = useId();

  const canSkip = review.available_actions.includes('skip');
  const title = describeStage(review.point).title;

  return (
    <section aria-labelledby={`${fileId}-title`} className="rounded-2xl overflow-hidden border border-primary/40 bg-primary/5">
      <div className="px-5 py-3.5 bg-accent-soft border-b border-primary/30 flex items-center gap-2.5">
        <MessageSquare className="h-5 w-5 text-primary" aria-hidden="true" />
        <h2 id={`${fileId}-title`} className="font-semibold text-primary text-sm">
          Your review: {title}
          {review.revision > 1 && <span className="font-normal"> · revision {review.revision}</span>}
        </h2>
        {review.artifact_id && (
          <IconButton
            className="ml-auto"
            size="sm"
            label="Download the document"
            icon={<Download className="h-3.5 w-3.5" />}
            // Through the client, so the auth header goes with it; a plain
            // link is a navigation and the endpoint rejects it.
            onClick={() => void downloadArtifact(runId, review.document || review.artifact_id)}
          />
        )}
      </div>
      <div className="p-5 space-y-4">
        {review.document ? (
          <GateDocument runId={runId} path={review.document} revision={review.revision} />
        ) : (
          <p className="text-sm text-text-secondary">
            This review is about <span className="font-mono">{review.artifact_id}</span>, which has no document to show here.
          </p>
        )}

        {review.comments && (
          <div className="p-3 bg-inset rounded-xl border border-border/30">
            <p className="text-xs font-medium text-text-muted mb-1.5">What you said last time</p>
            <p className="whitespace-pre-wrap text-xs text-text-secondary">{review.comments}</p>
          </div>
        )}

        <Textarea
          label="Your comment"
          hint="Needed to request changes; optional to approve."
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          disabled={isLoading}
        />

        <details className="text-xs text-text-secondary">
          <summary className="cursor-pointer text-text-muted">Replace it with your own version</summary>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <label htmlFor={fileId} className="text-text-secondary">An edited copy of the document</label>
            <input id={fileId} type="file" disabled={isLoading} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            {file && (
              <Button size="sm" variant="quiet" onClick={() => setFile(null)}>
                Remove {file.name}
              </Button>
            )}
          </div>
        </details>

        <div className="flex flex-wrap gap-3">
          <Button variant="primary" icon={<CheckCircle className="h-4 w-4" />} loading={isLoading} onClick={() => onSubmit('approve', comment, file || undefined)}>
            Approve
          </Button>
          <Button
            icon={<XCircle className="h-4 w-4" />}
            disabled={isLoading || (!comment.trim() && !file)}
            title={!comment.trim() && !file ? 'Say what to change, or give an edited copy' : undefined}
            onClick={() => onSubmit('changes', comment, file || undefined)}
          >
            Request changes
          </Button>
          {canSkip && (
            <Button variant="quiet" icon={<SkipForward className="h-4 w-4" />} disabled={isLoading} onClick={() => onSubmit('skip', comment)}>
              Skip
            </Button>
          )}
        </div>
      </div>
    </section>
  );
};
