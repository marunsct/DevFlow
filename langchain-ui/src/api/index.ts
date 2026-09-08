import axios from 'axios';
import type {
  ApprovalDecisionRequest,
  CreateRunResponse,
  EventResponse,
  RunListResponse,
  RunStatusResponse,
  StartRunRequest,
} from '../types';

export const api = axios.create({
  baseURL: '/api',
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

