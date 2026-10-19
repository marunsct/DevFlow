import React from 'react';
import { DiffText } from './DiffText';

interface FileDiff {
  path: string;
  body: string;
  added: number;
  removed: number;
}

/** A unified diff of several files, one entry per file, with its lines added and removed. */
function byFile(text: string): FileDiff[] {
  const files: FileDiff[] = [];
  for (const line of text.split('\n')) {
    if (line.startsWith('diff --git ')) {
      const path = / b\/(.+)$/.exec(line)?.[1] ?? line.slice('diff --git '.length);
      files.push({ path, body: line, added: 0, removed: 0 });
      continue;
    }
    const file = files[files.length - 1];
    if (!file) continue;
    file.body += `\n${line}`;
    if (line.startsWith('+') && !line.startsWith('+++')) file.added += 1;
    else if (line.startsWith('-') && !line.startsWith('---')) file.removed += 1;
  }
  return files;
}

/** Up to this many files open at once; a larger change opens folded, a list to choose from. */
const OPEN_UP_TO = 6;

/**
 * One commit's change, file by file (plan BG.9): each file folds, its heading
 * saying how many lines it added and removed, so a change of thirty files reads
 * as a list before it reads as a wall of diff.
 */
export const FileDiffs: React.FC<{ text: string; truncated?: boolean }> = ({ text, truncated }) => {
  const files = byFile(text);
  if (files.length <= 1) return <DiffText text={text} truncated={truncated} />;
  return (
    <div className="space-y-2 p-3">
      <p className="text-[11px] text-text-muted">{files.length} files</p>
      {files.map((file, index) => (
        <details key={`${file.path}-${index}`} open={files.length <= OPEN_UP_TO} className="rounded-lg border border-border/40">
          <summary className="flex cursor-pointer items-center gap-2 px-3 py-1.5 font-mono text-[12px] text-text-primary">
            <span className="min-w-0 truncate" title={file.path}>{file.path}</span>
            <span className="ml-auto tabular-nums text-success">+{file.added}</span>
            <span className="tabular-nums text-danger">{'−'}{file.removed}</span>
          </summary>
          <DiffText text={file.body} />
        </details>
      ))}
      {truncated && <p className="text-[12px] text-text-muted">The rest of this change is too long to show here.</p>}
    </div>
  );
};
