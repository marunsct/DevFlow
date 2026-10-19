import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SprintSummaryPanel } from './SprintSummaryPanel';
import type { SprintView } from '../types';

const view: SprintView = {
  number: 1, planned_total: 3, goal: 'Accounts and sign-in', status: 'Completed', failure_reason: '',
  attempts: 2, planned: ['Register', 'Sign in'], features: ['Register', 'Sign in', 'Sign out'],
  test_cases: 30, cases_passed: 28, cases_failed: 2, test_rounds: 3, total_bugs: 5, fixed_bugs: 4, open_bugs: 1,
  defects: [{ status: 'fixed', description: 'Sign-in accepts an empty password', owner: 'backend_specialist' }],
  attempt_history: ['**Attempt 1** (first attempt) - Failed: suite red.'],
};

const { getSprints, fetchArtifactContent } = vi.hoisted(() => ({
  getSprints: vi.fn(),
  fetchArtifactContent: vi.fn(async () => null),
}));
vi.mock('../api', () => ({ getSprints, fetchArtifactContent }));

describe('the sprint milestones', () => {
  it('draws each sprint from the route, with no document read', async () => {
    getSprints.mockResolvedValue({ sprints: [view] });
    render(<SprintSummaryPanel runId="run-1" />);

    expect(await screen.findByText('Accounts and sign-in')).toBeTruthy();
    expect(screen.getByText('1 of 3 planned · 1 re-run')).toBeTruthy();
    expect(screen.getByText('28/30')).toBeTruthy();
    expect(screen.getByText('Test cases passed:')).toBeTruthy();
    expect(fetchArtifactContent).not.toHaveBeenCalled();
  });

  it('reads the documents when the route has nothing', async () => {
    getSprints.mockRejectedValue(new Error('404'));
    fetchArtifactContent.mockResolvedValueOnce('# Sprint 1 of 2 Summary\n\n**Goal:** From the document\n**Status:** Completed\n' as never);
    render(<SprintSummaryPanel runId="run-1" />);

    expect(await screen.findByText('From the document')).toBeTruthy();
  });
});
