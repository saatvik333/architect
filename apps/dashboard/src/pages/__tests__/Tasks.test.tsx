import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Tasks from '../Tasks';
import { mockTasks } from '../../test/mocks/api';

vi.mock('../../api/client', () => ({
  fetchTasks: vi.fn(),
}));

import { fetchTasks } from '../../api/client';

const mockedFetchTasks = vi.mocked(fetchTasks);

function renderTasks() {
  return render(
    <MemoryRouter>
      <Tasks />
    </MemoryRouter>,
  );
}

describe('Tasks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    mockedFetchTasks.mockReturnValue(new Promise(() => {})); // never resolves
    renderTasks();
    expect(screen.getByText('Loading tasks...')).toBeInTheDocument();
  });

  it('renders task table when data loads', async () => {
    mockedFetchTasks.mockResolvedValue(mockTasks);
    renderTasks();

    expect(await screen.findByText('Build authentication module')).toBeInTheDocument();
    expect(screen.getByText('Implement login endpoint')).toBeInTheDocument();
    expect(screen.getByText('Write unit tests')).toBeInTheDocument();
    expect(screen.getByText('Database migration')).toBeInTheDocument();
  });

  it('renders table column headers', async () => {
    mockedFetchTasks.mockResolvedValue(mockTasks);
    renderTasks();

    await screen.findByText('Build authentication module');
    expect(screen.getByText('ID')).toBeInTheDocument();
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Progress')).toBeInTheDocument();
    expect(screen.getByText('Created')).toBeInTheDocument();
  });

  it('shows task IDs in the table', async () => {
    mockedFetchTasks.mockResolvedValue(mockTasks);
    renderTasks();

    expect(await screen.findByText('task-001')).toBeInTheDocument();
    expect(screen.getByText('task-002')).toBeInTheDocument();
  });

  it('shows status badges for each task', async () => {
    mockedFetchTasks.mockResolvedValue(mockTasks);
    renderTasks();

    await screen.findByText('Build authentication module');
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
  });

  it('shows error message on fetch failure', async () => {
    mockedFetchTasks.mockRejectedValue(new Error('Network error'));
    renderTasks();

    expect(await screen.findByText(/Failed to load tasks/)).toBeInTheDocument();
    expect(screen.getByText(/Network error/)).toBeInTheDocument();
  });

  it('shows empty state when no tasks exist', async () => {
    mockedFetchTasks.mockResolvedValue([]);
    renderTasks();

    expect(await screen.findByText('No tasks found.')).toBeInTheDocument();
  });

  it('renders the page heading', () => {
    mockedFetchTasks.mockReturnValue(new Promise(() => {}));
    renderTasks();
    expect(screen.getByText('Tasks')).toBeInTheDocument();
  });
});
