/**
 * Settings -> Models: sampling for each mode of a call.
 *
 * A reasoning model is called two ways: with its thinking on, and with it off. Model cards give different
 * sampling for each, so the harness keeps three modes per model - thinking (precise), thinking (general) and no
 * thinking - and sends each call its own mode's values. "Determine sampling" reads the model card and what the
 * harness knows of the model's family; any value can be set here instead, and "back to determined" undoes it.
 * Nothing is sent until "Send sampling by mode" is on: until then the model server's own defaults apply.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { api } from '../api';
import { useFeedback } from './Feedback';

export type ModeId = 'thinking_precise' | 'thinking_general' | 'no_thinking';

export interface SamplingMode {
  id: ModeId;
  label: string;
  used_for: string;
  what_it_does: string;
  values: Record<string, number>;
  derived: Record<string, number>;
  source: 'owner' | 'model card' | 'model family' | 'unknown';
  note: string;
  owner_set: boolean;
}

export interface Sampling {
  model: string;
  settings: string[];
  modes: SamplingMode[];
  choices: { send: boolean; thinking_calls: ModeId };
  determined_at: string;
}

/** What each setting does, in a sentence. */
export const SETTING_HELP: Record<string, string> = {
  temperature: 'How random each word choice is. Lower is steadier and more repeatable; higher is more varied.',
  top_p: 'Only the most likely words that together make up this share of the probability are considered.',
  top_k: 'Only this many of the most likely next words are considered.',
  min_p: 'Words less likely than this fraction of the top word are dropped. 0 turns it off.',
  presence_penalty: 'Discourages reusing any word already written. Helps prose avoid loops; harms code and JSON, which reuse names and keys.',
  repetition_penalty: 'Scales down words already used. 1.0 turns it off.',
};

const SOURCE_STYLE: Record<SamplingMode['source'], string> = {
  owner: 'text-primary border-primary/40',
  'model card': 'text-success border-success/40',
  'model family': 'text-text-secondary border-border',
  unknown: 'text-warning border-warning/40',
};

const isSampling = (data: unknown): data is Sampling =>
  Boolean(data) && typeof data === 'object' && !Array.isArray(data) && Array.isArray((data as Sampling).modes);

export const ModelSamplingPanel: React.FC = () => {
  const [sampling, setSampling] = useState<Sampling | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [edits, setEdits] = useState<Partial<Record<ModeId, Record<string, string>>>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const { notify } = useFeedback();

  const load = useCallback(async () => {
    try {
      const res = await api.get('/settings/model/sampling');
      setSampling(isSampling(res.data) ? res.data : null);
    } catch {
      setSampling(null);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const apply = (data: unknown) => {
    if (isSampling(data)) setSampling(data);
  };

  const determine = async () => {
    setBusy(true);
    setNote('');
    try {
      const res = await api.post('/settings/model/sampling/determine');
      apply(res.data);
      setNote('Determined from the model card and what the harness knows of this model family.');
    } catch (err: any) {
      setNote(err.response?.data?.detail ?? 'Sampling could not be determined.');
    } finally {
      setBusy(false);
    }
  };

  const put = async (body: Record<string, unknown>) => {
    setBusy(true);
    try {
      const res = await api.put('/settings/model/sampling', body);
      apply(res.data);
      return true;
    } catch (err: any) {
      notify(err.response?.data?.detail ?? 'Only an administrator can change the sampling.');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const shown = (mode: SamplingMode, name: string): string => {
    const edited = edits[mode.id]?.[name];
    if (edited !== undefined) return edited;
    const value = mode.values[name];
    return value === undefined ? '' : String(value);
  };
  const edit = (mode: SamplingMode, name: string, value: string) =>
    setEdits((before) => ({ ...before, [mode.id]: { ...(before[mode.id] ?? {}), [name]: value } }));

  const saveMode = async (mode: SamplingMode) => {
    const values: Record<string, number | null> = {};
    for (const name of sampling?.settings ?? []) {
      const raw = shown(mode, name).trim();
      values[name] = raw === '' ? null : Number(raw);
    }
    if (Object.values(values).some((v) => v !== null && Number.isNaN(v))) {
      notify('Each setting is a number, or left empty for the server default.');
      return;
    }
    if (await put({ mode: mode.id, values })) setEdits((before) => ({ ...before, [mode.id]: undefined }));
  };

  const resetMode = async (mode: SamplingMode) => {
    if (await put({ mode: mode.id, values: null })) setEdits((before) => ({ ...before, [mode.id]: undefined }));
  };

  const thinkingCalls = sampling?.choices.thinking_calls ?? 'thinking_precise';
  const usedNow = (id: ModeId) => id === 'no_thinking' || id === thinkingCalls;

  return (
    <section className="glass-card rounded-2xl overflow-hidden" aria-labelledby="model-sampling-heading">
      <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
        <SlidersHorizontal className="h-5 w-5 text-primary" />
        <h2 id="model-sampling-heading" className="font-semibold text-text-primary">Sampling by mode</h2>
      </div>
      <div className="px-6 py-4 space-y-4">
        <p className="text-sm text-text-secondary">
          Sampling decides how the model picks each next word. The harness calls a reasoning model in two ways -
          with its thinking on, and with it switched off - and model cards recommend different sampling for each.
          Here each call gets the values of its own mode. Determine the values from the model card, adjust any of
          them, and turn sending on when you are ready; until then the model server's own defaults are used.
        </p>

        {!loaded ? (
          <p role="status" className="text-sm text-text-muted">Loading…</p>
        ) : !sampling || !sampling.model ? (
          <p className="text-sm text-text-muted">No model is serving.</p>
        ) : (
          <>
            <p className="text-sm text-text-secondary">
              Served model <span className="font-mono text-text-primary">{sampling.model}</span>
              {sampling.determined_at
                ? <span className="text-text-muted">{` - determined ${sampling.determined_at}`}</span>
                : <span className="text-warning"> - not determined yet</span>}
            </p>

            <div className="rounded-lg border border-border p-3 space-y-3">
              <label className="flex items-start gap-3 text-sm text-text-primary">
                <input
                  type="checkbox"
                  aria-label="Send sampling by mode"
                  checked={sampling.choices.send}
                  disabled={busy}
                  onChange={(e) => put({ send: e.target.checked })}
                  className="mt-1"
                />
                <span>
                  <span className="font-medium">Send sampling by mode</span>
                  <span className="block text-text-secondary">
                    {sampling.choices.send
                      ? 'On: every call is sent the values of its mode below.'
                      : "Off: nothing is sent, and the model server's own defaults apply."}
                  </span>
                </span>
              </label>
              <label className="flex flex-wrap items-center gap-2 text-sm text-text-primary">
                <span className="font-medium">Calls with thinking on use</span>
                <select
                  aria-label="Mode for calls with thinking on"
                  value={thinkingCalls}
                  disabled={busy}
                  onChange={(e) => put({ thinking_calls: e.target.value })}
                  className="rounded border border-border bg-transparent px-2 py-1 text-text-primary"
                >
                  <option value="thinking_precise">Thinking - precise (recommended: the harness writes code)</option>
                  <option value="thinking_general">Thinking - general</option>
                </select>
                <span className="text-text-muted">Calls with thinking off always use "No thinking".</span>
              </label>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              {sampling.modes.map((mode) => (
                <article
                  key={mode.id}
                  aria-label={mode.label}
                  data-used={usedNow(mode.id) ? 'true' : undefined}
                  className={`rounded-lg border p-3 space-y-2 ${usedNow(mode.id) ? 'border-primary/50' : 'border-border opacity-80'}`}
                >
                  <header className="flex items-center justify-between gap-2">
                    <h3 className="font-medium text-text-primary">{mode.label}</h3>
                    <span className="text-xs text-text-muted">{usedNow(mode.id) ? 'in use' : 'not chosen'}</span>
                  </header>
                  <p className="text-xs text-text-secondary"><span className="font-medium">Used for: </span>{mode.used_for}</p>
                  <p className="text-xs text-text-secondary"><span className="font-medium">What it does: </span>{mode.what_it_does}</p>
                  <div className="flex items-center gap-2">
                    <span className={`inline-block rounded border px-2 py-0.5 text-xs ${SOURCE_STYLE[mode.source] ?? SOURCE_STYLE.unknown}`}>
                      {mode.source}
                    </span>
                    <span className="text-xs text-text-muted">{mode.note}</span>
                  </div>
                  <table className="w-full text-sm">
                    <tbody>
                      {sampling.settings.map((name) => (
                        <tr key={name} className="border-t border-border/50">
                          <th scope="row" className="py-1 pr-2 text-left font-normal text-text-primary" title={SETTING_HELP[name]}>
                            {name}
                            <span className="block text-[11px] leading-tight text-text-muted">{SETTING_HELP[name]}</span>
                          </th>
                          <td className="py-1 text-right align-top">
                            <input
                              aria-label={`${mode.label} ${name}`}
                              inputMode="decimal"
                              placeholder="server default"
                              value={shown(mode, name)}
                              onChange={(e) => edit(mode, name, e.target.value)}
                              className="w-24 rounded border border-border bg-transparent px-2 py-1 text-right text-text-primary"
                            />
                            {mode.owner_set && mode.derived[name] !== undefined && mode.derived[name] !== mode.values[name] && (
                              <span className="block text-[11px] text-text-muted">determined: {mode.derived[name]}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => saveMode(mode)}
                      disabled={busy || !edits[mode.id]}
                      className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium disabled:opacity-50"
                    >
                      Save {mode.label}
                    </button>
                    {mode.owner_set && (
                      <button
                        type="button"
                        onClick={() => resetMode(mode)}
                        disabled={busy}
                        className="px-3 py-1.5 rounded-lg border border-border text-text-primary text-xs disabled:opacity-50"
                      >
                        Back to determined
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={determine}
            disabled={busy || !sampling?.model}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-text-primary text-sm font-medium disabled:opacity-50"
          >
            {busy ? 'Working…' : 'Determine sampling'}
          </button>
          <span className="text-xs text-text-muted">
            Reads the model card's recommendations for each mode (or the base model's card), then what the harness
            knows of the model's family. Values you set yourself are kept.
          </span>
          {note && <span role="status" className="text-sm text-text-secondary">{note}</span>}
        </div>
      </div>
    </section>
  );
};

export default ModelSamplingPanel;
