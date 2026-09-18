import axios from 'axios';
import type {
  ApprovalDecisionRequest,
  CreateRunResponse,
  EventResponse,
  RunListResponse,
  RunStatusResponse,
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
