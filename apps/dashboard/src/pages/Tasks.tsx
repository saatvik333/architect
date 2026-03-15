import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchTasks } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import StatusBadge from '../components/StatusBadge';
import ProgressBar from '../components/ProgressBar';
import TaskDAG from '../components/TaskDAG';

type ViewMode = 'table' | 'dag';

function Tasks() {
  const { data: tasks, error, loading } = usePolling(fetchTasks, 3000);
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<ViewMode>('table');

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Tasks</h2>

        {tasks && tasks.length > 0 && (
          <div className="flex items-center bg-gray-800 rounded-lg border border-gray-700 p-0.5">
            <button
              onClick={() => setViewMode('table')}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                viewMode === 'table'
                  ? 'bg-gray-700 text-gray-200 shadow'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              Table
            </button>
            <button
              onClick={() => setViewMode('dag')}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                viewMode === 'dag'
                  ? 'bg-gray-700 text-gray-200 shadow'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              DAG
            </button>
          </div>
        )}
      </div>

      {loading && !tasks && (
        <p className="text-gray-500">Loading tasks...</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-4 mb-4">
          Failed to load tasks: {error.message}
        </div>
      )}

      {tasks && tasks.length === 0 && (
        <p className="text-gray-500 italic">No tasks found.</p>
      )}

      {tasks && tasks.length > 0 && viewMode === 'dag' && (
        <TaskDAG tasks={tasks} />
      )}

      {tasks && tasks.length > 0 && viewMode === 'table' && (
        <div className="bg-gray-800 rounded-lg shadow-lg overflow-hidden border border-gray-700">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 w-48">Progress</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {tasks.map((task) => (
                <tr
                  key={task.task_id}
                  onClick={() => navigate(`/tasks/${task.task_id}`)}
                  className="hover:bg-gray-750 hover:bg-gray-700/50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">
                    {task.task_id}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-200">
                    {task.name}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={task.status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <ProgressBar progress={task.progress} />
                      <span className="text-xs text-gray-500 w-10 text-right">
                        {task.progress}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {new Date(task.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default Tasks;
