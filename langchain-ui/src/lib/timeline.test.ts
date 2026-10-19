import { describe, expect, it } from 'vitest';
import { marks } from './timeline';
import type { LogEntry, RunStage } from '../types';

const stage = (name: string, started_at: string) => ({ name, started_at } as RunStage);
const decision = (timestamp: string) => ({ event_type: 'review_decision', timestamp, message: 'Review decision: approve' } as LogEntry);

describe('the marks on a run’s timeline', () => {
  it('places stages, decisions and directions at their share of the run, in order', () => {
    const found = marks('2026-10-19T10:00:00Z', Date.parse('2026-10-19T12:00:00Z'),
      [stage('principal_architect', '2026-10-19T10:00:00Z'), stage('defect_fix_2_3', '2026-10-19T11:30:00Z')],
      [decision('2026-10-19T11:00:00Z'), { event_type: 'tool_call', timestamp: '2026-10-19T11:10:00Z' } as LogEntry],
      [{ at: '2026-10-19T10:30:00Z', text: 'Keep the sign-in page' }]);

    expect(found.map((mark) => [mark.kind, mark.share])).toEqual([
      ['stage', 0], ['steering', 0.25], ['gate', 0.5], ['stage', 0.75],
    ]);
    expect(found[3].label).toBe('Fixing problem 4 (test round 2)');
    expect(found[1].label).toBe('Direction: Keep the sign-in page');
  });

  it('has nothing to place before the run has a span', () => {
    expect(marks('2026-10-19T10:00:00Z', Date.parse('2026-10-19T10:00:00Z'), [], [], [])).toEqual([]);
  });
});
