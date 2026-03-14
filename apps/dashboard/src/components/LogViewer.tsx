import { useEffect, useRef } from 'react';
import type { TaskLogEntry } from '../api/types';

interface LogViewerProps {
  entries: TaskLogEntry[];
}

const levelColors: Record<string, string> = {
  INFO: 'text-gray-400',
  WARN: 'text-yellow-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  DEBUG: 'text-blue-400',
};

function LogViewer({ entries }: LogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when entries change
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <div
      ref={containerRef}
      className="bg-gray-950 rounded-lg border border-gray-800 p-4 max-h-96 overflow-y-auto font-mono text-xs leading-relaxed"
    >
      {entries.length === 0 ? (
        <p className="text-gray-600 italic">No log entries.</p>
      ) : (
        entries.map((entry, index) => {
          const color = levelColors[entry.level.toUpperCase()] || 'text-gray-400';
          const time = new Date(entry.timestamp).toLocaleTimeString();

          return (
            <div key={index} className="flex gap-2 hover:bg-gray-900/50 px-1 py-0.5 rounded">
              <span className="text-gray-600 flex-shrink-0">{time}</span>
              <span className={`flex-shrink-0 w-12 text-right ${color}`}>
                {entry.level}
              </span>
              <span className="text-gray-500 flex-shrink-0">[{entry.source}]</span>
              <span className="text-gray-300">{entry.message}</span>
            </div>
          );
        })
      )}
    </div>
  );
}

export default LogViewer;
