import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { RunDashboard } from './RunDashboard';
import { FeedbackProvider } from '../components/Feedback';

const { run } = vi.hoisted(() => ({ run: {
  run_id: 'run-1', thread_id: 't', status: 'running', current_stage: 'defect_fix_2_3', stage_meaning: null,
  created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T01:00:00Z', stages: [], artifacts: [], reviews: [],
  remediation: null, error: null, auto_approve: false, completion_gaps: [], blocking_gaps: [], gate_deadline: null,
  approval_timeout_minutes: null, non_deliverable: '', delivery_mode: 'fast', use_frontier_model: false,
  max_run_tokens: null, max_run_cost_usd: null, cost: null,
  run_name: null, internet_lookups: null, model_pinned: false, model_last: { model: 'model-a', endpoint: '127.0.0.1:8888' },
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
    getWorkspaceFiles: { files: [{ path: 'src/app.py', size: 12 }], truncated: false, since: 'the scaffold', changed: [] },
    getWorkspaceFile: { path: 'src/app.py', content: 'print("hi")\n' },
    getSteering: [],
    getPendingReview: { pending: false },
    getPendingApproval: { pending: false },
    getHowToRun: ['cd app', 'npm install', 'sh start.sh'],
    resumeWithDirection: { message: 'ok' },
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
const theRunAsItStarts = { ...run };
afterEach(() => {
  vi.unstubAllGlobals();
  Object.assign(run, theRunAsItStarts);
});

describe('the run page', () => {
  it('says what may mean the product does not work apart from the notes', async () => {
    Object.assign(run, { status: 'completed', current_stage: 'complete', completion_gaps: ['AC-2 ships deferred', 'Code the product does not run: x'], blocking_gaps: ['AC-2 ships deferred'] });
    render(
      <MemoryRouter initialEntries={['/runs/run-1']}>
        <FeedbackProvider>
          <Routes><Route path="/runs/:runId" element={<RunDashboard />} /></Routes>
        </FeedbackProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText('Completed with 1 gap that may mean it does not work')).toBeTruthy();
    expect(screen.getByText('1 note on what it did not prove')).toBeTruthy();
    expect(screen.queryByText(/gaps? it did not prove/)).toBeNull();
  });

  it('names the criteria a delivered run cut, and says delivered when it cut none', async () => {
    Object.assign(run, { status: 'completed', current_stage: 'complete', verdict: 'delivered_with_cuts',
      scope_cuts: ['AC-4 ships deferred, unproven by the suite: the export view'],
      completion_gaps: ['AC-4 ships deferred, unproven by the suite: the export view'], blocking_gaps: [] });
    renderPage();
    expect(await screen.findByText('Delivered with cuts')).toBeTruthy();
    expect(screen.getByTestId('scope-cuts').textContent).toContain('the export view');
  });

  it('offers the product itself and how to run it once the run is complete', async () => {
    Object.assign(run, { status: 'completed', current_stage: 'complete', verdict: 'delivered', scope_cuts: [] });
    renderPage();
    expect(await screen.findByTestId('download-product')).toBeTruthy();
    expect((await screen.findByTestId('how-to-run')).textContent).toContain('sh start.sh');
  });

  // Deep review 2026-11-18, F4a: the product download showed only on a completed run.
  it('offers a stopped run\'s best attempt, said with the criteria it passed', async () => {
    known.getProductSummary = vi.fn(async () => ({ version: 'best', criteria_passed: 14, criteria_total: 18,
      tests_passed: null, tests_total: null, from_an_earlier_commit: false })) as never;
    Object.assign(run, { status: 'failed', current_stage: 'failed', error: 'Stopped: the last attempts did not beat the best' });
    renderPage();
    expect((await screen.findByTestId('download-best-attempt')).textContent).toContain('Download best attempt (14 of 18 criteria passed)');
    expect(screen.queryByTestId('download-product')).toBeNull();
  });

  it('resumes a failed run with the direction typed for it', async () => {
    Object.assign(run, { status: 'failed', current_stage: 'failed', error: 'The model server did not answer' });
    renderPage();
    await userEvent.click(await screen.findByText('Resume with a direction'));
    await userEvent.type(screen.getByLabelText('The direction to resume with'), 'keep the store in one file');
    await userEvent.click(screen.getByTestId('resume-with-direction'));
    await waitFor(() => expect(known.resumeWithDirection).toHaveBeenCalledWith('run-1', 'keep the store in one file'));
  });

  // Plan WS.3: a paused run keeps a note for when it resumes; the box used to be hidden while paused.
  it('offers steering on a paused run', async () => {
    Object.assign(run, { status: 'paused', current_stage: 'defect_fix_2_3' });
    renderPage();
    expect(await screen.findByText('Steer this run…')).toBeTruthy();
  });

  // Plan WL.3: the run record shows what the agents could look up on the internet, as the run was started.
  it('shows the internet lookups the run was started with', async () => {
    Object.assign(run, { internet_lookups: 'off' });
    renderPage();
    expect((await screen.findByTestId('internet-lookups')).textContent).toBe('Internet lookupsOff');
  });

  it('says delivered for a completed run with no cut and nothing blocking', async () => {
    Object.assign(run, { status: 'completed', current_stage: 'complete', verdict: 'delivered', scope_cuts: [] });
    renderPage();
    expect(await screen.findByTestId('delivered')).toBeTruthy();
    expect(screen.queryByText('Delivered with cuts')).toBeNull();
  });

  it('leaves the time the run spent paused out of the time it took, and says how much', async () => {
    // Created 00:00, ended 01:00, paused for 25 minutes of that hour.
    Object.assign(run, { status: 'completed', current_stage: 'complete', paused_seconds: 1500 });
    renderPage();
    expect(await screen.findByText('35m 0s')).toBeTruthy();
    expect(screen.getByText('25m 0s stopped or waiting, not counted')).toBeTruthy();
  });

  it('calls a run with only notes neither gapped nor proved everything', async () => {
    Object.assign(run, { status: 'completed', current_stage: 'complete', completion_gaps: ['Code the product does not run: x'], blocking_gaps: [] });
    render(
      <MemoryRouter initialEntries={['/runs/run-1']}>
        <FeedbackProvider>
          <Routes><Route path="/runs/:runId" element={<RunDashboard />} /></Routes>
        </FeedbackProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText('1 note on what it did not prove')).toBeTruthy();
    expect(screen.queryByText(/may mean it does not work/)).toBeNull();
  });

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

describe('the workspace tab', () => {
  it('opens on the file the address names, so a link shows the same code', async () => {
    render(
      <MemoryRouter initialEntries={['/runs/run-1?view=workspace&file=src%2Fapp.py']}>
        <FeedbackProvider>
          <Routes><Route path="/runs/:runId" element={<RunDashboard />} /></Routes>
        </FeedbackProvider>
      </MemoryRouter>,
    );

    expect((await screen.findByRole('tab', { name: 'Workspace' })).getAttribute('aria-selected')).toBe('true');
    expect((await screen.findByLabelText('The text of src/app.py')).textContent).toContain('print("hi")');
    expect(known.getWorkspaceFile).toHaveBeenCalledWith('run-1', 'src/app.py');
  });

  // Plan WS.2: a write in the feed opens its file there, on its change since the last accepted sprint.
  it('opens a file written in the feed on its change', async () => {
    const at = (n: number) => ({ run_id: 'run-1', event_id: `w${n}`, sequence: n, timestamp: `2026-10-19T00:10:0${n}Z`, stage: 'specialist_backend_0' });
    known.getLogs.mockResolvedValueOnce({ total: 2, logs: [
      { ...at(1), event_type: 'tool_call', message: 'write_artifact: {"relative_path": "src/app.py"}', metadata: { tool: 'write_artifact' } },
      { ...at(2), event_type: 'tool_result', message: '{"path": "src/app.py"}', metadata: {} },
    ] });
    known.getWorkspaceFileDiff = vi.fn(async () => ({ path: 'src/app.py', diff: '--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-a\n+print("hi")\n', truncated: false, since: 'the scaffold' }));
    renderPage();

    await userEvent.click(await screen.findByRole('link', { name: 'src/app.py' }));

    expect((await screen.findByRole('tab', { name: 'Workspace' })).getAttribute('aria-selected')).toBe('true');
    await waitFor(() => expect(known.getWorkspaceFileDiff).toHaveBeenCalledWith('run-1', 'src/app.py'));
    expect((await screen.findByRole('switch', { name: /Changed since the scaffold/ }) as HTMLInputElement).checked).toBe(true);
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
