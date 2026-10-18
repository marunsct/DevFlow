import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LessonsPanel } from './LessonsPanel';
import { FeedbackProvider } from './Feedback';

const lessons = [
  { id: 'L-1', stack: 'python', role: 'all', trigger: 'run_terminal_command X is not permitted', rule: 'Put the code in a file, then run it.', evidence_runs: 4, source: 'harness', status: 'proposed' },
  { id: 'L-2', stack: 'node', role: 'all', trigger: 'read_file refused', rule: 'Read once.', evidence_runs: 3, source: 'harness', status: 'approved' },
];

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(async () => ({ data: { lessons: [] as unknown[] } })),
  post: vi.fn(async () => ({ data: {} })),
}));
vi.mock('../api', () => ({ api: { get, post } }));

describe('the lessons panel', () => {
  it('offers approve and reject only for a proposal, and calls the route', async () => {
    get.mockResolvedValue({ data: { lessons } });
    render(<FeedbackProvider><LessonsPanel /></FeedbackProvider>);

    expect(await screen.findByText('Put the code in a file, then run it.')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Approve' })).toHaveLength(1);
    expect(screen.getByText(/seen in 4 runs/)).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(post).toHaveBeenCalledWith('/lessons/L-1/approve');
  });

  it('says so when there is nothing to decide', async () => {
    get.mockResolvedValue({ data: { lessons: [] } });
    render(<FeedbackProvider><LessonsPanel /></FeedbackProvider>);

    expect(await screen.findByText(/No lessons yet/)).toBeTruthy();
  });
});
