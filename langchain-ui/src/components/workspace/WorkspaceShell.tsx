/**
 * The workspace window (plan UX.5-UX.8), laid out as a code editor is: an activity bar (files, search, changes, the
 * preview beside the code), a resizable side panel, the open files as tabs over a Monaco reader or a side-by-side
 * diff, a bottom panel with the run's activity and log, and a status line naming the run's state and the stage
 * working now. Read-only: the run writes these files; nothing here edits them.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AppWindow, Files, GitCommitHorizontal, PanelBottomClose, PanelBottomOpen, Search, X,
} from 'lucide-react';
import { getWorkspaceFile, getWorkspaceFileAccepted } from '../../api';
import type { LogEntry, RunStatusResponse } from '../../types';
import { describeStage, describeStatus } from '../../lib/activity';
import { remember, remembered } from '../../lib/layoutMemory';
import { cx } from '../../ui';
import { AgentActivity } from '../AgentActivity';
import { ChangesPanel } from '../ChangesPanel';
import { LogViewer } from '../LogViewer';
import { PreviewPanel } from '../PreviewPanel';
import { FileTree, useWorkspaceTree } from '../WorkspacePanel';
import { Editor } from './Editor';
import { GoToFile } from './GoToFile';
import { SearchPanel } from './SearchPanel';
import { Splitter } from './Splitter';
import { closeFile, keepFile, NONE_OPEN, openFile, type OpenFiles } from './tabs';

type Activity = 'files' | 'search' | 'changes';
interface Layout { side: number; preview: number; bottom: number; sideOpen: boolean; bottomOpen: boolean; previewOpen: boolean }
export const LAYOUT_KEY = 'workspaceLayout';
const LAYOUT: Layout = { side: 272, preview: 560, bottom: 220, sideOpen: true, bottomOpen: false, previewOpen: false };

type Loaded = { text: string } | { problem: string };
type Base = { text: string; since: string | null; exists: boolean } | { problem: string };

const TONE: Record<string, string> = {
  active: 'bg-accent-soft text-text-primary',
  waiting: 'bg-warning-bg text-warning',
  error: 'bg-danger-bg text-danger',
  done: 'bg-success-bg text-success',
  idle: 'bg-surface text-text-secondary',
};

const ActivityButton: React.FC<{ label: string; on: boolean; onClick: () => void; children: React.ReactNode }> = ({ label, on, onClick, children }) => (
  <button type="button" aria-label={label} title={label} aria-pressed={on} onClick={onClick}
    className={cx(
      'relative inline-flex h-10 w-10 items-center justify-center rounded-md text-text-muted transition-colors hover:text-text-primary',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
      on && 'text-text-primary before:absolute before:inset-y-2 before:-left-1 before:w-0.5 before:rounded-full before:bg-accent',
    )}>
    <span aria-hidden="true">{children}</span>
  </button>
);

const nameOf = (path: string) => path.slice(path.lastIndexOf('/') + 1);

export const WorkspaceShell: React.FC<{
  runId: string;
  run: RunStatusResponse | null;
  logs: LogEntry[];
  /** A file to open first, kept (from the address). */
  initialFile?: string | null;
  /** The file shown now, for the address. */
  onActiveFile?: (path: string | null) => void;
}> = ({ runId, run, logs, initialFile, onActiveFile }) => {
  const refreshKey = `${run?.current_stage ?? ''}:${run?.status ?? ''}`;
  const { tree, problem: treeProblem, loads } = useWorkspaceTree(runId, refreshKey, logs);
  const [activity, setActivity] = useState<Activity>('files');
  const [layout, setLayout] = useState<Layout>(() => remembered(LAYOUT_KEY, LAYOUT));
  const [open, setOpen] = useState<OpenFiles>(() => (initialFile ? openFile(NONE_OPEN, initialFile, true) : NONE_OPEN));
  const [contents, setContents] = useState<Record<string, Loaded>>({});
  const [compare, setCompare] = useState(false);
  const [bases, setBases] = useState<Record<string, Base>>({});
  const [reveal, setReveal] = useState<{ path: string; line: number } | null>(null);
  const [goTo, setGoTo] = useState(false);
  const [searchFocus, setSearchFocus] = useState(0);
  const [bottomTab, setBottomTab] = useState<'activity' | 'log'>('activity');
  const [changeShown, setChangeShown] = useState<string | null>(null);

  const active = open.active;
  const paths = useMemo(() => (tree?.files ?? []).map((file) => file.path), [tree]);
  const settle = useCallback((change: Partial<Layout>) => {
    setLayout((before) => {
      const next = { ...before, ...change };
      remember(LAYOUT_KEY, next);
      return next;
    });
  }, []);

  useEffect(() => { onActiveFile?.(active); }, [active, onActiveFile]);

  // The file shown is read again whenever the tree is: a stage may have just written it.
  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    getWorkspaceFile(runId, active)
      .then((data) => current && setContents((all) => ({ ...all, [active]: { text: data.content } })))
      .catch((error) => current && setContents((all) => ({
        ...all, [active]: { problem: error?.response?.data?.detail || 'This file could not be read.' },
      })));
    return () => { current = false; };
  }, [runId, active, loads]);

  useEffect(() => {
    if (!active || !compare) return undefined;
    let current = true;
    getWorkspaceFileAccepted(runId, active)
      .then((data) => current && setBases((all) => ({ ...all, [active]: { text: data.content, since: data.since, exists: data.exists } })))
      .catch((error) => current && setBases((all) => ({
        ...all, [active]: { problem: error?.response?.data?.detail || 'The earlier version could not be read.' },
      })));
    return () => { current = false; };
  }, [runId, active, compare, loads]);

  const show = useCallback((path: string, keep = false, line?: number) => {
    setOpen((state) => openFile(state, path, keep));
    setReveal(line ? { path, line } : null);
    if (activity === 'changes') setActivity('files');
  }, [activity]);

  const chooseActivity = (next: Activity) => {
    if (next === activity && layout.sideOpen) settle({ sideOpen: false });
    else {
      setActivity(next);
      settle({ sideOpen: true });
    }
  };

  // The keys an editor answers to: go to a file, search, the side and bottom panels.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === 'p' && !event.shiftKey) {
        event.preventDefault();
        setGoTo(true);
      } else if (key === 'f' && event.shiftKey) {
        event.preventDefault();
        setActivity('search');
        settle({ sideOpen: true });
        setSearchFocus((n) => n + 1);
      } else if (key === 'b' && !event.shiftKey) {
        event.preventDefault();
        setLayout((before) => { const next = { ...before, sideOpen: !before.sideOpen }; remember(LAYOUT_KEY, next); return next; });
      } else if (key === 'j' && !event.shiftKey) {
        event.preventDefault();
        setLayout((before) => { const next = { ...before, bottomOpen: !before.bottomOpen }; remember(LAYOUT_KEY, next); return next; });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [settle]);

  const loaded = active ? contents[active] : undefined;
  const base = active ? bases[active] : undefined;
  const since = tree?.since ?? null;
  const diff = useMemo(
    () => (compare && base && 'text' in base ? { base: base.text, since: base.since ?? since ?? 'the last accepted sprint' } : null),
    [compare, base, since],
  );
  const changedNow = !!active && (tree?.changed ?? []).includes(active);
  const status = describeStatus(run?.status);
  const stage = run ? describeStage(run.current_stage).title : '';
  const names = useMemo(() => {
    const count = new Map<string, number>();
    for (const tab of open.tabs) count.set(nameOf(tab.path), (count.get(nameOf(tab.path)) ?? 0) + 1);
    return count;
  }, [open.tabs]);
  const lines = loaded && 'text' in loaded ? loaded.text.split('\n').length : null;
  const showChanges = activity === 'changes' && layout.sideOpen;

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas text-text-primary">
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Workspace views" className="flex w-12 shrink-0 flex-col items-center gap-1 border-r border-border bg-surface py-2">
          <ActivityButton label="Files" on={layout.sideOpen && activity === 'files'} onClick={() => chooseActivity('files')}><Files size={19} /></ActivityButton>
          <ActivityButton label="Search the files" on={layout.sideOpen && activity === 'search'} onClick={() => { chooseActivity('search'); setSearchFocus((n) => n + 1); }}><Search size={19} /></ActivityButton>
          <ActivityButton label="Changes, stage by stage" on={showChanges} onClick={() => chooseActivity('changes')}><GitCommitHorizontal size={19} /></ActivityButton>
          <ActivityButton label="Preview beside the code" on={layout.previewOpen} onClick={() => settle({ previewOpen: !layout.previewOpen })}><AppWindow size={19} /></ActivityButton>
          <span className="flex-1" />
          <ActivityButton label={layout.bottomOpen ? 'Hide the activity panel' : 'Show the activity panel'} on={layout.bottomOpen} onClick={() => settle({ bottomOpen: !layout.bottomOpen })}>
            {layout.bottomOpen ? <PanelBottomClose size={18} /> : <PanelBottomOpen size={18} />}
          </ActivityButton>
        </nav>

        {layout.sideOpen && !showChanges && (
          <>
            <aside aria-label={activity === 'search' ? 'Search' : 'Files'} style={{ width: layout.side }} className="flex min-h-0 shrink-0 flex-col bg-surface">
              <p className="flex h-9 shrink-0 items-center justify-between px-3 text-[12px] font-semibold text-text-secondary">
                {activity === 'search' ? 'Search' : 'Files'}
                {activity === 'files' && tree && <span className="font-normal tabular-nums text-text-muted">{tree.files.length.toLocaleString()}</span>}
              </p>
              {activity === 'files' && (
                <nav aria-label="The workspace's files" className="min-h-0 flex-1 overflow-y-auto pb-2">
                  {treeProblem && !tree && <p className="p-3 text-sm text-text-muted">{treeProblem}</p>}
                  <FileTree tree={tree} selected={active} onSelect={(path) => show(path)} onPin={(path) => show(path, true)} />
                </nav>
              )}
              {activity === 'search' && <SearchPanel runId={runId} focusKey={searchFocus} onOpen={(path, line) => show(path, false, line)} />}
            </aside>
            <Splitter label="Resize the side panel" axis="x" from="before" size={layout.side} min={180} max={640}
              onSize={(side) => setLayout((before) => ({ ...before, side }))} onSettle={(side) => settle({ side })} />
          </>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1">
            <main className="flex min-w-0 flex-1 flex-col bg-code">
              {showChanges ? (
                <div className="min-h-0 flex-1 bg-surface">
                  <ChangesPanel runId={runId} refreshKey={refreshKey} selected={changeShown} onSelect={setChangeShown} />
                </div>
              ) : (
                <>
                  <div role="tablist" aria-label="Open files" className="flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-border bg-surface">
                    {open.tabs.map((tab) => {
                      const on = tab.path === active;
                      const folder = tab.path.includes('/') ? tab.path.slice(0, tab.path.lastIndexOf('/')) : '';
                      return (
                        <div key={tab.path} className={cx(
                          'group flex shrink-0 items-center border-r border-border',
                          on ? 'bg-code shadow-[inset_0_2px_0_var(--accent)]' : 'hover:bg-overlay',
                        )}>
                          <button type="button" role="tab" aria-selected={on}
                            title={tab.kept ? tab.path : `${tab.path} (preview: open it twice to keep it)`}
                            onClick={() => setOpen((state) => ({ ...state, active: tab.path }))}
                            onDoubleClick={() => setOpen((state) => keepFile(state, tab.path))}
                            onAuxClick={(event) => { if (event.button === 1) setOpen((state) => closeFile(state, tab.path)); }}
                            className={cx('flex h-full items-center gap-1.5 pl-3 pr-1 font-mono text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--ring)]',
                              on ? 'text-text-primary' : 'text-text-secondary', !tab.kept && 'italic')}>
                            {nameOf(tab.path)}
                            {(names.get(nameOf(tab.path)) ?? 0) > 1 && folder && <span className="not-italic text-text-muted">{folder}</span>}
                          </button>
                          <button type="button" aria-label={`Close ${tab.path}`} title="Close"
                            onClick={() => setOpen((state) => closeFile(state, tab.path))}
                            className={cx('mr-1 inline-flex h-5 w-5 items-center justify-center rounded text-text-muted hover:bg-overlay-strong hover:text-text-primary focus-visible:opacity-100',
                              on ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')}>
                            <X size={12} aria-hidden="true" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  {active && (
                    <div className="flex h-8 shrink-0 items-center gap-3 border-b border-border/60 px-3 text-[12px]">
                      <span className="min-w-0 truncate font-mono text-text-secondary" title={active}>
                        {active.split('/').map((part, index, all) => (
                          <React.Fragment key={index}>
                            {index > 0 && <span aria-hidden="true" className="px-1 text-text-muted">›</span>}
                            <span className={index === all.length - 1 ? 'text-text-primary' : ''}>{part}</span>
                          </React.Fragment>
                        ))}
                      </span>
                      {since && (
                        <label className="ml-auto flex shrink-0 items-center gap-1.5 text-text-secondary">
                          <input type="checkbox" role="switch" checked={compare} onChange={(event) => setCompare(event.target.checked)} />
                          Compare with {since}{changedNow ? '' : ' (unchanged)'}
                        </label>
                      )}
                    </div>
                  )}
                  <div className="min-h-0 flex-1">
                    {!active && (
                      <div className="grid h-full place-items-center p-6 text-center">
                        <div className="max-w-sm space-y-2 text-sm text-text-muted">
                          <p className="text-text-secondary">Choose a file to read it, or press <kbd className="rounded border border-border px-1 font-mono text-xs">Ctrl P</kbd> to go to one by name.</p>
                          <p>The run writes these files; nothing here can be edited.</p>
                        </div>
                      </div>
                    )}
                    {active && !loaded && <p role="status" className="p-4 text-sm text-text-muted">Loading…</p>}
                    {active && loaded && 'problem' in loaded && <p className="p-4 text-sm text-text-muted">{loaded.problem}</p>}
                    {active && loaded && 'text' in loaded && compare && base && 'problem' in base && <p className="p-4 text-sm text-text-muted">{base.problem}</p>}
                    {active && loaded && 'text' in loaded && compare && !base && <p role="status" className="p-4 text-sm text-text-muted">Loading…</p>}
                    {active && loaded && 'text' in loaded && (!compare || diff) && (
                      <Editor path={active} text={loaded.text} diff={diff} line={reveal?.path === active ? reveal.line : undefined} />
                    )}
                  </div>
                </>
              )}
            </main>
            {layout.previewOpen && (
              <>
                <Splitter label="Resize the preview" axis="x" from="after" size={layout.preview} min={320} max={1600}
                  onSize={(preview) => setLayout((before) => ({ ...before, preview }))} onSettle={(preview) => settle({ preview })} />
                <div style={{ width: layout.preview }} className="flex min-h-0 shrink-0 flex-col bg-surface">
                  <PreviewPanel runId={runId} runStatus={run?.status} />
                </div>
              </>
            )}
          </div>
          {layout.bottomOpen && (
            <>
              <Splitter label="Resize the activity panel" axis="y" from="after" size={layout.bottom} min={120} max={720}
                onSize={(bottom) => setLayout((before) => ({ ...before, bottom }))} onSettle={(bottom) => settle({ bottom })} />
              <section aria-label="The run's activity" style={{ height: layout.bottom }} className="flex min-h-0 shrink-0 flex-col bg-surface">
                <div role="tablist" aria-label="Activity panel" className="flex h-8 shrink-0 items-stretch gap-1 border-b border-border px-2 text-[12px]">
                  {(['activity', 'log'] as const).map((tab) => (
                    <button key={tab} type="button" role="tab" aria-selected={bottomTab === tab} onClick={() => setBottomTab(tab)}
                      className={cx('-mb-px border-b-2 px-2', bottomTab === tab ? 'border-primary text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary')}>
                      {tab === 'activity' ? 'Activity' : `Log ${logs.length ? logs.length.toLocaleString() : ''}`}
                    </button>
                  ))}
                </div>
                <div className="min-h-0 flex-1">
                  {bottomTab === 'activity'
                    ? <AgentActivity logs={logs} isRunning={!!run && !['completed', 'failed', 'cancelled'].includes(run.status)} bare onOpenFile={(path) => { show(path, true); setCompare(true); }} />
                    : <LogViewer logs={logs} />}
                </div>
              </section>
            </>
          )}
        </div>
      </div>

      <div aria-label="Status" className="flex h-7 shrink-0 items-center gap-0 border-t border-border text-[12px]">
        <span className={cx('flex h-full items-center gap-2 px-3 font-medium', TONE[status.tone])}>
          {status.tone === 'active' && <span aria-hidden="true" className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />}
          {run ? status.label : 'Reading the run…'}
        </span>
        {run && stage && <span className="truncate px-3 text-text-secondary" title="The stage working now">{stage}</span>}
        <span className="ml-auto flex h-full items-center gap-3 px-3 text-text-muted">
          {active && lines !== null && <span className="font-mono tabular-nums">{lines.toLocaleString()} lines</span>}
          {since && <span>Changes since {since}</span>}
          <span className="inline-flex items-center gap-1" title="The run writes these files; nothing here edits them">Read-only</span>
          <button type="button" onClick={() => setGoTo(true)} className="hover:text-text-primary">Go to a file <span className="font-mono">Ctrl P</span></button>
        </span>
      </div>

      <GoToFile open={goTo} onClose={() => setGoTo(false)} paths={paths} onOpen={(path) => show(path)} />
    </div>
  );
};
