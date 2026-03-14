export interface TaskStatus {
  task_id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'cancelled';
  progress: number;
  children: string[];
  created_at: string;
  updated_at: string;
}

export interface TaskLogEntry {
  timestamp: string;
  level: string;
  message: string;
  source: string;
}

export interface TaskLogs {
  task_id: string;
  entries: TaskLogEntry[];
}

export interface Proposal {
  proposal_id: string;
  task_id: string;
  agent_id: string;
  mutations: Record<string, unknown>[];
  verdict: 'pending' | 'accepted' | 'rejected';
  created_at: string;
}

export interface HealthStatus {
  status: string;
  services: Record<string, string>;
  version: string;
}
