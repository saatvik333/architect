import { fetchHealth } from '../api/client';
import { usePolling } from '../hooks/usePolling';

const serviceStatusStyles: Record<string, string> = {
  healthy: 'border-green-600 bg-green-600/10',
  degraded: 'border-yellow-600 bg-yellow-600/10',
  down: 'border-red-600 bg-red-600/10',
};

const serviceStatusDots: Record<string, string> = {
  healthy: 'bg-green-400',
  degraded: 'bg-yellow-400',
  down: 'bg-red-400',
};

function Health() {
  const { data: health, error, loading } = usePolling(fetchHealth, 5000);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">System Health</h2>

      {loading && !health && (
        <p className="text-gray-500">Checking health...</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg p-4 mb-4">
          Failed to reach API: {error.message}
        </div>
      )}

      {health && (
        <>
          {/* Overall status */}
          <div className="bg-gray-800 rounded-lg shadow-lg p-6 border border-gray-700 mb-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold">Overall Status</h3>
                <p className="text-sm text-gray-400 mt-1">
                  {health.status === 'healthy'
                    ? 'All systems operational'
                    : `System is ${health.status}`}
                </p>
              </div>
              <div className="text-right">
                <span
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border ${
                    serviceStatusStyles[health.status] || serviceStatusStyles.down
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      serviceStatusDots[health.status] || serviceStatusDots.down
                    }`}
                  />
                  {health.status}
                </span>
                <p className="text-xs text-gray-500 mt-2">
                  Version: <span className="font-mono">{health.version}</span>
                </p>
              </div>
            </div>
          </div>

          {/* Service grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Object.entries(health.services).map(([name, status]) => {
              const cardStyle = serviceStatusStyles[status] || serviceStatusStyles.down;
              const dotColor = serviceStatusDots[status] || serviceStatusDots.down;

              return (
                <div
                  key={name}
                  className={`bg-gray-800 rounded-lg shadow-lg p-4 border ${cardStyle}`}
                >
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-semibold text-gray-200">{name}</h4>
                    <span className={`w-3 h-3 rounded-full ${dotColor}`} />
                  </div>
                  <p className="text-xs text-gray-400 mt-2 capitalize">{status}</p>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default Health;
