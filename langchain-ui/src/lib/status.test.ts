import { describe, expect, it } from 'vitest';
import { statusView, TONE_BADGE } from './status';

describe('the status map', () => {
  it('knows which statuses wait for the owner', () => {
    for (const status of ['waiting_for_approval', 'waiting_for_review', 'waiting_for_budget']) {
      expect(statusView(status).needsYou).toBe(true);
    }
    for (const status of ['running', 'completed', 'failed', 'cancelled', 'paused', 'created']) {
      expect(statusView(status).needsYou).toBe(false);
    }
  });

  it('knows which statuses are over', () => {
    expect(['completed', 'failed', 'cancelled'].every((s) => statusView(s).terminal)).toBe(true);
    expect(['running', 'paused', 'waiting_for_budget'].some((s) => statusView(s).terminal)).toBe(false);
  });

  it('says a budget stop in words and treats an unknown status as not started', () => {
    expect(statusView('waiting_for_budget').label).toBe('Stopped at its budget');
    expect(statusView('something_new').tone).toBe('neutral');
    expect(statusView(undefined).label).toBe('Not started yet');
  });

  it('gives every tone a badge made of one token pair', () => {
    for (const classes of Object.values(TONE_BADGE)) {
      expect(classes).toMatch(/bg-\S+ text-\S+ border-\S+/);
      expect(classes).not.toMatch(/white|black|slate|#/);
    }
  });
});

describe('the words for a stage', () => {
  it('names the stages a run numbers as it goes', async () => {
    const { describeStage } = await import('./activity');
    expect(describeStage('defect_fix_2_12').title).toBe('Fixing problem 13 (test round 2)');
    expect(describeStage('test_round_1').title).toBe('Testing, round 1');
    expect(describeStage('acceptance_author_0').title).toBe('Writing the acceptance tests');
    expect(describeStage('acceptance_author_1').title).toBe('Revising the acceptance tests (pass 2)');
    expect(describeStage('consult_ui_ux').title).toBe('Asking the interface specialist');
    expect(describeStage('scaffold').title).toBe('Setting up the project');
  });
});
