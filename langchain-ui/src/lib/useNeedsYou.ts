/**
 * The runs that need the owner, polled from any page: the live runs waiting at
 * a gate, a review or a budget (the count, also shown on the browser tab), and
 * the runs that failed since the Runs page was last opened. A run reaching a
 * status worth telling is shown as a browser notification when the owner has
 * turned those on; then the poll goes on, slower, while the tab is hidden too.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { listRuns } from '../api';
import type { RunSummary } from '../types';
import { dismissalKey, newlyArrived, readInbox, type Inbox } from './needsYou';
import { notificationsWanted, tell } from './notify';
import { showCountInTab } from './tabBadge';
import { usePageVisible } from './usePageVisible';

const SEEN = 'devflow.runsSeenAt';
const DISMISSED = 'devflow.inboxDismissed';
const HIDDEN_POLL_MS = 60_000;

export function markRunsSeen(): void {
  try {
    localStorage.setItem(SEEN, String(Date.now()));
  } catch {
    /* storage may be unavailable */
  }
}

const seenAt = (): number => {
  try {
    return Number(localStorage.getItem(SEEN) || 0);
  } catch {
    return 0;
  }
};

const readDismissed = (): Set<string> => {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISSED) || '[]') as string[]);
  } catch {
    return new Set();
  }
};

export interface NeedsYou extends Inbox {
  /** Live waiting runs only: a failed run waits for nothing. */
  count: number;
  refresh: () => void;
  /** Hide a row until its run moves again. */
  dismiss: (run: RunSummary) => void;
}

export function useNeedsYou(open: (runId: string) => void, intervalMs = 30_000): NeedsYou {
  const visible = usePageVisible();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [dismissed, setDismissed] = useState(readDismissed);
  const [polls, setPolls] = useState(0);
  const before = useRef<Map<string, string> | null>(null);
  const opener = useRef(open);
  useEffect(() => {
    opener.current = open;
  }, [open]);

  useEffect(() => {
    if (!localStorage.getItem('token')) return;
    if (!visible && !notificationsWanted()) return;
    let live = true;
    const read = async () => {
      try {
        const { runs: found } = await listRuns();
        if (!live) return;
        for (const run of newlyArrived(before.current, found)) tell(run, opener.current);
        before.current = new Map(found.map((run) => [run.run_id, run.status]));
        setRuns(found);
      } catch {
        /* the inbox stays as it was */
      }
    };
    void read();
    const timer = setInterval(read, visible ? intervalMs : HIDDEN_POLL_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [visible, intervalMs, polls]);

  const inbox = useMemo(() => readInbox(runs, seenAt(), dismissed), [runs, dismissed]);
  const count = inbox.waiting.length;

  useEffect(() => showCountInTab(count), [count]);

  const dismiss = useCallback(
    (run: RunSummary) => {
      // Only rows still listed are kept, so the stored set never outgrows the list.
      const listed = new Set(runs.map(dismissalKey));
      const next = new Set([...dismissed].filter((key) => listed.has(key)));
      next.add(dismissalKey(run));
      try {
        localStorage.setItem(DISMISSED, JSON.stringify([...next]));
      } catch {
        /* dismissed for this page only */
      }
      setDismissed(next);
    },
    [runs, dismissed],
  );

  const refresh = useCallback(() => setPolls((n) => n + 1), []);

  return { ...inbox, count, refresh, dismiss };
}
