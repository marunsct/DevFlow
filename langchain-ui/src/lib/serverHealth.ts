/**
 * What the header and the run pages say about the build model's server (plan
 * BG.5), from `GET /api/health/server`: the server's own account of itself,
 * read without a model call, and which runs hold it now.
 */
import { useEffect, useState } from 'react';
import { getServerHealth } from '../api';
import type { ServerHealth } from '../types';
import type { Tone } from './status';
import { usePageVisible } from './usePageVisible';

export interface ServerView {
  tone: Tone;
  /** One line: what the server is and how it serves. */
  said: string;
}

const context = (tokens: number | null | undefined): string =>
  tokens ? `${Math.round(tokens / 1000)}k context` : 'context not reported';

export function describeServer(health: ServerHealth | null): ServerView {
  if (!health) return { tone: 'neutral', said: 'Model server: not checked yet' };
  if (health.hosted) return { tone: 'neutral', said: `Model: ${health.model || 'a hosted API'} (hosted; nothing to check)` };
  if (!health.answered) {
    return { tone: 'warn', said: `Model server did not answer its status at ${health.checked_at.slice(11, 16)} UTC: down, or not a server that reports one` };
  }
  const slots = health.slots ?? 1;
  const parts = [
    health.model || 'unnamed model',
    health.quantisation,
    `${slots} slot${slots === 1 ? '' : 's'}`,
    context(health.slot_context),
  ].filter(Boolean);
  const busy = health.busy_runs.length;
  return {
    tone: 'ok',
    said: `Model server: ${parts.join(' · ')}${busy ? ` · ${busy} run${busy === 1 ? '' : 's'} on it` : ' · idle'}`,
  };
}

/**
 * The run that holds the model when it serves one request at a time, or null:
 * a new run, or this one, waits for it.
 */
export function holdingTheModel(health: ServerHealth | null, besides?: string): string | null {
  if (!health || health.hosted || health.slots !== 1) return null;
  return health.busy_runs.find((runId) => runId !== besides) ?? null;
}

/** The server's health, read every minute while the tab is visible. */
export function useServerHealth(everyMs = 60_000): ServerHealth | null {
  const visible = usePageVisible();
  const [health, setHealth] = useState<ServerHealth | null>(null);
  useEffect(() => {
    if (!visible || !localStorage.getItem('token')) return;
    let live = true;
    const read = () =>
      getServerHealth()
        .then((found) => live && setHealth(found))
        .catch(() => undefined);
    void read();
    const timer = setInterval(read, everyMs);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [visible, everyMs]);
  return health;
}
