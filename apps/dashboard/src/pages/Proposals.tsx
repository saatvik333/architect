import { useState } from 'react';
import { fetchProposals } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import StatusBadge from '../components/StatusBadge';
import type { Proposal } from '../api/types';

function Proposals() {
  const { data: proposals, error, loading } = usePolling(fetchProposals, 5000);
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => (prev === id ? null : id));
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Proposals</h2>

      {loading && !proposals && (
        <p className="text-gray-500">Loading proposals...</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-4 mb-4">
          Failed to load proposals: {error.message}
        </div>
      )}

      {proposals && proposals.length === 0 && (
        <p className="text-gray-500 italic">No proposals found.</p>
      )}

      {proposals && proposals.length > 0 && (
        <div className="bg-gray-800 rounded-lg shadow-lg overflow-hidden border border-gray-700">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                <th className="px-4 py-3">Proposal ID</th>
                <th className="px-4 py-3">Task ID</th>
                <th className="px-4 py-3">Agent ID</th>
                <th className="px-4 py-3">Verdict</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3 w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {proposals.map((proposal: Proposal) => (
                <>
                  <tr
                    key={proposal.proposal_id}
                    onClick={() => toggleExpand(proposal.proposal_id)}
                    className="hover:bg-gray-700/50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">
                      {proposal.proposal_id}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">
                      {proposal.task_id}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">
                      {proposal.agent_id}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={proposal.verdict} />
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {new Date(proposal.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {expanded === proposal.proposal_id ? '\u25B2' : '\u25BC'}
                    </td>
                  </tr>
                  {expanded === proposal.proposal_id && (
                    <tr key={`${proposal.proposal_id}-detail`}>
                      <td colSpan={6} className="px-4 py-3 bg-gray-900">
                        <div className="text-xs text-gray-500 mb-1">
                          Mutations ({proposal.mutations.length})
                        </div>
                        <pre className="text-xs bg-gray-950 p-3 rounded overflow-x-auto text-gray-400 font-mono">
                          {JSON.stringify(proposal.mutations, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default Proposals;
