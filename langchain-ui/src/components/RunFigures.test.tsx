import { describe, expect, it, vi } from 'vitest';
import { render, renderHook, screen, waitFor } from '@testing-library/react';
import { RunFigures } from './RunFigures';
import { useTypicalTime } from '../lib/runSummary';
import type { RunStatusResponse } from '../types';

vi.mock('../api', () => ({
  getOutcomes: vi.fn(async () => ({
    runs: [],
    forecast: { fast: { delivery_mode: 'fast', typical_hours: 7.6, shortest_hours: 1.4, longest_hours: 12.7, runs: 5 }, thorough: null },
  })),
}));

const run = (extra: Partial<RunStatusResponse> = {}): RunStatusResponse => ({
  run_id: 'run-1', thread_id: 't', status: 'running', current_stage: 'defect_fix_2_3', stage_meaning: null,
  created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T01:00:00Z', stages: [], artifacts: [], reviews: [],
  remediation: null, error: null, auto_approve: false, completion_gaps: [], gate_deadline: null,
  approval_timeout_minutes: null, non_deliverable: '', delivery_mode: 'fast', use_frontier_model: false,
  max_run_tokens: null, max_run_cost_usd: null,
  cost: {
    completion_tokens: 300_000, estimated_cost_usd: 0, fully_priced: false, priced_requests: 0, prices_as_of: '2026-10',
    prompt_tokens: 900_000, successful_requests: 412, total_tokens: 1_200_000, unpriced_models: ['qwen'], unpriced_requests: 412,
  },
  ...extra,
});

const show = (value: RunStatusResponse) => render(<dl><RunFigures run={value} /></dl>);

describe('the run figures', () => {
  it('shows the tokens in and out, and an unpriced run as not priced', () => {
    show(run());

    expect(screen.getByText('1.2 M')).toBeTruthy();
    expect(screen.getByText(/900\.0 k in · 300\.0 k out/)).toBeTruthy();
    expect(screen.getByText('not priced')).toBeTruthy();
    expect(screen.queryByText(/\$0\.00/)).toBeNull();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('draws the token ceiling when the deployment sets one', () => {
    show(run({ max_run_tokens: 5_000_000 }));

    const bar = screen.getByRole('progressbar', { name: 'Tokens against the run ceiling' });
    expect(bar.getAttribute('aria-valuenow')).toBe('1200000');
    expect(screen.getByText('1.2 M of 5.0 M tokens')).toBeTruthy();
  });

  it('gives the typical time of finished runs in the same mode', async () => {
    const { result } = renderHook(() => useTypicalTime('fast'));
    await waitFor(() => expect(result.current).toBe('typically 7.6 h for fast runs here (1.4-13 h, 5 runs)'));
  });
});
