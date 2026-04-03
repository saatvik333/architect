import { useState, useCallback, useEffect, useMemo } from 'react';
import { fetchActivity } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import { useWebSocket } from '../hooks/useWebSocket';
import ActivityItem from '../components/ActivityItem';
import type { ActivityEvent } from '../api/types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const wsUrl = new URL(API_URL);
wsUrl.protocol = wsUrl.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = wsUrl.toString().replace(/\/$/, '') + '/api/v1/ws';

const EVENT_TYPES = ['all', 'task', 'proposal', 'escalation', 'approval', 'build', 'deploy', 'test', 'error'];

function Activity() {
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [wsEvents, setWsEvents] = useState<ActivityEvent[]>([]);

  const activityFetcher = useCallback(
    (signal: AbortSignal) => fetchActivity(100, signal),
    [],
  );
  const { data: polledEvents, error, loading } = usePolling(activityFetcher, 5000);

  const { lastMessage, isConnected } = useWebSocket(WS_URL);

  // Merge WS events as they arrive
  useEffect(() => {
    if (lastMessage && lastMessage.type === 'activity') {
      const event = lastMessage.data as ActivityEvent;
      setWsEvents((prev) => [event, ...prev.slice(0, 199)]);
    }
  }, [lastMessage]);

  // Combine polled events with WS events, deduplicate by id.
  // Memoized to avoid re-running deduplication + sort on every render.
  const allEvents = useMemo(() => {
    const combined = [...wsEvents, ...(polledEvents ?? [])];
    const seen = new Set<string>();
    const deduped: ActivityEvent[] = [];
    for (const ev of combined) {
      if (!seen.has(ev.id)) {
        seen.add(ev.id);
        deduped.push(ev);
      }
    }
    return deduped.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [wsEvents, polledEvents]);

  const filtered = typeFilter === 'all'
    ? allEvents
    : allEvents.filter((e) => e.type === typeFilter);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold">Activity</h2>
          <span
            className="inline-flex items-center gap-1.5 text-xs font-mono"
            style={{ color: isConnected ? '#3fb950' : '#484f58' }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full inline-block"
              style={{
                background: isConnected ? '#3fb950' : '#484f58',
                boxShadow: isConnected ? '0 0 6px #3fb950' : 'none',
              }}
            />
            {isConnected ? 'live' : 'polling'}
          </span>
        </div>

        {/* Filter */}
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-indigo-400"
        >
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t === 'all' ? 'All types' : t}
            </option>
          ))}
        </select>
      </div>

      {loading && !polledEvents && (
        <p className="text-gray-500">Loading activity...</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-4 mb-4">
          Failed to load activity: {error.message}
        </div>
      )}

      {filtered.length === 0 && !loading && (
        <p className="text-gray-500 italic">No activity events found.</p>
      )}

      {filtered.length > 0 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 divide-y divide-gray-700/50">
          {filtered.map((event) => (
            <ActivityItem key={event.id} event={event} />
          ))}
        </div>
      )}
    </div>
  );
}

export default Activity;
