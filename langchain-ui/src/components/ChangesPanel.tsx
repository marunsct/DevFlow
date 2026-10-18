/**
 * What the run changed, commit by commit, from its workspace's own history
 * (`GET /runs/{id}/changes`). Every stage commits its work, so each entry is a
 * stage's change; choosing one shows its diff.
 */
import React, { useEffect, useState } from 'react';
import { getChange, getChanges, type WorkspaceCommit } from '../api';

const lineStyle = (line: string): string => {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-text-muted';
  if (line.startsWith('+')) return 'text-success bg-success-bg';
  if (line.startsWith('-')) return 'text-danger bg-danger-bg';
  if (line.startsWith('@@')) return 'text-primary';
  if (line.startsWith('diff --git')) return 'text-text-secondary font-semibold mt-3';
  return 'text-text-secondary';
};

export const ChangesPanel: React.FC<{
  runId: string;
  refreshKey: string;
  selected: string | null;
  onSelect: (sha: string | null) => void;
}> = ({ runId, refreshKey, selected, onSelect }) => {
  const [commits, setCommits] = useState<WorkspaceCommit[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{ sha: string; text: string; truncated: boolean } | null>(null);
  const diff = loaded && loaded.sha === selected ? loaded : null;

  useEffect(() => {
    getChanges(runId)
      .then((data) => { setCommits(data.commits); setProblem(data.problem ?? null); })
      .catch(() => setProblem('The change history could not be loaded.'));
  }, [runId, refreshKey]);

  useEffect(() => {
    if (!selected) return;
    getChange(runId, selected)
      .then((data) => setLoaded({ sha: selected, text: data.diff, truncated: data.truncated }))
      .catch(() => setLoaded({ sha: selected, text: 'This change could not be loaded.', truncated: false }));
  }, [runId, selected]);

  if (problem && !commits.length) {
    return <p className="p-4 text-sm text-text-muted">{problem}</p>;
  }
  return (
    <div className="h-full grid grid-cols-1 md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] min-h-0">
      <ul aria-label="Changes, newest first" className="overflow-y-auto border-b md:border-b-0 md:border-r border-border/40 min-h-0 max-h-48 md:max-h-none" tabIndex={0}>
        {commits.map((c) => {
          const added = c.files.reduce((n, f) => n + (f.added ?? 0), 0);
          const removed = c.files.reduce((n, f) => n + (f.removed ?? 0), 0);
          return (
            <li key={c.sha}>
              <button
                onClick={() => onSelect(selected === c.sha ? null : c.sha)}
                aria-current={selected === c.sha ? 'true' : undefined}
                className={`w-full text-left px-3 py-2 text-[13px] border-b border-border/20 hover:bg-overlay ${selected === c.sha ? 'bg-overlay-strong' : ''}`}
              >
                <span className="block text-text-primary truncate" title={c.message}>{c.message}</span>
                <span className="block text-[11px] text-text-muted tabular-nums">
                  {new Date(c.at).toLocaleString()} · {c.files.length} file{c.files.length === 1 ? '' : 's'}
                  {' '}<span className="text-success">+{added}</span> <span className="text-danger">-{removed}</span>
                </span>
              </button>
            </li>
          );
        })}
        {!commits.length && <li className="p-3 text-sm text-text-muted">Nothing has been changed yet.</li>}
      </ul>
      <div className="overflow-auto min-h-0" tabIndex={0} aria-label="The selected change">
        {!selected && <p className="p-4 text-sm text-text-muted">Choose a change to see what it did.</p>}
        {selected && !diff && <p className="p-4 text-sm text-text-muted" role="status">Loading…</p>}
        {diff && (
          <pre className="p-3 text-[12px] leading-5 font-mono">
            {diff.text.split('\n').map((line, i) => (
              <div key={i} className={`whitespace-pre px-1 ${lineStyle(line)}`}>{line || ' '}</div>
            ))}
            {diff.truncated && <div className="mt-2 text-text-muted">The rest of this change is too long to show here.</div>}
          </pre>
        )}
      </div>
    </div>
  );
};
