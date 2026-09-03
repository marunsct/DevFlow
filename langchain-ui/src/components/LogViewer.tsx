import React, { useEffect, useRef, useState } from 'react';
import type { LogEntry } from '../types';
import { ChevronDown, ChevronUp, Terminal } from 'lucide-react';

interface LogViewerProps {
  logs: LogEntry[];
}

export const LogViewer: React.FC<LogViewerProps> = ({ logs }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive if expanded
  useEffect(() => {
    if (isExpanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isExpanded]);

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden mt-6">
      <div 
        className="flex justify-between items-center px-4 py-3 bg-slate-50 border-b border-slate-200 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5 text-slate-500" />
          <h3 className="font-semibold text-slate-800">Live Logs</h3>
          <span className="bg-slate-200 text-slate-600 text-xs px-2 py-0.5 rounded-full font-medium">
            {logs.length}
          </span>
        </div>
        <button className="text-slate-500 hover:text-slate-800 focus:outline-none">
          {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
        </button>
      </div>
      
      {isExpanded && (
        <div 
          ref={scrollRef}
          className="p-4 max-h-[400px] overflow-y-auto bg-slate-900 text-slate-300 font-mono text-sm"
        >
          {logs.length === 0 ? (
            <div className="text-slate-500 italic">Waiting for logs...</div>
          ) : (
            <div className="space-y-1.5">
              {logs.map((log) => {
                const time = new Date(log.timestamp).toLocaleTimeString([], { 
                  hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit' 
                });
                
                return (
                  <div key={log.sequence} className="flex gap-3 hover:bg-slate-800 px-2 py-1 rounded">
                    <span className="text-slate-500 shrink-0">[{time}]</span>
                    <span className="text-sky-400 font-semibold shrink-0 w-32 truncate" title={log.stage}>
                      {log.stage}
                    </span>
                    <span className="text-slate-100 break-words">{log.message}</span>
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
