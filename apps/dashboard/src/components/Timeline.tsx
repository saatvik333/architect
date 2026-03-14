import type { TaskLogEntry } from '../api/types';

interface TimelineProps {
  entries: TaskLogEntry[];
}

const levelDotColors: Record<string, string> = {
  INFO: 'bg-gray-400',
  WARN: 'bg-yellow-400',
  WARNING: 'bg-yellow-400',
  ERROR: 'bg-red-400',
  DEBUG: 'bg-blue-400',
};

function Timeline({ entries }: TimelineProps) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-gray-500 italic">No events recorded yet.</p>
    );
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-3 top-0 bottom-0 w-px bg-gray-700" />

      <ul className="space-y-4">
        {entries.map((entry, index) => {
          const dotColor = levelDotColors[entry.level.toUpperCase()] || 'bg-gray-400';
          const time = new Date(entry.timestamp).toLocaleTimeString();

          return (
            <li key={index} className="relative pl-8">
              {/* Dot */}
              <div
                className={`absolute left-1.5 top-1.5 w-3 h-3 rounded-full ring-2 ring-gray-900 ${dotColor}`}
              />
              {/* Content */}
              <div>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <span>{time}</span>
                  <span className="font-mono">{entry.source}</span>
                </div>
                <p className="text-sm text-gray-300 mt-0.5">{entry.message}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default Timeline;
