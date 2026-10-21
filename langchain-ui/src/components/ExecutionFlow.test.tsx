import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ExecutionFlow, asDuration } from './ExecutionFlow';
import { describeStage } from '../lib/activity';
import type { RunStage } from '../types';

const stage = (name: string, status: string, duration: number | null): RunStage => ({
  name, sprint: 0, meaning: '', started_at: '2026-10-21T06:52:00Z', ended_at: null, status,
  duration_seconds: duration, retry_count: 0, approval_count: 0,
} as RunStage);

const stages = [
  stage('product_manager', 'completed', 28),
  stage('tools_models', 'completed', 106),
  stage('stack_selector', 'running', null),
];

describe('the progress pane', () => {
  it('shows a finished step as one line and the step in flight in full', () => {
    const { container } = render(<ExecutionFlow stages={stages} currentStage="stack_selector" isTerminal={false} />);

    expect(container.querySelectorAll('[data-compact="true"]')).toHaveLength(2);
    expect(screen.getByText('1m 46s')).toBeTruthy();
    const current = container.querySelector('[data-current="true"]');
    expect(current).not.toBeNull();
    expect(current!.querySelectorAll('p').length).toBeGreaterThanOrEqual(2);
  });

  it('keeps the sprint heading above the steps’ icons as they scroll under it', () => {
    const { container } = render(<ExecutionFlow stages={stages} currentStage="stack_selector" isTerminal={false} />);

    const heading = container.querySelector('header.sticky')!;
    const layer = (el: Element) => Number((el.className.match(/\bz-(\d+)\b/) || [])[1] || 0);
    const icons = Array.from(container.querySelectorAll('li > span.relative'));
    expect(icons.length).toBeGreaterThan(0);
    for (const icon of icons) expect(layer(heading)).toBeGreaterThan(layer(icon));
  });

  it('folds the earlier finished steps into one row that opens, beside a progress bar', () => {
    const planning = ['product_manager', 'tools_models', 'stack_selector', 'consult_database', 'consult_backend',
      'consult_security_reliability', 'consult_testing', 'research_brief'].map((name) => stage(name, 'completed', 30));
    const all = [...planning, { ...stage('principal_architect', 'running', null), started_at: new Date(Date.now() - 80_000).toISOString() }];
    const { container } = render(<ExecutionFlow stages={all} currentStage="principal_architect" isTerminal={false} />);

    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('8');
    expect(screen.getByRole('button', { name: /7 earlier steps/ })).toBeTruthy();
    expect(screen.getByText('3m 30s')).toBeTruthy();
    expect(screen.queryByText('Understanding your product')).toBeNull();
    expect(screen.getByText('Gathering what the plan needs')).toBeTruthy();
    expect(screen.getByTestId('working-for').textContent).toMatch(/^1m 2\ds$/);

    fireEvent.click(screen.getByRole('button', { name: /7 earlier steps/ }));
    expect(screen.getByText('Understanding your product')).toBeTruthy();
    expect(container.querySelector('[data-folded-summary="true"]')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Fold the finished steps/ }));
    expect(screen.queryByText('Understanding your product')).toBeNull();
  });

  it('names every step a run makes in words, never its raw name', () => {
    for (const name of ['research_brief', 'drafting', 'defect_fix', 'advice_review_ui_ux', 'code_review_1_0', 'stack_setup_0']) {
      const { title } = describeStage(name);
      expect(title.toLowerCase()).not.toBe(name.replace(/_/g, ' '));
      expect(title).not.toMatch(/_/);
    }
    expect(describeStage('advice_review_ui_ux').title).toBe('Checking the interface advice');
    expect(asDuration(3_840)).toBe('1h 4m');
  });
});
