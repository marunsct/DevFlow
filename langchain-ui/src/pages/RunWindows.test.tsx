import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { FeedbackProvider } from '../components/Feedback';

const { known } = vi.hoisted(() => ({ known: {} as Record<string, unknown> }));
vi.mock('../api', () => {
  Object.assign(known, {
    api: { get: vi.fn(async () => ({ data: { username: 'owner' } })) },
    getRun: vi.fn(async () => ({ run_id: 'run-1', run_name: 'Bookmarks', status: 'running', current_stage: 'sprint_build_1' })),
    getLogs: vi.fn(async () => ({ logs: [], total: 0 })),
    getPreview: vi.fn(async () => ({ enabled: true, state: 'none', idle_minutes: 15 })),
    getWorkspaceFiles: vi.fn(async () => ({ files: [{ path: 'src/app.py', size: 3 }], truncated: false, since: null, changed: [] })),
    listRuns: vi.fn(async () => ({ runs: [], total: 0 })),
  });
  return new Proxy(known, {
    get: (target, name) => {
      if (typeof name !== 'string' || name === 'then') return undefined;
      target[name] ??= vi.fn(async () => ({}));
      return target[name];
    },
  });
});

const at = (address: string) => render(
  <FeedbackProvider>
    <MemoryRouter initialEntries={[address]}>
      <AppRoutes />
    </MemoryRouter>
  </FeedbackProvider>,
);
const PAGE_SHELL = { name: 'DevFlow.ai home' };

beforeEach(() => localStorage.setItem('token', 'a-session'));
afterEach(() => localStorage.removeItem('token'));

describe("a run's own windows (plan UX.2)", () => {
  it("shows the preview alone, without the page's header and footer", async () => {
    at('/runs/run-1/preview');

    expect(await screen.findByRole('region', { name: 'Preview' })).toBeTruthy();
    expect(screen.queryByRole('link', PAGE_SHELL)).toBeNull();
    expect(screen.queryByText(/AI-Powered Product Development/)).toBeNull();
    expect(screen.getByRole('link', { name: 'Back to the run' }).getAttribute('href')).toBe('/runs/run-1?view=preview');
  });

  it("shows the workspace alone, without the page's header and footer", async () => {
    at('/runs/run-1/workspace');

    expect(await screen.findByRole('tablist', { name: 'Open files' })).toBeTruthy();
    expect(await screen.findByText('app.py')).toBeTruthy();
    expect(screen.queryByRole('link', PAGE_SHELL)).toBeNull();
  });

  it('asks for sign-in first', async () => {
    localStorage.removeItem('token');
    at('/runs/run-1/workspace');

    expect(await screen.findByText(/ADMIN_PASSWORD/)).toBeTruthy();
    expect(screen.queryByRole('tablist', { name: 'Open files' })).toBeNull();
  });
});
