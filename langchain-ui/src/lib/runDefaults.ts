/**
 * How the owner last started a run, kept on their account so the start form
 * opens with it on any browser (plan UI-S5). Saved when a run starts; an empty
 * object forgets it.
 */
import { api } from '../api';

export interface RunDefaults {
  delivery_mode?: 'fast' | 'thorough';
  use_frontier_model?: boolean;
  unattended?: boolean;
  auto_approve?: boolean;
  approval_timeout_minutes?: number | null;
  allow_subdirectories?: boolean;
  /** Review point -> whether the run stops there for the owner. */
  reviews?: Record<string, boolean>;
}

/** The review points the start form offers, in its order, with their words. */
export const REVIEW_POINTS: [string, string][] = [
  ['product_intake', 'Product intake'],
  ['technical_specification', 'Technical specification'],
  ['acceptance_tests', 'Acceptance tests'],
  ['sprint', 'Each sprint'],
  ['release', 'Release'],
  ['escalation', 'Escalation'],
];

export async function readRunDefaults(): Promise<RunDefaults | null> {
  try {
    const me = await api.get('/auth/me');
    const saved = me.data?.preferences?.run_defaults as RunDefaults | undefined;
    return saved && Object.keys(saved).length > 0 ? saved : null;
  } catch {
    return null;
  }
}

export async function saveRunDefaults(defaults: RunDefaults): Promise<void> {
  try {
    await api.patch('/auth/me/preferences', { run_defaults: defaults });
  } catch {
    /* the run started either way; the form opens as it did */
  }
}

export async function forgetRunDefaults(): Promise<void> {
  await api.patch('/auth/me/preferences', { run_defaults: {} });
}

/** The saved defaults in words, one line each, for the settings page. */
export function describeRunDefaults(defaults: RunDefaults): string[] {
  const lines: string[] = [];
  if (defaults.delivery_mode) lines.push(`Delivery: ${defaults.delivery_mode}`);
  if (defaults.use_frontier_model !== undefined) {
    lines.push(defaults.use_frontier_model ? 'Model: local, with the judgement model' : 'Model: local only');
  }
  if (defaults.unattended) lines.push('Unattended: no stops for review');
  else if (defaults.reviews) {
    const asked = REVIEW_POINTS.filter(([key]) => defaults.reviews?.[key]).map(([, words]) => words.toLowerCase());
    lines.push(asked.length ? `Stops for review at: ${asked.join(', ')}` : 'Stops for no review');
  }
  if (defaults.approval_timeout_minutes) lines.push(`A waiting gate approves itself after ${defaults.approval_timeout_minutes} min`);
  if (defaults.allow_subdirectories === false) lines.push('Writes only at the top of the workspace');
  return lines;
}
