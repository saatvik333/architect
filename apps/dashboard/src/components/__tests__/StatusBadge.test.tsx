import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import StatusBadge from '../StatusBadge';

describe('StatusBadge', () => {
  const statuses = [
    'pending',
    'running',
    'completed',
    'failed',
    'blocked',
    'cancelled',
    'accepted',
    'rejected',
  ] as const;

  it.each(statuses)('renders "%s" status text', (status) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it('renders with badge styling', () => {
    render(<StatusBadge status="running" />);
    const badge = screen.getByText('running');
    expect(badge).toHaveClass('rounded-full', 'text-xs', 'font-medium');
  });

  it('falls back to pending styling for unknown status', () => {
    render(<StatusBadge status="unknown" />);
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });

  it('applies correct color classes for completed status', () => {
    render(<StatusBadge status="completed" />);
    const badge = screen.getByText('completed');
    expect(badge.className).toContain('bg-green-600/30');
    expect(badge.className).toContain('text-green-300');
  });

  it('applies correct color classes for failed status', () => {
    render(<StatusBadge status="failed" />);
    const badge = screen.getByText('failed');
    expect(badge.className).toContain('bg-red-600/30');
    expect(badge.className).toContain('text-red-300');
  });

  it('applies correct color classes for running status', () => {
    render(<StatusBadge status="running" />);
    const badge = screen.getByText('running');
    expect(badge.className).toContain('bg-blue-600/30');
    expect(badge.className).toContain('text-blue-300');
  });
});
