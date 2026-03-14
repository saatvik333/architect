import { useParams, useNavigate } from 'react-router-dom';
import { useCallback, useState } from 'react';
import { fetchTask, fetchTaskLogs, fetchProposals, cancelTask } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import StatusBadge from '../components/StatusBadge';
import ProgressBar from '../components/ProgressBar';
import Timeline from '../components/Timeline';
import LogViewer from '../components/LogViewer';

function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [cancelling, setCancelling] = useState(false);

  const taskFetcher = useCallback(() => fetchTask(taskId!), [taskId]);
  const logsFetcher = useCallback(() => fetchTaskLogs(taskId!), [taskId]);
  const proposalsFetcher = useCallback(() => fetchProposals(taskId!), [taskId]);

  const { data: task, error: taskError, loading: taskLoading } = usePolling(taskFetcher, 3000);
  const { data: logs } = usePolling(logsFetcher, 3000);
  const { data: proposals } = usePolling(proposalsFetcher, 5000);

  const handleCancel = async (force: boolean) => {
    if (!taskId) return;
    setCancelling(true);
    try {
      await cancelTask(taskId, force);
    } catch {
      // Error will be reflected in next poll
    } finally {
      setCancelling(false);
    }
  };

  if (taskLoading && !task) {
    return <p className="text-gray-500">Loading task...</p>;
  }

  if (taskError) {
    return (
      <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-4">
        Failed to load task: {taskError.message}
      </div>
    );
  }

  if (!task) {
    return <p className="text-gray-500">Task not found.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button
            onClick={() => navigate('/tasks')}
            className="text-sm text-gray-500 hover:text-gray-300 mb-2 inline-block"
          >
            &larr; Back to Tasks
          </button>
          <h2 className="text-2xl font-bold">{task.name}</h2>
        </div>
        {task.status === 'running' && (
          <div className="flex gap-2">
            <button
              onClick={() => handleCancel(false)}
              disabled={cancelling}
              className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-sm font-medium rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => handleCancel(true)}
              disabled={cancelling}
              className="px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-sm font-medium rounded-lg transition-colors"
            >
              Force Cancel
            </button>
          </div>
        )}
      </div>

      {/* Metadata Card */}
      <div className="bg-gray-800 rounded-lg shadow-lg p-6 border border-gray-700">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider">Task ID</dt>
            <dd className="font-mono text-sm text-gray-300 mt-1">{task.task_id}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider">Status</dt>
            <dd className="mt-1">
              <StatusBadge status={task.status} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider">Created</dt>
            <dd className="text-sm text-gray-300 mt-1">
              {new Date(task.created_at).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wider">Updated</dt>
            <dd className="text-sm text-gray-300 mt-1">
              {new Date(task.updated_at).toLocaleString()}
            </dd>
          </div>
        </div>
        <div>
          <dt className="text-xs text-gray-500 uppercase tracking-wider mb-2">Progress</dt>
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <ProgressBar progress={task.progress} />
            </div>
            <span className="text-sm font-medium text-gray-300">{task.progress}%</span>
          </div>
        </div>
        {task.children.length > 0 && (
          <div className="mt-4">
            <dt className="text-xs text-gray-500 uppercase tracking-wider mb-2">
              Children ({task.children.length})
            </dt>
            <div className="flex flex-wrap gap-2">
              {task.children.map((childId) => (
                <button
                  key={childId}
                  onClick={() => navigate(`/tasks/${childId}`)}
                  className="font-mono text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded transition-colors"
                >
                  {childId}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Timeline */}
      {logs && logs.entries.length > 0 && (
        <div className="bg-gray-800 rounded-lg shadow-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Timeline</h3>
          <Timeline entries={logs.entries.slice(-20)} />
        </div>
      )}

      {/* Logs */}
      {logs && (
        <div className="bg-gray-800 rounded-lg shadow-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Logs</h3>
          <LogViewer entries={logs.entries} />
        </div>
      )}

      {/* Proposals */}
      {proposals && proposals.length > 0 && (
        <div className="bg-gray-800 rounded-lg shadow-lg p-6 border border-gray-700">
          <h3 className="text-lg font-semibold mb-4">Proposals</h3>
          <div className="space-y-3">
            {proposals.map((proposal) => (
              <div
                key={proposal.proposal_id}
                className="bg-gray-900 rounded-lg p-4 border border-gray-700"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-xs text-gray-400">
                    {proposal.proposal_id}
                  </span>
                  <StatusBadge status={proposal.verdict} />
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
                  <div>
                    Agent: <span className="font-mono text-gray-400">{proposal.agent_id}</span>
                  </div>
                  <div>
                    Created: {new Date(proposal.created_at).toLocaleString()}
                  </div>
                </div>
                {proposal.mutations.length > 0 && (
                  <details className="mt-2">
                    <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300">
                      Mutations ({proposal.mutations.length})
                    </summary>
                    <pre className="mt-2 text-xs bg-gray-950 p-2 rounded overflow-x-auto text-gray-400">
                      {JSON.stringify(proposal.mutations, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default TaskDetail;
