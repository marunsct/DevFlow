import React, { useEffect, useRef, useState } from 'react';
import { Pencil } from 'lucide-react';
import { setRunName } from '../api';
import { useFeedback } from './Feedback';

interface Props {
  runId: string;
  /** The name the run has, or none. */
  name?: string | null;
  /** Called with the saved name (empty when cleared) once the server has taken it. */
  onChanged?: (name: string) => void;
}

const LONGEST = 80;

/**
 * The run's name, above its title: click it to type another, Enter to save, Escape to leave it as it was.
 *
 * With several runs of the same brief the list showed only ids and stages, and the person could not tell which
 * run was which; a name makes one findable. An empty name clears it.
 */
export const RunNameField: React.FC<Props> = ({ runId, name, onChanged }) => {
  const { notify } = useFeedback();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name ?? '');
  const [saving, setSaving] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(name ?? '');
  }, [name, editing]);

  useEffect(() => {
    if (editing) input.current?.select();
  }, [editing]);

  const save = async () => {
    const wanted = draft.split(/\s+/).filter(Boolean).join(' ').slice(0, LONGEST);
    if (wanted === (name ?? '')) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await setRunName(runId, wanted);
      setEditing(false);
      onChanged?.(wanted);
    } catch (err: any) {
      notify('Failed to name the run: ' + (err?.response?.data?.detail || err?.message || 'unknown error'));
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <input
        ref={input}
        value={draft}
        maxLength={LONGEST}
        disabled={saving}
        aria-label="Run name"
        placeholder="Name this run"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => { if (!saving) void save(); }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); void save(); }
          if (e.key === 'Escape') { setDraft(name ?? ''); setEditing(false); }
        }}
        className="mb-0.5 w-full max-w-md rounded-md border border-primary/50 bg-surface px-2 py-0.5 text-sm font-semibold text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title={name ? 'Rename this run' : 'Give this run a name to find it in the list'}
      className={`group mb-0.5 inline-flex max-w-full items-center gap-1.5 rounded-md text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
        name ? 'font-semibold text-text-primary' : 'text-text-muted hover:text-text-secondary'
      }`}
    >
      <span className="truncate">{name || 'Name this run'}</span>
      <Pencil className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-70 group-focus-visible:opacity-70" aria-hidden="true" />
    </button>
  );
};
