import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RunDoctor } from './RunDoctor';

const { getRunDoctor, downloadDiagnosticBundle } = vi.hoisted(() => ({
  getRunDoctor: vi.fn(),
  downloadDiagnosticBundle: vi.fn(async () => undefined),
}));
vi.mock('../api', () => ({ getRunDoctor, downloadDiagnosticBundle }));

// Deep review 2026-11-18, F1: what happened in a run and what to do next were only in the operator's audit scripts.
describe('the run doctor', () => {
  it('says what to do, the defect that keeps coming back, and downloads the bundle only when asked', async () => {
    getRunDoctor.mockResolvedValue({
      status: 'failed', current_stage: 'failed', last_record_minutes_ago: 3, stage_order: ['technical_lead'],
      stage_switches: 4, stages: [{ stage: 'technical_lead', wall_seconds: 600, model_calls: 3, tool_failures: 0, share: 0.5 }],
      defects: { raised: 3, fixed: 0, left_open: 1, reverted: 2, closed: 0, deferred: 0,
        repeated: [{ id: 'd1', rounds: 3, ending: 'left open', description: 'GET /notes answers 500', first_stage: 'test_round_1' }] },
      resource_refusals: 1, model_errors: 0, restarts: 0, rewinds: 0,
      suggestions: [{ action: 'rewind', stage: 'technical_lead', said: 'Rewind to the sprint\'s planning.' }],
    });
    render(<RunDoctor runId="run-1" />);

    expect((await screen.findAllByTestId('doctor-suggestion'))[0].textContent).toContain('Rewind to the sprint');
    expect(screen.getByText(/GET \/notes answers 500/)).toBeTruthy();
    expect(downloadDiagnosticBundle).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('diagnostic-bundle'));
    expect(downloadDiagnosticBundle).toHaveBeenCalledWith('run-1');
  });
});
