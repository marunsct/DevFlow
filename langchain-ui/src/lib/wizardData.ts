/**
 * Turn a run's raw event stream into the model the guided wizard renders.
 *
 * The classic dashboard shows the run as a flat list of stages and a log. That
 * is accurate but it is also the shape the *code* has, not the shape the *work*
 * has. A person following a build thinks in phases: "understand the product,
 * design it, build sprint one, build sprint two, done." This module rebuilds
 * that shape from the same data the dashboard already holds, so the wizard can
 * present the run the way it actually happened.
 *
 * Everything here is a pure function over `(run, logs)`. No fetching, no
 * components, no side effects. That matters for two reasons:
 *
 *  - The wizard re-renders on every WebSocket log merge. Re-deriving the model
 *    from scratch each time is cheap (a run caps at 5000 events) and means the
 *    wizard can never drift out of sync with the log it is reading.
 *  - A pure function is trivial to test later: feed it a recorded event list,
 *    assert the sections you expect.
 */

import type { LogEntry, RunStatusResponse } from '../types';
import { describeStage, describeStatus } from './activity';

/* ------------------------------------------------------------------ *
 * The model
 * ------------------------------------------------------------------ */

/**
 * A single step inside a section, in the order it happened.
 *
 * `name` is the backend's stage name (e.g. `specialist_backend_0`); `title` and
 * `blurb` are the plain-English versions from `describeStage`, so the wizard
 * never has to show a raw identifier.
 */
export interface WizardStep {
  name: string;
  title: string;
  blurb: string;
  startedAt: string | null;
  endedAt: string | null;
  /** 'done' | 'active' | 'waiting' | 'error' | 'idle' - see describeStatus. */
  status: string;
  /** Human label for the status, e.g. "Done", "Working on it". */
  statusLabel: string;
  durationSeconds: number | null;
  /** The events that happened while this step was current. */
  events: LogEntry[];
}

/**
 * A review the run paused for.
 *
 * The backend does not publish a "decision" event - the answer only exists as
 * the *next stage* the graph moves to. So the outcome is inferred: if the run
 * went on to `sprint_advance` or `complete` the review was approved or skipped;
 * if it went straight back to `technical_lead` it was sent back for changes.
 * The comment text is not in the event stream at all, so it is `null` unless
 * the run's current review state still carries it.
 */
export interface WizardReview {
  point: string;
  revision: number;
  requestedAt: string;
  /** 'approved' | 'changes' | 'skipped' | 'pending' - inferred, see above. */
  outcome: string;
  comment: string | null;
}

/**
 * One pass through a sprint.
 *
 * A sprint is not one straight line: it is build, test, fix, review - and if
 * the review sends it back, the whole thing happens again. Each pass is a
 * "revision". The first pass is revision 1; a rejected review starts revision
 * 2 *under the same sprint*, which is exactly the behaviour the wizard was
 * asked to show (a re-run is a revision, not a brand-new sprint).
 */
export interface SprintRevision {
  number: number;
  steps: WizardStep[];
  review: WizardReview | null;
  /** The rejection comment that started this revision (null for the first). */
  revisionComment: string | null;
  /**
   * True if the run moved on to the next sprint after this revision (the
   * review was approved and `sprint_advance` ran). Used to infer the review's
   * outcome, which the backend never publishes as an event.
   */
  sawAdvance: boolean;
}

export type WizardSectionKind =
  | 'intake'
  | 'design'
  | 'sprint'
  | 'summary';

export interface WizardSection {
  id: string;
  kind: WizardSectionKind;
  title: string;
  blurb: string;
  /** 'done' | 'active' | 'waiting' | 'error' | 'idle' | 'upcoming'. */
  status: string;
  statusLabel: string;
  /** Sprint sections only: which sprint number this is (1-based). */
  sprintNumber?: number;
  /** Sprint sections only: the passes through this sprint. */
  revisions?: SprintRevision[];
  /** Non-sprint sections: the steps that happened in this phase. */
  steps?: WizardStep[];
  /** The events that happened while this section was current. */
  events: LogEntry[];
}

export interface WizardSummary {
  sprintsPlanned: number;
  sprintsExecuted: number;
  revisionsTotal: number;
  testRuns: number;
  defectsFound: number;
  documentsProduced: number;
  approvalsPassed: number;
  reviewsApproved: number;
  reviewsChanges: number;
  reviewsSkipped: number;
  reviewsPending: number;
  startedAt: string;
  endedAt: string | null;
  status: string;
  statusLabel: string;
  error: string | null;
}

export interface WizardModel {
  sections: WizardSection[];
  summary: WizardSummary;
  /** The section id the run is currently in, or null if terminal. */
  currentSectionId: string | null;
}

/* ------------------------------------------------------------------ *
 * Small helpers
 * ------------------------------------------------------------------ */

/**
 * Strip the pause prefix from a stage name.
 *
 * While a run waits on a person, the graph's `stage` field is
 * `awaiting_user_review:sprint` or `awaiting_approval:principal_architect`.
 * The part after the colon is the stage that is actually paused, and that is
 * the name every other event in the stream uses, so we normalise to it.
 */
const baseStage = (raw: string): string =>
  raw.replace(/^awaiting_(approval|user_review):/, '');

const isPauseStage = (raw: string): boolean =>
  /^awaiting_(approval|user_review):/.test(raw);

/**
 * A stage that means "a human review is open".
 *
 * These are the only stages that can sit between two passes of a sprint and
 * still mean "same sprint, sent back for changes". An approval pause is not a
 * review - it is the stage working - so it does not count.
 */
const isReviewStage = (raw: string): boolean =>
  baseStage(raw) === 'user_review_sprint' ||
  baseStage(raw) === 'user_review_specification' ||
  baseStage(raw) === 'user_review_product_intake';

/**
 * A stage that means "this sprint is done, move to the next one".
 *
 * `sprint_advance` is the graph's only path out of an *approved* sprint review
 * (workflow.py routes an approved review to `sprint_advance`, a rejected one
 * straight back to `technical_lead`). That makes it the one unambiguous signal
 * that separates "genuinely new sprint" from "revision of the same sprint".
 */
const isAdvanceStage = (raw: string): boolean => baseStage(raw) === 'sprint_advance';

const isLeadStage = (raw: string): boolean => baseStage(raw) === 'technical_lead';

const isTerminalStage = (raw: string): boolean =>
  baseStage(raw) === 'complete' || baseStage(raw) === 'failed';

/**
 * The status a step is in, in the words `describeStatus` uses.
 *
 * A step is "done" once a later step has started (the run moved on past it).
 * It is "active" if it is the last step and the run is still going. It is
 * "waiting" if the run is paused on it. Anything after the last step is
 * "upcoming" - it has not happened yet.
 */
function stepStatus(
  isLast: boolean,
  runStatus: string,
  currentStage: string | null
): { status: string; label: string } {
  if (!isLast) {
    // A step the run has moved past is finished, unless the whole run stopped
    // before it could finish.
    if (runStatus === 'failed' || runStatus === 'cancelled') {
      return { status: 'error', label: 'Stopped' };
    }
    return { status: 'done', label: 'Done' };
  }

  // The last step: it is the one in flight, or the one the run is waiting on.
  if (runStatus === 'completed') return { status: 'done', label: 'Done' };
  if (runStatus === 'failed') return { status: 'error', label: 'Stopped' };
  if (runStatus === 'cancelled') return { status: 'idle', label: 'Cancelled' };
  if (runStatus === 'waiting_for_review' || runStatus === 'waiting_for_approval') {
    return { status: 'waiting', label: 'Waiting for you' };
  }
  if (runStatus === 'paused') return { status: 'waiting', label: 'Paused' };
  if (runStatus === 'running' || runStatus === 'created') {
    // Only "active" if this step is actually the current one; a created run
    // has no current stage yet.
    if (runStatus === 'created' || !currentStage) {
      return { status: 'idle', label: 'Up next' };
    }
    return { status: 'active', label: 'Working on it' };
  }
  return { status: 'idle', label: 'Up next' };
}

const durationBetween = (start: string | null, end: string | null): number | null => {
  if (!start || !end) return null;
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return null;
  return Math.round((e - s) / 1000);
};

/* ------------------------------------------------------------------ *
 * The derivation
 * ------------------------------------------------------------------ */

/**
 * Build the wizard model from a run and its full event log.
 *
 * The walk is a single pass over the events in sequence order. As it goes it
 * keeps track of which section and which revision it is in, and decides, at
 * each `technical_lead` re-entry, whether that opens a new sprint or a new
 * revision of the current one (see the folding rule below).
 */
export function buildWizardModel(
  run: RunStatusResponse,
  logs: LogEntry[]
): WizardModel {
  // Events in sequence order. The dashboard already keeps them sorted, but the
  // wizard must not depend on that - a fresh fetch could arrive unsorted.
  const events = [...logs].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));

  const isTerminal = ['completed', 'failed', 'cancelled'].includes(run.status);
  const currentStage = run.current_stage;

  /* ---- 1. Walk the events into sections and revisions ---------------- */

  const intake: WizardSection = {
    id: 'intake',
    kind: 'intake',
    title: 'Product intake',
    blurb: 'Reading your document to work out what you want built and who it is for.',
    status: 'upcoming',
    statusLabel: 'Up next',
    steps: [],
    events: [],
  };

  const design: WizardSection = {
    id: 'design',
    kind: 'design',
    title: 'Design',
    blurb: 'Comparing options, choosing the technology, and writing the technical plan.',
    status: 'upcoming',
    statusLabel: 'Up next',
    steps: [],
    events: [],
  };

  const summary: WizardSection = {
    id: 'summary',
    kind: 'summary',
    title: 'Final summary',
    blurb: 'How the run went: sprints planned vs. built, revisions, tests and reviews.',
    status: 'upcoming',
    statusLabel: 'Up next',
    events: [],
  };

  const sprintSections: WizardSection[] = [];
  // The sections array is rebuilt at the end of the walk, once all sprint
  // sections have been pushed. A snapshot here would be empty (sprintSections
  // is still empty at this point) and the sprints would never appear.
  let sections: WizardSection[] = [intake, design, summary];

  // The section and revision the walk is currently writing into.
  let activeSection: WizardSection = intake;
  let activeRevision: SprintRevision | null = null;
  let sprintNumber = 0;

  // The steps of the current revision, in order.
  let currentSteps: WizardStep[] = [];
  // The review the current revision is waiting on, if any.
  let pendingReview: WizardReview | null = null;
  // The comment that started the current revision (a rejection), if any.
  let revisionComment: string | null = null;

  // What happened since the last technical_lead entry - used by the folding
  // rule to decide "new sprint" vs. "revision".
  let sawAdvance = false;
  let sawReview = false;

  const openStep = (name: string, at: string): WizardStep => {
    const copy = describeStage(name);
    return {
      name,
      title: copy.title,
      blurb: copy.blurb,
      startedAt: at,
      endedAt: null,
      status: 'active',
      statusLabel: 'Working on it',
      durationSeconds: null,
      events: [],
    };
  };

  // Where the current step lives depends on the phase: inside a sprint it is
  // part of the revision being built (currentSteps), but before the first
  // sprint opens, intake and design steps belong to their section directly.
  // If we pushed them into currentSteps they would be dropped - that array is
  // only committed when a sprint revision commits, and it is reset when the
  // first revision starts.
  const stepContainer = (): WizardStep[] =>
    sprintNumber > 0 ? currentSteps : (activeSection.steps ?? []);

  const closeCurrentStep = (at: string) => {
    const container = stepContainer();
    const last = container[container.length - 1];
    if (last && last.endedAt === null) {
      last.endedAt = at;
      last.durationSeconds = durationBetween(last.startedAt, last.endedAt);
    }
  };

  const commitRevision = () => {
    if (!activeRevision) return;
    activeRevision.steps = currentSteps;
    activeRevision.review = pendingReview;
    activeRevision.revisionComment = revisionComment;
    activeRevision.sawAdvance = sawAdvance;
    activeRevision = null;
    currentSteps = [];
    pendingReview = null;
    revisionComment = null;
  };

  const startRevision = (comment: string | null) => {
    const number = (activeRevision ? activeRevision.number : 0) + 1;
    activeRevision = {
      number,
      steps: [],
      review: null,
      revisionComment: comment,
      sawAdvance: false,
    };
    currentSteps = [];
    pendingReview = null;
    revisionComment = comment;
  };

  // The stage the walk last saw. A stage transition is detected when the
  // `stage` field of an event differs from the previous event's stage. This
  // works because the log does not always publish `stage_change` events for
  // every transition - it only publishes them for pause stages. The actual
  // stage transitions (technical_lead, sprint_advance, etc.) are visible as
  // the `stage` field of the events that happen while that stage is running.
  let prevStage: string | null = null;

  for (const event of events) {
    const stage = event.stage;
    const base = baseStage(stage);

    // A stage transition: the stage field changed from the previous event.
    // This is the only reliable signal of a new stage, because the log does
    // not publish `stage_change` events for non-pause stages.
    const isTransition = stage !== prevStage;
    prevStage = stage;

    if (isTransition) {
      // A pause stage is not a new step - it is the current step waiting on a
      // person. We handle it below (it opens a review) rather than as a step.
      if (isPauseStage(stage)) {
        if (isReviewStage(stage)) {
          // A review is open. Record it; the outcome is filled in when the run
          // moves on (the next stage tells us how the review was answered).
          const meta = (event.metadata ?? {}) as Record<string, unknown>;
          pendingReview = {
            point: String(meta.review_point ?? base),
            revision: Number(meta.revision ?? 0),
            requestedAt: event.timestamp,
            outcome: 'pending',
            comment: null,
          };
          sawReview = true;
        }
        // An approval pause is the step working, not a new step or a review.
        continue;
      }

      // A terminal stage ends the walk.
      if (isTerminalStage(stage)) {
        closeCurrentStep(event.timestamp);
        if (activeRevision) commitRevision();
        // The terminal stage's own events belong to the summary.
        summary.events.push(event);
        continue;
      }

      // The folding rule: every technical_lead entry is either a new sprint or
      // a new revision of the current one.
      if (isLeadStage(stage)) {
        closeCurrentStep(event.timestamp);

        if (sprintNumber === 0) {
          // The first technical_lead entry opens the first sprint.
          sprintNumber += 1;
          const section: WizardSection = {
            id: `sprint-${sprintNumber}`,
            kind: 'sprint',
            title: `Sprint ${sprintNumber}`,
            blurb: 'Building, testing and reviewing this chunk of the product.',
            status: 'upcoming',
            statusLabel: 'Up next',
            sprintNumber,
            revisions: [],
            events: [],
          };
          sprintSections.push(section);
          activeSection = section;
          startRevision(null);
        } else if (sawAdvance) {
          // An approved review ran sprint_advance in between: genuinely new sprint.
          commitRevision();
          sprintNumber += 1;
          const section: WizardSection = {
            id: `sprint-${sprintNumber}`,
            kind: 'sprint',
            title: `Sprint ${sprintNumber}`,
            blurb: 'Building, testing and reviewing this chunk of the product.',
            status: 'upcoming',
            statusLabel: 'Up next',
            sprintNumber,
            revisions: [],
            events: [],
          };
          sprintSections.push(section);
          activeSection = section;
          startRevision(null);
        } else if (sawReview) {
          // A review ran in between but no advance: the sprint was sent back.
          // A new revision under the *same* sprint, not a new sprint.
          commitRevision();
          startRevision(pendingReview?.comment ?? null);
        } else {
          // No review and no advance in between (e.g. re-entry from defect
          // remediation): the same revision continues, no new pass.
          // Nothing to commit; the step simply continues.
        }

        sawAdvance = false;
        sawReview = false;

        const step = openStep(base, event.timestamp);
        stepContainer().push(step);
        step.events.push(event);
        continue;
      }

      // Any other stage is a step within the current revision (or, before the
      // first sprint, within the design phase).
      closeCurrentStep(event.timestamp);

      if (isAdvanceStage(stage)) {
        // sprint_advance is the bridge between sprints. It is not a step of
        // either sprint; it just marks that the current one is done.
        sawAdvance = true;
        continue;
      }

      // Decide which section this step belongs to. Before the first sprint
      // opens, everything is design (except product_manager, which is intake).
      if (sprintNumber === 0) {
        if (base === 'product_manager') {
          activeSection = intake;
        } else {
          activeSection = design;
        }
      }

      const step = openStep(base, event.timestamp);
      stepContainer().push(step);
      step.events.push(event);
      continue;
    }

    // Not a stage transition: a note about the stage that is already running.
    // Attach it to the current step if the stage matches, otherwise to the
    // section (events with no matching step still belong somewhere).
    const container = stepContainer();
    const lastStep = container[container.length - 1];
    if (lastStep && baseStage(lastStep.name) === base) {
      lastStep.events.push(event);
    } else if (activeSection) {
      activeSection.events.push(event);
    }
  }

  // End of the walk: close whatever is still open.
  closeCurrentStep(events.length ? events[events.length - 1].timestamp : '');
  if (activeRevision) commitRevision();

  // Rebuild the sections array now that all sprint sections have been pushed.
  // The order is intake, design, sprints (in the order they opened), summary.
  sections = [intake, design, ...sprintSections, summary];

  /* ---- 2. Fill in section and step statuses ------------------------- */

  const markSectionStatus = (section: WizardSection, isLast: boolean) => {
    const { status, label } = stepStatus(isLast, run.status, currentStage);
    section.status = status;
    section.statusLabel = label;
  };

  const markStepStatus = (step: WizardStep, isLast: boolean) => {
    const { status, label } = stepStatus(isLast, run.status, currentStage);
    step.status = status;
    step.statusLabel = label;
  };

  // Intake and design are done once the first sprint opens (or the run ends).
  const firstSprintOpened = sprintSections.length > 0;
  if (firstSprintOpened || isTerminal) {
    intake.status = 'done';
    intake.statusLabel = 'Done';
    design.status = 'done';
    design.statusLabel = 'Done';
  } else if (run.status !== 'created') {
    // The run is in the design phase: whichever of intake/design is current.
    const inIntake = currentStage !== null && baseStage(currentStage) === 'product_manager';
    intake.status = inIntake ? 'active' : 'done';
    intake.statusLabel = inIntake ? 'Working on it' : 'Done';
    design.status = inIntake ? 'upcoming' : 'active';
    design.statusLabel = inIntake ? 'Up next' : 'Working on it';
  }

  // The steps inside intake and design need the same treatment as sprint
  // steps: a step is finished once the run has moved past it. So when its
  // section is done, every step in it is done; while the section is current,
  // only its last step is still in flight (or waiting).
  for (const section of [intake, design]) {
    const steps = section.steps ?? [];
    if (section.status === 'done') {
      for (const step of steps) {
        step.status = 'done';
        step.statusLabel = 'Done';
      }
    } else if (section.status === 'active' || section.status === 'waiting') {
      steps.forEach((step, i) => {
        // markStepStatus handles failed runs: passed steps show "Stopped".
        if (i < steps.length - 1) {
          markStepStatus(step, false);
        } else {
          markStepStatus(step, true);
        }
      });
    }
  }

  for (const section of sprintSections) {
    const isLastSprint = section === sprintSections[sprintSections.length - 1];
    if (isLastSprint && !isTerminal) {
      markSectionStatus(section, true);
    } else {
      section.status = 'done';
      section.statusLabel = 'Done';
    }
    for (const revision of section.revisions ?? []) {
      const isLastRevision =
        revision === (section.revisions ?? [])[ (section.revisions?.length ?? 1) - 1 ];
      for (const step of revision.steps) {
        markStepStatus(step, isLastRevision && isLastSprint && !isTerminal);
      }
    }
  }

  // The summary is current once the run is terminal; otherwise it is upcoming.
  if (isTerminal) {
    summary.status = 'done';
    summary.statusLabel = 'Done';
  } else {
    summary.status = 'upcoming';
    summary.statusLabel = 'Up next';
  }

  // Which section is the run currently in? The last one that is not done.
  let currentSectionId: string | null = null;
  if (!isTerminal) {
    for (const section of sections) {
      if (section.status === 'active' || section.status === 'waiting') {
        currentSectionId = section.id;
        break;
      }
    }
  }

  /* ---- 3. Infer review outcomes ------------------------------------ */

  // The backend never publishes a "decision" event - the answer to a review
  // only exists as the *next stage* the graph moves to. So we infer it:
  //
  //  - If a later revision started with a rejection comment, this review was
  //    sent back for changes (that comment is the rejection).
  //  - If the run moved on to the next sprint (sawAdvance) or finished, the
  //    review was approved or skipped.
  //  - If the run is still waiting on it, it is still open.
  for (const section of sprintSections) {
    const revisions = section.revisions ?? [];
    for (let i = 0; i < revisions.length; i++) {
      const review = revisions[i].review;
      if (!review || review.outcome !== 'pending') continue;

      const next = revisions[i + 1];
      if (next && next.revisionComment) {
        review.outcome = 'changes';
        review.comment = next.revisionComment;
      } else if (revisions[i].sawAdvance || isTerminal) {
        review.outcome = 'approved';
      } else if (run.status === 'waiting_for_review') {
        review.outcome = 'pending';
      } else {
        // The run is still inside this revision (building, testing, fixing)
        // and has not reached the review yet - or the review was answered and
        // the run is moving on. Either way it is not "sent back".
        review.outcome = 'approved';
      }
    }
  }

  // Attach the run's current review comment (the only place comment text
  // survives in the API) to the matching open review.
  const currentReview = run.reviews?.find((r) => r.status === 'pending');
  if (currentReview) {
    for (const section of sprintSections) {
      for (const revision of section.revisions ?? []) {
        if (revision.review?.outcome === 'pending') {
          revision.review.comment = currentReview.comments;
        }
      }
    }
  }

  /* ---- 4. The final summary ---------------------------------------- */

  const allRevisions = sprintSections.flatMap((s) => s.revisions ?? []);
  const allReviews = allRevisions.map((r) => r.review).filter(Boolean) as WizardReview[];

  const summaryModel: WizardSummary = {
    // The real "planned" count comes from the sprint plan artifact, which the
    // summary panel fetches separately (it is content, not in the run's stage
    // list). Until then we show how many sprints the run has actually opened.
    sprintsPlanned: sprintSections.length,
    sprintsExecuted: sprintSections.length,
    revisionsTotal: allRevisions.length,
    testRuns: run.remediation?.test_runs ?? 0,
    defectsFound: run.remediation?.defect_count ?? 0,
    documentsProduced: run.artifacts?.length ?? 0,
    approvalsPassed: (run.stages ?? []).reduce((n, s) => n + s.approval_count, 0),
    reviewsApproved: allReviews.filter((r) => r.outcome === 'approved').length,
    reviewsChanges: allReviews.filter((r) => r.outcome === 'changes').length,
    reviewsSkipped: allReviews.filter((r) => r.outcome === 'skipped').length,
    reviewsPending: allReviews.filter((r) => r.outcome === 'pending').length,
    startedAt: run.created_at,
    endedAt: isTerminal ? run.updated_at : null,
    status: run.status,
    statusLabel: describeStatus(run.status).label,
    error: run.error,
  };

  return { sections, summary: summaryModel, currentSectionId };
}
