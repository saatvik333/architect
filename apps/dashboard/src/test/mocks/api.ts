import type { TaskStatus, TaskLogs, HealthStatus, Proposal } from '../../api/types';

export const mockTasks: TaskStatus[] = [
  {
    task_id: 'task-001',
    name: 'Build authentication module',
    status: 'running',
    progress: 45,
    children: ['task-002', 'task-003'],
    created_at: '2026-03-15T10:00:00Z',
    updated_at: '2026-03-15T10:30:00Z',
  },
  {
    task_id: 'task-002',
    name: 'Implement login endpoint',
    status: 'completed',
    progress: 100,
    children: [],
    created_at: '2026-03-15T10:05:00Z',
    updated_at: '2026-03-15T10:25:00Z',
  },
  {
    task_id: 'task-003',
    name: 'Write unit tests',
    status: 'pending',
    progress: 0,
    children: [],
    created_at: '2026-03-15T10:05:00Z',
    updated_at: '2026-03-15T10:05:00Z',
  },
  {
    task_id: 'task-004',
    name: 'Database migration',
    status: 'failed',
    progress: 72,
    children: [],
    created_at: '2026-03-15T09:00:00Z',
    updated_at: '2026-03-15T09:45:00Z',
  },
];

export const mockTask: TaskStatus = mockTasks[0];

export const mockTaskLogs: TaskLogs = {
  task_id: 'task-001',
  entries: [
    {
      timestamp: '2026-03-15T10:00:00Z',
      level: 'INFO',
      message: 'Task started',
      source: 'task-engine',
    },
    {
      timestamp: '2026-03-15T10:10:00Z',
      level: 'INFO',
      message: 'Generating code for auth module',
      source: 'coding-agent',
    },
    {
      timestamp: '2026-03-15T10:20:00Z',
      level: 'WARN',
      message: 'Retrying API call',
      source: 'coding-agent',
    },
  ],
};

export const mockHealth: HealthStatus = {
  status: 'healthy',
  services: {
    'task-graph-engine': 'healthy',
    'world-state-ledger': 'healthy',
    'execution-sandbox': 'degraded',
    'evaluation-engine': 'healthy',
    'coding-agent': 'down',
  },
  version: '0.1.0',
};

export const mockProposals: Proposal[] = [
  {
    proposal_id: 'prop-001',
    task_id: 'task-001',
    agent_id: 'agent-alpha',
    mutations: [{ type: 'file_create', path: '/src/auth.ts' }],
    verdict: 'accepted',
    created_at: '2026-03-15T10:15:00Z',
  },
  {
    proposal_id: 'prop-002',
    task_id: 'task-001',
    agent_id: 'agent-beta',
    mutations: [{ type: 'file_modify', path: '/src/db.ts' }],
    verdict: 'pending',
    created_at: '2026-03-15T10:20:00Z',
  },
  {
    proposal_id: 'prop-003',
    task_id: 'task-004',
    agent_id: 'agent-alpha',
    mutations: [],
    verdict: 'rejected',
    created_at: '2026-03-15T09:30:00Z',
  },
];
