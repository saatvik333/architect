import StatusBadge from './StatusBadge';

interface AgentCardProps {
  id: string;
  type: string;
  status: string;
}

function AgentCard({ id, type, status }: AgentCardProps) {
  return (
    <div className="bg-gray-800 rounded-lg shadow-lg p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-200">{type}</h3>
        <StatusBadge status={status} />
      </div>
      <p className="font-mono text-xs text-gray-500 truncate" title={id}>
        {id}
      </p>
    </div>
  );
}

export default AgentCard;
