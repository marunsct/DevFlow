import { endSession, refreshNow, scheduleRefresh } from '../lib/session';
import axios from 'axios';
import type {
  ApprovalDecisionRequest,
  BriefPreview,
  CreateRunResponse,
  EventResponse,
  ModelProfile,
  RunListResponse,
  RunStatusResponse,
  RunUsage,
  ServerHealth,
  SettingsView,
  SprintsResponse,
  StartRunRequest,
  WizardModel,
} from '../types';

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response && error.response.status === 401) {
      // One quiet renewal before giving up: an expired access token with a good
      // refresh token is not a signed-out owner.
      if (original && !original._renewed && (await refreshNow())) {
        original._renewed = true;
        original.headers.Authorization = `Bearer ${localStorage.getItem('token')}`;
        return api.request(original);
      }
      endSession();
      if (window.location.pathname !== '/login') {
        const back = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `/login?back=${back}`;
      }
    }
    return Promise.reject(error);
  }
);

scheduleRefresh();

// Run API
export const createRun = async (files: File[]): Promise<CreateRunResponse> => {
  const formData = new FormData();
  files.forEach(file => {
    formData.append('files', file);
  });
  const response = await api.post<CreateRunResponse>('/runs', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const startRun = async (
  runId: string,
  request: StartRunRequest
): Promise<{ message: string; status: string }> => {
  const response = await api.post<{ message: string; status: string }>(
    `/runs/${runId}/start`,
    request
  );
  return response.data;
};

export const resumeRun = async (
  runId: string
): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>(`/runs/${runId}/resume`);
  return response.data;
};

export const cloneRun = async (
  runId: string
): Promise<CreateRunResponse> => {
  const response = await api.post<CreateRunResponse>(`/runs/${runId}/clone`);
  return response.data;
};


/** How many runs one page of the list holds. */
export const RUNS_PER_PAGE = 50;

/** One page of runs, newest first; page 1 unless asked. */
export const listRuns = async (page = 1): Promise<RunListResponse> => {
  const response = await api.get<RunListResponse>('/runs', {
    params: { limit: RUNS_PER_PAGE, offset: (Math.max(1, page) - 1) * RUNS_PER_PAGE },
  });
  return response.data;
};

export interface RunOutcome {
  run_id: string;
  status: string;
  /** What the release knew it did not prove (Initiative J.4). */
  completion_gaps?: string[];
  delivery_mode: string;
  use_frontier_model: boolean;
  started_at: string | null;
  hours: number | null;
  score: { benchmark?: string; passed?: number; total?: number; score?: number } | null;
}

/**
 * What completed runs of a delivery mode took here, from its most recent ones.
 * The times are null with fewer than three runs: two runs make no "typical".
 */
export interface RunForecast {
  delivery_mode: string;
  runs: number;
  typical_hours: number | null;
  shortest_hours: number | null;
  longest_hours: number | null;
  /** Hours per acceptance criterion: compares briefs of different sizes. */
  hours_per_criterion: number | null;
  fewest_criteria: number | null;
  most_criteria: number | null;
}

/** Finished runs with their time and score, and the typical time per delivery mode. */
export const getOutcomes = async (): Promise<{ runs: RunOutcome[]; forecast: Record<string, RunForecast | null> }> => {
  const response = await api.get('/runs/outcomes');
  return response.data;
};

/** The run's sprints, from the attempts the engine renders each sprint summary from (plan BG.6). */
export const getSprints = async (runId: string): Promise<SprintsResponse> => {
  const response = await api.get<SprintsResponse>(`/runs/${runId}/sprints`);
  return response.data;
};

/** What the build model's server says of itself, read without a model call (plan BG.5). */
export const getServerHealth = async (): Promise<ServerHealth> => {
  const response = await api.get<ServerHealth>('/health/server');
  return response.data;
};

export const getRun = async (runId: string): Promise<RunStatusResponse> => {
  const response = await api.get<RunStatusResponse>(`/runs/${runId}`);
  return response.data;
};

/**
 * Fetch the guided wizard's finished model for a run.
 *
 * The phases (intake, design, sprints with their revisions, summary) are
 * derived on the server from the run's event history and graph state. The
 * browser used to re-derive them locally from the same events, and the two
 * readers drifted apart - the server is now the single source of truth.
 */
export const getWizard = async (runId: string): Promise<WizardModel> => {
  const response = await api.get<WizardModel>(`/runs/${runId}/wizard`);
  return response.data;
};

export const getLogs = async (
  runId: string,
  limit: number = 50,
  offset: number = 0
): Promise<EventResponse> => {
  const response = await api.get<EventResponse>(`/runs/${runId}/logs`, {
    params: { limit, offset },
  });
  return response.data;
};

// Reviews and Approvals
export const getPendingReview = async (runId: string) => {
  const response = await api.get(`/runs/${runId}/review`);
  return response.data;
};

export const submitReview = async (
  runId: string,
  payload: { action: 'approve' | 'changes' | 'skip'; comment: string | null; file?: File }
): Promise<{ message: string }> => {
  const formData = new FormData();
  formData.append('action', payload.action);
  if (payload.comment) {
    formData.append('comment', payload.comment);
  }
  if (payload.file) {
    formData.append('file', payload.file);
  }
  const response = await api.post<{ message: string }>(
    `/runs/${runId}/review`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return response.data;
};

export const getPendingApproval = async (runId: string) => {
  const response = await api.get(`/runs/${runId}/approval`);
  return response.data;
};

export const submitApproval = async (
  runId: string,
  payload: ApprovalDecisionRequest
): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>(
    `/runs/${runId}/approval`,
    payload
  );
  return response.data;
};

/** Stop a running run at its next step and keep it to be resumed. */
export const pauseRun = async (runId: string): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>(`/runs/${runId}/pause`);
  return response.data;
};

/**
 * Keep a run on the model it last ran on (`pinned: true`), or let it follow the current model settings again.
 * Works mid-run: a request already sent finishes where it was sent, every new one goes to the run's model.
 * `base_url` and `model` (when pinning) pin it to that endpoint instead, without touching the settings; neither
 * carries a credential.
 */
export const setModelPin = async (
  runId: string,
  pinned: boolean,
  target?: { base_url?: string; model?: string },
): Promise<{ model_pinned: boolean; model_last: { model: string; endpoint: string } | null }> => {
  const response = await api.post(`/runs/${runId}/model-pin`, { pinned, ...(pinned ? target : {}) });
  return response.data;
};

/** A point in a run's history: the moment before one of its stages started. */
export interface RewindPoint {
  checkpoint_id: string;
  stage: string;
  sprint: number | null;
  at: string;
}

export const getRewindPoints = async (runId: string): Promise<RewindPoint[]> => {
  const response = await api.get<{ points: RewindPoint[] }>(`/runs/${runId}/rewind-points`);
  return response.data.points;
};

/** Rewind a stopped run to the start of a stage, with its files as they were, and run it from there. */
export const rewindRun = async (
  runId: string,
  checkpointId: string
): Promise<{ message: string; stage: string; files_restored: boolean }> => {
  const response = await api.post(`/runs/${runId}/rewind`, { checkpoint_id: checkpointId });
  return response.data;
};

export const cancelRun = async (runId: string) => {
  const response = await api.post(`/runs/${runId}/cancel`);
  return response.data;
};

/** Whether the frontier model is configured and answering - a listing of its models, never a model call. */
export interface FrontierStatus {
  configured: boolean;
  active: boolean;
  model: string;
  provider: string;
  /** Why a run asking for it would be refused; null when it is ready. */
  problem: string | null;
}

export const getFrontierStatus = async (): Promise<FrontierStatus> => {
  const response = await api.get<FrontierStatus>('/settings/frontier/status');
  return response.data;
};

/** The acceptance criteria a brief gives a run, before it starts (plan BG.10). */
export const previewBrief = async (brief: string): Promise<BriefPreview> => {
  const response = await api.post<BriefPreview>('/runs/preview', { brief });
  return response.data;
};

/** Seed a created run's workspace from an existing codebase, as an archive. */
export const uploadCodebase = async (runId: string, archive: File): Promise<unknown> => {
  const formData = new FormData();
  formData.append('file', archive);
  const response = await api.post(`/runs/${runId}/codebase`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
  return response.data;
};

export const deleteRun = async (runId: string) => {
  const response = await api.delete(`/runs/${runId}`);
  return response.data;
};

/**
 * Exchange the bearer token for a single-use streaming ticket.
 *
 * The JWT is never put in the WebSocket URL: query strings are recorded by
 * proxy access logs, browser history and Referer headers. A ticket expires in
 * seconds and is worthless once redeemed.
 */
export const getStreamTicket = async (runId: string): Promise<string> => {
  const response = await api.post<{ ticket: string }>(`/runs/${runId}/events/ticket`);
  return response.data.ticket;
};


/**
 * Download an artifact through the authenticated client.
 *
 * The obvious implementation - an `<a href>` or `window.open` pointing at the
 * download endpoint - cannot work here. The token lives in `localStorage` and
 * is attached by the request interceptor above; a browser *navigation* goes out
 * without it, so the endpoint answers `{"detail": "Not authenticated"}` and the
 * user sees that JSON instead of their document.
 *
 * Fetching the bytes with the client and handing the browser a blob keeps the
 * header on the request, which is the only part that was ever missing.
 */
/** The run's handover pack: its documents, decisions and acceptance suite, as one zip. */
export const downloadHandover = async (runId: string): Promise<void> => {
  const response = await api.get(`/runs/${runId}/handover`, { responseType: 'blob' });
  const url = URL.createObjectURL(response.data as Blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = `${runId}-handover.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
};

/** Time, tokens and failures per stage, from the run's transcript (plan BG.7). */
export const getUsage = async (runId: string): Promise<RunUsage> => {
  const response = await api.get<RunUsage>(`/runs/${runId}/usage`);
  return response.data;
};

/** A run's KPIs from its transcript, as the loop's ledger keeps them (plan UI-S6). */
export const getKpis = async (runId: string): Promise<Record<string, unknown>> => {
  const response = await api.get(`/runs/${runId}/kpis`);
  return response.data;
};

export interface KpiRow {
  key: string;
  a: number;
  b: number;
  /** (b - a) / a, or null when a is 0. */
  change: number | null;
  /** A regression by the ledger's rule. */
  worse: boolean;
}

/** Two runs' KPIs side by side, each change marked worse by the ledger's rule. */
export const compareRuns = async (a: string, b: string): Promise<{ a: string; b: string; rows: KpiRow[] }> => {
  const response = await api.get('/runs/compare', { params: { a, b } });
  return response.data;
};

/** The run's whole transcript as text: every model call, reply, tool call and result. */
export const downloadTranscript = async (runId: string): Promise<void> => {
  const response = await api.get(`/runs/${runId}/transcript`, { responseType: 'blob' });
  const url = URL.createObjectURL(response.data as Blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = `${runId}-transcript.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
};

export const downloadArtifact = async (runId: string, path: string): Promise<void> => {
  const response = await api.get(`/runs/${runId}/artifacts/download`, {
    params: { path },
    responseType: 'blob',
  });

  // Prefer the name the server chose; fall back to the last path segment so a
  // download is never saved as the run id.
  const disposition = String(response.headers['content-disposition'] ?? '');
  const named = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const filename = decodeURIComponent(named?.[1] ?? path.split('/').pop() ?? 'artifact');

  const url = URL.createObjectURL(response.data as Blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    // Revoking immediately can cancel the download in some browsers; a tick is
    // enough for the click to have been handed off.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
};

/**
 * Fetch the *content* of an artifact as text, for in-app display.
 *
 * `downloadArtifact` above hands the bytes to the browser as a download. That
 * is the right shape for "save this file", but the wizard wants to *read* the
 * file (e.g. the sprint plan, to show how many sprints were planned). A plain
 * `<a href>` navigation would not work: the browser would not send the auth
 * header, and the server would reject the request. Fetching with the client
 * keeps the header on the request, and asking for `text` gives us the content
 * as a string we can parse.
 *
 * The server resolves logical paths (e.g. `sprint-plan`) to graph-state keys
 * (e.g. `sprint_plan`) and returns the structured content as JSON. We ask for
 * `text` so the response is a string either way; the caller parses it.
 *
 * Returns `null` if the artifact has not been generated yet (the server 404s
 * in that case) or if the request fails for any other reason.
 */
/** What changed in a document since the version before, from the workspace's history (plan BG.3). */
export interface DocumentDiff {
  path: string;
  /** The commit of the version before, or null when there is none. */
  since: string | null;
  since_at: string | null;
  diff: string;
  truncated: boolean;
}

export const getDocumentDiff = async (runId: string, path: string): Promise<DocumentDiff> => {
  const response = await api.get<DocumentDiff>(`/runs/${runId}/artifacts/diff`, { params: { path } });
  return response.data;
};

export const fetchArtifactContent = async (
  runId: string,
  path: string
): Promise<string | null> => {
  try {
    const response = await api.get(`/runs/${runId}/artifacts/download`, {
      params: { path },
      responseType: 'text',
    });
    return response.data as string;
  } catch {
    // The artifact is not available yet (the run has not reached that stage)
    // or the request failed. Either way the caller should show a placeholder,
    // not an error.
    return null;
  }
};

/** Get saved model profiles, optionally filtered by target ('build' or 'frontier'). */
export const getModelProfiles = async (target?: 'build' | 'frontier'): Promise<ModelProfile[]> => {
  const response = await api.get<ModelProfile[]>('/settings/models', {
    params: target ? { target } : {},
  });
  return response.data;
};

/** Save only the local build model configuration and remember its profile. */
export const saveLocalModelSettings = async (payload: {
  llm_provider: string;
  openai_base_url: string;
  model_name: string;
  model_context_window: number;
  model_max_output_tokens: number;
  thinking_mode: 'default' | 'on' | 'off';
  thinking_effort: 'low' | 'medium' | 'high';
  api_key?: string;
}): Promise<SettingsView> => {
  const response = await api.put<SettingsView>('/settings/local', payload);
  return response.data;
};

/** Save only the frontier model configuration, or disable it with no_model=true. */
export const saveFrontierModelSettings = async (payload: {
  judgement_provider: string;
  judgement_base_url: string;
  judgement_model_name: string;
  judgement_context_window: number;
  judgement_max_output_tokens: number;
  judgement_api_key?: string;
  escalate_after_attempts: number;
  plan_on_judgement_model: boolean;
  no_model?: boolean;
}): Promise<SettingsView> => {
  const response = await api.put<SettingsView>('/settings/frontier', payload);
  return response.data;
};

/** One commit of a run's workspace history, with each file's lines added and removed. */
export interface WorkspaceCommit {
  sha: string;
  message: string;
  at: string;
  files: Array<{ path: string; added: number | null; removed: number | null }>;
}

export const getChanges = async (runId: string): Promise<{ commits: WorkspaceCommit[]; problem?: string }> => {
  const response = await api.get(`/runs/${runId}/changes`);
  return response.data;
};

export const getChange = async (runId: string, sha: string): Promise<{ sha: string; diff: string; truncated: boolean }> => {
  const response = await api.get(`/runs/${runId}/changes/${sha}`);
  return response.data;
};

/** A note the owner sent a run while it ran; its next model calls carry it. */
export interface SteeringNote {
  id?: string;
  text: string;
  by: string;
  at: string;
  scope?: 'run' | 'next_stage';
  /** Set when the first model call carried the note: the stage it was read in. */
  applied_stage?: string;
  applied_at?: string;
}

export const getSteering = async (runId: string): Promise<SteeringNote[]> => {
  const response = await api.get(`/runs/${runId}/steering`);
  return response.data.notes ?? [];
};

export const sendSteering = async (
  runId: string,
  text: string,
  scope: 'run' | 'next_stage' = 'run',
): Promise<SteeringNote> => {
  const response = await api.post(`/runs/${runId}/steering`, { text, scope });
  return response.data.note;
};
