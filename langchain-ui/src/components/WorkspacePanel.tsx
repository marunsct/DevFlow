/**
 * The product's code as the run writes it (plan WS.1): the workspace's files as every stage's listing shows them
 * (`GET /runs/{id}/files`), one file's text highlighted, and its change since the last accepted sprint. Read-only:
 * nothing here edits. The tree reloads when the stream says a file was written, once per burst.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { getWorkspaceFile, getWorkspaceFileDiff, getWorkspaceFiles, type WorkspaceTree } from '../api';
import { highlight, type TokenKind } from '../lib/highlight';
import { lastWriteSequence } from '../lib/activity';
import type { LogEntry } from '../types';
import { DiffText } from './DiffText';

/** How long after the last write the tree reloads: a stage writes in bursts. */
export const RELOAD_AFTER_MS = 1500;

export interface Folder { name: string; path: string; folders: Folder[]; files: { name: string; path: string; size: number }[] }

export function asTree(files: WorkspaceTree['files']): Folder {
  const root: Folder = { name: '', path: '', folders: [], files: [] };
  for (const file of files) {
    const parts = file.path.split('/');
    let here = root;
    parts.slice(0, -1).forEach((name, index) => {
      let next = here.folders.find((f) => f.name === name);
      if (!next) {
        next = { name, path: parts.slice(0, index + 1).join('/'), folders: [], files: [] };
        here.folders.push(next);
      }
      here = next;
    });
    here.files.push({ name: parts[parts.length - 1], path: file.path, size: file.size });
  }
  return root;
}

const TOKEN_CLASS: Record<TokenKind, string> = {
  comment: 'text-text-muted italic',
  string: 'text-success',
  number: 'text-warning',
  keyword: 'text-primary font-medium',
  plain: '',
};

/** The present highlighter: also the workspace editor's view on a phone or when the editor does not load (plan UX.6). */
export const Code: React.FC<{ text: string; path: string }> = ({ text, path }) => {
  const lines = useMemo(() => highlight(text, path), [text, path]);
  return (
    <pre className="p-3 text-[12px] leading-5 font-mono" aria-label={`The text of ${path}`}>
      {lines.map((tokens, index) => (
        <div key={index} className="flex whitespace-pre">
          <span aria-hidden="true" className="w-10 shrink-0 select-none pr-3 text-right tabular-nums text-text-muted/60">{index + 1}</span>
          <span className="text-text-secondary">
            {tokens.length ? tokens.map((t, i) => <span key={i} className={TOKEN_CLASS[t.kind]}>{t.text}</span>) : ' '}
          </span>
        </div>
      ))}
    </pre>
  );
};

interface EntryProps {
  folder: Folder; depth: number; changed: Set<string>; selected: string | null; onSelect: (path: string) => void;
  /** A double click: keep the file open in its own tab (the workspace window, plan UX.5). */
  onPin?: (path: string) => void;
}

const FolderRows: React.FC<EntryProps> = ({ folder, depth, changed, selected, onSelect, onPin }) => {
  const [open, setOpen] = useState(depth < 1 || (!!selected && selected.startsWith(`${folder.path}/`)));
  const indent = { paddingLeft: `${0.75 + depth * 0.9}rem` };
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={indent}
        className="flex w-full items-center gap-1 py-1 pr-2 text-left text-[13px] text-text-primary hover:bg-overlay"
      >
        {open ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
        <span className="truncate">{folder.name}</span>
      </button>
      {open && <Entries folder={folder} depth={depth + 1} changed={changed} selected={selected} onSelect={onSelect} onPin={onPin} />}
    </li>
  );
};

const Entries: React.FC<EntryProps> = ({ folder, depth, changed, selected, onSelect, onPin }) => (
  <ul>
    {folder.folders.map((f) => (
      <FolderRows key={f.path} folder={f} depth={depth} changed={changed} selected={selected} onSelect={onSelect} onPin={onPin} />
    ))}
    {folder.files.map((file) => (
      <li key={file.path}>
        <button
          type="button"
          onClick={() => onSelect(file.path)}
          onDoubleClick={onPin ? () => onPin(file.path) : undefined}
          aria-current={selected === file.path ? 'true' : undefined}
          title={`${file.path} · ${file.size.toLocaleString()} bytes`}
          style={{ paddingLeft: `${0.75 + depth * 0.9 + 1}rem` }}
          className={`flex w-full items-center gap-2 py-1 pr-2 text-left font-mono text-[12px] hover:bg-overlay ${selected === file.path ? 'bg-overlay-strong text-text-primary' : 'text-text-secondary'}`}
        >
          <span className="min-w-0 truncate">{file.name}</span>
          {changed.has(file.path) && <span className="ml-auto text-[11px] text-warning" title="Changed since the last accepted sprint">changed</span>}
        </button>
      </li>
    ))}
  </ul>
);

/** The workspace's files as a folding tree, the changed ones marked. */
export const FileTree: React.FC<{
  tree: WorkspaceTree | null; selected: string | null; onSelect: (path: string) => void; onPin?: (path: string) => void;
}> = ({ tree, selected, onSelect, onPin }) => {
  const root = useMemo(() => asTree(tree?.files ?? []), [tree]);
  const changed = useMemo(() => new Set(tree?.changed ?? []), [tree]);
  return (
    <>
      {tree && !tree.files.length && <p className="p-3 text-sm text-text-muted">No files have been written yet.</p>}
      <Entries folder={root} depth={0} changed={changed} selected={selected} onSelect={onSelect} onPin={onPin} />
      {tree?.truncated && <p className="p-3 text-xs text-text-muted">Only the first {tree.files.length.toLocaleString()} files are listed.</p>}
    </>
  );
};

/**
 * The workspace's tree, read again when `refreshKey` moves and once a burst of writes in `logs` ends. `loads` counts
 * the reads, so an open file can follow them.
 */
export function useWorkspaceTree(runId: string, refreshKey: string, logs: LogEntry[]) {
  const [tree, setTree] = useState<WorkspaceTree | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [loads, setLoads] = useState(0);
  const written = useMemo(() => lastWriteSequence(logs), [logs]);

  const load = useCallback(() => {
    getWorkspaceFiles(runId)
      .then((data) => { setTree(data); setProblem(null); setLoads((n) => n + 1); })
      .catch(() => setProblem('The workspace could not be read.'));
  }, [runId]);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    if (!written) return;
    const timer = setTimeout(load, RELOAD_AFTER_MS);
    return () => clearTimeout(timer);
  }, [load, written]);
  return { tree, problem, loads };
}

type Shown = { path: string; text: string } | { path: string; problem: string };
type Diff = { path: string; text: string; truncated: boolean; since: string | null };

export const WorkspacePanel: React.FC<{
  runId: string;
  refreshKey: string;
  logs: LogEntry[];
  selected: string | null;
  onSelect: (path: string | null) => void;
  /** Open the selected file on its change since the last accepted sprint: a written file opened from the feed (plan WS.2). */
  diff?: boolean;
}> = ({ runId, refreshKey, logs, selected, onSelect, diff: diffAsked = false }) => {
  const { tree, problem, loads } = useWorkspaceTree(runId, refreshKey, logs);
  const [shown, setShown] = useState<Shown | null>(null);
  const [showDiff, setShowDiff] = useState(diffAsked);
  // Asked again for another file while the tab is open: show that file's change too.
  const [asked, setAsked] = useState({ diffAsked, selected });
  if (asked.diffAsked !== diffAsked || asked.selected !== selected) {
    setAsked({ diffAsked, selected });
    if (diffAsked) setShowDiff(true);
  }
  const [diff, setDiff] = useState<Diff | null>(null);

  // The open file follows the tree: read again whenever the tree is.
  useEffect(() => {
    if (!selected) return;
    let current = true;
    getWorkspaceFile(runId, selected)
      .then((data) => current && setShown({ path: selected, text: data.content }))
      .catch((error) => current && setShown({
        path: selected, problem: error?.response?.data?.detail || 'This file could not be read.',
      }));
    if (showDiff) {
      getWorkspaceFileDiff(runId, selected)
        .then((data) => current && setDiff({ path: selected, text: data.diff, truncated: data.truncated, since: data.since }))
        .catch(() => current && setDiff({ path: selected, text: '', truncated: false, since: null }));
    }
    return () => { current = false; };
  }, [runId, selected, loads, showDiff]);

  const file = shown && shown.path === selected ? shown : null;
  const fileDiff = diff && diff.path === selected ? diff : null;
  // A workspace with no history has no change to show, whatever was asked.
  const diffing = showDiff && !!tree?.since;

  if (problem && !tree) return <p className="p-4 text-sm text-text-muted">{problem}</p>;
  return (
    <div className="h-full grid grid-cols-1 md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] min-h-0">
      <nav aria-label="The workspace's files" className="overflow-y-auto border-b md:border-b-0 md:border-r border-border/40 min-h-0 max-h-48 md:max-h-none py-1">
        <FileTree tree={tree} selected={selected} onSelect={(path) => onSelect(path)} />
      </nav>
      <div className="flex min-h-0 flex-col">
        {selected && (
          <div className="flex items-center gap-2 border-b border-border/40 px-3 py-1.5">
            <span className="min-w-0 truncate font-mono text-[12px] text-text-primary" title={selected}>{selected}</span>
            {tree?.since && (
              <label className="ml-auto flex shrink-0 items-center gap-1.5 text-xs text-text-secondary">
                <input type="checkbox" role="switch" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
                Changed since {tree.since}
              </label>
            )}
          </div>
        )}
        <div className="flex-1 overflow-auto min-h-0" tabIndex={0} aria-label="The selected file">
          {!selected && <p className="p-4 text-sm text-text-muted">Choose a file to read it. Nothing here can be edited.</p>}
          {selected && !file && <p className="p-4 text-sm text-text-muted" role="status">Loading…</p>}
          {file && 'problem' in file && <p className="p-4 text-sm text-text-muted">{file.problem}</p>}
          {file && 'text' in file && diffing && fileDiff && (
            fileDiff.text
              ? <DiffText text={fileDiff.text} truncated={fileDiff.truncated} />
              : <p className="p-4 text-sm text-text-muted">No change since {fileDiff.since ?? 'the last accepted sprint'}.</p>
          )}
          {file && 'text' in file && diffing && !fileDiff && <p className="p-4 text-sm text-text-muted" role="status">Loading…</p>}
          {file && 'text' in file && !diffing && <Code text={file.text} path={file.path} />}
        </div>
      </div>
    </div>
  );
};
