import type { Escalation } from '../api/types';

interface NotificationBannerProps {
  escalation: Escalation;
  onView: () => void;
  onDismiss: () => void;
}

function NotificationBanner({ escalation, onView, onDismiss }: NotificationBannerProps) {
  const isCritical = escalation.severity === 'critical';
  const bgClass = isCritical
    ? 'bg-red-900/40 border-red-700'
    : 'bg-yellow-600/20 border-yellow-600';
  const pulseClass = isCritical ? 'animate-pulse' : '';

  return (
    <div className={`${bgClass} ${pulseClass} border rounded-lg px-4 py-3 flex items-center gap-3 mb-4`}>
      {/* Severity dot */}
      <span
        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
        style={{
          background: isCritical ? '#f85149' : '#d29922',
          boxShadow: isCritical ? '0 0 8px rgba(248,81,73,0.6)' : '0 0 8px rgba(210,153,34,0.4)',
        }}
      />

      {/* Message */}
      <span className={`text-sm flex-1 ${isCritical ? 'text-red-200' : 'text-yellow-200'}`}>
        <span className="font-semibold uppercase text-xs tracking-wider mr-2">
          {escalation.severity}
        </span>
        {escalation.summary}
      </span>

      {/* View button */}
      <button
        onClick={onView}
        className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
          isCritical
            ? 'bg-red-700 text-white hover:bg-red-600'
            : 'bg-yellow-600 text-white hover:bg-yellow-500'
        }`}
      >
        View
      </button>

      {/* Dismiss */}
      <button
        onClick={onDismiss}
        className="text-gray-500 hover:text-gray-300 transition-colors text-sm"
        aria-label="Dismiss"
      >
        x
      </button>
    </div>
  );
}

export default NotificationBanner;
