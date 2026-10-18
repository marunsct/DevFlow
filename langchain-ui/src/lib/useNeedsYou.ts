/**
 * How many runs need the owner: those waiting at a gate, a review or a budget,
 * and those that failed since the Runs page was last opened. Polled while the
 * tab is visible, so the header can say it from any page.
 */
import { useEffect, useState } from 'react';
import { listRuns } from '../api';
import { statusView } from './status';
import { usePageVisible } from './usePageVisible';

const SEEN = 'devflow.runsSeenAt';

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

export function useNeedsYou(intervalMs = 30_000): { count: number; waiting: number; failed: number } {
  const visible = usePageVisible();
  const [found, setFound] = useState({ count: 0, waiting: 0, failed: 0 });

  useEffect(() => {
    if (!visible || !localStorage.getItem('token')) return;
    let live = true;
    const read = async () => {
      try {
        const { runs } = await listRuns();
        const since = seenAt();
        const waiting = runs.filter((r) => statusView(r.status).needsYou).length;
        const failed = runs.filter((r) => r.status === 'failed' && new Date(r.updated_at ?? r.created_at).getTime() > since).length;
        if (live) setFound({ count: waiting + failed, waiting, failed });
      } catch {
        /* the indicator stays as it was */
      }
    };
    void read();
    const timer = setInterval(read, intervalMs);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [visible, intervalMs]);

  return found;
}
