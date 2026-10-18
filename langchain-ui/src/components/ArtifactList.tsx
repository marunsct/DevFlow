import React, { useState } from 'react';
import type { ArtifactInfo } from '../types';
import { Download, FileText, Eye, Boxes } from 'lucide-react';
import { ArtifactViewer } from './ArtifactViewer';
import { downloadArtifact } from '../api';

interface ArtifactListProps {
  artifacts: ArtifactInfo[];
  runId: string;
}

/**
 * A readable name from the artifact's own path.
 *
 * `kind` is not usable as a title: it is either `file` or `structured`, so
 * using it labelled every row "Structured". The path carries the real name -
 * `docs/audit_log.md` or the logical `product_intake` - in both cases.
 */
const readableName = (artifact: ArtifactInfo) => {
  const base = (artifact.path.split('/').pop() || artifact.path).replace(/\.[^.]+$/, '');
  const spaced = base.replace(/[_-]+/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
};

/**
 * The documents and code this run produced, as a list a person can open.
 *
 * Renders as bare content, not a card: it lives inside the dashboard's tabbed
 * panel, which already supplies the surface and the heading. Drawing its own
 * header here produced a card inside a card and two competing titles.
 */
export const ArtifactList: React.FC<ArtifactListProps> = ({ artifacts, runId }) => {
  const [viewing, setViewing] = useState<ArtifactInfo | null>(null);

  if (!artifacts || artifacts.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 px-6 text-center">
        <span className="grid place-items-center h-10 w-10 rounded-xl bg-white/[0.03]">
          <FileText className="h-4 w-4 text-text-muted" />
        </span>
        <p className="text-sm text-text-secondary">Nothing produced yet</p>
        <p className="text-xs text-text-muted leading-relaxed max-w-xs">
          As the run works through its steps, the documents and code it writes will appear
          here for you to read or download.
        </p>
      </div>
    );
  }

  // Two different things arrive under one name. `file` is a document on disk
  // that can be opened and downloaded; `structured` is the step's own result
  // held in the run's state, with a logical name rather than a path. Offering
  // "download" on the second kind produced a link that could only 404, so they
  // are separated and only files get actions.
  const files = artifacts.filter((a) => a.kind === 'file');
  const results = artifacts.filter((a) => a.kind !== 'file');

  return (
    <div className="h-full overflow-y-auto p-3">
      {files.length > 0 && (
        <>
          <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-text-muted">
            Documents you can read
          </p>
          <ul className="space-y-1 mb-4">
            {files.map((artifact, index) => (
              <li
                key={`${artifact.path}-${index}`}
                className="group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-white/[0.04]"
              >
                <span className="flex-none grid place-items-center h-9 w-9 rounded-lg bg-primary/12 text-primary">
                  <FileText className="h-4 w-4" />
                </span>

                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-white truncate">{readableName(artifact)}</p>
                  <p className="text-[11px] text-text-muted font-mono truncate" title={artifact.path}>
                    {artifact.path}
                    {artifact.revision > 1 && ` · version ${artifact.revision}`}
                  </p>
                </div>

                <div className="flex-none flex items-center gap-1 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                  <button
                    onClick={() => setViewing(artifact)}
                    title="Read this document"
                    className="p-2 text-text-muted hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                  >
                    <Eye className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => {
                      // Through the client: a browser navigation carries no
                      // auth header and the endpoint answers with JSON.
                      void downloadArtifact(runId, artifact.path);
                    }}
                    title="Download"
                    className="p-2 text-text-muted hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {results.length > 0 && (
        <>
          <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-text-muted">
            Steps that finished
          </p>
          <ul className="space-y-0.5">
            {results.map((artifact, index) => (
              <li
                key={`${artifact.path}-${index}`}
                className="flex items-center gap-3 rounded-xl px-3 py-2"
              >
                <span className="flex-none grid place-items-center h-7 w-7 rounded-lg bg-white/[0.04] text-text-muted">
                  <Boxes className="h-3.5 w-3.5" />
                </span>
                <p className="min-w-0 flex-1 truncate text-[13px] text-text-secondary">
                  {readableName(artifact)}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}

      {viewing && (
        <ArtifactViewer runId={runId} path={viewing.path} onClose={() => setViewing(null)} />
      )}
    </div>
  );
};
