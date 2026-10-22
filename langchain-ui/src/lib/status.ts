/**
 * One map from a run's status to how it is shown: its words, its colour tokens,
 * its icon, and whether it needs the owner. The same facts used to be written
 * out in eight places, each slightly different; every surface now reads this.
 */
import { Activity, AlertCircle, CheckCircle2, Clock, Pause, XCircle, type LucideIcon } from 'lucide-react';
import { describeStatus } from './activity';

export type Tone = 'neutral' | 'accent' | 'ok' | 'warn' | 'danger';

export interface StatusView {
  label: string;
  tone: Tone;
  icon: LucideIcon;
  /** Whether the run is waiting for the owner (a gate, a review, a budget) - not one that merely failed. */
  needsYou: boolean;
  terminal: boolean;
}

const TERMINAL = ['completed', 'failed', 'cancelled'];
const NEEDS_YOU = ['waiting_for_approval', 'waiting_for_review', 'waiting_for_budget'];

const BASE: Record<string, { tone: Tone; icon: LucideIcon }> = {
  created: { tone: 'neutral', icon: Clock },
  running: { tone: 'accent', icon: Activity },
  waiting_for_review: { tone: 'warn', icon: AlertCircle },
  waiting_for_approval: { tone: 'warn', icon: AlertCircle },
  waiting_for_budget: { tone: 'warn', icon: AlertCircle },
  paused: { tone: 'warn', icon: Pause },
  completed: { tone: 'ok', icon: CheckCircle2 },
  failed: { tone: 'danger', icon: XCircle },
  cancelled: { tone: 'neutral', icon: XCircle },
};

export function statusView(status: string | null | undefined): StatusView {
  const key = status ?? 'created';
  const base = BASE[key] ?? BASE.created;
  return {
    label: describeStatus(key).label,
    tone: base.tone,
    icon: base.icon,
    needsYou: NEEDS_YOU.includes(key),
    terminal: TERMINAL.includes(key),
  };
}

/** The classes of a badge in each tone: a fill and text from the same token pair, so contrast holds in every theme. */
export const TONE_BADGE: Record<Tone, string> = {
  neutral: 'bg-overlay-strong text-text-secondary border-border',
  accent: 'bg-accent-soft text-primary border-primary/40',
  ok: 'bg-success-bg text-success border-success/40',
  warn: 'bg-warning-bg text-warning border-warning/40',
  danger: 'bg-danger-bg text-danger border-danger/40',
};
