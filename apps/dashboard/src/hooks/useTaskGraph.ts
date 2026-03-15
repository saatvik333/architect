import { useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import dagre from '@dagrejs/dagre';
import type { TaskStatus } from '../api/types';

const NODE_WIDTH = 200;
const NODE_HEIGHT = 80;

function buildGraph(tasks: TaskStatus[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 });

  const taskMap = new Map(tasks.map((t) => [t.task_id, t]));

  for (const task of tasks) {
    g.setNode(task.task_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  const edges: Edge[] = [];
  for (const task of tasks) {
    for (const childId of task.children) {
      if (taskMap.has(childId)) {
        const edgeId = `${task.task_id}->${childId}`;
        g.setEdge(task.task_id, childId);
        edges.push({
          id: edgeId,
          source: task.task_id,
          target: childId,
          animated: task.status === 'running',
          style: { stroke: '#6b7280' },
        });
      }
    }
  }

  dagre.layout(g);

  const nodes: Node[] = tasks.map((task) => {
    const pos = g.node(task.task_id);
    return {
      id: task.task_id,
      type: 'taskNode',
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
      data: {
        label: task.name,
        status: task.status,
        progress: task.progress,
        taskId: task.task_id,
      },
    };
  });

  return { nodes, edges };
}

export interface UseTaskGraphResult {
  nodes: Node[];
  edges: Edge[];
  isReady: boolean;
}

export function useTaskGraph(tasks: TaskStatus[] | null): UseTaskGraphResult {
  return useMemo(() => {
    if (!tasks || tasks.length === 0) {
      return { nodes: [], edges: [], isReady: false };
    }
    const { nodes, edges } = buildGraph(tasks);
    return { nodes, edges, isReady: true };
  }, [tasks]);
}
