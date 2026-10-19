import { describe, expect, it } from 'vitest';
import { aRun as run } from '../test/runs';
import { dismissalKey, inboxLine, inboxParts, newlyArrived, oneTapAnswer, readInbox } from './needsYou';

describe('the inbox', () => {
  it('counts only live waiting runs: never a finished, failed or dismissed one', () => {
    const gate = run('run-gate', 'waiting_for_approval');
    const hidden = run('run-hidden', 'waiting_for_review');
    const runs = [gate, hidden, run('run-failed', 'failed'), run('run-done', 'completed'), run('run-busy', 'running')];

    const inbox = readInbox(runs, 0, new Set([dismissalKey(hidden)]));

    expect(inbox.waiting.map((r) => r.run_id)).toEqual(['run-gate']);
    expect(inbox.stopped.map((r) => r.run_id)).toEqual(['run-failed']);
  });

  it('lists a failure only once, until the owner has looked', () => {
    const failed = run('run-failed', 'failed');
    expect(readInbox([failed], Date.parse('2026-10-19T02:00:00Z'), new Set()).stopped).toEqual([]);
  });

  it('shows a dismissed run again once it moves', () => {
    const before = run('run-gate', 'waiting_for_approval');
    const moved = run('run-gate', 'waiting_for_approval', { updated_at: '2026-10-19T03:00:00Z' });
    expect(readInbox([moved], 0, new Set([dismissalKey(before)])).waiting).toHaveLength(1);
  });

  it('says when a gate approves itself, so it is never silent', () => {
    const timed = run('run-8b0c41d2-aaaa', 'waiting_for_review', { gate_deadline: '2026-10-19T00:40:00Z' });
    expect(inboxLine(timed, () => '09:40')).toBe('run-8b0c41d2… · Release Review · approves itself at 09:40');
    expect(inboxLine(run('run-a', 'waiting_for_approval'))).toMatch(/waits for you$/);
    expect(inboxLine(run('run-a', 'waiting_for_budget'))).toMatch(/stopped at its budget$/);
  });

  it('answers a gate or a review in one tap, and leaves a budget to its page', () => {
    expect(oneTapAnswer(run('a', 'waiting_for_approval'))).toBe('approval');
    expect(oneTapAnswer(run('a', 'waiting_for_review'))).toBe('review');
    expect(oneTapAnswer(run('a', 'waiting_for_budget'))).toBeNull();
  });
});

describe('what is worth telling', () => {
  it('says nothing on the first poll, then each run that reaches a waiting, failed or finished status', () => {
    const runs = [run('a', 'waiting_for_approval'), run('b', 'completed'), run('c', 'running'), run('d', 'failed')];
    expect(newlyArrived(null, runs)).toEqual([]);

    const before = new Map([['a', 'running'], ['b', 'completed'], ['c', 'created'], ['d', 'running']]);
    expect(newlyArrived(before, runs).map((r) => r.run_id)).toEqual(['a', 'd']);
  });
});

describe('a row of the inbox', () => {
  it('keeps what happens next apart from the run, so a narrow row never cuts the deadline off', () => {
    const timed = run('run-8b0c41d2-aaaa', 'waiting_for_review', { gate_deadline: '2026-10-19T00:40:00Z' });
    expect(inboxParts(timed, () => '09:40')).toEqual({ who: 'run-8b0c41d2… · Release Review', what: 'approves itself at 09:40', timed: true });
  });
});
