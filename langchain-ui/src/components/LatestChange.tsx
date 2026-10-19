import React, { useEffect, useState } from 'react';
import { GitCommit } from 'lucide-react';
import { getChanges, type WorkspaceCommit } from '../api';

/** "3 files · +120/−8": what one commit changed, counted from its files. */
function changeSize(commit: WorkspaceCommit): string {
  const added = commit.files.reduce((sum, file) => sum + (file.added ?? 0), 0);
  const removed = commit.files.reduce((sum, file) => sum + (file.removed ?? 0), 0);
  const files = commit.files.length;
  return `${files} file${files === 1 ? '' : 's'} · +${added}/−${removed}`;
}

/**
 * The run's newest change, at the top of the rail (plan BG.4): what it was and
 * how big, opening the Changes tab on it.
 */
export const LatestChange: React.FC<{ runId: string; refreshKey: string; onOpen: (sha: string) => void }> = ({ runId, refreshKey, onOpen }) => {
  const [latest, setLatest] = useState<WorkspaceCommit | null>(null);
  useEffect(() => {
    let live = true;
    getChanges(runId)
      .then(({ commits }) => live && setLatest(commits[0] ?? null))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [runId, refreshKey]);
  if (!latest) return null;
  return (
    <button
      type="button"
      onClick={() => onOpen(latest.sha)}
      title={`${latest.message} - open it in Changes`}
      className="glass-card w-full rounded-xl px-3 py-2 text-left hover:bg-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
    >
      <span className="flex items-center gap-1.5 text-xs text-text-muted uppercase tracking-wider">
        <GitCommit className="h-3.5 w-3.5" aria-hidden="true" /> Latest change
      </span>
      <span className="mt-0.5 block truncate text-[13px] text-text-primary">{latest.message}</span>
      <span className="block text-xs text-text-secondary tabular-nums">{changeSize(latest)}</span>
    </button>
  );
};
