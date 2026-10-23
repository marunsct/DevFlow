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

export interface SteeringCheck { name: string; area: string; passed: number; tries: number }

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

  const diagnose = async () => {
    setStarting(true);
    setNote('');
    try {
      const res = await api.post('/settings/model/steering/diagnose');
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
            onClick={diagnose}
            disabled={starting || running}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50"
          >
            {running ? 'Diagnosing…' : 'Diagnose this model and set its guidance'}
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
                  <td className="py-1 text-text-primary">{check.name}</td>
                  <td className="py-1 text-text-secondary">{check.area}</td>
                  <td className={`py-1 text-right ${check.passed === check.tries ? 'text-success' : 'text-warning'}`}>
                    {check.passed}/{check.tries}
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
      </div>
    </section>
  );
};
