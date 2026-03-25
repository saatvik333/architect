import { useCallback } from 'react';
import { fetchProgress } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import MetricCard from '../components/MetricCard';
import EscalationCard from '../components/EscalationCard';
import ActivityItem from '../components/ActivityItem';
import StatusBadge from '../components/StatusBadge';

function Progress() {
  const progressFetcher = useCallback(
    (signal: AbortSignal) => fetchProgress(signal),
    [],
  );
  const { data: progress, error, loading } = usePolling(progressFetcher, 5000);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Progress</h2>

      {loading && !progress && (
        <p className="text-gray-500">Loading progress...</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-4 mb-4">
          Failed to load progress: {error.message}
        </div>
      )}

      {progress && (
        <>
          {/* Project header */}
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6 flex items-center gap-4">
            <div>
              <h3 className="text-lg font-semibold text-gray-100">{progress.project_name}</h3>
              <div className="mt-1">
                <StatusBadge status={progress.status} />
              </div>
            </div>
            <div className="ml-auto text-right">
              <div className="text-3xl font-bold text-gray-100">{progress.completion_pct}%</div>
              <div className="text-xs text-gray-500">Overall completion</div>
            </div>
          </div>

          {/* Metrics grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <MetricCard
              label="Task Progress"
              value={`${progress.tasks_completed} / ${progress.tasks_total}`}
              progress={progress.tasks_total > 0 ? (progress.tasks_completed / progress.tasks_total) * 100 : 0}
            />
            <MetricCard
              label="Budget Consumed"
              value={`${progress.budget_consumed_pct}%`}
              progress={progress.budget_consumed_pct}
              threshold={80}
              danger={95}
            />
            <MetricCard
              label="Tests"
              value={`${progress.tests_passing} passing / ${progress.tests_failing} failing`}
              progress={
                progress.tests_passing + progress.tests_failing > 0
                  ? (progress.tests_passing / (progress.tests_passing + progress.tests_failing)) * 100
                  : 0
              }
              threshold={70}
              danger={50}
            />
            <MetricCard
              label="Coverage"
              value={`${progress.coverage_pct}%`}
              progress={progress.coverage_pct}
            />
          </div>

          {/* Blockers */}
          {progress.blockers.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
                Blockers ({progress.blockers.length})
              </h3>
              <div className="space-y-4">
                {progress.blockers.map((esc) => (
                  <EscalationCard key={esc.id} escalation={esc} />
                ))}
              </div>
            </div>
          )}

          {/* Recent activity */}
          {progress.recent_events.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
                Recent Activity
              </h3>
              <div className="bg-gray-800 rounded-lg border border-gray-700 divide-y divide-gray-700">
                {progress.recent_events.map((event) => (
                  <ActivityItem key={event.id} event={event} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default Progress;
