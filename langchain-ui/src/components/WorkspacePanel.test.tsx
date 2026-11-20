import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkspacePanel, RELOAD_AFTER_MS } from './WorkspacePanel';
import { highlight } from '../lib/highlight';
import { lastWriteSequence } from '../lib/activity';
import type { LogEntry } from '../types';

const api = vi.hoisted(() => ({
  getWorkspaceFiles: vi.fn(),
  getWorkspaceFile: vi.fn(),
  getWorkspaceFileDiff: vi.fn(),
}));
vi.mock('../api', () => api);

const TREE = {
  files: [
    { path: 'README.md', size: 14 },
    { path: 'src/app.py', size: 43 },
    { path: 'src/web/page.tsx', size: 30 },
  ],
  truncated: false,
  since: 'sprint 1',
  changed: ['src/app.py'],
};

const event = (over: Partial<LogEntry>): LogEntry => ({
  event_id: `e${over.sequence}`, event_type: 'log', message: '', metadata: {}, run_id: 'r', sequence: 0,
  stage: 'specialist_backend', timestamp: '2026-11-20T00:00:00Z', ...over,
});

beforeEach(() => {
  api.getWorkspaceFiles.mockResolvedValue(TREE);
  api.getWorkspaceFile.mockResolvedValue({ path: 'src/app.py', content: "def greet():\n    return 'hi'  # say it\n" });
  api.getWorkspaceFileDiff.mockResolvedValue({
    path: 'src/app.py', since: 'sprint 1', truncated: false,
    diff: "diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1,2 @@\n def greet():\n+    return 'hi'",
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('the workspace view', () => {
  it('shows the files as a tree whose folders fold, and marks what changed since the last accepted sprint', async () => {
    render(<WorkspacePanel runId="r" refreshKey="k" logs={[]} selected={null} onSelect={() => {}} />);

    expect(await screen.findByText('README.md')).toBeTruthy();
    expect(screen.getByText('app.py').closest('button')!.textContent).toContain('changed');
    expect(screen.queryByText('page.tsx')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'web' }));
    expect(screen.getByText('page.tsx')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'src' }));
    expect(screen.queryByText('app.py')).toBeNull();
  });

  it('opens a file chosen in the tree', async () => {
    const onSelect = vi.fn();
    render(<WorkspacePanel runId="r" refreshKey="k" logs={[]} selected={null} onSelect={onSelect} />);

    await userEvent.click(await screen.findByText('README.md'));

    expect(onSelect).toHaveBeenCalledWith('README.md');
  });

  it('shows the chosen file\'s text read-only, highlighted, and its change since the last accepted sprint on asking', async () => {
    render(<WorkspacePanel runId="r" refreshKey="k" logs={[]} selected="src/app.py" onSelect={() => {}} />);

    const code = await screen.findByLabelText('The text of src/app.py');
    expect(code.textContent).toContain("return 'hi'");
    expect(screen.getByText('def').className).toContain('text-primary');
    expect(screen.getByText('# say it').className).toContain('italic');
    expect(document.querySelector('textarea, [contenteditable="true"]')).toBeNull();

    await userEvent.click(screen.getByRole('switch', { name: 'Changed since sprint 1' }));

    expect((await screen.findByText(/^\+\s+return 'hi'$/)).className).toContain('text-success');
    expect(api.getWorkspaceFileDiff).toHaveBeenCalledWith('r', 'src/app.py');
  });

  it('says why a file is not shown', async () => {
    api.getWorkspaceFile.mockRejectedValue({ response: { data: { detail: 'logo.png is not text; download it instead.' } } });
    render(<WorkspacePanel runId="r" refreshKey="k" logs={[]} selected="logo.png" onSelect={() => {}} />);

    expect(await screen.findByText('logo.png is not text; download it instead.')).toBeTruthy();
  });

  it('reads the tree again once a burst of writes ends, not on every write, and not on a read', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const first = [event({ sequence: 1, event_type: 'tool_call', message: 'read_file: {}', metadata: { tool: 'read_file' } }),
      event({ sequence: 2, event_type: 'tool_result' })];
    const { rerender } = render(<WorkspacePanel runId="r" refreshKey="k" logs={first} selected={null} onSelect={() => {}} />);
    await waitFor(() => expect(api.getWorkspaceFiles).toHaveBeenCalledTimes(1));
    await act(async () => { vi.advanceTimersByTime(RELOAD_AFTER_MS * 2); });
    expect(api.getWorkspaceFiles).toHaveBeenCalledTimes(1);

    let logs = first;
    for (const n of [3, 5]) {
      logs = [...logs,
        event({ sequence: n, event_type: 'tool_call', message: 'write_artifact: {}', metadata: { tool: 'write_artifact' } }),
        event({ sequence: n + 1, event_type: 'tool_result', message: 'Wrote src/app.py' })];
      rerender(<WorkspacePanel runId="r" refreshKey="k" logs={logs} selected={null} onSelect={() => {}} />);
      await act(async () => { vi.advanceTimersByTime(RELOAD_AFTER_MS / 2); });
    }
    expect(api.getWorkspaceFiles).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(RELOAD_AFTER_MS); });

    expect(api.getWorkspaceFiles).toHaveBeenCalledTimes(2);
  });
});

describe('what the stream says about writes', () => {
  it('takes an artifact event or a writing tool\'s result, matched to its call in the same stage', () => {
    expect(lastWriteSequence([
      event({ sequence: 1, event_type: 'tool_call', stage: 'a', metadata: { tool: 'edit_artifact' } }),
      event({ sequence: 2, event_type: 'tool_call', stage: 'b', metadata: { tool: 'grep' } }),
      event({ sequence: 3, event_type: 'tool_result', stage: 'b' }),
      event({ sequence: 4, event_type: 'tool_result', stage: 'a' }),
      event({ sequence: 5, event_type: 'tool_result', stage: 'b' }),
    ])).toBe(4);
    expect(lastWriteSequence([event({ sequence: 7, event_type: 'artifact' })])).toBe(7);
    expect(lastWriteSequence([event({ sequence: 8, event_type: 'tool_call', message: 'read_file: {}' }), event({ sequence: 9, event_type: 'tool_result' })])).toBe(0);
  });
});

describe('the highlighter', () => {
  const kinds = (text: string, path: string) => highlight(text, path).map((line) => line.map((t) => `${t.kind}:${t.text}`));

  it('knows each language\'s comments, strings and keywords by the file\'s extension', () => {
    expect(kinds('fn main() { // go\n', 'src/main.rs')[0]).toEqual(['keyword:fn', 'plain: main() { ', 'comment:// go']);
    expect(kinds('x = "a#b"  # note', 'app.rb')[0]).toEqual(['plain:x = ', 'string:"a#b"', 'plain:  ', 'comment:# note']);
    expect(kinds('SELECT 1 -- one', 'q.sql')[0]).toEqual(['plain:SELECT ', 'number:1', 'plain: ', 'comment:-- one']);
  });

  it('splits a comment or string that runs over lines at each line end', () => {
    expect(kinds('/* one\ntwo */ let', 'a.ts')).toEqual([['comment:/* one'], ['comment:two */', 'plain: ', 'keyword:let']]);
    expect(kinds('"""a\nb"""', 'a.py')).toEqual([['string:"""a'], ['string:b"""']]);
  });

  it('shows a file of an unknown kind plain, apostrophes and all', () => {
    expect(kinds("don't # stop", 'notes.txt')).toEqual([["plain:don't # stop"]]);
  });
});
