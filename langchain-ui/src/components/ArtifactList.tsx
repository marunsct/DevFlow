import React from 'react';
import type { ArtifactInfo } from '../types';
import { FileText, Eye } from 'lucide-react';

interface ArtifactListProps {
  artifacts: ArtifactInfo[];
}

export const ArtifactList: React.FC<ArtifactListProps> = ({ artifacts }) => {
  if (!artifacts || artifacts.length === 0) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden mt-6">
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200">
        <h3 className="font-semibold text-slate-800 flex items-center gap-2">
          <FileText className="h-5 w-5 text-slate-500" />
          Artifacts
        </h3>
      </div>
      <div className="divide-y divide-slate-100">
        {artifacts.map((artifact, idx) => (
          <div key={`${artifact.kind}-${idx}`} className="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors">
            <div>
              <p className="font-medium text-slate-800">{artifact.kind}</p>
              <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                <span>Rev: {artifact.revision}</span>
                <span>•</span>
                <span>By: {artifact.created_by}</span>
                <span>•</span>
                <span className="truncate max-w-[200px]" title={artifact.path}>
                  {artifact.path.split('/').pop()}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button 
                className="p-2 text-slate-500 hover:text-primary hover:bg-slate-200 rounded transition-colors"
                title="View Artifact"
                onClick={() => alert(`View artifact: ${artifact.path}`)}
              >
                <Eye className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
