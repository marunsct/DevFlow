/**
 * Give a running run a direction. The note is kept with the run, and every
 * model call from the next one on carries it, through the same instruction
 * injection as the stack's instructions (`POST /runs/{id}/steering`).
 */
import React, { useEffect, useState } from 'react';
import { getSteering, sendSteering, type SteeringNote } from '../api';
import { useFeedback } from './Feedback';

export const SteeringBox: React.FC<{ runId: string }> = ({ runId }) => {
  const [notes, setNotes] = useState<SteeringNote[]>([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [scope, setScope] = useState<'run' | 'next_stage'>('run');
  const { notify } = useFeedback();

  useEffect(() => {
    getSteering(runId).then(setNotes).catch(() => {});
  }, [runId]);

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    setSending(true);
    try {
      const note = await sendSteering(runId, text.trim(), scope);
      setNotes((kept) => [...kept, note]);
      setText('');
      notify('Sent. The run follows it from its next model call.', 'info');
    } catch {
      notify('The note could not be sent.', 'error');
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="glass-card rounded-2xl p-4" aria-labelledby="steering-heading">
      <h2 id="steering-heading" className="text-sm font-semibold text-text-primary mb-1">Steer this run</h2>
      <p className="text-xs text-text-muted mb-3">
        A direction for the agents, followed from their next model call. Nothing in progress is interrupted.
      </p>
      {notes.length > 0 && (
        <ul className="mb-3 space-y-1.5" aria-label="Directions sent">
          {notes.map((n, i) => (
            <li key={i} className="text-sm text-text-secondary">
              <span className="text-[11px] text-text-muted tabular-nums mr-2">{new Date(n.at).toLocaleTimeString()}</span>
              {n.text}
              <span className="block text-[11px] text-text-muted">
                {n.applied_stage ? `Read by the run in ${n.applied_stage}` : 'Not read yet - it is followed from the next model call'}
                {n.scope === 'next_stage' ? ' · for that one stage' : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={send} className="flex flex-col sm:flex-row gap-2">
        <label htmlFor="steering-text" className="sr-only">Direction for this run</label>
        <textarea
          id="steering-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={2000}
          rows={2}
          placeholder="e.g. Keep the sign-in page as it is; the session cookie is the problem."
          className="flex-1 rounded-lg bg-white/[0.04] border border-border/60 px-3 py-2 text-sm text-text-primary"
        />
        <label htmlFor="steering-scope" className="sr-only">How long this direction applies</label>
        <select
          id="steering-scope"
          value={scope}
          onChange={(e) => setScope(e.target.value as 'run' | 'next_stage')}
          className="shrink-0 rounded-lg bg-white/[0.04] border border-border/60 px-2 py-2 text-sm text-text-primary"
        >
          <option value="run">For the rest of the run</option>
          <option value="next_stage">For the next stage only</option>
        </select>
        <button
          type="submit"
          disabled={sending || !text.trim()}
          className="shrink-0 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50"
        >
          {sending ? 'Sending…' : 'Send'}
        </button>
      </form>
    </section>
  );
};
