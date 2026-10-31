import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { RunDashboard } from './RunDashboard';
import { FeedbackProvider } from '../components/Feedback';

const { run } = vi.hoisted(() => ({ run: {
  run_id: 'run-1', thread_id: 't', status: 'running', current_stage: 'defect_fix_2_3', stage_meaning: null,
  created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T01:00:00Z', stages: [], artifacts: [], reviews: [],
  remediation: null, error: null, auto_approve: false, completion_gaps: [], gate_deadline: null,
  approval_timeout_minutes: null, non_deliverable: '', delivery_mode: 'fast', use_frontier_model: false,
  max_run_tokens: null, max_run_cost_usd: null, cost: null,
  run_name: null, model_pinned: false, model_last: { model: 'model-a', endpoint: '127.0.0.1:8888' },
} }));

const { known } = vi.hoisted(() => ({ known: {} as Record<string, ReturnType<typeof vi.fn>> }));
vi.mock('../api', () => {
  const answers: Record<string, unknown> = {
    getRun: run,
    getLogs: { logs: [], total: 0 },
    getStreamTicket: 'ticket',
    getWizard: null,
    getOutcomes: { runs: [], forecast: {} },
    getSprints: { sprints: [] },
    fetchArtifactContent: null,
    getChanges: { commits: [] },
    getSteering: [],
    getPendingReview: { pending: false },
    getPendingApproval: { pending: false },
  };
  for (const [name, answer] of Object.entries(answers)) known[name] = vi.fn(async () => answer);
  known.api = { get: vi.fn(async () => ({ data: {} })) } as never;
  // Anything else the page or its panels call answers with an empty object;
  // not `then` (the module would read as a promise), and the same function
  // every time it is asked for.
  return new Proxy(known, {
    get: (target, name) => {
      if (typeof name !== 'string' || name === 'then') return undefined;
      target[name] ??= vi.fn(async () => ({}));
      return target[name];
    },
  });
});

class FakeSocket {
  static last: FakeSocket | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    FakeSocket.last = this;
    setTimeout(() => this.onopen?.(), 0);
  }
  send() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', FakeSocket);
  for (const fn of Object.values(known)) if (typeof fn === 'function' && 'mockClear' in fn) fn.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe('the run page', () => {
  it('pages the log history while the stream is down, and not once the stream carries it', async () => {
    render(
      <MemoryRouter initialEntries={['/runs/run-1']}>
        <FeedbackProvider>
          <Routes><Route path="/runs/:runId" element={<RunDashboard />} /></Routes>
        </FeedbackProvider>
      </MemoryRouter>,
    );
    await screen.findByText('Fixing problem 4 (test round 2)');
    await waitFor(() => expect(FakeSocket.last?.onmessage).toBeTruthy());
    const pagedBefore = known.getLogs.mock.calls.length;
    const readBefore = known.getRun.mock.calls.length;
    expect(pagedBefore).toBe(1);

    const event = { event_id: 'e1', event_type: 'stage_change', run_id: 'run-1', timestamp: '2026-10-19T01:00:01Z', sequence: 1, stage: 'test_round_3', message: 'next' };
    FakeSocket.last!.onmessage!({ data: JSON.stringify({ event: 'message', data: JSON.stringify(event) }) });

    await waitFor(() => expect(known.getRun.mock.calls.length).toBeGreaterThan(readBefore), { timeout: 3000 });
    expect(known.getLogs.mock.calls.length).toBe(pagedBefore);
  });

  it('refreshes the run when events start coming from another stage, not only at a gate', async () => {
    // Measured live: the specialist consults run between two gates and send
    // agent events only; the activity moved on to the testing specialist while
    // the header and the progress panel still said the backend one.
    renderPage();
    await screen.findByText('Fixing problem 4 (test round 2)');
    await waitFor(() => expect(FakeSocket.last?.onmessage).toBeTruthy());
    send({ event_id: 'a1', event_type: 'tool_call', stage: 'consult_backend', sequence: 1 });
    await waitFor(() => expect(known.getRun.mock.calls.length).toBe(2), { timeout: 3000 });
    send({ event_id: 'a2', event_type: 'tool_result', stage: 'consult_backend', sequence: 2 });
    send({ event_id: 'a3', event_type: 'tool_call', stage: 'consult_testing', sequence: 3 });

    await waitFor(() => expect(known.getRun.mock.calls.length).toBe(3), { timeout: 3000 });
  });

  it('runs a refresh asked for while another is in flight once that one ends', async () => {
    renderPage();
    await screen.findByText('Fixing problem 4 (test round 2)');
    await waitFor(() => expect(FakeSocket.last?.onmessage).toBeTruthy());
    let finish: (value: unknown) => void = () => {};
    known.getRun.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    send({ event_id: 'b1', event_type: 'stage_change', stage: 'consult_ui_ux', sequence: 1 });
    await waitFor(() => expect(known.getRun.mock.calls.length).toBe(2), { timeout: 3000 });
    send({ event_id: 'b2', event_type: 'stage_change', stage: 'consult_database', sequence: 2 });
    await new Promise((resolve) => setTimeout(resolve, 900));
    finish(run);

    await waitFor(() => expect(known.getRun.mock.calls.length).toBe(3), { timeout: 3000 });
  });

  it('offers to keep a running run on its model, naming the model and its port, and sends the choice', async () => {
    renderPage();
    await screen.findByText('Fixing problem 4 (test round 2)');
    const toggle = await screen.findByRole('switch', { name: 'Keep this run on its model' });
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    expect(screen.getByText('(model-a @ 127.0.0.1:8888)')).toBeTruthy();

    toggle.click();

    await waitFor(() => expect(known.setModelPin).toHaveBeenCalledWith('run-1', true));
  });
});

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/runs/run-1']}>
      <FeedbackProvider>
        <Routes><Route path="/runs/:runId" element={<RunDashboard />} /></Routes>
      </FeedbackProvider>
    </MemoryRouter>,
  );
}

function send(event: Record<string, unknown>) {
  const entry = { run_id: 'run-1', timestamp: '2026-10-19T01:00:01Z', message: '', ...event };
  FakeSocket.last!.onmessage!({ data: JSON.stringify({ event: 'message', data: JSON.stringify(entry) }) });
}
