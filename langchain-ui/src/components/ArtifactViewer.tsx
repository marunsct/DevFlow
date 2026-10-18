import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Download, FileText } from 'lucide-react';
import { Markdown } from './Markdown';
import { api } from '../api';
import { downloadArtifact } from '../api';

interface ArtifactViewerProps {
  runId: string;
  path: string;
  onClose: () => void;
}

export const ArtifactViewer: React.FC<ArtifactViewerProps> = ({ runId, path, onClose }) => {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchArtifact = async () => {
      setLoading(true);
      try {
        // Fetch it as text
        const res = await api.get(`/runs/${runId}/artifacts/download?path=${encodeURIComponent(path)}`, {
          responseType: 'text'
        });
        setContent(res.data);
      } catch (err) {
        // Logged rather than swallowed: the banner tells the reader the load
        // failed, and the console says why when someone comes to find out.
        console.error('Could not load artifact', path, err);
        setError('Could not load this document. Try again, or download it instead.');
      } finally {
        setLoading(false);
      }
    };
    fetchArtifact();
  }, [runId, path]);

  const [downloadError, setDownloadError] = useState('');

  /** Through the client, so the auth header goes with it. A plain
   *  `window.open` is a browser navigation and carries no header, which is why
   *  this button used to render `{"detail": "Not authenticated"}`. */
  const handleDownload = async () => {
    setDownloadError('');
    try {
      await downloadArtifact(runId, path);
    } catch {
      setDownloadError('Could not download this document.');
    }
  };

  // A dialog: Escape closes it, the page behind does not scroll, and focus
  // returns to whatever opened it.
  const closeRef = React.useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      before?.focus?.();
    };
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-scrim backdrop-blur-md animate-fade-in overscroll-contain" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="artifact-viewer-title" onClick={(e) => e.stopPropagation()} className="bg-surface-raised/95 backdrop-blur-xl border border-border rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-scale-in">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-border bg-inset">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2.5 bg-primary/20 rounded-xl shrink-0 shadow-inner">
              <FileText className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
              <h2 id="artifact-viewer-title" className="font-semibold text-text-primary text-lg truncate tracking-tight">{path.split('/').pop()}</h2>
              <p className="text-xs text-primary truncate font-mono mt-0.5">{path}</p>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={handleDownload}
              className="p-2 text-text-secondary hover:text-text-primary hover:bg-overlay-strong rounded-xl transition-all"
              title="Download"
              aria-label="Download"
            >
              <Download className="h-5 w-5" />
            </button>
            <button
              ref={closeRef}
              onClick={onClose}
              aria-label="Close"
              className="p-2 text-text-secondary hover:text-text-primary hover:bg-overlay-strong rounded-xl transition-all"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-8 relative scroll-smooth">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center bg-surface-raised/50 backdrop-blur-sm z-10">
              <div className="flex flex-col items-center gap-4">
                <div className="h-10 w-10 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
                <p className="text-sm font-medium text-text-secondary tracking-wider uppercase">Loading artifact...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-danger bg-danger-bg px-6 py-4 rounded-xl border border-danger/30 font-medium flex items-center gap-2">
                <X className="h-5 w-5" /> {error}
              </p>
            </div>
          ) : downloadError ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-danger bg-danger-bg px-6 py-4 rounded-xl border border-danger/30 font-medium flex items-center gap-2">
                <X className="h-5 w-5" /> {downloadError}
              </p>
            </div>
          ) : (
            // The `prose` classes here were inert: the Tailwind typography
            // plugin that defines them is not installed, so every artifact
            // rendered with default browser styles. The shared renderer styles
            // each element explicitly instead.
            <div className="max-w-none">
              {/\.(md|markdown)$/i.test(path) ? (
                <Markdown density="document">{content || ''}</Markdown>
              ) : (
                <pre className="text-sm font-mono whitespace-pre-wrap leading-relaxed text-text-primary">{content}</pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};
