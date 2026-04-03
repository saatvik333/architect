import type {
  TaskStatus,
  TaskLogs,
  HealthStatus,
  Proposal,
  Escalation,
  EscalationStats,
  ApprovalGate,
  ProgressSummary,
  ActivityEvent,
} from './types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('auth_token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const { headers: extraHeaders, ...rest } = options ?? {};

  const timeout = AbortSignal.timeout(15_000);
  const signal = options?.signal
    ? AbortSignal.any([timeout, options.signal])
    : timeout;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { ...headers, ...(extraHeaders as Record<string, string>) },
      ...rest,
      signal,
    });
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error(`Network error: Unable to reach API`);
    }
    throw err;
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = (body as Record<string, unknown>).detail ?? response.statusText;
    throw new Error(`API error ${response.status}: ${detail}`);
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

// ─── Escalations ────────────────────────────────────────────────

export async function fetchEscalations(
  params?: { status?: string; category?: string; severity?: string; limit?: number },
  signal?: AbortSignal,
): Promise<Escalation[]> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set('status', params.status);
  if (params?.category) searchParams.set('category', params.category);
  if (params?.severity) searchParams.set('severity', params.severity);
  if (params?.limit) searchParams.set('limit', String(params.limit));
  const qs = searchParams.toString();
  return request<Escalation[]>(`/api/v1/escalations${qs ? `?${qs}` : ''}`, { signal });
}

export async function fetchEscalation(id: string, signal?: AbortSignal): Promise<Escalation> {
  return request<Escalation>(`/api/v1/escalations/${id}`, { signal });
}

export async function resolveEscalation(
  id: string,
  data: { resolved_by: string; resolution: string; custom_input?: Record<string, unknown> },
): Promise<Escalation> {
  return request<Escalation>(`/api/v1/escalations/${id}/resolve`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchEscalationStats(signal?: AbortSignal): Promise<EscalationStats> {
  return request<EscalationStats>('/api/v1/escalations/stats', { signal });
}

// ─── Approval Gates ─────────────────────────────────────────────

export async function fetchApprovalGates(
  params?: { status?: string },
  signal?: AbortSignal,
): Promise<ApprovalGate[]> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set('status', params.status);
  const qs = searchParams.toString();
  return request<ApprovalGate[]>(`/api/v1/approval-gates${qs ? `?${qs}` : ''}`, { signal });
}

export async function voteOnGate(
  gateId: string,
  data: { voter: string; decision: 'approve' | 'deny'; comment?: string },
): Promise<ApprovalGate> {
  return request<ApprovalGate>(`/api/v1/approval-gates/${gateId}/vote`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ─── Progress ───────────────────────────────────────────────────

export async function fetchProgress(signal?: AbortSignal): Promise<ProgressSummary> {
  return request<ProgressSummary>('/api/v1/progress', { signal });
}

// ─── Activity ───────────────────────────────────────────────────

export async function fetchActivity(limit?: number, signal?: AbortSignal): Promise<ActivityEvent[]> {
  const qs = limit ? `?limit=${limit}` : '';
  return request<ActivityEvent[]>(`/api/v1/activity${qs}`, { signal });
}
