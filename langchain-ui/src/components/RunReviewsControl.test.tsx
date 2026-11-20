import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RunReviewsControl } from './RunReviewsControl';
import { FeedbackProvider } from './Feedback';

const known = vi.hoisted(() => ({ getReviewPolicy: vi.fn(), changeReviewPolicy: vi.fn() }));
vi.mock('../api', () => known);

const show = () =>
  render(
    <FeedbackProvider>
      <RunReviewsControl runId="run-1" />
    </FeedbackProvider>,
  );

describe('the reviews of a live run', () => {
  beforeEach(() => {
    known.getReviewPolicy.mockReset().mockResolvedValue({ technical_specification: true, sprint: true });
    known.changeReviewPolicy.mockReset();
  });

  it('shows the reviews the run stops for now', async () => {
    show();

    expect((await screen.findByTestId('reviews-on')).textContent).toContain('2 of 7 on');
    expect((screen.getByLabelText('Technical specification') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('The sprint plan') as HTMLInputElement).checked).toBe(false);
  });

  it('switches the plan gate on while the run runs, and shows the policy the server kept', async () => {
    known.changeReviewPolicy.mockResolvedValue({ technical_specification: true, sprint: true, sprint_plan: true });
    show();

    await userEvent.click(await screen.findByLabelText('The sprint plan'));

    await waitFor(() => expect(known.changeReviewPolicy).toHaveBeenCalledWith('run-1', { sprint_plan: true }));
    await waitFor(() => expect(screen.getByTestId('reviews-on').textContent).toContain('3 of 7 on'));
  });

  it('says why a change was refused and keeps what the run has', async () => {
    known.changeReviewPolicy.mockRejectedValue({ response: { data: { detail: 'Run run-1 is completed' } } });
    show();

    await userEvent.click(await screen.findByLabelText('Each sprint'));

    expect(await screen.findByText(/Run run-1 is completed/)).toBeTruthy();
    expect(screen.getByTestId('reviews-on').textContent).toContain('2 of 7 on');
  });
});
