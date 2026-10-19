/**
 * What the run page's summary card says about how far, how long and how much
 * (plan BG.1): the token count, the spend as priced or not, the typical time
 * of finished runs in the same delivery mode, and the run's ceilings.
 */
import { useEffect, useState } from 'react';
import { getOutcomes, type RunForecast } from '../api';
import type { CallUsage, RemediationInfo, RunCostSummary } from '../types';

/** "950", "12.4 k", "1.2 M". */
export function tokens(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)} M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)} k`;
  return String(count);
}

export interface Spend {
  /** What the card shows. */
  shown: string;
  /** Why, when the figure is partial or there is none. */
  why?: string;
  /** Whether the figure leaves calls out. */
  partial: boolean;
}

/**
 * The spend, never a made-up one: a run whose calls had no known price is
 * "not priced", not "$0.00"; one with some priced calls says how many were not.
 */
export function spend(cost: RunCostSummary, localOnly = false): Spend {
  if (cost.fully_priced) {
    // A run on the local model alone is priced at nothing, and says why.
    const local = localOnly && cost.estimated_cost_usd === 0 ? ' \u00B7 local model' : '';
    return { shown: `$${cost.estimated_cost_usd.toFixed(2)}${local}`, partial: false };
  }
  const models = cost.unpriced_models.join(', ') || 'no usage reported';
  if (cost.priced_requests === 0) {
    return {
      shown: 'not priced',
      why: `No call had a known price (${models}): a local model, or one missing from the price table.`,
      partial: true,
    };
  }
  return {
    shown: `$${cost.estimated_cost_usd.toFixed(2)} + ${cost.unpriced_requests} unpriced`,
    why: `Partial: ${cost.unpriced_requests} call(s) had no known price (${models}). The spending ceiling does not count them.`,
    partial: true,
  };
}

const hours = (value: number): string => (value >= 10 ? value.toFixed(0) : value.toFixed(1));

/** "typically 7.6 h for fast runs here (1.4-12.7 h, 5 runs)", or "" before any run of that mode finished. */
export function typicalTime(forecast: RunForecast | null | undefined): string {
  if (!forecast || forecast.runs < 1) return '';
  const range = forecast.runs > 1 ? ` (${hours(forecast.shortest_hours)}-${hours(forecast.longest_hours)} h, ${forecast.runs} runs)` : ' (1 run)';
  return `typically ${hours(forecast.typical_hours)} h for ${forecast.delivery_mode} runs here${range}`;
}

export interface Ceiling {
  label: string;
  used: number;
  limit: number;
  /** "1.2 M of 5.0 M tokens". */
  said: string;
}

/** A bar for each ceiling the deployment sets; none when it sets none. */
export function ceilings(
  cost: RunCostSummary | null | undefined,
  maxTokens: number | null | undefined,
  maxCostUsd: number | null | undefined,
): Ceiling[] {
  const found: Ceiling[] = [];
  const used = cost?.total_tokens ?? 0;
  if (maxTokens) {
    found.push({ label: 'Tokens against the run ceiling', used, limit: maxTokens, said: `${tokens(used)} of ${tokens(maxTokens)} tokens` });
  }
  if (maxCostUsd) {
    const spent = cost?.estimated_cost_usd ?? 0;
    found.push({
      label: 'Priced spend against the run ceiling',
      used: spent,
      limit: maxCostUsd,
      said: `$${spent.toFixed(2)} of $${maxCostUsd.toFixed(2)}, priced calls only`,
    });
  }
  return found;
}

/** "typically 7.6 h for fast runs here (...)" from the finished runs, or "" before there are any. */
export function useTypicalTime(deliveryMode: string | null | undefined): string {
  const [forecast, setForecast] = useState<Record<string, RunForecast | null>>({});
  useEffect(() => {
    let live = true;
    getOutcomes()
      .then((data) => live && setForecast(data.forecast ?? {}))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return deliveryMode ? typicalTime(forecast[deliveryMode]) : '';
}

/**
 * Where the fix loop stands while it runs: "2 of 3 fix cycles run · 23 defects,
 * 9 open · 7 test runs"; "" outside a test round or a fix.
 */
export function fixLoop(remediation: RemediationInfo | null | undefined, stage: string | null | undefined): string {
  if (!remediation || !/^(defect_fix|test_round)/.test(stage ?? '')) return '';
  const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;
  return [
    `${remediation.attempt} of ${remediation.max_attempts} fix cycles run`,
    // A server older than the open count sends none: the line leaves it out.
    typeof remediation.open_defects === 'number'
      ? `${plural(remediation.defect_count, 'defect')}, ${remediation.open_defects} open`
      : plural(remediation.defect_count, 'defect'),
    plural(remediation.test_runs, 'test run'),
    ...(remediation.escalated ? ['escalated'] : []),
  ].join(' · ');
}

export interface Pressure {
  /** Tokens the last call sent, and of how many the slot holds (null when the server does not say). */
  lastInput: number;
  slotContext: number | null;
  /** Share of the last 10 minutes spent waiting on replies, 0..1. */
  busy: number;
  /** Output tokens per second of each recent call, oldest first. */
  pace: number[];
}

/** How close the run's calls come to the slot's context, how busy the model is, and its pace (plan BG.15). */
export function pressure(calls: CallUsage[], slotContext: number | null | undefined, now = Date.now()): Pressure | null {
  if (calls.length === 0) return null;
  const last = calls[calls.length - 1];
  const window = 10 * 60 * 1000;
  const busySeconds = calls
    .filter((call) => now - new Date(call.at).getTime() <= window)
    .reduce((sum, call) => sum + call.seconds, 0);
  return {
    lastInput: last.input_tokens,
    slotContext: slotContext ?? null,
    busy: Math.min(1, busySeconds / (window / 1000)),
    pace: calls.filter((call) => call.seconds > 0).map((call) => call.output_tokens / call.seconds),
  };
}
