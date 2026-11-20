/**
 * Give a run a direction. The note is kept with the run, and every model call
 * from the next one on carries it, through the same instruction injection as
 * the stack's instructions (`POST /runs/{id}/steering`).
 *
 * Three levels (plan WS.3): this agent (the stage working now, at its next
 * model call), the whole run (every later stage), and stop and redirect (pause
 * when the working stage ends, then resume with the direction). A note waits,
 * greyed, until a model call reads it; until then it can be edited or
 * withdrawn. A note for the whole run can be for everyone or for one group of
 * stages or one builder (its audience), and each note in the list says who it
 * is for and who read it.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  editSteering,
  getSteering,
  pauseRun,
  resumeWithDirection,
  sendSteering,
  withdrawSteering,
  type SteeringAudience,
  type SteeringNote,
} from '../api';
import { useFeedback } from './Feedback';
import { describeStage, RESUMABLE } from '../lib/activity';

type Level = 'next_stage' | 'run' | 'redirect';

const LEVELS: { value: Level; label: string }[] = [
  { value: 'next_stage', label: 'This agent' },
  { value: 'run', label: 'The whole run' },
  { value: 'redirect', label: 'Stop and redirect' },
];

/** Who a note can be for, in the words the page uses (`app.server.steering.AUDIENCES`). */
export const AUDIENCES: { value: SteeringAudience; label: string }[] = [
  { value: 'all', label: 'Everyone' },
  { value: 'design', label: 'The design stages' },
  { value: 'planning', label: 'The planners' },
  { value: 'build', label: 'The builders' },
  { value: 'tests', label: 'The test writers' },
  { value: 'review', label: 'The reviewers' },
  { value: 'ui_ux', label: 'The interface builder' },
  { value: 'backend', label: 'The back-end builder' },
  { value: 'database', label: 'The database builder' },
  { value: 'security_reliability', label: 'The security builder' },
  { value: 'testing', label: 'The testing builder' },
  { value: 'documentation', label: 'The documentation writer' },
  { value: 'devops', label: 'The deployment builder' },
];

/** Who a note is for, in words: "everyone" when it names no one. */
export const audienceOf = (note: SteeringNote): string => {
  const named = (note.audience ?? []).filter((who) => who !== 'all');
  if (named.length === 0) return 'everyone';
  return named.map((who) => (AUDIENCES.find((a) => a.value === who)?.label ?? who).toLowerCase()).join(', ');
};

const stateOf = (note: SteeringNote): 'queued' | 'read' | 'withdrawn' =>
  note.state ?? (note.applied_stage ? 'read' : 'queued');

const detailOf = (error: any): string | undefined => error?.response?.data?.detail;

/**
 * Folded to one line until the owner opens it (plan BG.4), so the page leads
 * with what the run is doing. `heard` changes when the run's stream says a
 * note was read, so the list shows it at once.
 */
export const SteeringBox: React.FC<{
  runId: string;
  stage?: string | null;
  status?: string;
  heard?: number;
}> = ({ runId, stage, status, heard = 0 }) => {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState<SteeringNote[]>([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [level, setLevel] = useState<Level>('run');
  const [audience, setAudience] = useState<SteeringAudience>('all');
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  // A stop-and-redirect asked for while the run was running: sent as the run's direction once it has stopped.
  const [redirect, setRedirect] = useState<string | null>(null);
  const resuming = useRef(false);
  const { notify } = useFeedback();
  const stopped = !!status && RESUMABLE.includes(status);
  const working = stage ? describeStage(stage).title : 'the stage working now';

  const refresh = () => getSteering(runId).then(setNotes).catch(() => {});
  useEffect(() => {
    void refresh();
  }, [runId, heard, status]);

  useEffect(() => {
    if (redirect === null || status !== 'paused' || resuming.current) return;
    resuming.current = true;
    resumeWithDirection(runId, redirect)
      .then(() => {
        setRedirect(null);
        notify('Stopped and resumed with your direction.', 'info');
        void refresh();
      })
      .catch((error) => notify(detailOf(error) ?? 'The run stopped, but could not be resumed with the direction.', 'error'))
      .finally(() => { resuming.current = false; });
  }, [redirect, status, runId]);

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    const words = text.trim();
    if (!words) return;
    setSending(true);
    try {
      if (level === 'redirect') {
        if (stopped) {
          await resumeWithDirection(runId, words);
          notify('Resumed with your direction.', 'info');
          void refresh();
        } else {
          await pauseRun(runId, true);
          setRedirect(words);
          notify('The run stops when this stage ends, then resumes with your direction.', 'info');
        }
      } else {
        // "This agent" is the stage working now, whoever it is; an audience narrows a note for the whole run.
        const note = await sendSteering(runId, words, level, [level === 'run' ? audience : 'all']);
        setNotes((kept) => [...kept, note]);
        notify(
          status === 'paused' || status === 'waiting_for_budget'
            ? 'Kept. The run is paused; the note is read when it resumes.'
            : 'Sent. It is read at the next model call.',
          'info',
        );
      }
      setText('');
    } catch (error) {
      notify(detailOf(error) ?? 'The note could not be sent.', 'error');
    } finally {
      setSending(false);
    }
  };

  const saveEdit = async () => {
    if (!editing || !editing.text.trim()) return;
    try {
      const note = await editSteering(runId, editing.id, editing.text.trim());
      setNotes((kept) => kept.map((n) => (n.id === note.id ? note : n)));
      setEditing(null);
    } catch (error) {
      notify(detailOf(error) ?? 'The note could not be changed.', 'error');
      setEditing(null);
      void refresh();
    }
  };

  const withdraw = async (id: string) => {
    try {
      const note = await withdrawSteering(runId, id);
      setNotes((kept) => kept.map((n) => (n.id === note.id ? note : n)));
    } catch (error) {
      notify(detailOf(error) ?? 'The note could not be withdrawn.', 'error');
      void refresh();
    }
  };

  const waiting = notes.filter((note) => stateOf(note) === 'queued').length;
  if (!open) {
    return (
      <div className="glass-card rounded-2xl px-4 py-2.5 flex flex-wrap items-center gap-3 text-sm">
        <button type="button" aria-expanded="false" onClick={() => setOpen(true)} className="font-medium text-primary hover:underline">
          Steer this run…
        </button>
        <span className="text-xs text-text-muted">
          {notes.length === 0
            ? 'No direction sent'
            : `${notes.length} direction${notes.length === 1 ? '' : 's'} sent${waiting ? `, ${waiting} waiting` : ''}`}
          {redirect !== null ? ' · stopping to redirect' : ''}
        </span>
      </div>
    );
  }

  const hint =
    level === 'next_stage'
      ? `Only ${working} reads it, at its next model call.`
      : level === 'run'
        ? audience === 'all'
          ? 'Every later stage reads it, from the next model call on.'
          : `Only ${AUDIENCES.find((who) => who.value === audience)?.label.toLowerCase()} read it, from their next model call on.`
        : stopped
          ? 'The run resumes now with this direction.'
          : 'The run stops when this stage ends, then resumes with this direction.';

  return (
    <section className="glass-card rounded-2xl p-4" aria-labelledby="steering-heading">
      <div className="flex items-center justify-between gap-3 mb-1">
        <h2 id="steering-heading" className="text-sm font-semibold text-text-primary">Steer this run</h2>
        <button type="button" aria-expanded="true" onClick={() => setOpen(false)} className="text-xs text-text-muted hover:text-text-primary">
          Fold
        </button>
      </div>
      {(status === 'paused' || status === 'waiting_for_budget') && (
        <p role="status" className="text-xs text-text-muted mb-2">
          The run is paused. A note waits and is read when it resumes.
        </p>
      )}
      {redirect !== null && (
        <p role="status" data-testid="redirect-pending" className="text-xs text-text-muted mb-2">
          Stopping when this stage ends, then resuming with: {redirect}
        </p>
      )}
      {notes.length > 0 && (
        <ul className="mb-3 space-y-1.5" aria-label="Directions sent">
          {notes.map((n, i) => {
            const state = stateOf(n);
            const isEditing = editing !== null && editing.id === n.id;
            return (
              <li key={n.id ?? i} data-state={state} className={`text-sm ${state === 'queued' ? 'text-text-muted opacity-70' : 'text-text-secondary'}`}>
                <span className="text-xs text-text-muted tabular-nums mr-2">{new Date(n.at).toLocaleTimeString()}</span>
                {isEditing ? (
                  <span className="flex flex-col sm:flex-row gap-2 mt-1">
                    <label htmlFor={`steering-edit-${n.id}`} className="sr-only">New words for this note</label>
                    <textarea
                      id={`steering-edit-${n.id}`}
                      value={editing.text}
                      maxLength={2000}
                      rows={2}
                      onChange={(e) => setEditing({ id: editing.id, text: e.target.value })}
                      className="flex-1 rounded-lg bg-overlay border border-border/60 px-3 py-2 text-sm text-text-primary"
                    />
                    <button type="button" onClick={saveEdit} disabled={!editing.text.trim()} className="text-xs text-primary hover:underline disabled:opacity-50">
                      Save
                    </button>
                    <button type="button" onClick={() => setEditing(null)} className="text-xs text-text-muted hover:underline">
                      Keep as it was
                    </button>
                  </span>
                ) : (
                  <span className={state === 'withdrawn' ? 'line-through' : undefined}>{n.text}</span>
                )}
                <span className="block text-xs text-text-muted">
                  {state === 'read'
                    ? `Read by ${describeStage(n.applied_stage).title}`
                    : state === 'withdrawn'
                      ? 'Withdrawn - no model call reads it'
                      : 'Waiting - read at the next model call'}
                  {n.scope === 'next_stage' ? ' · this agent only' : ' · the whole run'}
                  {` · for ${audienceOf(n)}`}
                  {n.edited_at && state !== 'withdrawn' ? ' · edited' : ''}
                  {state === 'queued' && n.id && !isEditing && (
                    <>
                      {' · '}
                      <button type="button" onClick={() => setEditing({ id: n.id!, text: n.text })} className="text-primary hover:underline">
                        Edit
                      </button>
                      {' · '}
                      <button type="button" onClick={() => withdraw(n.id!)} className="text-primary hover:underline">
                        Withdraw
                      </button>
                    </>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <form onSubmit={send} className="flex flex-col gap-2">
        <fieldset className="flex flex-wrap gap-3 text-sm text-text-secondary">
          <legend className="sr-only">Who reads this direction</legend>
          {LEVELS.map((choice) => (
            <label key={choice.value} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="steering-level"
                value={choice.value}
                checked={level === choice.value}
                onChange={() => setLevel(choice.value)}
              />
              {choice.label}
            </label>
          ))}
        </fieldset>
        {level === 'run' && (
          <label className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
            Who it is for
            <select
              value={audience}
              onChange={(e) => setAudience(e.target.value as SteeringAudience)}
              className="rounded-lg bg-overlay border border-border/60 px-2 py-1 text-sm text-text-primary"
            >
              {AUDIENCES.map((who) => (
                <option key={who.value} value={who.value}>{who.label}</option>
              ))}
            </select>
          </label>
        )}
        <p className="text-xs text-text-muted">{hint}</p>
        <div className="flex flex-col sm:flex-row gap-2">
          <label htmlFor="steering-text" className="sr-only">Direction for this run</label>
          <textarea
            id="steering-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={2000}
            rows={2}
            placeholder="e.g. Keep the sign-in page as it is; the session cookie is the problem."
            className="flex-1 rounded-lg bg-overlay border border-border/60 px-3 py-2 text-sm text-text-primary"
          />
          <button
            type="submit"
            disabled={sending || !text.trim() || (level === 'redirect' && redirect !== null)}
            className="shrink-0 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50"
          >
            {sending ? 'Sending…' : level === 'redirect' ? (stopped ? 'Resume with this direction' : 'Stop and redirect') : 'Send'}
          </button>
        </div>
      </form>
    </section>
  );
};
