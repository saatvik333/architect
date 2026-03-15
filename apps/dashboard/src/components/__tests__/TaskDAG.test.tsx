import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { TaskStatus } from '../../api/types';
import TaskDAG from '../TaskDAG';

// Mock @xyflow/react since jsdom doesn't support the full rendering pipeline
vi.mock('@xyflow/react', () => {
  const MockReactFlow = ({ nodes, edges, children }: { nodes: unknown[]; edges: unknown[]; children?: React.ReactNode }) => (
    <div data-testid="react-flow" data-node-count={nodes.length} data-edge-count={edges.length}>
      {(nodes as Array<{ id: string; data: { label: string } }>).map((node) => (
        <div key={node.id} data-testid={`node-${node.id}`}>
          {node.data.label}
        </div>
      ))}
      {children}
    </div>
  );

  return {
    ReactFlow: MockReactFlow,
    MiniMap: () => <div data-testid="minimap" />,
    Controls: () => <div data-testid="controls" />,
    Background: () => <div data-testid="background" />,
    BackgroundVariant: { Dots: 'dots' },
    Handle: () => null,
    Position: { Top: 'top', Bottom: 'bottom' },
  };
});

const makeTasks = (overrides: Partial<TaskStatus>[] = []): TaskStatus[] => {
  const defaults: TaskStatus[] = [
    {
      task_id: 'task-1',
      name: 'Root Task',
      status: 'running',
      progress: 50,
      children: ['task-2', 'task-3'],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T01:00:00Z',
    },
    {
      task_id: 'task-2',
      name: 'Child A',
      status: 'completed',
      progress: 100,
      children: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T01:00:00Z',
    },
    {
      task_id: 'task-3',
      name: 'Child B',
      status: 'pending',
      progress: 0,
      children: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T01:00:00Z',
    },
  ];
  return overrides.length > 0
    ? overrides.map((o, i) => ({ ...defaults[i % defaults.length], ...o }))
    : defaults;
};

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('TaskDAG', () => {
  it('renders the empty state when given an empty task list', () => {
    renderWithRouter(<TaskDAG tasks={[]} />);
    expect(screen.getByText('No tasks to visualize.')).toBeInTheDocument();
  });

  it('renders ReactFlow with correct node count', () => {
    const tasks = makeTasks();
    renderWithRouter(<TaskDAG tasks={tasks} />);

    const flow = screen.getByTestId('react-flow');
    expect(flow).toBeInTheDocument();
    expect(flow.getAttribute('data-node-count')).toBe('3');
  });

  it('renders edges between parent and child tasks', () => {
    const tasks = makeTasks();
    renderWithRouter(<TaskDAG tasks={tasks} />);

    const flow = screen.getByTestId('react-flow');
    expect(flow.getAttribute('data-edge-count')).toBe('2');
  });

  it('renders nodes with task names', () => {
    const tasks = makeTasks();
    renderWithRouter(<TaskDAG tasks={tasks} />);

    expect(screen.getByText('Root Task')).toBeInTheDocument();
    expect(screen.getByText('Child A')).toBeInTheDocument();
    expect(screen.getByText('Child B')).toBeInTheDocument();
  });

  it('renders minimap and controls', () => {
    const tasks = makeTasks();
    renderWithRouter(<TaskDAG tasks={tasks} />);

    expect(screen.getByTestId('minimap')).toBeInTheDocument();
    expect(screen.getByTestId('controls')).toBeInTheDocument();
  });

  it('ignores edges to non-existent children', () => {
    const tasks: TaskStatus[] = [
      {
        task_id: 'task-1',
        name: 'Solo',
        status: 'running',
        progress: 25,
        children: ['task-nonexistent'],
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T01:00:00Z',
      },
    ];
    renderWithRouter(<TaskDAG tasks={tasks} />);

    const flow = screen.getByTestId('react-flow');
    expect(flow.getAttribute('data-edge-count')).toBe('0');
  });
});
