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

    await userEvent.type(screen.getByLabelText(/Or write the brief here/), '## Features\n- Add a note\n- Delete a note');
    expect(start.disabled).toBe(false);
    expect(await screen.findByText('Add a note', {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getAllByText('not yet')).toHaveLength(2);

    await userEvent.click(start);
    await waitFor(() => expect(mocks.startRun).toHaveBeenCalled());
    const sent = (mocks.createRun.mock.calls[0] as unknown as [File[]])[0];
    expect(sent.map((file) => file.name)).toEqual(['brief.md']);
  });

  it('deletes the run it created when the run cannot start', async () => {
    mocks.startRun.mockRejectedValueOnce(new Error('the worker is down'));
    show();
    await userEvent.type(screen.getByLabelText(/Or write the brief here/), 'A brief');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));

    await waitFor(() => expect(mocks.deleteRun).toHaveBeenCalledWith('run-new'));
    expect(await screen.findByText('the worker is down')).toBeTruthy();
  });
});

describe('the frontier model', () => {
  it('says it is ready when ticked', async () => {
    show();
    expect(await screen.findByText('Ready: claude-x on anthropic answers.')).toBeTruthy();
  });

  it('blocks the start with the reason when it is not configured or not answering', async () => {
    mocks.getFrontierStatus.mockResolvedValue({ configured: false, active: false, model: '', provider: '', problem: 'No frontier model is configured.' });
    show();
    expect(await screen.findByText(/No frontier model is configured\./)).toBeTruthy();

    await userEvent.type(screen.getByLabelText(/Or write the brief here/), 'A brief');
    await userEvent.click(screen.getByRole('button', { name: /Start Workflow Run/ }));

    expect(mocks.createRun).not.toHaveBeenCalled();
    expect(screen.getAllByText(/No frontier model is configured\./).length).toBeGreaterThan(1);
  });
});
