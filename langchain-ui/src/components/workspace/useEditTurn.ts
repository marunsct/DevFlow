/**
 * Whose turn it is to write a run's files (plans UX.12-UX.14, switch CO_DEVELOPMENT): the run's, while it is going;
 * one person's, while they hold the edit session on a stopped run. Taking the turn on a running run asks it to pause
 * at the end of its stage and takes the turn once it has; the holder's lease is renewed while the window is open.
 * With the switch off nothing here is offered and the workspace stays read-only.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  beatEditSession, discardEditSession, getEditSession, handBackEditSession, openEditSession, pauseRun,
  type EditSession, type HandBackAnswer,
} from '../../api';

export type Turn = 'off' | 'run' | 'yours' | 'theirs' | 'free' | 'pausing';

export interface EditTurn {
  turn: Turn;
  session: EditSession | null;
  /** Whether the editor may write now: the person holds the turn on a stopped run. */
  writable: boolean;
  take: () => Promise<void>;
  handBack: (reason: string) => Promise<HandBackAnswer>;
  discard: () => Promise<void>;
  refresh: () => void;
}

type Answered = { response?: { status?: number; data?: { detail?: unknown } } };

/** What the server said of a refused request: its words, and anything it sent beside them. */
export const refusalOf = (error: unknown): { status: number; message: string; extra: Record<string, unknown> } => {
  const response = (error as Answered | null)?.response;
  const detail = response?.data?.detail;
  if (detail && typeof detail === 'object') {
    const { message, ...extra } = detail as Record<string, unknown>;
    return { status: response?.status ?? 0, message: String(message ?? ''), extra };
  }
  return { status: response?.status ?? 0, message: typeof detail === 'string' ? detail : '', extra: {} };
};

const problemOf = (error: unknown, fallback: string): string => refusalOf(error).message || fallback;

export function useEditTurn(runId: string, runStatus: string | undefined, notify: (message: string) => void): EditTurn {
  const [enabled, setEnabled] = useState(false);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [session, setSession] = useState<EditSession | null>(null);
  const [pausing, setPausing] = useState(false);
  const [asked, setAsked] = useState(0);

  const refresh = useCallback(() => setAsked((n) => n + 1), []);

  useEffect(() => {
    let current = true;
    getEditSession(runId)
      .then((answer) => {
        if (!current) return;
        setEnabled(!!answer?.enabled);
        setStatuses(answer?.editable_statuses ?? []);
        setSession(answer?.session ?? null);
      })
      .catch(() => current && setEnabled(false));
    return () => { current = false; };
  }, [runId, runStatus, asked]);

  const stopped = !!runStatus && statuses.includes(runStatus);
  const mine = !!session?.yours;

  // The lease, renewed at half its length while the person holds the turn.
  const lease = session?.lease_seconds ?? 120;
  useEffect(() => {
    if (!enabled || !mine) return undefined;
    const beat = setInterval(() => {
      beatEditSession(runId).then((answer) => setSession(answer.session)).catch(() => refresh());
    }, Math.max(5, lease / 2) * 1000);
    return () => clearInterval(beat);
  }, [enabled, mine, lease, runId, refresh]);

  const opening = useRef(false);
  const open = useCallback(async () => {
    if (opening.current) return;
    opening.current = true;
    try {
      const answer = await openEditSession(runId);
      setSession(answer.session);
      setPausing(false);
    } catch (error) {
      notify(problemOf(error, 'The turn could not be taken.'));
    } finally {
      opening.current = false;
    }
  }, [runId, notify]);

  // Asked on a running run: the turn is taken as soon as the run has stopped at the end of its stage.
  useEffect(() => {
    if (pausing && stopped && !session) void open();
  }, [pausing, stopped, session, open]);

  const take = useCallback(async () => {
    if (stopped) {
      await open();
      return;
    }
    try {
      await pauseRun(runId, true);
      setPausing(true);
    } catch (error) {
      notify(problemOf(error, 'The run could not be paused.'));
    }
  }, [stopped, open, runId, notify]);

  const handBack = useCallback(async (reason: string) => {
    const answer = await handBackEditSession(runId, reason);
    setSession(null);
    return answer;
  }, [runId]);

  const discard = useCallback(async () => {
    await discardEditSession(runId);
    setSession(null);
  }, [runId]);

  const turn: Turn = !enabled ? 'off'
    : mine ? 'yours'
      : session ? 'theirs'
        : pausing ? 'pausing'
          : stopped ? 'free' : 'run';
  return { turn, session, writable: enabled && mine && stopped, take, handBack, discard, refresh };
}
