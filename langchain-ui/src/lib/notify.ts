/**
 * Browser notifications for a run that waits, fails or finishes, from any page.
 * Off until the owner turns them on: the browser's permission prompt appears
 * only from that choice, never on its own.
 */
import type { RunSummary } from '../types';
import { inboxLine } from './needsYou';

const WANTED = 'devflow.notify';

const HEADLINE: Record<string, string> = {
  waiting_for_approval: 'A run waits for your approval',
  waiting_for_review: 'A run waits for your review',
  waiting_for_budget: 'A run stopped at its budget',
  failed: 'A run stopped',
  completed: 'A run finished',
};

export const browserCanNotify = (): boolean => typeof Notification !== 'undefined';

export function notificationsWanted(): boolean {
  try {
    return localStorage.getItem(WANTED) === 'on';
  } catch {
    return false;
  }
}

/** Turn them on or off; true when they will be shown. Asks the browser only when turned on. */
export async function wantNotifications(on: boolean): Promise<boolean> {
  try {
    localStorage.setItem(WANTED, on ? 'on' : 'off');
  } catch {
    /* the choice holds for this page only */
  }
  if (!on || !browserCanNotify()) return false;
  if (Notification.permission === 'granted') return true;
  if (Notification.permission === 'denied') return false;
  return (await Notification.requestPermission()) === 'granted';
}

/** Show one run's news, when the owner wants it and the browser allows it. */
export function tell(run: RunSummary, open: (runId: string) => void): void {
  if (!notificationsWanted() || !browserCanNotify() || Notification.permission !== 'granted') return;
  const shown = new Notification(HEADLINE[run.status] ?? 'A run moved', { body: inboxLine(run), tag: run.run_id });
  shown.onclick = () => {
    window.focus();
    open(run.run_id);
    shown.close();
  };
}
