import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkspaceShell } from './WorkspaceShell';
import type { EditorViewProps } from './Editor';
import { FeedbackProvider } from '../Feedback';
import type { RunStatusResponse } from '../../types';

const { api } = vi.hoisted(() => ({ api: {} as Record<string, ReturnType<typeof vi.fn>> }));
vi.mock('../../api', () => new Proxy(api, {
  get: (target, name) => {
    if (typeof name !== 'string' || name === 'then') return undefined;
    target[name] ??= vi.fn(async () => ({}));
    return target[name];
  },
}));
// Monaco does not run in a test's page; at its edge it is a text area that passes on what is typed, or the two
// versions it was given to compare.
vi.mock('./monaco', () => ({
  default: ({ path, text, diff, editable, onEdit }: EditorViewProps) => (diff
    ? <output aria-label={`the change to ${path}`} data-now={text} data-base={diff.base} />
    : <textarea aria-label={`editor of ${path}`} value={text} readOnly={!editable} data-editable={String(!!editable)}
      onChange={(event) => onEdit?.(event.target.value)} />),
}));

const TREE = { files: [{ path: 'README.md', size: 14 }], truncated: false, since: null, changed: [] };
const SESSION = {
  holder: 'alice', yours: true, opened_at: null, heartbeat_at: null, lease_seconds: 120, lapsed: false,
  base_commit: 'c', files: [], baseline_tests: [],
};
const STOPPED = ['paused', 'waiting_for_review'];

function turn(status: string, session: typeof SESSION | null, enabled = true) {
  api.getEditSession = vi.fn(async () => ({ enabled, run_status: status, editable_statuses: STOPPED, session }));
}

beforeEach(() => {
  localStorage.removeItem('workspaceLayout');
  api.getWorkspaceFiles = vi.fn(async () => TREE);
  api.getWorkspaceFile = vi.fn(async (_run: string, path: string) => ({ path, content: `text of ${path}`, hash: 'h1' }));
  api.pauseRun = vi.fn(async () => ({ message: 'pausing' }));
  api.openEditSession = vi.fn(async () => ({ session: SESSION }));
  api.discardEditSession = vi.fn(async () => ({ restored: [] }));
});
afterEach(() => vi.clearAllMocks());

const shell = (status: string) => render(
  <FeedbackProvider>
    <WorkspaceShell runId="r" run={{ status, current_stage: 'specialist_backend_0' } as unknown as RunStatusResponse} logs={[]}
      initialFile="README.md" />
  </FeedbackProvider>,
);
const status = () => screen.getByLabelText('Status');

describe('write mode (plan UX.14)', () => {
  it('is read-only while the run is going, and taking the turn pauses it at the end of its stage', async () => {
    turn('running', null);
    shell('running');
    const editor = await screen.findByLabelText('editor of README.md');

    await userEvent.click(await within(status()).findByRole('button', { name: 'Take the turn' }));

    expect(editor.dataset.editable).toBe('false');
    expect(api.pauseRun).toHaveBeenCalledWith('r', true);
    expect(api.openEditSession).not.toHaveBeenCalled();
    expect(await within(status()).findByText(/Pausing at the end of the stage/)).toBeTruthy();
  });

  it('offers no writing at all with co-development off', async () => {
    turn('paused', null, false);
    shell('paused');
    const editor = await screen.findByLabelText('editor of README.md');
    await waitFor(() => expect(api.getEditSession).toHaveBeenCalled());

    expect(editor.dataset.editable).toBe('false');
    expect(within(status()).queryByRole('button', { name: 'Take the turn' })).toBeNull();
    expect(within(status()).getByText('Read-only')).toBeTruthy();
  });

  it('marks a changed file unsaved and saves it with the hash it was loaded at', async () => {
    turn('paused', SESSION);
    api.saveWorkspaceFile = vi.fn(async () => ({ path: 'README.md', hash: 'h2' }));
    shell('paused');
    const editor = await screen.findByLabelText('editor of README.md');
    await waitFor(() => expect(editor.dataset.editable).toBe('true'));

    await userEvent.type(editor, '!');
    const marked = screen.queryByRole('img', { name: 'unsaved changes' });
    await userEvent.keyboard('{Control>}s{/Control}');

    expect(marked).toBeTruthy();
    expect(api.saveWorkspaceFile).toHaveBeenCalledWith('r', 'README.md', 'text of README.md!', 'h1', false);
    await waitFor(() => expect(screen.queryByRole('img', { name: 'unsaved changes' })).toBeNull());
  });

  it('shows both versions when the file moved on since it was opened, and keeps the person\'s text', async () => {
    turn('paused', SESSION);
    api.saveWorkspaceFile = vi.fn(async () => {
      throw { response: { status: 409, data: { detail: { message: 'README.md changed', content: 'written since', hash: 'h3' } } } };
    });
    shell('paused');
    const editor = await screen.findByLabelText('editor of README.md');
    await waitFor(() => expect(editor.dataset.editable).toBe('true'));
    await userEvent.type(editor, '!');

    await userEvent.click(screen.getByRole('button', { name: /^Save/ }));

    const both = await screen.findByLabelText('the change to README.md');
    expect(both.dataset.base).toBe('written since');
    expect(both.dataset.now).toBe('text of README.md!');
    await userEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Save mine over it' }));
    expect(api.saveWorkspaceFile).toHaveBeenLastCalledWith('r', 'README.md', 'text of README.md!', 'h3', false);
  });

  it('asks before discarding, and discards only on yes', async () => {
    turn('paused', SESSION);
    shell('paused');
    const discard = await within(status()).findByRole('button', { name: 'Discard my changes' });

    await userEvent.click(discard);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    const afterNo = api.discardEditSession.mock.calls.length;
    await userEvent.click(discard);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Discard' }));

    expect(afterNo).toBe(0);
    await waitFor(() => expect(api.discardEditSession).toHaveBeenCalledWith('r'));
  });

  it("says whose turn it is when another person holds it, and stays read-only", async () => {
    turn('paused', { ...SESSION, holder: 'bob', yours: false });
    shell('paused');
    const editor = await screen.findByLabelText('editor of README.md');

    expect(await within(status()).findByText("bob's turn")).toBeTruthy();
    expect(editor.dataset.editable).toBe('false');
  });
});
