/**
 * Admin: every switch of the harness, what it does, and whether it is on.
 *
 * A switch is on or off by the first of: the setting made here (stored for
 * every process, effective within a few seconds), the deployed environment
 * (the Docker compose file), the code's own default. "Docker" here clears the
 * setting, so the switch follows the deployment again. Anyone signed in can
 * read the page; only an administrator can change a switch.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ToggleRight } from 'lucide-react';
import { api } from '../api';
import { Badge, useFeedback } from '../ui';

export interface SwitchEntry {
  name: string;
  module: string;
  summary: string;
  details: string;
  default: boolean;
  docker: boolean | null;
  setting: boolean | null;
  on: boolean;
  source: 'setting' | 'docker' | 'default';
}

type Choice = 'docker' | 'on' | 'off';
const choiceOf = (setting: boolean | null): Choice => (setting === null ? 'docker' : setting ? 'on' : 'off');
const settingOf = (choice: Choice): boolean | null => (choice === 'docker' ? null : choice === 'on');
const onOff = (value: boolean) => (value ? 'on' : 'off');

/** What the "Docker" choice means for this switch: the deployment's value, or the code's when it sets none. */
const dockerWords = (entry: SwitchEntry): string =>
  entry.docker === null ? `Docker (not set: code default, ${onOff(entry.default)})` : `Docker (${onOff(entry.docker)})`;

const SOURCE_WORDS: Record<SwitchEntry['source'], string> = {
  setting: 'set here',
  docker: 'from Docker',
  default: 'code default',
};

const isEntries = (data: unknown): data is SwitchEntry[] =>
  Array.isArray(data) && data.every((item) => item && typeof item === 'object' && 'name' in item && 'on' in item);

export const Admin: React.FC = () => {
  const [entries, setEntries] = useState<SwitchEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const { notify } = useFeedback();

  const load = useCallback(async () => {
    try {
      const res = await api.get('/settings/switches');
      if (isEntries(res.data)) {
        setEntries(res.data);
        setFailed(false);
      } else {
        setFailed(true);
      }
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    load();
    api.get('/auth/me').then((res) => setIsAdmin(res.data?.role === 'admin')).catch(() => setIsAdmin(false));
  }, [load]);

  const choose = async (entry: SwitchEntry, choice: Choice) => {
    setBusy(entry.name);
    try {
      const res = await api.put(`/settings/switches/${entry.name}`, { setting: settingOf(choice) });
      if (isEntries(res.data)) setEntries(res.data);
      else await load();
    } catch (err: any) {
      notify(err.response?.data?.detail ?? 'Only an administrator can change a switch.');
    } finally {
      setBusy(null);
    }
  };

  const shown = useMemo(() => {
    const words = query.trim().toLowerCase();
    if (!entries) return [];
    if (!words) return entries;
    return entries.filter((entry) => `${entry.name} ${entry.summary} ${entry.details}`.toLowerCase().includes(words));
  }, [entries, query]);

  const counts = useMemo(() => {
    const all = entries ?? [];
    return { total: all.length, on: all.filter((e) => e.on).length, set: all.filter((e) => e.setting !== null).length };
  }, [entries]);

  return (
    <div className="w-full mt-4 space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl font-bold text-text-primary mb-1">Admin</h1>
        <p className="text-text-secondary text-sm">
          Every switch of the harness and what it does. A switch set here applies to every process within a few
          seconds, including a run in progress. One left on Docker follows the deployment, and the code's own default
          where the deployment sets nothing.
        </p>
      </div>

      <section className="glass-card rounded-2xl overflow-hidden" aria-labelledby="switches-heading">
        <div className="px-6 py-4 border-b border-border/50 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ToggleRight className="h-5 w-5 text-primary" />
            <h2 id="switches-heading" className="font-semibold text-text-primary">Switches</h2>
          </div>
          {entries && (
            <p className="text-sm text-text-secondary" role="status">
              {counts.on} of {counts.total} on, {counts.set} set here
            </p>
          )}
        </div>
        <div className="px-6 py-4 space-y-4">
          {!isAdmin && entries && (
            <p className="text-sm text-text-muted">Only an administrator can change a switch; this view is read-only.</p>
          )}
          <label className="block text-sm">
            <span className="text-text-secondary">Find a switch</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Name or what it does"
              className="mt-1 w-full rounded-lg border border-border bg-transparent px-3 py-2 text-text-primary"
            />
          </label>

          {failed && <p role="alert" className="text-sm text-danger">The switches could not be loaded.</p>}
          {!entries && !failed && <p role="status" className="text-sm text-text-muted">Loading…</p>}
          {entries && shown.length === 0 && <p className="text-sm text-text-muted">No switch matches “{query}”.</p>}

          <ul className="space-y-3">
            {shown.map((entry) => (
              <li key={entry.name} className="rounded-lg border border-border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-mono font-medium text-text-primary">{entry.name}</span>
                    <Badge tone={entry.on ? 'ok' : 'neutral'}>{entry.on ? 'On' : 'Off'}</Badge>
                    <span className="text-xs text-text-muted">{SOURCE_WORDS[entry.source]}</span>
                  </div>
                  <label className="text-xs text-text-secondary flex items-center gap-2">
                    Value
                    <select
                      aria-label={`${entry.name} value`}
                      value={choiceOf(entry.setting)}
                      disabled={!isAdmin || busy === entry.name}
                      onChange={(e) => choose(entry, e.target.value as Choice)}
                      className="rounded border border-border bg-transparent px-2 py-1 text-text-primary disabled:opacity-60"
                    >
                      <option value="docker">{dockerWords(entry)}</option>
                      <option value="on">On</option>
                      <option value="off">Off</option>
                    </select>
                  </label>
                </div>
                <p className="mt-2 text-sm text-text-primary">{entry.summary}</p>
                {entry.details && (
                  <details className="mt-1">
                    <summary className="text-xs text-text-secondary cursor-pointer">Why it exists and how it works</summary>
                    <p className="mt-1 text-sm text-text-secondary whitespace-pre-wrap">{entry.details}</p>
                  </details>
                )}
                <p className="mt-1 text-xs text-text-muted font-mono">{entry.module}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
};
