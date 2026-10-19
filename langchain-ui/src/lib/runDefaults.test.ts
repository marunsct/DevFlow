import { describe, expect, it } from 'vitest';
import { describeRunDefaults } from './runDefaults';

describe('the run defaults, in words', () => {
  it('names the mode, the model, where a run stops and the timeout', () => {
    expect(describeRunDefaults({
      delivery_mode: 'thorough',
      use_frontier_model: false,
      reviews: { product_intake: true, technical_specification: false, release: true },
      approval_timeout_minutes: 30,
      allow_subdirectories: false,
    })).toEqual([
      'Delivery: thorough',
      'Model: local only',
      'Stops for review at: product intake, release',
      'A waiting gate approves itself after 30 min',
      'Writes only at the top of the workspace',
    ]);
  });

  it('says an unattended run stops for nothing, whatever the review points say', () => {
    expect(describeRunDefaults({ unattended: true, reviews: { release: true } })).toEqual(['Unattended: no stops for review']);
  });
});
