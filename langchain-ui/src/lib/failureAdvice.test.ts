import { describe, expect, it } from 'vitest';
import { failureAdvice } from './failureAdvice';

// LR.34: a failed run says what stopped it and what its owner can do, above the harness's own reason.
describe('what a failure means', () => {
  it('names the cause and an action for the common stops', () => {
    expect(failureAdvice('The acceptance suite proves nothing after 5 rounds: x')?.kind).toBe('The acceptance tests');
    expect(failureAdvice('The model server at :8888 did not answer')?.action).toMatch(/Resume/);
    expect(failureAdvice("Sprint 'a' was re-planned 3 times and still could not be accepted")?.kind)
      .toBe('A sprint that could not be finished');
  });

  it('still says something for a reason it does not know, and nothing for no error', () => {
    expect(failureAdvice('a new kind of stop')?.kind).toBe('Something unexpected');
    expect(failureAdvice(null)).toBeNull();
  });

  it('uses none of the product nouns', () => {
    const banned = /\b(?:task|tasks|to-do|todo|button|click|checkbox)\b/i;
    for (const error of ['acceptance suite proves nothing', 'model server', 'budget', 're-planned 3 times', 'structured response', 'time limit', 'x']) {
      const advice = failureAdvice(error)!;
      expect(banned.test(`${advice.kind} ${advice.meaning} ${advice.action}`)).toBe(false);
    }
  });
});
