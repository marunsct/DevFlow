/**
 * Point and say (plan WS.5): beside the part of the preview's page a person pointed at, they write what should
 * change. A run that is going gets a note (for the whole run, or for the stage working now) carrying where the part
 * is and which of the product's files most likely hold it, found by the server; a finished run's product, with
 * change requests on, gets a change request whose brief says the same.
 */
import React, { useState } from 'react';
import { sayAtPickedElement, type PickedSource } from '../api';
import type { PickedElement } from '../lib/pickedElement';

const ENDED = new Set(['completed', 'failed', 'cancelled']);

const detailOf = (error: any): string => error?.response?.data?.detail ?? 'The change could not be sent.';

export const PointAndSay: React.FC<{
  runId: string;
  element: PickedElement;
  runStatus?: string;
  changesAllowed?: boolean;
  onChangeRequest?: (brief: string) => void;
  onDone: () => void;
}> = ({ runId, element, runStatus, changesAllowed = false, onChangeRequest, onDone }) => {
  const [change, setChange] = useState('');
  const [scope, setScope] = useState<'run' | 'next_stage'>('run');
  const [sending, setSending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [kept, setKept] = useState<{ id: string; files: PickedSource[] } | null>(null);

  const going = !ENDED.has(runStatus ?? '');
  const asAChange = !going && runStatus === 'completed' && changesAllowed && !!onChangeRequest;

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!change.trim()) return;
    setSending(true);
    setProblem(null);
    try {
      const answer = await sayAtPickedElement(runId, {
        change: change.trim(), element, kind: asAChange ? 'change_request' : 'note', scope,
      });
      if (answer.kind === 'change_request') {
        onChangeRequest?.(answer.brief);
      } else {
        setKept({ id: answer.note.id ?? '', files: answer.note.element?.files ?? [] });
        setChange('');
      }
    } catch (error) {
      setProblem(detailOf(error));
    } finally {
      setSending(false);
    }
  };

  return (
    <aside aria-label="Say what should change here" className="flex w-full flex-col gap-2 rounded-lg border border-border/60 p-3 lg:w-80">
      <p className="text-xs text-text-muted">You pointed at</p>
      <p data-testid="picked-selector" className="break-all font-mono text-xs text-text-primary">{element.selector}</p>
      {element.text && (
        <p data-testid="picked-text" className="line-clamp-3 text-sm text-text-secondary">“{element.text}”</p>
      )}
      {!going && !asAChange ? (
        <p className="text-sm text-text-muted">
          This run has ended, so a note would reach no stage
          {runStatus === 'completed' ? '; with change requests on, this becomes a change request.' : '.'}
        </p>
      ) : (
        <form onSubmit={send} className="flex flex-col gap-2" aria-label="The change">
          <label htmlFor="picked-change" className="text-sm text-text-secondary">What should change here</label>
          <textarea id="picked-change" value={change} onChange={(e) => setChange(e.target.value)} rows={4} maxLength={2000}
            className="w-full rounded-lg bg-overlay border border-border/60 px-3 py-2 text-sm text-text-primary" />
          {going && (
            <fieldset className="flex flex-col gap-1 text-sm text-text-secondary">
              <legend className="sr-only">Who reads it</legend>
              <label className="flex items-center gap-2">
                <input type="radio" name="picked-scope" checked={scope === 'run'} onChange={() => setScope('run')} />
                For the whole run
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="picked-scope" checked={scope === 'next_stage'} onChange={() => setScope('next_stage')} />
                For the stage working now
              </label>
            </fieldset>
          )}
          {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
          {kept && (
            <p role="status" className="text-sm text-success">
              Kept as note {kept.id}
              {kept.files.length > 0 ? `; it names ${kept.files.map((f) => `${f.path}:${f.line}`).join(', ')}.` : '.'}
            </p>
          )}
          <div className="flex gap-2">
            <button type="submit" disabled={sending || !change.trim()}
              className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50">
              {asAChange ? 'Write a change request' : 'Send the note'}
            </button>
            <button type="button" onClick={onDone}
              className="px-3 py-1.5 rounded-lg border border-border/60 text-sm text-text-primary">
              Done
            </button>
          </div>
        </form>
      )}
    </aside>
  );
};
