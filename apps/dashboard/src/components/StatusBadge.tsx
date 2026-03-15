interface StatusBadgeProps {
  status: string;
}

interface BadgeConfig {
  bg: string;
  color: string;
  border: string;
  dot?: string;
  pulse?: boolean;
}

const statusConfig: Record<string, BadgeConfig> = {
  pending:   { bg: 'rgba(139,148,158,0.1)',  color: '#8b949e', border: '#484f58' },
  running:   { bg: 'rgba(88,166,255,0.1)',   color: '#58a6ff', border: '#1f6feb', dot: '#58a6ff', pulse: true },
  completed: { bg: 'rgba(63,185,80,0.1)',    color: '#3fb950', border: '#238636', dot: '#3fb950' },
  failed:    { bg: 'rgba(248,81,73,0.1)',    color: '#f85149', border: '#da3633', dot: '#f85149' },
  blocked:   { bg: 'rgba(210,153,34,0.1)',   color: '#d29922', border: '#9e6a03', dot: '#d29922' },
  cancelled: { bg: 'rgba(139,148,158,0.08)', color: '#6e7681', border: '#30363d' },
  accepted:  { bg: 'rgba(63,185,80,0.1)',    color: '#3fb950', border: '#238636', dot: '#3fb950' },
  rejected:  { bg: 'rgba(248,81,73,0.1)',    color: '#f85149', border: '#da3633', dot: '#f85149' },
  healthy:   { bg: 'rgba(63,185,80,0.1)',    color: '#3fb950', border: '#238636', dot: '#3fb950' },
  degraded:  { bg: 'rgba(210,153,34,0.1)',   color: '#d29922', border: '#9e6a03', dot: '#d29922' },
  down:      { bg: 'rgba(248,81,73,0.1)',    color: '#f85149', border: '#da3633', dot: '#f85149' },
};

function StatusBadge({ status }: StatusBadgeProps) {
  const cfg = statusConfig[status] ?? statusConfig.pending;

  return (
    <span
      className="status-badge"
      style={{ background: cfg.bg, color: cfg.color, borderColor: cfg.border }}
    >
      {cfg.dot && (
        <span
          className={`status-dot${cfg.pulse ? ' status-dot-running' : ''}`}
          style={{ background: cfg.dot }}
        />
      )}
      {status}
    </span>
  );
}

export default StatusBadge;
