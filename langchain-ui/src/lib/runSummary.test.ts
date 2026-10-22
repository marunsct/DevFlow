import { describe, expect, it } from 'vitest';
import type { RunCostSummary } from '../types';
import { ceilings, fixLoop, pressure, spend, tokens, typicalTime } from './runSummary';

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
    expect(spend(cost(), true).shown).toBe('$0.00 · local model');
  });

  const forecast = (extra = {}) => ({
    delivery_mode: 'fast', runs: 6, typical_hours: 4.7, shortest_hours: 0.7, longest_hours: 12.7,
    hours_per_criterion: 0.4, fewest_criteria: 8, most_criteria: 18, ...extra,
  });

  it('estimates a brief of its size, which compares the modes like with like', () => {
    expect(typicalTime(forecast(), 13)).toBe('about 5.2 h for 13 criteria (last 6 fast runs here: about 24 min a criterion)');
  });

  it('without a size, says the typical time and what it was measured on', () => {
    expect(typicalTime(forecast())).toBe('typically 4.7 h (last 6 fast runs here: 0.7-13 h, briefs of 8-18 criteria)');
  });

  it('calls two runs too few, rather than a typical time', () => {
    // Measured live: two thorough runs made a "typical" 1.5 h beside a fast 4.7 h.
    expect(typicalTime(forecast({ delivery_mode: 'thorough', runs: 2, typical_hours: null, hours_per_criterion: null }), 13))
      .toBe('only 2 thorough runs finished here: too few to estimate');
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
    const older = { ...remediation, open_defects: undefined as unknown as number };
    expect(fixLoop(older, 'defect_fix_2_3')).toBe('2 of 3 fix cycles run · 23 defects · 7 test runs');
  });
});

describe('the pressure on the model', () => {
  const at = (minutesAgo: number) => new Date(Date.parse('2026-10-19T12:00:00Z') - minutesAgo * 60_000).toISOString();
  const call = (minutesAgo: number, input: number, output: number, seconds: number) => ({ at: at(minutesAgo), stage: 's', input_tokens: input, output_tokens: output, seconds });

  it('says how full the last call was, how busy the last ten minutes were, and the pace', () => {
    const found = pressure([call(30, 50_000, 900, 30), call(8, 90_000, 600, 120), call(1, 118_000, 300, 180)], 126_464, Date.parse('2026-10-19T12:00:00Z'))!;
    expect(found.lastInput).toBe(118_000);
    expect(found.slotContext).toBe(126_464);
    expect(found.busy).toBeCloseTo(0.5);
    expect(found.pace).toEqual([30, 5, 300 / 180]);
  });

  it('says nothing before any call', () => {
    expect(pressure([], 126_464)).toBeNull();
  });
});
