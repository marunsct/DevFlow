import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { Home } from './Home';

const { mocks } = vi.hoisted(() => ({
  mocks: {
    createRun: vi.fn(async () => ({ run_id: 'run-new', status: 'created' })),
    startRun: vi.fn(async () => ({})),
    deleteRun: vi.fn(async () => ({})),
    uploadCodebase: vi.fn(async () => ({})),
    pullRequestDeliveryOn: vi.fn(async () => false),
    getOperatorHealth: vi.fn(async () => ({ runs: { waiting: [] as unknown[] } })),
    getOutcomes: vi.fn(async () => ({ runs: [], forecast: {} })),
    getFrontierStatus: vi.fn(async () => ({ configured: true, active: true, model: 'claude-x', provider: 'anthropic', problem: null as string | null })),
    previewBrief: vi.fn(async () => ({ criteria: [{ id: 'AC-1', text: 'Add a note' }, { id: 'AC-2', text: 'Delete a note' }], from_brief: true })),
    api: { get: vi.fn(async () => ({ data: {} })), patch: vi.fn(async () => ({ data: {} })) },
  },
}));
vi.mock('../api', () => mocks);

const show = () => render(<MemoryRouter><Home /></MemoryRouter>);

beforeEach(() => {
  Object.values(mocks).forEach((mock) => typeof mock === 'function' && mock.mockClear());
});

describe('starting a build', () => {
  it('takes a written brief, shows what it will be held to, and sends it as the brief', async () => {
    show();
    const start = screen.getByRole('button', { name: /Start Workflow Run/ }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);

    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note\n- Delete a note');
    expect(start.disabled).toBe(false);
    expect(await screen.findByText('Add a note', {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getAllByText('not yet')).toHaveLength(2);

    await userEvent.click(start);
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const sent = (mocks.createRun.mock.calls[0] as unknown as [File[]])[0];
    expect(sent.map((file) => file.name)).toEqual(['brief.md']);
  });

  it('starts the run under the name typed for it', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    await userEvent.type(screen.getByLabelText(/Run name/), 'second try');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    expect(JSON.stringify(mocks.startRun.mock.calls.at(-1))).toContain('"name":"second try"');
  });

  // Plan WL.3: the user decides per run what the agents may look up on the internet; "always" unless changed (owner 2026-11-23).
  it('starts the run with the internet lookups chosen for it, always unless changed', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    expect((screen.getByLabelText(/Internet lookups/) as HTMLSelectElement).value).toBe('always');
    await userEvent.selectOptions(screen.getByLabelText(/Internet lookups/), 'off');
    expect(screen.getByTestId('internet-lookups-help').textContent).toMatch(/registries and official\s+documentation/);
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const payload = (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];
    expect(payload.internet_lookups).toBe('off');
  });

  // Plan HK.10: product research only with the owner's consent for this run - unticked each time, and never under "off".
  it('sends consent to product research only when ticked for this run', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    const consent = screen.getByLabelText(/Product research for this run/) as HTMLInputElement;
    expect(consent.checked).toBe(false);
    await userEvent.click(consent);
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const payload = (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];
    expect(payload.product_research).toBe(true);
  });

  it('sends no consent to product research with internet lookups off, even once ticked', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    await userEvent.click(screen.getByLabelText(/Product research for this run/));
    await userEvent.selectOptions(screen.getByLabelText(/Internet lookups/), 'off');
    expect((screen.getByLabelText(/Product research for this run/) as HTMLInputElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const payload = (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];
    expect(payload.product_research).toBe(false);
  });

  it('starts a run from an uploaded codebase with that upload named as its source', async () => {
    mocks.uploadCodebase.mockResolvedValueOnce({ upload_id: 'app_1a2b3c4d.zip' } as any);
    const { container } = show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    const input = container.querySelector('#codebase-upload') as HTMLInputElement;
    await userEvent.upload(input, new File(['zip'], 'app.zip', { type: 'application/zip' }));
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const payload = (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];
    expect(payload.source).toEqual({ type: 'archive', upload_id: 'app_1a2b3c4d.zip' });
  });

  // Deep review 2026-11-18, F4a: the API took a Git source with a token, the form sent only archives and runs.
  it('starts a run from a Git repository with its branch and token as the source', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    await userEvent.type(screen.getByLabelText(/Or clone a Git repository/), 'https://example.com/team/app.git');
    await userEvent.type(screen.getByLabelText(/Branch or tag/), 'release');
    await userEvent.type(screen.getByLabelText(/Access token/), 'secret-123');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const payload = (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];
    expect(payload.source).toEqual({ type: 'git', url: 'https://example.com/team/app.git', ref: 'release', token: 'secret-123' });
    expect(mocks.uploadCodebase).not.toHaveBeenCalled();
  });

  // Plan WS.7: a run seeded from a repository delivers its change as a pull request with a token the owner gives.
  it('offers no pull-request token while pull-request delivery is off', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Or clone a Git repository/), 'https://example.com/team/app.git');
    await waitFor(() => expect(mocks.pullRequestDeliveryOn).toHaveBeenCalled());
    expect(screen.queryByLabelText(/Token to open a pull request/)).toBeNull();
  });

  it('sends the pull-request token with the Git source and keeps it nowhere after the start', async () => {
    mocks.pullRequestDeliveryOn.mockResolvedValueOnce(true);
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    await userEvent.type(screen.getByLabelText(/Or clone a Git repository/), 'https://example.com/team/app.git');
    const field = (await screen.findByLabelText(/Token to open a pull request/)) as HTMLInputElement;
    expect(field.type).toBe('password');
    await userEvent.type(field, 'pr-secret-456');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const payload = (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];
    expect(payload.source).toEqual({ type: 'git', url: 'https://example.com/team/app.git', delivery_token: 'pr-secret-456' });
    expect((screen.getByLabelText(/Token to open a pull request/) as HTMLInputElement).value).toBe('');
    const stored = [localStorage, sessionStorage].flatMap((store) => Object.keys(store).map((key) => store.getItem(key)));
    expect(stored.filter((value) => value?.includes('pr-secret-456'))).toEqual([]);
  });

  it('logs no token when the run cannot start', async () => {
    mocks.pullRequestDeliveryOn.mockResolvedValueOnce(true);
    (mocks.startRun as any).mockImplementationOnce(async (_id: string, body: unknown) => {
      throw Object.assign(new Error('the worker is down'), { config: { data: JSON.stringify(body) } });
    });
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    await userEvent.type(screen.getByLabelText(/Or clone a Git repository/), 'https://example.com/team/app.git');
    await userEvent.type(await screen.findByLabelText(/Token to open a pull request/), 'pr-secret-456');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    expect(await screen.findByText('the worker is down')).toBeTruthy();
    expect(JSON.stringify(logged.mock.calls, (_key, value) => (value instanceof Error ? { ...value, message: value.message } : value)))
      .not.toContain('pr-secret-456');
    expect((screen.getByLabelText(/Token to open a pull request/) as HTMLInputElement).value).toBe('');
    logged.mockRestore();
  });

  it('refuses to start from both an archive and a Git repository', async () => {
    const { container } = show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    await userEvent.upload(container.querySelector('#codebase-upload') as HTMLInputElement, new File(['zip'], 'app.zip', { type: 'application/zip' }));
    await userEvent.type(screen.getByLabelText(/Or clone a Git repository/), 'https://example.com/team/app.git');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    expect(await screen.findByText(/not both/)).toBeTruthy();
    expect(mocks.createRun).not.toHaveBeenCalled();
  });

  it('deletes the run it created when the run cannot start', async () => {
    mocks.startRun.mockRejectedValueOnce(new Error('the worker is down'));
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), 'A brief');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));

    await waitFor(() => expect(mocks.deleteRun).toHaveBeenCalledWith('run-new'));
    expect(await screen.findByText('the worker is down')).toBeTruthy();
  });
});

// Deep review 2026-11-18, F5: a run that waited for a worker said nothing of the runs ahead of it.
describe('runs waiting for a worker', () => {
  it('lists each waiting run in its place', async () => {
    mocks.getOperatorHealth.mockResolvedValueOnce({ runs: { waiting: [
      { run_id: 'run-aaaaaaaaaaaa1', name: 'first', since: '', minutes: 20, position: 1 },
      { run_id: 'run-bbbbbbbbbbbb2', name: '', since: '', minutes: 5, position: 2 },
    ] } });
    show();
    const queue = await screen.findByTestId('queue');
    expect(queue.textContent).toContain('2 runs wait for a worker');
    expect(Array.from(queue.querySelectorAll('li')).map((li) => li.textContent)).toEqual(
      ['first, waiting 20 min', 'run-bbbbbbbb, waiting 5 min']);
  });
});

describe('a server that cannot run commands', () => {
  it('says so and does not offer to start (LR.32)', async () => {
    (mocks.api.get as any).mockImplementation(async (path: string) => (path === '/health/commands'
      ? { data: { ready: false, reason: 'Command execution is off.' } } : { data: {} }) as any);
    show();
    expect((await screen.findByTestId('commands-off')).textContent).toContain('Command execution is off.');
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    expect((screen.getByRole('button', { name: /Start Workflow Run/ }) as HTMLButtonElement).disabled).toBe(true);
    (mocks.api.get as any).mockImplementation(async () => ({ data: {} }));
  });
});

describe('a change to a finished product', () => {
  it('starts from that run\'s product when opened for a change', async () => {
    render(<MemoryRouter initialEntries={['/?changeOf=run-old']}><Home /></MemoryRouter>);
    expect(screen.getByTestId('change-of').textContent).toContain('run-old');
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a tag to a note');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const payload = (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];
    expect(payload.source).toEqual({ type: 'run', run_id: 'run-old' });
  });
});

describe('a first run that stops for a person', () => {
  it('offers to tell this browser when the run needs its owner, and asks only when starting', async () => {
    const asked = vi.fn(async () => 'granted');
    vi.stubGlobal('Notification', Object.assign(function Notification() {}, { permission: 'default', requestPermission: asked }));
    show();
    await userEvent.click(screen.getByText('Review the key stages'));
    const box = screen.getByLabelText(/Tell me in this browser/) as HTMLInputElement;
    expect(box.checked).toBe(true);
    expect(asked).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/Write the brief/), '## Features\n- Add a note');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(asked).toHaveBeenCalled());
    vi.unstubAllGlobals();
  });
});

describe('the frontier model', () => {
  it('says it is ready when ticked', async () => {
    show();
    expect(await screen.findByText('Ready: claude-x on anthropic answers.')).toBeTruthy();
  });

  it('blocks the start with the reason when it is configured and not answering', async () => {
    mocks.getFrontierStatus.mockResolvedValue({ configured: true, active: false, model: 'claude-x', provider: 'anthropic', problem: 'The frontier model claude-x on anthropic could not be reached.' });
    show();
    expect(await screen.findByText(/could not be reached\./)).toBeTruthy();

    await userEvent.type(screen.getByLabelText(/Write the brief/), 'A brief');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));

    expect(mocks.createRun).not.toHaveBeenCalled();
    expect(screen.getAllByText(/could not be reached\./).length).toBeGreaterThan(1);
  });

  it('starts unticked when no frontier model is configured, and says why when ticked', async () => {
    mocks.getFrontierStatus.mockResolvedValue({ configured: false, active: false, model: '', provider: '', problem: 'No frontier model is configured.' });
    show();
    // Looked up each time: the page renders its checkboxes afresh.
    const box = () => screen.getByLabelText(/Use the frontier model/) as HTMLInputElement;
    await waitFor(() => expect(box().checked).toBe(false));

    await userEvent.click(box());
    expect(await screen.findByText(/No frontier model is configured\./)).toBeTruthy();
  });
});

describe('your involvement', () => {
  const sent = () => (mocks.startRun.mock.calls.at(-1) as unknown as [string, Record<string, any>])[1];

  it('hands-off skips every review and approves every action', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), 'A brief');
    await userEvent.click(screen.getByRole('radio', { name: /Hands-off/ }));
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    expect(sent().auto_approve).toBe(true);
    expect(Object.values(sent().review_policy).every((on) => on === false)).toBe(true);
  });

  it('approving every step asks before each action and keeps the reviews', async () => {
    show();
    await userEvent.type(screen.getByLabelText(/Write the brief/), 'A brief');
    await userEvent.click(screen.getByRole('radio', { name: /Approve every step/ }));
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    expect(sent().auto_approve).toBe(false);
    expect(sent().review_policy.release).toBe(true);
  });
});

