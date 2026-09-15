import React from 'react';
import type { RunStage } from '../types';
import { Check, X, Clock, Loader2, Circle, ListChecks } from 'lucide-react';
import { describeStage, describeStatus } from '../lib/activity';

interface ExecutionFlowProps {
  stages: RunStage[];
  currentStage: string | null;
  isTerminal: boolean;
}

const TONE = {
  done:    { icon: Check,     dot: 'bg-success/15 text-success border-success/30',   text: 'text-success' },
  active:  { icon: Loader2,   dot: 'bg-primary/15 text-primary border-primary/40',   text: 'text-primary' },
  waiting: { icon: Clock,     dot: 'bg-warning/15 text-warning border-warning/40',   text: 'text-warning' },
  error:   { icon: X,         dot: 'bg-danger/15 text-danger border-danger/40',      text: 'text-danger' },
  idle:    { icon: Circle,    dot: 'bg-white/[0.04] text-text-muted border-border/50', text: 'text-text-muted' },
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

export const ExecutionFlow: React.FC<ExecutionFlowProps> = ({ stages, currentStage, isTerminal }) => {
  const done = stages.filter((s) => s.status === 'completed').length;
  const groups = bySprint(stages);

  return (
    <div className="glass-card rounded-2xl flex flex-col h-full overflow-hidden">
      <div className="flex-none px-4 py-3 border-b border-border/40 flex items-center gap-2.5">
        <span className="grid place-items-center h-7 w-7 rounded-lg bg-primary/15">
          <ListChecks className="h-3.5 w-3.5 text-primary" />
        </span>
        <div className="min-w-0">
          <h3 className="font-semibold text-white text-sm leading-none">Progress</h3>
          <p className="text-[11px] text-text-muted mt-1 leading-none">
            {stages.length > 0 ? `${done} of ${stages.length} steps finished` : 'Steps appear as they start'}
          </p>
        </div>
      </div>

      {stages.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 px-6 text-center">
          <span className="grid place-items-center h-10 w-10 rounded-xl bg-white/[0.03]">
            <Circle className="h-4 w-4 text-text-muted" />
          </span>
          <p className="text-sm text-text-secondary">Not started yet</p>
          <p className="text-xs text-text-muted leading-relaxed">
            Each step will show up here with a short note on what it does.
          </p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
          {groups.map((group) => {
            const groupDone = group.stages.filter((s) => s.status === 'completed').length;
            return (
              <section key={`sprint-${group.sprint}`} className="mb-5 last:mb-0">
                <header className="flex items-baseline gap-2 mb-2.5">
                  <h4 className="text-[11px] font-semibold tracking-wide uppercase text-text-secondary">
                    {sprintTitle(group.sprint)}
                  </h4>
                  <span className="text-[11px] text-text-muted tabular-nums">
                    {groupDone}/{group.stages.length}
                  </span>
                  <span className="flex-1 h-px bg-border/40" aria-hidden />
                </header>

                <ol>
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

                    return (
                      <li key={`${group.sprint}-${stage.name}-${index}`} className="relative flex gap-3">
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
                          <p className="text-[13px] font-semibold text-white leading-snug" title={stage.name}>
                            {copy.title}
                          </p>
                          <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">{copy.blurb}</p>
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            {/* "Stopped" and "Finished" are already the step's title, so
                                repeating them as the status underneath reads as a bug. */}
                            {status.label !== copy.title && (
                              <span className={`text-[11px] font-medium ${tone.text}`}>{status.label}</span>
                            )}
                            {stage.duration_seconds !== null && (
                              <span className="text-[11px] text-text-muted tabular-nums">
                                {stage.duration_seconds < 60
                                  ? `${Math.round(stage.duration_seconds)}s`
                                  : `${Math.floor(stage.duration_seconds / 60)}m ${Math.round(stage.duration_seconds % 60)}s`}
                              </span>
                            )}
                            {/* Approvals are the step working, not repeating. Counting
                                them as retries told operators a run with two retries
                                had sixty-six. */}
                            {stage.approval_count > 0 && (
                              <span className="text-[11px] text-text-muted tabular-nums">
                                {stage.approval_count} {stage.approval_count === 1 ? 'approval' : 'approvals'}
                              </span>
                            )}
                            {stage.retry_count > 0 && (
                              <span className="text-[11px] text-warning">
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
