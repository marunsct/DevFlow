/**
 * What the header's inbox shows, worked out from one call to the runs list:
 * the live runs waiting for the owner (these are the count) and the runs that
 * failed since the Runs page was last opened (listed, never counted - nothing
 * of theirs waits). A row the owner dismisses stays hidden until its run moves.
 */
import type { RunSummary } from '../types';
import { describeStage } from './activity';
import { statusView } from './status';

export interface Inbox {
  /** Live runs waiting at a gate, a review or a budget. */
  waiting: RunSummary[];
  /** Runs that failed since the owner last looked. */
  stopped: RunSummary[];
}

const movedAt = (run: RunSummary): string => run.updated_at ?? run.created_at;

/** A dismissal holds for the run as it is now: once the run moves, its row shows again. */
export const dismissalKey = (run: RunSummary): string => `${run.run_id}@${movedAt(run)}`;

export function readInbox(runs: RunSummary[], seenAt: number, dismissed: ReadonlySet<string>): Inbox {
  const shown = runs.filter((run) => !dismissed.has(dismissalKey(run)));
  return {
    waiting: shown.filter((run) => statusView(run.status).needsYou),
    stopped: shown.filter((run) => run.status === 'failed' && new Date(movedAt(run)).getTime() > seenAt),
  };
}

/** What one tap answers for a waiting run, or null when only its page can (a budget needs a decision). */
export function oneTapAnswer(run: RunSummary): 'approval' | 'review' | null {
  if (run.status === 'waiting_for_approval') return 'approval';
  if (run.status === 'waiting_for_review') return 'review';
  return null;
}

export const shortRunId = (runId: string): string => (runId.length > 12 ? `${runId.slice(0, 12)}…` : runId);

const clock = (when: Date): string => when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/**
 * "run-8b0c41d2… · Release review · approves itself at 09:40". A gate with a
 * timeout says when it goes on without the owner, so it is never silent; one
 * without says it waits.
 */
export function inboxLine(run: RunSummary, formatTime: (when: Date) => string = clock): string {
  const { who, what } = inboxParts(run, formatTime);
  return `${who} · ${what}`;
}

export interface InboxParts {
  /** Which run, and where: "run-8b0c41d2… · Release review". */
  who: string;
  /** What happens next: "approves itself at 09:40", "waits for you". */
  what: string;
  /** The gate goes on without the owner at a set time. */
  timed: boolean;
}

/** The line in two parts, so a narrow row cuts the run's name short and never what happens next. */
export function inboxParts(run: RunSummary, formatTime: (when: Date) => string = clock): InboxParts {
  const who = `${shortRunId(run.run_id)} · ${describeStage(run.current_stage).title}`;
  if (run.status === 'waiting_for_budget') return { who, what: 'stopped at its budget', timed: false };
  if (run.gate_deadline) return { who, what: `approves itself at ${formatTime(new Date(run.gate_deadline))}`, timed: true };
  if (run.status === 'failed') return { who, what: 'stopped', timed: false };
  if (run.status === 'completed') return { who, what: 'finished', timed: false };
  return { who, what: 'waits for you', timed: false };
}

/** The statuses worth telling the owner about when a run reaches one. */
export const TOLD = ['waiting_for_approval', 'waiting_for_review', 'waiting_for_budget', 'failed', 'completed'];

/**
 * The runs that reached a status worth telling since the last poll. The first
 * poll only learns where each run stands: a page opened on ten finished runs
 * says nothing about them.
 */
export function newlyArrived(before: ReadonlyMap<string, string> | null, runs: RunSummary[]): RunSummary[] {
  if (!before) return [];
  return runs.filter((run) => TOLD.includes(run.status) && before.get(run.run_id) !== run.status);
}
