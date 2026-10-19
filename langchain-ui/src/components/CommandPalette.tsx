import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command as CommandIcon } from 'lucide-react';
import { listRuns } from '../api';
import type { RunListResponse, RunSummary } from '../types';
import { Dialog, IconButton, Kbd, useFeedback } from '../ui';
import { describeStage } from '../lib/activity';
import { getAppearance, nextTheme, setAppearance } from '../lib/appearance';
import { approveInOneTap, matchCommands, paletteKeys, SHORTCUTS, typing, type Command } from '../lib/commands';
import { inboxParts, oneTapAnswer, shortRunId } from '../lib/needsYou';

/**
 * The command palette (`⌘K` / `Ctrl K`) and the shortcuts sheet (`?`), from
 * any page (plan UI-S1). The palette reads the newest runs when it opens, so
 * "go to" and "approve" name runs as they stand.
 */
export const CommandPalette: React.FC<{
  /** Where the runs come from: the server, or sample runs on the kit page. */
  loadRuns?: () => Promise<RunListResponse>;
}> = ({ loadRuns = listRuns }) => {
  const navigate = useNavigate();
  const { notify } = useFeedback();
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const isOpen = useRef(open);
  useEffect(() => {
    isOpen.current = open;
  }, [open]);

  const show = useCallback(() => {
    setQuery('');
    setActive(0);
    setSheet(false);
    setOpen(true);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (isOpen.current) setOpen(false);
        else show();
      } else if (event.key === '?' && !event.metaKey && !event.ctrlKey && !event.altKey && !typing(event.target)) {
        event.preventDefault();
        setOpen(false);
        setSheet(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [show]);

  useEffect(() => {
    if (!open) return;
    let live = true;
    loadRuns()
      .then(({ runs: found }) => live && setRuns(found))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open, loadRuns]);

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => navigate(to);
    const fixed: Command[] = [
      { id: 'start', title: 'Start a build', hint: 'Home', keywords: 'new run brief', run: go('/') },
      { id: 'runs', title: 'Runs', hint: 'Every run', keywords: 'list history', run: go('/runs') },
      { id: 'settings', title: 'Settings', hint: 'Models and keys', keywords: 'model provider', run: go('/settings') },
      {
        id: 'theme', title: 'Switch the theme', hint: 'Dark, light, high contrast, the system\'s', keywords: 'appearance colour color dark light',
        run: () => setAppearance({ theme: nextTheme(getAppearance().theme) }),
      },
      { id: 'shortcuts', title: 'Keyboard shortcuts', hint: '?', keywords: 'keys help', run: () => setSheet(true) },
    ];
    const approvals: Command[] = runs.filter((run) => oneTapAnswer(run)).map((run) => ({
      id: `approve:${run.run_id}`,
      title: `Approve ${shortRunId(run.run_id)}`,
      // The title names the run; the hint says where it waits and what happens if nobody answers.
      hint: `${describeStage(run.current_stage).title} · ${inboxParts(run).what}`,
      keywords: `${run.run_id} gate review waiting`,
      run: async () => {
        try {
          await approveInOneTap(run);
          notify('Approved: the run goes on.', 'info');
        } catch {
          notify('The approval did not go through; open the run to answer it there.');
        }
      },
    }));
    const visits: Command[] = runs.slice(0, 20).map((run) => ({
      id: `run:${run.run_id}`,
      title: `Go to ${shortRunId(run.run_id)}`,
      hint: describeStage(run.current_stage).title,
      keywords: `${run.run_id} ${run.status} ${(run.document_names ?? []).join(' ')}`,
      run: go(`/runs/${run.run_id}`),
    }));
    return [...approvals, ...fixed, ...visits];
  }, [runs, navigate, notify]);

  const shown = useMemo(() => matchCommands(commands, query), [commands, query]);
  const current = Math.min(active, Math.max(0, shown.length - 1));

  const choose = (command: Command | undefined) => {
    if (!command) return;
    setOpen(false);
    void command.run();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((current + 1) % Math.max(1, shown.length));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((current - 1 + shown.length) % Math.max(1, shown.length));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      choose(shown[current]);
    }
  };

  const optionId = (index: number) => `${listId}-${index}`;

  return (
    <>
      <IconButton
        // A phone's header has no room for it; the palette has its keys.
        className="hidden sm:inline-flex"
        label={`Commands (${paletteKeys()})`}
        icon={<CommandIcon className="h-4 w-4" />}
        onClick={show}
      />

      <Dialog open={open} onClose={() => setOpen(false)} title="Commands" size="lg" initialFocus={input}>
        <input
          ref={input}
          type="text"
          role="combobox"
          aria-label="Find a command or a run"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={shown.length ? optionId(current) : undefined}
          aria-autocomplete="list"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          placeholder="Go to a run, start a build, approve..."
          className="w-full rounded-lg border border-border bg-inset px-3 py-2 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        />
        <ul id={listId} role="listbox" aria-label="Commands" className="mt-2 max-h-80 overflow-y-auto">
          {shown.map((command, index) => (
            <li
              key={command.id}
              id={optionId(index)}
              role="option"
              aria-selected={index === current}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(command)}
              className={`flex cursor-pointer flex-col gap-0.5 rounded-lg px-3 py-2 text-sm sm:flex-row sm:items-baseline sm:justify-between sm:gap-3 ${
                index === current ? 'bg-accent-soft text-text-primary' : 'text-text-secondary'
              }`}
            >
              <span className="shrink-0 font-medium">{command.title}</span>
              {command.hint && <span className="min-w-0 text-xs text-text-muted sm:truncate">{command.hint}</span>}
            </li>
          ))}
          {shown.length === 0 && <li className="px-3 py-2 text-sm text-text-muted">Nothing matches.</li>}
        </ul>
      </Dialog>

      <Dialog open={sheet} onClose={() => setSheet(false)} title="Keyboard shortcuts">
        <dl className="grid grid-cols-[max-content_1fr] items-baseline gap-x-4 gap-y-2">
          {SHORTCUTS.map(({ keys, what }) => (
            <React.Fragment key={what}>
              <dt className="flex gap-1">{keys.map((key) => <Kbd key={key}>{key}</Kbd>)}</dt>
              <dd className="text-sm text-text-secondary">{what}</dd>
            </React.Fragment>
          ))}
        </dl>
      </Dialog>
    </>
  );
};
