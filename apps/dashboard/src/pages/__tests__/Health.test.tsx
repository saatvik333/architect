import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Health from '../Health';
import { mockHealth } from '../../test/mocks/api';

vi.mock('../../api/client', () => ({
  fetchHealth: vi.fn(),
}));

import { fetchHealth } from '../../api/client';

const mockedFetchHealth = vi.mocked(fetchHealth);

describe('Health', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    mockedFetchHealth.mockReturnValue(new Promise(() => {}));
    render(<Health />);
    expect(screen.getByText('Checking health...')).toBeInTheDocument();
  });

  it('renders overall status when healthy', async () => {
    mockedFetchHealth.mockResolvedValue(mockHealth);
    render(<Health />);

    expect(await screen.findByText('Overall Status')).toBeInTheDocument();
    expect(screen.getByText('All systems operational')).toBeInTheDocument();
  });

  it('renders the version', async () => {
    mockedFetchHealth.mockResolvedValue(mockHealth);
    render(<Health />);

    await screen.findByText('Overall Status');
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
  });

  it('renders service health cards', async () => {
    mockedFetchHealth.mockResolvedValue(mockHealth);
    render(<Health />);

    await screen.findByText('Overall Status');
    expect(screen.getByText('task-graph-engine')).toBeInTheDocument();
    expect(screen.getByText('world-state-ledger')).toBeInTheDocument();
    expect(screen.getByText('execution-sandbox')).toBeInTheDocument();
    expect(screen.getByText('evaluation-engine')).toBeInTheDocument();
    expect(screen.getByText('coding-agent')).toBeInTheDocument();
  });

  it('shows degraded overall message when not healthy', async () => {
    mockedFetchHealth.mockResolvedValue({ ...mockHealth, status: 'degraded' });
    render(<Health />);

    expect(await screen.findByText('System is degraded')).toBeInTheDocument();
  });

  it('shows error message on fetch failure', async () => {
    mockedFetchHealth.mockRejectedValue(new Error('Connection refused'));
    render(<Health />);

    expect(await screen.findByText(/Failed to reach API/)).toBeInTheDocument();
    expect(screen.getByText(/Connection refused/)).toBeInTheDocument();
  });

  it('renders the page heading', () => {
    mockedFetchHealth.mockReturnValue(new Promise(() => {}));
    render(<Health />);
    expect(screen.getByText('System Health')).toBeInTheDocument();
  });

  it('renders service status text per card', async () => {
    mockedFetchHealth.mockResolvedValue(mockHealth);
    render(<Health />);

    await screen.findByText('task-graph-engine');
    // Check that "healthy", "degraded", "down" statuses are rendered as text in service cards
    const healthyTexts = screen.getAllByText('healthy');
    expect(healthyTexts.length).toBeGreaterThanOrEqual(3); // overall + 3 healthy services
    expect(screen.getByText('degraded')).toBeInTheDocument();
    expect(screen.getByText('down')).toBeInTheDocument();
  });
});
