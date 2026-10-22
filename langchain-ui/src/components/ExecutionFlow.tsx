import React, { useEffect, useRef, useState } from 'react';
import type { RunStage } from '../types';
import { Check, X, Clock, Loader2, Circle, ListChecks, ChevronDown, ChevronRight } from 'lucide-react';
import { describeStage, describeStatus } from '../lib/activity';

interface ExecutionFlowProps {
  stages: RunStage[];
  currentStage: string | null;
  isTerminal: boolean;
}

const TONE = {
  done:    { icon: Check,     dot: 'bg-success-bg text-success border-success/30',   text: 'text-success' },
  active:  { icon: Loader2,   dot: 'bg-accent-soft text-primary border-primary/40',   text: 'text-primary' },
  waiting: { icon: Clock,     dot: 'bg-warning-bg text-warning border-warning/40',   text: 'text-warning' },
  error:   { icon: X,         dot: 'bg-danger-bg text-danger border-danger/40',      text: 'text-danger' },
  idle:    { icon: Circle,    dot: 'bg-overlay text-text-muted border-border/50', text: 'text-text-muted' },
} as const;

/**
 * The steps this run has been through, in order, newest last.
 *
 * Every label here is written for someone who has never seen the pipeline. The
 * stage's own name (`principal_architect`, `specialist_backend_0`) is kept only
 * as a tooltip, because it is the right thing to quote in a bug report and the
 * wrong thing to lead with on screen.
 */
/**
 * The run's steps, split into the sprints they belong to.
 *
 * Stage names recur every sprint - `technical_lead`, `test_round_0` and every
 * specialist run once per sprint - so a flat list shows the same title several
 * times with no way to tell which pass it was. Sprint 0 is the planning that
 * happens before the first sprint opens.
 */
function bySprint(stages: RunStage[]): { sprint: number; stages: RunStage[] }[] {
  const groups: { sprint: number; stages: RunStage[] }[] = [];
  for (const stage of stages) {
    const last = groups[groups.length - 1];
    if (last && last.sprint === stage.sprint) last.stages.push(stage);
    else groups.push({ sprint: stage.sprint, stages: [stage] });
  }
  return groups;
}

const sprintTitle = (sprint: number) => (sprint === 0 ? 'Planning' : `Sprint ${sprint}`);

/** A duration as the steps list writes it: "28s", "1m 46s", "1h 4m". */
export function asDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

/** Finished steps a sprint shows one by one; past this, the earlier ones fold into one row. */
const SHOWN_FINISHED = 2;


export const ExecutionFlow: React.FC<ExecutionFlowProps> = ({ stages, currentStage, isTerminal }) => {
  const done = stages.filter((s) => s.status === 'completed').length;
  const groups = bySprint(stages);
  const scroller = useRef<HTMLDivElement>(null);
  // Sprints whose folded steps were opened.
  const [opened, setOpened] = useState<Set<number>>(new Set());
  // The step in flight shows how long it has been working, so the clock ticks.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (isTerminal) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isTerminal]);

  // The step in flight stays in view: the list grows downward, and a short
  // pane scrolled to its top showed only steps long finished.
  useEffect(() => {
    const box = scroller.current;
    const current = box?.querySelector<HTMLElement>('[data-current="true"]');
    if (box && current) box.scrollTop = Math.max(0, current.offsetTop - box.clientHeight / 2);
  }, [currentStage, stages.length]);

  return (
    <div className="glass-card rounded-2xl flex flex-col h-full overflow-hidden">
      <div className="flex-none px-4 py-3 border-b border-border/40 flex items-center gap-2.5">
        <span className="grid place-items-center h-7 w-7 rounded-lg bg-accent-soft">
          <ListChecks className="h-3.5 w-3.5 text-primary" />
        </span>
        <div className="min-w-0">
          <h2 className="font-semibold text-text-primary text-sm leading-none">Progress</h2>
          <p className="text-xs text-text-muted mt-1 leading-none">
            {stages.length > 0 ? `${done} of ${stages.length} steps finished` : 'Steps appear as they start'}
          </p>
        </div>
      </div>
      {stages.length > 0 && (
        <div className="flex-none h-1 bg-overlay" role="progressbar" aria-label="Steps finished"
             aria-valuemin={0} aria-valuemax={stages.length} aria-valuenow={done}>
          <div className="h-full bg-primary/70 transition-[width] duration-500" style={{ width: `${(done / stages.length) * 100}%` }} />
        </div>
      )}

      {stages.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 px-6 text-center">
          <span className="grid place-items-center h-10 w-10 rounded-xl bg-overlay">
            <Circle className="h-4 w-4 text-text-muted" />
          </span>
          <p className="text-sm text-text-secondary">Not started yet</p>
          <p className="text-xs text-text-muted leading-relaxed">
            Each step will show up here with a short note on what it does.
          </p>
        </div>
      ) : (
        <div ref={scroller} tabIndex={0} role="region" aria-label="The run's steps" className="flex-1 min-h-0 overflow-y-auto px-4 pb-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
          {groups.map((group) => {
            const groupDone = group.stages.filter((s) => s.status === 'completed').length;
            return (
              <section key={`sprint-${group.sprint}`} className="mb-5 last:mb-0">
                {/* Sticks while its steps scroll, flush with the top: the scroller
                    has no padding above it, so nothing shows through. Above the
                    steps' icons (z-10): level with them, each icon scrolled over it. */}
                <header className="sticky top-0 z-20 -mx-4 mb-2.5 flex items-baseline gap-2 bg-surface px-4 pb-1.5 pt-3">
                  <h3 className="text-xs font-semibold tracking-wide uppercase text-text-secondary">
                    {sprintTitle(group.sprint)}
                  </h3>
                  <span className="text-xs text-text-muted tabular-nums">
                    {groupDone}/{group.stages.length}
                  </span>
                  <span className="flex-1 h-px bg-border/40" aria-hidden />
                </header>

                <ol>
                  {(() => {
                    const finished = group.stages
                      .map((stage, index) => ({ stage, index }))
                      .filter(({ stage }) => describeStatus(stage.status).tone === 'done'
                        && !(stage.name === currentStage && !isTerminal) && stage.retry_count === 0);
                    const folded = opened.has(group.sprint) || finished.length <= SHOWN_FINISHED
                      ? [] : finished.slice(0, finished.length - 1);
                    if (!folded.length) return null;
                    const took = folded.reduce((sum, { stage }) => sum + (stage.duration_seconds ?? 0), 0);
                    return (
                      <li className="relative flex items-center gap-3" data-folded-summary="true">
                        <span className="absolute left-[9px] top-5 -bottom-1 w-px bg-border/40" aria-hidden />
                        <span className={`relative z-10 flex-none grid place-items-center h-5 w-5 rounded-full border ${TONE.done.dot}`}>
                          <Check className="h-3 w-3" />
                        </span>
                        <button
                          type="button"
                          aria-expanded={false}
                          onClick={() => setOpened(new Set([...opened, group.sprint]))}
                          className="min-w-0 flex-1 flex items-center gap-1 pb-2 pt-0.5 text-left text-[13px] text-text-secondary hover:text-text-primary"
                        >
                          <ChevronRight className="h-3 w-3 flex-none" aria-hidden />
                          {folded.length} earlier steps
                        </button>
                        <span className="flex-none pb-1.5 text-xs text-text-muted tabular-nums">{asDuration(took)}</span>
                      </li>
                    );
                  })()}
                  {opened.has(group.sprint) && (
                    <li>
                      <button
                        type="button"
                        aria-expanded={true}
                        onClick={() => setOpened(new Set([...opened].filter((sprint) => sprint !== group.sprint)))}
                        className="mb-1.5 ml-8 flex items-center gap-1 text-xs text-text-muted hover:text-text-primary"
                      >
                        <ChevronDown className="h-3 w-3" aria-hidden />
                        Fold the finished steps
                      </button>
                    </li>
                  )}
                  {group.stages.map((stage, index) => {
                    const isCurrent = stage.name === currentStage && !isTerminal;
                    // A stage the backend still calls "completed" while it is the
                    // current one is really the one in flight; showing it as finished
                    // makes the run look further along than it is.
                    const statusKey = isCurrent && stage.status === 'completed' ? 'running' : stage.status;
                    const status = describeStatus(statusKey);
                    const copy = describeStage(stage.name);
                    const tone = TONE[status.tone];
                    const Icon = tone.icon;
                    const isLast = index === group.stages.length - 1;

                    // A finished step is one line - its title and how long it took,
                    // its description on hover. Each took a title, a description and
                    // a status line, and the pane showed two steps at a time.
                    const finishedHere = group.stages.filter((other) => describeStatus(other.status).tone === 'done'
                      && !(other.name === currentStage && !isTerminal) && other.retry_count === 0);
                    const foldsHere = !opened.has(group.sprint) && finishedHere.length > SHOWN_FINISHED;
                    const place = finishedHere.indexOf(stage);
                    if (foldsHere && place >= 0 && place < finishedHere.length - 1) return null;
                    if (status.tone === 'done' && !isCurrent && stage.retry_count === 0) {
                      return (
                        <li key={`${group.sprint}-${stage.name}-${index}`} className="relative flex items-center gap-3" data-compact="true">
                          {!isLast && (
                            <span className="absolute left-[9px] top-5 -bottom-1 w-px bg-border/40" aria-hidden />
                          )}
                          <span className={`relative z-10 flex-none grid place-items-center h-5 w-5 rounded-full border ${tone.dot}`}>
                            <Icon className="h-3 w-3" />
                          </span>
                          <p className={`min-w-0 flex-1 truncate text-[13px] text-text-secondary ${isLast ? 'py-0.5' : 'pb-2 pt-0.5'}`} title={`${copy.blurb} (${stage.name})`}>
                            {copy.title}
                          </p>
                          {stage.duration_seconds !== null && (
                            <span className={`flex-none text-xs text-text-muted tabular-nums ${isLast ? '' : 'pb-1.5'}`}>
                              {asDuration(stage.duration_seconds)}
                            </span>
                          )}
                        </li>
                      );
                    }

                    return (
                      <li key={`${group.sprint}-${stage.name}-${index}`} className="relative flex gap-3" data-current={isCurrent ? 'true' : undefined}>
                        {!isLast && (
                          <span className="absolute left-[13px] top-7 bottom-0 w-px bg-border/40" aria-hidden />
                        )}

                        <span
                          className={`relative z-10 flex-none grid place-items-center h-7 w-7 rounded-full border ${tone.dot} ${
                            isCurrent ? 'ring-4 ring-primary/15' : ''
                          }`}
                        >
                          <Icon className={`h-3.5 w-3.5 ${status.tone === 'active' ? 'animate-spin' : ''}`} />
                        </span>

                        <div className={`min-w-0 flex-1 ${isLast ? 'pb-1' : 'pb-5'}`}>
                          <p className="text-[13px] font-semibold text-text-primary leading-snug" title={stage.name}>
                            {copy.title}
                          </p>
                          <p className="text-xs text-text-muted leading-relaxed mt-0.5">{copy.blurb}</p>
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            {/* "Stopped" and "Finished" are already the step's title, so
                                repeating them as the status underneath reads as a bug. */}
                            {status.label !== copy.title && (
                              <span className={`text-xs font-medium ${tone.text}`}>{status.label}</span>
                            )}
                            {isCurrent && stage.duration_seconds === null && stage.started_at && (
                              <span className="text-xs text-text-muted tabular-nums" data-testid="working-for">
                                {asDuration((now - Date.parse(stage.started_at)) / 1000)}
                              </span>
                            )}
                            {stage.duration_seconds !== null && (
                              <span className="text-xs text-text-muted tabular-nums">
                                {asDuration(stage.duration_seconds)}
                              </span>
                            )}
                            {/* Approvals are the step working, not repeating. Counting
                                them as retries told operators a run with two retries
                                had sixty-six. */}
                            {stage.approval_count > 0 && (
                              <span className="text-xs text-text-muted tabular-nums">
                                {stage.approval_count} {stage.approval_count === 1 ? 'approval' : 'approvals'}
                              </span>
                            )}
                            {stage.retry_count > 0 && (
                              <span className="text-xs text-warning">
                                started over {stage.retry_count === 1 ? 'once' : `${stage.retry_count} times`}
                              </span>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
};
