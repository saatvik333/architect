import type { ActivityEvent } from '../api/types';

interface ActivityItemProps {
  event: ActivityEvent;
}

const eventTypeColors: Record<string, { bg: string; color: string; border: string }> = {
  task:       { bg: 'rgba(88,166,255,0.1)',  color: '#58a6ff', border: '#1f6feb' },
  proposal:   { bg: 'rgba(139,148,158,0.1)', color: '#8b949e', border: '#484f58' },
  escalation: { bg: 'rgba(248,81,73,0.1)',   color: '#f85149', border: '#da3633' },
  approval:   { bg: 'rgba(210,153,34,0.1)',  color: '#d29922', border: '#9e6a03' },
  build:      { bg: 'rgba(63,185,80,0.1)',   color: '#3fb950', border: '#238636' },
  deploy:     { bg: 'rgba(0,217,255,0.1)',   color: '#00d9ff', border: '#1f6feb' },
  test:       { bg: 'rgba(63,185,80,0.1)',   color: '#3fb950', border: '#238636' },
  error:      { bg: 'rgba(248,81,73,0.1)',   color: '#f85149', border: '#da3633' },
};

function formatRelativeTime(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

function ActivityItem({ event }: ActivityItemProps) {
  const typeCfg = eventTypeColors[event.type] ?? eventTypeColors.proposal;

  return (
    <div className="flex items-start gap-3 py-2.5 px-3 hover:bg-gray-700/30 rounded transition-colors">
      {/* Timestamp */}
      <span className="text-[10px] font-mono text-gray-500 w-14 flex-shrink-0 pt-0.5 text-right">
        {formatRelativeTime(event.timestamp)}
      </span>

      {/* Event type badge */}
      <span
        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold tracking-wider flex-shrink-0"
        style={{
          background: typeCfg.bg,
          color: typeCfg.color,
          border: `1px solid ${typeCfg.border}`,
        }}
      >
        {event.type}
      </span>

      {/* Summary */}
      <span className="text-xs text-gray-300 leading-relaxed">{event.summary}</span>
    </div>
  );
}

export default ActivityItem;
