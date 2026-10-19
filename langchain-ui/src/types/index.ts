/**
 * What the server sends and accepts is generated from its OpenAPI schema
 * (`api.gen.ts`, written by `scripts/ui/openapi_schema.py`), so a field renamed
 * on one side fails this build. Only what the schema does not describe - the
 * event stream, the review form - is written by hand below.
 */
export type {
  ApprovalDecisionRequest,
  ArtifactInfo,
  CreateRunResponse,
  ModelProfile,
  RemediationInfo,
  ReviewInfo,
  RunCostSummary,
  RunListResponse,
  RunStage,
  RunStatusResponse,
  RunSummary,
  SettingsView,
  SprintRevision,
  StartRunRequest,
  WizardModel,
  WizardNote,
  WizardReview,
  WizardSection,
  WizardStep,
  WizardSummary,
} from './api.gen';

/* ------------------------------------------------------------------ *
 * Wizard model - the guided phase view of a run, built by the server.
 * Field names mirror `WizardModel` in `src/app/server/models.py`; the API
 * hands the browser a finished model and the UI only renders it.
 * ------------------------------------------------------------------ */

export interface ApprovalPayload {
  artifact_path: string;
  content_summary: string;
  risk_level: string;
  requested_by: string;
  stage: string;
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

