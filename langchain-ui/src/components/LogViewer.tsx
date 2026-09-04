import React, { useEffect, useRef, useState } from 'react';
import type { LogEntry } from '../types';
import { ChevronDown, ChevronUp, Terminal } from 'lucide-react';

interface LogViewerProps {
  logs: LogEntry[];
}

export const LogViewer: React.FC<LogViewerProps> = ({ logs }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isExpanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isExpanded]);

  const getEventColor = (eventType: string) => {
    switch (eventType) {
      case 'error': return 'text-danger';
      case 'approval_request': return 'text-warning';
      case 'approval_auto': return 'text-success';
      case 'review_request': return 'text-warning';
      case 'complete': return 'text-success';
      case 'stage_change': return 'text-primary';
      default: return 'text-text-secondary';
    }
  };

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div
        className="flex justify-between items-center px-5 py-3.5 border-b border-border/50 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2.5">
          <Terminal className="h-4.5 w-4.5 text-primary" />
          <h3 className="font-semibold text-white text-sm">Live Logs</h3>
          <span className="bg-primary/20 text-primary text-xs px-2 py-0.5 rounded-full font-semibold">
            {logs.length}
          </span>
        </div>
        <button className="text-text-muted hover:text-white focus:outline-none transition-colors">
          {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {isExpanded && (
        <div
          ref={scrollRef}
          className="p-4 max-h-[400px] overflow-y-auto bg-[#0a0f1a] font-mono text-xs leading-relaxed"
        >
          {logs.length === 0 ? (
            <div className="text-text-muted italic py-8 text-center">Waiting for logs...</div>
          ) : (
            <div className="space-y-1">
              {logs.map((log) => {
                const time = new Date(log.timestamp).toLocaleTimeString([], {
                  hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
                });
                return (
                  <div key={log.sequence} className="flex gap-3 hover:bg-white/[0.03] px-2 py-1 rounded">
                    <span className="text-text-muted shrink-0">{time}</span>
                    <span className={`font-semibold shrink-0 w-28 truncate ${getEventColor(log.event_type)}`} title={log.stage}>
                      {log.stage}
                    </span>
                    <span className="text-slate-300 break-words">{log.message}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
