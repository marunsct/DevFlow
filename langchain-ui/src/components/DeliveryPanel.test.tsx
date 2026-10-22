import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DeliveryPanel } from './DeliveryPanel';

const { get, getChanges } = vi.hoisted(() => ({
  get: vi.fn(async (url: string) => (url.endsWith('/decisions') ? { data: { decisions: [] } } : {
    data: {
      acceptance: { ran: true, criteria: { 'AC-1': { id: 'AC-1', text: 'Sign in', status: 'passed', tests: [] } } },
      deferred: {}, screenshots: [], pages: [],
      first_passed: { 'AC-1': { test: 'auth.spec.js › [AC-1] signs in', after: 'after defect_fix_1_0', at: '2026-10-19T10:00:00Z' } },
    },
  })),
  getChanges: vi.fn(async () => ({
    commits: [
      { sha: 'later', message: 'Before defect_fix_1_1', at: '2026-10-19T10:05:00Z', files: [] },
      { sha: 'thefix', message: 'Fix: [AC-1] sign in', at: '2026-10-19T10:00:01Z', files: [] },
      { sha: 'earlier', message: 'Before defect_fix_1_0', at: '2026-10-19T09:50:00Z', files: [] },
    ],
  })),
}));
vi.mock('../api', () => ({ api: { get }, getChanges }));

describe('a criterion in the ledger', () => {
  it('says after which step it first passed, and opens the change that did it', async () => {
    const onOpenChange = vi.fn();
    render(<DeliveryPanel runId="run-1" onOpenChange={onOpenChange} />);

    expect(await screen.findByText(/first passing test: after Fixing problem 1 \(test round 1\)/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'see the change' }));

    expect(onOpenChange).toHaveBeenCalledWith('thefix');
  });
});

describe('the measurement a criterion first passed in', () => {
  it('says a measurement taken before a step as such', async () => {
    get.mockImplementation(async (url: string) => (url.endsWith('/decisions') ? { data: { decisions: [] } } : {
      data: {
        acceptance: { ran: true, criteria: { 'AC-1': { id: 'AC-1', text: 'Sign in', status: 'passed', tests: [] } } },
        deferred: {}, screenshots: [], pages: [],
        first_passed: { 'AC-1': { test: 't', after: 'before defect_fix_2_16', at: '2026-10-19T10:00:00Z' } },
      },
    }));
    render(<DeliveryPanel runId="run-1" />);
    expect(await screen.findByText(/first passing test: by the start of Fixing problem 17 \(test round 2\)/)).toBeTruthy();
  });
});

describe('the criteria summary', () => {
  it('counts the criteria by where they stand, above the list', async () => {
    get.mockImplementation((async (url: string) => (url.endsWith('/decisions') ? { data: { decisions: [] } } : {
      data: {
        acceptance: { ran: true, criteria: {
          'AC-1': { id: 'AC-1', text: 'Sign in', status: 'passed', tests: [] },
          'AC-2': { id: 'AC-2', text: 'Sign out', status: 'failed', tests: [] },
          'AC-3': { id: 'AC-3', text: 'Share', status: 'deferred', tests: [] },
          'AC-4': { id: 'AC-4', text: 'Search', status: 'failed', tests: [] },
        } },
        deferred: {}, screenshots: [], pages: [],
      },
    })) as never);
    render(<DeliveryPanel runId="run-1" />);

    const bar = await screen.findByRole('progressbar', { name: 'Acceptance criteria passing' });
    expect(bar.getAttribute('aria-valuenow')).toBe('1');
    expect(screen.getByText('2 failed')).toBeTruthy();
    expect(screen.getByText('1 deferred')).toBeTruthy();
  });
});
