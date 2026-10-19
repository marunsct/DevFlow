/**
 * The KPIs a run is measured by, in words (plan UI-S6): the loop's ledger keys,
 * named for a person, and how each is shown.
 */
export const KPI_WORDS: Record<string, string> = {
  wall_minutes: 'Wall time (min)',
  active_minutes: 'Working time (min)',
  model_busy_share: 'Model busy',
  model_calls: 'Model calls',
  input_tokens: 'Input tokens',
  output_tokens: 'Output tokens',
  cached_token_share: 'Input served from cache',
  reasoning_share_estimated: 'Output spent reasoning',
  replies_lost_to_length: 'Replies lost to the output limit',
  lost_reply_output_share: 'Output in lost replies',
  tool_calls: 'Tool calls',
  tool_failure_rate: 'Tool calls that failed',
  redundant_read_rate: 'Reads of what it already had',
  identical_call_rate: 'Identical repeated calls',
  invalid_tool_call_rate: 'Tool calls that did not parse',
  unknown_tool_name_rate: 'Calls to tools that do not exist',
  test_rounds: 'Test rounds',
  defects_raised: 'Defects raised',
  defects_fixed: 'Defects fixed',
  defects_left_open: 'Defects left open',
  fixes_reverted: 'Fixes reverted',
  model_errors: 'Model errors',
  resumes: 'Resumes',
  steering_notes: 'Directions read',
};

/** The few a run's card shows first: what most often says a run went wrong. */
export const CARD_KPIS = ['identical_call_rate', 'cached_token_share', 'replies_lost_to_length', 'fixes_reverted', 'defects_left_open', 'tool_failure_rate'];

const SHARES = /(_rate|_share)$/;

export const kpiLabel = (key: string): string => KPI_WORDS[key] ?? key.replace(/_/g, ' ');

/** A KPI's value as shown: a share as a percentage, a count as a whole number. */
export function kpiValue(key: string, value: unknown): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  if (SHARES.test(key)) return `${(number * 100).toFixed(number < 0.1 ? 1 : 0)} %`;
  return Number.isInteger(number) ? number.toLocaleString() : number.toFixed(1);
}
