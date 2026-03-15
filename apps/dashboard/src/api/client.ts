import type { TaskStatus, TaskLogs, HealthStatus, Proposal } from './types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchTasks(signal?: AbortSignal): Promise<TaskStatus[]> {
  return request<TaskStatus[]>('/api/v1/tasks', { signal });
}

export async function fetchTask(taskId: string, signal?: AbortSignal): Promise<TaskStatus> {
  return request<TaskStatus>(`/api/v1/tasks/${taskId}`, { signal });
}

export async function fetchTaskLogs(taskId: string, signal?: AbortSignal): Promise<TaskLogs> {
  return request<TaskLogs>(`/api/v1/tasks/${taskId}/logs`, { signal });
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthStatus> {
  return request<HealthStatus>('/api/v1/health', { signal });
}

export async function fetchProposals(taskId?: string, signal?: AbortSignal): Promise<Proposal[]> {
  const path = taskId
    ? `/api/v1/proposals?task_id=${encodeURIComponent(taskId)}`
    : '/api/v1/proposals';
  return request<Proposal[]>(path, { signal });
}

export async function cancelTask(taskId: string, force: boolean = false): Promise<void> {
  await request<void>(`/api/v1/tasks/${taskId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  });
}
