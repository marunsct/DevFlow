import type { RunSummary } from '../types';

/** A run as the runs list sends it, every field present; a test names only what it is about. */
export const aRun = (run_id: string, status: string, extra: Partial<RunSummary> = {}): RunSummary => ({
  run_id,
  status,
  current_stage: 'release_review',
  created_at: '2026-10-19T00:00:00Z',
  updated_at: '2026-10-19T01:00:00Z',
  document_names: [],
  delivery_mode: 'fast',
  local_only: true,
  completion_gaps: 0,
  criteria_proven: null,
  criteria_total: null,
  gate_deadline: null,
  run_name: null,
  model_pinned: false,
  model_last: null,
  ...extra,
});
