/**
 * The guided wizard view of a run.
 *
 * The classic dashboard shows the run as a flat list of stages and a log -
 * accurate, but it is the shape the *code* has, not the shape the *work* has.
 * A person following a build thinks in phases: "understand the product, design
 * it, build sprint one, build sprint two, done." This component presents the
 * run that way: a clickable rail of phases on the left, and a detail panel on
 * the right that shows what happened in the phase the reader has selected.
 *
 * The model it renders comes from `buildWizardModel(run, logs)` - a pure
 * function that re-derives the phases from the same event stream the classic
 * dashboard already holds. So the wizard can never drift out of sync with the
 * log, and it re-renders on every WebSocket merge without any extra fetching.
 *
 * The one thing it *does* fetch is the sprint plan artifact (to show how many
 * sprints were planned, and the goals of each). That is content, not in the
 * run's stage list, so it is fetched on demand and cached.
 */

import React, { useEffect, useMemo, useState } from 'react';
import type { LogEntry, RunStatusResponse } from '../types';
import { buildWizardModel } from '../lib/wizardData';
import type {
  SprintRevision,
  WizardReview,
  WizardSection,
  WizardStep,
  WizardSummary,
} from '../lib/wizardData';
import { fetchArtifactContent } from '../api';
import {
  Check,
  X,
  Clock,
  Loader2,
  Circle,
  ListChecks,
  FileText,
  Rocket,
  ClipboardList,
  BarChart3,
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  SkipForward,
  AlertCircle,
} from 'lucide-react';

/* ------------------------------------------------------------------ *
 * Props
 * ------------------------------------------------------------------ */

interface WizardDashboardProps {
  run: RunStatusResponse;
  logs: LogEntry[];
}

/* ------------------------------------------------------------------ *
 * Tone map (mirrors ExecutionFlow's, so the wizard reads the same)
 * ------------------------------------------------------------------ */

const TONE = {
  done:    { icon: Check,     dot: 'bg-success/15 text-success border-success/30',   text: 'text-success',  glow: 'status-success' },
  active:  { icon: Loader2,   dot: 'bg-primary/15 text-primary border-primary/40',   text: 'text-primary',  glow: 'status-running' },
  waiting: { icon: Clock,     dot: 'bg-warning/15 text-warning border-warning/40',   text: 'text-warning',  glow: 'status-warning' },
  error:   { icon: X,         dot: 'bg-danger/15 text-danger border-danger/40',      text: 'text-danger',   glow: 'status-danger' },
  idle:    { icon: Circle,    dot: 'bg-white/[0.04] text-text-muted border-border/50', text: 'text-text-muted', glow: '' },
} as const;

const toneFor = (status: string) => TONE[(status as keyof typeof TONE) ?? 'idle'] ?? TONE.idle;

/* ------------------------------------------------------------------ *
 * Section icons
 * ------------------------------------------------------------------ */

const SECTION_ICON = {
  intake:  FileText,
  design:  ClipboardList,
  sprint:  Rocket,
  summary: BarChart3,
} as const;

/* ------------------------------------------------------------------ *
 * The component
 * ------------------------------------------------------------------ */

export const WizardDashboard: React.FC<WizardDashboardProps> = ({ run, logs }) => {
  // The model is re-derived on every render. It is a pure function over
  // (run, logs), and a run caps at 5000 events, so this is cheap. Re-deriving
  // (rather than caching) means the wizard can never drift out of sync with
  // the log the dashboard is reading.
  const model = useMemo(() => buildWizardModel(run, logs), [run, logs]);

  // The section the reader has selected. It starts at the section the run is
  // in right now (or the last one it reached), and the reader can click any
  // phase in the rail to look at it.
  const [selectedId, setSelectedId] = useState<string | null>(model.currentSectionId);

  // Keep the selection in sync with the run: if the run moves to a new section
  // and the reader has not manually selected anything else, follow it.
  useEffect(() => {
    if (model.currentSectionId) {
      setSelectedId((prev) => prev ?? model.currentSectionId);
    }
  }, [model.currentSectionId]);

  const selected =
    model.sections.find((s) => s.id === selectedId) ??
    model.sections[model.sections.length - 1] ??
    null;

  // The sprint plan, fetched on demand. It is content (the goals of each
  // planned sprint), not in the run's stage list, so we fetch it. We cache it
  // by run id so a re-render does not re-fetch.
  const [sprintPlan, setSprintPlan] = useState<{ goals: string[]; count: number } | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchArtifactContent(run.run_id, 'sprint-plan').then((content) => {
      if (cancelled || !content) return;
      try {
        const parsed = JSON.parse(content);
        const sprints = parsed?.sprints ?? [];
        setSprintPlan({
          goals: sprints.map((s: { goal?: string }) => s.goal ?? ''),
          count: sprints.length,
        });
      } catch {
        setSprintPlan(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [run.run_id]);

  return (
    <div className="animate-fade-in flex flex-col gap-4 xl:min-h-[calc(100vh-11rem)]">
      {/* The phase rail: the run's phases in order, clickable. */}
      <div className="glass-card rounded-2xl flex flex-col overflow-hidden">
        <div className="flex-none px-4 py-3 border-b border-border/40 flex items-center gap-2.5">
          <span className="grid place-items-center h-7 w-7 rounded-lg bg-primary/15">
            <ListChecks className="h-3.5 w-3.5 text-primary" />
          </span>
          <div className="min-w-0">
            <h3 className="font-semibold text-white text-sm leading-none">The build, in phases</h3>
            <p className="text-[11px] text-text-muted mt-1 leading-none">
              Click a phase to see what happened in it.
            </p>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
          <ol className="flex flex-col gap-1">
            {model.sections.map((section, index) => {
              const isSelected = section.id === selected?.id;
              const isLast = index === model.sections.length - 1;
              const tone = toneFor(section.status);
              const Icon = SECTION_ICON[section.kind];
              const isCurrent = section.id === model.currentSectionId && !isTerminal(run.status);

              return (
                <li key={section.id} className="relative">
                  {!isLast && (
                    <span className="absolute left-[15px] top-8 bottom-0 w-px bg-border/40" aria-hidden />
                  )}
                  <button
                    onClick={() => setSelectedId(section.id)}
                    className={`relative z-10 w-full flex items-start gap-3 rounded-xl px-2 py-2 text-left transition-colors ${
                      isSelected ? 'bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-white/[0.03]'
                    }`}
                  >
                    <span
                      className={`relative z-10 flex-none grid place-items-center h-8 w-8 rounded-full border ${tone.dot} ${
                        isCurrent ? 'ring-4 ring-primary/15' : ''
                      }`}
                    >
                      <Icon className={`h-4 w-4 ${section.status === 'active' ? 'animate-spin' : ''}`} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-[13px] font-semibold text-white leading-snug">
                          {section.title}
                        </p>
                        {section.kind === 'sprint' && (section.revisions?.length ?? 0) > 1 && (
                          <span className="text-[10px] font-medium text-warning bg-warning/10 border border-warning/30 rounded-full px-1.5 py-0.5">
                            {section.revisions?.length} passes
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">
                        {section.blurb}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <span className={`text-[11px] font-medium ${tone.text}`}>
                          {section.statusLabel}
                        </span>
                      </div>
                    </div>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      {/* The detail panel: what happened in the selected phase. */}
      <div className="glass-card-strong rounded-2xl flex flex-col overflow-hidden xl:flex-1 xl:min-h-[28rem]">
        {selected ? (
          <SectionDetail
            section={selected}
            run={run}
            summary={model.summary}
            sprintPlan={sprintPlan}
          />
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 px-6 text-center">
            <span className="grid place-items-center h-10 w-10 rounded-xl bg-white/[0.03]">
              <Circle className="h-4 w-4 text-text-muted" />
            </span>
            <p className="text-sm text-text-secondary">Nothing to show yet</p>
            <p className="text-xs text-text-muted leading-relaxed">
              Phases will appear here as the run moves through them.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * The detail panel for a selected section
 * ------------------------------------------------------------------ */

interface SectionDetailProps {
  section: WizardSection;
  run: RunStatusResponse;
  summary: WizardSummary;
  sprintPlan: { goals: string[]; count: number } | null;
}

const SectionDetail: React.FC<SectionDetailProps> = ({ section, run, summary, sprintPlan }) => {
  const Icon = SECTION_ICON[section.kind];
  const tone = toneFor(section.status);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-none px-5 py-4 border-b border-border/40 flex items-center gap-3">
        <span className={`grid place-items-center h-9 w-9 rounded-xl ${tone.dot}`}>
          <Icon className={`h-4.5 w-4.5 ${section.status === 'active' ? 'animate-spin' : ''}`} />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-white text-base leading-none">{section.title}</h3>
          <p className="text-[12px] text-text-muted mt-1 leading-none">{section.blurb}</p>
        </div>
        <span className={`text-[12px] font-medium ${tone.text}`}>{section.statusLabel}</span>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
        {section.kind === 'intake' && <IntakeDetail section={section} />}
        {section.kind === 'design' && <DesignDetail section={section} run={run} />}
        {section.kind === 'sprint' && <SprintDetail section={section} />}
        {section.kind === 'summary' && <SummaryDetail summary={summary} sprintPlan={sprintPlan} run={run} />}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * Intake detail: what the run understood about the product
 * ------------------------------------------------------------------ */

const IntakeDetail: React.FC<{ section: WizardSection }> = ({ section }) => {
  const steps = section.steps ?? [];
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-text-secondary leading-relaxed">
        The run read your document and worked out what you want built and who it is for.
      </p>
      {steps.length > 0 && (
        <div className="flex flex-col gap-2">
          {steps.map((step, i) => (
            <StepCard key={`${step.name}-${i}`} step={step} isLast={i === steps.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * Design detail: the decisions made on how the product works
 * ------------------------------------------------------------------ */

const DesignDetail: React.FC<{ section: WizardSection; run: RunStatusResponse }> = ({ section, run }) => {
  const steps = section.steps ?? [];
  // The key decisions are the stages that produced a document or a review:
  // the technical specification, the architecture review, and the reader's
  // review of the plan.
  const decisionSteps = steps.filter((s) =>
    ['technical_specification', 'architecture_review', 'user_review_specification', 'tools_models', 'stack_selector'].includes(s.name)
  );

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-text-secondary leading-relaxed">
        The run compared the options, chose the technology, and wrote the technical plan.
        These are the decisions it made on how the product works.
      </p>

      {decisionSteps.length > 0 && (
        <div className="flex flex-col gap-2">
          {decisionSteps.map((step, i) => (
            <StepCard key={`${step.name}-${i}`} step={step} isLast={i === decisionSteps.length - 1} showEvents />
          ))}
        </div>
      )}

      {/* The reader's review of the plan, if the run paused for it. */}
      {run.reviews?.filter((r) => r.point === 'technical_specification').map((review) => (
        <ReviewCard
          key={review.point}
          review={{
            point: review.point,
            revision: review.revision,
            requestedAt: review.updated_at,
            outcome: review.status === 'approved' ? 'approved' : review.status === 'changes_requested' ? 'changes' : review.status === 'skipped' ? 'skipped' : 'pending',
            comment: review.comments,
          }}
        />
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * Sprint detail: the tasks, tests, and review of one sprint
 * ------------------------------------------------------------------ */

const SprintDetail: React.FC<{ section: WizardSection }> = ({ section }) => {
  const revisions = section.revisions ?? [];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-text-secondary leading-relaxed">
        Building, testing and reviewing this chunk of the product.
        {revisions.length > 1 && (
          <span className="text-warning">
            {' '}This sprint was sent back {revisions.length - 1} time{revisions.length - 1 === 1 ? '' : 's'} for changes; each pass is shown below the last.
          </span>
        )}
      </p>

      {revisions.map((revision) => (
        <RevisionCard key={revision.number} revision={revision} />
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * A single revision (pass) of a sprint
 * ------------------------------------------------------------------ */

const RevisionCard: React.FC<{ revision: SprintRevision }> = ({ revision }) => {
  const steps = revision.steps;
  const review = revision.review;

  return (
    <div className="rounded-xl border border-border/40 overflow-hidden">
      {/* Revision header */}
      <div className="px-4 py-2.5 bg-white/[0.02] border-b border-border/40 flex items-center gap-2">
        <span className="text-[11px] font-semibold tracking-wide uppercase text-text-secondary">
          {revision.number === 1 ? 'First pass' : `Pass ${revision.number}`}
        </span>
        {revision.revisionComment && (
          <span className="text-[11px] text-warning flex items-center gap-1">
            <ThumbsDown className="h-3 w-3" />
            Sent back for changes
          </span>
        )}
      </div>

      {/* The rejection comment that started this revision (if any) */}
      {revision.revisionComment && (
        <div className="px-4 py-3 bg-warning/[0.04] border-b border-warning/20">
          <div className="flex items-start gap-2">
            <MessageSquare className="h-3.5 w-3.5 text-warning mt-0.5 flex-none" />
            <div className="min-w-0">
              <p className="text-[11px] font-medium text-warning">Review comment</p>
              <p className="text-[12px] text-text-secondary leading-relaxed mt-1 whitespace-pre-wrap">
                {revision.revisionComment}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* The steps of this pass */}
      <div className="px-4 py-3 flex flex-col gap-2">
        {steps.map((step, i) => (
          <StepCard key={`${step.name}-${i}`} step={step} isLast={i === steps.length - 1} showEvents />
        ))}
      </div>

      {/* The review at the end of this pass (if any) */}
      {review && <ReviewCard review={review} />}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * A single step, with its events
 * ------------------------------------------------------------------ */

const StepCard: React.FC<{ step: WizardStep; isLast: boolean; showEvents?: boolean }> = ({
  step,
  isLast,
  showEvents,
}) => {
  const tone = toneFor(step.status);
  const Icon = tone.icon;
  const [expanded, setExpanded] = useState(false);
  const hasEvents = step.events.length > 0;

  return (
    <div className={`rounded-lg border ${isLast ? 'border-border/40' : 'border-border/30'} overflow-hidden`}>
      <button
        onClick={() => hasEvents && setExpanded((e) => !e)}
        className={`w-full flex items-start gap-2.5 px-3 py-2 text-left ${hasEvents ? 'cursor-pointer hover:bg-white/[0.02]' : 'cursor-default'}`}
      >
        <span className={`flex-none grid place-items-center h-6 w-6 rounded-full border ${tone.dot} mt-0.5`}>
          <Icon className={`h-3 w-3 ${step.status === 'active' ? 'animate-spin' : ''}`} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-[12px] font-semibold text-white leading-snug">{step.title}</p>
            {step.durationSeconds !== null && (
              <span className="text-[10px] text-text-muted tabular-nums">
                {step.durationSeconds < 60
                  ? `${Math.round(step.durationSeconds)}s`
                  : `${Math.floor(step.durationSeconds / 60)}m ${Math.round(step.durationSeconds % 60)}s`}
              </span>
            )}
          </div>
          <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">{step.blurb}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-[10px] font-medium ${tone.text}`}>{step.statusLabel}</span>
            {hasEvents && (
              <span className="text-[10px] text-text-muted tabular-nums">
                {step.events.length} {step.events.length === 1 ? 'note' : 'notes'}
              </span>
            )}
          </div>
        </div>
      </button>

      {/* The events that happened while this step was current */}
      {showEvents && expanded && hasEvents && (
        <div className="px-3 pb-3 pl-[3.25rem]">
          <div className="flex flex-col gap-1.5">
            {step.events.map((event, i) => (
              <EventNote key={`${event.event_id}-${i}`} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * A single event note (a log line, a tool call, a review, etc.)
 * ------------------------------------------------------------------ */

const EventNote: React.FC<{ event: LogEntry }> = ({ event }) => {
  const type = event.event_type;
  const isReview = type === 'review_request';
  const isApproval = type === 'approval_request';
  const isError = type === 'error' || (event.metadata?.failed === true);
  const isTool = type === 'tool_call' || type === 'tool_result';

  const Icon = isError ? AlertCircle : isReview ? MessageSquare : isApproval ? Clock : isTool ? Loader2 : Circle;
  const color = isError ? 'text-danger' : isReview ? 'text-warning' : isApproval ? 'text-primary' : 'text-text-muted';

  return (
    <div className="flex items-start gap-2 animate-activity-in">
      <Icon className={`h-3 w-3 ${color} mt-0.5 flex-none`} />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-text-secondary leading-relaxed break-words">{event.message}</p>
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * A review card (the reader's review of a sprint or the plan)
 * ------------------------------------------------------------------ */

const ReviewCard: React.FC<{ review: WizardReview }> = ({ review }) => {
  const outcome = review.outcome;
  const config = {
    approved: { icon: ThumbsUp, label: 'Approved', color: 'text-success', bg: 'bg-success/[0.04]', border: 'border-success/20' },
    changes:  { icon: ThumbsDown, label: 'Sent back for changes', color: 'text-warning', bg: 'bg-warning/[0.04]', border: 'border-warning/20' },
    skipped:  { icon: SkipForward, label: 'Skipped', color: 'text-text-muted', bg: 'bg-white/[0.02]', border: 'border-border/40' },
    pending:  { icon: Clock, label: 'Waiting for you', color: 'text-primary', bg: 'bg-primary/[0.04]', border: 'border-primary/20' },
  }[outcome] ?? { icon: Clock, label: 'Waiting for you', color: 'text-primary', bg: 'bg-primary/[0.04]', border: 'border-primary/20' };
  const Icon = config.icon;

  return (
    <div className={`rounded-lg border ${config.border} ${config.bg} px-4 py-3`}>
      <div className="flex items-center gap-2">
        <Icon className={`h-3.5 w-3.5 ${config.color}`} />
        <span className={`text-[12px] font-semibold ${config.color}`}>
          {config.label}
          {review.revision > 0 && ` · revision ${review.revision}`}
        </span>
      </div>
      {review.comment && (
        <p className="text-[12px] text-text-secondary leading-relaxed mt-2 whitespace-pre-wrap">
          {review.comment}
        </p>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * Summary detail: the numbers
 * ------------------------------------------------------------------ */

const SummaryDetail: React.FC<{
  summary: WizardSummary;
  sprintPlan: { goals: string[]; count: number } | null;
  run: RunStatusResponse;
}> = ({ summary, sprintPlan, run }) => {
  const planned = sprintPlan?.count ?? summary.sprintsPlanned;

  const stats = [
    { label: 'Sprints planned', value: planned, icon: ClipboardList, color: 'text-primary' },
    { label: 'Sprints executed', value: summary.sprintsExecuted, icon: Rocket, color: 'text-success' },
    { label: 'Revisions', value: summary.revisionsTotal, icon: ThumbsDown, color: 'text-warning' },
    { label: 'Test runs', value: summary.testRuns, icon: ListChecks, color: 'text-primary' },
    { label: 'Defects found', value: summary.defectsFound, icon: AlertCircle, color: 'text-danger' },
    { label: 'Documents', value: summary.documentsProduced, icon: FileText, color: 'text-text-secondary' },
    { label: 'Approvals passed', value: summary.approvalsPassed, icon: ThumbsUp, color: 'text-success' },
    { label: 'Reviews approved', value: summary.reviewsApproved, icon: ThumbsUp, color: 'text-success' },
    { label: 'Reviews sent back', value: summary.reviewsChanges, icon: ThumbsDown, color: 'text-warning' },
    { label: 'Reviews pending', value: summary.reviewsPending, icon: Clock, color: 'text-primary' },
  ];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-text-secondary leading-relaxed">
        How the build went, in numbers.
      </p>

      {/* The stats grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className="rounded-lg border border-border/40 bg-white/[0.02] px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <Icon className={`h-3 w-3 ${stat.color}`} />
                <span className="text-[10px] text-text-muted leading-none">{stat.label}</span>
              </div>
              <p className={`text-lg font-semibold ${stat.color} mt-1 tabular-nums`}>{stat.value}</p>
            </div>
          );
        })}
      </div>

      {/* The goals of each planned sprint */}
      {sprintPlan && sprintPlan.goals.length > 0 && (
        <div className="rounded-lg border border-border/40 bg-white/[0.02] px-4 py-3">
          <p className="text-[11px] font-semibold tracking-wide uppercase text-text-secondary mb-2">
            Planned sprints
          </p>
          <ol className="flex flex-col gap-1.5">
            {sprintPlan.goals.map((goal, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-[11px] font-semibold text-primary tabular-nums mt-0.5">{i + 1}.</span>
                <p className="text-[12px] text-text-secondary leading-relaxed">{goal}</p>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* The run's error, if it stopped */}
      {run.error && (
        <div className="rounded-lg border border-danger/20 bg-danger/[0.04] px-4 py-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-3.5 w-3.5 text-danger" />
            <span className="text-[12px] font-semibold text-danger">The run stopped</span>
          </div>
          <p className="text-[12px] text-text-secondary leading-relaxed mt-2 whitespace-pre-wrap">{run.error}</p>
        </div>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 * Helpers
 * ------------------------------------------------------------------ */

const isTerminal = (status: string) => ['completed', 'failed', 'cancelled'].includes(status);
