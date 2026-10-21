import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExecutionFlow } from './ExecutionFlow';
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
});
