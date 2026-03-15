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
    const badge = screen.getByText('running').closest('.status-badge');
    expect(badge).toBeInTheDocument();
  });

  it('falls back to pending styling for unknown status', () => {
    render(<StatusBadge status="unknown" />);
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });

  it('applies correct color for completed status', () => {
    render(<StatusBadge status="completed" />);
    const badge = screen.getByText('completed').closest('.status-badge') as HTMLElement;
    expect(badge.style.color).toBe('rgb(63, 185, 80)');
  });

  it('applies correct color for failed status', () => {
    render(<StatusBadge status="failed" />);
    const badge = screen.getByText('failed').closest('.status-badge') as HTMLElement;
    expect(badge.style.color).toBe('rgb(248, 81, 73)');
  });

  it('applies correct color for running status', () => {
    render(<StatusBadge status="running" />);
    const badge = screen.getByText('running').closest('.status-badge') as HTMLElement;
    expect(badge.style.color).toBe('rgb(88, 166, 255)');
  });

  it('renders a pulsing dot for running status', () => {
    const { container } = render(<StatusBadge status="running" />);
    const dot = container.querySelector('.status-dot-running');
    expect(dot).toBeInTheDocument();
  });

  it('does not render a dot for pending status', () => {
    const { container } = render(<StatusBadge status="pending" />);
    const dot = container.querySelector('.status-dot');
    expect(dot).not.toBeInTheDocument();
  });
});
