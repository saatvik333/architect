interface StatusBadgeProps {
  status: string;
}

const statusStyles: Record<string, string> = {
  pending: 'bg-gray-600/30 text-gray-300 border-gray-600',
  running: 'bg-blue-600/30 text-blue-300 border-blue-600',
  completed: 'bg-green-600/30 text-green-300 border-green-600',
  failed: 'bg-red-600/30 text-red-300 border-red-600',
  blocked: 'bg-yellow-600/30 text-yellow-300 border-yellow-600',
  cancelled: 'bg-gray-600/30 text-gray-400 border-gray-600',
  accepted: 'bg-green-600/30 text-green-300 border-green-600',
  rejected: 'bg-red-600/30 text-red-300 border-red-600',
};

function StatusBadge({ status }: StatusBadgeProps) {
  const style = statusStyles[status] || statusStyles.pending;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${style}`}
    >
      {status}
    </span>
  );
}

export default StatusBadge;
