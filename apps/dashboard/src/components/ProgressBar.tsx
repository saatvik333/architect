interface ProgressBarProps {
  progress: number;
}

function ProgressBar({ progress }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, progress));
  const done = clamped === 100;

  return (
    <div className="progress-track">
      <div
        className={`progress-fill ${done ? 'progress-fill-done' : 'progress-fill-active'}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export default ProgressBar;
