import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlanPanel } from './PlanPanel';

const { getPlanNow } = vi.hoisted(() => ({ getPlanNow: vi.fn() }));
vi.mock('../api', () => ({ getPlanNow }));

describe('the sprint’s plan beside the feed (plan WS.2)', () => {
  it('shows each work order as done, working or open, with the attempt, round and open defects', async () => {
    getPlanNow.mockResolvedValueOnce({
      sprint: 2, planned_total: 3, goal: 'Export', attempt: 2, round: 1, open_defects: 1,
      work_orders: [
        { title: 'The export route', role: 'backend', state: 'done', files: [] },
        { title: 'The export view', role: 'ui_ux', state: 'working', files: [] },
        { title: 'The export tests', role: 'testing', state: 'open', files: [] },
      ],
    });
    render(<PlanPanel runId="run-1" refreshKey="a" />);

    expect(await screen.findByText('Sprint 2 of 3')).toBeTruthy();
    expect(screen.getByText('Work orders: 1 of 3 done')).toBeTruthy();
    const states = [...document.querySelectorAll('li[data-state]')].map((li) => [li.textContent, li.getAttribute('data-state')]);
    expect(states).toEqual([
      ['The export routebackend · done', 'done'],
      ['The export viewui ux · working', 'working'],
      ['The export teststesting · open', 'open'],
    ]);
    const figures = screen.getByText('Attempt').closest('dl')!.textContent;
    expect(figures).toBe('Attempt2Test round1Open defects1');
  });

  it('reads the plan again when the run moves on', async () => {
    getPlanNow.mockResolvedValue({ sprint: null, planned_total: 0, goal: '', attempt: 0, round: 0, open_defects: 0, work_orders: [] });
    const { rerender } = render(<PlanPanel runId="run-1" refreshKey="a" />);
    expect(await screen.findByText('The sprints are not planned yet.')).toBeTruthy();
    const before = getPlanNow.mock.calls.length;

    rerender(<PlanPanel runId="run-1" refreshKey="b" />);

    expect(getPlanNow.mock.calls.length).toBe(before + 1);
  });
});
