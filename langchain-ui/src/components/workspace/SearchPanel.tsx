/**
 * Search across the workspace's files (plan UX.7): plain text, in the files the tree lists only, the server capping
 * the hits and the time. Each hit opens its file at its line.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CaseSensitive } from 'lucide-react';
import { searchWorkspaceFiles, type SearchAnswer, type SearchHit } from '../../api';
import { cx } from '../../ui';

/** How long typing pauses before the search is sent. */
export const SEARCH_AFTER_MS = 300;

const Marked: React.FC<{ hit: SearchHit; length: number }> = ({ hit, length }) => {
  // The line from a little before the match, so a long line still shows what matched.
  const start = Math.max(0, hit.column - 1 - 24);
  const at = hit.column - 1 - start;
  const text = hit.text.slice(start);
  return (
    <span className="truncate font-mono text-[12px] text-text-secondary">
      {start > 0 && '…'}{text.slice(0, at)}
      <mark className="rounded-[3px] bg-accent-soft px-px text-text-primary outline outline-1 outline-accent/50">{text.slice(at, at + length)}</mark>
      {text.slice(at + length)}
    </span>
  );
};

export const SearchPanel: React.FC<{
  runId: string;
  onOpen: (path: string, line: number) => void;
  /** Focus the field: the panel was asked for by its key. */
  focusKey?: number;
}> = ({ runId, onOpen, focusKey }) => {
  const [query, setQuery] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [found, setAnswer] = useState<SearchAnswer | null>(null);
  const [failed, setProblem] = useState<string | null>(null);
  const [busy, setSearching] = useState(false);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => { field.current?.focus(); field.current?.select(); }, [focusKey]);

  useEffect(() => {
    if (!query.trim()) return undefined;
    let current = true;
    const timer = setTimeout(() => {
      setSearching(true);
      searchWorkspaceFiles(runId, query, caseSensitive)
        .then((found) => { if (current) { setAnswer(found); setProblem(null); } })
        .catch(() => { if (current) setProblem('The search did not finish. Try again.'); })
        .finally(() => setSearching(false));
    }, SEARCH_AFTER_MS);
    return () => { current = false; clearTimeout(timer); };
  }, [runId, query, caseSensitive]);

  // An emptied field shows nothing, whatever an earlier search found.
  const asked = !!query.trim();
  const answer = asked ? found : null;
  const searching = asked && busy;
  const problem = asked ? failed : null;

  const byFile = useMemo(() => {
    const groups = new Map<string, SearchHit[]>();
    for (const hit of answer?.hits ?? []) groups.set(hit.path, [...(groups.get(hit.path) ?? []), hit]);
    return [...groups.entries()];
  }, [answer]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 px-2 pb-2">
        <input
          ref={field}
          type="search"
          aria-label="Search the files"
          placeholder="Search the files"
          value={query}
          maxLength={200}
          onChange={(event) => setQuery(event.target.value)}
          className="h-7 min-w-0 flex-1 rounded-md border border-border bg-inset px-2 text-[13px] text-text-primary placeholder:text-text-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        />
        <button type="button" aria-pressed={caseSensitive} aria-label="Match case" title="Match case"
          onClick={() => setCaseSensitive(!caseSensitive)}
          className={cx('inline-flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:bg-overlay', caseSensitive && 'bg-overlay-strong text-text-primary')}>
          <CaseSensitive size={15} aria-hidden="true" />
        </button>
      </div>
      <p role="status" className="px-3 pb-1 text-[12px] text-text-muted">
        {searching && 'Searching…'}
        {!searching && answer && (answer.hits.length
          ? `${answer.hits.length.toLocaleString()} line${answer.hits.length === 1 ? '' : 's'} in ${byFile.length} file${byFile.length === 1 ? '' : 's'}`
          : 'Nothing found in the listed files.')}
        {!searching && answer?.truncated && ' · only the first are shown'}
        {!searching && answer?.timed_out && ' · the search stopped before every file was read; narrow it'}
      </p>
      {problem && <p role="alert" className="px-3 text-[12px] text-danger">{problem}</p>}
      <ul aria-label="Search results" className="min-h-0 flex-1 overflow-y-auto pb-2">
        {byFile.map(([path, hits]) => (
          <li key={path}>
            <p className="flex items-baseline gap-2 px-3 pt-2 pb-0.5 text-[12px]">
              <span className="min-w-0 truncate font-mono text-text-primary" title={path}>{path}</span>
              <span className="ml-auto shrink-0 tabular-nums text-text-muted">{hits.length}</span>
            </p>
            <ul>
              {hits.map((hit) => (
                <li key={`${hit.line}:${hit.column}`}>
                  <button type="button" onClick={() => onOpen(hit.path, hit.line)}
                    className="flex w-full items-baseline gap-2 py-0.5 pl-5 pr-2 text-left hover:bg-overlay focus-visible:bg-overlay focus-visible:outline-none">
                    <span className="w-8 shrink-0 text-right font-mono text-[11px] tabular-nums text-text-muted">{hit.line}</span>
                    <Marked hit={hit} length={answer?.query.length ?? query.length} />
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
};
