import { useCallback } from 'react';
import { fetchProgress, fetchEscalations } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import MetricCard from '../components/MetricCard';
import EscalationCard from '../components/EscalationCard';

function getBudgetStatusLabel(pct: number): string {
  if (pct >= 95) return 'CRITICAL';
  if (pct >= 80) return 'WARNING';
  return 'NORMAL';
}

function getBudgetStatusColor(pct: number): string {
  if (pct >= 95) return '#f85149';
  if (pct >= 80) return '#d29922';
  return '#3fb950';
}

function getBudgetBarGradient(pct: number): string {
  if (pct >= 95) return 'linear-gradient(90deg, #da3633, #f85149)';
  if (pct >= 80) return 'linear-gradient(90deg, #9e6a03, #d29922)';
  return 'linear-gradient(90deg, #238636, #3fb950)';
}

function Budget() {
  const progressFetcher = useCallback(
    (signal: AbortSignal) => fetchProgress(signal),
    [],
  );
  const budgetEscalationsFetcher = useCallback(
    (signal: AbortSignal) => fetchEscalations({ category: 'budget', status: 'pending' }, signal),
    [],
  );

  const { data: progress, error: progressError, loading: progressLoading } = usePolling(progressFetcher, 5000);
  const { data: budgetEscalations } = usePolling(budgetEscalationsFetcher, 5000);

  const isUnavailable = progressError && !progress;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Budget</h2>

      {progressLoading && !progress && (
        <p className="text-gray-500">Loading budget data...</p>
      )}

      {isUnavailable && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
          <div className="text-gray-500 text-lg mb-2">Budget data unavailable</div>
          <p className="text-gray-600 text-sm">
            The Economic Governor service may be offline. Budget tracking will resume when the service becomes available.
          </p>
        </div>
      )}

      {progress && (
        <>
          {/* Budget overview */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <MetricCard
              label="Budget Consumed"
              value={`${progress.budget_consumed_pct}%`}
              progress={progress.budget_consumed_pct}
              threshold={80}
              danger={95}
            />
            <MetricCard
              label="Budget Remaining"
              value={`${Math.max(0, 100 - progress.budget_consumed_pct)}%`}
              progress={Math.max(0, 100 - progress.budget_consumed_pct)}
            />
            <MetricCard
              label="Task Efficiency"
              value={
                progress.tasks_total > 0
                  ? `${((progress.tasks_completed / progress.tasks_total) * 100).toFixed(1)}%`
                  : 'N/A'
              }
              progress={
                progress.tasks_total > 0
                  ? (progress.tasks_completed / progress.tasks_total) * 100
                  : 0
              }
            />
          </div>

          {/* Budget status indicator */}
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-6">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-300">Budget Allocation</span>
              <span
                className="text-xs font-mono font-semibold"
                style={{ color: getBudgetStatusColor(progress.budget_consumed_pct) }}
              >
                {getBudgetStatusLabel(progress.budget_consumed_pct)}
              </span>
            </div>
            <div className="w-full h-4 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(100, progress.budget_consumed_pct)}%`,
                  background: getBudgetBarGradient(progress.budget_consumed_pct),
                }}
              />
            </div>
            <div className="flex justify-between mt-2 text-[10px] font-mono text-gray-500">
              <span>0%</span>
              <span className="text-yellow-300">80%</span>
              <span className="text-red-300">95%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Active budget warnings */}
          {budgetEscalations && budgetEscalations.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
                Active Warnings ({budgetEscalations.length})
              </h3>
              <div className="space-y-4">
                {budgetEscalations.map((esc) => (
                  <EscalationCard key={esc.id} escalation={esc} />
                ))}
              </div>
            </div>
          )}

          {budgetEscalations && budgetEscalations.length === 0 && (
            <p className="text-gray-500 italic text-sm">No active budget warnings.</p>
          )}
        </>
      )}
    </div>
  );
}

export default Budget;
