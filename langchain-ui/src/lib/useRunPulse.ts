/**
 * A run as an own-window page needs it (plan UX.2): the run's status read every few seconds while it is going and the
 * page is visible, and, when asked, its newest events, paged on from where the last read ended. The run page keeps
 * its own live stream; a window beside it reads at this pace instead.
 */
import { useEffect, useRef, useState } from 'react';
import { getLogs, getRun } from '../api';
import type { LogEntry, RunStatusResponse } from '../types';
import { usePageVisible } from './usePageVisible';

/** How often a going run is read again. */
export const PULSE_MS = 4000;
/** Events kept: the newest, for the feed and for when files were last written. */
const MOST_EVENTS = 1500;
const PAGE = 200;

const FINISHED = ['completed', 'failed', 'cancelled'];
const keyOf = (entry: LogEntry) => entry.event_id ?? `${entry.sequence}:${entry.timestamp}`;

export function useRunPulse(runId: string | undefined, withEvents = false) {
  const [run, setRun] = useState<RunStatusResponse | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const cursor = useRef<number | null>(null);
  const visible = usePageVisible();
  const going = !run || !FINISHED.includes(run.status);

  useEffect(() => {
    if (!runId) return undefined;
    let current = true;
    const read = async () => {
      try {
        const found = await getRun(runId);
        if (!current) return;
        setRun(found);
        setProblem(null);
        if (!withEvents) return;
        if (cursor.current === null) {
          const first = await getLogs(runId, 1, 0);
          cursor.current = Math.max(0, (first.total ?? 0) - MOST_EVENTS / 3);
        }
        for (let pages = 0; pages < 5 && current; pages += 1) {
          const page = await getLogs(runId, PAGE, cursor.current);
          const fresh = page.logs ?? [];
          if (!current || !fresh.length) break;
          cursor.current += fresh.length;
          setLogs((before) => {
            const seen = new Set(before.map(keyOf));
            return [...before, ...fresh.filter((entry) => !seen.has(keyOf(entry)))].slice(-MOST_EVENTS);
          });
          if (fresh.length < PAGE) break;
        }
      } catch (error: any) {
        if (current) setProblem(error?.response?.status === 404 ? 'This run was not found.' : 'The run could not be read. Retrying…');
      }
    };
    void read();
    if (!going || !visible) return () => { current = false; };
    const timer = setInterval(() => void read(), PULSE_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [runId, withEvents, going, visible]);

  return { run, problem, logs, going };
}
