interface MetricCardProps {
  label: string;
  value: string | number;
  progress?: number;
  threshold?: number;
  danger?: number;
}

function getProgressColor(progress: number, threshold?: number, danger?: number): string {
  if (danger !== undefined && progress >= danger) {
    return 'linear-gradient(90deg, #da3633, #f85149)';
  }
  if (threshold !== undefined && progress >= threshold) {
    return 'linear-gradient(90deg, #9e6a03, #d29922)';
  }
  return 'linear-gradient(90deg, #238636, #3fb950)';
}

function getTextColor(progress: number | undefined, threshold?: number, danger?: number): string {
  if (progress === undefined) return '#e6edf3';
  if (danger !== undefined && progress >= danger) return '#f85149';
  if (threshold !== undefined && progress >= threshold) return '#d29922';
  return '#e6edf3';
}

function MetricCard({ label, value, progress, threshold, danger }: MetricCardProps) {
  const textColor = getTextColor(progress, threshold, danger);

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
        {label}
      </div>
      <div className="text-2xl font-bold mb-2" style={{ color: textColor }}>
        {value}
      </div>
      {progress !== undefined && (
        <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${Math.min(100, Math.max(0, progress))}%`,
              background: getProgressColor(progress, threshold, danger),
            }}
          />
        </div>
      )}
    </div>
  );
}

export default MetricCard;
