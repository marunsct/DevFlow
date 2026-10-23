/**
 * Settings -> Models: what the served model can do (plan MD.5).
 *
 * The harness needs facts about the model it serves - whether it reads images,
 * how its thinking is switched, which languages it handles - and each one has
 * a source: the owner said so here, the harness measured it, the server
 * reported it, or the model card states it. A fact still unknown is marked so,
 * and "Find what is missing" asks the harness to measure and look up the rest.
 * A value set here wins over every other source; "automatic" hands it back.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Cpu } from 'lucide-react';
import { api } from '../api';
import { useFeedback } from './Feedback';

export type CapabilityValue = boolean | number | string | null;

export interface CapabilityField {
  key: string;
  label: string;
  kind: 'bool' | 'int' | 'text' | 'choice';
  options?: string[];
  value: CapabilityValue;
  source: 'owner' | 'measured' | 'server' | 'model card' | 'unknown';
  note: string;
  owner_value: CapabilityValue;
}

export interface Capabilities {
  model: string;
  status: 'idle' | 'running' | 'failed';
  message: string;
  fields: CapabilityField[];
}

/** How often a running look-up is asked about, in milliseconds. */
export const POLL_MS = 5000;

const SOURCE_STYLE: Record<CapabilityField['source'], string> = {
  owner: 'text-primary border-primary/40',
  measured: 'text-success border-success/40',
  server: 'text-text-secondary border-border',
  'model card': 'text-text-secondary border-border',
  unknown: 'text-warning border-warning/40',
};

const isCapabilities = (data: unknown): data is Capabilities =>
  Boolean(data) && typeof data === 'object' && !Array.isArray(data) && Array.isArray((data as Capabilities).fields);

export const ModelCapabilitiesPanel: React.FC = () => {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [edits, setEdits] = useState<Record<string, CapabilityValue>>({});
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { notify } = useFeedback();

  const load = useCallback(async () => {
    try {
      const res = await api.get('/settings/model/capabilities');
      const next = isCapabilities(res.data) ? res.data : null;
      setCapabilities(next);
      return next;
    } catch {
      setCapabilities(null);
      return null;
    } finally {
      setLoaded(true);
    }
  }, []);

  // Asked again every POLL_MS while the look-up runs, and no longer once it has finished.
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

  const send = async (values: Record<string, CapabilityValue>) => {
    setBusy(true);
    try {
      const res = await api.put('/settings/model/capabilities', { values });
      if (isCapabilities(res.data)) setCapabilities(res.data);
      else await load();
      setEdits({});
    } catch (err: any) {
      notify(err.response?.data?.detail ?? 'Only an administrator can change what the model can do.');
    } finally {
      setBusy(false);
    }
  };

  const fill = async () => {
    setBusy(true);
    setNote('');
    try {
      const res = await api.post('/settings/model/capabilities/fill');
      setNote(res.data?.message ?? 'Looking up what is missing.');
      if (timer.current) clearTimeout(timer.current);
      await follow();
    } catch (err: any) {
      setNote(err.response?.data?.detail ?? 'The look-up could not be started.');
    } finally {
      setBusy(false);
    }
  };

  const edit = (field: CapabilityField, value: CapabilityValue) => setEdits((before) => ({ ...before, [field.key]: value }));
  const shown = (field: CapabilityField): CapabilityValue => (field.key in edits ? edits[field.key] : field.value);
  const running = capabilities?.status === 'running';
  const changed = Object.keys(edits).length > 0;
  const missing = capabilities?.fields.filter((f) => f.source === 'unknown').length ?? 0;

  const control = (field: CapabilityField) => {
    const value = shown(field);
    const label = `${field.label} value`;
    if (field.kind === 'bool') {
      return (
        <select
          aria-label={label}
          value={value === true ? 'yes' : value === false ? 'no' : ''}
          onChange={(e) => edit(field, e.target.value === '' ? null : e.target.value === 'yes')}
          className="rounded border border-border bg-transparent px-2 py-1 text-text-primary"
        >
          <option value="">not known</option>
          <option value="yes">yes</option>
          <option value="no">no</option>
        </select>
      );
    }
    if (field.kind === 'choice') {
      return (
        <select
          aria-label={label}
          value={value == null ? '' : String(value)}
          onChange={(e) => edit(field, e.target.value === '' ? null : e.target.value)}
          className="rounded border border-border bg-transparent px-2 py-1 text-text-primary"
        >
          <option value="">not known</option>
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      );
    }
    return (
      <input
        aria-label={label}
        type={field.kind === 'int' ? 'number' : 'text'}
        value={value == null ? '' : String(value)}
        onChange={(e) => {
          const raw = e.target.value;
          edit(field, raw === '' ? null : field.kind === 'int' ? Number(raw) : raw);
        }}
        className="w-40 rounded border border-border bg-transparent px-2 py-1 text-text-primary"
      />
    );
  };

  return (
    <section className="glass-card rounded-2xl overflow-hidden" aria-labelledby="model-capabilities-heading">
      <div className="px-6 py-4 border-b border-border/50 flex items-center gap-2">
        <Cpu className="h-5 w-5 text-primary" />
        <h2 id="model-capabilities-heading" className="font-semibold text-text-primary">Model capabilities</h2>
      </div>
      <div className="px-6 py-4 space-y-4">
        <p className="text-sm text-text-secondary">
          What the served model can do, and where each fact came from. A value set here wins over what was
          measured or looked up; set it back to automatic to let the harness decide.
        </p>

        {!loaded ? (
          <p role="status" className="text-sm text-text-muted">Loading…</p>
        ) : !capabilities ? (
          <p className="text-sm text-text-muted">Nothing is known about the served model yet.</p>
        ) : (
          <>
            <p className="text-sm text-text-secondary">
              Served model <span className="font-mono text-text-primary">{capabilities.model || '-'}</span>
              {missing > 0 && <span className="text-warning">{` - ${missing} still unknown`}</span>}
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted">
                  <th scope="col" className="py-1 font-normal">Capability</th>
                  <th scope="col" className="py-1 font-normal">Value</th>
                  <th scope="col" className="py-1 font-normal">Source</th>
                  <th scope="col" className="py-1 font-normal"><span className="sr-only">Automatic</span></th>
                </tr>
              </thead>
              <tbody>
                {capabilities.fields.map((field) => (
                  <tr
                    key={field.key}
                    data-unknown={field.source === 'unknown' ? 'true' : undefined}
                    className={`border-t border-border/50 ${field.source === 'unknown' ? 'bg-warning/5' : ''}`}
                  >
                    <td className="py-2 pr-3 text-text-primary">{field.label}</td>
                    <td className="py-2 pr-3">{control(field)}</td>
                    <td className="py-2 pr-3">
                      <span
                        title={field.note}
                        className={`inline-block rounded border px-2 py-0.5 text-xs ${SOURCE_STYLE[field.source] ?? SOURCE_STYLE.server}`}
                      >
                        {field.source}
                      </span>
                      {field.note && <span className="block text-xs text-text-muted mt-0.5">{field.note}</span>}
                    </td>
                    <td className="py-2 text-right">
                      {field.owner_value !== null && field.owner_value !== undefined && (
                        <button
                          type="button"
                          onClick={() => send({ [field.key]: null })}
                          disabled={busy}
                          aria-label={`${field.label}: back to automatic`}
                          className="text-xs text-text-secondary underline disabled:opacity-50"
                        >
                          automatic
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => send(edits)}
            disabled={!changed || busy}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50"
          >
            Save capabilities
          </button>
          <button
            type="button"
            onClick={fill}
            disabled={busy || running}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-text-primary text-sm font-medium disabled:opacity-50"
          >
            {running ? 'Looking up…' : 'Find what is missing'}
          </button>
          {running && (
            <span role="status" className="text-sm text-text-secondary">
              {capabilities?.message || 'Measuring the model and looking up the rest.'}
            </span>
          )}
          {!running && capabilities?.status === 'failed' && (
            <span role="alert" className="text-sm text-danger">{capabilities.message || 'The last look-up failed.'}</span>
          )}
          {note && !running && <span className="text-sm text-text-secondary">{note}</span>}
        </div>
      </div>
    </section>
  );
};

export default ModelCapabilitiesPanel;
