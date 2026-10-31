import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { RunList } from './RunList';
import { FeedbackProvider } from '../components/Feedback';
import { listRuns } from '../api';

const runs = [
  { run_id: 'run-old-done', status: 'completed', current_stage: 'complete', created_at: '2026-10-17T01:00:00Z', updated_at: '2026-10-17T03:00:00Z', document_names: ['notes.md'], delivery_mode: 'fast', local_only: true, completion_gaps: 1, criteria_proven: 9, criteria_total: 10 },
  { run_id: 'run-new-going', status: 'running', current_stage: 'defect_fix_2_3', created_at: '2026-10-18T01:00:00Z', document_names: ['tasks.md'], delivery_mode: 'fast', local_only: true, completion_gaps: 0, criteria_proven: 3, criteria_total: 13 },
  { run_id: 'run-waiting', status: 'waiting_for_approval', current_stage: 'approval_pause_scaffold', created_at: '2026-10-16T01:00:00Z', document_names: [], delivery_mode: 'thorough', local_only: false, completion_gaps: 0 },
];

vi.mock('../api', () => ({
  RUNS_PER_PAGE: 50,
  listRuns: vi.fn(async () => ({ runs, total: runs.length })),
  deleteRun: vi.fn(), cloneRun: vi.fn(), resumeRun: vi.fn(), pauseRun: vi.fn(),
  getOutcomes: vi.fn(async () => ({ runs: [], forecast: {} })),
}));

const show = (path = '/runs') => render(
  <MemoryRouter initialEntries={[path]}><FeedbackProvider><RunList /></FeedbackProvider></MemoryRouter>,
);

describe('the pages of runs', () => {
  it('asks for the page in the address, says which runs it shows, and moves to older ones', async () => {
    vi.mocked(listRuns).mockResolvedValue({ runs: runs as never, total: 120 });
    show('/runs?page=2');

    expect(await screen.findByText('Runs 51-100 of 120')).toBeTruthy();
    expect(listRuns).toHaveBeenLastCalledWith(2);

    await userEvent.click(screen.getByRole('button', { name: 'Older' }));
    expect(listRuns).toHaveBeenLastCalledWith(3);
    expect(await screen.findByText('Page 3 of 3')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Older' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows no pager when every run fits on one page', async () => {
    vi.mocked(listRuns).mockResolvedValue({ runs: runs as never, total: runs.length });
    show();
    await screen.findAllByRole('row');

    expect(screen.queryByRole('navigation', { name: 'Pages of runs' })).toBeNull();
  });
});

describe('the runs table', () => {
  it('lists the run that needs the owner first, then the newest', async () => {
    show();
    const rows = await screen.findAllByRole('row');

    const ids = rows.slice(1).map((row) => within(row).getByText(/^run-/, { exact: false }).textContent ?? '');
    expect(ids[0]).toContain('run-waiting');
    expect(ids[1]).toContain('run-new-going');
    expect(ids[2]).toContain('run-old-done');
  });

  it('shows what is proven and the gaps, and "-" before the suite exists', async () => {
    show();
    await screen.findAllByRole('row');

    expect(screen.getByText('9 of 10')).toBeTruthy();
    expect(screen.getByText('3 of 13')).toBeTruthy();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });

  it('filters to the runs that need the owner, from the address', async () => {
    show('/runs?status=needs-you');
    const rows = await screen.findAllByRole('row');

    expect(rows).toHaveLength(2);
    expect(within(rows[1]).getByText(/run-waiting/)).toBeTruthy();
  });

  it('searches by brief and says so when nothing matches', async () => {
    show();
    await screen.findAllByRole('row');
    await userEvent.type(screen.getByLabelText('Search runs'), 'nothing-like-this');

    expect(await screen.findByText(/No run matches/)).toBeTruthy();
  });

  it('labels every row action with the run it acts on', async () => {
    show();
    await screen.findAllByRole('row');

    expect(screen.getByLabelText('Pause run-new-going')).toBeTruthy();
    expect(screen.getByLabelText('Delete run-old-done')).toBeTruthy();
    expect(screen.queryByLabelText('Delete run-new-going')).toBeNull();
  });
});

describe('the run name and the model switch on every row', () => {
  it('shows the name a run was given above its stage, and a switch on each run that is not finished', async () => {
    // by id: the list sorts the shared fixture array in place, so its order is not what it was written in
    const going = runs.find((r) => r.run_id === 'run-new-going')!;
    const done = runs.find((r) => r.run_id === 'run-old-done')!;
    const named = [
      { ...going, run_name: 'tasks-api on 8888', model_pinned: true, model_last: { model: 'model-a', endpoint: '127.0.0.1:8888' } },
      { ...done, run_name: null, model_pinned: false, model_last: null },
    ];
    vi.mocked(listRuns).mockResolvedValue({ runs: named as never, total: named.length });
    show();

    expect(await screen.findByText('tasks-api on 8888')).toBeTruthy();
    const switches = screen.getAllByRole('switch', { name: 'Keep this run on its model' });
    // the finished run has none; the running one has one, on, and says so
    expect(switches).toHaveLength(1);
    expect(switches[0].getAttribute('aria-checked')).toBe('true');
    expect(within(switches[0]).getByText('Pinned')).toBeTruthy();
  });
});
