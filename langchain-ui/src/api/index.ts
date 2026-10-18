import axios from 'axios';
import type {
  ApprovalDecisionRequest,
  CreateRunResponse,
  EventResponse,
  ModelProfile,
  RunListResponse,
  RunStatusResponse,
  SettingsView,
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
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

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


export const listRuns = async (): Promise<RunListResponse> => {
  const response = await api.get<RunListResponse>('/runs');
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

export interface RunForecast {
  delivery_mode: string;
  typical_hours: number;
  shortest_hours: number;
  longest_hours: number;
  runs: number;
}

/** Finished runs with their time and score, and the typical time per delivery mode. */
export const getOutcomes = async (): Promise<{ runs: RunOutcome[]; forecast: Record<string, RunForecast | null> }> => {
  const response = await api.get('/runs/outcomes');
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
