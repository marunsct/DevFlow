/**
 * Following the build (plan UX.11): a ready preview is looked at again every `FOLLOW_MS` to learn whether a newer
 * accepted sprint (or, for the workspace being built, a newer commit) is ready. Each look signs a fresh link, and a
 * new link would load the frame again and lose the page the person is on, so a look keeps the link it had while that
 * link has more than a minute left.
 */
import type { PreviewStatus } from '../types';

/** How often a ready preview is looked at again. */
export const FOLLOW_MS = 15_000;
/** A link with less than this left is replaced by the fresh one. */
const RENEW_WITHIN_MS = 60_000;

export function keepTheLink(previous: PreviewStatus | null, next: PreviewStatus, now: number = Date.now()): PreviewStatus {
  const same = previous?.state === 'ready' && next.state === 'ready' && previous.started_at === next.started_at;
  if (!same || !previous?.url || !previous.expires_at || previous.expires_at * 1000 - now <= RENEW_WITHIN_MS) {
    return next;
  }
  return { ...next, url: previous.url, pick_url: previous.pick_url, expires_at: previous.expires_at };
}
