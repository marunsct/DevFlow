import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Download, FileText } from 'lucide-react';
import Markdown from 'react-markdown';
import { api } from '../api';

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
      } catch (err: any) {
        setError('Failed to load artifact content.');
      } finally {
        setLoading(false);
      }
    };
    fetchArtifact();
  }, [runId, path]);

  const handleDownload = () => {
    window.open(`/api/runs/${runId}/artifacts/download?path=${encodeURIComponent(path)}`, '_blank');
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fade-in">
      <div className="bg-[#1e2330]/95 backdrop-blur-xl border border-white/10 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-scale-in">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-white/10 bg-black/20">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2.5 bg-primary/20 rounded-xl shrink-0 shadow-inner">
              <FileText className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-white text-lg truncate tracking-tight">{path.split('/').pop()}</h3>
              <p className="text-xs text-primary/80 truncate font-mono mt-0.5">{path}</p>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={handleDownload}
              className="p-2 text-white/60 hover:text-white hover:bg-white/10 rounded-xl transition-all"
              title="Download"
            >
              <Download className="h-5 w-5" />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-white/60 hover:text-white hover:bg-white/10 rounded-xl transition-all"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-8 relative scroll-smooth">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center bg-[#1e2330]/50 backdrop-blur-sm z-10">
              <div className="flex flex-col items-center gap-4">
                <div className="h-10 w-10 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
                <p className="text-sm font-medium text-white/60 tracking-wider uppercase">Loading artifact...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-red-400 bg-red-400/10 px-6 py-4 rounded-xl border border-red-400/20 font-medium flex items-center gap-2">
                <X className="h-5 w-5" /> {error}
              </p>
            </div>
          ) : (
            <div className="prose prose-invert prose-primary max-w-none prose-pre:bg-[#13161f] prose-pre:border prose-pre:border-white/5 prose-pre:shadow-xl prose-pre:rounded-xl">
              {path.endsWith('.md') ? (
                <Markdown>{content || ''}</Markdown>
              ) : (
                <pre className="text-sm font-mono whitespace-pre-wrap leading-relaxed">{content}</pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};
