import React, { useEffect, useState } from 'react';
import { getSteering } from '../api';
import type { LogEntry, RunStage } from '../types';
import { marks, type Mark } from '../lib/timeline';

const STYLE: Record<Mark['kind'], string> = {
  stage: 'h-3 w-0.5 bg-border-strong',
  gate: 'h-3 w-3 rounded-full bg-primary',
  steering: 'h-3 w-3 rotate-45 bg-warning',
};

/**
 * The run's span as a line (plan BG.14): a tick where each stage began, a dot
 * where the owner answered a gate, a diamond where a direction was sent.
 * Choosing a mark takes the feed to that moment.
 */
export const Timeline: React.FC<{
  runId: string;
  startedAt: string;
  endedAt: number;
  stages: RunStage[];
  logs: LogEntry[];
  onPick: (at: string) => void;
}> = ({ runId, startedAt, endedAt, stages, logs, onPick }) => {
  const [steering, setSteering] = useState<{ at: string; text: string }[]>([]);
  useEffect(() => {
    let live = true;
    getSteering(runId).then((notes) => live && setSteering(notes)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [runId]);

  const found = marks(startedAt, endedAt, stages, logs, steering);
  if (found.length === 0) return null;
  return (
    <div role="group" aria-label="The run's timeline" className="relative mx-4 my-2 h-5">
      <div aria-hidden="true" className="absolute inset-x-0 top-1/2 h-px bg-border" />
      {found.map((mark, index) => (
        <button
          key={`${mark.kind}-${mark.at}-${index}`}
          type="button"
          title={mark.label}
          aria-label={`${mark.label}, ${new Date(mark.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
          onClick={() => onPick(mark.at)}
          style={{ left: `${mark.share * 100}%` }}
          className="absolute top-1/2 grid h-6 w-6 -translate-x-1/2 -translate-y-1/2 place-items-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <span aria-hidden="true" className={STYLE[mark.kind]} />
        </button>
      ))}
    </div>
  );
};
