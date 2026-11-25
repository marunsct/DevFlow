import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkspaceShell } from './WorkspaceShell';
import type { EditorViewProps } from './Editor';
import { FeedbackProvider } from '../Feedback';
import { closeFile, matchPaths, NONE_OPEN, openFile } from './tabs';

const { api } = vi.hoisted(() => ({ api: {} as Record<string, ReturnType<typeof vi.fn>> }));
vi.mock('../../api', () => new Proxy(api, {
  get: (target, name) => {
    if (typeof name !== 'string' || name === 'then') return undefined;
    target[name] ??= vi.fn(async () => ({}));
    return target[name];
  },
}));
// Monaco does not run in a test's page; at its edge it shows what it was given.
vi.mock('./monaco', () => ({
  default: ({ path, text, diff, line }: EditorViewProps) => (
    <output aria-label={`editor of ${path}`} data-now={text} data-base={diff?.base ?? ''} data-line={line ?? ''} />
  ),
}));

const TREE = {
  files: [
    { path: 'README.md', size: 14 },
    { path: 'src/app.py', size: 43 },
    { path: 'src/store.py', size: 20 },
    { path: 'src/web/page.tsx', size: 30 },
  ],
  truncated: false,
  since: 'sprint 1',
  changed: ['src/app.py'],
};

beforeEach(() => {
  localStorage.removeItem('workspaceLayout');
  api.getWorkspaceFiles = vi.fn(async () => TREE);
  api.getWorkspaceFile = vi.fn(async (_run: string, path: string) => ({ path, content: `text of ${path}`, hash: 'h' }));
});
afterEach(() => vi.clearAllMocks());

const shell = () => render(
  <FeedbackProvider>
    <WorkspaceShell runId="r" run={null} logs={[]} />
  </FeedbackProvider>,
);
const tabs = () => within(screen.getByRole('tablist', { name: 'Open files' })).getAllByRole('tab');
const names = () => tabs().map((tab) => tab.textContent);
const shown = () => tabs().find((tab) => tab.getAttribute('aria-selected') === 'true')?.textContent;

describe('the workspace window (plan UX.5)', () => {
  it('keeps a file opened on purpose when another is opened, and lets the next file replace a previewed one', async () => {
    shell();
    await userEvent.dblClick(await screen.findByText('README.md'));
    await userEvent.click(screen.getByText('app.py'));
    const both = names();

    await userEvent.click(screen.getByText('store.py'));

    expect(both).toEqual(['README.md', 'app.py']);
    expect(names()).toEqual(['README.md', 'store.py']);
    expect((await screen.findByLabelText('editor of src/store.py')).dataset.now).toBe('text of src/store.py');
  });

  it('shows the neighbour of the file closed while it was shown', async () => {
    shell();
    for (const name of ['README.md', 'app.py', 'store.py']) await userEvent.dblClick(await screen.findByText(name));
    await userEvent.click(tabs()[1]);

    await userEvent.click(screen.getByRole('button', { name: 'Close src/app.py' }));

    expect(names()).toEqual(['README.md', 'store.py']);
    expect(shown()).toBe('store.py');
  });

  it('goes to a file by part of its path, from the tree already loaded', async () => {
    shell();
    await screen.findByText('README.md');

    await userEvent.keyboard('{Control>}p{/Control}');
    await userEvent.type(screen.getByRole('combobox', { name: "Part of the file's path" }), 'pag');
    const offered = screen.getAllByRole('option').map((option) => option.textContent);
    await userEvent.keyboard('{Enter}');

    expect(offered).toEqual(['page.tsxsrc/web']);
    expect(shown()).toBe('page.tsx');
    expect(api.getWorkspaceFiles).toHaveBeenCalledTimes(1);
  });

  it('shows a file beside its text at the last accepted sprint', async () => {
    api.getWorkspaceFileAccepted = vi.fn(async () => ({ path: 'src/app.py', content: 'the sprint 1 text', hash: 'b', since: 'sprint 1', exists: true }));
    shell();
    await userEvent.dblClick(await screen.findByText('app.py'));

    await userEvent.click(await screen.findByRole('switch', { name: /Compare with sprint 1/ }));

    const editor = await screen.findByLabelText('editor of src/app.py');
    await waitFor(() => expect(editor.dataset.base).toBe('the sprint 1 text'));
    expect(editor.dataset.now).toBe('text of src/app.py');
    expect(api.getWorkspaceFileAccepted).toHaveBeenCalledWith('r', 'src/app.py');
  });

  it('opens a search hit at its line', async () => {
    api.searchWorkspaceFiles = vi.fn(async () => ({
      query: 'greet', truncated: false, timed_out: false, files_searched: 4,
      hits: [{ path: 'src/store.py', line: 12, column: 5, text: 'def greet():' }],
    }));
    shell();
    await screen.findByText('README.md');
    await userEvent.click(screen.getByRole('button', { name: 'Search the files' }));

    await userEvent.type(screen.getByLabelText('Search the files', { selector: 'input' }), 'greet');
    await userEvent.click(await screen.findByRole('button', { name: /12\s*def greet/ }));

    expect(shown()).toBe('store.py');
    expect((await screen.findByLabelText('editor of src/store.py')).dataset.line).toBe('12');
    expect(api.searchWorkspaceFiles).toHaveBeenCalledWith('r', 'greet', false);
  });

  it('puts the preview beside the code on asking', async () => {
    api.getPreview = vi.fn(async () => ({ enabled: true, state: 'none', idle_minutes: 15 }));
    shell();
    await screen.findByText('README.md');

    await userEvent.click(screen.getByRole('button', { name: 'Preview beside the code' }));

    expect(await screen.findByRole('region', { name: 'Preview' })).toBeTruthy();
    expect(screen.getByRole('navigation', { name: "The workspace's files" })).toBeTruthy();
  });
});

describe('the open files', () => {
  it('closing the last file shown leaves the one before it shown', () => {
    const three = ['a', 'b', 'c'].reduce((state, path) => openFile(state, path, true), NONE_OPEN);

    expect(closeFile(three, 'c').active).toBe('b');
    expect(closeFile(closeFile(three, 'c'), 'b').active).toBe('a');
    expect(closeFile(closeFile(closeFile(three, 'c'), 'b'), 'a')).toEqual(NONE_OPEN);
  });

  it("finds a path by its letters in order, the file's own name first", () => {
    expect(matchPaths(['src/apple/x.ts', 'src/app.py', 'docs/a-p-p.md'], 'app')).toEqual(['src/app.py', 'src/apple/x.ts', 'docs/a-p-p.md']);
    expect(matchPaths(['src/app.py'], 'zz')).toEqual([]);
  });
});
