import { useState } from 'react';
import type { Escalation } from '../api/types';
import StatusBadge from './StatusBadge';

interface EscalationCardProps {
  escalation: Escalation;
  onResolve?: (resolution: string, customInput?: string) => void;
}

const severityBorderColors: Record<string, string> = {
  critical: '#f85149',
  high: '#d29922',
  medium: '#58a6ff',
  low: '#484f58',
};

function EscalationCard({ escalation, onResolve }: EscalationCardProps) {
  const [customInput, setCustomInput] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const isResolved = escalation.status !== 'pending';
  const borderColor = severityBorderColors[escalation.severity] ?? '#484f58';

  return (
    <div
      className={`bg-gray-800 rounded-lg border border-gray-700 overflow-hidden ${isResolved ? 'opacity-60' : ''}`}
      style={{ borderLeftWidth: 4, borderLeftColor: borderColor }}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <StatusBadge status={escalation.severity} />
          <StatusBadge status={escalation.category} />
          <StatusBadge status={escalation.status} />
          {escalation.source_agent_id && (
            <span className="text-xs font-mono text-gray-500 ml-auto">
              {escalation.source_agent_id}
            </span>
          )}
        </div>

        {/* Summary */}
        <h3 className="text-sm font-semibold text-gray-100 mb-3">{escalation.summary}</h3>

        {/* Options */}
        {escalation.options.length > 0 && (
          <div className="space-y-2 mb-3">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Options</span>
            {escalation.options.map((opt, i) => (
              <div
                key={i}
                className={`p-3 rounded border ${
                  escalation.recommended_option === opt.label
                    ? 'border-indigo-400 bg-indigo-400/5'
                    : 'border-gray-700 bg-gray-900'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-gray-200">{opt.label}</span>
                  {escalation.recommended_option === opt.label && (
                    <span className="text-[10px] font-mono uppercase tracking-wider text-indigo-400 bg-indigo-400/10 px-1.5 py-0.5 rounded">
                      recommended
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mb-1">{opt.description}</p>
                <p className="text-xs text-gray-500 italic">Tradeoff: {opt.tradeoff}</p>
              </div>
            ))}
          </div>
        )}

        {/* Reasoning */}
        {escalation.reasoning && (
          <div className="mb-3">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Reasoning</span>
            <p className="text-xs text-gray-300 mt-1">{escalation.reasoning}</p>
          </div>
        )}

        {/* Risk if wrong */}
        {escalation.risk_if_wrong && (
          <div className="bg-red-900/20 border border-red-700/50 rounded p-3 mb-3">
            <span className="text-xs font-medium text-red-300 uppercase tracking-wider">Risk if wrong</span>
            <p className="text-xs text-red-200 mt-1">{escalation.risk_if_wrong}</p>
          </div>
        )}

        {/* Resolution details (if resolved) */}
        {isResolved && escalation.resolution && (
          <div className="bg-gray-900 border border-gray-700 rounded p-3 mb-3">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Resolution</span>
            <p className="text-xs text-gray-300 mt-1">{escalation.resolution}</p>
            {escalation.resolved_by && (
              <p className="text-xs text-gray-500 mt-1">
                Resolved by {escalation.resolved_by}
                {escalation.resolved_at && ` at ${new Date(escalation.resolved_at).toLocaleString()}`}
              </p>
            )}
          </div>
        )}

        {/* Action buttons */}
        {!isResolved && onResolve && (
          <div className="flex flex-wrap gap-2 mt-4">
            {escalation.options.map((opt) => (
              <button
                key={opt.label}
                onClick={() => onResolve(opt.label)}
                className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                  escalation.recommended_option === opt.label
                    ? 'bg-indigo-600 text-white hover:bg-indigo-500'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {opt.label}
              </button>
            ))}
            <button
              onClick={() => setShowCustom(!showCustom)}
              className="px-3 py-1.5 text-xs font-medium rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
            >
              Custom Input
            </button>
          </div>
        )}

        {/* Custom input field */}
        {!isResolved && showCustom && onResolve && (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              placeholder="Enter custom resolution..."
              className="flex-1 bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-400"
            />
            <button
              onClick={() => {
                if (customInput.trim()) {
                  onResolve('custom', customInput.trim());
                  setCustomInput('');
                  setShowCustom(false);
                }
              }}
              className="px-3 py-1.5 text-xs font-medium rounded bg-indigo-600 text-white hover:bg-indigo-500 transition-colors"
            >
              Submit
            </button>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-gray-900 border-t border-gray-700 flex items-center gap-4 text-[10px] text-gray-500 font-mono">
        <span>{escalation.id}</span>
        <span>{new Date(escalation.created_at).toLocaleString()}</span>
        {escalation.expires_at && (
          <span>Expires: {new Date(escalation.expires_at).toLocaleString()}</span>
        )}
      </div>
    </div>
  );
}

export default EscalationCard;
