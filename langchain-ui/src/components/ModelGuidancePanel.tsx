/**
 * Settings -> Models: how the harness steers the model it is serving (plan MD.3).
 *
 * The diagnosis asks the served model questions shaped like the harness's
 * stages, measures how often it does as asked, and from that picks its
 * capability tier and which guides it gets - each guide its own switch. The
 * result is kept against the model, so it is measured once per model, not
 * once per run. A guide can be set On or Off here for this model; Auto
 * follows the diagnosis.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Compass } from 'lucide-react';
import { api } from '../api';
import { useFeedback } from './Feedback';

export interface SteeringCheck {
  name: string;
  area: string;
  passed: number;
  tries: number;
  /** Tries the server failed (an error, a timeout): not counted either way. */
  unmeasured?: number;
  /** Asked and shown, not scored: nearly every model fails it by its wording. */
  calibrating?: boolean;
}

export interface SteeringGuide {
  id: string;
  title: string;
  area: string;
  text: string;
  switch: string;
  switch_on: boolean;
  chosen: boolean;
  override: boolean | null;
  active: boolean;
}

export interface Steering {
  model: string;
  measured_at: string | null;
  status: 'idle' | 'running' | 'failed';
  message: string;
  tier: 'strong' | 'standard' | 'weak' | null;
  score: number | null;
  checks: SteeringCheck[];
  guides: SteeringGuide[];
  settings: { structured_answers: string; reasoning_effort: string; reply_ceiling: number | null; tail_reminder: boolean };
  /** What differs between the server the diagnosis was measured on and the server now; runs are not given it. */
  stale?: string[];
  /** Guides dropped because a check fell when they were given together. */
  harmful?: string[];
  /** The settings the diagnosis measures, each overridable (PROFILE_FROM_DIAGNOSIS). */
  profile?: ProfileSection;
}

export interface ProfileField {
  id: string;
  title: string;
  /** The values it takes, or null for a number. */
  choices: string[] | null;
  number: 'int' | 'float' | null;
  measured: number | string | null;
  evidence: string;
  confidence: string;
  /** The owner's value; it always wins. */
  override: number | string | null;
  /** What runs use now; null for the harness's default. */
  applied: number | string | null;
  behind_switch: boolean;
}

export interface ProfileSection {
  switch: string;
  switch_on: boolean;
  measured_at?: string | null;
  fields: ProfileField[];
}

/** How often a running diagnosis is asked about, in milliseconds. */
export const POLL_MS = 5000;

const TIER_WORDS: Record<string, string> = {
  strong: 'strong - needs no steering',
  standard: 'standard - targeted guidance',
  weak: 'weak - full steering with reminders',
};

type Choice = 'auto' | 'on' | 'off';
const choiceOf = (override: boolean | null): Choice => (override === null ? 'auto' : override ? 'on' : 'off');
const overrideOf = (choice: Choice): boolean | null => (choice === 'auto' ? null : choice === 'on');

/** A payload the panel can show; anything else (an error page, an empty list) is no steering yet. */
const isSteering = (data: unknown): data is Steering =>
  Boolean(data) && typeof data === 'object' && !Array.isArray(data) && Array.isArray((data as Steering).guides);

export const ModelGuidancePanel: React.FC = () => {
  const [steering, setSteering] = useState<Steering | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [note, setNote] = useState('');
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { notify } = useFeedback();

  const load = useCallback(async () => {
    try {
      const res = await api.get('/settings/model/steering');
      const next = isSteering(res.data) ? res.data : null;
      setSteering(next);
      return next;
    } catch {
      setSteering(null);
      return null;
    } finally {
      setLoaded(true);
    }
  }, []);

  // Asked again every POLL_MS while the diagnosis runs, and no longer once it has finished.
  const follow = useCallback(async () => {
    const ask = async function askAgain(): Promise<void> {
      const next = await load();
      if (next?.status === 'running') {
        timer.current = setTimeout(askAgain, POLL_MS);
      }
    };
    await ask();
  }, [load]);

  useEffect(() => {
    follow();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [follow]);

  const diagnose = async (full = false) => {
    setStarting(true);
    setNote('');
    try {
      const res = full
        ? await api.post('/settings/model/steering/diagnose', { full: true })
        : await api.post('/settings/model/steering/diagnose');
      setNote(res.data?.message ?? 'The diagnosis has started.');
      if (timer.current) clearTimeout(timer.current);
      await follow();
    } catch (err: any) {
      setNote(err.response?.data?.detail ?? 'The diagnosis could not be started.');
    } finally {
      setStarting(false);
    }
  };

  const choose = async (guide: SteeringGuide, choice: Choice) => {
    try {
      const res = await api.put(`/settings/model/steering/guides/${guide.id}`, { override: overrideOf(choice) });
      if (isSteering(res.data)) setSteering(res.data);
      else await load();
    } catch (err: any) {
      notify(err.response?.data?.detail ?? 'Only an administrator can change a guide.');
    }
  };

  const setField = async (field: ProfileField, value: string) => {
    const typed = value === '' ? null : field.number ? Number(value) : value;
    try {
      const res = await api.put(`/settings/model/steering/profile/${field.id}`, { value: typed });
      if (isSteering(res.data)) setSteering(res.data);
      else await load();
    } catch (err: any) {
      notify(err.response?.data?.detail ?? 'Only an administrator can change a setting.');
    }
  };

  const running = steering?.status === 'running';

  return (
    <section className="glass-card rounded-2xl overflow-hidden" aria-labelledby="model-guidance-heading">
      <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
        <Compass className="h-5 w-5 text-primary" />
        <h2 id="model-guidance-heading" className="font-semibold text-text-primary">Model guidance</h2>
      </div>
      <div className="px-6 py-4 space-y-5">
        <p className="text-sm text-text-secondary">
          The diagnosis asks the served model questions shaped like the harness's stages and keeps what it
          needs against the model: a stronger model is left alone, a weaker one is steered in the areas it
          falls short in.
        </p>

        {!loaded ? (
          <p role="status" className="text-sm text-text-muted">Loading…</p>
        ) : (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div>
              <dt className="text-text-muted">Served model</dt>
              <dd className="text-text-primary font-mono">{steering?.model || '-'}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Last diagnosed</dt>
              <dd className="text-text-primary">{steering?.measured_at ?? 'not yet'}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Capability</dt>
              <dd className="text-text-primary">
                {steering?.tier ? TIER_WORDS[steering.tier] ?? steering.tier : 'not measured'}
                {steering?.score != null ? ` (score ${Math.round(steering.score * 100)}%)` : ''}
              </dd>
            </div>
          </dl>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => diagnose()}
            disabled={starting || running}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50"
          >
            {running ? 'Diagnosing…' : 'Diagnose this model and set its guidance'}
          </button>
          <button
            type="button"
            onClick={() => diagnose(true)}
            disabled={starting || running}
            title="Also replays stage requests at every reasoning effort and budget at a stage's size: 20 to 90 minutes of the model server, between runs."
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-sm font-medium text-text-primary disabled:opacity-50"
          >
            Full calibration (20-90 minutes)
          </button>
          {running && (
            <span role="status" className="text-sm text-text-secondary">
              {steering?.message || 'The diagnosis is asking the model its questions.'}
            </span>
          )}
          {!running && steering?.status === 'failed' && (
            <span role="alert" className="text-sm text-danger">{steering.message || 'The last diagnosis failed.'}</span>
          )}
          {note && !running && <span className="text-sm text-text-secondary">{note}</span>}
        </div>

        {steering?.stale && steering.stale.length > 0 && (
          <p role="alert" className="text-sm text-warning">
            Measured on another server ({steering.stale.join('; ')}): runs are not given these settings until the
            model is diagnosed again.
          </p>
        )}
        {steering?.harmful && steering.harmful.length > 0 && (
          <p className="text-sm text-text-secondary">
            Dropped because a check fell when they were given together: {steering.harmful.join(', ')}.
          </p>
        )}

        {steering && steering.checks.length > 0 && (
          <table className="w-full text-sm">
            <caption className="text-left text-text-muted mb-1">What the diagnosis measured</caption>
            <thead>
              <tr className="text-left text-text-muted">
                <th scope="col" className="py-1 font-normal">Check</th>
                <th scope="col" className="py-1 font-normal">Area</th>
                <th scope="col" className="py-1 font-normal text-right">Passed</th>
              </tr>
            </thead>
            <tbody>
              {steering.checks.map((check) => (
                <tr key={check.name} className="border-t border-border/50">
                  <td className="py-1 text-text-primary">
                    {check.name}
                    {check.calibrating && <span className="ml-2 text-xs text-text-muted">calibrating, not scored</span>}
                  </td>
                  <td className="py-1 text-text-secondary">{check.area}</td>
                  <td className={`py-1 text-right ${check.passed === check.tries ? 'text-success' : 'text-warning'}`}>
                    {check.passed}/{check.tries}
                    {check.unmeasured ? <span className="ml-1 text-xs text-text-muted">({check.unmeasured} not measured)</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {steering && steering.guides.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-2">Guides</h3>
            <ul className="space-y-3">
              {steering.guides.map((guide) => (
                <li key={guide.id} className="rounded-lg border border-border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-medium text-text-primary">{guide.title}</span>
                      <span className="text-xs text-text-muted">{guide.area}</span>
                      <span className={`text-xs ${guide.active ? 'text-success' : 'text-text-muted'}`}>
                        {guide.active ? 'active' : 'not active'}
                      </span>
                      {guide.chosen && <span className="text-xs text-text-secondary">chosen by the diagnosis</span>}
                    </div>
                    <label className="text-xs text-text-secondary flex items-center gap-2">
                      For this model
                      <select
                        aria-label={`${guide.title} for this model`}
                        value={choiceOf(guide.override)}
                        onChange={(e) => choose(guide, e.target.value as Choice)}
                        className="rounded border border-border bg-transparent px-2 py-1 text-text-primary"
                      >
                        <option value="auto">Auto (follow the diagnosis)</option>
                        <option value="on">On</option>
                        <option value="off">Off</option>
                      </select>
                    </label>
                  </div>
                  <p className="mt-1 text-xs text-text-muted">
                    Switch <span className="font-mono">{guide.switch}</span>
                    {guide.switch_on ? ' on' : ' - off globally'}
                  </p>
                  <details className="mt-1">
                    <summary className="text-xs text-text-secondary cursor-pointer">What the model is told</summary>
                    <p className="mt-1 text-sm text-text-primary whitespace-pre-wrap">{guide.text}</p>
                  </details>
                </li>
              ))}
            </ul>
          </div>
        )}

        {steering && (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div>
              <dt className="text-text-muted">Structured answers</dt>
              <dd className="text-text-primary">{steering.settings.structured_answers}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Reasoning effort sent</dt>
              <dd className="text-text-primary">{steering.settings.reasoning_effort || 'none sent'}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Reply ceiling</dt>
              <dd className="text-text-primary">
                {steering.settings.reply_ceiling ? `${steering.settings.reply_ceiling.toLocaleString()} tokens` : 'the deployment’s own'}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted">Reminder at the end of each request</dt>
              <dd className="text-text-primary">{steering.settings.tail_reminder ? 'yes' : 'no'}</dd>
            </div>
          </dl>
        )}

        {steering?.profile && steering.profile.fields.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-1">Measured settings</h3>
            <p className="text-xs text-text-muted mb-2">
              Switch <span className="font-mono">{steering.profile.switch}</span>
              {steering.profile.switch_on ? ' on: measured values are used.' : ' off: only your values and the timeout floor are used.'}
              {' '}A value you set always wins; leave it empty to follow the diagnosis.
            </p>
            <table className="w-full text-sm">
              <caption className="sr-only">Settings the diagnosis measured</caption>
              <thead>
                <tr className="text-left text-text-muted">
                  <th scope="col" className="py-1 font-normal">Setting</th>
                  <th scope="col" className="py-1 font-normal">Measured</th>
                  <th scope="col" className="py-1 font-normal">Your value</th>
                  <th scope="col" className="py-1 font-normal">In use</th>
                </tr>
              </thead>
              <tbody>
                {steering.profile.fields.map((field) => (
                  <tr key={field.id} className="border-t border-border/50 align-top">
                    <td className="py-1 text-text-primary">{field.title}</td>
                    <td className="py-1 text-text-secondary">
                      {field.measured ?? 'not measured'}
                      {field.evidence && <span className="block text-xs text-text-muted">{field.evidence}</span>}
                    </td>
                    <td className="py-1">
                      {field.choices ? (
                        <select
                          aria-label={`${field.title}: your value`}
                          value={field.override == null ? '' : String(field.override)}
                          onChange={(e) => setField(field, e.target.value)}
                          className="rounded border border-border bg-transparent px-2 py-1 text-text-primary"
                        >
                          <option value="">Follow the diagnosis</option>
                          {field.choices.map((choice) => (
                            <option key={choice} value={choice}>{choice}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          aria-label={`${field.title}: your value`}
                          type="number"
                          min={field.number === 'int' ? 1 : 0}
                          step={field.number === 'int' ? 1 : 'any'}
                          defaultValue={field.override == null ? '' : String(field.override)}
                          placeholder="follow the diagnosis"
                          onBlur={(e) => {
                            const was = field.override == null ? '' : String(field.override);
                            if (e.target.value !== was) setField(field, e.target.value);
                          }}
                          className="w-32 rounded border border-border bg-transparent px-2 py-1 text-text-primary"
                        />
                      )}
                    </td>
                    <td className="py-1 text-text-primary">{field.applied ?? 'default'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
};
