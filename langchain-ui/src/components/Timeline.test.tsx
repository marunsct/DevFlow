import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Timeline } from './Timeline';
import type { LogEntry, RunStage } from '../types';

const known = vi.hoisted(() => ({ getSteering: vi.fn(async (): Promise<unknown[]> => []) }));
vi.mock('../api', () => known);

describe('the timeline', () => {
  it('takes the feed to the moment a mark stands for', async () => {
    const onPick = vi.fn();
    render(
      <Timeline
        runId="run-1"
        startedAt="2026-10-19T10:00:00Z"
        endedAt={Date.parse('2026-10-19T12:00:00Z')}
        stages={[{ name: 'test_round_1', started_at: '2026-10-19T11:00:00Z' } as RunStage]}
        logs={[] as LogEntry[]}
        onPick={onPick}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /Testing, round 1/ }));
    expect(onPick).toHaveBeenCalledWith('2026-10-19T11:00:00Z');
  });

  it('marks the directions sent, leaving out one withdrawn before any stage read it', async () => {
    known.getSteering.mockResolvedValueOnce([
      { id: 'N-1', text: 'keep the store in one file', by: 'owner', at: '2026-10-19T10:30:00Z', state: 'read' },
      { id: 'N-2', text: 'drop the export', by: 'owner', at: '2026-10-19T10:40:00Z', state: 'withdrawn' },
    ]);
    render(
      <Timeline
        runId="run-1"
        startedAt="2026-10-19T10:00:00Z"
        endedAt={Date.parse('2026-10-19T12:00:00Z')}
        stages={[] as RunStage[]}
        logs={[] as LogEntry[]}
        onPick={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByRole('button', { name: /keep the store in one file/ })).toBeTruthy());
    expect(screen.queryByRole('button', { name: /drop the export/ })).toBeNull();
  });
});
