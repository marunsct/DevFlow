/**
 * The workspace window (plan UX.5-UX.8), laid out as a code editor is: an activity bar (files, search, changes, the
 * preview beside the code), a resizable side panel, the open files as tabs over a Monaco reader or a side-by-side
 * diff, a bottom panel with the run's activity and log, and a status line naming the run's state and the stage
 * working now. Read-only while the run writes these files; with co-development on (plans UX.12-UX.14, switch
 * CO_DEVELOPMENT) a person takes the turn on a stopped run and edits them: unsaved marks on the tabs, save with the
 * hash the file was loaded at, both versions side by side when the file moved on since, discard that asks first, and
 * a hand back with a reason the next stage reads.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AppWindow, Files, GitCommitHorizontal, PanelBottomClose, PanelBottomOpen, Search, X,
} from 'lucide-react';
import { getWorkspaceFile, getWorkspaceFileAccepted, saveWorkspaceFile } from '../../api';
import type { LogEntry, RunStatusResponse } from '../../types';
import { describeStage, describeStatus } from '../../lib/activity';
import { remember, remembered } from '../../lib/layoutMemory';
import { cx, useFeedback } from '../../ui';
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
import { refusalOf, useEditTurn } from './useEditTurn';

type Activity = 'files' | 'search' | 'changes';
interface Layout { side: number; preview: number; bottom: number; sideOpen: boolean; bottomOpen: boolean; previewOpen: boolean }
export const LAYOUT_KEY = 'workspaceLayout';
const LAYOUT: Layout = { side: 272, preview: 560, bottom: 220, sideOpen: true, bottomOpen: false, previewOpen: false };

type Loaded = { text: string; hash?: string } | { problem: string };
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

function without<T>(all: Record<string, T>, path: string): Record<string, T> {
  const rest = { ...all };
  delete rest[path];
  return rest;
}

export const WorkspaceShell: React.FC<{
  runId: string;
  run: RunStatusResponse | null;
  logs: LogEntry[];
  /** A file to open first, kept (from the address). */
  initialFile?: string | null;
  /** The file shown now, for the address. */
  onActiveFile?: (path: string | null) => void;
}> = ({ runId, run, logs, initialFile, onActiveFile }) => {
  const { notify, confirm } = useFeedback();
  const edit = useEditTurn(runId, run?.status, notify);
  const [edits, setEdits] = useState(0);
  const refreshKey = `${run?.current_stage ?? ''}:${run?.status ?? ''}:${edits}`;
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
  // The person's unsaved text per file, and a file's text on disk when a save found it had moved on (plan UX.14).
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [stale, setStale] = useState<Record<string, { text: string; hash: string }>>({});
  const [handingBack, setHandingBack] = useState(false);
  const [reason, setReason] = useState('');

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
      .then((data) => current && setContents((all) => ({ ...all, [active]: { text: data.content, hash: data.hash } })))
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

  const unsaved = Object.keys(drafts);
  const edited = useCallback((path: string, text: string) => {
    setDrafts((all) => {
      const now = contents[path];
      if (now && 'text' in now && text === now.text) {
        return without(all, path);
      }
      return { ...all, [path]: text };
    });
  }, [contents]);

  const settleSaved = useCallback((path: string, text: string, hash: string) => {
    setContents((all) => ({ ...all, [path]: { text, hash } }));
    setDrafts((all) => without(all, path));
    setStale((all) => without(all, path));
  }, []);

  // A file closed with unsaved changes is asked about first; closed, its changes are dropped.
  const closeTab = async (path: string) => {
    if (drafts[path] !== undefined) {
      const yes = await confirm({ title: `Close ${nameOf(path)} without saving?`, message: 'Your changes to it are dropped.', confirmLabel: 'Close', danger: true });
      if (!yes) return;
      setDrafts((all) => without(all, path));
      setStale((all) => without(all, path));
    }
    setOpen((state) => closeFile(state, path));
  };

  const save = useCallback(async (path: string, over?: string): Promise<void> => {
    const text = drafts[path];
    const now = contents[path];
    const hash = over ?? (now && 'hash' in now ? now.hash : undefined);
    if (text === undefined || !hash) return;
    const attempt = async (confirmBaseline: boolean): Promise<void> => {
      const answer = await saveWorkspaceFile(runId, path, text, hash, confirmBaseline);
      settleSaved(path, text, answer.hash);
      setEdits((n) => n + 1);
    };
    try {
      await attempt(false);
    } catch (error) {
      const refused = refusalOf(error);
      if (refused.status === 409 && refused.extra.needs_confirmation === 'baseline_test') {
        const yes = await confirm({
          title: 'Change a test of the product as it was seeded?',
          message: `${path} is held as the product's regression baseline. Changed, the baseline is taken again when you hand back.`,
          confirmLabel: 'Change it',
        });
        if (yes) await attempt(true).catch((again) => notify(refusalOf(again).message || `${path} was not saved.`));
      } else if (refused.status === 409 && typeof refused.extra.content === 'string') {
        const theirs = { text: refused.extra.content, hash: String(refused.extra.hash ?? '') };
        setStale((all) => ({ ...all, [path]: theirs }));
      } else {
        notify(refused.message || `${path} was not saved.`);
      }
    }
  }, [drafts, contents, runId, settleSaved, confirm, notify]);

  const takeTheirs = (path: string) => {
    const theirs = stale[path];
    if (theirs) settleSaved(path, theirs.text, theirs.hash);
  };

  const discard = async () => {
    const yes = await confirm({
      title: 'Discard your changes?',
      message: 'Every file you changed in this turn goes back to how it was before you changed it, and the turn ends.',
      confirmLabel: 'Discard',
      danger: true,
    });
    if (!yes) return;
    try {
      await edit.discard();
      setDrafts({});
      setStale({});
      setContents({});
      setEdits((n) => n + 1);
    } catch (error) {
      notify(refusalOf(error).message || 'The changes could not be discarded.');
    }
  };

  const handBack = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!reason.trim() || unsaved.length) return;
    try {
      const answer = await edit.handBack(reason.trim());
      setHandingBack(false);
      setReason('');
      setEdits((n) => n + 1);
      notify(answer.commit
        ? `Handed back: ${answer.files.length} file(s) in commit ${answer.commit.slice(0, 8)}. The checks run when the run goes on.`
        : (answer.message || 'Handed back.'), 'info');
      if (answer.rewind_offered) {
        notify(`You changed ${(answer.documents ?? []).join(', ')}, which earlier stages wrote. Rewind the run from the run page if the stages after them should start again.`, 'info');
      }
    } catch (error) {
      notify(refusalOf(error).message || 'The turn could not be handed back.');
    }
  };

  const saveShown = useRef<() => void>(() => undefined);
  useEffect(() => {
    saveShown.current = () => { if (active && edit.writable) void save(active); };
  }, [active, edit.writable, save]);

  // The keys an editor answers to: go to a file, search, the side and bottom panels, save.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === 's' && !event.shiftKey) {
        event.preventDefault();
        saveShown.current();
      } else if (key === 'p' && !event.shiftKey) {
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
  const movedOn = active ? stale[active] : undefined;
  const draft = active ? drafts[active] : undefined;
  const diff = useMemo(
    () => (movedOn ? { base: movedOn.text, since: 'the file as it is now' }
      : compare && base && 'text' in base ? { base: base.text, since: base.since ?? since ?? 'the last accepted sprint' } : null),
    [movedOn, compare, base, since],
  );
  const changedNow = !!active && (tree?.changed ?? []).includes(active);
  const status = describeStatus(run?.status);
  const stage = run ? describeStage(run.current_stage).title : '';
  const names = useMemo(() => {
    const count = new Map<string, number>();
    for (const tab of open.tabs) count.set(nameOf(tab.path), (count.get(nameOf(tab.path)) ?? 0) + 1);
    return count;
  }, [open.tabs]);
  const lines = draft !== undefined ? draft.split('\n').length : loaded && 'text' in loaded ? loaded.text.split('\n').length : null;
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
                            onAuxClick={(event) => { if (event.button === 1) void closeTab(tab.path); }}
                            className={cx('flex h-full items-center gap-1.5 pl-3 pr-1 font-mono text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--ring)]',
                              on ? 'text-text-primary' : 'text-text-secondary', !tab.kept && 'italic')}>
                            {nameOf(tab.path)}
                            {(names.get(nameOf(tab.path)) ?? 0) > 1 && folder && <span className="not-italic text-text-muted">{folder}</span>}
                            {drafts[tab.path] !== undefined && <span role="img" aria-label="unsaved changes" title="Unsaved changes" className="not-italic text-accent">●</span>}
                          </button>
                          <button type="button" aria-label={`Close ${tab.path}`} title="Close"
                            onClick={() => void closeTab(tab.path)}
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
                      {edit.writable && draft !== undefined && !movedOn && (
                        <button type="button" onClick={() => void save(active)}
                          className="ml-auto shrink-0 rounded px-2 py-0.5 font-medium text-accent hover:bg-overlay">
                          Save <span className="font-mono text-text-muted">Ctrl S</span>
                        </button>
                      )}
                      {since && (
                        <label className={cx('flex shrink-0 items-center gap-1.5 text-text-secondary', !(edit.writable && draft !== undefined && !movedOn) && 'ml-auto')}>
                          <input type="checkbox" role="switch" checked={compare} onChange={(event) => setCompare(event.target.checked)} />
                          Compare with {since}{changedNow ? '' : ' (unchanged)'}
                        </label>
                      )}
                    </div>
                  )}
                  {active && movedOn && (
                    <div role="alert" className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border bg-warning-bg px-3 py-1.5 text-[12px] text-warning">
                      <span className="mr-auto">{active} changed since you opened it. Left: the file as it is now; right: your text, kept.</span>
                      <button type="button" onClick={() => void save(active, movedOn.hash)} className="rounded border border-warning/40 px-2 py-0.5 font-medium hover:bg-overlay">Save mine over it</button>
                      <button type="button" onClick={() => takeTheirs(active)} className="rounded px-2 py-0.5 hover:bg-overlay">Take the file as it is now</button>
                    </div>
                  )}
                  <div className="min-h-0 flex-1">
                    {!active && (
                      <div className="grid h-full place-items-center p-6 text-center">
                        <div className="max-w-sm space-y-2 text-sm text-text-muted">
                          <p className="text-text-secondary">Choose a file to read it, or press <kbd className="rounded border border-border px-1 font-mono text-xs">Ctrl P</kbd> to go to one by name.</p>
                          <p>{edit.writable ? 'It is your turn: a file you open can be changed and saved.' : 'The run writes these files; nothing here can be edited now.'}</p>
                        </div>
                      </div>
                    )}
                    {active && !loaded && <p role="status" className="p-4 text-sm text-text-muted">Loading…</p>}
                    {active && loaded && 'problem' in loaded && <p className="p-4 text-sm text-text-muted">{loaded.problem}</p>}
                    {active && loaded && 'text' in loaded && compare && base && 'problem' in base && <p className="p-4 text-sm text-text-muted">{base.problem}</p>}
                    {active && loaded && 'text' in loaded && compare && !base && <p role="status" className="p-4 text-sm text-text-muted">Loading…</p>}
                    {active && loaded && 'text' in loaded && (!compare || diff) && (
                      <Editor path={active} text={draft ?? loaded.text} diff={diff} line={reveal?.path === active ? reveal.line : undefined}
                        editable={edit.writable && !diff} onEdit={(text) => edited(active, text)} />
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
          {edit.turn === 'off' && <span className="inline-flex items-center gap-1" title="The run writes these files; nothing here edits them">Read-only</span>}
          {(edit.turn === 'run' || edit.turn === 'free') && (
            <>
              <span>{edit.turn === 'run' ? "The run's turn" : 'Nobody holds the turn'}</span>
              <button type="button" onClick={() => void edit.take()} className="font-medium text-accent hover:text-text-primary"
                title={edit.turn === 'run' ? 'Pause the run at the end of its stage, then edit its files' : 'Edit the files of the stopped run'}>
                Take the turn
              </button>
            </>
          )}
          {edit.turn === 'pausing' && <span role="status">Pausing at the end of the stage…</span>}
          {edit.turn === 'theirs' && <span>{edit.session?.holder}'s turn{edit.session?.lapsed ? ' (not seen lately)' : ''}</span>}
          {edit.turn === 'yours' && (
            <>
              <span className="font-medium text-text-primary">Your turn{unsaved.length ? ` · ${unsaved.length} unsaved` : ''}</span>
              <button type="button" onClick={() => setHandingBack((open) => !open)} className="font-medium text-accent hover:text-text-primary">Hand back</button>
              <button type="button" onClick={() => void discard()} className="hover:text-danger">Discard my changes</button>
            </>
          )}
          <button type="button" onClick={() => setGoTo(true)} className="hover:text-text-primary">Go to a file <span className="font-mono">Ctrl P</span></button>
        </span>
      </div>

      {handingBack && edit.turn === 'yours' && (
        <form onSubmit={handBack} aria-label="Hand the turn back" className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border bg-surface px-3 py-2 text-[12px]">
          <label className="flex min-w-0 flex-1 items-center gap-2">
            <span className="shrink-0 text-text-secondary">Why you changed the files</span>
            <input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={200} required
              placeholder="One line; the next stage reads it"
              className="min-w-0 flex-1 rounded border border-border bg-canvas px-2 py-1 text-text-primary" />
          </label>
          {unsaved.length > 0 && <span className="text-warning">Save or close the unsaved files first.</span>}
          <button type="submit" disabled={!reason.trim() || unsaved.length > 0}
            className="rounded bg-primary px-3 py-1 font-semibold text-primary-foreground disabled:opacity-50">Hand back</button>
        </form>
      )}

      <GoToFile open={goTo} onClose={() => setGoTo(false)} paths={paths} onOpen={(path) => show(path)} />
    </div>
  );
};
