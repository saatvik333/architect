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

// ─── Human Interface (Component 14) ─────────────────────────────

export interface EscalationOption {
  label: string;
  description: string;
  tradeoff: string;
}

export interface Escalation {
  id: string;
  source_agent_id: string | null;
  source_task_id: string | null;
  summary: string;
  category: 'confidence' | 'security' | 'budget' | 'architectural';
  severity: 'low' | 'medium' | 'high' | 'critical';
  options: EscalationOption[];
  recommended_option: string | null;
  reasoning: string | null;
  risk_if_wrong: string | null;
  status: 'pending' | 'resolved' | 'expired' | 'auto_resolved';
  resolved_by: string | null;
  resolution: string | null;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}

export interface EscalationStats {
  total: number;
  pending: number;
  resolved: number;
  expired: number;
}

export interface ApprovalGate {
  id: string;
  action_type: string;
  resource_id: string | null;
  required_approvals: number;
  current_approvals: number;
  status: 'pending' | 'approved' | 'denied' | 'expired';
  context: Record<string, unknown>;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}

export interface ApprovalVote {
  id: string;
  gate_id: string;
  voter: string;
  decision: 'approve' | 'deny';
  comment: string | null;
  created_at: string;
}

export interface ProgressSummary {
  project_name: string;
  status: string;
  completion_pct: number;
  tasks_completed: number;
  tasks_total: number;
  budget_consumed_pct: number;
  tests_passing: number;
  tests_failing: number;
  coverage_pct: number;
  blockers: Escalation[];
  recent_events: ActivityEvent[];
}

export interface ActivityEvent {
  id: string;
  type: string;
  timestamp: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface WebSocketMessage {
  type: string;
  data: unknown;
  timestamp: string;
}
