import React, { useEffect, useState } from 'react';
import { fetchArtifactContent, getDocumentDiff, type DocumentDiff } from '../api';
import { Skeleton, Tabs } from '../ui';
import { Markdown } from './Markdown';
import { DiffText } from './DiffText';

/**
 * The document a gate asks about, in place (plan BG.3): read here, not
 * downloaded, edited and uploaded again. From the second revision on, what
 * changed since the version before is a tab beside it.
 */
export const GateDocument: React.FC<{ runId: string; path: string; revision: number }> = ({ runId, path, revision }) => {
  const [text, setText] = useState<string | null | undefined>(undefined);
  const [diff, setDiff] = useState<DocumentDiff | null>(null);

  useEffect(() => {
    let live = true;
    fetchArtifactContent(runId, path).then((found) => live && setText(found));
    if (revision > 1) {
      getDocumentDiff(runId, path)
        .then((found) => live && setDiff(found))
        .catch(() => undefined);
    }
    return () => {
      live = false;
    };
  }, [runId, path, revision]);

  if (text === undefined) return <Skeleton lines={4} />;
  if (text === null) return <p className="text-sm text-text-muted">The document is not available yet.</p>;

  const body = (
    <div className="max-h-[50vh] overflow-y-auto rounded-xl border border-border/40 bg-surface p-4">
      {path.endsWith('.md') ? <Markdown>{text}</Markdown> : <pre className="whitespace-pre-wrap text-xs font-mono text-text-secondary">{text}</pre>}
    </div>
  );
  if (!diff || !diff.diff) return body;
  return (
    <Tabs
      label="The document"
      items={[
        { id: 'document', label: 'Document', content: body },
        {
          id: 'changed',
          label: 'What changed',
          content: (
            <div className="max-h-[50vh] overflow-auto rounded-xl border border-border/40 bg-surface">
              <p className="px-4 pt-3 text-xs text-text-muted">Since the version of {new Date(diff.since_at ?? '').toLocaleString()}</p>
              <DiffText text={diff.diff} truncated={diff.truncated} />
            </div>
          ),
        },
      ]}
    />
  );
};
