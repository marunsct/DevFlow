import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Timeline } from './Timeline';
import type { LogEntry, RunStage } from '../types';

vi.mock('../api', () => ({ getSteering: vi.fn(async () => []) }));

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
});
