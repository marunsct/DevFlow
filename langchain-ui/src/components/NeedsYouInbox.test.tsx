import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { NeedsYouInbox } from './NeedsYouInbox';
import { FeedbackProvider } from './Feedback';

const { listRuns, submitApproval, submitReview } = vi.hoisted(() => ({
  listRuns: vi.fn(),
  submitApproval: vi.fn(async () => ({ message: 'ok' })),
  submitReview: vi.fn(async () => ({ message: 'ok' })),
}));
vi.mock('../api', () => ({ listRuns, submitApproval, submitReview }));

const base = { current_stage: 'release_review', created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T01:00:00Z', document_names: [] };

const show = () =>
  render(
    <MemoryRouter>
      <FeedbackProvider>
        <NeedsYouInbox />
      </FeedbackProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  localStorage.setItem('token', 'signed-in');
  listRuns.mockReset();
  submitApproval.mockClear();
  submitReview.mockClear();
});

describe('the needs-you inbox', () => {
  it('counts the live waiting run only, says when its gate approves itself, and approves it in one tap', async () => {
    listRuns.mockResolvedValue({
      runs: [
        { ...base, run_id: 'run-gate', status: 'waiting_for_approval', gate_deadline: '2026-10-19T00:40:00Z' },
        { ...base, run_id: 'run-failed', status: 'failed' },
        { ...base, run_id: 'run-done', status: 'completed' },
      ],
      total: 3,
    });
    show();

    const trigger = await screen.findByRole('button', { name: '1 run waiting for you' });
    await userEvent.click(trigger);

    const region = screen.getByRole('region', { name: 'What needs you' });
    expect(region.textContent).toMatch(/run-gate · Release Reviewapproves itself at/);
    expect(region.textContent).toMatch(/Stopped since you last looked/);

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(submitApproval).toHaveBeenCalledWith('run-gate', { action: 'approve', reason: null });
  });

  it('answers a review with a review approval', async () => {
    listRuns.mockResolvedValue({ runs: [{ ...base, run_id: 'run-review', status: 'waiting_for_review' }], total: 1 });
    show();

    await userEvent.click(await screen.findByRole('button', { name: '1 run waiting for you' }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(submitReview).toHaveBeenCalledWith('run-review', { action: 'approve', comment: null });
  });

  it('hides a dismissed row, and the count with it', async () => {
    listRuns.mockResolvedValue({ runs: [{ ...base, run_id: 'run-gate', status: 'waiting_for_approval' }], total: 1 });
    show();

    await userEvent.click(await screen.findByRole('button', { name: '1 run waiting for you' }));
    await userEvent.click(screen.getByRole('button', { name: 'Hide run-gate until it moves' }));

    expect(screen.getByRole('button', { name: 'Nothing waits for you' })).toBeTruthy();
  });

  it('closes on Escape and gives focus back', async () => {
    listRuns.mockResolvedValue({ runs: [], total: 0 });
    show();

    const trigger = screen.getByRole('button', { name: 'Nothing waits for you' });
    await userEvent.click(trigger);
    expect(screen.getByRole('region', { name: 'What needs you' })).toBeTruthy();

    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('region', { name: 'What needs you' })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
