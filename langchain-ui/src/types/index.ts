export interface RunStage {
  name: string;
  meaning: string;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  duration_seconds: number | null;
  retry_count: number;
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
  event_type: string;
  run_id: string;
  timestamp: string;
  sequence: number;
  stage: string;
  message: string;
  details?: Record<string, any>;
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
  model_override?: string;
  artifact_directory?: string;
  allow_subdirectories?: boolean;
}

export interface CreateRunResponse {
  run_id: string;
  thread_id: string;
  status: string;
  created_at: string;
}
