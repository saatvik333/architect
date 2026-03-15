import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { useNavigate } from 'react-router-dom';

interface TaskNodeData {
  label: string;
  status: string;
  progress: number;
  taskId: string;
  [key: string]: unknown;
}

const borderColors: Record<string, string> = {
  completed: 'border-green-500',
  running: 'border-blue-500',
  pending: 'border-gray-500',
  failed: 'border-red-500',
  blocked: 'border-amber-500',
  cancelled: 'border-gray-600',
};

const statusDotColors: Record<string, string> = {
  completed: 'bg-green-400',
  running: 'bg-blue-400',
  pending: 'bg-gray-400',
  failed: 'bg-red-400',
  blocked: 'bg-amber-400',
  cancelled: 'bg-gray-500',
};

function TaskNode({ data }: NodeProps) {
  const navigate = useNavigate();
  const { label, status, progress, taskId } = data as unknown as TaskNodeData;
  const border = borderColors[status] || borderColors.pending;
  const dot = statusDotColors[status] || statusDotColors.pending;

  const truncatedName =
    typeof label === 'string' && label.length > 24
      ? label.slice(0, 22) + '...'
      : label;

  return (
    <>
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div
        onClick={() => navigate(`/tasks/${taskId}`)}
        className={`bg-gray-800 rounded-lg border-2 ${border} px-3 py-2 cursor-pointer
          hover:bg-gray-700/80 transition-colors shadow-md min-w-[180px]`}
      >
        <div className="text-sm font-medium text-gray-200 truncate" title={String(label)}>
          {String(truncatedName)}
        </div>
        <div className="flex items-center justify-between mt-1.5 gap-2">
          <div className="flex items-center gap-1.5">
            <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
            <span className="text-xs text-gray-400 capitalize">{String(status)}</span>
          </div>
          <span className="text-xs text-gray-500">{Number(progress)}%</span>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-1 mt-1.5 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-blue-400 transition-all duration-500"
            style={{ width: `${Math.max(0, Math.min(100, Number(progress)))}%` }}
          />
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </>
  );
}

export default memo(TaskNode);
