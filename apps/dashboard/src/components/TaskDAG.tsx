import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import type { TaskStatus } from '../api/types';
import { useTaskGraph } from '../hooks/useTaskGraph';
import TaskNode from './TaskNode';

const nodeTypes = { taskNode: TaskNode };

interface TaskDAGProps {
  tasks: TaskStatus[];
}

function TaskDAG({ tasks }: TaskDAGProps) {
  const { nodes, edges, isReady } = useTaskGraph(tasks);

  if (!isReady) {
    return (
      <div className="flex items-center justify-center h-96 text-gray-500 italic">
        No tasks to visualize.
      </div>
    );
  }

  return (
    <div className="h-[600px] w-full rounded-lg border border-gray-700 overflow-hidden bg-gray-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#374151" />
        <Controls
          className="!bg-gray-800 !border-gray-700 !shadow-lg [&>button]:!bg-gray-800 [&>button]:!border-gray-700 [&>button]:!text-gray-300 [&>button:hover]:!bg-gray-700"
        />
        <MiniMap
          nodeColor="#4b5563"
          maskColor="rgba(0, 0, 0, 0.6)"
          className="!bg-gray-800 !border-gray-700"
        />
      </ReactFlow>
    </div>
  );
}

export default TaskDAG;
