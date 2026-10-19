import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Compare } from './Compare';

vi.mock('../api', () => ({
  listRuns: vi.fn(async () => ({ runs: [], total: 0 })),
  compareRuns: vi.fn(async () => ({
    a: 'run-a', b: 'run-b',
    rows: [
      { key: 'tool_failure_rate', a: 0.1, b: 0.2, change: 1, worse: true },
      { key: 'cached_token_share', a: 0.5, b: 0.6, change: 0.2, worse: false },
    ],
  })),
}));

describe('comparing two runs', () => {
  it('shows each measure before and after, and marks the worse', async () => {
    render(<MemoryRouter initialEntries={['/runs/compare?a=run-a&b=run-b']}><Compare /></MemoryRouter>);

    const failed = (await screen.findByText('Tool calls that failed')).closest('tr')!;
    expect(failed.textContent).toMatch(/10 %20 %\+100 %/);
    expect(failed.textContent).toMatch(/worse/);
    expect(screen.getByText('Input served from cache').closest('tr')!.textContent).not.toMatch(/worse/);
  });
});
