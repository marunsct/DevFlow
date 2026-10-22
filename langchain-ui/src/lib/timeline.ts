/**
 * The marks on a run's timeline (plan BG.14): where each stage began, where the
 * owner answered a gate, where a direction was sent. Each sits at its share of
 * the run's span, so the line reads as the run's shape at a glance.
 */
import type { LogEntry, RunStage } from '../types';
import { describeStage } from './activity';

export interface Mark {
  kind: 'stage' | 'gate' | 'steering';
  at: string;
  /** 0..1 along the run's span. */
  share: number;
  label: string;
}

const time = (value: string | null | undefined): number | null => {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export function marks(
  startedAt: string,
  endedAt: number,
  stages: RunStage[],
  logs: LogEntry[],
  steering: { at: string; text: string }[],
): Mark[] {
  const from = time(startedAt);
  if (from === null || endedAt <= from) return [];
  const share = (at: number) => Math.min(1, Math.max(0, (at - from) / (endedAt - from)));
  const found: Mark[] = [];
  for (const stage of stages) {
    const at = time(stage.started_at);
    if (at !== null) found.push({ kind: 'stage', at: stage.started_at!, share: share(at), label: describeStage(stage.name).title });
  }
  for (const entry of logs) {
    if (entry.event_type !== 'review_decision' && entry.event_type !== 'approval_decision') continue;
    const at = time(entry.timestamp);
    if (at !== null) found.push({ kind: 'gate', at: entry.timestamp, share: share(at), label: entry.message || 'Your decision' });
  }
  for (const note of steering) {
    const at = time(note.at);
    if (at !== null) found.push({ kind: 'steering', at: note.at, share: share(at), label: `Direction: ${note.text}` });
  }
  return found.sort((a, b) => a.share - b.share);
}
