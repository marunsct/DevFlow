import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Health } from './Health';

const { getOperatorHealth } = vi.hoisted(() => ({ getOperatorHealth: vi.fn() }));
vi.mock('../api', () => ({ getOperatorHealth }));

// Deep review 2026-11-18, F5: the disk filled and crashed the database, and only the loop's output said so.
describe('the health page', () => {
  it('shows every part with its state, and the runs waiting for a worker', async () => {
    getOperatorHealth.mockResolvedValue({
      status: 'warn', checked_at: '2026-11-18T12:00:00Z', version: 'abc1234',
      disk: { status: 'warn', said: '3.0 GiB free (1%). Low: a full disk stops the database and every run.' },
      database: { status: 'ok', said: 'The database answers.' },
      runs: { status: 'ok', said: '1 running of 2 slots, 1 waiting for a worker.', running: ['run-1'],
        waiting: [{ run_id: 'run-2', name: 'second', since: '', minutes: 7, position: 1 }] },
      model: { status: 'fail', said: 'The model server does not answer its status request.' },
      backup: { status: 'unknown', said: 'No backup folder is visible to the server.' },
    });
    render(<MemoryRouter><Health /></MemoryRouter>);

    expect((await screen.findByTestId('health-disk')).textContent).toContain('Low: a full disk');
    expect(screen.getByTestId('health-model').textContent).toContain('Down');
    expect(screen.getByText('second')).toBeTruthy();
    expect(screen.getByText(/Version abc1234/)).toBeTruthy();
  });
});
