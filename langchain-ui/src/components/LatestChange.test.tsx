import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LatestChange } from './LatestChange';

vi.mock('../api', () => ({
  getChanges: vi.fn(async () => ({
    commits: [
      { sha: 'abc1234', message: 'Fix: [AC-12] sign-in keeps the session', at: '2026-10-19T12:00:00Z',
        files: [{ path: 'a.py', added: 100, removed: 8 }, { path: 'b.py', added: 20, removed: 0 }, { path: 'img.png', added: null, removed: null }] },
      { sha: 'def5678', message: 'Before defect_fix_2_3', at: '2026-10-19T11:00:00Z', files: [] },
    ],
  })),
}));

describe('the latest change', () => {
  it('says what the newest commit was and how big, and opens it', async () => {
    const onOpen = vi.fn();
    render(<LatestChange runId="run-1" refreshKey="defect_fix_2_3:running" onOpen={onOpen} />);

    expect(await screen.findByText('Fix: [AC-12] sign-in keeps the session')).toBeTruthy();
    expect(screen.getByText('3 files · +120/−8')).toBeTruthy();
    await userEvent.click(screen.getByRole('button'));
    expect(onOpen).toHaveBeenCalledWith('abc1234');
  });
});
