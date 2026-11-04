/**
 * Settings -> Lessons: what the harness proposes to tell every later run, with
 * the evidence for each. Nothing reaches a prompt until it is approved here.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useFeedback } from './Feedback';

interface Lesson {
  id: string;
  stack: string;
  role: string;
  trigger: string;
  rule: string;
  evidence_runs: number;
  evidence?: string[];
  source: string;
  status: 'proposed' | 'approved' | 'rejected';
}

const VIEWS: Array<[Lesson['status'], string]> = [['proposed', 'To decide'], ['approved', 'In use'], ['rejected', 'Rejected']];
const EMPTY: Record<Lesson['status'], string> = {
  proposed: 'Nothing waits for a decision.',
  approved: 'No lesson is in use yet.',
  rejected: 'No lesson has been rejected.',
};

export const LessonsPanel: React.FC = () => {
  const [lessons, setLessons] = useState<Lesson[] | null>(null);
  const [view, setView] = useState<Lesson['status'] | null>(null);
  const { notify } = useFeedback();

  const load = useCallback(() => {
    api.get('/lessons').then((res) => setLessons(res.data.lessons ?? [])).catch(() => setLessons([]));
  }, []);
  useEffect(load, [load]);

  const decide = async (lesson: Lesson, verb: 'approve' | 'reject') => {
    try {
      await api.post(`/lessons/${lesson.id}/${verb}`);
      load();
    } catch {
      notify('Only an administrator can decide a lesson.');
    }
  };

  // Opens on what waits for a decision; with nothing waiting, on what is in use.
  const shownStatus: Lesson['status'] = view ?? (lessons?.some((lesson) => lesson.status === 'proposed') ? 'proposed' : 'approved');
  const shown = (lessons ?? [])
    .filter((lesson) => lesson.status === shownStatus)
    .sort((a, b) => b.evidence_runs - a.evidence_runs);

  return (
    <section className="glass-card rounded-2xl p-5" aria-labelledby="lessons-heading">
      <h2 id="lessons-heading" className="text-base font-semibold text-text-primary">Lessons from earlier runs</h2>
      <p className="text-sm text-text-secondary mt-0.5 mb-4">
        A lesson is added to the instructions of every later run on its stack only once you approve it.
      </p>
      {lessons === null ? (
        <p role="status" className="text-sm text-text-muted">Loading…</p>
      ) : lessons.length === 0 ? (
        <p className="text-sm text-text-muted">No lessons yet. The loop proposes one when the same failure recurs across runs.</p>
      ) : (
        <>
          <div role="group" aria-label="Show" className="mb-3 inline-flex gap-1 rounded-lg border border-border p-1 text-sm">
            {VIEWS.map(([status, label]) => (
              <button
                key={status}
                type="button"
                aria-pressed={shownStatus === status}
                onClick={() => setView(status)}
                className={`rounded-md px-3 py-1 ${shownStatus === status ? 'bg-accent-soft font-medium text-primary' : 'text-text-secondary hover:text-text-primary'}`}
              >
                {label} ({lessons.filter((lesson) => lesson.status === status).length})
              </button>
            ))}
          </div>
          {shown.length === 0 && <p className="text-sm text-text-muted">{EMPTY[shownStatus]}</p>}
          <ul className="space-y-3">
          {shown.map((lesson) => (
            <li key={lesson.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
                <span className="font-mono">{lesson.id}</span>
                <span>{lesson.stack}</span>
                <span>seen in {lesson.evidence_runs} run{lesson.evidence_runs === 1 ? '' : 's'}</span>
              </div>
              <p className="mt-1 text-sm text-text-primary">{lesson.rule}</p>
              <p className="mt-0.5 text-xs text-text-muted break-words">Answers: {lesson.trigger}</p>
              {(lesson.evidence ?? []).length > 0 && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-text-secondary">What was recorded ({lesson.evidence!.length})</summary>
                  {lesson.evidence!.map((quote) => (
                    <p key={quote} className="mt-0.5 text-xs text-text-muted break-words">{quote}</p>
                  ))}
                </details>
              )}
              {lesson.status === 'proposed' && (
                <div className="mt-2 flex gap-2">
                  <button type="button" onClick={() => decide(lesson, 'approve')} className="px-3 py-1 rounded-lg bg-primary text-primary-foreground text-sm font-medium">
                    Approve
                  </button>
                  <button type="button" onClick={() => decide(lesson, 'reject')} className="px-3 py-1 rounded-lg border border-border text-sm text-text-secondary hover:bg-overlay">
                    Reject
                  </button>
                </div>
              )}
            </li>
          ))}
          </ul>
        </>
      )}
    </section>
  );
};
