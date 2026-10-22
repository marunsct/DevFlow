import { describe, expect, it } from 'vitest';
import type { ServerHealth } from '../types';
import { describeServer, holdingTheModel } from './serverHealth';

const health = (extra: Partial<ServerHealth> = {}): ServerHealth => ({
  hosted: false,
  answered: true,
  model: 'Qwen3.6-35B-A3B-UD-Q4_K_M.gguf',
  quantisation: 'Q4_K_M',
  slots: 2,
  slot_context: 126_464,
  checked_at: '2026-10-19T12:03:00Z',
  busy_runs: ['run-a'],
  ...extra,
});

describe('the model server, in words', () => {
  it('says what it holds, how it serves and who is on it', () => {
    const view = describeServer(health());
    expect(view.tone).toBe('ok');
    expect(view.said).toBe('Model server: Qwen3.6-35B-A3B-UD-Q4_K_M.gguf · Q4_K_M · 2 slots · 126k context · 1 run on it');
  });

  it('says a server that did not answer, and a hosted API, for what they are', () => {
    expect(describeServer(health({ answered: false })).tone).toBe('warn');
    expect(describeServer(health({ answered: false })).said).toMatch(/did not answer its status at 12:03 UTC/);
    expect(describeServer(health({ hosted: true, model: 'claude' })).said).toMatch(/hosted; nothing to check/);
    expect(describeServer(null).said).toMatch(/not checked yet/);
  });

  it('names the run holding a one-slot server, and none on a server with more', () => {
    expect(holdingTheModel(health({ slots: 1, busy_runs: ['run-a'] }))).toBe('run-a');
    expect(holdingTheModel(health({ slots: 1, busy_runs: ['run-a'] }), 'run-a')).toBeNull();
    expect(holdingTheModel(health({ slots: 2 }))).toBeNull();
    expect(holdingTheModel(health({ slots: 1, busy_runs: [] }))).toBeNull();
  });
});
