import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { LogEntry } from '../types';
import { ArrowDown, Terminal } from 'lucide-react';
import { describeStage } from '../lib/activity';

interface LogViewerProps {
  logs: LogEntry[];
}

const EVENT_COLOR: Record<string, string> = {
  error: 'text-danger',
  approval_request: 'text-warning',
  review_request: 'text-warning',
  approval_auto: 'text-success',
  complete: 'text-success',
  stage_change: 'text-primary',
  agent_message: 'text-slate-400',
  tool_call: 'text-primary',
  tool_result: 'text-text-muted',
};

/**
 * Every event the run emitted, verbatim and in order.
 *
 * This is the escape hatch, not the main view: the dashboard's other panels say
 * what is happening in plain words, and this one is here for when that is not
 * enough and someone needs the raw record to file a bug against.
 *
 * Renders bare, without card chrome, because it sits inside the dashboard's
 * tabbed panel which already provides the surface and the title.
 */
export const LogViewer: React.FC<LogViewerProps> = ({ logs }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 48);
  }, []);

  useLayoutEffect(() => {
    if (!pinned) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs.length, pinned]);

  if (logs.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 px-6 text-center">
        <span className="grid place-items-center h-10 w-10 rounded-xl bg-white/[0.03]">
          <Terminal className="h-4 w-4 text-text-muted" />
        </span>
        <p className="text-sm text-text-secondary">No events yet</p>
        <p className="text-xs text-text-muted">The raw event record appears here once the run starts.</p>
      </div>
    );
  }

  return (
    <div className="relative h-full">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        role="log"
        aria-live="polite"
        aria-label="Run log"
        tabIndex={0}
        className="absolute inset-0 overflow-y-auto bg-[#080c16] px-3 py-3 font-mono text-[11.5px] leading-relaxed"
      >
        {logs.map((log) => {
          const time = new Date(log.timestamp).toLocaleTimeString([], {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          });
          return (
            <div
              key={log.event_id ?? log.sequence}
              className="flex gap-3 rounded px-2 py-1 hover:bg-white/[0.03]"
            >
              <span className="flex-none text-text-muted tabular-nums">{time}</span>
              <span
                className={`flex-none w-36 truncate font-semibold ${EVENT_COLOR[log.event_type] ?? 'text-text-secondary'}`}
                title={`${log.stage} · ${log.event_type}`}
              >
                {describeStage(log.stage).title}
              </span>
              <span className="min-w-0 flex-1 break-words whitespace-pre-wrap text-slate-300">
                {log.message}
              </span>
            </div>
          );
        })}
      </div>

      {!pinned && (
        <button
          type="button"
          onClick={() => {
            const el = scrollRef.current;
            if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
            setPinned(true);
          }}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full border border-border/60 bg-surface-raised/95 px-3 py-1.5 text-[11px] font-medium text-text-secondary shadow-lg backdrop-blur hover:text-white transition-colors"
        >
          <ArrowDown className="h-3 w-3" />
          Jump to latest
        </button>
      )}
    </div>
  );
};
