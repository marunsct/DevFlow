import React, { useState } from 'react';
import type { ArtifactInfo } from '../types';
import { FileText, Download, Package, Eye } from 'lucide-react';
import { ArtifactViewer } from './ArtifactViewer';

interface ArtifactListProps {
  artifacts: ArtifactInfo[];
  runId: string;
}

export const ArtifactList: React.FC<ArtifactListProps> = ({ artifacts, runId }) => {
  const [viewingArtifact, setViewingArtifact] = useState<ArtifactInfo | null>(null);

  if (!artifacts || artifacts.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-8 text-center">
        <Package className="h-10 w-10 text-text-muted mx-auto mb-3 opacity-40" />
        <p className="text-text-muted text-sm">No artifacts generated yet.</p>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border/50">
        <h3 className="font-semibold text-white text-sm flex items-center gap-2">
          <FileText className="h-4.5 w-4.5 text-primary" />
          Artifacts
          <span className="bg-primary/20 text-primary text-xs px-2 py-0.5 rounded-full font-semibold">
            {artifacts.length}
          </span>
        </h3>
      </div>
      <div className="divide-y divide-border/30">
        {artifacts.map((artifact, idx) => (
          <div key={`${artifact.kind}-${idx}`} className="p-4 hover:bg-white/[0.02] transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium text-white text-sm">{artifact.kind}</p>
                <div className="flex items-center gap-2 mt-1 text-xs text-text-muted">
                  <span>Rev {artifact.revision}</span>
                  <span>•</span>
                  <span>{artifact.created_by}</span>
                </div>
                <p className="text-xs text-text-muted mt-1 truncate font-mono" title={artifact.path}>
                  {artifact.path}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  className="p-2 text-text-muted hover:text-primary hover:bg-primary/10 rounded-lg transition-all"
                  title="View artifact"
                  onClick={() => setViewingArtifact(artifact)}
                >
                  <Eye className="h-4 w-4" />
                </button>
                <button
                  className="p-2 text-text-muted hover:text-primary hover:bg-primary/10 rounded-lg transition-all"
                  title="Download artifact"
                  onClick={() => window.open(`/api/runs/${runId}/artifacts/download?path=${encodeURIComponent(artifact.path)}`, '_blank')}
                >
                  <Download className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
      
      {viewingArtifact && (
        <ArtifactViewer
          runId={runId}
          path={viewingArtifact.path}
          onClose={() => setViewingArtifact(null)}
        />
      )}
    </div>
  );
};
