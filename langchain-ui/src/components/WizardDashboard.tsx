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
 * It is a pure renderer. The model it draws comes from `GET /runs/{id}/wizard`
 * - the server walks the run's event history and graph state and returns a
 * finished `WizardModel`. This used to be derived here in the browser (in
 * `lib/wizardData.ts`) from the same events, which meant two readers of one
 * truth free to drift apart; the server is now the single source and the view
 * only fetches and paints.
 *
 * The one thing it still fetches on demand is the sprint plan *artifact* (to
 * show how many sprints were planned and their goals). That is document
 * content, not run structure, so it does not belong in the wizard model.
 */

import React, { useEffect, useState } from 'react';
import type {
  RunStatusResponse,
  SprintRevision,
  WizardModel,
  WizardNote,
  WizardReview,
  WizardSection,
  WizardStep,
  WizardSummary,
} from '../types';
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
  /** The finished wizard model, fetched by the parent page. */
  model: WizardModel | null;
}

/* ------------------------------------------------------------------ *
 * Tone map (mirrors ExecutionFlow's, so the wizard reads the same)
 * ------------------------------------------------------------------ */

const TONE = {
  done:    { icon: Check,     dot: 'bg-success-bg text-success border-success/30',   text: 'text-success',  glow: 'status-success' },
  active:  { icon: Loader2,   dot: 'bg-accent-soft text-primary border-primary/40',   text: 'text-primary',  glow: 'status-running' },
  waiting: { icon: Clock,     dot: 'bg-warning-bg text-warning border-warning/40',   text: 'text-warning',  glow: 'status-warning' },
  error:   { icon: X,         dot: 'bg-danger-bg text-danger border-danger/40',      text: 'text-danger',   glow: 'status-danger' },
  idle:    { icon: Circle,    dot: 'bg-overlay text-text-muted border-border/50', text: 'text-text-muted', glow: '' },
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

const isTerminal = (status: string) => ['completed', 'failed', 'cancelled'].includes(status);

/* ------------------------------------------------------------------ *
 * The component
 * ------------------------------------------------------------------ */

export const WizardDashboard: React.FC<WizardDashboardProps> = ({ run, model }) => {
  // The section the reader has selected. It starts at the section the run is
  // in right now (or the last one it reached), and the reader can click any
  // phase in the rail to look at it.
  const [selectedId, setSelectedId] = useState<string | null>(
    model?.current_section_id ?? model?.sections[model.sections.length - 1]?.id ?? null
  );

  // Keep the selection in sync with the run: if the run moves to a new section
  // and the reader has not manually selected anything else, follow it.
  const currentSectionId = model?.current_section_id ?? null;
  useEffect(() => {
    if (currentSectionId) {
      setSelectedId((prev) => prev ?? currentSectionId);
    }
  }, [currentSectionId]);

  // The sprint plan, fetched on demand. It is content (the goals of each
  // planned sprint), not in the wizard model, so we fetch it. We cache it by
  // run id so a re-render does not re-fetch.
  const [sprintPlan, setSprintPlan] = useState<{ goals: string[]; count: number } | null>(null);
  useEffect(() => {
    let cancelled = false;
    setSprintPlan(null);
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
        // The plan artifact is not JSON we understand; the summary falls back
        // to the server's own `sprints_planned` number.
        setSprintPlan(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [run.run_id]);

  const sections = model?.sections ?? [];
  const selected =
    sections.find((s) => s.id === selectedId) ?? sections[sections.length - 1] ?? null;

  if (!model || sections.length === 0) {
    return (
      <div className="animate-fade-in flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
        <Loader2 className="h-5 w-5 text-text-muted animate-spin" />
        <p className="text-sm text-text-secondary">Loading the build phases…</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in flex flex-col gap-4 xl:min-h-[calc(100vh-11rem)]">
      {/* The phase rail: the run's phases in order, clickable. */}
      <div className="glass-card rounded-2xl flex flex-col overflow-hidden">
        <div className="flex-none px-4 py-3 border-b border-border/40 flex items-center gap-2.5">
          <span className="grid place-items-center h-7 w-7 rounded-lg bg-accent-soft">
            <ListChecks className="h-3.5 w-3.5 text-primary" />
          </span>
          <div className="min-w-0">
            <h2 className="font-semibold text-text-primary text-sm leading-none">The build, in phases</h2>
            <p className="text-[11px] text-text-muted mt-1 leading-none">
              Click a phase to see what happened in it.
            </p>
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
          <ol className="flex flex-col gap-1">
            {sections.map((section, index) => {
              const isSelected = section.id === selected?.id;
              const isLast = index === sections.length - 1;
              const tone = toneFor(section.status);
              const Icon = SECTION_ICON[section.kind];
              const isCurrent = section.id === model.current_section_id && !isTerminal(run.status);

              return (
                <li key={section.id} className="relative">
                  {!isLast && (
                    <span className="absolute left-[15px] top-8 bottom-0 w-px bg-border/40" aria-hidden />
                  )}
                  <button
                    onClick={() => setSelectedId(section.id)}
                    className={`relative z-10 w-full flex items-start gap-3 rounded-xl px-2 py-2 text-left transition-colors ${
                      isSelected ? 'bg-accent-soft ring-1 ring-primary/30' : 'hover:bg-overlay'
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
                        <p className="text-[13px] font-semibold text-text-primary leading-snug">
                          {section.title}
                        </p>
                        {section.kind === 'sprint' && section.revisions.length > 1 && (
                          <span className="text-[10px] font-medium text-warning bg-warning-bg border border-warning/30 rounded-full px-1.5 py-0.5">
                            {section.revisions.length} passes
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">
                        {section.blurb}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <span className={`text-[11px] font-medium ${tone.text}`}>
                          {section.status_label}
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
            <span className="grid place-items-center h-10 w-10 rounded-xl bg-overlay">
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
          <h2 className="font-semibold text-text-primary text-base leading-none">{section.title}</h2>
          <p className="text-[12px] text-text-muted mt-1 leading-none">{section.blurb}</p>
        </div>
        <span className={`text-[12px] font-medium ${tone.text}`}>{section.status_label}</span>
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
  const steps = section.steps;
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
  const steps = section.steps;
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
            requested_at: review.updated_at,
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
  const revisions = section.revisions;

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
      <div className="px-4 py-2.5 bg-overlay border-b border-border/40 flex items-center gap-2">
        <span className="text-[11px] font-semibold tracking-wide uppercase text-text-secondary">
          {revision.number === 1 ? 'First pass' : `Pass ${revision.number}`}
        </span>
        {revision.rejection_comment && (
          <span className="text-[11px] text-warning flex items-center gap-1">
            <ThumbsDown className="h-3 w-3" />
            Sent back for changes
          </span>
        )}
      </div>

      {/* The rejection comment that started this revision (if any) */}
      {revision.rejection_comment && (
        <div className="px-4 py-3 bg-warning/[0.04] border-b border-warning/20">
          <div className="flex items-start gap-2">
            <MessageSquare className="h-3.5 w-3.5 text-warning mt-0.5 flex-none" />
            <div className="min-w-0">
              <p className="text-[11px] font-medium text-warning">Review comment</p>
              <p className="text-[12px] text-text-secondary leading-relaxed mt-1 whitespace-pre-wrap">
                {revision.rejection_comment}
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
        className={`w-full flex items-start gap-2.5 px-3 py-2 text-left ${hasEvents ? 'cursor-pointer hover:bg-overlay' : 'cursor-default'}`}
      >
        <span className={`flex-none grid place-items-center h-6 w-6 rounded-full border ${tone.dot} mt-0.5`}>
          <Icon className={`h-3 w-3 ${step.status === 'active' ? 'animate-spin' : ''}`} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-[12px] font-semibold text-text-primary leading-snug">{step.title}</p>
            {step.duration_seconds !== null && (
              <span className="text-[10px] text-text-muted tabular-nums">
                {step.duration_seconds < 60
                  ? `${Math.round(step.duration_seconds)}s`
                  : `${Math.floor(step.duration_seconds / 60)}m ${Math.round(step.duration_seconds % 60)}s`}
              </span>
            )}
          </div>
          <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">{step.blurb}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-[10px] font-medium ${tone.text}`}>{step.status_label}</span>
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
              <EventNote key={`${event.id}-${i}`} event={event} />
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

const EventNote: React.FC<{ event: WizardNote }> = ({ event }) => {
  const type = event.kind;
  const isReview = type === 'review_request';
  const isApproval = type === 'approval_request' || type === 'approval_auto';
  const isError = type === 'error';
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
    skipped:  { icon: SkipForward, label: 'Skipped', color: 'text-text-muted', bg: 'bg-overlay', border: 'border-border/40' },
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
  // The plan artifact is the richer source (it has the per-sprint goals); the
  // server's own count covers runs whose plan has not been written as an
  // artifact yet.
  const planned = sprintPlan?.count ?? summary.sprints_planned ?? summary.sprints_executed;

  const stats = [
    { label: 'Sprints planned', value: planned, icon: ClipboardList, color: 'text-primary' },
    { label: 'Sprints executed', value: summary.sprints_executed, icon: Rocket, color: 'text-success' },
    { label: 'Revisions', value: summary.revisions_total, icon: ThumbsDown, color: 'text-warning' },
    { label: 'Test runs', value: summary.test_runs, icon: ListChecks, color: 'text-primary' },
    { label: 'Defects found', value: summary.defects_found, icon: AlertCircle, color: 'text-danger' },
    { label: 'Documents', value: summary.documents_produced, icon: FileText, color: 'text-text-secondary' },
    { label: 'Approvals passed', value: summary.approvals_passed, icon: ThumbsUp, color: 'text-success' },
    { label: 'Reviews approved', value: summary.reviews_approved, icon: ThumbsUp, color: 'text-success' },
    { label: 'Reviews sent back', value: summary.reviews_changes, icon: ThumbsDown, color: 'text-warning' },
    { label: 'Reviews pending', value: summary.reviews_pending, icon: Clock, color: 'text-primary' },
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
            <div key={stat.label} className="rounded-lg border border-border/40 bg-overlay px-3 py-2.5">
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
        <div className="rounded-lg border border-border/40 bg-overlay px-4 py-3">
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
