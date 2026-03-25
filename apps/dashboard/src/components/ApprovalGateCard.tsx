import type { ApprovalGate } from '../api/types';
import StatusBadge from './StatusBadge';

interface ApprovalGateCardProps {
  gate: ApprovalGate;
  onVote?: (decision: 'approve' | 'deny') => void;
}

function ApprovalGateCard({ gate, onVote }: ApprovalGateCardProps) {
  const isPending = gate.status === 'pending';
  const progressPct = gate.required_approvals > 0
    ? Math.min(100, (gate.current_approvals / gate.required_approvals) * 100)
    : 0;

  return (
    <div className={`bg-gray-800 rounded-lg border border-gray-700 overflow-hidden ${!isPending ? 'opacity-60' : ''}`}>
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm font-semibold text-gray-200">{gate.action_type}</span>
          <StatusBadge status={gate.status} />
          {gate.resource_id && (
            <span className="text-xs font-mono text-gray-500 ml-auto">{gate.resource_id}</span>
          )}
        </div>

        {/* Vote progress */}
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-400">
              Approvals: {gate.current_approvals} / {gate.required_approvals}
            </span>
            <span className="text-xs text-gray-500">{Math.round(progressPct)}%</span>
          </div>
          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${progressPct}%`,
                background: progressPct >= 100
                  ? 'linear-gradient(90deg, #238636, #3fb950)'
                  : 'linear-gradient(90deg, #1f6feb, #00d9ff)',
              }}
            />
          </div>
        </div>

        {/* Context summary */}
        {Object.keys(gate.context).length > 0 && (
          <div className="mb-3">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Context</span>
            <div className="mt-1 bg-gray-900 rounded p-2">
              {Object.entries(gate.context).map(([key, val]) => (
                <div key={key} className="flex gap-2 text-xs">
                  <span className="text-gray-500 font-mono">{key}:</span>
                  <span className="text-gray-300">{String(val)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action buttons */}
        {isPending && onVote && (
          <div className="flex gap-2 mt-4">
            <button
              onClick={() => onVote('approve')}
              className="px-4 py-1.5 text-xs font-medium rounded bg-green-600 text-white hover:bg-green-500 transition-colors"
            >
              Approve
            </button>
            <button
              onClick={() => onVote('deny')}
              className="px-4 py-1.5 text-xs font-medium rounded bg-red-700 text-white hover:bg-red-600 transition-colors"
            >
              Deny
            </button>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-gray-900 border-t border-gray-700 flex items-center gap-4 text-[10px] text-gray-500 font-mono">
        <span>{gate.id}</span>
        <span>{new Date(gate.created_at).toLocaleString()}</span>
        {gate.expires_at && (
          <span>Expires: {new Date(gate.expires_at).toLocaleString()}</span>
        )}
      </div>
    </div>
  );
}

export default ApprovalGateCard;
