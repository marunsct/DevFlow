import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentActivity } from './AgentActivity';
import { laneOf } from '../lib/activity';
import type { LogEntry } from '../types';

let sequence = 0;
const event = (event_type: string, stage: string, message: string, metadata: Record<string, unknown> = {}): LogEntry => ({
  event_id: `e${++sequence}`, event_type, run_id: 'run-1', timestamp: `2026-10-19T10:00:${String(sequence).padStart(2, '0')}Z`,
  sequence, stage, message, metadata,
} as LogEntry);

const logs = [
  event('tool_call', 'principal_architect', 'read_file: {"file_path": "docs/spec.md"}', { tool: 'read_file' }),
  event('tool_result', 'principal_architect', '`docs/spec.md` is in the project memory at the start of this conversation, whole and as it is now'),
  event('review_decision', 'technical_specification', 'Review decision: changes — Name the session store.', { action: 'changes', review_point: 'technical_specification' }),
  event('agent_message', 'defect_fix_2_3', 'The session cookie is now set on sign-in.'),
];

describe('the activity feed', () => {
  it('shows a held-back read as what it is, not as a failure', async () => {
    render(<AgentActivity logs={logs} />);
    expect(await screen.findByText('held back: already read')).toBeTruthy();
    expect(screen.queryByText(/didn't work/)).toBeNull();
  });

  it('puts the owner’s decisions in their place', () => {
    render(<AgentActivity logs={logs} />);
    expect(screen.getByText('You asked for changes to Technical Specification')).toBeTruthy();
    expect(screen.getByText('“Name the session store.”')).toBeTruthy();
  });

  it('shows a step that answers in structured output alone: its start and its outcome', () => {
    render(<AgentActivity logs={[
      event('stage_change', 'tools_models', 'Comparing frameworks, model providers, and infrastructure options.', { status: 'running' }),
      event('log', 'architecture_review', 'Outcome: passed\nNo blocking finding.'),
    ]} />);
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
