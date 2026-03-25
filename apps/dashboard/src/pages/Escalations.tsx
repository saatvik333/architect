import { useState, useCallback, useMemo } from 'react';
import { fetchEscalations, fetchEscalationStats, resolveEscalation } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import EscalationCard from '../components/EscalationCard';
import NotificationBanner from '../components/NotificationBanner';
import type { Escalation } from '../api/types';

function Escalations() {
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  const escalationsFetcher = useCallback(
    (signal: AbortSignal) =>
      fetchEscalations(
        {
          status: statusFilter || undefined,
          category: categoryFilter || undefined,
          severity: severityFilter || undefined,
        },
        signal,
      ),
    [statusFilter, categoryFilter, severityFilter],
  );

  const statsFetcher = useCallback(
    (signal: AbortSignal) => fetchEscalationStats(signal),
    [],
  );

  const { data: escalations, error, loading } = usePolling(escalationsFetcher, 3000);
  const { data: stats } = usePolling(statsFetcher, 5000);

  const handleResolve = async (escalation: Escalation, resolution: string, customInput?: string) => {
    try {
      await resolveEscalation(escalation.id, {
        resolved_by: 'dashboard_user',
        resolution,
        custom_input: customInput,
      });
    } catch (err) {
      console.error('Failed to resolve escalation:', err);
    }
  };

  // Separate pending escalations that need notification banners (critical/high)
  const pendingCritical = useMemo(
    () =>
      (escalations ?? []).filter(
        (e) => e.status === 'pending' && (e.severity === 'critical' || e.severity === 'high') && !dismissedIds.has(e.id),
      ),
    [escalations, dismissedIds],
  );

  // Sort: pending first, then by created_at descending.
  // Memoized to avoid re-sorting on every render.
  const sorted = useMemo(
    () =>
      [...(escalations ?? [])].sort((a, b) => {
        if (a.status === 'pending' && b.status !== 'pending') return -1;
        if (a.status !== 'pending' && b.status === 'pending') return 1;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }),
    [escalations],
  );

  return (
    <div>
      {/* Notification banners for critical/high */}
      {pendingCritical.map((esc) => (
        <NotificationBanner
          key={esc.id}
          escalation={esc}
          onView={() => {
            const el = document.getElementById(`escalation-${esc.id}`);
            el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }}
          onDismiss={() => setDismissedIds((prev) => new Set([...prev, esc.id]))}
        />
      ))}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold">Escalations</h2>
          {stats && stats.pending > 0 && (
            <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-red-900/50 text-red-300 border border-red-700">
              {stats.pending} pending
            </span>
          )}
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-indigo-400"
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="resolved">Resolved</option>
            <option value="expired">Expired</option>
            <option value="auto_resolved">Auto-resolved</option>
          </select>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-indigo-400"
          >
            <option value="">All categories</option>
            <option value="confidence">Confidence</option>
            <option value="security">Security</option>
            <option value="budget">Budget</option>
            <option value="architectural">Architectural</option>
          </select>

          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-indigo-400"
          >
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      {loading && !escalations && (
        <p className="text-gray-500">Loading escalations...</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-4 mb-4">
          Failed to load escalations: {error.message}
        </div>
      )}

      {escalations && escalations.length === 0 && (
        <p className="text-gray-500 italic">No escalations found.</p>
      )}

      {sorted.length > 0 && (
        <div className="space-y-4">
          {sorted.map((esc) => (
            <div key={esc.id} id={`escalation-${esc.id}`}>
              <EscalationCard
                escalation={esc}
                onResolve={(resolution, customInput) => handleResolve(esc, resolution, customInput)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Escalations;
