import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { LogEntry } from '../types';
import {
  ArrowDown,
  BookOpen,
  Brain,
  Check,
  ChevronRight,
  FileText,
  Loader2,
  Search,
  Sparkles,
  Terminal,
  UserCheck,
} from 'lucide-react';
import {
  commandOutcome,
  describeAction,
  describeStage,
  laneOf,
  pathFromResult,
  readRangeFromResult,
  shortenPath,
  splitToolMessage,
  workspacePath,
} from '../lib/activity';
import { Markdown } from './Markdown';
import { useStreamedText } from '../hooks/useStreamedText';

interface AgentActivityProps {
  logs: LogEntry[];
  /** Whether the run is still going, so an unfinished action can show as live. */
  isRunning?: boolean;
  /** Inside another card (a tab of the run's work area): no card of its own. */
  bare?: boolean;
  /** A moment to show: the feed scrolls to its first entry from then (the timeline, plan BG.14). */
  focusAt?: string | null;
  /** Open a written file in the Workspace tab with its change (plan WS.2); without it the link is a plain address. */
  onOpenFile?: (path: string) => void;
}

/** The address that opens a file in the Workspace tab with its change, as the run page reads it. */
export const workspaceHref = (path: string): string =>
  `?view=workspace&file=${encodeURIComponent(path)}&diff=1`;

/** How many entries the feed shows at once, and adds each time earlier ones are asked for. */
const SHOWN_AT_ONCE = 300;

/**
 * `stage_change` and `log` are in the feed too: a stage that answers in
 * structured output alone - an intake, a technology consultation - sends no
 * message and no tool call, so without its start and its outcome the feed said
 * "Nothing to show yet" while the steps beside it were finishing.
 */
const ACTIVITY_TYPES = new Set(['agent_message', 'tool_call', 'tool_result', 'review_decision', 'approval_decision', 'stage_change', 'log']);

/**
 * A result the harness gave instead of what was asked - a read of something the
 * agent already has, a listing after reading is done (plan BG.8). Not a
 * failure of the work, and shown as what it is.
 */
const HELD_BACK = /is in the project memory at the start of this conversation|You have already read lines|same bytes|Refusing to read .{0,200}? again|reading is done for this stage|Not looking/;

const KIND_ICON = {
  write: FileText,
  read: BookOpen,
  search: Search,
  run: Terminal,
  think: Brain,
} as const;

interface Item {
  key: string;
  type: 'message' | 'action' | 'decision' | 'note';
  stage: string;
  at: string;
  text: string;
  /** For a message: the working-out behind the headline, if any. */
  reasoning?: string;
  detail?: string;
  target?: string;
  /** Which part of a file this touched: "lines 120-180 of 1,412". */
  range?: string;
  kind?: keyof typeof KIND_ICON;
  failed?: boolean;
  /** An action whose result has not arrived yet. */
  pending?: boolean;
  /** The harness answered with what the agent already had, instead of what it asked. */
  heldBack?: boolean;
  /** The call's id, which its result carries too (newer events). */
  callId?: string;
  /** A command's exit status, once its result says it. */
  exitCode?: number;
  /** Characters of a command's output the stream left out. */
  leftOut?: number;
  /** A written file, as the Workspace tab names it. */
  file?: string;
}

/** Consecutive items from the same workflow step, shown under one heading. */
interface Group {
  stage: string;
  items: Item[];
  from: string;
  to: string;
}

/**
 * Split a message into the part that is an update and the part that is working.
 *
 * Agents lead with a conclusion and then justify it: "All required changes have
 * been completed:" followed by a numbered list, or a sentence followed by a
 * verification table. The first paragraph is the progress update a reader
 * actually wants; everything after it is reasoning, and putting all of it on
 * screen is what turned this panel into a transcript.
 */
function splitMessage(raw: string): { headline: string; reasoning?: string } {
  const text = raw.trim();
  const brk = text.search(/\n\s*\n/);
  if (brk === -1) return { headline: text };
  return { headline: text.slice(0, brk).trim(), reasoning: text.slice(brk).trim() || undefined };
}

function buildItems(logs: LogEntry[]): Item[] {
  const items: Item[] = [];

  for (const entry of logs) {
    if (!ACTIVITY_TYPES.has(entry.event_type)) continue;
    const key = String(entry.event_id ?? entry.sequence);
    const stage = entry.stage || '';
    const at = entry.timestamp;

    if (entry.event_type === 'review_decision' || entry.event_type === 'approval_decision') {
      // The owner's own decisions, in their place in the feed.
      const action = String(entry.metadata?.action ?? '');
      const point = String(entry.metadata?.review_point ?? '');
      const verb = action === 'approve' ? 'approved' : action === 'changes' ? 'asked for changes to' : action === 'skip' ? 'skipped'
        : action === 'reject' ? 'rejected' : action;
      const what = point ? describeStage(point).title : 'the request';
      const comment = (entry.message || '').split(' — ').slice(1).join(' — ');
      items.push({ key, type: 'decision', stage, at, text: `You ${verb} ${what}`, detail: comment || undefined });
      continue;
    }

    if (entry.event_type === 'stage_change') {
      // A step starting, named as the steps list names it; its meaning beneath.
      const name = stage.replace(/^awaiting_approval:/, '');
      const meaning = (entry.message || '').trim();
      items.push({ key, type: 'note', stage, at, text: `Started: ${describeStage(name).title}`,
        detail: meaning && meaning !== name ? meaning : undefined });
      continue;
    }

    if (entry.event_type === 'log') {
      // What a step decided: its first line, the rest beneath.
      const [first, ...rest] = (entry.message || '').trim().split('\n');
      if (!first) continue;
      items.push({ key, type: 'note', stage, at, text: first, detail: rest.join('\n').trim() || undefined });
      continue;
    }

    if (entry.event_type === 'agent_message') {
      const raw = (entry.message || '').trim();
      if (!raw) continue;
      const { headline, reasoning } = splitMessage(raw);
      items.push({ key, type: 'message', stage, at, text: headline, reasoning });
      continue;
    }

    if (entry.event_type === 'tool_call') {
      const split = splitToolMessage(entry.message || '');
      const tool = (entry.metadata?.tool as string) || split.tool;
      const action = describeAction(tool, split.args);
      const callId = typeof entry.metadata?.call_id === 'string' ? entry.metadata.call_id : undefined;
      items.push({
        key, type: 'action', stage, at,
        text: action.summary, target: action.target, kind: action.kind,
        range: action.range, detail: split.args, pending: true, callId,
      });
      continue;
    }

    // A result belongs to its call: the one with the same id when the event
    // carries it (side-by-side workers interleave), else the action just above
    // it. Attaching it there keeps the feed one line per action; only a failure
    // changes what is displayed, because a successful result adds nothing a
    // reader needs - except a command's exit status, and its output folded.
    const resultCall = typeof entry.metadata?.call_id === 'string' ? entry.metadata.call_id : undefined;
    let previous: Item | undefined = items[items.length - 1];
    if (resultCall) {
      for (let index = items.length - 1; index >= 0; index -= 1) {
        if (items[index].callId === resultCall) {
          previous = items[index];
          break;
        }
      }
    }
    const heldBack = HELD_BACK.test(entry.message || '');
    const failed = !heldBack && (entry.metadata?.failed === true || /^Failed:/i.test(entry.message || ''));
    if (previous && previous.type === 'action') {
      previous.detail = entry.message;
      previous.pending = false;
      previous.heldBack = heldBack;
      if (previous.kind === 'run' && !failed && !heldBack) {
        const outcome = commandOutcome(entry.message || '', entry.metadata);
        previous.exitCode = outcome.exitCode;
        previous.leftOut = outcome.leftOut;
        previous.detail = outcome.output;
      }
      // Fill in a filename the call itself could not supply, so a write stops
      // being narrated as "Saved a document".
      if (!failed && !previous.target && previous.kind === 'write') {
        const path = pathFromResult(entry.message || '');
        if (path) {
          previous.target = path;
          previous.text = `Saved ${path.split('/').pop()}`;
        }
      }
      // The result knows what was actually returned, including how long the
      // file is; the call only knew what was asked for. A read that ran past
      // the end of the file reports the truth here and nowhere else.
      if (!failed && previous.kind === 'read') {
        const range = readRangeFromResult(entry.message || '');
        if (range) {
          previous.range = range;
          previous.text = previous.text.replace(/^Reading part of/, 'Read part of');
        }
      }
      if (failed) {
        previous.failed = true;
        previous.text = `${previous.text} — didn't work`;
      } else if (previous.kind === 'write') {
        previous.file = workspacePath(previous.target);
      }
    } else if (failed) {
      items.push({
        key, type: 'action', stage, at, text: "Something didn't work",
        kind: 'think', failed: true, detail: entry.message,
      });
    }
  }

  return items;
}

/** Break the flat stream into the workflow steps that produced it. */
function groupByStage(items: Item[]): Group[] {
  const groups: Group[] = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last && last.stage === item.stage) {
      last.items.push(item);
      last.to = item.at;
    } else {
      groups.push({ stage: item.stage, items: [item], from: item.at, to: item.at });
    }
  }
  return groups;
}

const formatSpan = (from: string, to: string): string | null => {
  const seconds = Math.round((new Date(to).getTime() - new Date(from).getTime()) / 1000);
  if (!Number.isFinite(seconds) || seconds < 1) return null;
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60 ? `${minutes}m ${seconds % 60}s` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};

/**
 * A progress update from the model, with its working-out folded away.
 *
 * The headline renders as Markdown because agents write Markdown: without a
 * renderer their `**emphasis**` and `` `paths` `` appear as literal punctuation
 * and their tables as columns of pipe characters.
 */
const MessageRow: React.FC<{
  item: Item;
  stream: boolean;
  onGrow?: () => void;
  onStreamed?: () => void;
}> = ({ item, stream, onGrow, onStreamed }) => {
  const [open, setOpen] = useState(false);
  const { visible, streaming } = useStreamedText(item.text, stream, onGrow, onStreamed);

  return (
    <div className="py-1.5 pl-2 pr-1">
      {/* The caret is appended to the Markdown source rather than rendered
          beside it. Markdown emits block elements, so a sibling element would
          drop to its own line instead of sitting at the end of the sentence -
          which is the one position that reads as a cursor. */}
      <Markdown>{streaming ? `${visible}\u258d` : visible}</Markdown>

      {item.reasoning && !streaming && (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text-secondary transition-colors"
            aria-expanded={open}
          >
            <ChevronRight className={`h-3 w-3 transition-transform ${open ? 'rotate-90' : ''}`} />
            {open ? 'Hide reasoning' : 'Show reasoning'}
          </button>

          {open && (
            // Recessed and rule-marked, so it reads as the model's working
            // rather than as another progress update. Height-capped with its own
            // scroll: one expanded verification matrix is long enough to fill the
            // whole panel and bury the updates on either side of it.
            <div tabIndex={0} className="mt-1.5 max-h-80 overflow-y-auto border-l-2 border-border/60 pl-3">
              <Markdown>{item.reasoning}</Markdown>
            </div>
          )}
        </>
      )}
    </div>
  );
};

/**
 * A command: its command line and exit status on one line, its output folded
 * (plan WS.2). The output is what reached the page; when the stream clipped it,
 * the fold says so and where the whole of it is.
 */
const CommandRow: React.FC<{ item: Item; live: boolean }> = ({ item, live }) => {
  const [open, setOpen] = useState(false);
  const running = live && item.pending;
  const settled = !item.pending && !item.failed && !item.heldBack;
  const exit = item.exitCode;
  const line = item.target || item.text;

  return (
    <div className="group" data-testid="command">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`${line}${exit === undefined ? '' : `, exit ${exit}`}: ${open ? 'hide' : 'show'} its output`}
        className={`w-full flex items-center gap-2 rounded-lg py-1.5 pl-2 pr-1 text-left transition-colors ${
          item.failed || (exit !== undefined && exit !== 0) ? 'hover:bg-danger-bg' : 'hover:bg-overlay'
        }`}
      >
        <span className="flex-none grid place-items-center h-4 w-4">
          {running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          ) : item.failed || (exit !== undefined && exit !== 0) ? (
            <span className="h-1.5 w-1.5 rounded-full bg-danger" />
          ) : item.heldBack ? (
            <span className="h-1.5 w-1.5 rounded-full bg-text-muted" />
          ) : (
            <Check className="h-3.5 w-3.5 text-success/70" />
          )}
        </span>
        <Terminal className="h-3.5 w-3.5 flex-none text-text-muted" aria-hidden="true" />
        <code className={`min-w-0 flex-1 truncate font-mono text-[12px] ${item.failed ? 'text-danger' : 'text-text-secondary'}`} title={line}>
          {line}
        </code>
        {settled && exit !== undefined && (
          <span
            data-testid="exit-status"
            className={`flex-none rounded px-1.5 py-px text-xs font-medium tabular-nums ${
              exit === 0 ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
            }`}
          >
            exit {exit}
          </span>
        )}
        {item.heldBack && (
          <span className="flex-none rounded bg-overlay px-1.5 py-px text-xs font-medium text-text-muted">held back</span>
        )}
        <ChevronRight className={`h-3.5 w-3.5 flex-none text-text-muted transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden="true" />
      </button>

      {open && (
        <div className="mb-2 ml-8 mr-1 mt-1">
          <pre tabIndex={0} aria-label={`The output of ${line}`} className="max-h-72 overflow-auto rounded-lg bg-inset p-3 font-mono text-xs leading-relaxed text-text-secondary whitespace-pre-wrap break-all">
            {item.pending ? 'Still running.' : item.detail?.trim() || '(no output)'}
          </pre>
          {!!item.leftOut && (
            <p className="mt-1 text-xs text-text-muted">
              Clipped: the page is sent the first 2,000 characters; {item.leftOut.toLocaleString()} more are in the run&apos;s transcript.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

/** One action: a sentence, its state, and the raw payload behind a disclosure. */
const ActionRow: React.FC<{ item: Item; live: boolean; onOpenFile?: (path: string) => void }> = ({ item, live, onOpenFile }) => {
  const [open, setOpen] = useState(false);
  const Icon = KIND_ICON[item.kind ?? 'think'];
  const running = live && item.pending;

  if (item.kind === 'run') return <CommandRow item={item} live={live} />;

  return (
    <div className="group">
      <button
        type="button"
        onClick={() => item.detail && setOpen((v) => !v)}
        aria-expanded={item.detail ? open : undefined}
        className={`w-full flex items-start gap-2 rounded-lg py-1.5 pl-2 pr-1 text-left transition-colors ${
          item.failed ? 'hover:bg-danger-bg' : 'hover:bg-overlay'
        }`}
      >
        {/* State first, then kind. Whether it finished is the more urgent fact. */}
        <span className="mt-0.5 flex-none grid place-items-center h-4 w-4">
          {running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          ) : item.failed ? (
            <span className="h-1.5 w-1.5 rounded-full bg-danger" />
          ) : item.heldBack ? (
            <span className="h-1.5 w-1.5 rounded-full bg-text-muted" />
          ) : (
            <Check className="h-3.5 w-3.5 text-success/70" />
          )}
        </span>

        <Icon className={`mt-0.5 h-3.5 w-3.5 flex-none ${item.failed ? 'text-danger' : 'text-text-muted'}`} />

        <span className="min-w-0 flex-1">
          <span className={`block text-[13px] leading-snug ${item.failed ? 'text-danger' : 'text-text-secondary'}`}>
            {item.text}
          </span>
          {item.heldBack && (
            <span className="mt-0.5 inline-block rounded bg-overlay px-1.5 py-px text-xs font-medium text-text-muted">
              held back: already read
            </span>
          )}
          {((item.target && !item.file) || item.range) && (
            <span className="mt-0.5 flex items-center gap-1.5 min-w-0">
              {item.target && !item.file && (
                <span className="text-xs text-text-muted font-mono truncate" title={item.target}>
                  {shortenPath(item.target)}
                </span>
              )}
              {/* Which part of the file, kept as its own chip so it survives the
                  truncation that a long path would otherwise impose on it. */}
              {item.range && (
                <span className="flex-none rounded bg-overlay px-1.5 py-px text-xs font-medium tabular-nums text-text-secondary">
                  {item.range}
                </span>
              )}
            </span>
          )}
        </span>

        {item.detail && (
          <ChevronRight
            className={`mt-0.5 h-3.5 w-3.5 flex-none text-text-muted transition-transform ${open ? 'rotate-90' : ''} opacity-0 group-hover:opacity-100 group-focus-within:opacity-100`}
          />
        )}
      </button>

      {/* A written file opens in the Workspace tab with its change (plan WS.2).
          A link beside the row, not inside its button: a link in a button is
          neither, to a keyboard or a screen reader. */}
      {item.file && (
        <a
          href={workspaceHref(item.file)}
          onClick={(event) => {
            if (!onOpenFile || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
            event.preventDefault();
            onOpenFile(item.file!);
          }}
          title={`Open ${item.file} in the Workspace tab with its change`}
          className="-mt-1 mb-0.5 ml-[3.4rem] mr-1 block truncate font-mono text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] rounded"
        >
          {shortenPath(item.file)}
        </a>
      )}

      {open && item.detail && (
        <pre tabIndex={0} className="mb-2 ml-8 mr-1 mt-1 max-h-56 overflow-auto rounded-lg bg-inset p-3 text-xs leading-relaxed text-text-secondary whitespace-pre-wrap break-all">
          {item.detail}
        </pre>
      )}
    </div>
  );
};

/** A step starting, or what it decided: quieter than a message, so the work stays the headline. */
const NoteRow: React.FC<{ item: Item }> = ({ item }) => (
  <div className="my-0.5 flex items-start gap-2 py-1 pl-2 pr-2" data-testid="activity-note">
    <Sparkles className="mt-0.5 h-3.5 w-3.5 flex-none text-text-muted" aria-hidden="true" />
    <span className="min-w-0 text-[13px] leading-snug text-text-secondary">
      {item.text}
      {item.detail && <span className="block text-[12px] text-text-muted">{item.detail}</span>}
    </span>
  </div>
);

/** One of the owner's decisions - an approval, a review answered - in its place in the feed. */
const DecisionRow: React.FC<{ item: Item }> = ({ item }) => (
  <div className="my-1 flex items-start gap-2 rounded-lg border border-primary/30 bg-accent-soft py-1.5 pl-2 pr-2">
    <UserCheck className="mt-0.5 h-3.5 w-3.5 flex-none text-primary" aria-hidden="true" />
    <span className="min-w-0 text-[13px] leading-snug text-text-primary">
      {item.text}
      {item.detail && <span className="block text-[12px] text-text-secondary">“{item.detail}”</span>}
    </span>
  </div>
);

/**
 * A running narration of what the workflow is doing, newest at the bottom.
 *
 * Grouped by workflow step rather than shown as one flat stream: after a couple
 * of hundred entries "Read the specification" means nothing without knowing
 * which step was reading it, and the heading is the only thing that says so.
 * Each action carries its own state, so an unfinished one reads as in progress
 * instead of looking identical to a finished one.
 */
export const AgentActivity: React.FC<AgentActivityProps> = ({ logs, isRunning = false, bare = false, focusAt = null, onOpenFile }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const all = useMemo(() => buildItems(logs), [logs]);
  // Lanes, when the feed has more than one (plan BG.8): the roles working side
  // by side in parallel mode, or planning, testing and fixes in order.
  const lanes = useMemo(() => [...new Set(all.map((item) => laneOf(item.stage)))], [all]);
  const [lane, setLane] = useState<string | null>(null);
  const items = useMemo(() => (lane ? all.filter((item) => laneOf(item.stage) === lane) : all), [all, lane]);
  // The newest entries only, and earlier ones on request (plan UI-S4): 876
  // entries were 10,361 elements, nine in ten of the page, rebuilt each time
  // the tab was opened; a run's 5,000-event cap would be six times that.
  const [shownCount, setShownCount] = useState(SHOWN_AT_ONCE);
  const hidden = Math.max(0, items.length - shownCount);
  const shown = useMemo(() => items.slice(hidden), [items, hidden]);
  const groups = useMemo(() => groupByStage(shown), [shown]);
  // What a screen reader hears: the newest progress update, not every action.
  const headline = useMemo(() => [...all].reverse().find((item) => item.type === 'message')?.text ?? '', [all]);

  // How many arrived while the reader was scrolled away, so the catch-up
  // control can say what it is offering instead of just "go to the end".
  //
  // The baseline is recorded only from the scroll handler. Deriving it during
  // render meant writing to a ref mid-render, which React is explicitly not safe
  // under: a double render in StrictMode would reset the count being shown.
  const [seenCount, setSeenCount] = useState(0);
  const countRef = useRef(items.length);
  useEffect(() => {
    countRef.current = items.length;
  }, [items.length]);

  const missed = Math.max(0, items.length - seenCount);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    // A small tolerance, because sub-pixel scroll heights never land exactly.
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    setPinned(atBottom);
    // Programmatic scrolling fires this too, so while the feed is following
    // along the baseline stays current and `missed` stays at zero.
    if (atBottom) setSeenCount(countRef.current);
  }, []);

  // Layout effect, so the jump happens in the same frame the item is painted and
  // the reader never sees the feed sitting one entry short.
  useLayoutEffect(() => {
    if (!pinned) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items.length, pinned]);

  const scrollToEnd = () => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    setPinned(true);
  };

  // Called on every frame of a text reveal. It moves the scroller directly
  // rather than raising state, because the alternative is re-rendering a feed of
  // several hundred rows sixty times a second to animate one of them.
  const pinnedRef = useRef(pinned);
  useEffect(() => {
    pinnedRef.current = pinned;
  }, [pinned]);
  const followText = useCallback(() => {
    const el = scrollRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }, []);

  // Which message, if any, should be revealed rather than appear whole.
  //
  // Only the newest, only while the run is going, and only once: a finished run
  // being opened has nothing live about it, and a message already revealed must
  // not replay every time polling returns a new array. The set is the memory of
  // what has been shown, and it survives re-renders because the items do not.
  const [streamedKeys, setStreamedKeys] = useState<ReadonlySet<string>>(() => new Set());
  const newestMessageKey = useMemo(() => {
    for (let index = items.length - 1; index >= 0; index -= 1) {
      if (items[index].type === 'message') return items[index].key;
    }
    return undefined;
  }, [items]);
  const streamingKey =
    isRunning && newestMessageKey && !streamedKeys.has(newestMessageKey)
      ? newestMessageKey
      : undefined;
  // Recorded when the reveal ends, not when it starts. Marking it up front made
  // the next render withdraw the `stream` prop, and the hook, told it was no
  // longer animating, jumped straight to the full text - so the animation was
  // cancelled on the frame after it began.
  //
  // Returning the existing set unchanged when the key is already in it is what
  // stops this looping: a fresh `Set` every time would be a new reference, a new
  // render, and another completion callback behind it.
  const markStreamed = useCallback(() => {
    if (!streamingKey) return;
    setStreamedKeys((previous) =>
      previous.has(streamingKey) ? previous : new Set(previous).add(streamingKey),
    );
  }, [streamingKey]);

  // Steps folded to one line each (plan WS.2): the newest step - the one
  // working now, or where a finished run ended - stays open, and a step the
  // reader opens or folds stays as they left it.
  const [folding, setFolding] = useState<ReadonlyMap<string, boolean>>(() => new Map());
  // The entry a moment from the timeline lands on: its step is opened.
  const focusKey = useMemo(() => {
    if (!focusAt) return undefined;
    const from = Date.parse(focusAt);
    return items.find((item) => Date.parse(item.at) >= from)?.key;
  }, [items, focusAt]);

  // A moment older than the entries shown: show back to it first.
  const [reach, setReach] = useState<string | null>(null);
  if (focusAt !== reach) {
    setReach(focusAt);
    if (focusAt) setFolding(new Map());
    if (focusAt) {
      const index = items.findIndex((item) => Date.parse(item.at) >= Date.parse(focusAt));
      if (index >= 0 && index < hidden) setShownCount(items.length - index + 20);
    }
  }

  // Taken to a moment from the timeline: the first entry from then, centred.
  useEffect(() => {
    if (!focusAt || !scrollRef.current) return;
    const from = Date.parse(focusAt);
    const target = [...scrollRef.current.querySelectorAll<HTMLElement>('[data-at]')]
      .find((element) => Date.parse(element.dataset.at ?? '') >= from);
    target?.scrollIntoView?.({ block: 'center' });
  }, [focusAt, shownCount]);

  const live = items.length > 0;
  // Only the newest action can still be in flight; anything earlier was settled
  // by whatever came after it, whether or not its own result was recorded.
  const lastKey = items[items.length - 1]?.key;
  const working = isRunning && items[items.length - 1]?.pending === true;

  return (
    <div className={`${bare ? '' : 'glass-card rounded-2xl '}flex flex-col h-full overflow-hidden`}>
      <div className="flex-none px-4 py-3 border-b border-border/40 flex items-center gap-2.5">
        <span className="grid place-items-center h-7 w-7 rounded-lg bg-accent-soft">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
        </span>
        <div className="min-w-0">
          <h2 className="font-semibold text-text-primary text-sm leading-none">Live progress</h2>
          <p className="text-xs text-text-muted mt-1 leading-none">What the workflow is doing right now</p>
        </div>
        {live && <span className="ml-auto text-xs text-text-muted tabular-nums">{items.length}</span>}
      </div>
      {lanes.length > 1 && (
        <div role="group" aria-label="Show one lane" className="flex-none flex flex-wrap gap-1.5 px-4 py-2 border-b border-border/40">
          {[null, ...lanes].map((name) => (
            <button
              key={name ?? 'all'}
              type="button"
              aria-pressed={lane === name}
              onClick={() => setLane(name)}
              className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${
                lane === name ? 'border-primary/50 bg-accent-soft text-primary' : 'border-border text-text-secondary hover:bg-overlay'
              }`}
            >
              {name ?? 'All'}
            </button>
          ))}
        </div>
      )}

      <p role="status" aria-live="polite" className="sr-only">{headline}</p>
      <div className="flex-1 min-h-0 flex flex-col">
        {/* The scroller is absolutely positioned inside a relative box rather
            than being a flex child. As a flex child its height resolved against
            its own content, so `scrollHeight` equalled `clientHeight`, the
            scroll-to-bottom effect had nowhere to move, and the feed sat frozen
            on its oldest entry. */}
        <div className="relative flex-1 min-h-0">
          <div
            ref={scrollRef}
            onScroll={onScroll}
            role="log"
            // Off: every action read aloud as it lands drowned the reader. The
            // newest headline is announced by the status line below instead.
            aria-live="off"
            aria-label="Agent activity"
            tabIndex={0}
            // No padding above: a step's heading sticks to the scroller's top
            // edge, and with padding there the entries scrolled visibly through
            // the strip between the heading and the toolbar above it.
            className="absolute inset-0 overflow-y-auto px-2 pb-3 flex flex-col"
          >
            {!live ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 px-6 text-center">
                <span className="grid place-items-center h-10 w-10 rounded-xl bg-overlay">
                  <Sparkles className="h-4 w-4 text-text-muted" />
                </span>
                <p className="text-sm text-text-secondary">Nothing to show yet</p>
                <p className="text-xs text-text-muted leading-relaxed">
                  Once the run starts, each step it takes will appear here as it happens.
                </p>
              </div>
            ) : (
              // `mt-auto` is what makes this read as a chat rather than a list:
              // the first entries sit at the bottom and are pushed upward as more
              // arrive. Preferred over `justify-end` on the scroller, which leaves
              // the earliest entries unreachable in several browsers.
              <div className="mt-auto">
                {hidden > 0 && (
                  <button
                    type="button"
                    onClick={() => setShownCount((count) => count + SHOWN_AT_ONCE)}
                    className="mb-2 w-full rounded-lg border border-border/60 py-1.5 text-xs font-medium text-text-secondary hover:bg-overlay hover:text-text-primary"
                  >
                    Show {Math.min(SHOWN_AT_ONCE, hidden)} earlier ({hidden} not shown)
                  </button>
                )}
                {groups.map((group, index) => {
                  const span = formatSpan(group.from, group.to);
                  const id = `${group.stage}:${group.items[0].key}`;
                  const newest = index === groups.length - 1;
                  const open = folding.get(id) ?? (newest || (!!focusKey && group.items.some((item) => item.key === focusKey)));
                  const title = describeStage(group.stage).title;
                  const count = group.items.length;
                  return (
                    <section key={id} className="mb-1" data-testid="activity-step">
                      {/* Sticky, so the step you are reading stays named however
                          far down its actions run. */}
                      {/* Fully opaque. At 95% the entries scrolling underneath
                          showed through as a smear of half-legible text along
                          the top edge of the panel. */}
                      <header className="sticky top-0 z-10 -mx-2 border-b border-border/40 bg-surface-raised">
                        <h3 className="m-0">
                          <button
                            type="button"
                            aria-expanded={open}
                            onClick={() => setFolding((was) => new Map(was).set(id, !open))}
                            className="flex w-full items-baseline gap-2 px-4 py-1.5 text-left hover:bg-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                          >
                            <ChevronRight className={`h-3 w-3 flex-none self-center text-text-muted transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden="true" />
                            <span className="min-w-0 truncate text-xs font-semibold uppercase tracking-wider text-text-secondary">{title}</span>
                            {newest && isRunning && <span className="flex-none text-xs font-medium text-primary">working now</span>}
                            <span className="ml-auto flex-none text-xs text-text-muted tabular-nums">
                              {count} {count === 1 ? 'entry' : 'entries'}{span ? ` · ${span}` : ''}
                            </span>
                          </button>
                        </h3>
                      </header>

                      {open && <div className="space-y-0.5 pt-1">
                        {group.items.map((item) => (
                          <div key={item.key} data-at={item.at} className="animate-activity-in">
                            {item.type === 'decision' ? (
                              <DecisionRow item={item} />
                            ) : item.type === 'note' ? (
                              <NoteRow item={item} />
                            ) : item.type === 'message' ? (
                              <MessageRow
                                item={item}
                                stream={item.key === streamingKey}
                                onGrow={followText}
                                onStreamed={markStreamed}
                              />
                            ) : (
                              <ActionRow item={item} live={item.key === lastKey && isRunning} onOpenFile={onOpenFile} />
                            )}
                          </div>
                        ))}
                      </div>}
                    </section>
                  );
                })}

                {/* The model is between tool calls: there is nothing to show, and
                    showing nothing looks like the run has stalled. */}
                {working && (
                  <div className="flex items-center gap-2 py-2 pl-2 text-[12px] text-text-muted">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                    <span className="animate-pulse">Thinking…</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* A bar, not a floating pill. Floated over the feed it covered the very
            text the reader had scrolled up to read. */}
        {!pinned && live && (
          <div className="flex-none border-t border-border/40 bg-surface-raised/60 p-1.5">
            <button
              type="button"
              onClick={scrollToEnd}
              className="w-full flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-overlay transition-colors"
            >
              <ArrowDown className="h-3 w-3" />
              {missed > 0 ? `${missed} new ${missed === 1 ? 'update' : 'updates'}` : 'Jump to latest'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
