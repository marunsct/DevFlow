import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentActivity } from './AgentActivity';
import { commandLine, laneOf, workspacePath } from '../lib/activity';
import type { LogEntry } from '../types';

let sequence = 0;
const event = (event_type: string, stage: string, message: string, metadata: Record<string, unknown> = {}): LogEntry => ({
  event_id: `e${++sequence}`, event_type, run_id: 'run-1', timestamp: `2026-10-19T10:00:${String(sequence).padStart(2, '0')}Z`,
  sequence, stage, message, metadata,
} as LogEntry);

/** Steps are folded to one line each, the newest open (plan WS.2): open one by its title. */
const openStep = (title: string) => userEvent.click(screen.getByRole('button', { name: new RegExp(`^${title}`) }));

const logs = [
  event('tool_call', 'principal_architect', 'read_file: {"file_path": "docs/spec.md"}', { tool: 'read_file' }),
  event('tool_result', 'principal_architect', '`docs/spec.md` is in the project memory at the start of this conversation, whole and as it is now'),
  event('review_decision', 'technical_specification', 'Review decision: changes — Name the session store.', { action: 'changes', review_point: 'technical_specification' }),
  event('agent_message', 'defect_fix_2_3', 'The session cookie is now set on sign-in.'),
];

describe('the activity feed', () => {
  it('shows a held-back read as what it is, not as a failure', async () => {
    render(<AgentActivity logs={logs} />);
    await openStep('Designing how it works');
    expect(await screen.findByText('held back: already read')).toBeTruthy();
    expect(screen.queryByText(/didn't work/)).toBeNull();
  });

  it('puts the owner’s decisions in their place', async () => {
    render(<AgentActivity logs={logs} />);
    await openStep('Technical Specification');
    expect(screen.getByText('You asked for changes to Technical Specification')).toBeTruthy();
    expect(screen.getByText('“Name the session store.”')).toBeTruthy();
  });

  it('shows a step that answers in structured output alone: its start and its outcome', async () => {
    render(<AgentActivity logs={[
      event('stage_change', 'tools_models', 'Comparing frameworks, model providers, and infrastructure options.', { status: 'running' }),
      event('log', 'architecture_review', 'Outcome: passed\nNo blocking finding.'),
    ]} />);
    await openStep('Comparing the options');
    expect(screen.queryByText('Nothing to show yet')).toBeNull();
    expect(screen.getAllByTestId('activity-note')).toHaveLength(2);
    expect(screen.getByText(/^Started: /)).toBeTruthy();
    expect(screen.getByText('Comparing frameworks, model providers, and infrastructure options.')).toBeTruthy();
    expect(screen.getByText('Outcome: passed')).toBeTruthy();
  });

  it('filters to one lane', async () => {
    render(<AgentActivity logs={logs} />);
    await userEvent.click(screen.getByRole('button', { name: 'fixes' }));
    expect(screen.getByRole('button', { name: 'fixes' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.queryByText('held back: already read')).toBeNull();
  });

  it('names lanes by role, then by kind of step', () => {
    expect(laneOf('specialist_backend_specialist_2')).toBe('backend');
    expect(laneOf('specialist_ui_ux_0')).toBe('ui ux');
    expect(laneOf('defect_fix_2_3')).toBe('fixes');
    expect(laneOf('acceptance_author_1')).toBe('testing');
    expect(laneOf('principal_architect')).toBe('planning');
  });
});

describe('what a screen reader hears', () => {
  it('the newest progress update, not every action', () => {
    render(<AgentActivity logs={logs} />);
    expect(screen.getByRole('log').getAttribute('aria-live')).toBe('off');
    expect(screen.getByRole('status').textContent).toBe('The session cookie is now set on sign-in.');
  });
});

describe('a long feed', () => {
  const many = Array.from({ length: 650 }, (_, index) =>
    ({ event_id: `m${index}`, event_type: 'agent_message', run_id: 'run-1', timestamp: new Date(Date.parse('2026-10-19T10:00:00Z') + index * 1000).toISOString(),
       sequence: 1000 + index, stage: 'defect_fix_2_3', message: `Update ${index}`, metadata: {} }) as LogEntry);

  it('shows the newest entries, and earlier ones on request', async () => {
    render(<AgentActivity logs={many} />);
    expect(screen.queryByText('Update 349')).toBeNull();
    expect(screen.getByText('Update 350')).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: 'Show 300 earlier (350 not shown)' }));
    expect(screen.getByText('Update 50')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Show 50 earlier (50 not shown)' }));
    expect(screen.getByText('Update 0')).toBeTruthy();
  });
});

describe('a run a person can follow (plan WS.2)', () => {
  const command = (stage: string, call: string, argv: string) =>
    event('tool_call', stage, `run_terminal_command: {'command': [${argv}]}`, { tool: 'run_terminal_command', call_id: call });

  it('shows a command as its command line and exit status, its output folded until asked for', async () => {
    render(<AgentActivity logs={[
      command('test_round_1', 'c1', "'npm', 'run', 'test'"),
      event('tool_result', 'test_round_1', '2 passed\n1 failed\n--- stderr ---\nAssertionError', { exit_code: 1, call_id: 'c1' }),
    ]} />);

    const line = screen.getByRole('button', { name: /^npm run test, exit 1/ });
    expect(within(line).getByTestId('exit-status').textContent).toBe('exit 1');
    expect(screen.queryByText(/1 failed/)).toBeNull();

    await userEvent.click(line);
    expect(screen.getByLabelText('The output of npm run test').textContent).toContain('2 passed\n1 failed');
    expect(screen.queryByText(/Clipped/)).toBeNull();
  });

  it('says when the page was sent only part of the output, and reads the exit status of an older event', async () => {
    render(<AgentActivity logs={[
      command('test_round_1', 'c1', "'pytest'"),
      event('tool_result', 'test_round_1', `content='{"stdout": "ok", "returncode": "0"} ${'x'.repeat(40)}'\n\n[+3,000 more characters]`),
    ]} />);

    await userEvent.click(screen.getByRole('button', { name: /^pytest, exit 0/ }));
    expect(screen.getByText(/3,000 more are in the run's transcript/)).toBeTruthy();
    expect(screen.getByLabelText('The output of pytest').textContent).not.toContain('more characters]');
  });

  it('puts each result under its own call when side-by-side workers interleave', async () => {
    render(<AgentActivity logs={[
      command('specialist_backend_0', 'c1', "'go', 'test'"),
      command('specialist_frontend_1', 'c2', "'npm', 'test'"),
      event('tool_result', 'specialist_backend_0', 'FAIL', { exit_code: 2, call_id: 'c1' }),
      event('tool_result', 'specialist_frontend_1', 'ok', { exit_code: 0, call_id: 'c2' }),
    ]} />);

    expect(screen.getByRole('button', { name: /^npm test, exit 0/ })).toBeTruthy();
    await openStep('Building the backend');
    expect(screen.getByRole('button', { name: /^go test, exit 2/ })).toBeTruthy();
  });

  it('links a written file to the Workspace tab, on its change', async () => {
    const opened = vi.fn();
    render(<AgentActivity onOpenFile={opened} logs={[
      event('tool_call', 'specialist_backend_0', 'write_artifact: {"relative_path": "src/app.py", "content": "x"}', { tool: 'write_artifact' }),
      event('tool_result', 'specialist_backend_0', '{"path": "src/app.py", "bytes": 1}'),
    ]} />);

    const link = screen.getByRole('link', { name: 'src/app.py' });
    expect(link.getAttribute('href')).toBe('?view=workspace&file=src%2Fapp.py&diff=1');
    await userEvent.click(link);
    expect(opened).toHaveBeenCalledWith('src/app.py');
  });

  it('folds every step to one line but the one working now', async () => {
    render(<AgentActivity isRunning logs={[
      event('agent_message', 'principal_architect', 'The design is written.'),
      event('agent_message', 'specialist_backend_0', 'Writing the route.'),
    ]} />);

    const earlier = screen.getByRole('button', { name: /^Designing how it works/ });
    const now = screen.getByRole('button', { name: /^Building the backend/ });
    expect(earlier.getAttribute('aria-expanded')).toBe('false');
    expect(now.getAttribute('aria-expanded')).toBe('true');
    expect(within(now).getByText('working now')).toBeTruthy();
    expect(earlier.textContent).toContain('1 entry');
    expect(screen.queryByText('The design is written.')).toBeNull();

    await userEvent.click(earlier);
    expect(screen.getByText('The design is written.')).toBeTruthy();
  });

  it('names a written file as the Workspace tab does, and reads a command line whole', () => {
    expect(workspacePath('/app/data/workspaces/a-product/src/app.py')).toBe('src/app.py');
    expect(workspacePath('./docs/a.md')).toBe('docs/a.md');
    expect(workspacePath('../outside.txt')).toBeUndefined();
    expect(commandLine(`{'command': ['npx', 'vitest', 'run', 'a b.test.ts'], 'category': 'test'}`)).toBe('npx vitest run a b.test.ts');
  });

  it('opens the step a moment from the timeline lands in', () => {
    const first = event('agent_message', 'principal_architect', 'The design is written.');
    render(<AgentActivity focusAt={first.timestamp} logs={[first, event('agent_message', 'specialist_backend_0', 'Writing the route.')]} />);

    expect(screen.getByRole('button', { name: /^Designing how it works/ }).getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('The design is written.')).toBeTruthy();
  });
});
