export interface RunStage {
  name: string;
  meaning: string;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  duration_seconds: number | null;
  retry_count: number;
  /** Approvals this stage passed through - progress, not repetition. */
  approval_count: number;
  /** Which sprint the stage belongs to; 0 is the planning before the first. */
  sprint: number;
}

export interface ArtifactInfo {
  path: string;
  kind: string;
  revision: number;
  created_by: string;
  stage: string;
}

export interface ReviewInfo {
  point: string;
  status: string;
  reviewer: string;
  revision: number;
  comments: string | null;
  updated_at: string;
}

export interface RemediationInfo {
  attempt: number;
  max_attempts: number;
  escalated: boolean;
  defect_count: number;
  test_runs: number;
}

export interface RunCostSummary {
  estimated_cost_usd: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  successful_requests: number;
  priced_requests: number;
  /** Calls whose model had no published rate: cost unknown, not zero. */
  unpriced_requests: number;
  unpriced_models: string[];
  /** False when any call went unpriced, so estimated_cost_usd is partial. */
  fully_priced: boolean;
  prices_as_of: string;
}

export interface RunStatusResponse {
  run_id: string;
  thread_id: string;
  status:
    | "created"
    | "running"
    | "waiting_for_approval"
    | "waiting_for_review"
    // Parked at MAX_RUN_COST_USD. A pause, not a failure: the run is intact and
    // resumes once the ceiling is raised.
    | "waiting_for_budget"
    | "paused"
    | "failed"
    | "cancelled"
    | "completed";
  current_stage: string | null;
  stage_meaning: string | null;
  created_at: string;
  updated_at: string;
  stages: RunStage[];
  artifacts: ArtifactInfo[];
  reviews: ReviewInfo[];
  remediation: RemediationInfo | null;
  error: string | null;
  /** What this release knew it did not prove: deferred criteria, problems the
   *  suite was locked with, an unproven setup (Initiative J.4). A completed
   *  run with gaps is never plain "completed" on any surface that shows it. */
  completion_gaps?: string[];
  /** When a waiting gate approves itself; null when it waits for the person. */
  gate_deadline?: string | null;
  approval_timeout_minutes?: number | null;
  /** What the workspace's NON-DELIVERABLE marker says, or '' when the
   *  workspace is deliverable: every terminal state but a clean release
   *  writes it into the workspace root (Initiative J.6). */
  non_deliverable?: string;
  // Absent when this run's accounting lives in another worker process, which is
  // not the same as zero - see RunCostSummary on the API side.
  cost?: RunCostSummary | null;
}

export interface RunSummary {
  run_id: string;
  status: string;
  current_stage: string | null;
  created_at: string;
  document_name: string | null;
}

export interface RunListResponse {
  runs: RunSummary[];
  total: number;
}

/* ------------------------------------------------------------------ *
 * Wizard model - the guided phase view of a run, built by the server.
 * Field names mirror `WizardModel` in `src/app/server/models.py`; the API
 * hands the browser a finished model and the UI only renders it.
 * ------------------------------------------------------------------ */

export interface WizardNote {
  /** Stable event id - the list key. */
  id: string;
  /** Event type ('log', 'tool_call', 'review_request', 'error', ...) - used to pick an icon. */
  kind: string;
  /** The line as written for a human to read. */
  message: string;
}

export interface WizardReview {
  point: string;
  revision: number;
  requested_at: string | null;
  outcome: "approved" | "changes" | "skipped" | "pending";
  comment: string | null;
}

export interface WizardStep {
  name: string;
  title: string;
  blurb: string;
  started_at: string | null;
  /** Null while the step is still in flight. */
  ended_at: string | null;
  status: "done" | "active" | "waiting" | "upcoming" | "idle" | "error";
  status_label: string;
  duration_seconds: number | null;
  /** Log lines that happened while this step ran, expandable in the UI. */
  events: WizardNote[];
}

export interface SprintRevision {
  /** 1 for the first pass; increments on each rejection. */
  number: number;
  steps: WizardStep[];
  /** The end-of-sprint review, once one was requested. */
  review: WizardReview | null;
  /** Why this revision was rejected - present only when a later revision exists. */
  rejection_comment: string | null;
  saw_advance: boolean;
}

export interface WizardSection {
  id: string;
  kind: "intake" | "design" | "sprint" | "summary";
  title: string;
  blurb: string;
  status: "done" | "active" | "waiting" | "upcoming" | "idle";
  status_label: string;
  sprint_number: number | null;
  /** Present for kind='sprint' sections. */
  revisions: SprintRevision[];
  /** Steps that belong to the phase itself (intake/design), not a revision. */
  steps: WizardStep[];
}

export interface WizardSummary {
  /** From the sprint plan when it exists; null means "not yet planned". */
  sprints_planned: number | null;
  sprints_executed: number;
  revisions_total: number;
  test_runs: number;
  defects_found: number;
  documents_produced: number;
  approvals_passed: number;
  reviews_approved: number;
  reviews_changes: number;
  reviews_skipped: number;
  reviews_pending: number;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  status_label: string;
  error: string | null;
}

export interface WizardModel {
  /** In build order: intake, design, sprints 1..n, final summary. */
  sections: WizardSection[];
  summary: WizardSummary;
  /** Which section the run is currently inside, if any. */
  current_section_id: string | null;
}

/** Provider configuration as the API exposes it: credentials are masked. */
export interface SettingsView {
  llm_provider: string;
  openai_base_url: string;
  model_name: string;
  /** The model's context window in tokens; every context budget derives from it. */
  model_context_window: number;
  /** The longest single reply in tokens; shares the window with the conversation. */
  model_max_output_tokens: number;
  /** 'default' leaves the model server's own setting alone; 'on'/'off' override it. */
  thinking_mode: 'default' | 'on' | 'off';
  /** How much of the reply budget thinking may spend. */
  thinking_effort: 'low' | 'medium' | 'high';
  /** Read-only: the tokens thinking actually gets at the current setting. */
  thinking_budget_tokens?: number;
  /** Read-only: what that window currently implies, so a change shows its consequences. */
  derived_budgets?: Record<string, number>;
  openai_api_key_hint?: string | null;
  anthropic_api_key_hint?: string | null;
  google_api_key_hint?: string | null;
  openai_api_key_configured: boolean;
  anthropic_api_key_configured: boolean;
  google_api_key_configured: boolean;
  /** 'linear' runs stages serially; 'parallel' fans out specialist tasks concurrently. */
  execution_mode: 'linear' | 'parallel';
  delivery_mode?: 'fast' | 'thorough';
  /** The model the judging stages run on (architect, QA, reviews, test rounds,
   *  fixes). An empty name means every stage runs on the model above; empty
   *  provider, address and window are the default model's. */
  judgement_provider?: string;
  judgement_base_url?: string;
  judgement_model_name?: string;
  judgement_context_window?: number;
  judgement_max_output_tokens?: number;
  judgement_api_key_hint?: string | null;
  judgement_api_key_configured?: boolean;
  // The two tiers: failed tries on the build model before the judgement model
  // takes over, and whether the judgement model also plans.
  escalate_after_attempts?: number;
  plan_on_judgement_model?: boolean;
  // Whether each model's endpoint has its own key saved.
  endpoint_key_saved?: boolean;
  judgement_endpoint_key_saved?: boolean;
}

/** A model configuration saved when it was applied, so it can be picked again.
 *  Never carries a credential: those stay write-only on the server. */
export interface ModelProfile {
  id: string;
  label: string;
  target?: string;
  llm_provider: string | null;
  openai_base_url: string | null;
  model_name: string | null;
  model_context_window: number | null;
  model_max_output_tokens: number | null;
  thinking_mode: 'default' | 'on' | 'off' | null;
  thinking_effort: 'low' | 'medium' | 'high' | null;
  judgement_provider?: string | null;
  judgement_base_url?: string | null;
  judgement_model_name?: string | null;
  judgement_context_window?: number | null;
  judgement_max_output_tokens?: number | null;
  escalate_after_attempts?: number | null;
  plan_on_judgement_model?: boolean | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface ApprovalPayload {
  artifact_path: string;
  content_summary: string;
  risk_level: string;
  requested_by: string;
  stage: string;
}

export interface ApprovalDecisionRequest {
  action: "approve" | "reject";
  reason: string | null;
}

export interface ReviewPayload {
  point: string;
  artifact_id: string;
  revision: number;
  comments: string | null;
  available_actions: string[];
}

export interface ReviewDecisionRequest {
  action: "approve" | "changes" | "skip";
  comment: string | null;
}

export interface LogEntry {
  /** Stable per-event identifier, used to deduplicate history and live events. */
  event_id: string;
  event_type: string;
  run_id: string;
  timestamp: string;
  sequence: number;
  stage: string;
  message: string;
  metadata?: Record<string, unknown>;
}

export interface EventResponse {
  run_id: string;
  total: number;
  offset: number;
  limit: number;
  logs: LogEntry[];
}

export interface StartRunRequest {
  review_policy?: Record<string, boolean>;
  reviewer?: string;
  /** A label for the run's workspace. The server owns the actual path. */
  workspace_label?: string;
  allow_subdirectories?: boolean;
  auto_approve?: boolean;
  delivery_mode?: 'fast' | 'thorough';
  /** False keeps every stage of the run on the local build model. */
  use_frontier_model?: boolean;
  /** Minutes a gate waits for a person before approving itself. */
  approval_timeout_minutes?: number;
  llm_provider?: string;
  openai_base_url?: string;
  model_name?: string;
}

export interface CreateRunResponse {
  run_id: string;
  thread_id: string;
  status: string;
  created_at: string;
}
