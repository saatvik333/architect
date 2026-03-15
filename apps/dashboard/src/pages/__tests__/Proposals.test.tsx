import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Proposals from '../Proposals';
import { mockProposals } from '../../test/mocks/api';

vi.mock('../../api/client', () => ({
  fetchProposals: vi.fn(),
}));

import { fetchProposals } from '../../api/client';

const mockedFetchProposals = vi.mocked(fetchProposals);

function renderProposals() {
  return render(
    <MemoryRouter>
      <Proposals />
    </MemoryRouter>,
  );
}

describe('Proposals', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    mockedFetchProposals.mockReturnValue(new Promise(() => {}));
    renderProposals();
    expect(screen.getByText('Loading proposals...')).toBeInTheDocument();
  });

  it('renders the page heading', () => {
    mockedFetchProposals.mockReturnValue(new Promise(() => {}));
    renderProposals();
    expect(screen.getByText('Proposals')).toBeInTheDocument();
  });

  it('renders proposal table with data', async () => {
    mockedFetchProposals.mockResolvedValue(mockProposals);
    renderProposals();

    expect(await screen.findByText('prop-001')).toBeInTheDocument();
    expect(screen.getByText('prop-002')).toBeInTheDocument();
    expect(screen.getByText('prop-003')).toBeInTheDocument();
  });

  it('renders table column headers', async () => {
    mockedFetchProposals.mockResolvedValue(mockProposals);
    renderProposals();

    await screen.findByText('prop-001');
    expect(screen.getByText('Proposal ID')).toBeInTheDocument();
    expect(screen.getByText('Task ID')).toBeInTheDocument();
    expect(screen.getByText('Agent ID')).toBeInTheDocument();
    expect(screen.getByText('Verdict')).toBeInTheDocument();
    expect(screen.getByText('Created')).toBeInTheDocument();
  });

  it('shows agent IDs', async () => {
    mockedFetchProposals.mockResolvedValue(mockProposals);
    renderProposals();

    await screen.findByText('prop-001');
    expect(screen.getAllByText('agent-alpha')).toHaveLength(2);
    expect(screen.getByText('agent-beta')).toBeInTheDocument();
  });

  it('shows verdict badges', async () => {
    mockedFetchProposals.mockResolvedValue(mockProposals);
    renderProposals();

    await screen.findByText('prop-001');
    expect(screen.getByText('accepted')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
    expect(screen.getByText('rejected')).toBeInTheDocument();
  });

  it('shows error message on fetch failure', async () => {
    mockedFetchProposals.mockRejectedValue(new Error('Server error'));
    renderProposals();

    expect(await screen.findByText(/Failed to load proposals/)).toBeInTheDocument();
    expect(screen.getByText(/Server error/)).toBeInTheDocument();
  });

  it('shows empty state when no proposals exist', async () => {
    mockedFetchProposals.mockResolvedValue([]);
    renderProposals();

    expect(await screen.findByText('No proposals found.')).toBeInTheDocument();
  });

  it('shows task IDs in the table', async () => {
    mockedFetchProposals.mockResolvedValue(mockProposals);
    renderProposals();

    await screen.findByText('prop-001');
    expect(screen.getAllByText('task-001')).toHaveLength(2);
    expect(screen.getByText('task-004')).toBeInTheDocument();
  });
});
