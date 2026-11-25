/**
 * Go to a file by typing part of its path (plan UX.5, Ctrl P), over the tree already loaded: no request is sent.
 */
import React, { useId, useMemo, useRef, useState } from 'react';
import { Dialog } from '../../ui';
import { matchPaths } from './tabs';

export const GoToFile: React.FC<{
  open: boolean;
  onClose: () => void;
  paths: string[];
  onOpen: (path: string) => void;
}> = ({ open, onClose, paths, onOpen }) => {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const field = useRef<HTMLInputElement>(null);
  const listId = useId();
  const shown = useMemo(() => matchPaths(paths, query), [paths, query]);
  const current = Math.min(active, Math.max(0, shown.length - 1));

  const close = () => {
    setQuery('');
    setActive(0);
    onClose();
  };
  const choose = (path: string | undefined) => {
    if (!path) return;
    close();
    onOpen(path);
  };
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((current + step + shown.length) % Math.max(1, shown.length));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      choose(shown[current]);
    }
  };

  return (
    <Dialog open={open} onClose={close} title="Go to a file" size="lg" initialFocus={field}>
      <input
        ref={field}
        role="combobox"
        aria-label="Part of the file's path"
        aria-expanded="true"
        aria-controls={listId}
        aria-activedescendant={shown.length ? `${listId}-${current}` : undefined}
        aria-autocomplete="list"
        value={query}
        onChange={(event) => { setQuery(event.target.value); setActive(0); }}
        onKeyDown={onKeyDown}
        placeholder="app.py, src/routes…"
        spellCheck={false}
        className="w-full rounded-lg border border-border bg-inset px-3 py-2 font-mono text-sm text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
      />
      <ul id={listId} role="listbox" aria-label="Files" className="mt-2 max-h-80 overflow-y-auto">
        {shown.map((path, index) => {
          const cut = path.lastIndexOf('/');
          return (
            <li key={path} id={`${listId}-${index}`} role="option" aria-selected={index === current}
              onMouseEnter={() => setActive(index)} onClick={() => choose(path)}
              className={`flex cursor-pointer items-baseline gap-3 rounded-lg px-3 py-1.5 ${index === current ? 'bg-accent-soft' : ''}`}>
              <span className="shrink-0 font-mono text-[13px] text-text-primary">{path.slice(cut + 1)}</span>
              <span className="min-w-0 truncate font-mono text-[12px] text-text-muted">{cut > 0 ? path.slice(0, cut) : ''}</span>
            </li>
          );
        })}
        {!shown.length && <li className="px-3 py-2 text-sm text-text-muted">No file's path holds that.</li>}
      </ul>
    </Dialog>
  );
};
