import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import TaskDetail from '../TaskDetail';
import { mockTask, mockTaskLogs, mockProposals } from '../../test/mocks/api';

vi.mock('../../api/client', () => ({
  fetchTask: vi.fn(),
  fetchTaskLogs: vi.fn(),
  fetchProposals: vi.fn(),
  cancelTask: vi.fn(),
}));

import { fetchTask, fetchTaskLogs, fetchProposals, cancelTask } from '../../api/client';

const mockedFetchTask = vi.mocked(fetchTask);
const mockedFetchTaskLogs = vi.mocked(fetchTaskLogs);
const mockedFetchProposals = vi.mocked(fetchProposals);
const mockedCancelTask = vi.mocked(cancelTask);

function renderTaskDetail(taskId = 'task-001') {
  return render(
    <MemoryRouter initialEntries={[`/tasks/${taskId}`]}>
      <Routes>
        <Route path="/tasks/:taskId" element={<TaskDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('TaskDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedFetchTaskLogs.mockResolvedValue(mockTaskLogs);
    mockedFetchProposals.mockResolvedValue(mockProposals);
  });

  it('shows loading state initially', () => {
    mockedFetchTask.mockReturnValue(new Promise(() => {}));
    renderTaskDetail();
    expect(screen.getByText('Loading task...')).toBeInTheDocument();
  });

  it('renders task metadata', async () => {
    mockedFetchTask.mockResolvedValue(mockTask);
    renderTaskDetail();

    expect(await screen.findByText('Build authentication module')).toBeInTheDocument();
    expect(screen.getByText('task-001')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
  });

  it('renders metadata labels', async () => {
    mockedFetchTask.mockResolvedValue(mockTask);
    renderTaskDetail();

    await screen.findByText('Build authentication module');
    expect(screen.getByText('Task ID')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(screen.getByText('Updated')).toBeInTheDocument();
  });

  it('shows progress percentage', async () => {
    mockedFetchTask.mockResolvedValue(mockTask);
    renderTaskDetail();

    await screen.findByText('Build authentication module');
    expect(screen.getByText('45%')).toBeInTheDocument();
  });

  it('shows cancel buttons for running task', async () => {
    mockedFetchTask.mockResolvedValue(mockTask);
    renderTaskDetail();

    expect(await screen.findByText('Cancel')).toBeInTheDocument();
    expect(screen.getByText('Force Cancel')).toBeInTheDocument();
  });

  it('does not show cancel buttons for completed task', async () => {
    mockedFetchTask.mockResolvedValue({ ...mockTask, status: 'completed' });
    renderTaskDetail();

    await screen.findByText('Build authentication module');
    expect(screen.queryByText('Cancel')).not.toBeInTheDocument();
    expect(screen.queryByText('Force Cancel')).not.toBeInTheDocument();
  });

  it('shows error state on fetch failure', async () => {
    mockedFetchTask.mockRejectedValue(new Error('Not found'));
    renderTaskDetail();

    expect(await screen.findByText(/Failed to load task/)).toBeInTheDocument();
    expect(screen.getByText(/Not found/)).toBeInTheDocument();
  });

  it('renders back to tasks link', async () => {
    mockedFetchTask.mockResolvedValue(mockTask);
    renderTaskDetail();

    await screen.findByText('Build authentication module');
    expect(screen.getByText(/Back to Tasks/)).toBeInTheDocument();
  });

  it('shows child task links', async () => {
    mockedFetchTask.mockResolvedValue(mockTask);
    renderTaskDetail();

    await screen.findByText('Build authentication module');
    expect(screen.getByText('task-002')).toBeInTheDocument();
    expect(screen.getByText('task-003')).toBeInTheDocument();
  });

  it('calls cancelTask when cancel button is clicked', async () => {
    const userEvent = (await import('@testing-library/user-event')).default;
    mockedFetchTask.mockResolvedValue(mockTask);
    mockedCancelTask.mockResolvedValue(undefined);
    const user = userEvent.setup();

    renderTaskDetail();
    const cancelBtn = await screen.findByText('Cancel');
    await user.click(cancelBtn);

    expect(mockedCancelTask).toHaveBeenCalledWith('task-001', false);
  });

  it('calls cancelTask with force=true for Force Cancel', async () => {
    const userEvent = (await import('@testing-library/user-event')).default;
    mockedFetchTask.mockResolvedValue(mockTask);
    mockedCancelTask.mockResolvedValue(undefined);
    const user = userEvent.setup();

    renderTaskDetail();
    const forceBtn = await screen.findByText('Force Cancel');
    await user.click(forceBtn);

    expect(mockedCancelTask).toHaveBeenCalledWith('task-001', true);
  });
});
