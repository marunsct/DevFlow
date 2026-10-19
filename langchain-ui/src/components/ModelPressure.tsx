import React, { useEffect, useState } from 'react';
import { Gauge } from 'lucide-react';
import { getUsage } from '../api';
import type { CallUsage } from '../types';
import { Progress } from '../ui';
import { pressure, tokens } from '../lib/runSummary';
import { usePageVisible } from '../lib/usePageVisible';

/** A line of the recent pace, as small as a word: the shape matters, not the axes. */
const Sparkline: React.FC<{ values: number[]; label: string }> = ({ values, label }) => {
  if (values.length < 2) return null;
  const top = Math.max(...values) || 1;
  const points = values.map((value, index) => `${(index / (values.length - 1)) * 100},${20 - (value / top) * 18}`).join(' ');
  return (
    <svg viewBox="0 0 100 20" preserveAspectRatio="none" role="img" aria-label={label} className="h-6 w-full">
      <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
};

/**
 * How hard the run presses on the model (plan BG.15): how much of the slot's
 * context the last call filled - a call near the edge is the next to be cut -
 * how busy the model was in the last ten minutes, and the pace of its replies.
 */
export const ModelPressure: React.FC<{ runId: string; live: boolean; slotContext: number | null | undefined }> = ({ runId, live, slotContext }) => {
  const visible = usePageVisible();
  const [calls, setCalls] = useState<CallUsage[]>([]);
  useEffect(() => {
    let alive = true;
    const read = () => getUsage(runId).then((usage) => alive && setCalls(usage.recent_calls ?? [])).catch(() => undefined);
    void read();
    if (!live || !visible) return () => { alive = false; };
    const timer = setInterval(read, 60_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [runId, live, visible]);

  const found = pressure(calls, slotContext);
  if (!found) return null;
  const share = found.slotContext ? found.lastInput / found.slotContext : null;
  const pace = found.pace.length ? found.pace[found.pace.length - 1] : null;
  return (
    <section aria-labelledby="model-pressure" className="glass-card rounded-xl px-3 py-2.5 space-y-1.5">
      <h2 id="model-pressure" className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-text-muted">
        <Gauge className="h-3.5 w-3.5" aria-hidden="true" /> Model pressure
      </h2>
      <p className={`text-[13px] tabular-nums ${share !== null && share > 0.9 ? 'text-danger font-semibold' : 'text-text-primary'}`}>
        Last call used {tokens(found.lastInput)}{found.slotContext ? ` of ${tokens(found.slotContext)}` : ''} context
      </p>
      {share !== null && <Progress label="Context the last call used" value={found.lastInput} max={found.slotContext!} />}
      <p className="text-xs text-text-secondary tabular-nums">
        Busy {Math.round(found.busy * 100)}% of the last 10 min{pace !== null ? ` · ${pace.toFixed(1)} tokens/s last reply` : ''}
      </p>
      <Sparkline values={found.pace} label="Output tokens per second over the last hour" />
    </section>
  );
};
