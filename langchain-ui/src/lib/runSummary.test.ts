import { describe, expect, it } from 'vitest';
import type { RunCostSummary } from '../types';
import { ceilings, fixLoop, spend, tokens, typicalTime } from './runSummary';

const cost = (extra: Partial<RunCostSummary> = {}): RunCostSummary => ({
  completion_tokens: 300_000,
  estimated_cost_usd: 0,
  fully_priced: true,
  priced_requests: 0,
  prices_as_of: '2026-10',
  prompt_tokens: 900_000,
  successful_requests: 412,
  total_tokens: 1_200_000,
  unpriced_models: [],
  unpriced_requests: 0,
  ...extra,
});

describe('the summary card', () => {
  it('counts tokens in words a person reads', () => {
    expect(tokens(950)).toBe('950');
    expect(tokens(12_400)).toBe('12.4 k');
    expect(tokens(1_200_000)).toBe('1.2 M');
  });

  it('says an unpriced run is not priced, never $0.00', () => {
    const local = spend(cost({ fully_priced: false, unpriced_requests: 412, unpriced_models: ['qwen3.6-35b'] }));
    expect(local.shown).toBe('not priced');
    expect(local.why).toMatch(/qwen3\.6-35b/);

    const partial = spend(cost({ fully_priced: false, priced_requests: 10, unpriced_requests: 3, estimated_cost_usd: 1.5 }));
    expect(partial.shown).toBe('$1.50 + 3 unpriced');
    expect(spend(cost({ estimated_cost_usd: 2 })).shown).toBe('$2.00');
  });

  it('gives the typical time from the finished runs of the same mode', () => {
    expect(typicalTime({ delivery_mode: 'fast', typical_hours: 7.62, shortest_hours: 1.4, longest_hours: 12.7, runs: 5 }))
      .toBe('typically 7.6 h for fast runs here (1.4-13 h, 5 runs)');
    expect(typicalTime(null)).toBe('');
  });

  it('draws a bar for each ceiling that is set, and none otherwise', () => {
    expect(ceilings(cost(), null, null)).toEqual([]);
    const [bar] = ceilings(cost(), 5_000_000, null);
    expect(bar).toMatchObject({ used: 1_200_000, limit: 5_000_000, said: '1.2 M of 5.0 M tokens' });
    expect(ceilings(cost({ estimated_cost_usd: 1.2 }), null, 5)[0].said).toBe('$1.20 of $5.00, priced calls only');
  });
});

describe('the fix loop', () => {
  const remediation = { attempt: 2, max_attempts: 3, escalated: false, defect_count: 23, open_defects: 9, test_runs: 7 };

  it('says where it stands while a test round or a fix runs, and nothing otherwise', () => {
    expect(fixLoop(remediation, 'defect_fix_2_3')).toBe('2 of 3 fix cycles run · 23 defects, 9 open · 7 test runs');
    expect(fixLoop(remediation, 'test_round_2')).toMatch(/^2 of 3/);
    expect(fixLoop(remediation, 'acceptance_author_1')).toBe('');
    expect(fixLoop(null, 'defect_fix_1_0')).toBe('');
  });
});
