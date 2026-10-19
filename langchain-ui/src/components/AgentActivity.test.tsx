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
