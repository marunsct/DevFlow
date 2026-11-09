import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OutcomesPanel } from './OutcomesPanel';

const outcome = (run_id: string, passed: number) => ({
  run_id, status: 'completed', delivery_mode: 'fast', use_frontier_model: false, started_at: null, hours: 1,
  score: { passed, total: 10 },
});

vi.mock('../api', () => ({
  getOutcomes: vi.fn(async () => ({
    runs: [outcome('run-aaaaaaaaaaaa1', 10), outcome('run-bbbbbbbbbbbb2', 9), outcome('run-cccccccccccc3', 8)],
    forecast: {},
  })),
}));

describe('the outcomes beside a page of runs', () => {
  it('shows only the finished runs of the page, in its order', async () => {
    render(<MemoryRouter><OutcomesPanel runIds={['run-cccccccccccc3', 'run-unfinished00', 'run-aaaaaaaaaaaa1']} /></MemoryRouter>);

    expect(await screen.findByText('Outcomes of the finished runs on this page')).toBeTruthy();
    const scores = screen.getAllByText(/^\d+\/10$/).map((cell) => cell.textContent);
    expect(scores).toEqual(['8/10', '10/10']);
  });

  it('says so when nothing on the page has finished', async () => {
    render(<MemoryRouter><OutcomesPanel runIds={['run-unfinished00']} /></MemoryRouter>);

    expect(await screen.findByText(/None of the runs on this page has finished yet/)).toBeTruthy();
  });
});
