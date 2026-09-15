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

export interface RunStatusResponse {
  run_id: string;
  thread_id: string;
  status:
    | "created"
    | "running"
    | "waiting_for_approval"
    | "waiting_for_review"
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
