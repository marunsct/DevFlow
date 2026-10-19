/**
 * What the server sends and accepts is generated from its OpenAPI schema
 * (`api.gen.ts`, written by `scripts/ui/openapi_schema.py`), so a field renamed
 * on one side fails this build. Only what the schema does not describe - the
 * event stream, the review form - is written by hand below.
 */
export type {
  ApprovalDecisionRequest,
  BriefPreview,
  CallUsage,
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
  RunUsage,
  SettingsView,
  ServerHealth,
  SprintDefectView,
  SprintRevision,
  SprintView,
  SprintsResponse,
  StageUsage,
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
  /** The workspace path of the document the review is about, when it has one. */
  document?: string | null;
}

export interface ReviewDecisionRequest {
  action: "approve" | "changes" | "skip";
  comment: string | null;
}

// A run's event and a page of them: generated from the server's schema, so an
// event type added there reaches this build (plan UI-S4).
export type { RunEvent as LogEntry, EventPage as EventResponse } from './api.gen';

