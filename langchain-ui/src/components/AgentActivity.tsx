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
} from 'lucide-react';
import {
  describeAction,
  describeStage,
  pathFromResult,
  readRangeFromResult,
  shortenPath,
  splitToolMessage,
} from '../lib/activity';
import { Markdown } from './Markdown';
import { useStreamedText } from '../hooks/useStreamedText';

interface AgentActivityProps {
  logs: LogEntry[];
  /** Whether the run is still going, so an unfinished action can show as live. */
  isRunning?: boolean;
}

const ACTIVITY_TYPES = new Set(['agent_message', 'tool_call', 'tool_result']);

const KIND_ICON = {
  write: FileText,
  read: BookOpen,
  search: Search,
  run: Terminal,
  think: Brain,
} as const;

interface Item {
  key: string;
  type: 'message' | 'action';
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
      items.push({
        key, type: 'action', stage, at,
        text: action.summary, target: action.target, kind: action.kind,
        range: action.range, detail: split.args, pending: true,
      });
      continue;
    }

    // A result belongs to the action just above it. Attaching it there keeps the
    // feed one line per action; only a failure changes what is displayed,
    // because a successful result adds nothing a reader needs.
    const previous = items[items.length - 1];
    const failed = entry.metadata?.failed === true || /^Failed:/i.test(entry.message || '');
    if (previous && previous.type === 'action') {
      previous.detail = entry.message;
      previous.pending = false;
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
            className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-medium text-text-muted hover:text-text-secondary transition-colors"
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
            <div className="mt-1.5 max-h-80 overflow-y-auto border-l-2 border-border/60 pl-3">
              <Markdown>{item.reasoning}</Markdown>
            </div>
          )}
        </>
      )}
    </div>
  );
};

/** One action: a sentence, its state, and the raw payload behind a disclosure. */
const ActionRow: React.FC<{ item: Item; live: boolean }> = ({ item, live }) => {
  const [open, setOpen] = useState(false);
  const Icon = KIND_ICON[item.kind ?? 'think'];
  const running = live && item.pending;

  return (
    <div className="group">
      <button
        type="button"
        onClick={() => item.detail && setOpen((v) => !v)}
        aria-expanded={item.detail ? open : undefined}
        className={`w-full flex items-start gap-2 rounded-lg py-1.5 pl-2 pr-1 text-left transition-colors ${
          item.failed ? 'hover:bg-danger/10' : 'hover:bg-white/[0.04]'
        }`}
      >
        {/* State first, then kind. Whether it finished is the more urgent fact. */}
        <span className="mt-0.5 flex-none grid place-items-center h-4 w-4">
          {running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          ) : item.failed ? (
            <span className="h-1.5 w-1.5 rounded-full bg-danger" />
          ) : (
            <Check className="h-3.5 w-3.5 text-success/70" />
          )}
        </span>

        <Icon className={`mt-0.5 h-3.5 w-3.5 flex-none ${item.failed ? 'text-danger' : 'text-text-muted'}`} />

        <span className="min-w-0 flex-1">
          <span className={`block text-[13px] leading-snug ${item.failed ? 'text-danger' : 'text-slate-300'}`}>
            {item.text}
          </span>
          {(item.target || item.range) && (
            <span className="mt-0.5 flex items-center gap-1.5 min-w-0">
              {item.target && (
                <span className="text-[11px] text-text-muted font-mono truncate" title={item.target}>
                  {shortenPath(item.target)}
                </span>
              )}
              {/* Which part of the file, kept as its own chip so it survives the
                  truncation that a long path would otherwise impose on it. */}
              {item.range && (
                <span className="flex-none rounded bg-white/[0.06] px-1.5 py-px text-[10px] font-medium tabular-nums text-text-secondary">
                  {item.range}
                </span>
              )}
            </span>
          )}
        </span>

        {item.detail && (
          <ChevronRight
            className={`mt-0.5 h-3.5 w-3.5 flex-none text-text-muted transition-transform ${open ? 'rotate-90' : ''} opacity-0 group-hover:opacity-100`}
          />
        )}
      </button>

      {open && item.detail && (
        <pre className="mb-2 ml-8 mr-1 mt-1 max-h-56 overflow-auto rounded-lg bg-black/30 p-3 text-[11px] leading-relaxed text-text-secondary whitespace-pre-wrap break-all">
          {item.detail}
        </pre>
      )}
    </div>
  );
};

/**
 * A running narration of what the workflow is doing, newest at the bottom.
 *
 * Grouped by workflow step rather than shown as one flat stream: after a couple
 * of hundred entries "Read the specification" means nothing without knowing
 * which step was reading it, and the heading is the only thing that says so.
 * Each action carries its own state, so an unfinished one reads as in progress
 * instead of looking identical to a finished one.
 */
export const AgentActivity: React.FC<AgentActivityProps> = ({ logs, isRunning = false }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  const items = useMemo(() => buildItems(logs), [logs]);
  const groups = useMemo(() => groupByStage(items), [items]);

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

  const live = items.length > 0;
  // Only the newest action can still be in flight; anything earlier was settled
  // by whatever came after it, whether or not its own result was recorded.
  const lastKey = items[items.length - 1]?.key;
  const working = isRunning && items[items.length - 1]?.pending === true;

  return (
    <div className="glass-card rounded-2xl flex flex-col h-full overflow-hidden">
      <div className="flex-none px-4 py-3 border-b border-border/40 flex items-center gap-2.5">
        <span className="grid place-items-center h-7 w-7 rounded-lg bg-primary/15">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
        </span>
        <div className="min-w-0">
          <h3 className="font-semibold text-white text-sm leading-none">Live progress</h3>
          <p className="text-[11px] text-text-muted mt-1 leading-none">What the workflow is doing right now</p>
        </div>
        {live && <span className="ml-auto text-[11px] text-text-muted tabular-nums">{items.length}</span>}
      </div>

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
            className="absolute inset-0 overflow-y-auto px-2 py-3 flex flex-col"
          >
            {!live ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 px-6 text-center">
                <span className="grid place-items-center h-10 w-10 rounded-xl bg-white/[0.03]">
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
                {groups.map((group, index) => {
                  const span = formatSpan(group.from, group.to);
                  return (
                    <section key={`${group.stage}-${group.from}-${index}`} className="mb-1">
                      {/* Sticky, so the step you are reading stays named however
                          far down its actions run. */}
                      {/* Fully opaque. At 95% the entries scrolling underneath
                          showed through as a smear of half-legible text along
                          the top edge of the panel. */}
                      <header className="sticky top-0 z-10 -mx-2 flex items-baseline gap-2 border-b border-border/40 bg-[#172033] px-4 py-1.5">
                        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary truncate">
                          {describeStage(group.stage).title}
                        </h4>
                        {span && <span className="ml-auto text-[11px] text-text-muted tabular-nums">{span}</span>}
                      </header>

                      <div className="space-y-0.5 pt-1">
                        {group.items.map((item) => (
                          <div key={item.key} className="animate-activity-in">
                            {item.type === 'message' ? (
                              <MessageRow
                                item={item}
                                stream={item.key === streamingKey}
                                onGrow={followText}
                                onStreamed={markStreamed}
                              />
                            ) : (
                              <ActionRow item={item} live={item.key === lastKey && isRunning} />
                            )}
                          </div>
                        ))}
                      </div>
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
              className="w-full flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-[11px] font-medium text-text-secondary hover:text-white hover:bg-white/[0.04] transition-colors"
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
